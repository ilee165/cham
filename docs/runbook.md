# Runbook

## Session start
1. `cd spatium && docker compose up -d` (laptop stack)
2. `terraform -chdir=terraform/envs/lab apply` (or merge a PR)
3. Bring up tunnel: `sudo wg-quick up wg0` on laptop
4. Verify: `dig db.azure.dwsolution.co` from laptop → private IP

## Session end — ALWAYS
1. Confirm `enable_private_resolver = false` (grep tfvars)
2. `terraform -chdir=terraform/envs/lab destroy` OR run destroy.yml
3. `az resource list -g rg-cham-lab -o table` → must be empty
   (public IPs and disks survive VM deletion)
4. `az consumption budget list` sanity check if unsure

## Private Resolver session (~$2, timeboxed)
1. Set phone timer: 3 hours
2. `enable_private_resolver = true` → apply
3. Point on-prem conditional forwarder at `resolver_inbound_ip` output
4. Test both directions, screenshot, capture dig output into docs/
5. `enable_private_resolver = false` → apply
6. Verify: portal shows no dnspr-* resources

## Split-horizon demo (interview)
1. Browser → https://www.dwsolution.co (tunnel DOWN) → public page
2. `sudo wg-quick up wg0`, flush DNS cache
3. Same URL → internal page served via BIND9 internal answer
4. Narrate: same FQDN, two answers, one repo managing both
