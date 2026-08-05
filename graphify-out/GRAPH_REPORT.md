# Graph Report - cham  (2026-08-05)

## Corpus Check
- 75 files · ~59,607 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 716 nodes · 903 edges · 52 communities (43 shown, 9 thin omitted)
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 61 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d5e9af13`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Hybrid DDI Architecture|Hybrid DDI Architecture]]
- [[_COMMUNITY_Azure Core Planning|Azure Core Planning]]
- [[_COMMUNITY_Reconciler Domain Model|Reconciler Domain Model]]
- [[_COMMUNITY_Terraform Approval Workflows|Terraform Approval Workflows]]
- [[_COMMUNITY_Reconciler Test Suite|Reconciler Test Suite]]
- [[_COMMUNITY_WireGuard Hybrid DNS|WireGuard Hybrid DNS]]
- [[_COMMUNITY_Phase 2 Review Fixes|Phase 2 Review Fixes]]
- [[_COMMUNITY_Repository Skill Routing|Repository Skill Routing]]
- [[_COMMUNITY_Capacity Recovery Evidence|Capacity Recovery Evidence]]
- [[_COMMUNITY_Cloudflare Reconciler Plan|Cloudflare Reconciler Plan]]
- [[_COMMUNITY_Azure Regional Recovery|Azure Regional Recovery]]
- [[_COMMUNITY_CI CD Roadmap|CI CD Roadmap]]
- [[_COMMUNITY_Reconciler CLI Entry|Reconciler CLI Entry]]
- [[_COMMUNITY_CLI Contract Tests|CLI Contract Tests]]
- [[_COMMUNITY_Azure DNS Provider|Azure DNS Provider]]
- [[_COMMUNITY_Reconciler Package Facade|Reconciler Package Facade]]
- [[_COMMUNITY_Current Session Memory|Current Session Memory]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]

## God Nodes (most connected - your core abstractions)
1. `Phase 2 — Azure Core Candidate Implementation Plan` - 40 edges
2. `diff_records()` - 27 edges
3. `rec()` - 24 edges
4. `Phase 2: Code Review Report` - 23 edges
5. `Phase 2 Azure Core — Planning Research` - 22 edges
6. `Phase 3 WireGuard Tunnel and Hybrid DNS Implementation Plan` - 19 edges
7. `Phase 4 Cloudflare and Reconciler v2 Implementation Plan` - 18 edges
8. `Phase 2 Checkpoint C Recovery Evidence` - 17 edges
9. `Phase 3 Checkpoint A Readiness Evidence` - 17 edges
10. `Phase 5 — CI/CD Pipeline Implementation Plan` - 17 edges

## Surprising Connections (you probably didn't know these)
- `Exact-Hash Approval Boundary` --semantically_similar_to--> `Reviewed Plan Approval Binding`  [INFERRED] [semantically similar]
  docs/evidence/phase2/checkpoint-c-plan.md → .github/workflows/apply.yml
- `Exact-Hash Destroy Approval` --semantically_similar_to--> `Two-Stage Destroy Gate`  [INFERRED] [semantically similar]
  docs/evidence/phase2/checkpoint-d-destroy-ncus.md → .github/workflows/destroy.yml
- `No-Drift Guard` --semantically_similar_to--> `Nightly Drift Detection`  [INFERRED] [semantically similar]
  docs/evidence/phase3/checkpoint-a-readiness.md → .github/workflows/drift.yml
- `Terraform and Reconciler Repository Review` --conceptually_related_to--> `cham — Phases 2–5 Overview`  [INFERRED]
  .remember/archive.md → docs/superpowers/plans/2026-07-31-phases-2-5-overview.md
- `Remaining Phase Implementation Tasks` --conceptually_related_to--> `cham — Phases 2–5 Overview`  [INFERRED]
  .remember/today-2026-07-31.done.md → docs/superpowers/plans/2026-07-31-phases-2-5-overview.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Reviewed Saved-Plan CI Flow** — workflows_plan_manual_main_saved_plan, workflows_plan_sanitized_plan_manifest, workflows_plan_immutable_plan_artifact, workflows_apply_current_main_source_run_verification, workflows_apply_artifact_manifest_hash_verification, workflows_apply_protected_lab_environment, workflows_apply_exact_saved_plan_apply [EXTRACTED 1.00]
- **Hybrid DNS Planes** — docs_architecture_cloudflare_public_dns_plane, docs_architecture_spatium_bind_dns_plane, docs_architecture_azure_private_dns_plane, readme_python_reconciler_convergence [EXTRACTED 1.00]
- **Phase 3 Readiness Flow** — phase3_checkpoint_a_readiness_pinned_spatium_runtime, phase3_checkpoint_a_readiness_bind_wireguard_rehearsal, phase3_checkpoint_a_readiness_kea_ddns_rehearsal, phase3_checkpoint_a_readiness_no_drift_guard, phase3_checkpoint_a_readiness_vm_deallocation_watchdog, phase3_checkpoint_a_readiness_checkpoint_b_timebox [EXTRACTED 1.00]
- **Phase 2 Gated Azure Lifecycle** — plans_2026_07_31_phase_2_azure_core_azure_hub_and_spoke_lab, plans_2026_07_31_phase_2_azure_core_entra_rbac_azure_remote_state, plans_2026_07_31_phase_2_azure_core_default_off_spoke_verification_vms, plans_2026_07_31_phase_2_azure_core_saved_plan_approval_gates, plans_2026_07_31_phase_2_azure_core_sanitized_infrastructure_evidence [EXTRACTED 1.00]
- **Phase 3 Hybrid DNS Proof Flow** — plans_2026_07_31_phase_3_wireguard_hybrid_dns_native_debian_docker_engine, plans_2026_07_31_phase_3_wireguard_hybrid_dns_exact_address_spatium_dns_listener, plans_2026_07_31_phase_3_wireguard_hybrid_dns_split_tunnel_wireguard_link, plans_2026_07_31_phase_3_wireguard_hybrid_dns_bidirectional_conditional_dns_forwarding, plans_2026_07_31_phase_3_wireguard_hybrid_dns_fresh_kea_lease_dns_proof, plans_2026_07_31_phase_3_wireguard_hybrid_dns_mandatory_tunnel_and_vm_closeout, plans_2026_07_31_phase_3_wireguard_hybrid_dns_independent_deallocation_watchdog [EXTRACTED 1.00]
- **Reconciler Multi-Edge Convergence** — plans_2026_07_31_phase_4_cloudflare_reconciler_v2_spatiumddi_read_only_source_of_truth, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_managed_key_ownership_allowlist, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_per_edge_convergence_runner, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_azure_private_dns_adapter, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_cloudflare_rrset_adapter, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_committed_desired_state_snapshot_adr_006 [EXTRACTED 1.00]

## Communities (52 total, 9 thin omitted)

### Community 0 - "Hybrid DDI Architecture"
Cohesion: 0.28
Nodes (9): Azure Private DNS Plane, Cloudflare Public DNS Plane, Hybrid DNS Architecture, Internal BIND View, Spatium BIND DNS Plane, WireGuard Transfer Network, ADR-002 WireGuard over VPN Gateway, BIND WireGuard Rehearsal (+1 more)

### Community 1 - "Azure Core Planning"
Cohesion: 0.16
Nodes (14): Azure Hub-and-Spoke Lab, Azure Private DNS Zone azure.dwsolution.co, Checkpoint C Regional Core Quota Block, Default-Off Spoke Verification VMs, Private Resolver Disabled Cost Gate, Spoke Isolation, Phase 3 Private Resolver Absence, All-Source Terminal Hub NSG Deny (+6 more)

### Community 2 - "Reconciler Domain Model"
Cohesion: 0.06
Nodes (52): CanonicalRecord, Diff, CanonicalRecord, RecordKey, CanonicalRecord, Diff, RecordKey, CloudflareProvider (+44 more)

### Community 3 - "Terraform Approval Workflows"
Cohesion: 0.05
Nodes (46): CI prerequisites, Exact-Artifact Session Start, Exact-Plan Session End, Hybrid DDI Runbook, Phase 3 local runtime pin (Checkpoint A), Phase 3 Runtime Pin, Private Resolver session (~$2, timeboxed), Private Resolver Timebox (+38 more)

### Community 4 - "Reconciler Test Suite"
Cohesion: 0.06
Nodes (31): 1.1 Resolve and verify the toolchain, 1.2 Restore and prove the Phase 1 runtime, 1.3 Rehearse the fresh Kea lease proof, 1.4 Re-run the ignored-input and live-state guards, 1.5 Prepare and dry-run the independent VM watchdog, 1.6 Checkpoint A report, 2.1 Arm closeout, then start the hub only, 2.2 Install or reuse the hub WireGuard key safely (+23 more)

### Community 5 - "WireGuard Hybrid DNS"
Cohesion: 0.09
Nodes (38): Checkpoint B Hard Stop, Continue Here — Phase 3 Checkpoint A Review, Current live state, Material revisions, Next action, Phase 3 Checkpoint A Complete, Planning artifacts, Resolved Zero-Cost Phase 3 Prerequisites (+30 more)

### Community 6 - "Phase 2 Review Fixes"
Cohesion: 0.15
Nodes (13): Post-Review Verification, Bidirectional NVA Transit Fix, Hub DNS Forwarding Target, Hub NSG Destination Scoping, Per-Spoke Resource Flags, Phase 2 Code Review Fix Report, Spoke Isolation Posture, State-Backed Plan Review (+5 more)

### Community 7 - "Repository Skill Routing"
Cohesion: 0.06
Nodes (39): Graphify-First Repository Navigation, Infrastructure Security and Cost Controls, Offline Reconciler Test Boundary, Repository Agent Guidelines, GSD Lifecycle Ownership Correction, AGENTS.md Skill Discovery Hook, Global Constraints, Process Domain Repository-Tools Order (+31 more)

### Community 8 - "Capacity Recovery Evidence"
Cohesion: 0.05
Nodes (41): 32-Resource Base Posture, Approved artifact, Basv2 Capacity Gate, Capacity and next gate, Live verification, North Central US Base Lab, Phase 2 Checkpoint B Evidence, Sanitization (+33 more)

### Community 9 - "Cloudflare Reconciler Plan"
Cohesion: 0.11
Nodes (28): Azure Private DNS Adapter, CanonicalRecord Boundary Model, Cloudflare Public DNS Zone, Cloudflare RRset Adapter, Cloudflare Separate Terraform State ADR-004, Committed Desired-State Snapshot ADR-006, DDI Reconciler v2, Managed-Key Ownership Allowlist (+20 more)

### Community 10 - "Azure Regional Recovery"
Cohesion: 0.08
Nodes (26): Apply chronology, Azure NRP Read-Path Inconsistency, East US 2 Base Lab Rebuild, Import Block Recovery, Phase 2 Checkpoint B — eastus2 Rebuild, Verification, Verified Base Topology, Deallocated Closeout (+18 more)

### Community 11 - "CI CD Roadmap"
Cohesion: 0.13
Nodes (20): Branch Protection Plan Jobs, Entra OIDC Workload Federation, Exact Saved-Plan Artifact Promotion, Exit Criteria (all must hold), GitHub Actions Infrastructure Pipeline, Global Constraints, Lab Environment Approval Gate, Phase 5 — CI/CD Pipeline Implementation Plan (+12 more)

### Community 20 - "Community 20"
Cohesion: 0.08
Nodes (25): Commits (oldest first), Fixed Issues, IN-01: MASQUERADE exclusion covers only 10.0.0.0/8, not all RFC1918, IN-02: Test VM subnet chosen by `values(...)[0]` — lexicographic accident, IN-03: Module `location` defaults ("eastus") contradict the lab region, IN-04: No validation on CIDR/IP variables rendered into named.conf/WG/NSGs, IN-05: Budget amount/thresholds magic numbers; `budget_start_date` unvalidated, IN-06: Hub VM has no boot diagnostics while extensions are disabled (+17 more)

### Community 21 - "Community 21"
Cohesion: 0.08
Nodes (24): Architecture, Checkpoint A requirements — used inside Task 4, Checkpoint B — Base plan, subscription, and cost, Checkpoint C — Temporary verification workload, Checkpoint D — Destructive approval, Decisions selected for review, Dependency map, Exit criteria (+16 more)

### Community 22 - "Community 22"
Cohesion: 0.08
Nodes (23): Exit Criteria (all must hold), Global Constraints, Phase 4 — Cloudflare + Reconciler v2 Implementation Plan, Target File Structure (Track B), Task A1: Cloudflare zone and scoped token (manual, console), Task A2: Terraform edits — public www target + internal page on the hub, Task A3: Internal www override zone in SpatiumDDI, Task A4: Apply the Cloudflare stack (+15 more)

### Community 23 - "Community 23"
Cohesion: 0.10
Nodes (20): Azure, BLOCKER 1 — The local DNS endpoint is not currently executable, BLOCKER 2 — Docker Desktop container traffic bypasses Debian `wg0`, BLOCKER 3 — The selected WSL endpoint lacks WireGuard and keys, BLOCKER 4 — The old prerequisite and VM lifecycle are stale, BLOCKER 5 — Hub key installation is unsafe to rerun, BLOCKER 6 — Closeout does not stop cost, Evidence examined (+12 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (19): Entra RBAC Azure Remote State, Saved-Plan Approval Gates, Azure Private DNS Zone Overview, Azure Virtual Network Routing and NVA Requirements, Baseline facts, Current first-party references, Evidence examined, Executive finding (+11 more)

### Community 25 - "Community 25"
Cohesion: 0.13
Nodes (15): One-Hour Cost Timebox, Checkpoint B Timebox, Checkpoint B timebox and rollback, Fresh Kea lease and automatic DDNS rehearsal, Ignored-input, state, and no-drift guards, Independent watchdog, Local finally cleanup, Local security and runtime checks (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.12
Nodes (15): Deterministic audit evidence, Dimension scores, Final verification statement, Goal-backward traceability, Goal-Backward Traceability Review, Live-verification status, Non-blocking execution flags, Phase 2 Azure Core — Plan Verification (+7 more)

### Community 27 - "Community 27"
Cohesion: 0.12
Nodes (15): Audit or Review, Bug or CI Failure, Evidence Order, Failure and Fallback Rules, Feature or Infrastructure Work, Hybrid Policy, Layer 2: Domain Specialists, Layer 3: Repository Tools and Facts (+7 more)

### Community 28 - "Community 28"
Cohesion: 0.13
Nodes (15): BLOCKER 1 — Process and approval routing is wrong, BLOCKER 2 — The execution toolchain does not exist in the current environment, BLOCKER 3 — Existing Task 0 is stale and contains an unsafe optional rewrite, BLOCKER 4 — Live cloud mutations lack explicit review/cost gates, BLOCKER 5 — Hub NSG terminal deny is narrower than the stated policy, BLOCKER 6 — Backend handling is environment-specific and incomplete, Findings, IMPORTANT 1 — Make AzureRM subscription selection explicit (+7 more)

### Community 29 - "Community 29"
Cohesion: 0.16
Nodes (13): ADR-001: BIND9 on a burstable VM instead of Azure DNS Private Resolver, ADR-001 BIND VM over Private Resolver, ADR-002: WireGuard instead of Azure VPN Gateway, ADR-003: Hub-and-spoke over a single flat VNet, ADR-004 Separate Terraform State, ADR-004: Separate Terraform state for Cloudflare vs Azure, ADR-005: SpatiumDDI as source of truth; Terraform seeds, reconciler converges, Architecture Decision Records (+5 more)

### Community 30 - "Community 30"
Cohesion: 0.18
Nodes (12): Configuration Single-Sourcing, IN-02 Lexicographic Test Subnet Selection, IN-03 Region Default Mismatch, IN-08 Cloudflare Version Floor, IN-09 Untagged Resolver Resources, IN-11 Blocked ICMP Diagnostics, IN-12 Provider Registration Documentation, Phase 2: Code Review Report (+4 more)

### Community 31 - "Community 31"
Cohesion: 0.15
Nodes (13): IN-01: MASQUERADE exclusion covers only 10.0.0.0/8, not all RFC1918, IN-02: Test VM subnet chosen by `values(...)[0]` — lexicographic accident, not declaration, IN-03: Module `location` defaults ("eastus") contradict the lab's region ("northcentralus"), IN-04: No validation on `onprem_address_space`, `wg_transfer_cidr`, `onprem_dns_ip`, `hub_vm_ip` — malformed values render straight into named.conf, IN-05: Budget amount/thresholds are magic numbers and `budget_start_date` format is unvalidated, IN-06: Hub VM has no boot diagnostics while extensions are also disabled — cloud-init failures are undebuggable, IN-07: One `enable_test_vm` flag drives both spokes — quota-blocked partial applies cannot converge, IN-08: Cloudflare version floor `~> 4.0` understates the real requirement of the `content` attribute; no tfvars.example for the cloudflare root (+5 more)

### Community 32 - "Community 32"
Cohesion: 0.20
Nodes (9): Build, Test, and Development Commands, Coding Style & Naming Conventions, Commit & Pull Request Guidelines, graphify, Project Structure & Module Organization, Repository Guidelines, Security & Cost Controls, Skill Routing (+1 more)

### Community 33 - "Community 33"
Cohesion: 0.22
Nodes (8): Hub-and-Spoke Address Plan, ADR-003 Hub-Spoke Topology, Kea DDNS Rehearsal, Dependency-Ordered Provisioning, DHCP-to-DNS Propagation, IPAM Cloud Space Model, SpatiumDDI — local stack, SpatiumDDI Upstream Repository

### Community 34 - "Community 34"
Cohesion: 0.25
Nodes (7): 11:48 | feat/plan-and-verify-phase-2, 17:18 | feat/plan-and-verify-phase-2, 17:53-18:30 | feat/plan-and-verify-phase-2, 18:53 | feat/plan-and-verify-phase-2, 19:24 | feat/plan-and-verify-phase-2, 21:08 | feat/plan-and-verify-phase-2, 23:13 | feat/plan-and-verify-phase-2

### Community 35 - "Community 35"
Cohesion: 0.33
Nodes (7): ADR-005 Spatium Source of Truth, No-Drift Guard, Python Reconciler Convergence, Drift Issue Creation, Nightly Drift Detection, Nightly Drift Workflow, Reconciler Dry Run

### Community 36 - "Community 36"
Cohesion: 0.29
Nodes (7): Warnings, WR-01: Hub NSG has no outbound rules — all on-prem/WireGuard-initiated traffic toward spokes is dropped at the hub NIC, WR-02: Spoke-to-spoke "allow via hub only" is not implemented — forwarded inter-spoke traffic is denied by both the hub and destination-spoke NSGs, WR-03: dns-resolver forwarding rule targets an address unreachable from the resolver subnet — the flag-gated feature cannot work when enabled, WR-04: `onprem_address_space` is not passed to the hub module — overriding it in tfvars silently splits hub and spoke views of on-prem, WR-05: Spoke CIDRs are duplicated as literals between the hub's transit allow-list and the spoke module blocks, WR-06: cloud-init hardcodes WireGuard addressing (172.16.0.1/24, 172.16.0.2/32), ignoring the `wg_transfer_cidr`/`onprem_dns_ip` variables it renders elsewhere in the same file

### Community 37 - "Community 37"
Cohesion: 0.29
Nodes (7): 1.1 Make subscription selection explicit, 1.2 Enforce a single IPv4 /32, 1.3 Close the hub NSG default-rule gap, 1.4 Prepare BIND and the NVA, 1.5 Preserve spoke isolation, 1.6 Local task check, Task 1 — Terraform correctness and security

### Community 38 - "Community 38"
Cohesion: 0.29
Nodes (6): Correction verification, Deterministic validation, Independent goal-backward review, Phase 3 WireGuard + Hybrid DNS — Plan Verification, Review gate, Review target and safety boundary

### Community 39 - "Community 39"
Cohesion: 0.40
Nodes (4): Apply, Closeout, Phase 2 Checkpoint C — eastus2 Simultaneous Three-VM Topology Tests, Test results — all eight pass

### Community 40 - "Community 40"
Cohesion: 0.40
Nodes (4): Apply outcome, Approval boundary, Cost effect, Phase 2 Checkpoint D — North Central US Lab Stack Destroy

### Community 41 - "Community 41"
Cohesion: 0.40
Nodes (5): 4.1 Partial backend configuration, 4.2 Harden state storage, 4.3 Review and apply the saved bootstrap plan, 4.4 Initialize lab with local non-credential config, Task 4 — Portable remote state and bootstrap

### Community 42 - "Community 42"
Cohesion: 0.40
Nodes (4): cham, Layout, Status, What this demonstrates

### Community 43 - "Community 43"
Cohesion: 0.50
Nodes (3): Addressing, Architecture, DNS zones

### Community 44 - "Community 44"
Cohesion: 0.67
Nodes (3): Network Input Validation, IN-04 Missing Network Value Validation, IN-05 Budget Magic and Date Validation

### Community 45 - "Community 45"
Cohesion: 0.67
Nodes (3): Skipped Behavior Changes, IN-01 Incomplete RFC1918 SNAT Exclusion, IN-06 Missing Boot Diagnostics

## Ambiguous Edges - Review These
- `Checkpoint C Capacity Block` → `Eight of Eight Phase 2 Topology Tests`  [AMBIGUOUS]
  .remember/today-2026-08-03.done.md · relation: conceptually_related_to

## Knowledge Gaps
- **340 isolated node(s):** `Current live state`, `Planning artifacts`, `Material revisions`, `Zero-cost prerequisites resolved`, `Next action` (+335 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **9 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Checkpoint C Capacity Block` and `Eight of Eight Phase 2 Topology Tests`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Phase 2 Azure Core — Planning Research` connect `Community 24` to `Azure Core Planning`, `WireGuard Hybrid DNS`, `Repository Skill Routing`, `Cloudflare Reconciler Plan`, `Community 21`, `Community 26`, `Community 28`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Why does `Phase 2 Post-Review Corrections` connect `Terraform Approval Workflows` to `Phase 2 Review Fixes`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `diff_records()` (e.g. with `canonical_record_key()` and `RecordUpdate`) actually correct?**
  _`diff_records()` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Azure provider for cham-reconcile.  Usage:     Uses azure-mgmt-privatedns wit`, `Cloudflare adapter — reconciled edge for the PUBLIC zone only.  Scoped API tok`, `SpatiumDDI adapter — the SOURCE OF TRUTH side.  Reads zones/records from the S` to the rest of the system?**
  _360 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Reconciler Domain Model` be split into smaller, more focused modules?**
  _Cohesion score 0.06153846153846154 - nodes in this community are weakly interconnected._
- **Should `Terraform Approval Workflows` be split into smaller, more focused modules?**
  _Cohesion score 0.054078014184397165 - nodes in this community are weakly interconnected._