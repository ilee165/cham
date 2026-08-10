# PR #11 review of NEW-IN-04: the DenyOtherSpokes list contract.
# alltrue([]) is true, so an empty spoke_address_spaces used to pass plan and
# render an NSG rule with no source form — which ARM rejects only at apply.
# The list must also contain this spoke's own address_space, because it is
# defined as the complete set of lab spoke CIDRs (own-spoke traffic is
# admitted earlier by AllowIntraSpoke).
#
# mock_provider keeps this credential-free: run `terraform test` from
# terraform/modules/spoke (init downloads the provider schema only).
mock_provider "azurerm" {}

variables {
  name                 = "app"
  location             = "eastus2"
  resource_group_name  = "rg-test"
  address_space        = "10.10.4.0/22"
  subnets              = { workload = "10.10.4.0/24" }
  hub_vnet_id          = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-hub"
  hub_vnet_name        = "vnet-hub"
  hub_address_space    = "10.10.0.0/22"
  hub_nva_ip           = "10.10.0.10"
  spoke_address_spaces = ["10.10.4.0/22", "10.10.8.0/22"]
  # Structurally valid ed25519 wire format with an all-zero key: decodes at
  # plan time, is not (and cannot be) a real credential.
  ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA plan-test"
}

run "deny_rule_carries_the_configured_spoke_list" {
  command = plan

  assert {
    condition = contains(
      one([for r in azurerm_network_security_group.spoke.security_rule :
      r.source_address_prefixes if r.name == "DenyOtherSpokes"]),
    "10.10.8.0/22")
    error_message = "DenyOtherSpokes does not include the other configured spoke CIDR"
  }

  assert {
    condition = length(regexall(
      "10\\.10\\.0\\.0/16",
      jsonencode([for r in azurerm_network_security_group.spoke.security_rule :
    r.source_address_prefix if r.name == "DenyOtherSpokes"]))) == 0
    error_message = "DenyOtherSpokes still hard-codes the 10.10.0.0/16 supernet"
  }
}

run "an_empty_spoke_list_is_rejected" {
  command = plan

  variables {
    spoke_address_spaces = []
  }

  expect_failures = [var.spoke_address_spaces]
}

run "a_list_missing_this_spokes_own_space_is_rejected" {
  command = plan

  variables {
    spoke_address_spaces = ["10.10.8.0/22"]
  }

  expect_failures = [var.spoke_address_spaces]
}

run "a_leading_zero_spoke_entry_is_rejected" {
  command = plan

  variables {
    spoke_address_spaces = ["010.010.4.0/22", "10.10.4.0/22"]
  }

  expect_failures = [var.spoke_address_spaces]
}
