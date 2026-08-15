# WR-06 (2026-08-13 review): the top-level routed networks — hub VNet, both
# spoke VNets, the on-prem range, and the WireGuard transfer network — must be
# pairwise DISJOINT. They meet in UDRs, NSG rules, BIND ACLs, WireGuard
# AllowedIPs, and NAT sources; an overlap plans cleanly and then hairpins or
# blackholes traffic depending on which table wins. Containment invariants for
# subnets carved from the hub range live in the hub and dns-resolver module
# tests — here, the root is the only place that sees every routed network at
# once.
#
# mock_provider keeps this credential-free: run
#   terraform init -backend=false && terraform test
# from terraform/envs/lab (init downloads the provider schema only).
mock_provider "azurerm" {}

# Fixture preamble intentionally duplicated across the five *.tftest.hcl
# files that need dummy keys/addresses (2026-08-15 standards review): tftest
# has no include mechanism, and the one sharing vehicle — a committed tfvars
# auto-loaded by `terraform test` — would need a carve-out in the .gitignore
# rule keeping tfvars out of this public repo. Self-contained files win.
variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  home_ip         = "203.0.113.5/32"
  # Structurally valid ed25519 wire format with an all-zero key: decodes at
  # plan time, is not (and cannot be) a real credential.
  ssh_public_key     = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA plan-test"
  wg_peer_public_key = "PlanOnlyTestPeerPublicKeyNotRealCredential0="
  alert_email        = "ops@example.test"
  budget_start_date  = "2026-08-01T00:00:00Z"
}

run "routed_networks_disjoint_on_defaults" {
  command = plan
}

# The review's exact repro class: an on-prem range wide enough to swallow the
# hub and spoke /22s. Every UDR and AllowedIPs entry for on-prem then shadows
# in-cloud destinations.
run "onprem_swallowing_the_hub_range_is_rejected" {
  command = plan

  variables {
    onprem_address_space = "10.10.0.0/16"
  }

  expect_failures = [azurerm_resource_group.lab]
}

# Overlap between the two user-settable variables themselves.
run "onprem_overlapping_wireguard_transfer_is_rejected" {
  command = plan

  variables {
    onprem_address_space = "172.16.0.0/16"
  }

  expect_failures = [azurerm_resource_group.lab]
}

# Boundary-adjacent is NOT overlap: 10.10.12.0/22 starts one address after the
# mgmt spoke's 10.10.8.0/22 ends. The disjointness arithmetic must not round
# adjacency up into a false collision.
run "boundary_adjacent_networks_pass" {
  command = plan

  variables {
    onprem_address_space = "10.10.12.0/22"
  }
}
