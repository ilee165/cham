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
| Federated credentials | 4 subjects, ID-embedded form (`repo:ilee165@140726424/cham@1318631051:{ref:refs/heads/main,pull_request,environment:lab,environment:cloudflare-prod}`); prefix re-confirmed 2026-08-12 | `az ad app federated-credential list`, `gh api .../actions/oidc/customization/sub` |
| 4th credential for `…:environment:cloudflare-prod` | created 2026-08-12 as `cham-cloudflare-prod`. Required because a job declaring an environment presents that environment's subject, not the branch subject — without it the Cloudflare apply job fails `AADSTS700213` at `azure/login@v2` and never reaches its own remote state. Verified by case-sensitive comparison, not by eye: the stored subject equals the live `sub_claim_prefix` concatenated with `:environment:cloudflare-prod`, and issuer and audience match exactly | `az ad app federated-credential list` compared against `gh api .../actions/oidc/customization/sub` |
| RBAC | Contributor at subscription scope + Storage Blob Data Contributor on the state account | Phase 4 configuration, unchanged |
| Repository secrets | 9 (3 OIDC identifiers, 4 lab config, 2 Cloudflare tokens) | `gh secret list` |
| `BUDGET_START_DATE` variable | `2026-08-01T00:00:00Z` | `gh variable list` |
| Lab resource group | absent (destroyed after Phase 4) | `az group exists --name rg-cham-lab` → `false` |
| Branch protection on `main` | strict, requires `Credential-free Terraform checks` + `tests` | `gh api .../branches/main/protection` |
| `CLOUDFLARE_API_TOKEN` out of the repository scope | yes — repository level holds `CLOUDFLARE_API_TOKEN_RO` alone | `gh secret list` / `gh secret list --env lab` |
| `cloudflare-prod` environment holding the edit token | exists (verified 2026-08-11) — protection rules `required_reviewers` + `branch_policy`, custom branch policy naming `main` and nothing else, environment secret `CLOUDFLARE_API_TOKEN`. Both assertions `apply.yml` makes at job start therefore hold. The `lab` environment carries no secrets, so the edit token is no longer inside `destroy.yml`'s approval scope | `gh api repos/ilee165/cham/environments/cloudflare-prod`, `.../environments/cloudflare-prod/{secrets,deployment-branch-policies}` |
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
| 4 | Drift, green path — converged, silent, no issue | Run [31596160048](https://github.com/ilee165/cham/actions/runs/31596160048), dispatched on `main` at `0dd83cf` | Green and silent. Public edge checked first and credential-free: `[cloudflare-public] converged (0 changes)` / `summary: 0 add, 0 update, 0 delete across 1 edge(s)`. `Report drift` **skipped** — no issue opened, which is the whole point of the green path. Azure edge correctly skipped on an absent zone: the gate step reports `LOGIN: success  ZONE: success  AZURE: skipped`, so the skip was a determinate "the zone is not there", never an assumed `false`. |
| 5 | Drift, red path — green run plus a labelled issue carrying the diff | PENDING | — |
| 6 | Two-stage destroy from the Actions UI | PENDING | — |

## OIDC, first real exercise (2026-08-12)

The federation was configured 2026-08-06 and, as noted at the time, never
actually exercised — `plan.yml`'s Azure-touching job is conditional and was
skipped on every branch run, so a green PR proved nothing about it. Drift run
[31596160048](https://github.com/ilee165/cham/actions/runs/31596160048) is the
first run in which GitHub minted a token and Azure accepted it:
`Azure login (OIDC)` → `Subscription is set successfully.`, under the
`…:ref:refs/heads/main` subject. The `…:environment:cloudflare-prod` subject
remains unexercised until run 3.

## Issue hygiene

Issue #6 (`DNS drift detected — 2026-08-08`) was closed 2026-08-12. It was
raised by the 06:46Z cron carrying the two ADDs that Phase 4 task C2 applied
later the same day, so it had been resolved for four days and merely left
open. Closing it is not cosmetic: the Phase 5 workflow keeps exactly one
drift-labelled issue open and comments further findings onto it, so a stale
open issue would have silently absorbed the next real alert — including the
red-path evidence in run 5.

## Custody-chain evidence (run 2/3)

To be captured per the plan's Task 5 Step 2: the blob path, the artifact file
list, the matching hashes, and the absence of the complete delta from the
public run log.
