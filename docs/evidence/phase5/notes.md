# Phase 5 evidence — CI/CD pipeline

Every workflow in this repo is only testable by running it, so each one owes
at least one real run URL here before the phase closes. Entries marked
PENDING have not been run yet; nothing in this file describes a run that did
not happen.

## Configuration state (verified 2026-08-10)

| Item | State | How verified |
|---|---|---|
| Repo slug | `ilee165/cham` | `gh repo view --json nameWithOwner` |
| `lab` environment | exists, required reviewer `ilee165`, branch policy | `gh api repos/ilee165/cham/environments/lab` |
| Federated credentials | 3 subjects, ID-embedded form (`repo:ilee165@140726424/cham@1318631051:{ref:refs/heads/main,pull_request,environment:lab}`) | `az ad app federated-credential list` |
| RBAC | Contributor at subscription scope + Storage Blob Data Contributor on the state account | Phase 4 configuration, unchanged |
| Repository secrets | 9 (3 OIDC identifiers, 4 lab config, 2 Cloudflare tokens) | `gh secret list` |
| `BUDGET_START_DATE` variable | `2026-08-01T00:00:00Z` | `gh variable list` |
| Lab resource group | absent (destroyed after Phase 4) | `az group exists --name rg-cham-lab` → `false` |
| Branch protection on `main` | strict, requires `Credential-free Terraform checks` + `tests` | `gh api .../branches/main/protection` |
| `CLOUDFLARE_API_TOKEN` out of the repository scope | yes — repository level holds `CLOUDFLARE_API_TOKEN_RO` alone | `gh secret list` / `gh secret list --env lab` |
| `cloudflare-prod` environment holding the edit token | PENDING — the 2026-08-11 review found `lab` also gates `destroy.yml`, so the token must move to its own environment | — |
| Bootstrap `tfplans/` expiry policy applied | rule `expire-saved-plans`, prefix `tfplans/`, 7 days for base blobs and versions | `az storage account management-policy show` |

## Local gate re-run before execution (2026-08-10)

Carried-forward quality-gate item from Phase 4, re-run against the Phase 5
working tree:

| Gate | Result |
|---|---|
| `uv run pytest` | 365 passed |
| `uv run ruff check .` | All checks passed |
| `actionlint` | clean |
| `terraform fmt -check -recursive terraform` | clean |
| `terraform validate` (bootstrap, envs/lab, cloudflare) | 3× valid |
| `tflint --recursive` (shared config, azurerm 0.32.0) | 0 issues |
| `checkov -d terraform` | 52 passed, 0 failed, 15 skipped |

## Workflow runs

| # | Proof | Run | Outcome |
|---|---|---|---|
| 1 | PR → credential-free gate blocks merge until green; no plan, no cloud call on a PR | PR [#12](https://github.com/ilee165/cham/pull/12), runs [31496365494](https://github.com/ilee165/cham/actions/runs/31496365494) (Terraform) and [31496365506](https://github.com/ilee165/cham/actions/runs/31496365506) (reconciler) | Both required checks green. Both saved-plan jobs **skipped** — `Saved plan from current main` and `Saved Cloudflare plan from current main` never started, so no credential was requested and no cloud call was made. Merge state moved `BLOCKED` → `CLEAN` only after both checks reported. |
| 2 | Dispatched saved plan → private blob custody → environment-gated apply (lab) | PENDING | — |
| 3 | Same custody chain for the Cloudflare stack | PENDING | — |
| 4 | Drift, green path — converged, silent, no issue | PENDING | — |
| 5 | Drift, red path — green run plus a labelled issue carrying the diff | PENDING | — |
| 6 | Two-stage destroy from the Actions UI | PENDING | — |

## Custody-chain evidence (run 2/3)

To be captured per the plan's Task 5 Step 2: the blob path, the artifact file
list, the matching hashes, and the absence of the complete delta from the
public run log.
