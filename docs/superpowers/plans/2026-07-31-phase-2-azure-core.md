# Phase 2 — Azure Core (hub, spokes, peering, NSG, UDR) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Take the already-authored Terraform stack from "code that has never been applied" to a deployed, verified, destroy-and-reapply-proven Azure hub-and-spoke topology with Private DNS.

**Architecture:** One resource group (`rg-cham-lab`); hub VNet (10.10.0.0/22) holding a B1s NVA VM (future WireGuard + BIND9); two spokes (10.10.4.0/22 app, 10.10.8.0/22 mgmt) instantiated from one module with bidirectional peering, NSG isolation, and 0.0.0.0/0 UDRs through the NVA; Private DNS zone `azure.dwsolution.co` linked to all three VNets (auto-registration on spokes only); subscription budget alert. Remote state in an Azure Storage blob created by the bootstrap stack.

**Tech Stack:** Terraform ≥ 1.9, azurerm ~> 4.0, Azure CLI, WSL2/bash. No CI in this phase (that's Phase 5) — everything runs locally with `az login`.

## Global Constraints

- Terraform `required_version = ">= 1.9"`, provider `azurerm ~> 4.0` (already pinned — do not change).
- Free-tier posture: only `Standard_B1s` VMs, `Standard_LRS` disks, no Private Resolver (`enable_private_resolver = false` at all times in this phase).
- `home_ip` is always a single `/32`. Never widen it. It lives only in gitignored `terraform.tfvars` or `TF_VAR_home_ip`.
- Secrets (tfvars, private keys) never enter git. `.gitignore` already covers `terraform.tfvars`, `*.key`, `wg0.conf` — keep it that way.
- Region: `eastus` everywhere (variable default — don't override).
- Evidence convention: verification command output is captured with `tee` into `docs/evidence/phase2/*.txt` and committed. This pattern repeats in every later phase.
- All shell commands below run from the repo root `/mnt/d/code-projects/cham` unless a `cd` is shown.

## Task Dependency / Parallelism Map

```
Task 0 (hygiene)
  └─→ Task 1 (terraform fixes)  ─┐   } Task 1 and Task 2 are parallelizable
  └─→ Task 2 (test VM module)   ─┤   } (different files); Task 3 is also
  └─→ Task 3 (bootstrap state)  ─┘   } independent of 1 and 2
        └─→ Task 4 (tfvars + plan)     [needs 1, 2, 3 all committed]
              └─→ Task 5 (apply + verify)
                    └─→ Task 6 (destroy discipline + docs)
```

---

### Task 0: Repo hygiene — line endings and the broken `azure.py` tail

The whole tree currently shows as modified (877 insertions / 877 deletions) because files on disk are CRLF while the index is LF. Also `ddi-reconciler/providers/azure.py` ends with a dangling `from` (a syntax error) that must not be committed.

**Files:**
- Create: `.gitattributes`
- Modify: `ddi-reconciler/providers/azure.py` (delete line 13)

**Interfaces:**
- Produces: a clean `git status` baseline every later task's commits depend on.

- [ ] **Step 1: Write `.gitattributes`**

```gitattributes
* text=auto eol=lf
*.png binary
*.jpg binary
*.ico binary
```

- [ ] **Step 2: Remove the dangling `from` at the end of `ddi-reconciler/providers/azure.py`**

The file must end after the module docstring (the line containing only `from` is deleted). Verify it parses:

Run: `python3 -c "import ast; ast.parse(open('ddi-reconciler/providers/azure.py').read())"`
Expected: no output, exit 0.

- [ ] **Step 3: Renormalize and inspect**

Run:
```bash
git add .gitattributes
git add --renormalize .
git status
```
Expected: `git status` now shows only real content changes (the `.gitattributes`, `azure.py`, and any files whose bytes genuinely differ from HEAD) — the wall of phantom whole-file modifications is gone from the diff (`git diff --cached --stat` shows small numbers, not ±877).

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: normalize line endings to LF, drop dangling import in azure provider"
```

- [ ] **Step 5 (optional): Rewrite working tree to LF**

Only with a clean tree, to make on-disk files match the LF policy:
```bash
git ls-files -z | xargs -0 rm && git checkout -- .
```

---

### Task 1: Terraform correctness fixes found in review (apply-blocking bugs)

Four latent bugs will bite in Phase 3/4 if not fixed before the first apply; fixing them now avoids a VM rebuild later (cloud-init only runs at first boot).

**Files:**
- Modify: `terraform/modules/hub/cloud-init.yml.tpl`
- Modify: `terraform/modules/hub/main.tf:143-148` (templatefile vars)
- Modify: `terraform/modules/hub/variables.tf` (new variable)
- Modify: `terraform/modules/spoke/main.tf` (new NSG rule; comment fix)
- Modify: `terraform/modules/spoke/variables.tf` (new variable)
- Modify: `terraform/modules/private-dns/main.tf:20-21` (comment contradicts ADR-005)

**Interfaces:**
- Produces: `wg_transfer_cidr` variable (default `"172.16.0.0/24"`) on both hub and spoke modules; hub BIND9 that will accept laptop queries in Phase 3; spoke NSGs that will accept tunnel-sourced traffic in Phase 3; hub NAT so spoke VMs get internet egress through the NVA.

Background for each fix:
1. **BIND9 `allow-query` omits the WireGuard transfer net.** The laptop queries hub BIND9 as `172.16.0.2` → would get REFUSED.
2. **`allow-recursion` is unset.** BIND's default (`localnets; localhost;`) does not include the spoke subnets (hub's own subnets only), so spoke VMs would get recursion refused even though `allow-query` passes.
3. **No SNAT on the NVA.** Spokes default-route through the hub; forwarded packets leave the hub NIC with the spoke's source IP, which Azure will not SNAT to the hub's public IP — spoke internet egress silently fails. Add MASQUERADE for internet-bound traffic only (excluding 10.0.0.0/8 so spoke-to-spoke traffic keeps its source and stays deniable by NSG).
4. **Misleading comments.** `spoke/main.tf` says "allow via hub only" but the rule set (correctly, per ADR-003's isolation story) denies spoke↔spoke even via the hub — the comment must match reality. `private-dns/main.tf` says "reconciler owns ongoing convergence" of seed records, contradicting ADR-005 (Terraform owns seeds; the reconciler's managed set is disjoint).

- [ ] **Step 1: Replace the BIND9 options and add NAT in `terraform/modules/hub/cloud-init.yml.tpl`**

Full new file content:

```yaml
#cloud-config
# Hub DDI VM: WireGuard endpoint + BIND9 conditional forwarder + NVA SNAT.
# NVA requirement #2 of 2: ip_forward in the guest (NIC flag is in Terraform).
package_update: true
packages:
  - wireguard
  - bind9
  - bind9-utils
  - iptables-persistent

write_files:
  - path: /etc/sysctl.d/99-forwarding.conf
    content: |
      net.ipv4.ip_forward=1

  - path: /etc/wireguard/wg0.conf
    permissions: "0600"
    content: |
      [Interface]
      # Generate on first boot: wg genkey — do NOT commit real keys
      PrivateKey = REPLACE_ON_HOST
      Address = 172.16.0.1/24
      ListenPort = 51820

      [Peer]
      # Laptop
      PublicKey = ${wg_peer_public_key}
      AllowedIPs = 172.16.0.2/32, ${onprem_cidr}

  - path: /etc/bind/named.conf.options
    content: |
      options {
        directory "/var/cache/bind";
        recursion yes;
        allow-query { 10.10.0.0/16; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
        allow-recursion { 10.10.0.0/16; ${onprem_cidr}; ${wg_transfer_cidr}; localhost; };
        // Default path: Azure-provided DNS (Private DNS zones resolve here)
        forwarders { 168.63.129.16; };
        forward only;
        dnssec-validation no;  // 168.63.129.16 doesn't serve DNSSEC for private zones
      };

  - path: /etc/bind/named.conf.local
    content: |
      // On-prem lab zone -> laptop BIND9 across the tunnel
      zone "${lab_zone}" {
        type forward;
        forward only;
        forwarders { ${onprem_dns_ip}; };
      };

runcmd:
  - sysctl --system
  # NVA SNAT: internet-bound traffic from the Azure supernet only. Spoke-to-spoke
  # traffic (dest inside 10/8) keeps its original source so spoke NSGs can deny it.
  - iptables -t nat -A POSTROUTING -o eth0 -s 10.10.0.0/16 ! -d 10.0.0.0/8 -j MASQUERADE
  - netfilter-persistent save
  - systemctl enable --now bind9 || systemctl enable --now named
  # WireGuard left disabled until a real private key is installed:
  - echo "Run 'wg genkey' on this host, patch wg0.conf, then: systemctl enable --now wg-quick@wg0"
```

- [ ] **Step 2: Pass `wg_transfer_cidr` into the template**

In `terraform/modules/hub/main.tf`, extend the `templatefile` call:

```hcl
  custom_data = base64encode(templatefile("${path.module}/cloud-init.yml.tpl", {
    onprem_cidr        = var.onprem_address_space
    lab_zone           = var.lab_zone
    onprem_dns_ip      = var.onprem_dns_ip # laptop BIND9 via tunnel
    wg_peer_public_key = var.wg_peer_public_key
    wg_transfer_cidr   = var.wg_transfer_cidr
  }))
```

Append to `terraform/modules/hub/variables.tf`:

```hcl
variable "wg_transfer_cidr" {
  description = "WireGuard transfer network — laptop tunnel source addresses"
  type        = string
  default     = "172.16.0.0/24"
}
```

- [ ] **Step 3: Spoke NSG — allow the WireGuard transfer net**

In `terraform/modules/spoke/main.tf`, insert after the `AllowOnPrem` rule (priority 110):

```hcl
  security_rule {
    name                       = "AllowWireGuardTransfer"
    priority                   = 111
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "*"
    source_port_range          = "*"
    destination_port_range     = "*"
    source_address_prefix      = var.wg_transfer_cidr
    destination_address_prefix = "*"
  }
```

Append to `terraform/modules/spoke/variables.tf`:

```hcl
variable "wg_transfer_cidr" {
  description = "WireGuard transfer network — tunnel-sourced traffic arrives with these source IPs"
  type        = string
  default     = "172.16.0.0/24"
}
```

- [ ] **Step 4: Fix the two lying comments**

In `terraform/modules/spoke/main.tf` replace the NSG header comment (line 21) with:

```hcl
# --- NSG: spoke isolation. Spoke-to-spoke is denied outright (even via the
# hub NVA — forwarded packets keep their spoke source IP and hit DenyOtherSpokes).
# Only hub, on-prem, tunnel, and intra-spoke sources are allowed in. ---
```

In `terraform/modules/private-dns/main.tf` replace the comment above `azurerm_private_dns_a_record.static` with:

```hcl
# Terraform-owned SEED records only (ADR-005). The reconciler manages a
# DISJOINT record set declared in its managed-key allowlist and never
# touches these.
```

- [ ] **Step 5: Validate**

Run:
```bash
terraform -chdir=terraform/envs/lab init -backend=false
terraform -chdir=terraform/envs/lab validate
terraform fmt -check -recursive terraform/
```
Expected: `Success! The configuration is valid.` and fmt exits 0 (run `terraform fmt -recursive terraform/` first if it rewrites anything).

- [ ] **Step 6: Commit**

```bash
git add terraform/modules
git commit -m "fix(terraform): BIND9 acl + recursion for tunnel/spokes, NVA SNAT, spoke NSG wg rule, truthful comments"
```

---

### Task 2: Flag-gated test VM in the spoke module

*Parallelizable with Task 1 (different files) and Task 3.*

Without a workload NIC in a spoke there is no way to verify UDRs (effective routes need a NIC), DNS-from-spoke, auto-registration, or NSG isolation. Add a `count`-gated B1s test VM to the spoke module, off by default (same pattern as the resolver module). Cost when enabled: ~$0.01/hr each beyond the one free B1s allowance — session-scoped pennies.

**Files:**
- Create: `terraform/modules/spoke/testvm.tf`
- Modify: `terraform/modules/spoke/variables.tf`
- Modify: `terraform/modules/spoke/outputs.tf`
- Modify: `terraform/envs/lab/main.tf` (wire into both spokes)
- Modify: `terraform/envs/lab/variables.tf`
- Modify: `terraform/envs/lab/terraform.tfvars.example`

**Interfaces:**
- Consumes: existing `azurerm_subnet.subnets` map in the spoke module.
- Produces: `var.enable_test_vm` (bool, default false), `var.ssh_public_key` (string) on the spoke module; `testvm_private_ip` output; root-level `enable_test_vm` variable. Phase 3 and Phase 4 verification steps depend on these names exactly.

- [ ] **Step 1: Create `terraform/modules/spoke/testvm.tf`**

```hcl
# Flag-gated test VM — session-scoped verification workload only (effective
# routes, DNS-from-spoke, auto-registration, NSG isolation). No public IP.
# Reach it via the hub as an SSH jump host.

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
```

- [ ] **Step 2: Add variables and output to the spoke module**

Append to `terraform/modules/spoke/variables.tf`:

```hcl
variable "enable_test_vm" {
  description = "Session-scoped verification VM (~$0.01/hr). Off by default."
  type        = bool
  default     = false
}

variable "admin_username" {
  type    = string
  default = "labadmin"
}

variable "ssh_public_key" {
  description = "SSH key for the test VM (same key as the hub)"
  type        = string
}
```

Append to `terraform/modules/spoke/outputs.tf`:

```hcl
output "testvm_private_ip" {
  description = "Private IP of the test VM, null when disabled"
  value       = try(azurerm_network_interface.testvm[0].private_ip_address, null)
}
```

- [ ] **Step 3: Wire into the root module**

In `terraform/envs/lab/main.tf`, add to BOTH `module "spoke_app"` and `module "spoke_mgmt"` blocks:

```hcl
  enable_test_vm = var.enable_test_vm
  ssh_public_key = var.ssh_public_key
```

Append to `terraform/envs/lab/variables.tf`:

```hcl
variable "enable_test_vm" {
  description = "Deploy one B1s test VM per spoke for verification sessions"
  type        = bool
  default     = false
}
```

Append to `terraform/envs/lab/outputs.tf`:

```hcl
output "testvm_app_ip" {
  description = "Spoke A test VM private IP (null when disabled)"
  value       = module.spoke_app.testvm_private_ip
}

output "testvm_mgmt_ip" {
  description = "Spoke B test VM private IP (null when disabled)"
  value       = module.spoke_mgmt.testvm_private_ip
}
```

Append to `terraform/envs/lab/terraform.tfvars.example`:

```hcl
# enable_test_vm = true   # session-only verification VMs, one per spoke (~$0.01/hr each)
```

- [ ] **Step 4: Validate and commit**

Run:
```bash
terraform -chdir=terraform/envs/lab init -backend=false && terraform -chdir=terraform/envs/lab validate && terraform fmt -check -recursive terraform/
```
Expected: valid, fmt clean.

```bash
git add terraform/
git commit -m "feat(terraform): flag-gated per-spoke test VM for topology verification"
```

---

### Task 3: Bootstrap remote state and pin the backend

*Parallelizable with Tasks 1–2. Requires: an Azure subscription and `az` CLI.*

**Files:**
- Modify: `terraform/envs/lab/providers.tf:14` (storage account name)
- Modify: `terraform/cloudflare/main.tf:15` (same storage account name)

**Interfaces:**
- Produces: a real storage account name replacing both `REPLACE_FROM_BOOTSTRAP_OUTPUT` placeholders; blob container `tfstate`. Phase 4 (cloudflare state) and Phase 5 (CI init) depend on this.

- [ ] **Step 1: Log in and select the subscription**

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
az account show -o table
```
Expected: the intended subscription is listed as the default.

- [ ] **Step 2: Apply the bootstrap stack (local state — apply once, keep the tfstate)**

```bash
terraform -chdir=terraform/bootstrap init
terraform -chdir=terraform/bootstrap apply
terraform -chdir=terraform/bootstrap output backend_config
```
Expected: 3 resources created; output prints the generated `storage_account_name` (pattern `stchamtfXXXXXX`).

Note: `terraform/bootstrap/terraform.tfstate` is gitignored. It contains only these three resources; keep the file (or note the SA name — the stack is trivially re-importable with `terraform import`).

- [ ] **Step 3: Pin the backend in both stacks**

Replace `REPLACE_FROM_BOOTSTRAP_OUTPUT` with the real name in:
- `terraform/envs/lab/providers.tf` (`storage_account_name`)
- `terraform/cloudflare/main.tf` (`storage_account_name`)

- [ ] **Step 4: Verify the container exists**

Run: `az storage container list --account-name <stchamtfXXXXXX> --auth-mode login -o table`
Expected: one container `tfstate`. (If auth fails, add yourself `Storage Blob Data Contributor` on the SA or rerun with `--auth-mode key`.)

- [ ] **Step 5: Commit**

```bash
git add terraform/envs/lab/providers.tf terraform/cloudflare/main.tf
git commit -m "chore(terraform): pin remote-state backend to bootstrap storage account"
```

---

### Task 4: tfvars, WireGuard keypair, first plan

*Depends on Tasks 1, 2, 3.*

**Files:**
- Create: `terraform/envs/lab/terraform.tfvars` (gitignored — verify with `git check-ignore`)
- Create (outside repo): `~/.wg/cham-laptop.key`, `~/.wg/cham-laptop.pub`

**Interfaces:**
- Produces: the laptop WireGuard keypair (private key stays in `~/.wg/`, public key goes into tfvars as `wg_peer_public_key`). Phase 3 Task 2 consumes `~/.wg/cham-laptop.key` — the path must match.

- [ ] **Step 1: Generate the laptop WireGuard keypair now (it's a required tfvar)**

```bash
sudo apt-get install -y wireguard-tools
mkdir -p ~/.wg && chmod 700 ~/.wg
wg genkey | tee ~/.wg/cham-laptop.key | wg pubkey > ~/.wg/cham-laptop.pub
chmod 600 ~/.wg/cham-laptop.key
cat ~/.wg/cham-laptop.pub
```

- [ ] **Step 2: Fill tfvars**

```bash
cd terraform/envs/lab
cp terraform.tfvars.example terraform.tfvars
curl -4 -s ifconfig.me   # → home_ip value, append /32
```

Fill every field: `subscription_id`, `home_ip` (`<curl result>/32`), `ssh_public_key` (`cat ~/.ssh/id_ed25519.pub`; run `ssh-keygen -t ed25519` first if absent), `wg_peer_public_key` (`cat ~/.wg/cham-laptop.pub`), `alert_email`, `budget_start_date` (first day, 00:00:00Z, of the month you are applying in — e.g. applying during July 2026 → `2026-07-01T00:00:00Z`). Leave `enable_private_resolver` and `enable_test_vm` unset (false).

Run: `git check-ignore -v terraform.tfvars`
Expected: matched by the `terraform.tfvars` rule — it will never be committed.

- [ ] **Step 3: Init against the real backend and plan**

```bash
terraform init
terraform plan -out=tfplan
```
Expected: `Plan: 31 to add, 0 to change, 0 to destroy.` Breakdown: 1 RG + 8 hub (vnet, 2 subnets, pip, nsg, nsg-assoc, nic, vm) + 2×8 spoke (vnet, subnet, nsg, nsg-assoc, route table, rt-assoc, 2 peerings) + 5 private-dns (zone, 3 links, seed A record) + 1 budget. Resolver and test VMs contribute 0 (flags off). Read the plan — no resource should carry a public IP except `pip-hub-ddi`, and the NSG rules should match Task 1.

---

### Task 5: Apply and verify the topology

*Depends on Task 4. This is the phase's proof-of-work; capture evidence as you go.*

**Files:**
- Create: `docs/evidence/phase2/` (verification outputs)

- [ ] **Step 1: Apply**

```bash
mkdir -p ../../../docs/evidence/phase2
terraform apply tfplan
terraform output
```
Expected: apply completes in ~5 min; outputs show `hub_public_ip` (real IP) and `hub_private_ip = 10.10.0.10`.

- [ ] **Step 2: Peering is Connected in all four directions**

```bash
az network vnet peering list -g rg-cham-lab --vnet-name vnet-hub -o table | tee ../../../docs/evidence/phase2/peering.txt
az network vnet peering list -g rg-cham-lab --vnet-name vnet-app -o table | tee -a ../../../docs/evidence/phase2/peering.txt
az network vnet peering list -g rg-cham-lab --vnet-name vnet-mgmt -o table | tee -a ../../../docs/evidence/phase2/peering.txt
```
Expected: `peer-hub-to-app`, `peer-hub-to-mgmt` from the hub; one peering from each spoke; every `PeeringState` = `Connected`.

- [ ] **Step 3: Hub VM is up, cloud-init succeeded, BIND9 answers**

```bash
HUB_IP=$(terraform output -raw hub_public_ip)
ssh labadmin@"$HUB_IP" 'cloud-init status --wait; systemctl is-active named; sudo iptables -t nat -S POSTROUTING'
```
Expected: `status: done`, `active`, and the MASQUERADE rule from Task 1 present.

```bash
ssh labadmin@"$HUB_IP" 'dig +short @168.63.129.16 db.azure.dwsolution.co; dig +short @127.0.0.1 db.azure.dwsolution.co' | tee ../../../docs/evidence/phase2/dns-hub.txt
```
Expected: `10.10.4.20` twice — once straight from Azure DNS (zone link works), once through BIND9's forwarder (the Phase 3 resolution path, minus the tunnel).

- [ ] **Step 4: Enable the test VMs and re-apply**

Set `enable_test_vm = true` in `terraform.tfvars`, then:
```bash
terraform apply
terraform output testvm_app_ip testvm_mgmt_ip
```
Expected: 4 resources added (NIC + VM per spoke); both outputs show 10.10.4.x / 10.10.8.x addresses.

- [ ] **Step 5: UDRs — effective routes prove the NVA path**

```bash
az network nic show-effective-route-table -g rg-cham-lab -n nic-testvm-app -o table | tee ../../../docs/evidence/phase2/routes-app.txt
```
Expected rows: `0.0.0.0/0 → VirtualAppliance 10.10.0.10` and `10.20.0.0/16 → VirtualAppliance 10.10.0.10` (Default route superseded by User routes).

- [ ] **Step 6: DNS + egress-via-NVA from a spoke**

```bash
APP_IP=$(terraform output -raw testvm_app_ip)
ssh -J labadmin@"$HUB_IP" labadmin@"$APP_IP" 'resolvectl query db.azure.dwsolution.co; curl -4 -s --max-time 10 ifconfig.me; echo'
```
Expected: `db.azure.dwsolution.co: 10.10.4.20` (resolved via VNet DNS = hub BIND9 — proves spoke→hub port-53 NSG rule and `allow-recursion` fix), and `ifconfig.me` returns **the hub's public IP** (proves 0/0 UDR + NVA SNAT). Save to `docs/evidence/phase2/spoke-egress.txt`.

- [ ] **Step 7: Auto-registration appeared; seed record intact**

```bash
az network private-dns record-set a list -g rg-cham-lab -z azure.dwsolution.co --query '[].{name:name, auto:isAutoRegistered, ips:aRecords[].ipv4Address}' -o table | tee ../../../docs/evidence/phase2/autoreg.txt
```
Expected: `db` (auto=False, 10.10.4.20), `vm-test-app` and `vm-test-mgmt` (auto=True). This exact state is what the Phase 4 reconciler must prove it never touches.

- [ ] **Step 8: Spoke isolation (negative test)**

```bash
MGMT_IP=$(terraform output -raw testvm_mgmt_ip)
ssh -J labadmin@"$HUB_IP" labadmin@"$APP_IP" "ping -c 3 -W 2 $MGMT_IP; echo exit=\$?"
```
Expected: 100% packet loss, nonzero exit — app→mgmt is denied by `DenyOtherSpokes` even through the hub. From the hub itself, `ping -c 3 $MGMT_IP` succeeds (AllowFromHub). Save both to `docs/evidence/phase2/isolation.txt`.

- [ ] **Step 9: NSG negative test from an off-home network**

From a phone hotspot (or any non-home egress): `nc -vz -w 5 <HUB_IP> 22`
Expected: timeout — SSH is home-IP-only. (Manual step; note the result in the evidence file.)

- [ ] **Step 10: Budget alert exists**

```bash
az consumption budget list --query '[].{name:name, amount:amount, grain:timeGrain}' -o table | tee ../../../docs/evidence/phase2/budget.txt
```
Expected: `budget-cham-lab`, amount 50, Monthly.

- [ ] **Step 11: Commit evidence**

```bash
git add docs/evidence/phase2/
git commit -m "docs: phase 2 verification evidence (peering, routes, dns, isolation, budget)"
```

---

### Task 6: Destroy discipline and phase closeout

*Depends on Task 5.*

**Files:**
- Modify: `README.md:44` (check the Phase 2 box)

- [ ] **Step 1: Destroy everything**

```bash
terraform destroy
az group exists --name rg-cham-lab
```
Expected: destroy removes all 35 resources including the RG; `az group exists` prints `false`. (The tfstate storage RG `rg-cham-tfstate` remains — that's bootstrap, not lab.)

- [ ] **Step 2: Prove idempotent re-creation**

```bash
terraform plan
```
Expected: the same `Plan: 35 to add` (31 + 4 test VMs with the flag still true) with zero errors — the stack rebuilds from nothing with no manual steps. Apply again only if continuing into a work session; otherwise leave it down. Note for Phase 3: `hub_public_ip` changes on every rebuild — the laptop WireGuard config takes the endpoint from `terraform output`, not from a hardcoded value.

- [ ] **Step 3: Check the box and commit**

In `README.md` set `- [x] Phase 2 — Azure core (hub, spokes, peering, NSG, UDR)`.

```bash
git add README.md
git commit -m "docs: phase 2 complete — Azure core deployed and verified"
```

---

## Exit Criteria (all must hold)

1. `terraform apply` from a clean subscription state succeeds unattended using only `terraform.tfvars` — no manual portal steps, no placeholder values left in committed files.
2. All four peerings `Connected`; effective routes on a spoke NIC show 0/0 and 10.20.0.0/16 via `10.10.0.10`.
3. From a spoke test VM: `db.azure.dwsolution.co` resolves to `10.10.4.20` via the hub, and internet egress returns the hub's public IP (NVA SNAT proven).
4. Auto-registered records for both test VMs visible in the private zone alongside the untouched `db` seed.
5. Spoke→spoke traffic denied; hub→spoke allowed; SSH/WireGuard ports unreachable from non-home IPs.
6. Budget `budget-cham-lab` exists with 50/90 thresholds.
7. `terraform destroy` leaves `az group exists rg-cham-lab` = false, and a fresh `terraform plan` offers the full stack again.
8. Evidence files committed under `docs/evidence/phase2/`; README Phase 2 box checked; working tree clean with LF normalization in place.

## What Completion Looks Like

One command brings the whole Azure estate up in ~6 minutes; a checklist of nine verifications (each a single captured command) proves hub-and-spoke routing, DNS, isolation, and cost guardrails; one command tears it all down to zero spend. The repo tells the story: the fixes commit shows the review caught real bugs (BIND ACLs, missing SNAT), the evidence directory shows the topology actually ran, and nothing secret ever entered git. Phase 3 can start at "SSH to the hub and install a WireGuard key" with every prerequisite (keypair, ACLs, NSG rules, NAT) already in place.
