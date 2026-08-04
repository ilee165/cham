# Phase 3 — WireGuard Tunnel + Hybrid Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Note: most steps here are operational (SSH, dig, control-plane config), not code — "verify" steps are the test cycle.

**Goal:** A site-to-site WireGuard tunnel between the laptop (WSL2) and the Azure hub VM, with BIND9 conditional forwarding working in both directions: Azure resolves `lab.dwsolution.co` via the laptop, and the laptop resolves `azure.dwsolution.co` via the hub.

**Architecture:** Laptop `172.16.0.2` ↔ hub `172.16.0.1` over UDP 51820 (hub public IP, NSG-restricted to the home IP). Hub BIND9 (installed by Phase 2 cloud-init) forwards `lab.dwsolution.co` → `172.16.0.2` and everything else → Azure DNS `168.63.129.16`. The SpatiumDDI BIND9 on the laptop gets a conditional forward zone `azure.dwsolution.co` → `172.16.0.1`. Laptop-originated traffic (including queries from the SpatiumDDI Docker containers) is SNAT'd to `172.16.0.2` before entering the tunnel, because WireGuard's cryptokey routing drops packets whose source is outside `AllowedIPs`.

**Tech Stack:** wireguard-tools (laptop WSL2 + hub Ubuntu 24.04), BIND9, SpatiumDDI control plane (Docker Compose from Phase 1), Terraform outputs for addressing. ADR-002 governs (WireGuard over VPN Gateway).

## Global Constraints

- Private keys never enter the repo, tfvars, or Terraform state. Laptop key: `~/.wg/cham-laptop.key` (created in Phase 2 Task 4). Hub key: generated **on the hub** and never leaves it. Only public keys move.
- `wg0.conf` is gitignored (already in `.gitignore`) — belt and suspenders: never `git add` it anywhere.
- Split tunnel only: laptop `AllowedIPs` is the transfer net + Azure supernet. Never `0.0.0.0/0`.
- The hub public IP changes on every destroy/apply cycle — always read it from `terraform output -raw hub_public_ip`, never hardcode it.
- Evidence goes to `docs/evidence/phase3/`.
- Prerequisite state: Phase 2 fully applied (with the Task 1 fixes baked into cloud-init) and the local SpatiumDDI stack up (`cd spatium && docker compose up -d`).

## Task Dependency / Parallelism Map

```
Task 1 (hub key install)    ─┐  parallelizable (different machines)
Task 2 (laptop wg0.conf)    ─┘
        └─→ Task 3 (bring up tunnel + L3 verification)
              ├─→ Task 4 (on-prem → Azure DNS path)   ─┐ parallelizable
              ├─→ Task 5 (Azure → on-prem DNS path)   ─┘ (independent directions)
              └────→ Task 6 (end-to-end closeout + docs)
Task 7 (Private Resolver session) — OPTIONAL, any time after Task 5
```

---

### Task 1: Install the hub's WireGuard private key and start the interface

The design deliberately keeps the hub private key out of cloud-init/Terraform state (`REPLACE_ON_HOST` placeholder). This is the one manual step per VM rebuild; it is documented in the runbook, not automated.

- [ ] **Step 1: Generate the key on the hub and patch the config in place**

```bash
HUB_IP=$(terraform -chdir=terraform/envs/lab output -raw hub_public_ip)
ssh labadmin@"$HUB_IP" '
  umask 077
  wg genkey | sudo tee /etc/wireguard/hub.key >/dev/null
  sudo sed -i "s|PrivateKey = REPLACE_ON_HOST|PrivateKey = $(sudo cat /etc/wireguard/hub.key)|" /etc/wireguard/wg0.conf
  sudo cat /etc/wireguard/hub.key | wg pubkey
'
```
Expected: prints the hub's **public** key. Record it — Task 2 needs it. (The private key stays in `/etc/wireguard/` on the VM only.)

- [ ] **Step 2: Enable the interface**

```bash
ssh labadmin@"$HUB_IP" 'sudo systemctl enable --now wg-quick@wg0 && sudo wg show'
```
Expected: `interface: wg0` listening on 51820, one peer (the laptop public key from Phase 2), no handshake yet.

- [ ] **Step 3: Confirm forwarding is live in the guest**

```bash
ssh labadmin@"$HUB_IP" 'sysctl net.ipv4.ip_forward'
```
Expected: `net.ipv4.ip_forward = 1`.

---

### Task 2: Laptop WireGuard config (WSL2)

*Parallelizable with Task 1 — but Step 1's `PublicKey` value arrives from Task 1 Step 1, so finish that first or leave the placeholder until it lands.*

**Files:**
- Create (NOT in repo): `/etc/wireguard/wg0.conf` on the laptop (WSL2)

- [ ] **Step 1: Write `/etc/wireguard/wg0.conf`**

```ini
[Interface]
Address = 172.16.0.2/24
PrivateKey = <contents of ~/.wg/cham-laptop.key>
# SpatiumDDI's BIND/Kea run in Docker; their queries egress with docker-bridge
# source IPs. WireGuard drops sources outside AllowedIPs, so SNAT everything
# leaving via wg0 to our tunnel address.
PostUp = iptables -t nat -A POSTROUTING -o wg0 -j MASQUERADE
PostDown = iptables -t nat -D POSTROUTING -o wg0 -j MASQUERADE

[Peer]
# Azure hub VM — public key from Phase 3 Task 1
PublicKey = <HUB_PUBLIC_KEY>
Endpoint = <hub_public_ip>:51820
AllowedIPs = 172.16.0.0/24, 10.10.0.0/16
# Laptop is behind home NAT; keep the mapping alive so the hub can
# initiate DNS queries to us between our outbound packets.
PersistentKeepalive = 25
```

`chmod 600 /etc/wireguard/wg0.conf`. Fill the three placeholders: laptop private key, hub public key (Task 1), `terraform output -raw hub_public_ip`.

- [ ] **Step 2: WSL2 sanity checks**

```bash
sudo apt-get install -y wireguard-tools
uname -r                      # WSL2 kernel ≥ 5.6 has wireguard built in
ss -ulpn | grep ':53 '        # SpatiumDDI BIND9 must be bound on the host
```
Expected: kernel is 6.6.x (wireguard in-kernel: `modprobe wireguard` succeeds or is built-in); port 53/udp is listened on by docker-proxy (the SpatiumDDI BIND container publish). If 53 is not published on the host, fix the compose port mapping in the spatium stack before continuing — the hub will query `172.16.0.2:53`.

---

### Task 3: Bring the tunnel up and verify L3 both directions

*Depends on Tasks 1 and 2. Requires the relevant per-spoke test VM and NIC flags applied through an approved saved plan for the spoke checks.*

- [ ] **Step 1: Up + handshake**

```bash
sudo wg-quick up wg0
sleep 5 && sudo wg show
```
Expected: `latest handshake:` a few seconds ago; `transfer:` counters nonzero. On the hub, `sudo wg show` shows the same handshake.

- [ ] **Step 2: Transfer-net pings**

```bash
ping -c 3 172.16.0.1        # laptop → hub tunnel address
```
Expected: 0% loss. Then from the hub (`ssh labadmin@$HUB_IP`): `ping -c 3 172.16.0.2` — also 0% loss (keepalive holds the NAT mapping open).

- [ ] **Step 3: Laptop reaches hub VNet and spoke addresses**

```bash
ping -c 3 10.10.0.10                                        # hub private IP via tunnel
APP_IP=$(terraform -chdir=terraform/envs/lab output -raw testvm_app_ip)
ping -c 3 "$APP_IP"                                         # spoke test VM via hub forwarding
```
Expected: both 0% loss. The spoke ping proves: hub `ip_forward` + spoke NSG rule `AllowWireGuardTransfer` (Phase 2 fix) + spoke UDR return path (0/0 → NVA). If the spoke ping fails but 10.10.0.10 works, re-check that Phase 2 Task 1 Step 3 (NSG rule 111) is applied.

- [ ] **Step 4: Split tunnel confirmed (negative test)**

```bash
curl -4 -s ifconfig.me; echo
```
Expected: your **home** public IP, not the hub's — general internet traffic does not transit Azure.

- [ ] **Step 5: Capture evidence**

```bash
mkdir -p docs/evidence/phase3
{ sudo wg show; ping -c 3 172.16.0.1; ping -c 3 10.10.0.10; } | tee docs/evidence/phase3/tunnel.txt
```

---

### Task 4: On-prem → Azure resolution (`azure.dwsolution.co` via the hub)

*Depends on Task 3. Parallelizable with Task 5.*

- [ ] **Step 1: Add the conditional forward zone in SpatiumDDI**

In the SpatiumDDI control plane (Phase 1 stack), on the DNS server group serving the lab: create a **forward zone** `azure.dwsolution.co` with forwarder `172.16.0.1`, forward-only. Do this through the control plane (not by hand-editing the container) so it persists and shows in the IPAM story. The BIND9 configuration it must produce is equivalent to:

```conf
zone "azure.dwsolution.co" {
    type forward;
    forward only;
    forwarders { 172.16.0.1; };
};
```

If the SpatiumDDI release in use has no forward-zone object, fall back to a server-group config override with exactly that stanza, and record which mechanism was used in `docs/evidence/phase3/notes.md`.

- [ ] **Step 2: Verify from the laptop through the Spatium resolver**

```bash
dig +short @localhost db.azure.dwsolution.co
dig +short @localhost vm-test-app.azure.dwsolution.co
```
Expected: `10.10.4.20` (Terraform seed) and the test VM's auto-registered address (compare `terraform output testvm_app_ip`). The query path is: laptop dig → Spatium BIND9 (container) → forward zone → SNAT to 172.16.0.2 → tunnel → hub BIND9 (172.16.0.1, allowed by the Phase 2 `allow-query`/`allow-recursion` fix) → 168.63.129.16 → Private DNS zone.

If this times out: check each hop in order — `dig +short @172.16.0.1 db.azure.dwsolution.co` directly from the laptop first (isolates the Spatium-container leg from the tunnel leg), then `sudo iptables -t nat -L POSTROUTING -v` (MASQUERADE hit counters), then `sudo tcpdump -ni wg0 port 53` on the hub.

- [ ] **Step 3: Capture evidence**

```bash
dig @localhost db.azure.dwsolution.co | tee docs/evidence/phase3/onprem-to-azure.txt
```

---

### Task 5: Azure → on-prem resolution (`lab.dwsolution.co` via the laptop)

*Depends on Task 3. Parallelizable with Task 4. Requires a resolvable name in the lab zone — the Phase 1 exit test's `printer.lab.dwsolution.co` (a Kea-lease-created record). If it has expired, trigger a fresh lease or add a static A record in SpatiumDDI first.*

- [ ] **Step 1: From the hub itself**

```bash
ssh labadmin@"$HUB_IP" 'dig +short @127.0.0.1 printer.lab.dwsolution.co'
```
Expected: the printer's `10.20.x.x` address. Path: hub BIND9 forward zone → `172.16.0.2` (laptop Spatium BIND9 across the tunnel).

- [ ] **Step 2: From a spoke test VM (the full enterprise path)**

```bash
ssh -J labadmin@"$HUB_IP" labadmin@"$APP_IP" 'resolvectl query printer.lab.dwsolution.co'
```
Expected: same `10.20.x.x` answer. Path: spoke VM → VNet DNS (10.10.0.10 hub BIND9) → tunnel → laptop. This single command exercises: spoke DNS config, hub NSG port-53 rule, BIND forward zone, WireGuard, and the Phase 1 DHCP→DNS propagation — the whole DDI story in one query.

- [ ] **Step 3: Capture evidence**

```bash
ssh labadmin@"$HUB_IP" 'dig @127.0.0.1 printer.lab.dwsolution.co' | tee docs/evidence/phase3/azure-to-onprem.txt
```

---

### Task 6: Closeout — runbook accuracy, README, commit

*Depends on Tasks 4 and 5.*

**Files:**
- Modify: `README.md:45` (check Phase 3 box)
- Modify: `docs/runbook.md` (session-start additions learned here)

- [ ] **Step 1: Re-run the runbook "Session start" top to bottom**

The four runbook steps must work exactly as written. Amend the runbook with what Phase 3 actually requires — append to the "Session start" list:

```markdown
3a. Endpoint check: hub public IP changes on rebuild — update `Endpoint` in
    /etc/wireguard/wg0.conf from `terraform output -raw hub_public_ip`
    before `wg-quick up` (skip if the stack wasn't destroyed).
3b. If the hub VM was rebuilt: reinstall its WireGuard key (Phase 3 Task 1 —
    wg genkey on the hub, patch wg0.conf, enable wg-quick@wg0).
4a. Reverse check: `ssh labadmin@$HUB_IP 'dig +short @127.0.0.1 printer.lab.dwsolution.co'` → 10.20.x
```

- [ ] **Step 2: DHCP→DNS→tunnel chain demo (the flagship DDI proof)**

Connect (or renew) a device on the lab network so Kea issues a fresh lease, then from the spoke test VM: `resolvectl query <new-host>.lab.dwsolution.co`.
Expected: the new lease's address — a DHCP event on the laptop became resolvable inside Azure with no manual DNS edit. Capture to `docs/evidence/phase3/lease-to-azure.txt`.

- [ ] **Step 3: Check the box and commit**

In `README.md` set `- [x] Phase 3 — WireGuard tunnel + hybrid resolution`.

```bash
git add README.md docs/runbook.md docs/evidence/phase3/
git commit -m "docs: phase 3 complete — tunnel up, bidirectional hybrid resolution verified"
```

---

### Task 7 (OPTIONAL, timeboxed ~$2): Private Resolver flag session

*Any time after Task 5. This validates the prewired managed resolver path without changing the current hub-BIND client design. Skip freely; it gates nothing.*

- [ ] **Step 1:** Set a phone timer for 3 hours (runbook rule). Set `enable_private_resolver = true` in tfvars, generate a fresh saved plan, inspect its complete delta and SHA-256, and stop for explicit approval before applying that exact artifact. Expected after approval/apply: 12 resolver-module resources (including three forwarding-ruleset VNet links plus the inbound return route table and association) plus the gated hub NSG update; output `resolver_inbound_ip` populated.
- [ ] **Step 2:** In SpatiumDDI, temporarily repoint the `azure.dwsolution.co` forward zone's forwarder from `172.16.0.1` to the `resolver_inbound_ip` value. Verify `dig +short @localhost db.azure.dwsolution.co` still answers `10.10.4.20` — now via the managed resolver.
- [ ] **Step 3:** From a spoke, explicitly query Azure-provided DNS (`dig @168.63.129.16 printer.lab.dwsolution.co`) and verify the ruleset/outbound endpoint reaches on-premises DNS. The spoke VNet remains configured with the hub BIND VM, so ordinary client queries do not use the ruleset merely because the VNet link exists.
- [ ] **Step 4:** Screenshot the portal resources + capture both directions' `dig` output to `docs/evidence/phase3/resolver-session.txt`.
- [ ] **Step 5:** Repoint the forwarder back to `172.16.0.1`; set `enable_private_resolver = false`; generate and separately approve the exact saved removal plan before applying it. Verify: `az resource list -g rg-cham-lab --query "[?contains(name,'dnspr')]" -o table` → empty. Confirm the timer is cancelled.

---

## Exit Criteria (all must hold)

1. `wg show` on both ends reports a handshake newer than ~2 minutes continuously (keepalive holding through home NAT).
2. Laptop pings `172.16.0.1`, `10.10.0.10`, and a spoke test VM; hub pings `172.16.0.2`. Laptop's general internet egress still exits via the home IP (split tunnel).
3. `dig @localhost db.azure.dwsolution.co` on the laptop returns `10.10.4.20`, and an auto-registered test-VM name also resolves (on-prem → Azure, via the Spatium control-plane-managed forward zone).
4. `resolvectl query printer.lab.dwsolution.co` from a spoke test VM returns the on-prem lease address (Azure → on-prem, full path).
5. A fresh Kea lease becomes resolvable from inside Azure with zero manual DNS edits.
6. No private key exists in the repo, tfvars, or Terraform state (`git grep -i privatekey` shows only the `REPLACE_ON_HOST` template line; `terraform state pull | grep -ci privatekey` finds only the template blob).
7. The runbook session-start executes top-to-bottom in under 10 minutes including tunnel bring-up; evidence committed under `docs/evidence/phase3/`; README Phase 3 box checked.

## What Completion Looks Like

Two DNS planes behave as one: any record SpatiumDDI knows — including ones that exist only because a device took a DHCP lease seconds ago — answers inside Azure spokes, and every Azure private record (seeded or auto-registered) answers on the laptop, all across an encrypted tunnel whose only manual step per rebuild is one key install documented in the runbook. The demo is a single split-screen: `resolvectl query printer.lab...` on a spoke VM next to `dig db.azure...` on the laptop, both answering, `wg show` underneath. The optional resolver session leaves before/after evidence that both managed directions work and records the additional client-DNS change required for a full cutover.
