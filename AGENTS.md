@SKILLS.md

# Repository Guidelines

## Skill Routing

Before non-trivial work, read `SKILLS.md` and select the process, domain, and repository-tool layers in that order. Do not combine competing orchestrators. Explicit user skill requests take precedence.

## Project Structure & Module Organization

This repository models a hybrid DNS/DDI lab. Under `terraform/`, reusable infrastructure is in `modules/`, the Azure lab root is `envs/lab/`, state setup is in `bootstrap/`, and Cloudflare has a separate configuration in `cloudflare/`. The Python reconciler is in `ddi-reconciler/`, with implementation in `src/`, adapters in `providers/`, and tests in `tests/`. Keep architecture and operational guidance in `docs/`; `spatium/` contains local SpatiumDDI notes.

## Build, Test, and Development Commands

- `cd ddi-reconciler && uv sync --dev` installs Python 3.11+ dependencies from `uv.lock` (`pyproject.toml` requires ≥3.11 — `tomllib`).
- `uv run pytest -q` runs the reconciler test suite.
- `uv run ruff check .` checks Python style and import ordering.
- `terraform fmt -recursive` formats every Terraform file; use `terraform fmt -check -recursive` before submitting.
- From `terraform/envs/lab`, run `terraform init` and `terraform validate` for the main lab configuration.
- Terraform linting, from the repository root:

  ```bash
  export TFLINT_CONFIG_FILE="$PWD/terraform/.tflint.hcl"
  cd terraform && tflint --init && tflint --recursive
  ```

  The export is not optional. `--recursive` re-runs tflint inside each
  directory and each child run looks for its own config, so without it the
  azurerm ruleset never loads in `envs/lab` or `modules/*` and the lint passes
  without having checked anything — while CI, which does set it, fails on
  rules you had no local way to see. CI also runs Checkov security scans.

Run `terraform plan`, inspect the output, and avoid applying infrastructure merely to verify a code change.

## Coding Style & Naming Conventions

Use four spaces for Python and Ruff-compatible conventions: `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants. Keep provider behavior in `providers/` and reconciliation logic independent of cloud SDKs. Format Terraform with `terraform fmt`; use lowercase `snake_case` for resources, variables, and outputs. Follow module file names such as `main.tf`, `variables.tf`, and `outputs.tf`.

## Testing Guidelines

Pytest is the test framework. Name files `test_*.py` and tests `test_*`; place them under `ddi-reconciler/tests/`. Test validation, diff behavior, CLI modes, and provider boundaries. The same suite also hosts the repository's structural contract pins — properties that live outside the reconciler's own code, such as workflow YAML gates (`test_workflow_gates.py`) and Terraform structure (`test_terraform_structure.py`) — because it is the only pytest suite CI runs on every PR. Tests must run without network access, cloud credentials, or Azure login. No coverage threshold is configured, so behavioral changes should include regression tests.

## Commit & Pull Request Guidelines

History uses short, imperative summaries (for example, `changed project name`); keep subjects concise and describe one logical change per commit. Pull requests should explain intent, list validation commands, link relevant issues or ADRs, and include Terraform plan excerpts when infrastructure changes. Add screenshots only for rendered documentation or UI changes.

## Security & Cost Controls

Never commit `.env`, `terraform.tfvars`, `*.auto.tfvars`, state/plan files, private keys, or WireGuard configuration. Use OIDC and repository secrets as established in `.github/workflows/`. Cost-heavy DNS Private Resolver resources are flag-gated; do not enable or apply them without explicit approval.

## graphify

This project has a graphify knowledge graph at `graphify-out/`.

Rules:
- For codebase / architecture questions, first run `graphify query "<question>"` when `graphify-out/graph.json` exists.
  Use `graphify path "<A>" "<B>"` for relationships between two concepts and `graphify explain "<concept>"` for a focused node + its connections.
  These return a scoped subgraph (usually much smaller than GRAPH_REPORT.md or raw grep).
- If `graphify-out/wiki/index.md` exists, use it for broad navigation instead of raw source browsing.
- Read `graphify-out/GRAPH_REPORT.md` only for high-level architecture review (god nodes, surprising connections) or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost). Prefer this over a full rebuild unless docs/PDFs/images also changed.
- Do not fall back to broad Grep/Glob of the whole repo until the graph tools have been tried (or the graph is missing/stale).
