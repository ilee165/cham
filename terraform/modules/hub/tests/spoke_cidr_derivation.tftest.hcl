# WR-02 (2026-08-08 review): DNS/HTTP NSG sources, the BIND ACL, and the NAT
# script must all follow the configured hub + spoke CIDRs — previously they
# hard-coded 10.10.0.0/16 while the transit rules followed the variable.
#
# mock_provider keeps this credential-free: run `terraform test` from
# terraform/modules/hub (init downloads the provider schema only).
mock_provider "azurerm" {}

# Fixture preamble intentionally duplicated across the five *.tftest.hcl
# files that need dummy keys/addresses (2026-08-15 standards review): tftest
# has no include mechanism, and the one sharing vehicle — a committed tfvars
# auto-loaded by `terraform test` — would need a carve-out in the .gitignore
# rule keeping tfvars out of this public repo. Self-contained files win.
variables {
  location            = "eastus2"
  resource_group_name = "rg-test"
  home_ip             = "203.0.113.5/32"
  # Structurally valid ed25519 wire format with an all-zero key: decodes at
  # plan time, is not (and cannot be) a real credential.
  ssh_public_key       = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA plan-test"
  onprem_address_space = "192.168.50.0/24"
  onprem_dns_ip        = "192.168.50.2"
  # 43 base64 chars + '=' (WR-07 shape) — self-describingly not a credential.
  wg_peer_public_key = "PlanOnlyTestPeerPublicKeyNotRealCredential0="
  lab_zone           = "lab.example.test"
  # One spoke far outside 10.10.0.0/16 plus one inside it: every derived rule
  # must carry both.
  spoke_address_spaces         = ["192.168.60.0/24", "10.10.4.0/24"]
  resolver_inbound_subnet_cidr = "10.10.2.0/28"
}

run "derived_rules_follow_a_non_default_spoke_cidr" {
  command = plan

  assert {
    condition = contains(
      one([for r in azurerm_network_security_group.hub.security_rule :
      r.source_address_prefixes if r.name == "AllowDNSFromRFC1918"]),
    "192.168.60.0/24")
    error_message = "AllowDNSFromRFC1918 does not include the configured non-default spoke CIDR"
  }

  assert {
    condition = contains(
      one([for r in azurerm_network_security_group.hub.security_rule :
      r.source_address_prefixes if r.name == "AllowHTTPInternal"]),
    "192.168.60.0/24")
    error_message = "AllowHTTPInternal does not include the configured non-default spoke CIDR"
  }

  assert {
    condition = length(regexall(
      "allow-query \\{[^}]*192\\.168\\.60\\.0/24",
    base64decode(azurerm_linux_virtual_machine.hub.custom_data))) > 0
    error_message = "BIND allow-query ACL does not include the configured spoke CIDR"
  }

  assert {
    condition = length(regexall(
      "-s 192\\.168\\.60\\.0/24 -o \"\\$outbound_interface\" -j MASQUERADE",
    base64decode(azurerm_linux_virtual_machine.hub.custom_data))) > 0
    error_message = "NAT masquerade rules do not include the configured spoke CIDR"
  }

  assert {
    condition = length(regexall(
      "-s 192\\.168\\.60\\.0/24 -d 192\\.168\\.50\\.0/24 -j RETURN",
    base64decode(azurerm_linux_virtual_machine.hub.custom_data))) > 0
    error_message = "NAT exclusion (RETURN) rules do not pair the spoke with the on-prem destination"
  }

  assert {
    condition = length(regexall(
      "10\\.10\\.0\\.0/16",
    base64decode(azurerm_linux_virtual_machine.hub.custom_data))) == 0
    error_message = "cloud-init still hard-codes 10.10.0.0/16 somewhere"
  }
}

# NEW-WR-02 (2026-08-10 review): address_space and every spoke entry feed the
# public-IP hub's BIND ACLs, NSG allow rules, and NAT sources via
# internal_cidrs, so a public or over-broad value must die at plan time —
# not become an open recursive resolver (valid public CIDR) or a boot-time
# named.conf/iptables failure (malformed string).

run "public_spoke_cidr_is_rejected" {
  command = plan

  variables {
    spoke_address_spaces = ["0.0.0.0/0"]
  }

  expect_failures = [var.spoke_address_spaces]
}

run "public_address_space_is_rejected" {
  command = plan

  variables {
    address_space = "8.8.0.0/16"
  }

  expect_failures = [var.address_space]
}

# PR #11 review: Terraform's CIDR functions read leading-zero octets as
# decimal (010.010.0.0/16 == 10.10.0.0/16 to the RFC1918 check), but the
# original string renders into iptables, which reads them as octal
# (8.8.0.0/16) — bypassing the security property the validation enforces.

run "leading_zero_spoke_cidr_is_rejected" {
  command = plan

  variables {
    spoke_address_spaces = ["010.010.4.0/24"]
  }

  expect_failures = [var.spoke_address_spaces]
}

run "leading_zero_address_space_is_rejected" {
  command = plan

  variables {
    address_space = "010.010.0.0/16"
  }

  expect_failures = [var.address_space]
}
