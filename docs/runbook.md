# Runbook

## CI prerequisites

- Two GitHub environments, each with at least one required reviewer and
  deployments permitted from `main` only: `lab` gates the Azure stack's apply
  and destroy, `cloudflare-prod` gates the public-DNS apply. They are separate
  because environment secrets are scoped to the environment and never to a
  job — one shared environment would put the DNS:Edit token for the live M365
  zone inside the secret scope of every lab teardown. Each gated job fails
  closed if its environment is missing a required-reviewer rule **or** a
  branch policy restricting it to `main`, and independently verifies the
  planned main commit. The apply and destroy jobs additionally refuse to run
  from any ref but `main`.
- The OIDC principal has Contributor at subscription scope and Storage Blob
  Data Contributor on the state storage account; shared keys are disabled.
- Saved plan binaries and their complete human-readable output never ship
  as workflow artifacts **or appear in workflow logs**: on a public
  repository any authenticated GitHub user can download both, and a plan
  embeds secret variable values (the home IP inside NSG rules), the full
  state snapshot, and the backend configuration (NEW-CR-01 + PR #11
  review). Each plan run stores `tfplan` and `plan-output.txt` (the
  complete delta) at
  `tfplans/lab/<apply|destroy>/<commit>-<run_id>-<run_attempt>/` in the
  private state storage account, written with `--overwrite false` so a
  reviewed attempt is immutable; the manifest binds the blob path and the
  artifact carries only the sanitized manifest and summary.
- **Reviewing a CI plan before approving its hash:** download the private
  review file and read the complete delta — the public run summary shows
  only actions, addresses, and the SHA-256:
  `az storage blob download --account-name <state account> --container-name
  tfplans --name "lab/apply/<commit>-<run_id>-<attempt>/plan-output.txt"
  --file plan-output.txt --auth-mode login` (destroy runs use
  `lab/destroy/.../destroy-output.txt`). Approve the apply dispatch only
  after reading it. A bootstrap lifecycle policy expires plan blobs and
  their versions after 7 days.
- Repository secrets/variables named by the workflows are configured
  (Phase 5): the three OIDC identifiers, the four lab config secrets, the
  two Cloudflare tokens, and the `BUDGET_START_DATE` variable. Neither a
  branch push nor a merge applies infrastructure; apply is a separate manual
  exact-artifact dispatch.
- **Two Cloudflare tokens, two blast radii.** `CLOUDFLARE_API_TOKEN_RO`
  (Zone:Read + DNS:Read) is a repository secret and is what the unattended
  nightly drift job uses — a bug there can misreport but never mutate.
  `CLOUDFLARE_API_TOKEN` (Zone:Read + DNS:Edit) lives **only** in the
  `cloudflare-prod` environment — not in `lab`, which `destroy.yml` also uses,
  and where approving a routine teardown would mechanically approve a job that
  can read it. Replacing the read-only token with the edit token "because it
  also works" removes the boundary the drift workflow was reviewed for.

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
   current `main` commit — the complete delta is in the private
   `plan-output.txt` blob (see "Reviewing a CI plan" above), not in the
   public run log. A merge never applies infrastructure.
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

Idempotent hub key behavior: the hub key install procedure (operator-run on
the hub; there is no tracked script for it in this repository) replaces the
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

## CI operations

**Plan.** Actions → `terraform-plan` → Run workflow on `main`. Pick `stack`
(`lab`, `cloudflare`, or `both`); the VM/NIC/resolver booleans apply to the
lab stack only. Nothing plans on a pull request — PRs run the
credential-free checks and nothing else. Note the run ID and the SHA-256
from the run summary, then read the complete delta from private storage
before approving anything (procedure under CI prerequisites above; the
Cloudflare stack's review file is
`cloudflare/apply/<commit>-<run_id>-<attempt>/cloudflare-plan-output.txt`).

**Apply.** Actions → `terraform-apply-reviewed-plan` → Run workflow from
`main` with the same `stack`, the `plan_run_id`, the `source_commit` (must
still be current `main`), the approved `plan_sha256`, and `confirm=APPLY`.
The run pauses at "Waiting for review" on `lab` for the Azure stack or
`cloudflare-prod` for the public one; approve it there. The job applies that
exact saved plan and nothing else — it never re-plans. Both the plan blob and
its manifest artifact live seven days, so the review window is a week for
both.

**Drift.** `nightly-drift` runs at 06:00 UTC and on dispatch, against the
committed `desired-records.json` (ADR-006). The public edge is checked first,
in its own credential-free invocation with the read-only token, so nothing on
the Azure side can suppress it. The Azure edge is then checked only if the
`azure.dwsolution.co` private zone actually exists, and every Azure step is
best-effort: a failed login or probe still lets the public result and its
issue land, then turns the run red at the end. Converged runs are green and
silent; drift is a green run plus an issue labelled `drift` carrying the
diff — or a comment on the open one, since only a single drift issue is kept
open at a time. Heal with `uv run cham-reconcile --apply`, then close it. A
run that fails loudly means exit 1, an exit code outside the 0/2/1 contract,
or an Azure edge that could not be reached — treat it as a broken tool, not
as drift.

Expect an Azure-edge ADD for `app` on any freshly rebuilt lab: Terraform
seeds only `db`, and `app` is reconciler-owned. That is real drift, not a
false positive — heal it the same way.

**Kill switch, from anywhere including a phone.** Actions →
`terraform-destroy`, `operation=plan` + `confirm=PLAN_DESTROY`, review the
deletions, then the same workflow with `operation=apply`, the plan run
ID/hash, and `confirm=DESTROY`.

**Two staleness traps.** `HOME_IP` must be re-set when the ISP rotates the
home address — the symptom is a CI apply that succeeds and locks you out of
SSH and WireGuard, because the NSG now allows a stranger's address instead
of yours. `BUDGET_START_DATE` must be bumped to the first of the current
month if a fresh CI apply fails variable validation on the budget start
date.

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

## Reconciler snapshot + drift operations (ADR-006)

The scheduled `nightly-drift` workflow checks **only the public Cloudflare
edge** (`--edge cloudflare-public`), because the Azure lab is destroyed
between sessions and a nightly job that is always red tells you nothing —
see the amended ADR-006 and the comment in `.github/workflows/drift.yml`.
The Azure edge is checked by hand during live sessions.

Every session that changed truth ends with:

1. `cd ddi-reconciler && uv run cham-reconcile --export desired-records.json`
   (the Spatium stack must be up). The export refuses to shrink the committed
   snapshot and marks an unprovable read `truth_verified=false`; CI rejects an
   unverified snapshot, so re-export from a healthy stack rather than forcing.
2. Review the `git diff` of `desired-records.json` — every dropped record is
   a standing delete order for the next `--apply`.
3. Commit the snapshot with the session's changes.

Checking and healing drift by hand:

- `uv run cham-reconcile --dry-run` → exit 0 converged / 2 drift / 1 error.
- Review the printed plan, then `uv run cham-reconcile --apply`. Apply
  re-verifies convergence and fails (exit 1) if the edge still drifts.
- A nightly `drift`-labeled issue contains the diff; heal locally with
  `--apply`, close the issue, and re-dispatch the workflow to confirm green.

## Split-horizon demo (interview)

What the split horizon **is** (proven, `docs/evidence/phase4/split-horizon.txt`):
the public internet resolves `www.dwsolution.co` through Cloudflare to the
GitHub Pages site, while the SpatiumDDI-managed resolver answers the same
name with the hub's private IP, whose nginx serves the internal page. Per
ADR-007, the internal answer belongs to the **SpatiumDDI resolver** — the
hub's own BIND9 has no `www` override and returns the public answer, so a
tunnel client pointed at `10.10.0.10` does NOT see the internal page.

1. Public half: `dig +short @1.1.1.1 www.dwsolution.co` → Pages addresses;
   `curl -s https://www.dwsolution.co | head -1` → `PUBLIC` page.
2. Internal half (lab up, Spatium stack running): `dig +short -p 1053
   @127.0.0.1 www.dwsolution.co` → `10.10.0.10`, then from a host that can
   reach the hub's private IP (hub SSH session, or a spoke VM):
   `curl -s http://10.10.0.10/ | head -1` → `INTERNAL` page.
3. Narrate: same FQDN, two simultaneous answers; the public half managed by
   this repo, the internal override rendered by the SpatiumDDI control plane;
   naming which resolver serves which answer is part of the demo (ADR-007).

The browser-over-tunnel version of this demo (tunnel up → same URL flips to
the internal page) requires the ADR-007 resolver unification plus the
operator WireGuard key step, both scheduled in Phase 5 — do not present it
as available until then.
