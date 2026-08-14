# WR-07 (2026-08-13 review): wg_peer_public_key renders straight into the
# hub's cloud-init WireGuard config. An empty or malformed value (e.g. a
# repository secret that was never set) passes planning, Azure creates and
# bills the VM, and WireGuard setup fails on first boot — the advertised
# hybrid path is unusable while the meter runs. A WireGuard public key is
# exactly 32 bytes base64-encoded: 43 base64 characters plus one '='.
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
  # 43 base64 chars + '=' — shape-valid, self-describingly not a credential.
  wg_peer_public_key           = "PlanOnlyTestPeerPublicKeyNotRealCredential0="
  lab_zone                     = "lab.example.test"
  spoke_address_spaces         = ["10.10.4.0/22", "10.10.8.0/22"]
  resolver_inbound_subnet_cidr = "10.10.2.0/28"
}

run "shape_valid_key_passes" {
  command = plan
}

run "empty_key_is_rejected" {
  command = plan

  variables {
    wg_peer_public_key = ""
  }

  expect_failures = [var.wg_peer_public_key]
}

run "whitespace_key_is_rejected" {
  command = plan

  variables {
    wg_peer_public_key = " "
  }

  expect_failures = [var.wg_peer_public_key]
}

run "prose_key_is_rejected" {
  command = plan

  variables {
    wg_peer_public_key = "laptop-wireguard-public-key"
  }

  expect_failures = [var.wg_peer_public_key]
}

run "wrong_length_key_is_rejected" {
  command = plan

  variables {
    # 44 base64 chars before the '=' — one too many.
    wg_peer_public_key = "PlanOnlyTestPeerPublicKeyNotARealCredential0="
  }

  expect_failures = [var.wg_peer_public_key]
}
