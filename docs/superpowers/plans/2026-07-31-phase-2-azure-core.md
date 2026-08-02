# Phase 2 — Azure Core Candidate Implementation Plan

**Status:** Local Tasks 1-3 and 4.1-4.2 are implemented and statically validated; Azure authentication and Checkpoints A-D remain pending.
**Lifecycle owner:** GSD. Eventual execution uses gsd-execute-phase only after approval.
**Research basis:** 2026-08-01-phase-2-azure-core-research.md.

> EXECUTION GATE: User plan approval authorizes repository code work. Tool installation/download was separately approved and completed on 2026-08-02. Azure login and provider readiness, bootstrap apply, base apply, test-VM enablement, and destroy remain gated as specified below. Every cloud mutation requires separate approval at execution time.

## Goal

Take the authored Terraform from an unvalidated baseline to a reproducible Azure hub-and-spoke lab that has been statically checked, applied from reviewed plans, tested from temporary spoke workloads, destroyed cleanly, and proven ready to recreate.

## Architecture

- One lab resource group: rg-cham-lab.
- Hub VNet 10.10.0.0/22 with one Standard_B1s Linux VM at 10.10.0.10.
- The hub VM is both a BIND9 DNS forwarder and a network virtual appliance.
- App spoke 10.10.4.0/22 and management spoke 10.10.8.0/22, instantiated from one module.
- Bidirectional hub/spoke peerings; no direct spoke trust.
- Spoke default and on-prem routes use the hub NVA.
- Private DNS zone azure.dwsolution.co links to hub and spokes; auto-registration is enabled only on spokes.
- Azure Storage remote state is created by the bootstrap root.
- Azure DNS Private Resolver stays disabled throughout Phase 2.

## Scope

Phase 2 includes:

1. Terraform security and correctness fixes required before the first apply.
2. Default-off verification VMs in both spokes.
3. Offline Terraform validation and provider lock files.
4. Portable remote-state bootstrap and initialization.
5. A reviewed base plan and base apply.
6. Temporary test-VM plan/apply and positive/negative topology checks.
7. A reviewed destroy plan, destroy proof, and no-apply recreation plan.
8. Sanitized evidence and documentation closeout.

Phase 2 excludes:

- Repository-wide line-ending normalization.
- The unrelated dangling import in ddi-reconciler/providers/azure.py.
- WireGuard tunnel activation or hub private-key installation.
- Azure DNS Private Resolver.
- Cloudflare resources, reconciler v2, CI/CD, and production deployment. Task 4 changes only Cloudflare's shared-backend declaration; it does not plan or create Cloudflare resources.

## Non-negotiable constraints

- No apply or destroy without a fresh saved plan and explicit user approval.
- enable_private_resolver remains false in every Phase 2 plan.
- enable_test_vm defaults false and is enabled only for the approved verification window.
- home_ip must validate as one IPv4 /32; never use 0.0.0.0/0.
- No private key, tfvars, backend config, plan, state, credential, tenant/subscription ID, home IP, or personal email is committed as evidence.
- Azure budgets are notifications, not spend caps.
- Do not claim free-tier eligibility. Before apply, show current subscription-specific cost expectations for VMs, disks, public IP, and state storage.
- The live plan output wins over resource-count estimates.
- README Phase 2 remains unchecked until every live exit criterion passes.
- Planning verification may pass while all live checks remain deferred.

## Decisions selected for review

1. **Execution host:** native Windows PowerShell 7. If Linux/WSL is selected, convert shell-specific commands and re-run plan verification.
2. **Backend authentication:** Microsoft Entra ID with Storage Blob Data Contributor; no access keys in files or arguments.
3. **Repository hygiene:** mixed line endings and the Python stub are excluded.
4. **Cloud authority:** plan approval authorizes code work only. Bootstrap apply, base apply, verification-VM apply, and destroy each retain an execution-time checkpoint.

## Dependency map

~~~text
Gate 0: user review and toolchain choice
  -> Task 1: Terraform correctness and security
  -> Task 2: default-off verification workload
       Task 2 follows Task 1 because both edit spoke/root variables
  -> Task 3: offline validation and lock files
  -> Task 4a: remote-state code and saved bootstrap plan
  -> Checkpoint A: bootstrap plan review and approval
  -> Task 4b: bootstrap apply and backend initialization
  -> Task 5: local inputs and saved base plan
  -> Checkpoint B: base plan review, cost review, and approval
  -> Task 6: base apply and base verification
  -> Task 7: saved verification-VM plan
  -> Checkpoint C: temporary workload cost review and approval
  -> Task 8: verification-VM apply and topology proof
  -> Task 9: saved destroy plan
  -> Checkpoint D: destructive review and approval
  -> Task 10: destroy, recreation proof, and closeout
~~~

Tasks 1–10 are serial. Tasks 1 and 2 overlap Terraform variable files and must not run concurrently. Cloud operations are additionally checkpointed.

---

## Gate 0 — Review and toolchain readiness

**Files changed:** none.

- [x] User approved the four decisions above on 2026-08-02.
- [x] User explicitly approved required tool installation/download on 2026-08-02.
- [x] The host has Terraform 1.15.8, Azure CLI 2.88.0, TFLint 0.64.0, Checkov 3.3.9, Git 2.54.0, OpenSSH 10.0p2, and WireGuard tools 1.0.20260223.
- [ ] The account can create networking, VMs, budgets, storage, and role assignments.
- [x] The branch is codex/phase-2-planning and only expected planning changes existed when approval was recorded.

~~~powershell
git branch --show-current
git status --short
terraform version
az version
tflint --version
checkov --version
ssh -V
wg --version
~~~

Stop if the host choice changes, tool installation is not approved, permissions are insufficient, or unrelated changes overlap planned files.

---

## Task 1 — Terraform correctness and security

**Files:**

- Create: terraform/bootstrap/variables.tf
- Modify: terraform/bootstrap/main.tf
- Modify: terraform/envs/lab/providers.tf
- Modify: terraform/envs/lab/variables.tf
- Modify: terraform/modules/hub/main.tf
- Modify: terraform/modules/hub/variables.tf
- Modify: terraform/modules/hub/cloud-init.yml.tpl
- Modify: terraform/modules/spoke/main.tf
- Modify: terraform/modules/spoke/variables.tf
- Modify: terraform/modules/private-dns/main.tf

**Interfaces produced:**

- Explicit subscription selection for bootstrap and lab providers.
- Enforced IPv4 /32 home ingress.
- Explicit Standard public IP SKU.
- A true terminal deny on the hub NSG.
- wg_transfer_cidr on hub and spoke modules, default 172.16.0.0/24.
- BIND9 recursion for Azure, on-prem, and transfer networks.
- Guest forwarding and deterministic internet-only SNAT.

### 1.1 Make subscription selection explicit

In both AzureRM provider blocks:

~~~hcl
provider "azurerm" {
  subscription_id = var.subscription_id
  features {}
}
~~~

Create terraform/bootstrap/variables.tf with a required subscription_id string. Keep and use the existing lab subscription_id variable.

### 1.2 Enforce a single IPv4 /32

Add this validation to root and hub-module home_ip variables:

~~~hcl
validation {
  condition = (
    can(cidrhost(var.home_ip, 0)) &&
    can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", var.home_ip))
  )
  error_message = "home_ip must be one valid IPv4 host expressed as a /32."
}
~~~

### 1.3 Close the hub NSG default-rule gap

- Keep UDP 51820 and TCP 22 allows from home_ip.
- Keep DNS port 53 for approved internal and transfer networks.
- Change DenyAllOtherInbound at priority 4000 to source_address_prefix = "*".
- Confirm every necessary allow has a lower numeric priority.
- Set sku = "Standard" explicitly on azurerm_public_ip.hub.

### 1.4 Prepare BIND and the NVA

Rendered cloud-init must:

- enable net.ipv4.ip_forward;
- install wireguard, bind9, bind9-utils, and iptables-persistent;
- leave WireGuard disabled with REPLACE_ON_HOST as the private-key marker;
- allow query/recursion from 10.10.0.0/16, onprem_cidr, wg_transfer_cidr, and localhost;
- forward general queries to 168.63.129.16;
- forward lab_zone to onprem_dns_ip;
- start BIND;
- discover the default outbound interface from the guest route table;
- add one idempotent POSTROUTING MASQUERADE rule for 10.10.0.0/16 when destination is outside 10.0.0.0/8;
- persist the NAT rule.

Pass wg_transfer_cidr through the hub templatefile call. Define it on hub and spoke modules with default 172.16.0.0/24.

### 1.5 Preserve spoke isolation

Add a spoke inbound allow for wg_transfer_cidr at priority 111, after on-prem allow and before deny rules. Keep DenyOtherSpokes authoritative for other 10.10.0.0/16 sources.

Correct comments to state that spoke-to-spoke traffic is denied and Terraform owns seed Private DNS records while the reconciler later owns only a disjoint managed set.

### 1.6 Local task check

~~~powershell
terraform fmt -recursive terraform
git diff --check
git diff -- terraform
~~~

Invariant: only listed files changed; resolver enable/count behavior is untouched.

**Suggested atomic commit:** fix(terraform): harden Azure provider, DNS, NVA, and NSGs

---

## Task 2 — Default-off spoke verification VMs

**Files:**

- Create: terraform/modules/spoke/testvm.tf
- Modify: terraform/modules/spoke/variables.tf
- Modify: terraform/modules/spoke/outputs.tf
- Modify: terraform/envs/lab/main.tf
- Modify: terraform/envs/lab/variables.tf
- Modify: terraform/envs/lab/outputs.tf
- Modify: terraform/envs/lab/terraform.tfvars.example

**Interfaces:**

- enable_test_vm, bool, default false, at root and spoke module.
- admin_username and ssh_public_key spoke inputs.
- testvm_private_ip spoke output, null when disabled.
- testvm_app_ip and testvm_mgmt_ip root outputs, null when disabled.

Create terraform/modules/spoke/testvm.tf:

~~~hcl
resource "azurerm_network_interface" "testvm" {
  count               = var.enable_test_vm ? 1 : 0
  name                = "nic-testvm-${var.name}"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  ip_configuration {
    name                          = "primary"
    subnet_id                     = values(azurerm_subnet.subnets)[0].id
    private_ip_address_allocation = "Dynamic"
  }
}

resource "azurerm_linux_virtual_machine" "testvm" {
  count                 = var.enable_test_vm ? 1 : 0
  name                  = "vm-test-${var.name}"
  location              = var.location
  resource_group_name   = var.resource_group_name
  size                  = "Standard_B1s"
  admin_username        = var.admin_username
  network_interface_ids = [azurerm_network_interface.testvm[0].id]
  tags                  = var.tags

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 30
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
}
~~~

Add module variables:

~~~hcl
variable "enable_test_vm" {
  description = "Create one temporary verification VM in this spoke."
  type        = bool
  default     = false
}

variable "admin_username" {
  type    = string
  default = "labadmin"
}

variable "ssh_public_key" {
  description = "SSH public key for the private verification VM."
  type        = string
}
~~~

Add the safe disabled output:

~~~hcl
output "testvm_private_ip" {
  description = "Private IP of the verification VM, or null when disabled."
  value       = try(azurerm_network_interface.testvm[0].private_ip_address, null)
}
~~~

Pass enable_test_vm and ssh_public_key to both spoke instances. Add root outputs for both modules. Document the flag in terraform.tfvars.example but leave it commented/false.

~~~powershell
terraform fmt -recursive terraform
git diff --check
git diff -- terraform/modules/spoke terraform/envs/lab
~~~

Invariant: false means zero test NICs/VMs and null outputs.

**Suggested atomic commit:** feat(terraform): add default-off spoke verification VMs

---

## Task 3 — Offline validation and lock files

**Files produced:**

- terraform/bootstrap/.terraform.lock.hcl
- terraform/envs/lab/.terraform.lock.hcl
- terraform/cloudflare/.terraform.lock.hcl only if its root is initialized for Task 4
- Narrowly justified lint/security suppressions only if required

~~~powershell
terraform fmt -check -recursive
terraform -chdir=terraform/bootstrap init -backend=false
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/envs/lab init -backend=false
terraform -chdir=terraform/envs/lab validate
tflint --init
tflint --recursive
checkov -d terraform
git diff --check
~~~

Requirements:

- Downloads occur only after Gate 0 approval.
- Commit lock files; never commit .terraform directories.
- Do not blanket-skip Checkov findings.
- Every suppression identifies rule, exact resource, rationale, compensating control, and owner.
- Review the hub public IP, home-restricted ingress, and deliberate NVA route explicitly.
- Record pre-existing failures separately; stop if they block meaningful validation.
- Terraform validate does not replace a real plan.

~~~powershell
git check-ignore -v terraform/envs/lab/terraform.tfvars
git check-ignore -v terraform/envs/lab/tfplan
git status --short --ignored
git grep -n -I -E "BEGIN (RSA|OPENSSH|PRIVATE) KEY|PrivateKey ="
~~~

Expected: local inputs/plans/state are ignored. No private-key header or real private material appears; inspect every placeholder, key-generation command, and `PrivateKey =` template match.

**Execution evidence — 2026-08-02:**

- All three Terraform roots initialized with signed providers and produced `.terraform.lock.hcl` files.
- `terraform fmt -check -recursive terraform` passed.
- Bootstrap, lab, and Cloudflare roots each passed `terraform validate` with no warnings.
- `tflint --init` and `tflint --recursive` passed with zero issues after adding explicit Terraform/provider requirements to the bootstrap root and all reusable Azure modules. The DNS resolver resource counts and enablement condition were not changed.
- Checkov 3.3.9 reported 38 passed, 0 failed, 15 narrowly documented skips, and 0 parsing errors.
- AzureRM 4.81 requires standalone `azurerm_storage_account_queue_properties`; the bootstrap uses that current resource instead of the deprecated inline block.
- At the offline-validation stage, no Azure login, provider registration, authenticated plan, apply, destroy, test-VM enablement, or other cloud action occurred.

---

## Checkpoint A requirements — used inside Task 4

Present before Azure mutation:

- az account show with subscription name and masked ID;
- bootstrap saved-plan summary;
- current state-storage cost expectation;
- object ID receiving Storage Blob Data Contributor;
- secure local bootstrap-state storage plan;
- confirmation that backend resources persist after lab destroy.

Task 4 first produces the saved bootstrap plan, then stops here. No apply occurs until the user explicitly approves Checkpoint A.

---

## Task 4 — Portable remote state and bootstrap

**Files:**

- Modify: .gitignore
- Modify: terraform/bootstrap/main.tf
- Modify: terraform/bootstrap/variables.tf
- Modify: terraform/envs/lab/providers.tf
- Modify: terraform/cloudflare/main.tf
- Modify: docs/runbook.md only if recovery commands change
- Local only: terraform/envs/lab/backend.auto.tfbackend
- Local only: terraform/bootstrap/terraform.tfvars

### 4.1 Partial backend configuration

Lab backend:

~~~hcl
backend "azurerm" {
  resource_group_name = "rg-cham-tfstate"
  container_name      = "tfstate"
  key                 = "lab.tfstate"
  use_azuread_auth    = true
}
~~~

Cloudflare uses the same stable fields with key = "cloudflare.tfstate". Add *.tfbackend to .gitignore. Do not commit a generated account name.

### 4.2 Harden state storage

Bootstrap must:

- bind provider subscription_id explicitly;
- enable blob versioning;
- use seven-day blob/container delete retention;
- keep TLS 1.2 minimum and public-container access disabled;
- require principal_object_id;
- manage one azurerm_role_assignment on the storage account with role Storage Blob Data Contributor.

Expected managed bootstrap objects: suffix, resource group, storage account, queue-logging configuration, container, and role assignment.

### 4.3 Review and apply the saved bootstrap plan

~~~powershell
az login
az account set --subscription "<approved-subscription>"
$subscriptionId = (az account show --query id -o tsv).Trim()
$principalId = (az ad signed-in-user show --query id -o tsv).Trim()
terraform -chdir=terraform/bootstrap init
terraform fmt -check -recursive
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/envs/lab init -backend=false
terraform -chdir=terraform/envs/lab validate
tflint --recursive
checkov -d terraform
terraform -chdir=terraform/bootstrap plan -var "subscription_id=$subscriptionId" -var "principal_object_id=$principalId" -out bootstrap.tfplan
terraform -chdir=terraform/bootstrap show -no-color bootstrap.tfplan
~~~

**Execution evidence — 2026-08-02:**

- The active Azure subscription is enabled, the signed-in user object ID resolves, and the user has the Owner role at subscription scope. Identifiers are withheld from repository evidence.
- Azure provider auto-registration is disabled explicitly in both Azure roots with `resource_provider_registrations = "none"`; authenticated planning performed no provider registration.
- The gitignored saved bootstrap plan passed with 6 creates, 0 updates, 0 deletes, and 0 warnings. It creates only the random suffix, state resource group, Standard LRS storage account, queue logging settings, private state container, and Storage Blob Data Contributor assignment.
- At the initial Checkpoint A review, `Microsoft.Storage` was `NotRegistered`; registration and the saved-plan apply were blocked for explicit approval.
- At the initial Checkpoint A review, no Terraform apply or other resource-creating operation had occurred and no local bootstrap state existed.

Stop for Checkpoint A. After approval only:

~~~powershell
terraform -chdir=terraform/bootstrap apply bootstrap.tfplan
~~~

**Checkpoint A apply and recovery evidence — 2026-08-02:**

- The user approved registration of `Microsoft.Storage` and application of the exact reviewed bootstrap plan. Azure reported the provider `Registered` before Terraform ran.
- The approved apply partially completed the random suffix, resource group, and Standard LRS storage account, then stopped while polling the storage data plane with `KeyBasedAuthenticationNotPermitted`. The private container, queue logging, and role assignment were not created.
- Root cause: shared keys are disabled by design, while AzureRM defaults storage Blob/Queue operations to shared-key authentication. The bootstrap provider now sets `storage_use_azuread = true`; Entra blob access was proven for the active principal.
- The partial state is gitignored, ACL-restricted to the active Windows account and SYSTEM, and backed up outside the repository with a matching SHA-256 hash. Account, tenant, principal, resource IDs, and storage names are withheld from repository evidence.
- Azure completed the storage account with the intended base controls: Standard LRS, StorageV2, TLS 1.2, HTTPS-only, shared keys disabled, and public blob access disabled. Blob versioning and retention were not reached and remain in the recovery plan.
- Terraform marked the successfully created storage account tainted. After live identity and base configuration matched state, the taint was cleared from the protected local state to prevent an unnecessary destroy/recreate.
- The gitignored recovery plan has SHA-256 `b4228d676de601bb7c419686c9688b7f8a878936047faa02854865097539b06f` and contains 3 creates, 1 in-place update, 0 deletes, and 0 warnings. It adds the private container, queue logging, and RBAC assignment and enables versioning plus seven-day blob/container retention.

**Recovery completion evidence — 2026-08-02:**

- The user explicitly approved `bootstrap-recovery.tfplan`; its SHA-256 was revalidated immediately before apply.
- The recovery apply completed with 3 additions, 1 in-place update, 0 destroys, and 0 warnings.
- Terraform state contains exactly the six expected bootstrap resources, and a fresh authenticated post-apply plan reports no changes and no warnings.
- Azure confirms Standard LRS StorageV2, TLS 1.2, HTTPS-only, shared keys disabled, public blob access disabled, blob versioning enabled, seven-day blob/container soft delete, a private `tfstate` container, and exactly one Storage Blob Data Contributor assignment for the approved principal.
- Queue read/write/delete logging with seven-day retention is present in refreshed Terraform state, and Entra-authenticated access to the backend container succeeds.
- The completed state and automatic local backup are gitignored and ACL-restricted. A matching six-resource recovery copy is stored outside the repository; sensitive identifiers remain excluded from documentation.

The Checkpoint A recovery hard stop is cleared. Task 4.4 may proceed, but no lab-resource apply is authorized by this recovery approval.

### 4.4 Initialize lab with local non-credential config

backend.auto.tfbackend contains only non-credential identifiers:

~~~hcl
storage_account_name = "value-from-bootstrap-output"
subscription_id      = "approved-subscription-id"
tenant_id            = "approved-tenant-id"
~~~

~~~powershell
terraform -chdir=terraform/envs/lab init -backend-config=backend.auto.tfbackend -reconfigure
~~~

Retry the Entra-authenticated container check until the new role assignment propagates or a documented timeout is reached. Do not fall back to keys without a new user decision.

Recovery invariant: bootstrap local state is ignored and treated as sensitive; bootstrap is retained at Phase 2 closeout.

**Suggested atomic commit:** feat(terraform): secure and parameterize Azure remote state

---

## Task 5 — Local inputs and saved base plan

**Local only:**

- terraform/envs/lab/terraform.tfvars
- terraform/envs/lab/backend.auto.tfbackend
- WireGuard keypair outside the repository
- terraform/envs/lab/tfplan

Generate the WireGuard key with the approved CLI:

~~~powershell
$keyDir = Join-Path $env:USERPROFILE ".wg"
New-Item -ItemType Directory -Force -Path $keyDir | Out-Null
$privateKey = (& wg genkey).Trim()
$privateKey | Set-Content -NoNewline (Join-Path $keyDir "cham-laptop.key")
$publicKey = ($privateKey | & wg pubkey).Trim()
$publicKey | Set-Content -NoNewline (Join-Path $keyDir "cham-laptop.pub")
icacls $keyDir /inheritance:r /grant:r "$($env:USERNAME):(OI)(CI)F"
~~~

The icacls command restricts the directory to the current user. The private key never enters tfvars/state.

Populate terraform.tfvars with subscription ID, approved home /32, SSH public key, WireGuard public key, alert email, current-month budget start date, enable_private_resolver = false, and enable_test_vm = false.

~~~powershell
git check-ignore -v terraform/envs/lab/terraform.tfvars
git check-ignore -v terraform/envs/lab/backend.auto.tfbackend
git check-ignore -v terraform/envs/lab/tfplan
terraform -chdir=terraform/envs/lab validate
terraform -chdir=terraform/envs/lab plan -out=tfplan
terraform -chdir=terraform/envs/lab show -no-color tfplan
~~~

Plan invariants:

- no resolver resources;
- no test NIC/VM resources;
- exactly one public IP on the hub;
- hub NSG ends with the all-source terminal deny;
- spokes use hub DNS and NVA routes;
- Private DNS links all three VNets;
- no unexpected replacement/deletion.

---

## Checkpoint B — Base plan, subscription, and cost

Present:

- subscription name and masked ID;
- Terraform and locked provider versions;
- add/change/destroy summary and resource categories;
- resolver/test flags false;
- current cost exposure and any credit assumptions;
- saved-plan hash;
- rollback path.

No base apply without approval of this fresh plan.

---

## Task 6 — Base apply and verification

After Checkpoint B:

~~~powershell
terraform -chdir=terraform/envs/lab apply tfplan
~~~

Create docs/evidence/phase2 after apply. Capture narrow sanitized projections for:

1. All four peerings Connected.
2. Hub cloud-init done and BIND active.
3. db.azure.dwsolution.co returns 10.10.4.20 through 168.63.129.16 and local BIND.
4. Azure NIC forwarding, guest ip_forward, and one expected MASQUERADE rule.
5. Named NSG allows and terminal deny without recording home IP.
6. Budget with 50/90 notifications.
7. Resolver and test resources absent.

~~~powershell
az network vnet peering list --resource-group rg-cham-lab --vnet-name vnet-hub --query "[].{name:name,state:peeringState}" --output table
$hubIp = (terraform -chdir=terraform/envs/lab output -raw hub_public_ip).Trim()
ssh "labadmin@$hubIp" "cloud-init status --wait; systemctl is-active bind9 || systemctl is-active named; sysctl net.ipv4.ip_forward; sudo iptables -t nat -S POSTROUTING"
ssh "labadmin@$hubIp" "dig +short @168.63.129.16 db.azure.dwsolution.co; dig +short @127.0.0.1 db.azure.dwsolution.co"
~~~

If base verification fails, stop. Do not enable test VMs until diagnosed and replanned.

---

## Task 7 — Saved verification-workload plan

Set enable_test_vm = true locally:

~~~powershell
terraform -chdir=terraform/envs/lab plan -out=testvm.tfplan
terraform -chdir=terraform/envs/lab show -no-color testvm.tfplan
~~~

Expected delta: one private NIC and Standard_B1s VM per spoke, no public IP, no unrelated change.

---

## Checkpoint C — Temporary verification workload

Present saved-plan hash/delta, current incremental cost, timebox, no-public-IP confirmation, negative tests, and rollback. No apply without approval.

---

## Task 8 — Verification-VM apply and topology proof

After Checkpoint C:

~~~powershell
terraform -chdir=terraform/envs/lab apply testvm.tfplan
~~~

Capture sanitized evidence:

1. App NIC routes 0.0.0.0/0 and 10.20.0.0/16 through 10.10.0.10.
2. Spoke DNS resolves db.azure.dwsolution.co to 10.10.4.20 through hub.
3. Spoke egress equals the hub public IP; committed evidence records only MATCH=true, not either public IP.
4. Both VM records auto-register; db remains a non-auto seed.
5. App-to-management traffic fails.
6. Hub-to-management traffic succeeds.
7. The effective NSG restricts SSH/WireGuard sources to the approved /32, WireGuard remains disabled in Phase 2, and off-home SSH fails.
8. Home SSH succeeds.

~~~powershell
az network nic show-effective-route-table --resource-group rg-cham-lab --name nic-testvm-app --query "value[].{prefix:addressPrefix,nextHop:nextHopType,nextHopIp:nextHopIpAddress}" --output table
$appIp = (terraform -chdir=terraform/envs/lab output -raw testvm_app_ip).Trim()
$mgmtIp = (terraform -chdir=terraform/envs/lab output -raw testvm_mgmt_ip).Trim()
ssh -J "labadmin@$hubIp" "labadmin@$appIp" "resolvectl query db.azure.dwsolution.co; curl -4 -s --max-time 10 ifconfig.me"
ssh -J "labadmin@$hubIp" "labadmin@$appIp" "ping -c 3 -W 2 $mgmtIp"
ssh "labadmin@$hubIp" "ping -c 3 -W 2 $mgmtIp"
~~~

Compare the egress result to $hubIp in memory and write only MATCH=true/false to evidence. Auto-registration evidence projects only record name, flag, and private IP. A failed negative test is a security failure and requires replanning.

---

## Task 9 — Saved destroy plan

~~~powershell
terraform -chdir=terraform/envs/lab plan -destroy -out=destroy.tfplan
terraform -chdir=terraform/envs/lab show -no-color destroy.tfplan
~~~

Verify all lab resources are selected, backend resources are not in lab state, and no unrelated subscription resource is selected.

---

## Checkpoint D — Destructive approval

Present destroy summary/hash, retained backend/cost, and recovery path. No destroy without approval.

---

## Task 10 — Destroy, recreation proof, and closeout

After Checkpoint D:

~~~powershell
terraform -chdir=terraform/envs/lab apply destroy.tfplan
az group exists --name rg-cham-lab
az group exists --name rg-cham-tfstate
~~~

Expected: lab false, backend true, and no Phase 2 compute/network/DNS/budget resource remains. Persistent state storage may still cost money.

Reset enable_test_vm = false. Generate but do not apply:

~~~powershell
terraform -chdir=terraform/envs/lab plan -out=recreate.tfplan
terraform -chdir=terraform/envs/lab show -no-color recreate.tfplan
~~~

The recreate plan describes the base stack with resolver/test flags false.

Before evidence staging:

~~~powershell
git diff --check
git status --short
git grep -n -I -E "BEGIN (RSA|OPENSSH|PRIVATE) KEY|PrivateKey ="
~~~

Review evidence for account IDs, IPs, email, keys, backend names, and raw state/plan content. Update README only when all exit criteria pass. Update architecture/runbook if live behavior differs.

**Suggested closeout commit:** docs: record verified Phase 2 Azure core evidence

---

## Verification matrix

| Requirement | Planned proof | Live status |
|---|---|---|
| Tool/provider correctness | Gate 0 and Task 3 | Passed locally 2026-08-02: fmt/validate, TFLint, and Checkov |
| Portable secure state | Task 4 / Checkpoint A | Bootstrap complete; post-apply plan is clean, state is protected, backend initialization pending |
| Peerings | Task 6 | Deferred |
| DNS through hub | Tasks 6 and 8 | Deferred |
| Private DNS auto-registration | Task 8 | Deferred |
| UDR/NVA forwarding | Tasks 6 and 8 | Deferred |
| Hub SNAT | Task 8 | Deferred |
| Spoke isolation | Task 8 paired tests | Deferred |
| Home-only ingress | Task 8 paired tests | Deferred |
| Resolver disabled | Tasks 3, 5, and 6 | Deferred |
| Cost review | Checkpoints A–C | Deferred |
| Clean destroy | Tasks 9–10 / Checkpoint D | Deferred |
| Recreate readiness | Task 10 no-apply plan | Deferred |
| Evidence secrecy | Tasks 3, 6, 8, and 10 | Deferred |

## Exit criteria

Phase 2 is complete only when:

1. fmt, validate, TFLint, and Checkov pass or have narrow justified findings; lock files are recorded.
2. Bootstrap succeeds and backend uses Entra/RBAC without committed credentials.
3. A reviewed base plan applies to the approved subscription with resolver/test flags false.
4. All four peerings are Connected.
5. Hub and spoke DNS proofs pass.
6. Effective routes use 10.10.0.10 for default and on-prem prefixes.
7. Azure/guest forwarding and SNAT are proven.
8. Both VM records auto-register without changing the db seed.
9. Isolation and public-ingress positive/negative tests pass.
10. Budget notifications exist with the no-spend-cap caveat.
11. Reviewed destroy removes all lab resources and retains only backend resources.
12. A no-apply recreation plan is valid with resolver/test flags false.
13. Evidence is sanitized and no secret/local artifact is staged.
14. README is checked only after items 1–13.

## User review checklist

- [x] Approved PowerShell 7.
- [x] Approved Entra/RBAC partial backend configuration.
- [x] Confirmed EOL normalization and the Python stub stay out of Phase 2.
- [x] Approved scope, ordering, and exit criteria.
- [x] Confirmed later bootstrap/apply/test/destroy checkpoints require fresh approval.
- [x] No changes requested; authorized gsd-execute-phase on 2026-08-02.

> GATE 0 RECORD: Plan approval was received on 2026-08-02. Local repository implementation may proceed. Tool installation/readiness and Checkpoints A-D remain unresolved until their stated evidence and approvals are complete.
