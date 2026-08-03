# Phase 2 Checkpoint B — eastus2 Rebuild

Executed 2026-08-03 as gate 2 of the eastus2 recovery. The operator approved
saved plan `checkpoint-b-eastus2-v7.tfplan` (SHA-256
`16347d147c8d32291b5855feb136409bf9f8c6e4a4d47e84537da404bf78f16e`, generated
from commit `dc01ce1`, 32 add / 0 change / 0 destroy) at 18:25 EDT and
directed the sequence to continue.

## Apply chronology

The apply required three rounds because the eastus2 Network RP read path
returned intermittent 404s for freshly created resources for roughly 25
minutes. Working hypothesis: `rg-cham-lab` was deleted in North Central US at
22:10 UTC and recreated with the same name in eastus2 at 22:26 UTC, and some
ARM/NRP frontends kept resolving the stale mapping. The activity log shows
every write `Succeeded`, no delete operations after the Checkpoint D tail,
and no caller other than the operator identity — the failures were purely
read-path: `Provider produced inconsistent result after apply … Root object
was present, but now absent`, and 404s while polling parent VNets.

1. **Round one (22:26–22:28 UTC)** — hash re-verified, apply of the approved
   plan. 9 resources landed in state; the hub public IP and app VNet were
   created successfully but dropped from state as provider-inconsistent
   (orphans); the remaining creates failed on parent-VNet 404s.
2. **Recovery** — a 60-second poll confirmed direct GETs healed within two
   minutes. CLI `terraform import` failed on a legacy import-graph for_each
   limitation, so temporary plannable `import` blocks (committed as
   `0ad805c`, subscription ID via `var.subscription_id`) carried the orphans
   inside the remainder plan. Set-difference verification proved the
   remainder (2 import + 21 add + 9 in state = the approved 32, 0 change,
   0 destroy) before apply.
3. **Round two (22:33–22:38 UTC)** — both imports plus the hub VM, hub
   subnets, and app subnet associations landed (state 19 of 32); the read
   path flapped again, orphaning the app-to-hub peering and tainting three
   healthy resources (`snet-shared` and the two workload subnet
   associations, all verified present and correctly attached in Azure).
4. **Stabilization** — after a ~10 minute wait, five consecutive probes 30
   seconds apart all passed. Import blocks were rotated to the peering
   (`e8c4917`), the three tainted-but-healthy resources were untainted
   (state metadata only), and the round-three plan verified as 1 import +
   12 add + 0 change + 0 destroy, all creates inside the approved set. An
   intermediate plan before the untaints showed 3 replacements and was
   discarded without apply.
5. **Round three (~23:00 UTC)** — `Apply complete! Resources: 1 imported,
   12 added, 0 changed, 0 destroyed.` State tracks 32 of 32. The spent
   import scaffolding was removed (`c84a521`).

## Verification

- Drift plan after completion: `No changes. Your infrastructure matches the
  configuration.` (full refresh — also proves the read path stabilized).
- Four peerings `Connected` (hub↔app, hub↔mgmt).
- Private DNS zone with three links; auto-registration enabled for app and
  mgmt only; seed record `db → 10.10.4.20` present.
- Subscription budget `budget-cham-lab` ($50) recreated.
- Hub VM `Standard_D2als_v7` (NVMe controller): `Provisioning succeeded`,
  `VM running`; over SSH: cloud-init `done`, BIND `active`,
  `net.ipv4.ip_forward = 1`, NAT `MASQUERADE 10.10.0.0/16 → !10.0.0.0/8`
  on eth0, WireGuard inactive (expected at base posture).
- The hub public IP changed with the region move; local WireGuard endpoint
  and firewall references must be updated to the new address (value in
  `terraform output hub_public_ip`; not recorded here).

Checkpoint B is complete. Gate 3 (Checkpoint C) requires a fresh saved plan
adding the two `Standard_F1als_v7` test VMs and NICs, hash-approved before
apply.
