# Phase 3 Checkpoint C Evidence — Closeout and Validation

Captured 2026-08-06 after the Checkpoint B window closed.

## Mandatory closeout (2.6)

Executed in plan order whether or not gates had passed:

| Step | Result |
| --- | --- |
| 1. Hub `wg-quick@wg0` disabled and stopped; key/config preserved | `true` |
| 2. Laptop `wg0` brought down | `true` |
| 3. Spatium Phase 3 profiles stopped; persistent volumes retained | `true` (8 volumes) |
| 4. Deallocation issued for app, hub, and mgmt (defensive no-op) | `true` |
| 5. Instance view confirmed `VM deallocated` for all three | `true` |
| 6. `enable_private_resolver = false` and zero resolver resources | `true` |
| 7. Watchdog cancelled only after step 5 was proven | `true` |

Final power states read from the Azure control plane, not inferred from
command exit codes:

| VM | Power state |
| --- | --- |
| `vm-hub-ddi` | `VM deallocated` |
| `vm-test-app` | `VM deallocated` |
| `vm-test-mgmt` | `VM deallocated` |

## Operator-active setup time

Timestamps captured during the approved window show watchdog arm at
`2026-08-06T04:03:59Z` and the fresh-lease trigger — after the full hub
bring-up, key verification, tunnel gates, and app start — at
`2026-08-06T04:17:31Z`. Operator-active setup was under ten minutes; the
whole live window used roughly 25 of 60 authorized minutes. No VM was
restarted for documentation validation.

## Validation suite (Task 3.5)

| Check | Result |
| --- | --- |
| `git diff --check` | pass |
| `terraform fmt -check -recursive` | pass |
| `terraform validate` (envs/lab) | `Success! The configuration is valid.` |
| `tflint --chdir=terraform/envs/lab --recursive` | pass (exit 0, no findings) |
| `checkov -d terraform` | 38 passed / 0 failed / 15 skipped |

## Secret and evidence scan (Task 3.6)

| Check | Result |
| --- | --- |
| Tracked files containing local SSH/WireGuard private key material | `0` |
| Tracked `wg0.conf`, tfvars, backend config, state, or saved plan | `0` |

## Post-session drift check (Task 3.7)

| Check | Result |
| --- | --- |
| Refresh-backed plan detailed exit code | `0` |
| Plan result | `No changes` (0 warnings) |

## Checkpoint D — destroy (executed 2026-08-06)

The operator explicitly chose Option 2 (destroy) and then separately
approved the exact saved artifact before apply.

| Step | Result |
| --- | --- |
| Fresh saved destroy plan from current state and `HEAD` (`5fb845e`) | `Plan: 0 to add, 0 to change, 36 to destroy` |
| Complete deletion summary reviewed by operator | `true` |
| Artifact SHA-256 approved | `900e717990e711a7f2b3a57b76cffc4c9aba56af6b7378a93647c6d1bbf43785` |
| Hash re-verified immediately before apply | `true` |
| Apply of that exact artifact | `0 added, 0 changed, 36 destroyed` (exit 0) |
| Raw `terraform destroy` / `-auto-approve` used | `false` |

Post-destroy verification:

| Check | Result |
| --- | --- |
| `rg-cham-lab` exists | `false` |
| Subscription-wide VMs / public IPs / Private DNS zones / budgets | `0 / 0 / 0 / 0` |
| Resolver resources | `0` |
| `rg-cham-tfstate` retained with bootstrap state storage | `true` (1 resource) |
| Remaining resource groups | `NetworkWatcherRG`, `rg-cham-tfstate` |
| Lab state addresses remaining | `0` |
| Fresh recreation plan generates for review | `true` (`36 to add`, detailed exit `2`) |
| Recreation plan applied | `false` |
