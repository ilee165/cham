# WR-06 (2026-08-13 review): the resolver inbound and outbound subnets are
# carved from the hub VNet by THIS module, so this module is where their
# relationships are provable: contained within the hub range, mutually
# disjoint, and clear of the hub subnets that already exist there (VPN,
# shared). A violation used to plan cleanly and fail at Azure apply — behind
# the cost gate, that failure would burn a deliberately-budgeted resolver
# session on a subnet collision.
#
# The validations are variable-level, so they hold even while enabled=false —
# a bad CIDR is rejected the moment it is written, not on the day the
# cost-gated flag is finally flipped.
#
# mock_provider keeps this credential-free: run `terraform test` from
# terraform/modules/dns-resolver (init downloads the provider schema only).
mock_provider "azurerm" {}

variables {
  enabled               = false
  location              = "eastus2"
  resource_group_name   = "rg-test"
  hub_vnet_id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-hub"
  hub_vnet_name         = "vnet-hub"
  hub_nva_ip            = "10.10.0.10"
  onprem_address_space  = "192.168.50.0/24"
  wg_transfer_cidr      = "172.16.0.0/24"
  forwarding_vnet_links = {}
  lab_zone              = "lab.example.test"
  hub_dns_ip            = "10.10.0.10"
  hub_address_space     = "10.10.0.0/22"
  # The hub's default VPN and shared subnets.
  hub_reserved_subnet_cidrs = ["10.10.0.0/27", "10.10.1.0/24"]
}

run "resolver_subnet_invariants_hold_on_default_layout" {
  command = plan
}

run "outbound_subnet_outside_hub_range_is_rejected" {
  command = plan

  variables {
    outbound_subnet_cidr = "10.11.0.16/28"
  }

  expect_failures = [var.outbound_subnet_cidr]
}

run "inbound_subnet_overlapping_outbound_subnet_is_rejected" {
  command = plan

  variables {
    # Identical to the default outbound subnet.
    inbound_subnet_cidr = "10.10.2.16/28"
  }

  expect_failures = [var.inbound_subnet_cidr]
}

run "inbound_subnet_colliding_with_reserved_hub_subnet_is_rejected" {
  command = plan

  variables {
    # Inside the hub's shared subnet 10.10.1.0/24.
    inbound_subnet_cidr = "10.10.1.16/28"
  }

  expect_failures = [var.inbound_subnet_cidr]
}

run "outbound_subnet_colliding_with_reserved_hub_subnet_is_rejected" {
  command = plan

  variables {
    # Inside the hub's VPN subnet 10.10.0.0/27.
    outbound_subnet_cidr = "10.10.0.0/28"
  }

  expect_failures = [var.outbound_subnet_cidr]
}
