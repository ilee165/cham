# Phase 3 Checkpoint B Evidence — Hybrid DNS

Captured 2026-08-06 in the same authorized window as
`checkpoint-b-tunnel.md`. All resolution gates ran only after the tunnel
gates passed. `enable_private_resolver` stayed `false`; no resolver resource
existed at any point.

## Local data plane

| Check | Result |
| --- | --- |
| Compose profiles `dns-bind9` + `dhcp` up on native Debian engine | `true` |
| BIND published only on `172.16.0.2:53` over UDP and TCP | `true` |
| Wildcard `:53` listeners | `0` |
| Docker Desktop involved | `false` |
| Foreground WSL session held for the timebox | `true` |

## Hub-only gates (2.4, before app start)

Azure seed queries must return `10.10.4.20`; every path is UDP and TCP
explicitly — a UDP pass never substituted for TCP.

| Path | UDP | TCP |
| --- | --- | --- |
| Laptop direct → hub BIND (`172.16.0.1`) `db.azure.dwsolution.co` | pass | pass |
| Laptop → Spatium composed (`172.16.0.2`) `db.azure.dwsolution.co` | pass | pass |
| Hub → Spatium (`172.16.0.2`) `printer.lab.dwsolution.co` | match | match |

The hub-originated answers equal the current Phase 1 lease-backed local
answer. Per the corrected plan, `vm-test-app.azure.dwsolution.co` was not
queried in this hub-only gate.

## App path gates (2.5, after hub gates passed)

| Check | Result |
| --- | --- |
| `vm-test-app` start accepted; Azure reported `VM running` | `true` |
| `vm-test-mgmt` remained `VM deallocated` | `true` |
| Auto-registered name matched Terraform app private IP over UDP | `true` |
| Auto-registered name matched Terraform app private IP over TCP | `true` |
| Bounded post-start poll converged | iteration 1 of 24 |
| Laptop reached app private IP through the tunnel/hub forwarding | `true` |
| `dig` present in app guest (no criterion weakened) | `true` |
| App `resolvectl` uses hub BIND (`10.10.0.10`) | `true` |
| App `dig @10.10.0.10 printer.lab.dwsolution.co` UDP / TCP | match / match |
| App `resolvectl query` for the on-prem record | match |

## Fresh Kea lease and automatic DDNS (2.5)

New unique hostname; the rehearsed disposable-client procedure from the
approved Checkpoint A report was reused unchanged. No manual or static
record was involved.

| Check | Result |
| --- | --- |
| Hostname | `phase3-lease-20260806041731` |
| Matching record absent before trigger | `true` |
| Trigger (UTC) | `2026-08-06T04:17:31Z` |
| Disposable client started on Docker-only `10.20.0.0/24` | `true` |
| DHCP renewal trigger succeeded | `true` |
| DDNS record present with equal UDP and TCP answers | `true` |
| Poll converged | iteration 2 (≤120 s bound) |
| Lease address within `10.20.0.200-10.20.0.220` | `true` |
| App resolved the fresh name over UDP via `10.10.0.10` | match |
| App resolved the fresh name over TCP via `10.10.0.10` | match |
| Disposable client released and removed | `true` |
| Operator management/uplink interface touched | `false` |

## Sanitization

This evidence omits public/home IPs, subscription/tenant identifiers, key
material, MAC/client identifiers, raw `dig`/`wg` output beyond match
booleans, and raw state/plan data. Private lab addresses shown here already
appear in the committed plan.
