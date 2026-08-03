# Phase 2 Post-Review Corrections

Captured 2026-08-03 on `feat/plan-and-verify-phase-2` after the operator
approved all four post-review findings. No Terraform apply, VM start/stop,
destroy, provider registration, quota request, or other Azure mutation was run.

## 1. Obsolete recovery plan retired

- The pre-review artifact with SHA-256
  `cda9d41188a4c3cb7920208a8fefbf77349d003e3672181cf463afb1325faf35`
  was renamed locally to
  `SUPERSEDED-DO-NOT-APPLY-checkpoint-c-recovery-regional-cores-nva-nsg.tfplan`.
- It remains gitignored and ACL-restricted. Its prior approval is void because
  the embedded configuration predates the review fixes.
- A stray untracked plan accidentally written with the literal name
  `$planName` was permanently removed after its exact path and SHA-256 were
  verified. It was a regenerable local artifact and was never applied.
- Resume/evidence/plan documents now require a fresh state-backed plan from the
  current reviewed source and a new hash approval.

## 2. Partial test state represented safely

- Root configuration now has independent, nullable app/management VM and NIC
  overrides. The old shared VM flag remains only as a compatibility fallback.
- The spoke module can retain an already-created NIC while its VM is absent.
- The documented 35-resource state is represented as app VM/NIC `true`,
  management NIC `true`, management VM `false`.
- Hub cloud-init encoding now normalizes CRLF to LF. A first verification plan
  exposed a line-ending-only `custom_data` replacement; normalization removed
  that unsafe hub replacement without changing rendered cloud-init lines.

## 3. CI applies only reviewed artifacts

- A merge or push no longer triggers Terraform apply.
- Pull requests run only credential-free format, lint, security, and
  backend-disabled validation checks. They receive neither Azure/OIDC
  permissions nor a Terraform plan.
- Manual `plan.yml` runs on `main` create a three-day saved-plan artifact,
  manifest, sanitized resource summary, and SHA-256.
- `apply.yml` is manual and rejects anything except a successful manual plan
  run for the exact current `main` commit. It verifies the run, artifact name,
  repository, manifest, run ID, commit, and approved SHA-256 before applying
  the saved plan file.
- Apply and destroy jobs fail closed unless the `lab` environment reports a
  required-reviewer rule. Both workflows pass complete OIDC environment values
  and resolve the randomized state account before `terraform init`.
- `destroy.yml` is now a two-run plan/apply workflow. The second run can apply
  only the exact approved destroy-plan artifact; no raw `terraform destroy
  -auto-approve` remains.
- The live GitHub `lab` environment now has one required reviewer and a custom
  deployment branch policy permitting `main` only. This immediately gates the
  pre-existing main workflow and prevents feature-branch workflow variants
  from deploying through that environment.
- CI still requires the remaining external setup: OIDC secrets/federation,
  Contributor at subscription scope, and Storage Blob Data Contributor on the
  shared-key-disabled state account.
- A names-only GitHub check found none of the workflow's seven required
  repository secrets or `BUDGET_START_DATE` variable configured yet. The new
  workflows therefore fail before Terraform planning/apply until Phase 5
  provisions those values; no secret values were read or copied during this
  correction.

## 4. DNS Private Resolver path completed behind its cost gate

- The forwarding ruleset now creates links to the hub, app, and management
  VNets only when `enable_private_resolver = true`.
- The hub NSG creates a DNS-only outbound rule from the on-premises and
  WireGuard transfer prefixes to the resolver inbound subnet under the same
  flag.
- The resolver inbound subnet now has a flag-gated route table and association
  that returns both prefixes through the hub NVA, preventing an asymmetric
  reply path for queries arriving over WireGuard.
- Resolver subnet CIDRs are single-sourced between the resolver and hub
  modules. Default/Phase 2 behavior remains disabled and cost-neutral.
- The VNet links govern queries sent to Azure-provided DNS. Because current
  spoke clients remain configured for hub BIND, the optional resolver session
  validates the managed path but is not described as a one-flag client
  cutover.

## Fresh verification

- `terraform fmt -check -recursive terraform`: passed.
- Terraform validation: bootstrap, lab, and Cloudflare roots passed.
- TFLint: passed with zero issues.
- Checkov: 52 passed, 0 failed, 15 documented skips.
- Actionlint: all workflows passed.
- GitHub Actions Checkov: 225 passed, 0 failed, 3 documented skips.
- GitHub API readback: one required-reviewer rule, custom deployment branch
  policies enabled, and exactly one allowed pattern (`main`).
- State-backed verification plan flags: app VM/NIC `true`, management NIC
  `true`, management VM `false`, resolver `false`.
- Plan result: 0 create, 1 update, 0 delete, 0 replacement. The only action is
  an in-place update of `module.hub.azurerm_network_security_group.hub`.
- Plan inspection confirms both new transit rules, scoped home/DNS
  destinations, app VM/NIC and management NIC all `no-op`, management VM
  absent, and zero resolver changes.
- Verification artifact:
  `checkpoint-c-postreview-verification.tfplan`, SHA-256
  `73b71af977da790c2a282c2563e5ea046c1c5ce85c1e96f372a9086c1eae3c2e`.
  It is gitignored and ACL-restricted.
- A separate resolver-enabled verification plan showed exactly 12 gated
  resolver-module creates plus the same in-place hub NSG update, with zero
  deletes and zero replacements. Its three VNet links, inbound route table,
  and route-table association were all present. That temporary sensitive plan
  and both plan-output logs were permanently removed after inspection.
- Final Azure readback found `vm-hub-ddi` and `vm-test-app` both
  `VM deallocated` and zero deployed DNS Private Resolver resources.

The verification artifact was generated from an uncommitted working tree and
is **not approved for apply**. After the corrections are committed, generate a
new saved plan from that immutable commit, compare the complete delta, and
obtain a new explicit hash approval before any Azure mutation.
