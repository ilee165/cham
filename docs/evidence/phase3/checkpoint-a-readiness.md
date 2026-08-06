# Phase 3 Checkpoint A Readiness Evidence

Captured 2026-08-04. Checkpoint A is a zero-cost local and read-only cloud
gate. No Azure VM was started, no Terraform plan was saved or applied, and no
Azure resource was changed.

## Result and hard stop

| Check | Sanitized result |
| --- | --- |
| Checkpoint A | PASS |
| Checkpoint B authorization | NOT GRANTED |
| Azure mutation/apply | `false` |
| Any VM started | `false` |
| All three VMs deallocated at final guard | `true` |
| Private DNS Resolver present | `false` |
| Final live guard | `2026-08-04T14:55:54Z` |

## Verified toolchain and runtime pin

| Component | Verified version or pin |
| --- | --- |
| Terraform | 1.15.8 |
| Azure CLI | 2.88.0 |
| TFLint | 0.64.0 |
| Checkov | 3.3.9 |
| Windows OpenSSH | OpenSSH 9.5p2 / LibreSSL 3.8.2 |
| Debian WireGuard tools | 1.0.20210914; kernel interface probe passed |
| Native Debian Docker Engine | 29.7.1 |
| Docker Compose | v5.4.0; `!override` supported |
| SpatiumDDI checkout | `/opt/spatiumddi-phase3` |
| SpatiumDDI commit | `091f8a14241611b1d7fe8bc6352828b0b30cdbe4` |
| SpatiumDDI image tag | `2026.07.30-1` |

Docker Desktop was stopped. The data-plane containers ran on the native
Debian daemon, and a held foreground WSL session prevented the host from
cycling that daemon during the rehearsal.

## Local security and runtime checks

| Check | Result |
| --- | --- |
| SSH private-key parent/key ACL restricted | `true` |
| WireGuard directory/key ACL restricted | `true` |
| Private key material printed or copied into the repository | `false` |
| Native Debian daemon/context/one `dockerd` proved | `true` |
| Pinned Spatium services healthy | `true` |
| DNS published only on `172.16.0.2:53/udp` and `:53/tcp` | `true` |
| Rendered query/cache/recursion ACLs equal approved sources | `true` |
| Zone transfer restricted to the hub transfer address | `true` |
| `azure.dwsolution.co` rendered forward-only to the hub | `true` |
| Known Phase 1 record returned expected address over UDP/TCP | `true` |
| Actual BIND container traffic selected host `wg0` | `true` |
| No-peer UDP/TCP probes timed out and incremented `wg0` TX | `true` |

The first control-plane diagnostic exposed WSL lifecycle churn rather than an
API defect: isolated WSL calls restarted the daemon and its containers. The
final rehearsal held WSL open, after which DNS and DHCP agent rendering
converged without resets.

## Fresh Kea lease and automatic DDNS rehearsal

| Check | Result |
| --- | --- |
| Disposable client alias | `phase3-preflight-container` |
| Disposable interface | `eth0` on Docker-only `10.20.0.0/24` |
| Operator management/uplink interface touched | `false` |
| MAC/client identifier recorded in evidence | `false` |
| Successful trigger | `2026-08-04T14:04:28.886932Z` |
| Lease address within `10.20.0.200-10.20.0.220` | `true` |
| Spatium lease issue time after trigger | `true` |
| Matching A record absent before trigger | `true` |
| Matching A record created automatically after trigger | `true` |
| Local UDP and TCP answers matched the fresh lease | `true` |
| Converged within the 120-second, five-second poll | `true` |
| Disposable client removed | `true` |
| Preflight lease/record artifacts removed | `true` |

The successful client sent a short DHCP option-12 hostname. Do not add an
option-81 FQDN: the observed policy sanitizes the entire FQDN into one label
before applying the configured `lab.dwsolution.co` override. The rehearsed
Alpine procedure was:

```bash
hostname=phase3-preflight-$(date -u +%Y%m%d%H%M%S)
docker run -d --name phase3-preflight-client --hostname "$hostname" --network phase3-preflight-l2 --cap-add NET_ADMIN --cap-add NET_RAW alpine:3.22 sleep 600
docker exec phase3-preflight-client sh -ec "ip address flush dev eth0; udhcpc -i eth0 -x hostname:$hostname -n -q -t 5 -T 3"
# Poll every five seconds for at most 120 seconds, then query the FQDN over UDP and TCP.
docker exec phase3-preflight-client sh -c "udhcpc -i eth0 -x hostname:$hostname -n -q -R -t 1 -T 1 >/dev/null 2>&1"
docker rm -f phase3-preflight-client
```

Checkpoint B must use a new `phase3-lease-<UTC>` name and repeat the same
temporal lease/DDNS assertions from the Azure app.

## Ignored-input, state, and no-drift guards

No compared value is included below.

| Check | Result |
| --- | --- |
| Current public IP equals ignored `home_ip` | `true` |
| Derived/stored WireGuard public key equals ignored input | `true` |
| App/mgmt VM and NIC flags all explicitly enabled | `true` |
| `enable_private_resolver` is false | `true` |
| Azure account enabled and subscription equals ignored input | `true` |
| Remote state tracks hub, both test VMs, and all three NICs | `true` |
| No `Microsoft.Network/dnsResolvers` resource exists | `true` |
| Refresh-backed plan detailed exit code | `0` |
| Refresh-backed plan result | `No changes` |
| Terraform plan warning count | `0` |
| Saved plan created | `false` |

Final VM power states:

| VM | Power state |
| --- | --- |
| `vm-hub-ddi` | `VM deallocated` |
| `vm-test-app` | `VM deallocated` |
| `vm-test-mgmt` | `VM deallocated` |

## Independent watchdog

`scripts/phase3-vm-watchdog.ps1` passed:

- PowerShell parser validation;
- source scanning for prohibited Azure/Terraform operations;
- exact resource-group and three-VM allow-list validation;
- absolute UTC and maximum 60-minute deadline validation;
- a one-second `-DryRun` with no Azure call;
- sanitized three-line log validation; and
- a separately launched hidden process that was observed running and exited
  successfully.

The helper contains only deallocation requests and instance-view polling. It
cannot start, resize, deploy, destroy, or apply infrastructure.

## Local finally cleanup

| Check | Result |
| --- | --- |
| Spatium containers stopped | `true` |
| Persistent Spatium volumes retained | `true` |
| Temporary DNS listener absent | `true` |
| Temporary dummy `wg0` absent | `true` |
| Temporary `10.10.0.0/16` route absent | `true` |
| Disposable DHCP network absent | `true` |

## Checkpoint B timebox and rollback

Checkpoint B remains blocked pending explicit approval. Its maximum window is
60 minutes. Start the hub first; start the app only after the hub tunnel and
DNS gates pass; never start the management VM. Arm the independent watchdog
before any start.

Normal and watchdog rollback use the same exact Azure targets:

```powershell
$vms = @('vm-hub-ddi', 'vm-test-app', 'vm-test-mgmt')
foreach ($vm in $vms) {
    az vm deallocate --resource-group rg-cham-lab --name $vm --no-wait
}
foreach ($vm in $vms) {
    az vm get-instance-view --resource-group rg-cham-lab --name $vm --query "instanceView.statuses[?code=='PowerState/deallocated'].displayStatus" --output tsv
}
```

Local rollback:

```bash
sudo wg-quick down wg0 || true
cd /opt/spatiumddi-phase3
docker compose -f docker-compose.yml -f docker-compose.phase3-local.yml --profile dns-bind9 --profile dhcp down --remove-orphans
```

## Sanitization

This evidence omits subscription/tenant identifiers, public and home IPs,
backend details, contacts, SSH/WireGuard key values, private configuration,
MAC/client identifiers, raw Terraform state/plan output, raw API responses,
and saved plan artifacts.
