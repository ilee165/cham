# Repository Skills Handbook Design

**Date:** 2026-08-01
**Status:** Approved design

## Purpose

Create a repository-local `SKILLS.md` that helps agents select useful installed skills before they build, improve, fix, review, or audit cham. The handbook is a routing document, not an installable Codex skill and not a catalog of every skill available in the environment.

The handbook must make workflow ownership unambiguous, keep skill usage proportionate to task risk, and connect general agent workflows to this repository's Terraform, Python, DNS, security, and cost constraints.

## Discovery and Precedence

Update `AGENTS.md` to include `@SKILLS.md` and require agents to read the handbook before non-trivial work. Keep detailed routing in `SKILLS.md`; retain project invariants and the immediate graphify rules in `AGENTS.md`.

Precedence is:

1. System and user instructions
2. `AGENTS.md`
3. `SKILLS.md`
4. The selected skill's own instructions

An explicitly requested skill must be used when available. If a routed skill is unavailable, the agent must state the fallback and continue with the closest safe workflow; it must not invent a skill or silently install a plugin.

## Three-Layer Operating Model

For non-trivial tasks, agents select and apply layers in this order:

1. **Process:** GSD or Superpowers decides how the work is managed.
2. **Domain:** Load the smallest set of specialists matching the task.
3. **Repository tools and facts:** Use graphify, project documents, scoped commands, MCP connectors, and official documentation to gather evidence and perform the work.

Only one top-level process owns a task. Domain skills refine execution but cannot replace that process. Repository tools provide evidence and actions; they do not choose the workflow.

## Hybrid Enforcement Policy

Skill routing is required for ambiguous feature design, unexplained bugs, security-sensitive changes, formal reviews or audits, and completion verification. It is recommended for ordinary implementation, tests, documentation, and GitHub work.

A task may bypass orchestration only when it is a clearly mechanical, single-file change that affects no runtime behavior, public interface, infrastructure, security posture, or architecture. The bypass still requires a proportionate validation command. Use `gsd-fast` instead when GSD tracking is desired.

## Process Layer

### GSD: macro-orchestration

GSD owns project roadmaps, milestone and phase state, research, phase decisions, executable phase plans, isolated execution, formal audits, and user acceptance:

| Situation | Route |
|---|---|
| Existing project; next action unclear | `gsd-progress` or `gsd-progress --do "task description"` |
| New roadmap or milestone | `gsd-new-project` or `gsd-new-milestone` |
| Phase-level decisions | `gsd-discuss-phase` |
| Research and verified phase plan | `gsd-plan-phase` |
| Approved phase execution | `gsd-execute-phase` |
| Bounded change needing GSD guarantees | `gsd-quick` |
| Mechanical task under two minutes | `gsd-fast` |
| Persistent or context-heavy investigation | `gsd-debug` |
| Formal phase review | `gsd-code-review` |
| Threat-mitigation audit | `gsd-secure-phase` |
| Conversational UAT | `gsd-verify-work` |
| Cross-phase milestone verification | `gsd-audit-milestone` |
| Code-verified documentation refresh | `gsd-docs-update` |

### Superpowers: micro-implementation

Inside a GSD-owned implementation task, use these focused disciplines as applicable:

- `superpowers:test-driven-development` for behavior-changing code
- `superpowers:systematic-debugging` for a focused, reproducible failure
- `superpowers:verification-before-completion` before success claims
- `superpowers:requesting-code-review` after meaningful implementation
- `superpowers:receiving-code-review` when acting on review feedback

For bounded work intentionally outside GSD, Superpowers may own the complete lifecycle: `superpowers:brainstorming` → `superpowers:writing-plans` → `superpowers:executing-plans` → verification → branch completion.

### Conflict boundaries

An active GSD lifecycle owns specifications, plans, task dispatch, phase state, and completion gates. Do not nest Superpowers `brainstorming`, `writing-plans`, or `executing-plans` inside a planned GSD phase. If a GSD task is under-specified, update or rerun the GSD workflow rather than creating a competing plan.

Use `gsd-debug` for investigations requiring persistent state or context isolation; otherwise use `systematic-debugging`. Use `gsd-code-review` for a formal phase artifact and `requesting-code-review` for an implementation checkpoint. Use the active orchestrator's isolation mechanism instead of stacking worktree systems.

## Domain Layer

Initially document only specialists relevant to the current repository:

- `github:github` for general GitHub operations
- `github:gh-fix-ci` for observed CI failures
- `github:gh-address-comments` for pull-request feedback

GSD security, review, and documentation skills remain in the process layer because they own workflows and artifacts. There is no installed Terraform/Azure/Cloudflare or general Python specialist; agents must not pretend otherwise. UI, AI, and rich-artifact routes are intentionally deferred until those domains enter the repository.

## Repository Tools and Facts

Use evidence in this order:

1. `graphify query`, `graphify path`, or `graphify explain` when `graphify-out/graph.json` exists
2. `graphify-out/wiki/index.md` for broad navigation
3. Relevant source files, ADRs, architecture documentation, runbook sections, and workflows
4. Scoped repository commands
5. Task-relevant MCP connectors and current official documentation
6. Broad repository search only when the graph is missing, stale, or insufficient

Do not start a full graph build implicitly because semantic extraction may incur cost. After code changes, update an existing graph with `graphify update .`. Documentation, PDF, or image changes may require an explicitly requested fuller rebuild.

The handbook must preserve these facts:

- The reconciler uses Python 3.11+ (`pyproject.toml` `requires-python`), uv, pytest, and Ruff. Tests run offline without cloud credentials.
- Terraform 1.9+ configurations have separate bootstrap, Azure lab, and Cloudflare state roots.
- Azure DNS Private Resolver is cost-gated and cannot be enabled without approval.
- A Terraform plan is a review artifact; validation does not authorize apply.
- Secrets, keys, WireGuard configuration, Terraform state, and plan files are never committed.
- `docs/decisions.md`, `docs/architecture.md`, and `docs/runbook.md` are authoritative context.

## Completion Matrix

| Change | Minimum evidence |
|---|---|
| Python | Targeted pytest, full `uv run pytest -q`, and Ruff |
| Terraform | Format check, initialization and validation in the affected root, tflint, and Checkov when available |
| GitHub workflow | YAML review and relevant local checks; inspect actual CI with `gh-fix-ci` when failing |
| Documentation | Verify paths, links, commands, and consistency with live code |
| Code with an existing graph | `graphify update .` after validation |

Unavailable checks must be reported, not presented as passing. External MCP writes require the authority implied by the user's request.

## Scenario Recipes

**Feature or infrastructure work:** Route through GSD, load a current specialist if relevant, gather context with graphify and authoritative documents, use TDD for code tasks, run repository checks, complete verification/review gates, then update the graph.

**Bug or CI failure:** Choose focused systematic debugging or persistent `gsd-debug`, load `gh-fix-ci` when applicable, trace the affected concepts, reproduce the failure, add a regression test, verify, and request review for meaningful changes.

**Audit or review:** Choose the matching GSD audit, use graphify and repository checks as evidence, report findings without edits unless fixes were requested, and rerun the audit after authorized fixes.

**Trivial change:** Use `gsd-fast` when tracking is useful; otherwise apply the bypass and run a scoped check.

## Success Criteria

- An agent can choose one owning workflow without reading every installed skill.
- GSD and Superpowers do not produce competing plans for the same work.
- Domain skills are loaded only when relevant and available.
- Graphify and scoped inspection precede broad repository searches.
- Validation is proportionate, evidence-based, and respects infrastructure, secret, and cost boundaries.
- `AGENTS.md` reliably points agents to `SKILLS.md` without duplicating the full handbook.
