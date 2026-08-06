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

## Checkpoint D

Retain-or-destroy remains an explicit, separate operator decision. All
compute is deallocated; idle non-compute charges continue for managed disks,
the static hub public IP, Private DNS, networking metadata, and state
storage.
