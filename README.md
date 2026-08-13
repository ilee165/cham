# cham

Hybrid DDI lab: one source of truth for DNS across three planes — an
on-prem SpatiumDDI stack (BIND9 + Kea under a control plane), Azure
hub-and-spoke with Private DNS, and Cloudflare public DNS — all managed
from this repo with Terraform and converged by a Python reconciler.

Named for cham or 참 meaning geniune in Korean Hanja: the core demo is **split-horizon
resolution** — `www.dwsolution.co` answers differently inside and outside
the lab. The public answer is Terraform-managed in this repo; the internal
override lives in the SpatiumDDI control plane (created by hand in Task A3 —
ADR-007 records which resolver serves it).

## What this demonstrates
- **Terraform** — reusable modules (one spoke module, two instantiations),
  remote state with locking, flag-gated cost-heavy resources
- **Azure networking** — hub-and-spoke, peering, NSGs, UDRs through an NVA,
  Private DNS with auto-registration, hybrid resolution
- **DDI** — DHCP-lease-to-DNS propagation, conditional forwarding both
  directions over WireGuard, split-horizon, IPAM modeling of cloud space
- **CI/CD** — OIDC to Azure (no stored secrets), plan-on-PR, gated apply,
  nightly drift detection, tflint + checkov

## Layout
| Path | What |
|---|---|
| `terraform/bootstrap` | State storage (apply once, local state) |
| `terraform/modules` | hub / spoke / private-dns / dns-resolver (flag-gated) |
| `terraform/envs/lab` | Root module — the lab |
| `terraform/cloudflare` | Public zone (separate state + credential) |
| `ddi-reconciler` | Reconciler v2 — SpatiumDDI truth → Azure + Cloudflare |
| `spatium` | Local stack notes |
| `docs` | Architecture, ADRs, runbook |

## Cost posture
Core network objects have no fixed charge. Phase 2 runs in East US 2 with a
parameterized `Standard_D2als_v7` hub VM and two `Standard_F1als_v7` test
VMs (the original North Central US B-series design was superseded by
subscription capacity — see the ADR-001 amendment and
`docs/evidence/phase2/`). VMs run only inside bounded verification windows
and are deallocated otherwise; while the stack is retained between phases,
the managed disks, hub static public IP, and Private DNS accrue small
charges (~cents/day) until a separately approved destroy. Free-account
benefits are not assumed. Azure DNS Private Resolver (~$360/mo both endpoints) is
`count`-gated behind `enable_private_resolver` and used only in explicitly
approved prorated sessions. CI never applies on merge: pull requests run only
credential-free static checks, while a manual `plan.yml` run on `main`
publishes a short-lived saved-plan artifact. `apply.yml` requires its exact
commit, run ID, SHA-256, and a protected `lab` environment. `destroy.yml` uses
the same two-stage saved-plan gate. An Azure budget notification is not a
spend cap.

See [docs/decisions.md](docs/decisions.md) for why each of those calls
was made. Start with ADR-001.

## Status
- [x] Phase 1 — local SpatiumDDI, zones, DHCP→DNS propagation
- [x] Phase 2 — Azure core (hub, spokes, peering, NSG, UDR)
- [x] Phase 3 — WireGuard tunnel + hybrid resolution
- [x] Phase 4 — Cloudflare + reconciler v2
- [x] Phase 5 — CI/CD pipeline

Phase 4 defined **eight** exit criteria. Seven hold as written, with evidence
under `docs/evidence/phase4/`: the offline suite passes with no credentials
and no network, the exit-code contract is proven live (1 operational error /
2 drift / 0 converged), first convergence applied the three seeded records
and an immediate re-run is a no-op, tampering each edge is detected and
healed, the before/after listings differ by exactly the reconciler's own
record, the Cloudflare stack applies from its own state file with only a
scoped token, and the snapshot/ADR-006/README closeout items are done. The
eighth — the runbook's laptop-over-tunnel split-horizon demo — was
**redefined, not met**: the split horizon is real and captured
(`split-horizon.txt`), but it is served by the SpatiumDDI resolver; a client
using the hub's own resolver over the tunnel gets the public answer, and no
tunnel run was performed (ADR-007).

Four things Phase 4 did **not** settle were carried into Phase 5's
carried-forward work section. Two are now closed: the truth-side `demo`
CNAME is stored absolute (issue #9 — all three predictions measured true,
zero edge churn), and the apex zone no longer shadows this domain's live
Microsoft 365 records — it moved to a serverless truth-only group so the
lab resolver recurses for the apex (ADR-008; production MX, SPF, and
autodiscover all verified resolving through it). The remaining two — the
`www` split horizon served by the hub's own BIND9 (ADR-007) and the manual
WireGuard key-generation step — are paired into one post-Phase-5 lab
session, tracked as issue #18.

Phase 5's pipeline is proven by execution, not description: all six
evidence runs in `docs/evidence/phase5/notes.md` carry real run URLs — the
PR gate blocking merge with no cloud call, both stacks applying through the
saved-plan custody chain behind their own environment gates, drift's green
path (silent) and red path (a labelled issue carrying the diff, then
deduplicating), and the two-stage destroy. The first lab apply failed on a
genuine Azure provisioning race and the custody chain held while the
Terraform underneath it was fixed (PR #13) — which is the failure mode you
want a pipeline to have.
