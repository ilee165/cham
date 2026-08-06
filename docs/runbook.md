# Runbook

## CI prerequisites

- GitHub environment `lab` has at least one required reviewer and permits
  deployments from `main` only. The workflows fail closed when reviewer
  protection is absent and independently verify the planned main commit.
- The OIDC principal has Contributor at subscription scope and Storage Blob
  Data Contributor on the state storage account; shared keys are disabled.
- Repository secrets/variables named by the workflow are configured. Neither a
  branch push nor a merge applies infrastructure; apply is a separate manual
  exact-artifact dispatch. As of the Phase 2 post-review correction, these
  secrets/variables are not yet configured; CI planning/apply remains a Phase 5
  prerequisite and will fail closed in the meantime.

## Session start
1. For Phase 3, use the pinned laptop runtime below. The repository's
   `spatium/` directory contains notes only and is not an executable checkout.
2. Set all four per-spoke VM/NIC flags explicitly, deriving them from
   refreshed Terraform state and `.continue-here.md` — never from a
   remembered or historical shape (a stale recipe here once implied
   deleting a live VM). After the East US 2 Checkpoint C completion the
   live topology has both test VMs and both NICs present (all four flags
   `true`); keep the resolver `false`.
3. Generate a saved plan and review its complete delta and SHA-256. Locally,
   use `terraform plan -out=tfplan`; in CI, manually dispatch `plan.yml` on the
   current `main` commit. A merge never applies infrastructure.
4. After explicit hash approval, apply that exact local plan file or manually
   dispatch `apply.yml` with the plan run ID, source commit, approved SHA-256,
   and `confirm=APPLY`. The `lab` environment must have required reviewers.
5. Follow the proven live-window sequence below; never start a VM outside an
   explicitly approved, watchdog-armed window.
6. Bring up tunnel: `sudo wg-quick up wg0` on laptop (only after the hub
   endpoint has been refreshed from Terraform output).
7. Start the pinned Phase 3 stack using the exact-address command below.
8. Verify: `dig db.azure.dwsolution.co` from laptop → private IP

### Phase 3 local runtime pin (Checkpoint A)

- Checkout: `/opt/spatiumddi-phase3`
- Commit: `091f8a14241611b1d7fe8bc6352828b0b30cdbe4`
- Image tag: `2026.07.30-1`
- Runtime: native Debian Docker Engine 29.7.1 with Compose v5.4.0. Docker
  Desktop must remain stopped.
- Keep one foreground Debian WSL session open for the entire timebox. This
  host otherwise suspends WSL and restarts the native daemon, which interrupts
  the API and agents.

The ignored `.env`, administrator password, and
`docker-compose.phase3-local.yml` stay in that checkout and must never be
copied into the repository. Start the DNS profile only after real `wg0` is up
with `172.16.0.2/24`; the override publishes DNS only on
`172.16.0.2:53` over UDP and TCP.

```bash
cd /opt/spatiumddi-phase3
docker compose -f docker-compose.yml -f docker-compose.phase3-local.yml --profile dns-bind9 --profile dhcp up -d
```

Stop the Phase 3 services without deleting their persistent volumes:

```bash
cd /opt/spatiumddi-phase3
docker compose -f docker-compose.yml -f docker-compose.phase3-local.yml --profile dns-bind9 --profile dhcp down --remove-orphans
```

Checkpoint A ended with all containers stopped, the volumes retained, and the
temporary dummy interface, route, listener, and DHCP client network absent.

### Phase 3 live-window sequence (proven at Checkpoint B, 2026-08-06)

Azure CLI path bootstrap for local shells:

```powershell
$env:Path = 'C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin;' + $env:Path
```

Key and configuration locations:

- Laptop WireGuard keys: `%USERPROFILE%\.wg` (only the public file is ever
  read or compared by tooling; the private value stays operator-local).
- Laptop WireGuard config: `/etc/wireguard/wg0.conf` in Debian WSL2,
  `root:root` mode `0600`, split-tunnel `AllowedIPs` only.
- Hub: `/etc/wireguard/hub.key` and `/etc/wireguard/wg0.conf`, `root:root`
  mode `0600`; `wg-quick@wg0` stays disabled for boot.
- Dedicated SSH key: `%USERPROFILE%\.ssh\cham_lab_ed25519`. The Windows
  OpenSSH client needs a Windows-style path for `-i`, and `ssh -J` does not
  pass `-i` to the jump hop — use an explicit `ProxyCommand` that carries the
  identity for laptop → hub → app.

Endpoint refresh: resolve the hub endpoint with
`terraform -chdir=terraform/envs/lab output -raw hub_public_ip` immediately
before editing the peer `Endpoint`; never hardcode it or record it in
evidence.

Idempotent hub key behavior: the install script replaces the
`REPLACE_ON_HOST` marker exactly once and otherwise requires the stored and
configured keys to match. A mismatch is a stop condition; nothing rotates
implicitly on retry.

Minimum VM sequence (unconditional):

1. Arm the deallocation-only watchdog (`scripts/phase3-vm-watchdog.ps1`)
   with an absolute UTC deadline of at most 60 minutes and prove it is
   running before any start.
2. Start `vm-hub-ddi` only; wait for `VM running`, SSH, and cloud-init.
3. Run every hub tunnel/DNS gate; only then start `vm-test-app`.
4. Never start `vm-test-mgmt`.
5. Closeout always runs: disable hub `wg-quick@wg0`, bring laptop `wg0`
   down, stop the Compose profiles (volumes retained), deallocate all three
   VMs, confirm `VM deallocated` from instance view, and cancel the watchdog
   only after that confirmation.

## Session end — ALWAYS
1. Confirm `enable_private_resolver = false` (grep tfvars)
2. Generate a saved destroy plan (`terraform plan -destroy -out=destroy.tfplan`)
   or dispatch `destroy.yml` with `operation=plan` and
   `confirm=PLAN_DESTROY`. Review every deletion and the SHA-256.
3. After separate approval, apply that exact destroy plan or dispatch the same
   workflow with `operation=apply`, its plan run ID/hash, and
   `confirm=DESTROY`. Never run raw `terraform destroy -auto-approve`.
4. `az resource list -g rg-cham-lab -o table` → must be empty
   (public IPs and disks survive VM deletion)
5. `az consumption budget list` sanity check if unsure

## Private Resolver experiment (deferred — not part of Phase 3)

Phase 3 completed with `enable_private_resolver = false` throughout. The
paid resolver session below is deferred to a separately planned and
separately approved experiment (~$2, timeboxed).
1. Set phone timer: 3 hours
2. Set `enable_private_resolver = true`, generate a fresh saved plan, and
   confirm it contains the resolver endpoints, ruleset, three VNet links, the
   inbound-subnet return route table and association, and the DNS-only hub NSG
   rule. Apply only after approving that exact plan hash.
3. Point on-prem conditional forwarder at `resolver_inbound_ip` output
4. Test on-prem-to-Azure through the inbound endpoint. For the outbound path,
   query Azure-provided DNS (`168.63.129.16`) explicitly from a spoke and
   verify the forwarding-ruleset path to on-premises DNS.
5. Remember that the spokes still use the hub BIND VM as their configured DNS
   server. Ruleset VNet links affect queries sent to Azure-provided DNS; this
   session validates the managed path but does not cut ordinary spoke clients
   over to it. Screenshot and capture dig output into docs/.
6. Set `enable_private_resolver = false`, generate and separately approve the
   exact removal plan, then apply that saved plan.
7. Verify: portal shows no dnspr-* resources

## Split-horizon demo (interview)
1. Browser → https://www.dwsolution.co (tunnel DOWN) → public page
2. `sudo wg-quick up wg0`, flush DNS cache
3. Same URL → internal page served via BIND9 internal answer
4. Narrate: same FQDN, two answers, one repo managing both
