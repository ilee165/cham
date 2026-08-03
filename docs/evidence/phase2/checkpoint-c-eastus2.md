# Phase 2 Checkpoint C — eastus2 Simultaneous Three-VM Topology Tests

Executed 2026-08-03 as gate 3 of the eastus2 recovery. The operator approved
saved plan `checkpoint-c-eastus2-f1als-v7.tfplan` (SHA-256
`5c789f876e0927c740e96fb9ca94242f93edd9604fefe81ca440ad072d176cff`, generated
from commit `df274a8`, 4 add / 0 change / 0 destroy) at 19:23 EDT. The hash
was re-verified immediately before apply and matched.

## Apply

- Started 23:24:44 UTC, completed 23:26:58 UTC:
  `Apply complete! Resources: 4 added, 0 changed, 0 destroyed.`
- Created: app and management test NICs plus both `Standard_F1als_v7` test
  VMs (NVMe disk controller), private IPs `10.10.4.4` (app) and `10.10.8.4`
  (mgmt). No read-path inconsistency recurred.
- Regional cores in use: hub 2 + app 1 + mgmt 1 = 4 of 4. No resize step
  existed anywhere in the sequence.
- The one-hour bounded window opened with the management VM create at about
  23:26 UTC; all tests and the final deallocation completed by about
  23:38 UTC (~12 minutes).

## Test results — all eight pass

1. **SSH + cloud-init** — both test VMs reachable over SSH via the hub
   jump; `cloud-init status: done` on both. PASS.
2. **Effective routes** — both test NICs show the user-defined default
   route `0.0.0.0/0 → VirtualAppliance (hub NVA private IP)` and
   `10.20.0.0/16 → VirtualAppliance`. PASS.
3. **Hub DNS + seed** — from both spokes, the seed record
   `db.azure.dwsolution.co → 10.10.4.20` and an external name resolve via
   the hub BIND resolver. PASS.
4. **Auto-registration** — `vm-test-app → 10.10.4.4` and
   `vm-test-mgmt → 10.10.8.4` registered with `isAutoRegistered=True`; the
   seed record remains `False`; cross-spoke name resolution works both
   directions. PASS.
5. **Egress via hub SNAT** — public egress IP observed from each test VM
   equals the hub public IP: app match=true, mgmt match=true (booleans
   only; the NSG transit rules that fix the NCUS egress failure are part
   of the base configuration here). PASS.
6. **App→management isolation** — TCP 22 from app to the management VM:
   BLOCKED. PASS.
7. **Hub→management reachability** — TCP 22 from the hub to the management
   VM: OPEN. PASS.
8. **Ingress posture** — effective NSG on the hub NIC: SSH 22 and
   WireGuard UDP 51820 allowed only from the operator's home /32; DNS 53
   only from lab/on-prem/tunnel RFC1918 ranges; the four reviewed
   spoke-transit rules present; `DenyAllOtherInbound` backstop; WireGuard
   service `inactive`. PASS.

## Closeout

- All three VMs deallocated by about 23:38 UTC; `az vm list -d` confirms
  `VM deallocated` for hub, app, and management. Compute billing stopped.
- Retained while deallocated: managed disks, static public IP, private DNS,
  networking, and state storage — small ongoing charges.
- Checkpoint C is **complete**. Phase 2 validation semantics (simultaneous
  three-VM topology) were fully exercised in eastus2.
- No teardown action was taken. The eastus2 teardown decision (Checkpoint D
  destroy of the 36-resource lab stack versus retention) awaits a separate
  operator-approved saved plan.
