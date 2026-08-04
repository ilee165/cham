# Phase 3 WireGuard + Hybrid DNS — Plan Verification

**Date:** 2026-08-04
**Verdict:** PASS — ready for operator review, not implementation
**Independent score:** 100/100
**Blockers:** 0
**Warnings:** 0

## Scope and safety boundary

This verification covers the Phase 3 plan, planning research, merged Phase 2
baseline, and execution gates. It does not authorize Checkpoint A or B. No VM
was started, no Terraform apply ran, and no Azure resource was mutated while
the plan was revised or verified.

The reviewed branch is `feat/phase-3-wireguard-hybrid-dns`. Its base, local
`main`, and `origin/main` all resolve to merged commit
`f734d879b262e5783df25c1da00798acd7a68e7a`.

## Read-only baseline

- Azure reports `vm-hub-ddi`, `vm-test-app`, and `vm-test-mgmt` as
  `VM deallocated`.
- Azure reports zero `Microsoft.Network/dnsResolvers` resources in the lab
  resource group.
- The ignored lab inputs retain all four test NIC/VM flags as `true` and
  `enable_private_resolver = false`.
- A refresh-backed Terraform detailed-exit-code plan returned `0` and
  `No changes. Your infrastructure matches the configuration.`
- The current home `/32` and WireGuard public key match their ignored inputs;
  only match booleans were observed.
- No private key, subscription/tenant identifier, public/home IP, state, plan,
  backend configuration, or tfvars content is recorded here.

## Independent goal-backward review

The initial review correctly rejected a moving draft. The final draft fixes
every identified execution gap:

1. Native Docker Engine inside Debian WSL2 replaces the invalid Docker Desktop
   network-namespace assumption.
2. The Compose override replaces the upstream mapping and binds BIND only to
   `172.16.0.2:53` over UDP and TCP.
3. Checkpoint A keeps the dummy interface/runtime active through a real fresh
   Kea lease rehearsal and performs finally-style local cleanup afterward.
4. The app guest has a bounded `dnsutils` prerequisite and explicit UDP/TCP
   tests.
5. The hub peer is compared before WireGuard starts; the service is started
   non-persistently and remains disabled for future boots.
6. A separately running, deallocation-only watchdog protects the single
   60-minute VM window.
7. Live/Terraform guards must be no more than five minutes old immediately
   before the hub starts.
8. Documentation validation cannot silently start another VM window.
9. Private Resolver stays absent and disabled; any Terraform delta blocks VM
   start and requires a fresh named plan/hash approval.

The independent checker re-read the stable revision and returned PASS,
100/100, zero blockers, and zero warnings.

## Requirement-to-evidence traceability

| Required outcome | Planned proof | Safety/closeout evidence |
|---|---|---|
| Encrypted split tunnel | Recent handshake and bidirectional counter booleans; exact `172.16.0.0/24` and `10.10.0.0/16` routes | No default route; no raw key/endpoint output; both tunnel services stopped |
| Laptop to Azure DNS | Direct and Spatium-composed queries for Azure seed and auto-registered names over UDP and TCP | Hub-only proof precedes app start |
| Azure to on-premises DNS | Hub and app query the exact Spatium listener over UDP and TCP | Listener restricted to `172.16.0.2:53`; Docker Desktop remains stopped |
| DHCP-to-DNS propagation | Unique post-trigger Kea lease, automatically created DDNS record, bounded 120-second poll, and app UDP/TCP resolution | Disposable client restored; static/manual records are rejected as evidence |
| Lowest practical cost | Hub starts first; app starts only after hub-only proof; management never starts | One 60-minute watchdog window; all three VMs deallocated on success/failure/timeout |
| No unreviewed infrastructure change | Fresh live/input guards and Terraform exit `0` immediately before start | Any delta requires a separately reviewed saved plan and SHA-256 |
| Secure evidence | Boolean/count-only key, route, handshake, and secret checks | No private material, raw state/plan, IDs, IPs, or packet captures committed |

## Deterministic validation

| Check | Result |
|---|---|
| `terraform fmt -check -recursive` | PASS |
| `terraform -chdir=terraform/envs/lab validate` | PASS |
| `tflint --recursive --no-color` | PASS |
| `checkov -d terraform --quiet --compact` | PASS — 38 passed, 0 failed, 15 skipped |
| `git diff --check` | PASS |
| PowerShell plan fences | 13 parsed, 0 syntax errors |
| Hub Bash template | `bash -n` PASS |
| Embedded hub Python blocks | 2 parsed, 0 syntax errors |
| Executable VM start commands | hub 1, app 1, management 0 |
| Exact DNS publish mappings | UDP present, TCP present |
| `enable_private_resolver = true` assignments | 0 |
| Changed-file secret markers/key-shaped values | 0 / 0 |
| Missing local Markdown links | 0 |

## Review gate

The plan is internally consistent and executable, but Phase 3 implementation
remains intentionally stopped. The next possible authorization is Checkpoint A
only: zero-cost local runtime/tool/key preparation plus read-only Azure and
Terraform readiness checks. Checkpoint A must finish with all three VMs still
deallocated and return a fresh report before any Checkpoint B VM approval.

Plan review must also accept native Docker Engine inside Debian WSL2 as the
runtime choice. If Docker Desktop must remain the engine, this plan is not
approved; the tunnel/proxy architecture must be redesigned first.
