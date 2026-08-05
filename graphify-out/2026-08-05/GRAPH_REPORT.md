# Graph Report - .  (2026-08-04)

## Corpus Check
- 78 files · ~59,177 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 342 nodes · 544 edges · 20 communities (15 shown, 5 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 61 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `diff_records()` - 27 edges
2. `rec()` - 24 edges
3. `Phase 2 Code Review Report` - 19 edges
4. `Phase 3 WireGuard Tunnel and Hybrid DNS Implementation Plan` - 19 edges
5. `Phase 4 Cloudflare and Reconciler v2 Implementation Plan` - 18 edges
6. `Phase 2 Azure Core Candidate Implementation Plan` - 15 edges
7. `Phase 2 Azure Core Planning Research` - 13 edges
8. `Phase 5 CI/CD Pipeline Implementation Plan` - 12 edges
9. `CanonicalRecord` - 11 edges
10. `Phase 2 Code Review Fix Report` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Exact-Hash Approval Boundary` --semantically_similar_to--> `Reviewed Plan Approval Binding`  [INFERRED] [semantically similar]
  docs/evidence/phase2/checkpoint-c-plan.md → .github/workflows/apply.yml
- `Exact-Hash Destroy Approval` --semantically_similar_to--> `Two-Stage Destroy Gate`  [INFERRED] [semantically similar]
  docs/evidence/phase2/checkpoint-d-destroy-ncus.md → .github/workflows/destroy.yml
- `No-Drift Guard` --semantically_similar_to--> `Nightly Drift Detection`  [INFERRED] [semantically similar]
  docs/evidence/phase3/checkpoint-a-readiness.md → .github/workflows/drift.yml
- `East US 2 Phase 2 Rebuild` --conceptually_related_to--> `Azure Hub-and-Spoke Lab`  [INFERRED]
  .remember/today-2026-08-03.done.md → docs/superpowers/plans/2026-07-31-phase-2-azure-core.md
- `Terraform and Reconciler Repository Review` --conceptually_related_to--> `cham Phases 2–5 Overview`  [INFERRED]
  .remember/archive.md → docs/superpowers/plans/2026-07-31-phases-2-5-overview.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Reviewed Saved-Plan CI Flow** — workflows_plan_manual_main_saved_plan, workflows_plan_sanitized_plan_manifest, workflows_plan_immutable_plan_artifact, workflows_apply_current_main_source_run_verification, workflows_apply_artifact_manifest_hash_verification, workflows_apply_protected_lab_environment, workflows_apply_exact_saved_plan_apply [EXTRACTED 1.00]
- **Hybrid DNS Planes** — docs_architecture_cloudflare_public_dns_plane, docs_architecture_spatium_bind_dns_plane, docs_architecture_azure_private_dns_plane, readme_python_reconciler_convergence [EXTRACTED 1.00]
- **Phase 3 Readiness Flow** — phase3_checkpoint_a_readiness_pinned_spatium_runtime, phase3_checkpoint_a_readiness_bind_wireguard_rehearsal, phase3_checkpoint_a_readiness_kea_ddns_rehearsal, phase3_checkpoint_a_readiness_no_drift_guard, phase3_checkpoint_a_readiness_vm_deallocation_watchdog, phase3_checkpoint_a_readiness_checkpoint_b_timebox [EXTRACTED 1.00]
- **Phase 2 Gated Azure Lifecycle** — plans_2026_07_31_phase_2_azure_core_azure_hub_and_spoke_lab, plans_2026_07_31_phase_2_azure_core_entra_rbac_azure_remote_state, plans_2026_07_31_phase_2_azure_core_default_off_spoke_verification_vms, plans_2026_07_31_phase_2_azure_core_saved_plan_approval_gates, plans_2026_07_31_phase_2_azure_core_sanitized_infrastructure_evidence [EXTRACTED 1.00]
- **Phase 3 Hybrid DNS Proof Flow** — plans_2026_07_31_phase_3_wireguard_hybrid_dns_native_debian_docker_engine, plans_2026_07_31_phase_3_wireguard_hybrid_dns_exact_address_spatium_dns_listener, plans_2026_07_31_phase_3_wireguard_hybrid_dns_split_tunnel_wireguard_link, plans_2026_07_31_phase_3_wireguard_hybrid_dns_bidirectional_conditional_dns_forwarding, plans_2026_07_31_phase_3_wireguard_hybrid_dns_fresh_kea_lease_dns_proof, plans_2026_07_31_phase_3_wireguard_hybrid_dns_mandatory_tunnel_and_vm_closeout, plans_2026_07_31_phase_3_wireguard_hybrid_dns_independent_deallocation_watchdog [EXTRACTED 1.00]
- **Reconciler Multi-Edge Convergence** — plans_2026_07_31_phase_4_cloudflare_reconciler_v2_spatiumddi_read_only_source_of_truth, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_managed_key_ownership_allowlist, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_per_edge_convergence_runner, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_azure_private_dns_adapter, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_cloudflare_rrset_adapter, plans_2026_07_31_phase_4_cloudflare_reconciler_v2_committed_desired_state_snapshot_adr_006 [EXTRACTED 1.00]

## Communities (20 total, 5 thin omitted)

### Community 0 - "Hybrid DDI Architecture"
Cohesion: 0.07
Nodes (40): Azure Private DNS Plane, Cloudflare Public DNS Plane, Hub-and-Spoke Address Plan, Hybrid DNS Architecture, Internal BIND View, Spatium BIND DNS Plane, WireGuard Transfer Network, ADR-001 BIND VM over Private Resolver (+32 more)

### Community 1 - "Azure Core Planning"
Cohesion: 0.09
Nodes (35): Azure Hub-and-Spoke Lab, Azure Private DNS Zone azure.dwsolution.co, Checkpoint C Regional Core Quota Block, Default-Off Spoke Verification VMs, Deterministic NVA SNAT, Entra RBAC Azure Remote State, Hub BIND9 DNS Forwarder and NVA, Phase 2 Azure Core Candidate Implementation Plan (+27 more)

### Community 2 - "Reconciler Domain Model"
Cohesion: 0.10
Nodes (21): CanonicalRecord, Diff, CanonicalRecord, RecordKey, CanonicalRecord, Diff, RecordKey, CloudflareProvider (+13 more)

### Community 3 - "Terraform Approval Workflows"
Cohesion: 0.09
Nodes (33): CI Prerequisites, Exact-Artifact Session Start, Exact-Plan Session End, Hybrid DDI Runbook, Private Resolver Timebox, State-Derived Resource Flags, Partial Test State Representation, Phase 2 Post-Review Corrections (+25 more)

### Community 4 - "Reconciler Test Suite"
Cohesion: 0.14
Nodes (31): diff_records(), Compare desired vs actual within an explicit ownership boundary.      Every de, Diff-logic tests — these run today, before any provider exists. Being able to t, rec(), test_a_record_values_are_whitespace_stripped(), test_aaaa_representation_does_not_create_false_drift(), test_aaaa_values_are_canonicalized(), test_changed_value_is_update_not_add_delete() (+23 more)

### Community 5 - "WireGuard Hybrid DNS"
Cohesion: 0.11
Nodes (32): Checkpoint B Hard Stop, Continue Here Phase 3 Checkpoint A Review, Phase 3 Checkpoint A Complete, Resolved Zero-Cost Phase 3 Prerequisites, Retained Deallocated Lab State, Bidirectional Conditional DNS Forwarding, Direct-Hop Before Composed DNS Testing, Exact-Address Spatium DNS Listener (+24 more)

### Community 6 - "Phase 2 Review Fixes"
Cohesion: 0.10
Nodes (29): Bidirectional NVA Transit Fix, Configuration Single-Sourcing, Hub DNS Forwarding Target, Hub NSG Destination Scoping, Network Input Validation, Per-Spoke Resource Flags, Phase 2 Code Review Fix Report, Skipped Behavior Changes (+21 more)

### Community 7 - "Repository Skill Routing"
Cohesion: 0.14
Nodes (22): Graphify-First Repository Navigation, Infrastructure Security and Cost Controls, Offline Reconciler Test Boundary, Repository Agent Guidelines, AGENTS.md Skill Discovery Hook, Process Domain Repository-Tools Order, Repository Skill-Routing Handbook, Repository Skills Handbook Implementation Plan (+14 more)

### Community 8 - "Capacity Recovery Evidence"
Cohesion: 0.12
Nodes (18): Obsolete Recovery Plan Retirement, 32-Resource Base Posture, Basv2 Capacity Gate, North Central US Base Lab, Phase 2 Checkpoint B Evidence, Basv2 Family Quota Failure, D2als v6 Test VM Alternative, One-Hour Cost Timebox (+10 more)

### Community 9 - "Cloudflare Reconciler Plan"
Cohesion: 0.22
Nodes (18): Azure Private DNS Adapter, CanonicalRecord Boundary Model, Cloudflare Public DNS Zone, Cloudflare RRset Adapter, Cloudflare Separate Terraform State ADR-004, Committed Desired-State Snapshot ADR-006, DDI Reconciler v2, Managed-Key Ownership Allowlist (+10 more)

### Community 10 - "Azure Regional Recovery"
Cohesion: 0.15
Nodes (17): Azure NRP Read-Path Inconsistency, East US 2 Base Lab Rebuild, Import Block Recovery, Phase 2 Checkpoint B East US 2 Rebuild, Verified Base Topology, Deallocated Closeout, Eight Topology Tests, Phase 2 Checkpoint C East US 2 Topology Tests (+9 more)

### Community 11 - "CI CD Roadmap"
Cohesion: 0.18
Nodes (17): Branch Protection Plan Jobs, Entra OIDC Workload Federation, Exact Saved-Plan Artifact Promotion, GitHub Actions Infrastructure Pipeline, Lab Environment Approval Gate, Phase 5 CI/CD Pipeline Implementation Plan, TFLint and Checkov Gates, Typed DESTROY Kill Switch (+9 more)

## Ambiguous Edges - Review These
- `Checkpoint C Capacity Block` → `Eight of Eight Phase 2 Topology Tests`  [AMBIGUOUS]
  .remember/today-2026-08-03.done.md · relation: conceptually_related_to

## Knowledge Gaps
- **43 isolated node(s):** `IN-02 Lexicographic Test Subnet Selection`, `IN-03 Region Default Mismatch`, `IN-08 Cloudflare Version Floor`, `IN-09 Untagged Resolver Resources`, `IN-11 Blocked ICMP Diagnostics` (+38 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Checkpoint C Capacity Block` and `Eight of Eight Phase 2 Topology Tests`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Phase 2 Post-Review Corrections` connect `Terraform Approval Workflows` to `Hybrid DDI Architecture`, `Capacity Recovery Evidence`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `Phase 2 Azure Core Planning Research` connect `Azure Core Planning` to `CI CD Roadmap`, `WireGuard Hybrid DNS`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `Phase 2 Code Review Fix Report` connect `Phase 2 Review Fixes` to `Terraform Approval Workflows`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `diff_records()` (e.g. with `canonical_record_key()` and `RecordUpdate`) actually correct?**
  _`diff_records()` has 21 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Azure provider for cham-reconcile.  Usage:     Uses azure-mgmt-privatedns wit`, `Cloudflare adapter — reconciled edge for the PUBLIC zone only.  Scoped API tok`, `SpatiumDDI adapter — the SOURCE OF TRUTH side.  Reads zones/records from the S` to the rest of the system?**
  _63 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Hybrid DDI Architecture` be split into smaller, more focused modules?**
  _Cohesion score 0.06794871794871794 - nodes in this community are weakly interconnected._