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
| Federated credentials | 3 subjects, ID-embedded form (`repo:ilee165@140726424/cham@1318631051:{ref:refs/heads/main,environment:lab,environment:cloudflare-prod}`); prefix re-confirmed 2026-08-12. Each has a caller and a run URL proving it works; the `pull_request` subject was deleted the same day for having neither | `az ad app federated-credential list`, `gh api .../actions/oidc/customization/sub` |
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
| 2 | Dispatched saved plan → private blob custody → environment-gated apply (lab) | Plan [31597174733](https://github.com/ilee165/cham/actions/runs/31597174733) → apply [31603340729](https://github.com/ilee165/cham/actions/runs/31603340729) **failed**; re-plan [31604290864](https://github.com/ilee165/cham/actions/runs/31604290864) → apply [31604529524](https://github.com/ilee165/cham/actions/runs/31604529524) succeeded | The pipeline worked on the first attempt and the **Terraform did not**. Every custody step passed — hash verified, plan pulled from the private blob, `environment:lab` OIDC login accepted — and then `terraform apply` hit a genuine provisioning race (see the section below). That is the outcome to want from a first real apply: the gate proved the artifact, and the failure it surfaced was in the thing being applied. Delta re-plan after the fix: `Apply complete! Resources: 12 added, 0 changed, 0 destroyed`, all four peerings `Connected`/`Succeeded`, all three private-DNS links `Succeeded`. |
| 3 | Same custody chain for the Cloudflare stack | Plan [31596919668](https://github.com/ilee165/cham/actions/runs/31596919668) → apply [31597133904](https://github.com/ilee165/cham/actions/runs/31597133904) | `Apply complete! Resources: 0 added, 0 changed, 0 destroyed` — the stack was already converged, so the chain was proven without mutating a single public record. First and so far only exercise of the `…:environment:cloudflare-prod` subject. Public DNS re-verified byte-identical afterwards, M365 MX included. The environment gate held the run at `waiting` until approved, and the approval prompt named `cloudflare-prod`, not `lab`. |
| 4 | Drift, green path — converged, silent, no issue | Run [31596160048](https://github.com/ilee165/cham/actions/runs/31596160048), dispatched on `main` at `0dd83cf` | Green and silent. Public edge checked first and credential-free: `[cloudflare-public] converged (0 changes)` / `summary: 0 add, 0 update, 0 delete across 1 edge(s)`. `Report drift` **skipped** — no issue opened, which is the whole point of the green path. Azure edge correctly skipped on an absent zone: the gate step reports `LOGIN: success  ZONE: success  AZURE: skipped`, so the skip was a determinate "the zone is not there", never an assumed `false`. |
| 5 | Drift, red path — green run plus a labelled issue carrying the diff | Runs [31604875749](https://github.com/ilee165/cham/actions/runs/31604875749) and [31605035833](https://github.com/ilee165/cham/actions/runs/31605035833), issue [#14](https://github.com/ilee165/cham/issues/14) | No tamper was staged. A rebuilt lab genuinely lacks the reconciler-owned `app` record, which is the condition ADR-006 predicts, so the red path was exercised by a real finding rather than a synthetic one. Run green, issue raised: `[azure-private] ADD app A 10.10.4.30 ttl=300` beside `[cloudflare-public] converged (0 changes)` — both edges in one issue body. Gate reported `LOGIN: success  ZONE: success  AZURE: success`, so this run also proves the *present* branch of the presence probe that run 4 proved the absent branch of. The second run confirms deduplication: still exactly one open drift issue, which gained a comment instead of a sibling. |
| 6 | Two-stage destroy from the Actions UI | Plan [31605156142](https://github.com/ilee165/cham/actions/runs/31605156142) → apply [31605336092](https://github.com/ilee165/cham/actions/runs/31605336092) | `Apply complete! Resources: 0 added, 0 changed, 32 destroyed` — the exact inverse of the build. Blast radius checked against the destroy summary before approving: 32 delete lines, zero non-delete lines, and zero occurrences of `tfstate`, `cloudflare`, `bootstrap`, or the state account name; the only resource-group entry is `azurerm_resource_group.lab`. Afterwards `az group exists rg-cham-lab` → `false`, with `rg-cham-tfstate` the only remaining `rg-cham*` group. Public DNS verified unchanged after teardown. |

## OIDC, first real exercise (2026-08-12)

The federation was configured 2026-08-06 and, as noted at the time, never
actually exercised — `plan.yml`'s Azure-touching job is conditional and was
skipped on every branch run, so a green PR proved nothing about it. Drift run
[31596160048](https://github.com/ilee165/cham/actions/runs/31596160048) is the
first run in which GitHub minted a token and Azure accepted it:
`Azure login (OIDC)` → `Subscription is set successfully.`, under the
`…:ref:refs/heads/main` subject. Runs 3 and 2 then exercised
`…:environment:cloudflare-prod` and `…:environment:lab` respectively, so three
of the four configured subjects have now minted a token that Azure accepted.

The fourth, `…:pull_request`, was **deleted 2026-08-12** rather than left
configured. It had no caller and could not acquire one by accident: both
`id-token: write` jobs in `plan.yml` are gated
`if: github.event_name == 'workflow_dispatch'`, and the only other
PR-triggered workflow, `reconciler-tests.yml`, deliberately grants no
`id-token` at all. Nothing in the repository could present that subject, so no
green run would ever have validated it — and a standing trust relationship
that nobody exercises is one whose breakage, or whose misuse, goes unnoticed.
Deleting it means every remaining credential has a caller and a run URL
proving it works.

Reversible in one command if a PR-time plan is ever wanted; the credential is
three fields and a subject, and the subject is recorded above.

## Issue hygiene

Issue #6 (`DNS drift detected — 2026-08-08`) was closed 2026-08-12. It was
raised by the 06:46Z cron carrying the two ADDs that Phase 4 task C2 applied
later the same day, so it had been resolved for four days and merely left
open. Closing it is not cosmetic: the Phase 5 workflow keeps exactly one
drift-labelled issue open and comments further findings onto it, so a stale
open issue would have silently absorbed the next real alert — including the
red-path evidence in run 5.

Issue #14 was closed the same day for the same reason once the lab was
destroyed. Its finding was correct when raised and simply ceased to have an
edge to exist on. The rule this establishes: a drift issue is closed when the
condition ends, whether that is by reconciling it or by removing the edge —
never left open as a reminder, because the one open issue is a live channel,
not a notepad.

## Custody-chain evidence (run 2/3)

Captured per the plan's Task 5 Step 2. Cloudflare chain shown in full; the lab
chain has the same shape under `lab/apply/` and `lab/destroy/`.

| Element | Value |
|---|---|
| Blob path | `cloudflare/apply/2f39aaf…-31596919668-1/cloudflare.tfplan` |
| Artifact contents | exactly two files — `cloudflare-plan-manifest.json` (354 B), `cloudflare-plan-summary.txt` (149 B). The plan binary is **not** among them. |
| Hash in manifest | `aac1316a0d0b2c207345be791c1f57e6afd7cde1bea052cb5fa7de931cdc5d19` |
| Hash echoed by apply | `APPROVED_SHA256: aac1316a…` — passed as a dispatch input by a human, then matched against the manifest before the plan was fetched |
| Artifact transfer integrity | `SHA256 digest of downloaded artifact is a6930a78…` matching the expected digest |
| Summary content | `Changed resources: - none` — enough to review, not enough to reveal |

**Absence of the delta from the public log**, which is the property that matters:
the plan run's log is 715 lines and the apply run's is 432, and across both,
these patterns occur zero times — `cloudflare_record`, `will be created`,
`will be updated`, `will be destroyed`, `~ content`, `ipv4Address`, and the
string `dwsolution` itself. The complete delta exists only in the private
storage account. Lab runs behave the same way; the 32-line destroy summary
names resource *addresses* and no addresses, IPs, or key material.

## The one real defect this phase surfaced

Evidence run 2's first apply ([31603340729](https://github.com/ilee165/cham/actions/runs/31603340729))
failed creating `peer-app-to-hub`:

```
ReferencedResourceNotProvisioned: Cannot proceed with operation because resource
.../virtualNetworks/vnet-hub ... is not in Succeeded state. Resource is in Updating
state and the last operation that updated/is updating the resource is PutSubnetOperation.
```

Azure returns a VNet's id and name as soon as the VNet exists, while a subnet
write leaves the parent VNet in `Updating` for seconds afterwards; a peering
against a VNet in that state is rejected with a 400, which the provider does
not retry. Terraform had no edge to order on — the spoke module receives the
hub VNet as two plain strings, so the graph only knew "the hub VNet exists".

Fixed in PR [#13](https://github.com/ilee165/cham/pull/13) on both sides: the
hub's `vnet_id`/`vnet_name` outputs now depend on the hub's subnet writes,
which propagates the wait to every consumer, and both spoke peerings depend on
the spoke's own subnet writes. The next apply created all four peerings without
incident.

Worth recording as a phase outcome rather than a footnote: this was the second
occurrence — the same error took down Checkpoint B on 2026-08-03 and was worked
around by re-applying. It is timing-dependent, so a retry usually succeeds,
which is exactly how it survived to fail again. A CI pipeline that applies a
reviewed plan is what turned it from an annoyance into something with a run URL
attached.

## Phase 4 carry-forward items closed locally (2026-08-13, Task 7)

Two of the five carried-forward items were free and needed only the local
SpatiumDDI stack. Both done, both verified by measurement.

**Issue #9 — `demo` CNAME trailing dot, fixed on the truth side.**
`PUT {"value": "www.dwsolution.co."}` on the Spatium record. The three
predictions made when the issue was opened all measured true:

| Prediction | Measured |
|---|---|
| Internal BIND9 renders absolute | before: `www.dwsolution.co.dwsolution.co.` → after: `www.dwsolution.co.` (`dig -p 1053 @127.0.0.1`) |
| Zero edge churn | `cham-reconcile --dry-run --edge cloudflare-public` → `converged (0 changes)`, exit 0 |
| Snapshot unchanged | `--export desired-records.json` → byte-identical to the committed file |

**Apex-zone M365 shadow — resolved by scoping, not mirroring (ADR-008).**
The `dwsolution.co` truth zone moved to a new serverless `truth-only` group;
the lab resolver stopped serving the apex and now recurses for it. Measured
after the move, all through `dig -p 1053 @127.0.0.1`:

| Query | Before | After |
|---|---|---|
| `dwsolution.co MX` | NODATA (authoritative empty) | `0 dwsolution-co.mail.protection.outlook.com.` |
| `dwsolution.co TXT` | NODATA | `MS=…` verification + production SPF |
| `autodiscover.dwsolution.co` | NXDOMAIN | `autodiscover.outlook.com.` |
| `www.dwsolution.co A` | `10.10.0.10` | `10.10.0.10` — override zone untouched |
| `app.azure.dwsolution.co A` | `10.10.4.30` | `10.10.4.30` — served zones untouched |

The autodiscover row is the reason scoping beat mirroring: it proves the fix
covers the *class* of M365 names, not an enumerated list. Reconciler truth was
unaffected because `fetch_desired` walks every group and filters zones by
name — dry-run converged and the snapshot re-export was byte-identical, which
also means the nightly drift job needed no snapshot commit for either item.

One operational rule came out of the move, recorded in ADR-008: a zone must
never exist in two groups while the reconciler runs (`fetch_desired` merges
groups into one RRset, doubling every value), so a zone move is always
create → verify → delete with no reconciler invocation inside the window.

Remaining Task 7 items: ADR-007 resolver unification and the WireGuard
operator step (both need the lab up — natural pairing for one session), and
the quality-gate re-run confirmation (arguably satisfied by the 2026-08-10
gate re-run; needs a written verdict, not new work).

## Cost

The lab existed for roughly 90 minutes across evidence runs 2 and 6, with all
cost-bearing options off (`enable_test_vm_*`, `enable_test_nic_*`,
`enable_private_resolver` all `false`) — one hub VM instead of the Phase 4
shape's three. Prorated against the ~$10–12/mo figure, the whole exercise cost
cents. Billing is back to zero: the only surviving resource group is the state
backend.
