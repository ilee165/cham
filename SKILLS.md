# Repository Skill Routing

## Purpose and Precedence

Use this handbook to choose skills before building, improving, fixing, reviewing, or auditing cham. It is a routing guide, not an exhaustive catalog of installed skills.

Follow instructions in this order: system and user instructions, `AGENTS.md`, this handbook, then the selected skill's instructions. An explicitly requested skill takes precedence when it is available. Load only the skills needed for the current task.

## Order of Operations

For non-trivial work, choose layers in this order:

1. **Process:** Select GSD or Superpowers to own the workflow.
2. **Domain:** Load the smallest matching specialist set.
3. **Repository tools and facts:** Gather evidence with graphify, project documents, scoped commands, MCP connectors, and official documentation.

Only one top-level process may own a task. Domain skills refine execution but do not replace the process. Repository tools supply evidence and actions; they do not decide the workflow.

## Hybrid Policy

Skill routing is required for ambiguous feature design, unexplained failures, security-sensitive changes, formal reviews or audits, and completion verification. It is recommended for ordinary implementation, test additions, documentation, and GitHub work.

A task may bypass orchestration only when it is a clearly mechanical, single-file edit that changes no runtime behavior, public interface, infrastructure, security posture, or architecture. The bypass still requires a proportionate check. Use `gsd-fast` instead when GSD tracking is useful.

## Layer 1: Process Orchestration

### GSD Macro-Orchestration

Use GSD for roadmaps, milestones, phase gates, research, context isolation, formal artifacts, and cross-cutting work.

| Situation | Skill |
|---|---|
| Existing project; next action is unclear | `gsd-progress` or `gsd-progress --do "task description"` |
| Establish a roadmap or milestone | `gsd-new-project` or `gsd-new-milestone` |
| Resolve phase-level decisions | `gsd-discuss-phase` |
| Research and create a verified phase plan | `gsd-plan-phase` |
| Execute an approved phase | `gsd-execute-phase` |
| Complete a bounded change with GSD guarantees | `gsd-quick` |
| Perform a mechanical task under two minutes | `gsd-fast` |
| Run a persistent or context-heavy investigation | `gsd-debug` |
| Produce a formal phase quality review | `gsd-code-review` |
| Verify threat mitigations | `gsd-secure-phase` |
| Perform conversational acceptance testing | `gsd-verify-work` |
| Verify integration across a milestone | `gsd-audit-milestone` |
| Refresh documentation against live code | `gsd-docs-update` |

Start with `gsd-progress` when a GSD project is already active and routing is uncertain. Preserve the gates and artifacts of whichever GSD workflow owns the task.

### Superpowers Micro-Implementation

Within an active GSD implementation task, load compatible Superpowers disciplines as needed:

- `superpowers:test-driven-development` for behavior-changing code.
- `superpowers:systematic-debugging` for a focused, reproducible failure.
- `superpowers:verification-before-completion` before claiming success.
- `superpowers:requesting-code-review` after meaningful implementation.
- `superpowers:receiving-code-review` when evaluating and applying review feedback.

For bounded work intentionally outside GSD, Superpowers may own the complete lifecycle:

`superpowers:brainstorming` → `superpowers:writing-plans` → `superpowers:executing-plans` → `superpowers:verification-before-completion` → `superpowers:finishing-a-development-branch`.

Use `superpowers:using-git-worktrees` when the standalone workflow needs isolation and the user has not directed work to the current branch.

### Conflict Rules

- An active GSD lifecycle owns specifications, plans, task dispatch, phase state, commits, and completion gates.
- Do not nest Superpowers `brainstorming`, `writing-plans`, or `executing-plans` inside a planned GSD phase.
- If a GSD task is under-specified, update or rerun the GSD discussion or planning workflow. Do not create a parallel plan.
- Choose `gsd-debug` for investigations needing persistent state or context isolation; otherwise choose `superpowers:systematic-debugging`.
- Choose `gsd-code-review` for a formal phase artifact and `superpowers:requesting-code-review` for an implementation checkpoint.
- Use the active orchestrator's isolation mechanism instead of stacking worktree or workspace systems.
- Do not invoke another skill merely because its name resembles the active workflow.

## Layer 2: Domain Specialists

Current repository work has these specialist routes:

| Task | Skill |
|---|---|
| General GitHub repository, issue, pull-request, or workflow operation | `github:github` |
| Diagnose and repair an observed CI failure | `github:gh-fix-ci` |
| Evaluate and address pull-request review comments | `github:gh-address-comments` |

Use the minimum matching set. GitHub skills do not authorize pushes, comments, merges, or other external writes beyond the user's request.

There is no installed Terraform/Azure/Cloudflare specialist or general Python specialist. For those domains, combine the selected process with repository evidence, local validation, and current official provider documentation. Do not invent a skill or silently install a plugin.

## Layer 3: Repository Tools and Facts

### Evidence Order

1. When `graphify-out/graph.json` exists, run `graphify query "question"` for codebase and architecture questions. Use `graphify path "A" "B"` for relationships and `graphify explain "concept"` for a focused node.
2. Use `graphify-out/wiki/index.md` for broad navigation when it exists.
3. Read `graphify-out/GRAPH_REPORT.md` only for high-level architecture review or when scoped graph commands are insufficient.
4. Inspect relevant source files, `docs/decisions.md`, `docs/architecture.md`, `docs/runbook.md`, and affected workflows.
5. Run scoped repository commands.
6. Use task-relevant MCP connectors and current official documentation for external facts or systems.
7. Use broad repository search only when the graph is missing, stale, or insufficient.

Do not start a full graph build implicitly because semantic extraction may incur cost. After modifying code, run `graphify update .` when an existing graph is present. Documentation, PDF, or image changes may require an explicitly requested fuller rebuild. When the graph is absent, use scoped `rg` queries and report that graph maintenance was skipped.

Use GitHub connectors only for GitHub state placed in scope. Use context-mode for large command output or source analysis. Prefer primary, official sources for current Terraform, Azure, Cloudflare, Python, and dependency behavior.

### Project Facts

- `ddi-reconciler/` targets Python 3.10+ and uses uv, pytest, Ruff-compatible style, and Hatchling.
- Reconciler tests must run without network access, Azure login, or Cloudflare credentials.
- `terraform/bootstrap`, `terraform/envs/lab`, and `terraform/cloudflare` are separate Terraform roots with distinct state concerns.
- Terraform configurations require version 1.9 or newer.
- Azure DNS Private Resolver is cost-gated. Do not enable or apply it without explicit approval.
- A Terraform plan is a review artifact. Never run `terraform apply` merely to validate a change.
- Never commit `.env`, `terraform.tfvars`, `*.auto.tfvars`, state or plan files, private keys, or WireGuard configuration.
- Treat `docs/decisions.md`, `docs/architecture.md`, and `docs/runbook.md` as authoritative repository context, then verify claims against live code.

Common local commands:

```powershell
cd ddi-reconciler
uv sync --dev
uv run pytest -q
uv run ruff check .

terraform fmt -check -recursive
checkov -d terraform

cd terraform/envs/lab
terraform init
terraform validate
tflint --init
tflint --recursive
```

Run Terraform initialization, validation, and planning from the affected root. Inspect plans before reporting them; do not expose sensitive values in logs or review comments.

### Validation Matrix

| Change | Minimum evidence |
|---|---|
| Python | Targeted pytest, full `uv run pytest -q`, and `uv run ruff check .` |
| Terraform | `terraform fmt -check -recursive`, initialization and validation in the affected root, tflint, and Checkov when available |
| GitHub workflow | YAML review plus relevant local checks; inspect actual CI with `github:gh-fix-ci` when it is failing |
| Documentation | Verify paths, links, commands, and consistency with live code |
| Code with an existing graph | Run `graphify update .` after other validation |

Run targeted checks first, then the broader relevant suite. A failed pre-existing baseline must be reported separately from regressions caused by the current change.

## Task Recipes

### Feature or Infrastructure Work

1. Route through GSD progress, discussion, planning, and execution when the work is phase-sized or cross-cutting.
2. Load a current domain specialist only when it matches the task.
3. Query graphify and inspect authoritative project documents.
4. Use `superpowers:test-driven-development` within behavior-changing code tasks.
5. Run the validation matrix, `superpowers:verification-before-completion`, and the appropriate GSD review or UAT gate.
6. Update an existing graph after code changes.

### Bug or CI Failure

1. Choose `superpowers:systematic-debugging`; escalate to `gsd-debug` when persistent state or context isolation is needed.
2. Load `github:gh-fix-ci` when the evidence is in GitHub CI.
3. Use graphify to trace affected concepts, reproduce the failure, and add a regression test before changing behavior.
4. Verify the fix and request review for meaningful changes.

### Audit or Review

1. Select `gsd-code-review`, `gsd-secure-phase`, or `gsd-audit-milestone` according to scope.
2. Use graphify and repository checks as evidence.
3. Report findings without modifying code unless fixes were explicitly requested.
4. After authorized fixes, rerun the relevant audit or review.

### Trivial Change

Use `gsd-fast` when state tracking is helpful. Otherwise apply the orchestration bypass, inspect only the affected file, make the mechanical edit, and run a proportionate check.

## Failure and Fallback Rules

- If a routed skill is unavailable, say so and use the closest safe workflow. Do not claim the skill ran.
- If graphify is missing or stale, use scoped source inspection and state the limitation.
- If a validation tool or credential is unavailable, report the skipped check and never present it as passing.
- If a canonical baseline already fails, distinguish that failure from current changes and obtain direction when it blocks meaningful verification.
- If process skills conflict, stop and retain the single workflow selected at the process layer.
- External writes, infrastructure changes, destructive actions, and cost-bearing operations require authority from the user's request.
