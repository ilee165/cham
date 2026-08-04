# Phase 2 Azure Core — Planning Research

**Date:** 2026-08-01
**Branch:** `codex/phase-2-planning` (created from `main` at `5c1b526`)
**Scope:** Plan-quality research only. No Terraform apply, Azure login, provider registration, resource creation, or resource destruction was performed.

## Executive finding

The existing Phase 2 plan has the right architectural center—hub/spoke networking, a small burstable NVA/DNS VM, Private DNS, flag-gated verification VMs, remote state, and live apply/destroy proof—but it is not ready to execute unchanged.

The revised plan must:

1. replace the stale repository-hygiene task;
2. use GSD as the lifecycle owner and stop for human approval before implementation;
3. add an explicit toolchain gate because the required local tools are absent;
4. separate offline validation, state bootstrap, base apply, verification-workload apply, and destroy into distinct approval/cost gates;
5. fix the hub NSG terminal-deny gap and enforce `/32` input validation;
6. use portable backend configuration and commit provider lock files;
7. distinguish plan verification from live infrastructure verification.

## Evidence examined

### Repository evidence

- `docs/superpowers/plans/2026-07-31-phase-2-azure-core.md`
- `docs/superpowers/plans/2026-07-31-phases-2-5-overview.md`
- `docs/superpowers/plans/2026-07-31-phase-3-wireguard-hybrid-dns.md`
- `docs/architecture.md`, `docs/decisions.md`, `docs/runbook.md`, `README.md`
- `terraform/bootstrap/`
- `terraform/envs/lab/`
- `terraform/modules/hub/`, `spoke/`, `private-dns/`, and `dns-resolver/`
- `.gitignore`, `AGENTS.md`, and `SKILLS.md`

The repository graph was attempted first as required, but `graphify-out/graph.json` is absent. Scoped source inspection was therefore used.

### Current first-party references

- [AzureRM provider documentation](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [AzureRM 4.0 upgrade guide](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/4.0-upgrade-guide)
- [Terraform backend and partial-configuration guidance](https://developer.hashicorp.com/terraform/language/backend)
- [Azure Private DNS zone overview](https://learn.microsoft.com/en-us/azure/dns/private-dns-privatednszone)
- [Azure virtual-network routing and NVA requirements](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-udr-overview)
- [Azure default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access)
- [Azure public IP guidance](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/virtual-network-public-ip-address)
- [Azure budget API requirements](https://learn.microsoft.com/en-us/rest/api/consumption/budgets/get)

## Baseline facts

- The planning branch is clean and points at the same commit as local and remote-tracking `main` at branch creation.
- There is no `.planning/` GSD project directory. The checked-in Phase 2 plan under `docs/superpowers/plans/` is therefore the plan to revise in place; creating a second parallel plan would be ambiguous.
- The existing plan is detailed and already contains Tasks 0–6, dependency ordering, expected evidence, and exit criteria.
- `terraform`, `tflint`, `checkov`, `az`, and WSL were not available in the current execution environment. `uv 0.11.13` and Python 3.14 were available.
- Terraform formatting, initialization, validation, TFLint, Checkov, and plan generation could not be run during this planning pass.
- The worktree is not suffering the whole-tree dirty-state claimed by existing Task 0. It is clean, while the index intentionally contains a mixture of LF and CRLF files.
- There is no `.gitattributes` file. Running `git add --renormalize .` after adding an LF policy would intentionally create a large repository-wide normalization diff.
- `ddi-reconciler/providers/azure.py` still ends with a bare `from` and fails `py_compile`, but that file is outside the Terraform Phase 2 delivery surface.
- The lab and Cloudflare backends contain `REPLACE_FROM_BOOTSTRAP_OUTPUT`; the existing plan resolves this by committing one generated storage-account name into both roots.
- No `.terraform.lock.hcl` files are checked in.
- The spoke module has no flag-gated test VM yet, so effective-route, DNS-from-spoke, auto-registration, and isolation checks are not currently executable.
- The resolver module is cost-gated and disabled by default. It must remain disabled throughout Phase 2.

## Findings

### BLOCKER 1 — Process and approval routing is wrong

The existing plan header requires `superpowers:subagent-driven-development` or `superpowers:executing-plans`. `SKILLS.md` now assigns phase-sized work to GSD and forbids competing top-level orchestrators.

**Correction:** The revised plan must state that eventual execution is owned by `gsd-execute-phase` only after the user approves the reviewed plan. Compatible implementation disciplines may be used inside tasks, but they do not own the lifecycle.

### BLOCKER 2 — The execution toolchain does not exist in the current environment

The plan assumes Terraform, Azure CLI, TFLint, Checkov, and WSL2/bash. None were callable here, and `wsl.exe` was absent. Treating installation as implicit would make Task 1 non-executable and could trigger network/system mutations without approval.

**Correction:** Add Toolchain Gate 0. The user selects the execution host (native PowerShell or a separately prepared Linux/WSL environment), approves any installations, and verifies pinned versions before code changes. Commands after this gate must consistently use the selected shell.

### BLOCKER 3 — Existing Task 0 is stale and contains an unsafe optional rewrite

The worktree is clean. Adding `.gitattributes` and renormalizing the current mixed-EOL index would produce a large, expected mechanical diff—not the small diff claimed by the plan. The optional `git ls-files -z | xargs -0 rm && git checkout -- .` deletes every tracked working-tree file before restoration and should not appear in an infrastructure execution plan.

The dangling Python import is real, but it is unrelated to the Terraform phase and should not be mixed with repository-wide line-ending normalization.

**Correction:** Remove the current Task 0 from the critical path. If the user wants repository normalization, plan it as a separate, explicitly approved mechanical change. Leave the Python stub for its owning reconciler phase unless the user separately authorizes cleanup.

### BLOCKER 4 — Live cloud mutations lack explicit review/cost gates

The existing plan moves directly from code changes to bootstrap apply, lab apply, enabling two test VMs, and destroy. Those are distinct external mutations with different cost and recovery profiles. Azure budgets are notifications, not spend caps.

**Correction:** Add explicit checkpoints before:

1. bootstrapping the remote-state resource group/storage account;
2. applying the base lab;
3. enabling verification VMs;
4. destroying the lab.

Each checkpoint must show the selected subscription, sanitized plan summary, estimated resources/cost, flags, and rollback target. Planning approval alone must not be treated as approval for a later cost-bearing apply.

### BLOCKER 5 — Hub NSG terminal deny is narrower than the stated policy

`terraform/modules/hub/main.tf` names a rule `DenyAllOtherInbound`, but its source is only `Internet`. Azure's default `AllowVNetInBound` rule can therefore permit unmatched traffic from peered spokes to arbitrary hub ports. That contradicts the stated “SSH from home only” posture.

**Correction:** After explicit home-IP, DNS, and tunnel-source allow rules, use a terminal inbound deny whose source is `*`. Add a Terraform validation that rejects any `home_ip` not expressed as a single IPv4 `/32`. Verify the compiled NSG rules before apply and use both positive and negative live tests afterward.

### BLOCKER 6 — Backend handling is environment-specific and incomplete

Committing a random, subscription-specific storage account name into both Azure and Cloudflare roots makes the repository non-portable. HashiCorp supports partial backend configuration and warns that backend configuration is copied into `.terraform/` and saved plans; credentials must remain environment-sourced.

**Correction:** Keep non-secret, stable fields in each backend block and provide the generated storage account through a gitignored backend-config file or explicit `terraform init -backend-config` argument. Use Azure CLI/Entra authentication rather than embedding credentials. Commit provider lock files created by the approved `terraform init` runs. Document secure handling/recovery of the bootstrap stack's local state.

### IMPORTANT 1 — Make AzureRM subscription selection explicit

AzureRM 4.x requires a subscription ID for plan/apply. Current provider documentation can source it from configuration, `ARM_SUBSCRIPTION_ID`, or the active Azure CLI subscription, while the 4.0 upgrade guide recommends the property or environment variable. The repository declares `subscription_id` but does not bind it in the provider blocks.

**Correction:** Set `subscription_id = var.subscription_id` in the lab provider and add an equivalent explicit input for bootstrap, or standardize on `ARM_SUBSCRIPTION_ID` and remove the misleading unused variable. In all cases, compare it with `az account show` at every cloud checkpoint.

### IMPORTANT 2 — Preserve and verify the DNS-forwarder design

Azure states that a VNet using custom DNS does not automatically query linked Private DNS zones; the custom DNS server must forward private-zone queries to `168.63.129.16`. The current spokes point at the hub VM and the current hub template forwards to Azure DNS, which is the intended design.

**Correction:** Keep this architecture, make the forwarding rule explicit, and verify both `@168.63.129.16` and `@127.0.0.1` on the hub before testing from a spoke. Verify both UDP and TCP DNS paths. Do not enable Azure DNS Private Resolver in this phase.

### IMPORTANT 3 — NVA egress proof depends on both Azure and guest settings

Microsoft requires Azure NIC IP forwarding, guest OS IP forwarding, and proxy/NAT when a virtual appliance sends private-source traffic to public destinations. Current Terraform enables NIC forwarding and the existing plan correctly proposes guest forwarding plus MASQUERADE.

**Correction:** Retain the NVA fix, make the outbound interface discovery robust rather than assuming an interface name where practical, and verify the effective UDR, guest forwarding flag, NAT rule/counter, and observed egress IP as separate checks.

### IMPORTANT 4 — Verification workloads are necessary but cost-bearing

Without a workload NIC, the plan cannot prove effective routes, custom DNS, auto-registration, egress, or spoke isolation. The proposed flag-gated, no-public-IP test VMs are justified.

**Correction:** Keep every per-spoke test VM/NIC flag false by default. Apply and verify the base stack first, then require a separate saved-plan approval for a short test-VM session. Set all four explicitly when state is partial. Do not describe the VMs, disks, state storage, or public IP as universally free; eligibility and pricing depend on the subscription and current rates.

### IMPORTANT 5 — Static validation and lock files must precede every plan

The plan lacks a complete offline quality gate and does not mention lock files.

**Correction:** After the selected toolchain is available, run in order:

1. `terraform fmt -check -recursive`;
2. `terraform init -backend=false` and `terraform validate` in bootstrap and lab roots;
3. `tflint --init` and `tflint --recursive`;
4. Checkov against `terraform/`, with any suppressions scoped and justified;
5. secret scanning and `git check-ignore` checks for tfvars, backend config, plans, state, and keys;
6. real-backend `terraform init`, then review and commit `.terraform.lock.hcl` files;
7. a saved plan and a sanitized machine-readable summary.

Expected resource counts may be used as a review hint, not as the sole assertion. The plan must explicitly assert that resolver resources are absent and only the hub has a public IP.

### IMPORTANT 6 — Evidence must be intentionally sanitized

Raw Azure CLI, Terraform plan, state, or debug output can include subscription IDs, tenant IDs, public/home IPs, email addresses, public keys, and backend details. Public identifiers are not credentials, but they need not be committed.

**Correction:** Capture narrow `--query` projections, redact account-specific values, never commit raw plan/state/debug logs, and run a secret/identifier review before staging `docs/evidence/phase2/`.

### IMPORTANT 7 — Completion claims must remain live-evidence gated

This planning pass can verify that the plan is executable and requirement-complete; it cannot verify that Azure resources apply, route, resolve, isolate, or destroy successfully.

**Correction:** Keep README Phase 2 unchecked until all live exit criteria pass. The plan-verification report must label live checks `DEFERRED TO IMPLEMENTATION`, not `PASS`.

### NICE TO HAVE

- Add validation for SSH and WireGuard public-key formats and for mutually safe feature flags.
- State the expected lifecycle of the generated WireGuard laptop key: public key may enter tfvars/state; private key must remain outside the repository and Terraform state.
- Use explicit `sku = "Standard"` for the hub public IP even though current AzureRM 4.x defaults to Standard; this makes the post-Basic-SKU intent obvious.
- Add storage-state recovery guidance such as blob versioning/retention, subject to the chosen cost/security posture.
- Use a verification table that records command, expected invariant, evidence file, and sensitivity review.

## Recommended plan order

1. **Human Plan Review Gate** — approve scope and unresolved execution choices; no implementation before this gate.
2. **Toolchain Gate** — select shell/host, approve installations, record versions.
3. **Terraform correctness and security** — provider subscription binding, NSG terminal deny, `/32` validation, BIND ACL/recursion, NVA forwarding/NAT, explicit public-IP SKU, accurate comments.
4. **Flag-gated verification workload** — test NIC/VM resources, inputs, outputs, default-off behavior.
5. **Offline validation** — fmt, backend-disabled init/validate, TFLint, Checkov, secret checks.
6. **Remote-state design and bootstrap checkpoint** — partial backend configuration, approved bootstrap plan/apply, secure local bootstrap state, lock files.
7. **Local inputs and saved base plan** — gitignored tfvars/backend config/keys, subscription check, sanitized plan review.
8. **Base Apply Checkpoint** — explicit approval, apply saved plan, verify hub/peerings/BIND/NVA/budget.
9. **Verification-VM Checkpoint** — explicit approval, enable temporary VMs, verify effective routes, DNS, auto-registration, egress, positive hub access, and negative spoke isolation/exposure.
10. **Destroy Checkpoint** — explicit destructive approval, destroy lab, verify lab RG absent and backend RG retained, generate (but do not apply) a clean recreation plan.
11. **Closeout** — sanitize evidence, update runbook/architecture if reality differed, check README only after every live criterion passes.

## Verification matrix for the revised plan

| Dimension | Plan must specify | Planning-pass status |
|---|---|---|
| Scope | Azure core, Private DNS, NVA, two spokes; resolver disabled | Evidence available |
| Process | GSD-owned execution and human approval gate | Must be corrected |
| Toolchain | Exact host/shell and version preflight | Blocked pending user choice/install approval |
| Static Terraform | fmt, validate, TFLint, Checkov, lock files | Deferred; tools absent |
| State | Portable backend config, credential isolation, recovery | Must be corrected |
| Security | `/32`, home-only public ingress, terminal deny, secret checks | Must be corrected |
| Cost | Subscription check, current estimate, short test window, no spend-cap claim | Must be corrected |
| DNS | custom DNS to hub; hub forward to `168.63.129.16`; UDP/TCP proof | Architecture supported; live proof deferred |
| Routing | peerings, UDRs, NIC/guest forwarding, SNAT | Architecture supported; live proof deferred |
| Testability | temporary spoke workloads and positive/negative checks | Must be implemented later |
| Destruction | explicit approval, lab RG absent, backend retained, re-plan only | Live proof deferred |
| Evidence | narrow queries, redaction, no raw state/plan/debug logs | Must be corrected |

## Review decisions for the user

The revised plan should surface these decisions rather than silently assume them:

1. **Execution host:** native PowerShell on this Windows workspace, or a separately prepared Linux/WSL environment.
2. **Backend authentication:** Entra ID/RBAC with partial configuration is preferred; any alternative must avoid committed credentials.
3. **Repository hygiene:** exclude line-ending normalization and the unrelated Python stub from Phase 2 unless separately authorized.
4. **Live execution:** plan approval authorizes planning only; bootstrap/apply/test-VM/destroy each remain later explicit checkpoints.

## Research conclusion

Phase 2 is plannable without changing the architecture. The existing plan should be revised in place around the blocker corrections above, then checked goal-backward by an independent plan verifier. Passing that check means the plan is safe and complete enough to review—not that Azure has been deployed or verified.
