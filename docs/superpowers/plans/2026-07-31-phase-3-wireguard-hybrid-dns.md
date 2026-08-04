# Phase 3 — WireGuard Tunnel + Hybrid DNS Implementation Plan

**Status:** Revised and independently plan-verified on 2026-08-04. Awaiting
operator review.
No Phase 3 implementation, VM start, Terraform apply, or Azure mutation is
authorized by this document.

**Execution owner:** Use the repository's GSD phase-execution workflow after
this plan is approved. The planning workflow files referenced by the local GSD
installation are missing, so this revision used the documented fallback:
repository research, goal-backward planning, deterministic checks, and an
independent plan review.

## Goal

Build and prove a split-tunnel WireGuard link between the laptop's Debian WSL2
environment (`172.16.0.2`) and the Azure hub (`172.16.0.1`) so that:

1. the laptop's SpatiumDDI resolver forwards `azure.dwsolution.co` to hub BIND9;
2. Azure hub/app clients resolve `lab.dwsolution.co` through the laptop;
3. a fresh Kea lease becomes resolvable from the Azure app spoke; and
4. the Azure VMs are deallocated immediately after the bounded test window.

The existing architecture remains unchanged: hub BIND9 forwards Azure-private
queries to `168.63.129.16` and the on-premises zone to `172.16.0.2`. Azure DNS
Private Resolver is not part of this phase.

## Current baseline

Read-only verification on 2026-08-04 established:

- branch `feat/phase-3-wireguard-hybrid-dns` starts at merged `main` commit
  `f734d879b262e5783df25c1da00798acd7a68e7a`;
- remote Terraform state tracks 36 addresses and a fresh plan reports
  `No changes`;
- Azure reports `vm-hub-ddi`, `vm-test-app`, and `vm-test-mgmt` as
  `VM deallocated`;
- all four per-spoke VM/NIC preservation flags are `true`;
- `enable_private_resolver = false`;
- the current home `/32` matches the ignored Terraform input;
- the existing Windows WireGuard public-key file matches
  `wg_peer_public_key` without exposing either key; and
- no VM was started and no Azure mutation was made during planning.

Two zero-cost prerequisites are not ready and must be fixed before a VM start:

- Debian WSL2 has OpenSSH and `dig`, but not `wireguard-tools`; and
- this repository contains only SpatiumDDI notes and no Compose checkout; and
- the installed Docker Desktop engine is not an acceptable substitute for an
  in-Debian engine in this design: its containers run in Docker's isolated VM
  and outbound sockets originate through Windows `com.docker.backend`, bypassing
  Debian `wg0`.

## Scope boundaries and invariants

### In scope

- restore and prove the existing Phase 1 SpatiumDDI runtime;
- prepare the WSL2 WireGuard and SSH runtime outside the repository;
- start only the hub and, conditionally, the app test VM;
- install/reuse the hub's locally generated WireGuard key;
- prove tunnel, routing, split-tunnel, UDP/TCP DNS, and DHCP-to-DNS behavior;
- capture sanitized evidence and update the runbook/status; and
- deallocate every VM at closeout.

### Out of scope

- starting `vm-test-mgmt`;
- changing the hub/spoke architecture;
- enabling Azure DNS Private Resolver;
- Phase 4 Cloudflare/reconciler work;
- committing private keys, `wg0.conf`, tfvars, state, or plan artifacts;
- applying any infrastructure delta without a fresh saved plan and explicit
  hash approval; and
- destroying the lab without a separately reviewed destroy plan.

### Hard safety and cost contract

1. **Planning approval is not VM-start approval.**
2. Checkpoint A is local/read-only and ends with a second hard stop.
3. Checkpoint B needs explicit authorization for one maximum 60-minute window.
4. Start the hub first. Start the app only after the hub tunnel path passes.
5. Never start the management VM.
6. On any failure or timeout: bring down laptop `wg0`, deallocate all three
   VMs, verify their power states, then diagnose offline.
7. Keep `enable_private_resolver = false` throughout Phase 3.
8. Any Terraform detailed-exit code other than `0` blocks VM start. A real
   delta requires a named saved plan, complete review, SHA-256, and explicit
   approval of that exact artifact.
9. Private keys never enter command output, evidence, Terraform inputs/state,
   the repository, or chat. Only WireGuard and SSH public keys may be compared.
10. Evidence omits subscription/tenant IDs, public/home IPs, contacts, backend
    details, raw state/plan JSON, key material, and raw packet captures.

## Execution hosts

- **Windows PowerShell:** Git, Terraform, TFLint, Checkov, and Azure CLI.
  Azure CLI is installed under
  `C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin` but is not on the current
  Codex shell PATH; prepend that directory or call `azps.ps1` explicitly.
- **Debian WSL2:** WireGuard, SSH, `dig`, listener/route inspection, and a
  native in-distribution Docker Engine for the Spatium data plane. The Docker
  daemon and `wg0` must share Debian's routing/iptables path.
- **Azure guests:** SSH commands only after the corresponding VM-start gate.

Do not silently switch the tunnel to native Windows. That would change the
Docker routing/source-NAT design and requires a new plan.

## Dependency map

```text
Plan review (Gate 0)
  -> Checkpoint A: zero-cost local + read-only cloud readiness
     -> Checkpoint B approval: one bounded hub/app VM window
        -> hub key + laptop tunnel + handshake
           -> conditional app start
              -> bidirectional DNS + fresh-lease proof
                 -> mandatory tunnel-down + VM deallocation
                    -> Checkpoint C evidence review
                       -> Checkpoint D retain-or-destroy decision
```

---

## Gate 0 — Review this plan

The operator reviews and decides:

- WSL2 remains the tunnel endpoint;
- Spatium's data-plane containers run on a native Debian Docker Engine so their
  traffic crosses Debian `wg0`; or, if Docker Desktop must be retained, this
  plan is rejected and a Windows-tunnel/explicit-proxy redesign is requested;
- Phase 1's actual pinned SpatiumDDI checkout/runtime can be located or restored;
- only hub and app may run during a maximum 60-minute window;
- management remains deallocated;
- Private Resolver remains disabled; and
- closeout always deallocates all VMs before evidence review.

**HARD STOP:** Do not perform Task 1, start Docker, install WSL packages,
configure Spatium, start a VM, or modify Azure until the operator approves this
plan.

---

## Task 1 — Checkpoint A: zero-cost readiness

Checkpoint A contains local preparation and read-only cloud/Terraform checks.
It does not authorize a VM start or Terraform apply.

### 1.1 Resolve and verify the toolchain

Record versions without recording identifiers:

```powershell
$env:Path = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;' + $env:Path
terraform version
az version
tflint --version
checkov --version
wsl.exe --status
wsl.exe -d Debian -- bash -lc 'uname -r; dig -v'
```

Install `wireguard-tools` inside Debian WSL2 using Debian's package manager,
then require `wg --version` and `modprobe wireguard` (or built-in-kernel proof)
to pass. This is a local prerequisite and must finish before any VM start.

Install/repair the official Windows OpenSSH Client (already authorized in the
tool-installation decision) and require `ssh.exe -V`. Use the dedicated
Windows SSH key and ProxyJump for both guests; do not copy the SSH private key
into WSL.

Before using either Windows private key, inspect both the key and its parent
directory with Windows ACL tooling. The dedicated SSH key currently reports
only the operator and `SYSTEM`; reverify that result at Checkpoint A. The
WireGuard directory has inheritance disabled but still grants an explicit
`CodexSandboxUsers` read/execute ACE; remove unintended explicit readers and
require only the operator and approved system/administrator principals. A
mounted Windows key reporting mode `0777` through DrvFS is not an acceptable
permission check.

The operator performs the ACL correction locally, equivalent to removing the
unintended group grant and then verifying the final trustees:

```powershell
$keyDir = Join-Path $env:USERPROFILE '.wg'
icacls $keyDir /inheritance:r
icacls $keyDir /remove:g CodexSandboxUsers /T
icacls $keyDir /grant:r "$($env:USERNAME):(OI)(CI)F" "SYSTEM:(OI)(CI)F" /T
icacls $keyDir
```

The final verification must fail if another non-approved explicit reader
remains. Evidence records only `ACL_OK=true`; it does not copy the ACL listing.

WireGuard private-key injection is an **operator-only local step**: the agent
must not read, copy, interpolate, or print the private value. At Checkpoint B,
the operator creates root-owned `/etc/wireguard/wg0.conf` mode `0600`. The
derived WSL public value must match the saved Windows public file, ignored
Terraform input, and hub peer; the comparison prints only `MATCH` or
`MISMATCH`.

If either comparison fails, stop. Prefer restoring the original private key.
Replacing the WireGuard peer input can force hub replacement through
`custom_data`; that requires a fresh state-backed saved plan and separate hash
approval. Do not patch only the live peer and leave Terraform intent stale.

### 1.2 Restore and prove the Phase 1 runtime

`spatium/` contains notes only; it is not an executable Compose project.
Locate the existing pinned SpatiumDDI checkout and record its version/path in
the runbook without copying secrets into this repository. If it cannot be
located, stop and restore Phase 1 before using Azure compute.

Docker Desktop WSL integration exposes a CLI inside Debian but keeps the engine
in Docker's isolated VM; official Docker networking documentation says
container outbound traffic becomes Windows host sockets. Such traffic will not
traverse Debian `wg0`, so the old Docker-bridge/MASQUERADE assumption is false
for Docker Desktop.

To preserve the approved WSL2 tunnel design, use a native Docker Engine in
Debian for the Spatium data-plane containers. Installing it is a separate local
action covered only after Gate 0 approval. Keep Docker Desktop stopped or its
Debian integration disabled to avoid daemon/context ambiguity. Require
`docker context show`, `docker info`, a Debian `dockerd` process, and route/
iptables counters to prove the containers and `wg0` share the Debian path.

If the operator wants to keep the Docker Desktop engine, stop and revise the
architecture around a native Windows tunnel or an explicit bidirectional DNS
proxy. Do not improvise Windows routes or assume WSL integration changes the
engine network namespace.

Create a local Compose override in the pinned checkout (outside this
repository) that replaces, rather than appends to, the upstream port list:

```yaml
services:
  dns-bind9:
    ports: !override
      - "172.16.0.2:53:53/udp"
      - "172.16.0.2:53:53/tcp"
```

Pin a Docker Compose version that supports `!override`. Never use
`DNS_HOST_PORT=53` by itself because that publishes a recursive resolver on all
host interfaces.

For a zero-cost rehearsal, create a temporary local `wg0` dummy interface with
`172.16.0.2/24` and a `10.10.0.0/16` route. Start the pinned stack on the
proven Debian engine with the override. Require all of these to pass:

- Compose services are healthy;
- `docker compose port`, exact-address `ss`, and container identity show only
  `172.16.0.2:53` for both UDP and TCP;
- explicit UDP and TCP queries to `@172.16.0.2` return the known Phase 1
  record;
- rendered BIND query/recursion ACLs admit only the hub transfer address plus
  the exact local bridge/health sources required by the pinned runtime; and
- the Spatium control plane can persist and render DNS changes.

From the actual BIND container, send bounded UDP/TCP probes toward
`10.10.0.10`; they should time out because there is no peer, while the dummy
interface TX/route counters prove egress selected the Debian host path. Keep
the DNS service and temporary interface/route active through the fresh-lease
rehearsal in 1.3. No Azure peer or private key is needed. Docker CLI
availability alone is not sufficient.

Do not accept `ss | grep :53` as proof: WSL's internal DNS proxy can satisfy
that grep while being unrelated to Spatium and unreachable over `wg0`. Verify
the exact bind address, protocol, owning process/container, and a DNS answer.
Do not use a generic REDIRECT/port-proxy workaround or reconfigure the hub to a
nonstandard port.

Through the control plane, create a forward-only zone:

```conf
zone "azure.dwsolution.co" {
    type forward;
    forward only;
    forwarders { 172.16.0.1; };
};
```

Use a documented server-group override only if the pinned release has no
forward-zone object. Do not hand-edit an ephemeral BIND container. Validate
the rendered configuration before continuing; a timeout to `172.16.0.1` is
expected while the hub is deallocated.

### 1.3 Rehearse the fresh Kea lease proof

Select a disposable client on the Phase 1 DHCP network. Never release/renew the
operator laptop's primary management/uplink interface. Before any VM start,
the readiness report must record:

- client alias and interface (MAC/client ID kept operator-local);
- a unique hostname such as `phase3-lease-<UTC timestamp>`;
- the exact OS-specific hostname + DHCP release/renew commands;
- the expected lab zone and maximum 120-second DDNS poll; and
- the command that restores the client's prior hostname/network state.

Supported renewal paths are:

```powershell
# Disposable Windows client, run locally on that client
ipconfig /release "<lab-adapter>"
ipconfig /renew "<lab-adapter>"
```

```bash
# Disposable Linux client, run locally on that client
sudo dhclient -r <lab-interface>
sudo dhclient -v <lab-interface>
```

Rehearse with a separate `phase3-preflight-*` hostname while the temporary
local DNS interface is active. Require:

1. Spatium shows a lease issued after the trigger time;
2. the matching A record is created by DHCP/DDNS, not manually;
3. local UDP and TCP queries return the lease address within 120 seconds
   (poll every five seconds with bounded query time/tries); and
4. the client is restored/cleaned up.

After restoring the client—whether the rehearsal passes or fails—stop the DNS
service, delete the temporary interface and route, and verify that the dummy
listener and route are absent. Treat this cleanup as a local `finally` action.

If no disposable client or deterministic renewal path exists, Checkpoint A
fails and no VM starts. Checkpoint B uses a new unique hostname and repeats the
same trigger; a static or pre-existing record cannot satisfy the exit
criterion.

### 1.4 Re-run the ignored-input and live-state guards

Without printing values, require:

- current public IP equals ignored `home_ip`;
- Windows/WSL WireGuard public key equals ignored `wg_peer_public_key`;
- `enable_test_vm_app`, `enable_test_vm_mgmt`,
  `enable_test_nic_app`, and `enable_test_nic_mgmt` are all `true`;
- `enable_private_resolver` is `false`;
- Azure account state is enabled and the active subscription matches the
  ignored `subscription_id`;
- remote state still tracks the hub, both test VMs, and both test NICs;
- all three VMs are `VM deallocated`; and
- no `dnspr-*` resolver resource exists.

Run a refresh-backed, unsaved plan:

```powershell
$env:Path = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;' + $env:Path
terraform -chdir=terraform/envs/lab plan `
  -input=false -lock-timeout=30s -no-color -detailed-exitcode
```

Required result: exit code `0`, `No changes`. Exit code `2` or any warning is
a hard stop. Do not use an old Phase 2 plan. If a correction is necessary,
create a fresh named plan from current state/HEAD, sanitize its summary,
compute SHA-256, and wait for approval before applying it or starting a VM.

### 1.5 Prepare and dry-run the independent VM watchdog

During implementation, add `scripts/phase3-vm-watchdog.ps1`. It must:

- accept an absolute UTC deadline, resource group, and the exact three VM
  names;
- contain deallocate/poll logic only—never VM start, resize, deploy, Terraform,
  resolver, or destroy commands;
- run as an independent hidden `pwsh` process so it survives an agent/tool
  interruption;
- at the deadline, deallocate all three VMs and poll instance view until all
  are `VM deallocated`;
- write only VM names, timestamps, and power states to a sanitized local log;
  and
- support `-DryRun` so Checkpoint A can exercise deadline/parsing behavior
  without Azure mutation.

Review the source and run the one-second `-DryRun`. A real VM start is
prohibited unless the helper passes and its independent process can be
observed.

### 1.6 Checkpoint A report

Create `docs/evidence/phase3/checkpoint-a-readiness.md` containing booleans,
versions, the no-change result, VM power states, planned timebox, and rollback
commands. Do not include raw configuration or sensitive values.

**CHECKPOINT A HARD STOP:** Present the readiness report and request explicit
authorization for Checkpoint B. All VMs must still be deallocated.

---

## Task 2 — Checkpoint B: bounded tunnel and DNS verification

Checkpoint B approval must explicitly authorize:

1. starting `vm-hub-ddi`;
2. starting `vm-test-app` only after the hub checks pass;
3. running the tests below for at most 60 minutes from the first VM start; and
4. deallocating all three VMs at the end or on any failure.

It does not authorize starting `vm-test-mgmt`, enabling Private Resolver, a
Terraform apply, or a destroy.

### 2.1 Arm closeout, then start the hub only

Immediately before arming the window, re-run every guard in 1.4. The account,
home `/32`, public-key comparisons, VM states, four preservation flags,
resolver false/absent checks, and Terraform exit-0 plan must all be no more
than five minutes old. If any result differs from the approved Checkpoint A
report, stop and return for review.

Set the absolute deadline before the first start, launch the reviewed watchdog
as a separate hidden process, and prove it remains running:

```powershell
$deadlineUtc = (Get-Date).ToUniversalTime().AddMinutes(60)
$watchdogArgs = @(
  '-NoProfile',
  '-File', (Resolve-Path 'scripts/phase3-vm-watchdog.ps1'),
  '-DeadlineUtc', $deadlineUtc.ToString('o'),
  '-ResourceGroup', 'rg-cham-lab',
  '-VmNames', 'vm-hub-ddi,vm-test-app,vm-test-mgmt'
)
$watchdog = Start-Process -FilePath (Get-Command pwsh).Source `
  -ArgumentList $watchdogArgs -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 2
if ($watchdog.HasExited) { throw 'Phase 3 watchdog failed to arm' }

az vm start --resource-group rg-cham-lab --name vm-hub-ddi
```

The executing agent also treats deallocation as an in-session `finally`
action and must not yield while compute is running. The watchdog is the
independent backstop, not a replacement for normal closeout.

If hub/app start fails for quota, capacity, policy, or any other reason, do not
resize, redeploy, recreate, or change region. Deallocate anything that started
and stop for a new state-backed plan/review.

Wait for Azure `VM running`, SSH reachability, and cloud-init completion.
Resolve the hub endpoint from `terraform output -raw hub_public_ip`; never
hardcode or record it in evidence.

### 2.2 Install or reuse the hub WireGuard key safely

On the hub:

1. If `/etc/wireguard/wg0.conf` still contains `REPLACE_ON_HOST`, create
   `/etc/wireguard/hub.key` once with `umask 077`, reuse it if already present,
   and replace only the marker.
2. If the marker is absent, require the stored key and configured private key
   to match without printing either. A mismatch is a stop condition; do not
   rotate implicitly.
3. Require the configured peer public key to match the laptop public key.
4. Keep `wg-quick@wg0` disabled for boot, start it only for this bounded
   session, verify `net.ipv4.ip_forward=1`, and return only the hub public key
   for the laptop configuration.

Use a stdin-fed root script so the private key is read/written only on the
guest and never placed in a process argument:

```powershell
$SSH_KEY = Join-Path $env:USERPROFILE '.ssh\cham_lab_ed25519'
if (-not (Test-Path -LiteralPath $SSH_KEY -PathType Leaf)) {
  throw 'Dedicated Phase 3 SSH key is missing'
}

$laptopWgPublic = (Get-Content `
  (Join-Path $env:USERPROFILE '.wg\cham-laptop.pub') -Raw).Trim()
if ($laptopWgPublic -notmatch '^[A-Za-z0-9+/]{43}=$') {
  throw 'Unexpected laptop WireGuard public-key format'
}

$hubKeyScriptTemplate = @'
set -euo pipefail
conf=/etc/wireguard/wg0.conf
key=/etc/wireguard/hub.key
expected_peer='__EXPECTED_LAPTOP_PUBLIC_KEY__'
test -f "$conf"
umask 077

if grep -Fxq 'PrivateKey = REPLACE_ON_HOST' "$conf"; then
  if [ ! -s "$key" ]; then
    wg genkey >"$key"
  fi
  python3 - <<'PY'
import os
from pathlib import Path

conf = Path("/etc/wireguard/wg0.conf")
key = Path("/etc/wireguard/hub.key")
marker = "PrivateKey = REPLACE_ON_HOST"
text = conf.read_text()
if text.count(marker) != 1:
    raise SystemExit("unexpected private-key marker count")
private = key.read_text().strip()
tmp = conf.with_suffix(".conf.tmp")
tmp.write_text(text.replace(marker, f"PrivateKey = {private}"))
os.chmod(tmp, 0o600)
os.replace(tmp, conf)
PY
else
  python3 - <<'PY'
from pathlib import Path

conf_lines = Path("/etc/wireguard/wg0.conf").read_text().splitlines()
configured = [line.split("=", 1)[1].strip() for line in conf_lines
              if line.startswith("PrivateKey = ")]
stored = Path("/etc/wireguard/hub.key").read_text().strip()
if len(configured) != 1 or configured[0] != stored:
    raise SystemExit("stored/configured hub key mismatch")
PY
fi

chown root:root "$key" "$conf"
chmod 600 "$key" "$conf"
test "$(stat -c '%U:%G:%a' "$key")" = 'root:root:600'
test "$(stat -c '%U:%G:%a' "$conf")" = 'root:root:600'
wg-quick strip "$conf" >/dev/null
configured_peer="$(awk '/^PublicKey = / {print $3}' "$conf")"
test -n "$configured_peer"
test "$configured_peer" = "$expected_peer"
systemctl disable wg-quick@wg0 >/dev/null
if systemctl is-enabled --quiet wg-quick@wg0; then
  exit 1
fi
systemctl start wg-quick@wg0
systemctl is-active --quiet wg-quick@wg0
test "$(sysctl -n net.ipv4.ip_forward)" = 1
printf 'HUB_KEY_STATE=OK\n'
printf 'HUB_PEER_MATCH=true\n'
'@
$hubKeyScript = $hubKeyScriptTemplate.Replace(
  '__EXPECTED_LAPTOP_PUBLIC_KEY__', $laptopWgPublic)
$hubKeyScript | ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes `
  "labadmin@$HUB_IP" 'sudo bash -s'

$hubWgPublic = (ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes `
  "labadmin@$HUB_IP" `
  'sudo sh -c "wg pubkey </etc/wireguard/hub.key"').Trim()
```

Keep `$hubWgPublic` operator-local for `wg0.conf`; do not echo or commit it.
The only reportable output is the boolean/state line.

The old generate-and-blind-`sed` sequence is prohibited because rerunning it
could create a new key file while leaving the old key in the active config.

### 2.3 Create the laptop config outside the repository

The operator creates root-owned `/etc/wireguard/wg0.conf` in Debian WSL2 with
mode `0600`, without placing the private value in agent-visible shell
history/output:

```ini
[Interface]
Address = 172.16.0.2/24
PrivateKey = <read securely from the WSL-only key file>
PostUp = iptables -t nat -C POSTROUTING -o %i -j MASQUERADE || iptables -t nat -A POSTROUTING -o %i -j MASQUERADE
PostDown = iptables -t nat -C POSTROUTING -o %i -j MASQUERADE && iptables -t nat -D POSTROUTING -o %i -j MASQUERADE || true

[Peer]
PublicKey = <hub public key>
Endpoint = <current Terraform hub public IP>:51820
AllowedIPs = 172.16.0.0/24, 10.10.0.0/16
PersistentKeepalive = 25
```

Require exactly those split-tunnel routes; never use a default route. Verify
IPv4 forwarding. The Compose DNS service remains stopped until real `wg0` is
up, then uses the exact-address port override rehearsed in Checkpoint A.

### 2.4 Prove the hub-only tunnel path

Bring up laptop `wg0`, start the native-Debian `dns-bind9` service with the
exact `172.16.0.2:53` TCP/UDP override, and require:

- a recent handshake on both peers and increasing transfer counters;
- laptop-to-hub and hub-to-laptop transfer-address reachability;
- exact listener/container identity and a hub-originated UDP/TCP query to
  `172.16.0.2:53` returning the expected on-premises answer;
- direct laptop UDP and TCP DNS queries to hub BIND9 for
  `db.azure.dwsolution.co` return `10.10.4.20`;
- the same query through local Spatium BIND9 succeeds; and
- laptop internet egress remains the home path, compared as a boolean without
  recording either public IP.

Run both the direct and composed forward paths explicitly:

```bash
# Debian WSL2: direct hub BIND path
dig +time=2 +tries=1 @172.16.0.1 db.azure.dwsolution.co
dig +tcp +time=2 +tries=1 @172.16.0.1 db.azure.dwsolution.co

# Debian WSL2: Spatium conditional-forward path
for name in db.azure.dwsolution.co vm-test-app.azure.dwsolution.co; do
  dig +time=2 +tries=1 @172.16.0.2 "$name"
  dig +tcp +time=2 +tries=1 @172.16.0.2 "$name"
done
```

```powershell
# Hub-to-Spatium reverse path
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes "labadmin@$HUB_IP" `
  'dig +time=2 +tries=1 @172.16.0.2 printer.lab.dwsolution.co'
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes "labadmin@$HUB_IP" `
  'dig +tcp +time=2 +tries=1 @172.16.0.2 printer.lab.dwsolution.co'
```

The Azure queries must return `10.10.4.20`; both reverse queries must match the
current Phase 1 lease-backed answer. A UDP pass cannot substitute for TCP.

Raw `wg show` includes public keys/endpoints and must not be committed. Record
only handshake freshness, nonzero-transfer booleans, and test results.

If any hub-only check fails, do not start the app. Run mandatory closeout.

### 2.5 Conditionally start and prove the app path

Only after 2.4 passes:

```powershell
az vm start --resource-group rg-cham-lab --name vm-test-app
```

Require `vm-test-mgmt` to remain `VM deallocated`. Obtain the app private IP
from `terraform output -raw testvm_app_ip`.

The retained app image has no Terraform/cloud-init guarantee that `dig` is
installed. Through Windows OpenSSH + ProxyJump, require it or install
`dnsutils` inside the temporary guest:

```powershell
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes -J "labadmin@$HUB_IP" `
  "labadmin@$APP_IP" `
  'command -v dig >/dev/null || (sudo apt-get update && sudo apt-get install -y dnsutils)'
```

Bound this preparation to five minutes. If it fails, do not weaken the
UDP/TCP criterion; run closeout.

Prove:

- laptop reaches the app private IP through WireGuard/hub forwarding and the
  app returns through its UDR;
- laptop resolves both `db.azure.dwsolution.co` and the auto-registered
  `vm-test-app.azure.dwsolution.co` through Spatium;
- hub BIND9 resolves `printer.lab.dwsolution.co` through `172.16.0.2`;
- app `resolvectl` and explicit UDP/TCP `dig @10.10.0.10` resolve the same
  on-premises record; and
- a newly issued/renewed Kea lease becomes resolvable from the app without a
  manual DNS record edit.

For the lease proof, choose a new `phase3-lease-<UTC timestamp>` hostname,
record the trigger time, execute the exact disposable-client renewal procedure
approved at Checkpoint A, and poll local DNS every five seconds for no more
than 120 seconds. Require Spatium's lease issue time and DDNS record creation
to be after the trigger, then query that same name from the app over UDP and
TCP. Restore the client afterward. Never substitute `printer` or a manually
created/static record for this fresh event.

Test the direct resolver hops before the composed path so failures are
localized cheaply:

1. Spatium local answer;
2. hub query to laptop transfer address;
3. laptop direct query to hub transfer address;
4. conditional-forwarded laptop query; and
5. app query through hub BIND9.

The app's explicit transport checks are:

```powershell
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes -J "labadmin@$HUB_IP" `
  "labadmin@$APP_IP" `
  'dig +time=2 +tries=1 @10.10.0.10 printer.lab.dwsolution.co'
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes -J "labadmin@$HUB_IP" `
  "labadmin@$APP_IP" `
  'dig +tcp +time=2 +tries=1 @10.10.0.10 printer.lab.dwsolution.co'
```

Repeat both commands for the unique fresh-lease name. Each answer must match
the corresponding Spatium lease; record only match booleans.

### 2.6 Mandatory closeout

Whether tests pass, fail, time out, or the session is interrupted:

1. disable/stop `wg-quick@wg0` on the hub while preserving its key/config, so
   a later generic VM boot cannot reopen the tunnel automatically;
2. bring down laptop `wg0` (tolerate already-down only);
3. stop the native-Debian Spatium services started for Phase 3 without deleting
   volumes;
4. deallocate `vm-test-app` and `vm-hub-ddi`;
5. issue deallocation for `vm-test-mgmt` as a defensive no-op;
6. wait until Azure reports all three `VM deallocated`;
7. confirm `enable_private_resolver = false` and no resolver resource exists;
   and
8. cancel the watchdog only after step 6 is proven.

Use the explicit cleanup sequence (the management deallocation is a defensive
no-op when the plan has been followed):

```powershell
ssh.exe -i "$SSH_KEY" -o IdentitiesOnly=yes "labadmin@$HUB_IP" `
  'sudo systemctl disable --now wg-quick@wg0'
wsl.exe -d Debian -- bash -lc 'if sudo ip link show wg0 >/dev/null 2>&1; then sudo wg-quick down wg0; fi'
# Run the exact native-Debian Compose stop command recorded at Checkpoint A.
az vm deallocate --resource-group rg-cham-lab --name vm-test-app
az vm deallocate --resource-group rg-cham-lab --name vm-hub-ddi
az vm deallocate --resource-group rg-cham-lab --name vm-test-mgmt
az vm list --resource-group rg-cham-lab --show-details `
  --query "[].{name:name,powerState:powerState}" --output table
```

Required final table: exactly the three expected names, all
`VM deallocated`. Retry the read until the control plane converges; never infer
deallocation merely from a successful command exit. Only then:

```powershell
if (-not $watchdog.HasExited) { Stop-Process -Id $watchdog.Id }
```

Do not wait for Checkpoint C review with a VM running.

---

## Task 3 — Checkpoint C: evidence, documentation, and plan closeout

After power-state verification:

1. Write sanitized results to:
   - `docs/evidence/phase3/checkpoint-b-tunnel.md`;
   - `docs/evidence/phase3/checkpoint-b-dns.md`; and
   - `docs/evidence/phase3/checkpoint-c-closeout.md`.
2. Update `docs/runbook.md` with the actual pinned Spatium start path,
   Azure-CLI path bootstrap, WSL key/config locations, endpoint refresh,
   idempotent hub-key behavior, the minimum VM sequence, and unconditional
   deallocation. Remove the current paid Private Resolver session from the
   Phase 3 runbook path and defer it to a separately planned experiment.
3. Update `docs/architecture.md` to show the proven native-Debian Docker,
   exact-address DNS listener, and WireGuard hops; remove any placeholder or
   Docker Desktop namespace assumption.
4. Rehearse only the runbook's zero-cost local steps and read-only preflight
   while all VMs remain deallocated. Use timestamps captured during the
   already-approved Checkpoint B window to prove operator-active setup was
   under ten minutes; do not restart a VM for documentation validation. Any
   later live rerun requires a new explicit VM-window approval and a newly
   armed 60-minute watchdog.
5. Run:

```powershell
git diff --check
terraform fmt -check -recursive
terraform -chdir=terraform/envs/lab validate
tflint --chdir=terraform/envs/lab --recursive
checkov -d terraform
```

6. Run an offline secret/evidence scan that reports only booleans/counts. It
   must verify that no tracked file contains the actual local SSH/WireGuard
   private key, `wg0.conf`, tfvars, backend config, state, or saved plan.
7. Re-run the unsaved Terraform detailed-exit-code plan. Required: `0` and
   `No changes`.
8. Mark README Phase 3 complete only if every exit criterion below passes.

**CHECKPOINT C HARD STOP:** Present evidence and the clean deallocated state.
Do not destroy or retain silently.

---

## Task 4 — Checkpoint D: explicit retain-or-destroy decision

### Option 1 — Retain deallocated

Keep all three VMs deallocated and record the continuing non-compute charges:
managed disks, the hub static public IP, Private DNS, networking metadata, and
state storage. Update `.continue-here.md` with the next owner and date.

### Option 2 — Destroy the lab (recommended for the lowest idle cost)

Generate a fresh saved destroy plan from current state and current `HEAD`.
Report its complete deletion summary and SHA-256, then stop for explicit
approval. Apply only that exact artifact after approval. Never run raw
`terraform destroy`, `-auto-approve`, or reuse a Phase 2 plan.

After an approved destroy, verify:

- `rg-cham-lab` is absent/empty;
- no lab VMs, disks, public IP, Private DNS, budget, or resolver resources
  remain;
- `rg-cham-tfstate` and its bootstrap state remain; and
- a fresh recreation plan can be generated for review but is not applied.

---

## Failure and recovery matrix

| Condition | Required response |
|---|---|
| Spatium checkout/runtime cannot be located | Restore Phase 1 locally; no VM start |
| Native Debian Docker context or the exact `172.16.0.2:53` TCP/UDP bind is not ready | Fix and retest locally; keep Docker Desktop stopped; no VM start |
| SSH/WireGuard key comparison fails | Restore original key or prepare a separately approved replacement plan |
| Home `/32`, subscription, flags, state, or Terraform drift is wrong | Stop; fresh saved plan/hash review before any VM |
| Independent watchdog cannot arm or remain running | Do not start a VM; repair and dry-run the watchdog locally |
| VM start fails for quota, capacity, policy, or another Azure condition | Deallocate anything started; do not resize, redeploy, or change region; return for a new reviewed saved plan if infrastructure must change |
| Hub key/config state is ambiguous | Do not rotate; deallocate hub and diagnose |
| Hub handshake/direct DNS fails | Do not start app; tunnel down and deallocate hub |
| Direct tunnel DNS works but Spatium forwarding fails | Deallocate; correct the local control-plane configuration |
| App path or DHCP-to-DNS proof fails | Capture sanitized failure, then deallocate hub/app |
| 60-minute deadline is reached | Stop testing immediately and run closeout |
| Deallocation command reports an error | Retry/read instance view until all three are confirmed deallocated; escalate if confirmation cannot be obtained |

## Exit criteria

All must hold before Phase 3 is marked complete:

1. Every VM begins and ends `VM deallocated`; management never starts, the
   independent watchdog is armed before the hub starts, and it is cancelled
   only after all three deallocations are verified.
2. Hub and laptop report a recent WireGuard handshake and bidirectional
   transfer without exposing key/endpoint material.
3. Laptop reaches the hub transfer address and app private IP while general
   internet egress stays at home.
4. Native Docker Engine in Debian WSL2—not Docker Desktop—publishes BIND9 only
   on `172.16.0.2:53` over UDP and TCP; laptop Spatium resolves the Azure seed
   and auto-registered app name through the tunnel over both protocols.
5. Hub and app resolve the on-premises record through the tunnel over UDP and
   TCP.
6. A fresh Kea lease resolves from the Azure app without a manual DNS edit.
7. `enable_private_resolver` remains false and no resolver resource exists.
8. Terraform still reports `No changes`; no unapproved apply occurred.
9. No private key/config/state/plan/tfvars/backend artifact is tracked or
   present in evidence.
10. The immediately pre-start guards are no more than five minutes old, the
    hub WireGuard service is disabled before closeout, and laptop `wg0` and
    Phase 3's native Debian containers are stopped.
11. Sanitized evidence and the corrected runbook are committed, and only then
    is the README Phase 3 checkbox marked complete.

## What completion looks like

For one bounded window, SpatiumDDI and Azure Private DNS behave as a single
hybrid namespace over an encrypted split tunnel. The app resolves a new
on-premises DHCP name, the laptop resolves Azure seed/auto-registered names,
and the evidence explains every hop. The session ends with laptop `wg0` down,
all three Azure VMs deallocated, Private Resolver absent, and an explicit
operator decision about retaining or destroying the idle lab.
