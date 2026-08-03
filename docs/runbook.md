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
1. `cd spatium && docker compose up -d` (laptop stack)
2. Set all four per-spoke VM/NIC flags explicitly to the intended state. For
   the current documented partial state: app VM/NIC `true`, management NIC
   `true`, management VM `false`; keep the resolver `false`.
3. Generate a saved plan and review its complete delta and SHA-256. Locally,
   use `terraform plan -out=tfplan`; in CI, manually dispatch `plan.yml` on the
   current `main` commit. A merge never applies infrastructure.
4. After explicit hash approval, apply that exact local plan file or manually
   dispatch `apply.yml` with the plan run ID, source commit, approved SHA-256,
   and `confirm=APPLY`. The `lab` environment must have required reviewers.
5. Bring up tunnel: `sudo wg-quick up wg0` on laptop
6. Verify: `dig db.azure.dwsolution.co` from laptop → private IP

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

## Private Resolver session (~$2, timeboxed)
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
