# cham

Hybrid DDI lab: one source of truth for DNS across three planes — an
on-prem SpatiumDDI stack (BIND9 + Kea under a control plane), Azure
hub-and-spoke with Private DNS, and Cloudflare public DNS — all managed
from this repo with Terraform and converged by a Python reconciler.

Named for cham or 참 meaning geniune in Korean Hanja: the core demo is **split-horizon
resolution** — `www.dwsolution.co` answers differently inside and outside
the lab, both answers managed here.

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
- [ ] Phase 2 — Azure core (hub, spokes, peering, NSG, UDR)
- [ ] Phase 3 — WireGuard tunnel + hybrid resolution
- [ ] Phase 4 — Cloudflare + reconciler v2
- [ ] Phase 5 — CI/CD pipeline
