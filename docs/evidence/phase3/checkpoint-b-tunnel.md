# Phase 3 Checkpoint B Evidence — WireGuard Tunnel

Captured 2026-08-06 during the single authorized 60-minute window. The
operator explicitly approved Checkpoint B in-session, bound to branch commit
`53cea30a5781dc22d156aebbb111da58debe65e8` and watchdog SHA-256
`dbe059fc8e00dfdfeaa24a581bb46a1e183d8405556926f1c63b57e530ffcb92`.

## Window control

| Check | Result |
| --- | --- |
| All 1.4 pre-start guards re-run within five minutes of arming | `true` |
| Guard deltas versus the approved Checkpoint A report | none |
| Refresh-backed plan detailed exit code / result / warnings | `0` / `No changes` / `0` |
| Watchdog armed as independent hidden process before first start | `true` |
| Watchdog deadline (UTC) | `2026-08-06T05:03:59Z` |
| `vm-hub-ddi` start accepted (exit 0) | `true` |
| `vm-test-mgmt` started at any point | `false` |
| Window closed with verified deallocation before deadline | `true` |
| Approximate active window used | 25 of 60 minutes |

## Hub bring-up

| Check | Result |
| --- | --- |
| Azure power state reached `VM running` | `true` |
| SSH reachable with dedicated key | `true` |
| cloud-init status | `done` |
| Hub endpoint resolved from `terraform output` only | `true` |

## Hub WireGuard key state (2.2)

Stdin-fed root script; no private value entered command output, arguments,
or this repository.

| Check | Result |
| --- | --- |
| `HUB_KEY_STATE` | `OK` |
| Configured peer equals laptop public key (`HUB_PEER_MATCH`) | `true` |
| Key/config owned `root:root` mode `600` | `true` |
| `wg-quick strip` parse check | pass |
| `wg-quick@wg0` disabled for boot, started for session only | `true` |
| `net.ipv4.ip_forward` on hub | `1` |
| Implicit key rotation performed | `false` |

## Laptop configuration and transport (2.3 / 2.4)

| Check | Result |
| --- | --- |
| `Address = 172.16.0.2/24` in laptop config | `true` |
| `AllowedIPs = 172.16.0.0/24, 10.10.0.0/16` exact split-tunnel | `true` |
| Configured peer equals hub public key | match (no edit needed) |
| Endpoint equals current Terraform hub endpoint | match (no edit needed) |
| `wg0` brought up from root-owned `0600` config | `true` |
| Laptop `net.ipv4.ip_forward` | `1` |
| Local handshake epoch via `cut -f2`, single nonzero value | `true` |
| Local handshake age within 0–120 s | `true` |
| Hub peer handshake age within 0–120 s | `true` (22 s) |
| Transfer counters increased across probe traffic | `true` |
| Laptop → hub transfer address (172.16.0.1) reachable | `true` |
| Hub → laptop transfer address (172.16.0.2) reachable | `true` |
| Laptop internet egress unchanged (boolean home-path compare) | `true` |
| Raw `wg show` output recorded or committed | `false` |

## Deviations (local tooling only; no infrastructure impact)

1. The Windows OpenSSH client required a Windows-style identity-file path;
   the initial POSIX-style path made key auth fail until corrected.
2. `ssh -J` does not pass `-i` to the jump hop; an explicit `ProxyCommand`
   carrying the dedicated identity was used for laptop → hub → app.
3. A stale `known_hosts` entry for the app private IP (pre-East-US-2-rebuild
   host key) was removed with `ssh-keygen -R`; the current key was then
   accepted via `accept-new`. The tool wrote a local backup automatically.

## Sanitization

This evidence omits public/home IPs, subscription/tenant identifiers,
SSH/WireGuard key material, raw `wg show` output, raw state/plan data, and
backend details.
