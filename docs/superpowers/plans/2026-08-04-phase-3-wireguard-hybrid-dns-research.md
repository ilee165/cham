# Phase 3 WireGuard + Hybrid DNS — Planning Research

**Date:** 2026-08-04
**Branch:** `feat/phase-3-wireguard-hybrid-dns`
**Scope:** Planning and read-only verification only. No VM start, Terraform
apply, Azure mutation, Docker start, WSL package installation, or secret output
occurred.

## Executive finding

The existing Phase 3 architecture remains sound, but its execution plan was not
safe to run unchanged. It assumed an applied/running Phase 2 lab, an executable
Spatium checkout, WSL WireGuard tooling, and a non-idempotent hub-key step. It
also lacked a guaranteed deallocation path and included an optional paid
resolver experiment that conflicts with the current near-zero-cost goal.

The revised plan preserves the design while adding:

1. a zero-cost local/read-only checkpoint before any VM;
2. a hard stop for the currently unavailable Spatium/Docker and WSL WireGuard
   prerequisites;
3. key-consistency checks that never output private material;
4. a hub-first, app-conditional, management-never-started VM sequence;
5. a maximum 60-minute cost window with unconditional deallocation;
6. direct-hop then composed-path UDP/TCP DNS tests;
7. a no-drift/saved-plan gate for any infrastructure correction; and
8. an explicit retain-versus-destroy decision after all VMs are deallocated.

## Evidence examined

- `AGENTS.md`, `SKILLS.md`, and the available `gsd-plan-phase` skill
- `README.md`, `.continue-here.md`, `docs/architecture.md`,
  `docs/decisions.md`, and `docs/runbook.md`
- the Phase 2 plan, research, verification, review, corrections, and live
  checkpoint evidence under `docs/evidence/phase2/`
- `terraform/envs/lab/` and the hub, spoke, private-DNS, and resolver modules
- `spatium/README.md`
- the existing Phase 3 and downstream Phase 4/5 plans
- official upstream SpatiumDDI `main` at commit
  `091f8a14241611b1d7fe8bc6352828b0b30cdbe4`; its
  `docker-compose.agent-dns-bind9.yml` defaults both TCP and UDP DNS host
  publishing to `1053:53` and recommends port 53/DNAT for a real DNS server
- [Docker Desktop WSL architecture](https://docs.docker.com/desktop/features/wsl/)
  and [Docker Desktop networking](https://docs.docker.com/desktop/features/networking/)

The required repository graph was checked first, but
`graphify-out/graph.json` and `graphify-out/wiki/index.md` are absent. Scoped
source inspection was therefore used.

The GSD plan-phase skill was selected. Its referenced
`get-shit-done/workflows/plan-phase.md` and `references/ui-brand.md` files are
missing from this installation, so the repository's documented fallback was
used instead of mixing in a competing top-level orchestrator.

## Read-only current-state facts

### Git and Terraform

- Local `main` was fast-forwarded to merged remote commit
  `f734d879b262e5783df25c1da00798acd7a68e7a`.
- The Phase 2 remote branch was pruned.
- The Phase 3 branch was created cleanly at that exact commit.
- The ignored lab tfvars preserve both test VMs and NICs with all four
  per-spoke flags `true`.
- `enable_private_resolver` is `false`.
- Remote Terraform state tracks 36 addresses.
- A refresh-backed, unsaved Terraform plan exited `0` with `No changes`.

### Azure

- Azure CLI account state is enabled.
- `vm-hub-ddi`, `vm-test-app`, and `vm-test-mgmt` all report
  `VM deallocated`.
- The resource group lists 22 top-level Azure resources; this is distinct from
  Terraform's 36 state addresses, which include separately managed
  associations/rules/subresources.
- No VM start or Azure mutation occurred during planning.

### Keys and ingress

- Dedicated Windows WireGuard private/public files exist outside the
  repository; only file presence/length was inspected.
- The public file matches the ignored `wg_peer_public_key`.
- The current public IP matches the ignored home `/32`.
- The private key was never read into command output.
- Windows ACL inspection found an unintended explicit
  `CodexSandboxUsers` read/execute ACE on the WireGuard directory despite
  inheritance being disabled. It must be removed before the key is used.
- Debian WSL2 has neither the WireGuard key nor a WSL SSH-key copy yet. Those
  must be handled by the operator after plan approval; the generated
  `/etc/wireguard/wg0.conf` and WSL SSH material must be root-owned/mode
  `0600` and compared by their public values only.

### Tool/runtime readiness

| Item | Planning observation |
|---|---|
| Terraform | 1.15.8, callable |
| Azure CLI | 2.88.0, installed; current shell PATH needs explicit bootstrap |
| TFLint | 0.64.0, callable |
| Checkov | 3.3.9, callable |
| WSL2 | Debian, WSL version 2, kernel 6.6.114.1 |
| WSL OpenSSH | 10.0p2, callable |
| WSL `dig`/iptables | present |
| WSL WireGuard CLI | missing |
| Docker Desktop | client installed, engine not running |
| Debian Docker integration | not enabled/runnable |
| Spatium Compose checkout | not present in this repository or the inspected workspace |
| Upstream Spatium DNS publish | current Compose example uses TCP/UDP host port 1053, while the hub requires 172.16.0.2:53 |

## Findings and required corrections

### BLOCKER 1 — The local DNS endpoint is not currently executable

The old plan says `cd spatium && docker compose up -d`, but `spatium/` contains
only a README. Docker Desktop is stopped and Debian WSL integration is not
usable. Starting Azure first would spend compute time while discovering or
rebuilding Phase 1.

**Correction:** Locate/restore the pinned Spatium checkout, enable the local
runtime, and replace the upstream 1053 publish with an exact-address Compose
override binding the container only to `172.16.0.2:53` over TCP and UDP. Do
not treat WSL's unrelated internal port-53 DNS proxy as Spatium proof.

### BLOCKER 2 — Docker Desktop container traffic bypasses Debian `wg0`

Official Docker documentation states that Docker Desktop runs in its own
isolated WSL distribution; per-distribution integration exposes the Docker CLI,
not the engine network namespace. Desktop container egress is NATed in the
Docker VM and emitted as Windows `com.docker.backend` sockets. Debian routes
and iptables on `wg0` therefore do not govern Spatium traffic.

**Correction:** This is a review-time topology choice. To keep the WSL2 tunnel,
run the Spatium data plane on a native Docker Engine inside Debian, keep Docker
Desktop stopped/integration disabled, bind BIND only to
`172.16.0.2:53` TCP/UDP, and prove both container egress and tunnel ingress.
If Docker Desktop must remain the engine, redesign around a native Windows
tunnel or explicit bidirectional DNS proxy; do not improvise a generic port
proxy.

### BLOCKER 3 — The selected WSL endpoint lacks WireGuard and keys

The Windows keypair exists and its public value matches Terraform, but Debian
WSL has no `wg` command and no local key/SSH directory. The Windows directory
also retains an unintended explicit sandbox-group read ACE; Phase 2's
inheritance/grant command did not remove existing explicit readers.

**Correction:** Install `wireguard-tools`, correct/verify Windows ACLs, and
make private-key injection an operator-only local action during the zero-cost
checkpoint. Compare only derived public values. Any mismatch blocks execution;
do not silently generate a replacement because the hub peer is rendered from
the Terraform input and a change can force replacement.

### BLOCKER 4 — The old prerequisite and VM lifecycle are stale

Phase 2 is retained rather than freshly applied, and every VM is deallocated.
The old plan begins directly with SSH and does not gate or timebox starts.

**Correction:** Re-run current account, ignored-input, power-state, resolver,
and no-drift checks. Require a second explicit approval for a 60-minute window.
Start hub first and app only after the hub path passes; management stays
deallocated.

### BLOCKER 5 — Hub key installation is unsafe to rerun

The old command always generates a key and then replaces
`REPLACE_ON_HOST`. If the marker is already gone, a retry can create a new key
file while leaving a different private key in `wg0.conf`.

**Correction:** Make the operation state-aware: create/reuse exactly one key
when the marker is present, compare stored/configured keys when it is absent,
and stop on ambiguity. Never rotate implicitly.

### BLOCKER 6 — Closeout does not stop cost

The old closeout checks documentation and commits evidence but neither brings
down laptop `wg0` nor deallocates the VMs.

**Correction:** Make tunnel-down and verified deallocation of all three VMs an
unconditional `finally` action on success, failure, timeout, or interruption.
Evidence review occurs only after Azure confirms every VM deallocated.

### WARNING 1 — The old L3 expectation conflicts with the security posture

The old plan treats pinging the hub private IP as required while the Phase 2
hub NSG deliberately documents blocked ICMP for ordinary NIC paths.

**Correction:** Use transfer-address reachability plus UDP/TCP DNS as the
hub-service proof, and app private-IP reachability as the forwarded-path proof.
Do not diagnose an intentionally blocked ICMP path as a tunnel failure.

### WARNING 2 — Evidence commands expose more than necessary

Raw `wg show`, state, plan JSON, and account output can disclose public
endpoints, IDs, and key metadata even when no private key is present.

**Correction:** Capture boolean matches, handshake freshness, nonzero transfer,
expected-answer comparisons, power states, and narrow plan summaries only.

### WARNING 3 — The optional managed-resolver task undermines the cost goal

The prior plan includes a timeboxed paid resolver session. It is not required
to prove the hub-BIND design and creates another apply/remove risk.

**Correction:** Remove it from Phase 3. Any future managed-resolver experiment
needs its own current-cost review, fresh saved plans, hashes, approvals, and
forced removal.

### WARNING 4 — Waiting for an app approval while the hub runs wastes money

A separate pause after starting only the hub could leave compute billing while
the operator is away.

**Correction:** Checkpoint B authorizes one conditional sequence: hub start,
hub tests, app start only on success, full tests, and immediate deallocation.
The pre-VM readiness report remains the deliberate human-review boundary.

## Recommended order

1. Review and approve the revised plan.
2. Approve native Docker Engine inside Debian WSL2 as the Phase 3 container
   runtime; keep Docker Desktop stopped so the tunnel namespace is explicit.
3. Run zero-cost Checkpoint A and stop with all VMs deallocated.
4. Approve one bounded Checkpoint B VM window.
5. Prove direct tunnel hops before composed DNS paths.
6. Prove the app path and fresh DHCP-to-DNS propagation.
7. Bring down the tunnel and verify all VMs deallocated.
8. Review sanitized evidence and update the runbook/status.
9. Separately choose retained/deallocated or saved-plan destroy.
