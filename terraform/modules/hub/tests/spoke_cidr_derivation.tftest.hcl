# WR-02 (2026-08-08 review): DNS/HTTP NSG sources, the BIND ACL, and the NAT
# script must all follow the configured hub + spoke CIDRs — previously they
# hard-coded 10.10.0.0/16 while the transit rules followed the variable.
#
# mock_provider keeps this credential-free: run `terraform test` from
# terraform/modules/hub (init downloads the provider schema only).
mock_provider "azurerm" {}

variables {
  location            = "eastus2"
  resource_group_name = "rg-test"
  home_ip             = "203.0.113.5/32"
  # Structurally valid ed25519 wire format with an all-zero key: decodes at
  # plan time, is not (and cannot be) a real credential.
  ssh_public_key       = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA plan-test"
  onprem_address_space = "192.168.50.0/24"
  onprem_dns_ip        = "192.168.50.2"
  wg_peer_public_key   = "PlanOnlyTestPeerPublicKeyNotARealCredential0="
  lab_zone             = "lab.example.test"
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
