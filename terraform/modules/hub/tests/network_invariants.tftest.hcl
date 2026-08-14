# WR-06 (2026-08-13 review): the subnets carved from the hub VNet — VPN,
# shared, and the resolver inbound subnet — must lie INSIDE address_space and
# be pairwise disjoint. These are containment invariants, not the disjointness
# the top-level routed networks need (that lives in the envs/lab root): a hub
# subnet disjoint from the hub range would be the bug, not the fix. A
# violation used to plan cleanly and fail at Azure apply (or worse, deploy a
# subnet whose traffic silently bypasses the VPN/shared NSG boundaries).
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
  wg_peer_public_key   = "PlanOnlyTestPeerPublicKeyNotRealCredential0="
  lab_zone             = "lab.example.test"
  spoke_address_spaces = ["10.10.4.0/22", "10.10.8.0/22"]
  # Default layout: vpn 10.10.0.0/27, shared 10.10.1.0/24, resolver inbound
  # boundary-adjacent right after the shared subnet.
  resolver_inbound_subnet_cidr = "10.10.2.0/28"
}

run "hub_subnet_invariants_hold_on_default_layout" {
  command = plan
}

run "vpn_subnet_outside_address_space_is_rejected" {
  command = plan

  variables {
    vpn_subnet_cidr = "10.99.0.0/27"
  }

  expect_failures = [var.vpn_subnet_cidr]
}

run "shared_subnet_overlapping_vpn_subnet_is_rejected" {
  command = plan

  variables {
    # /26 starting at the VNet base swallows the whole 10.10.0.0/27 VPN subnet.
    shared_subnet_cidr = "10.10.0.0/26"
  }

  expect_failures = [var.shared_subnet_cidr]
}

run "resolver_inbound_outside_hub_range_is_rejected" {
  command = plan

  variables {
    resolver_inbound_subnet_cidr = "10.99.2.0/28"
  }

  expect_failures = [var.resolver_inbound_subnet_cidr]
}

run "resolver_inbound_colliding_with_vpn_subnet_is_rejected" {
  command = plan

  variables {
    resolver_inbound_subnet_cidr = "10.10.0.0/28"
  }

  expect_failures = [var.resolver_inbound_subnet_cidr]
}
