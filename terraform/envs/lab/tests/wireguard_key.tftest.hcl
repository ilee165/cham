# WR-07 (2026-08-13 review): the root validates wg_peer_public_key too, so a
# never-set repository secret (CI passes TF_VAR_wg_peer_public_key from
# secrets.WG_PEER_PUBLIC_KEY) dies at plan time in the workflow logs instead
# of billing a hub VM whose WireGuard config fails on first boot.
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

run "prose_key_is_rejected" {
  command = plan

  variables {
    wg_peer_public_key = "laptop-wireguard-public-key"
  }

  expect_failures = [var.wg_peer_public_key]
}
