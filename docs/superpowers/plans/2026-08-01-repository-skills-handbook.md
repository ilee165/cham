# Repository Skills Handbook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a repository-local skill-routing handbook and make `AGENTS.md` load it before non-trivial work.

**Architecture:** `SKILLS.md` is the single source of truth for workflow routing, specialist selection, repository tools, and completion evidence. `AGENTS.md` imports it and keeps only a concise discovery rule alongside existing repository invariants and graphify instructions.

**Tech Stack:** Markdown, PowerShell validation, Git

## Global Constraints

- Select skills in this order: process, domain specialist, repository tools and facts.
- GSD owns macro planning and phase lifecycle; compatible Superpowers disciplines operate within GSD implementation tasks.
- Do not create parallel GSD and Superpowers plans for the same task.
- Initially route only domain specialists relevant to the current repository; defer UI, AI, and rich-artifact routes.
- Prefer graphify before broad repository search when an existing graph is available.
- Never apply infrastructure merely to validate a change, expose secrets, or enable cost-gated resources without approval.
- Preserve unrelated and pre-existing worktree changes.

---

### Task 1: Create the Repository Skill-Routing Handbook

**Files:**
- Create: `SKILLS.md`
- Reference: `docs/superpowers/specs/2026-08-01-repository-skills-handbook-design.md`

**Interfaces:**
- Consumes: the approved routing hierarchy, hybrid enforcement policy, conflict boundaries, active specialist list, graphify policy, repository facts, and completion matrix from the design specification
- Produces: a self-contained handbook imported by `AGENTS.md` and readable without the design specification

- [ ] **Step 1: Confirm the handbook does not already exist**

Run:

```powershell
Test-Path -LiteralPath SKILLS.md
```

Expected: `False`.

- [ ] **Step 2: Create `SKILLS.md` with the approved structure**

Write these sections in order:

```markdown
# Repository Skill Routing

## Purpose and Precedence
## Order of Operations
## Hybrid Policy
## Layer 1: Process Orchestration
### GSD Macro-Orchestration
### Superpowers Micro-Implementation
### Conflict Rules
## Layer 2: Domain Specialists
## Layer 3: Repository Tools and Facts
### Evidence Order
### Project Facts
### Validation Matrix
## Task Recipes
### Feature or Infrastructure Work
### Bug or CI Failure
### Audit or Review
### Trivial Change
## Failure and Fallback Rules
```

Use exact installed skill identifiers. Include the approved GSD routing table. Permit these Superpowers skills inside GSD tasks: `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `superpowers:verification-before-completion`, `superpowers:requesting-code-review`, and `superpowers:receiving-code-review`. Restrict the standalone `brainstorming` → `writing-plans` → `executing-plans` lifecycle to work outside active GSD management.

List only `github:github`, `github:gh-fix-ci`, and `github:gh-address-comments` as current domain specialists. State that there is no installed Terraform/Azure/Cloudflare or general Python specialist. Do not add UI, AI, document, PDF, presentation, spreadsheet, image, or Firecrawl routing.

Include graphify query/path/explain and wiki behavior, scoped inspection before broad search, authoritative project documents, current repository commands, infrastructure safety, offline test requirements, and the approved validation matrix. State that an unavailable skill or check must be reported rather than fabricated.

- [ ] **Step 3: Validate required sections and routes**

Run:

```powershell
$text = Get-Content -LiteralPath SKILLS.md -Raw
$required = @(
  '# Repository Skill Routing',
  '## Order of Operations',
  '### GSD Macro-Orchestration',
  '### Superpowers Micro-Implementation',
  '### Conflict Rules',
  '## Layer 2: Domain Specialists',
  '## Layer 3: Repository Tools and Facts',
  '## Task Recipes',
  'superpowers:test-driven-development',
  'github:gh-fix-ci',
  'graphify query',
  'terraform fmt -check -recursive',
  'uv run pytest -q'
)
$missing = $required | Where-Object { -not $text.Contains($_) }
if ($missing) { throw "Missing handbook content: $($missing -join ', ')" }
```

Expected: no output and exit code 0.

- [ ] **Step 4: Check deferred routes and placeholders are absent**

Run:

```powershell
$text = Get-Content -LiteralPath SKILLS.md -Raw
$forbidden = @('TBD', 'TODO', 'frontend-design', 'openai-docs', 'documents:documents', 'pdf:pdf', 'presentations:Presentations', 'spreadsheets:Spreadsheets')
$found = $forbidden | Where-Object { $text.Contains($_) }
if ($found) { throw "Unexpected handbook content: $($found -join ', ')" }
```

Expected: no output and exit code 0.

- [ ] **Step 5: Commit the handbook**

```powershell
git add -- SKILLS.md
git commit -m "add repository skill routing handbook"
```

### Task 2: Integrate the Handbook with Agent Instructions

**Files:**
- Modify: `AGENTS.md:1`
- Test: `AGENTS.md`, `SKILLS.md`

**Interfaces:**
- Consumes: `SKILLS.md` as the detailed routing source
- Produces: an import and concise non-trivial-work rule that reliably sends agents to the handbook without duplicating it

- [ ] **Step 1: Confirm the discovery hook is absent**

Run:

```powershell
Select-String -LiteralPath AGENTS.md -SimpleMatch '@SKILLS.md'
```

Expected: no matches.

- [ ] **Step 2: Add the import and routing rule near the top of `AGENTS.md`**

Make the opening exactly:

```markdown
@SKILLS.md

# Repository Guidelines

## Skill Routing

Before non-trivial work, read `SKILLS.md` and select the process, domain, and repository-tool layers in that order. Do not combine competing orchestrators. Explicit user skill requests take precedence.
```

Keep all existing repository guideline and graphify sections after this addition.

- [ ] **Step 3: Validate discovery and avoid duplicated routing**

Run:

```powershell
$agents = Get-Content -LiteralPath AGENTS.md -Raw
if (-not $agents.StartsWith("@SKILLS.md")) { throw 'AGENTS.md must begin with @SKILLS.md' }
if (($agents.Split('@SKILLS.md').Count - 1) -ne 1) { throw 'SKILLS.md import must appear exactly once' }
if (-not $agents.Contains('Do not combine competing orchestrators.')) { throw 'Missing conflict rule' }
if (-not $agents.Contains('## graphify')) { throw 'Existing graphify rules were lost' }
```

Expected: no output and exit code 0.

- [ ] **Step 4: Run final documentation checks**

Run:

```powershell
$paths = @('SKILLS.md', 'AGENTS.md', 'docs/superpowers/specs/2026-08-01-repository-skills-handbook-design.md')
$missing = $paths | Where-Object { -not (Test-Path -LiteralPath $_) }
if ($missing) { throw "Missing documentation: $($missing -join ', ')" }
git diff --check -- AGENTS.md SKILLS.md
```

Expected: no missing files and no whitespace errors.

- [ ] **Step 5: Handle graph maintenance proportionately**

Run:

```powershell
Test-Path -LiteralPath graphify-out/graph.json
```

Expected for the current worktree: `False`. Do not start a full graph build implicitly. If this expectation changes and the graph exists, run `graphify update .` and report its result.

- [ ] **Step 6: Commit the agent-instruction integration**

```powershell
git add -- AGENTS.md
git commit -m "route agents through repository skills handbook"
```

- [ ] **Step 7: Verify final repository state**

Run:

```powershell
git status --short
git log -3 --oneline
```

Expected: `AGENTS.md` and `SKILLS.md` are committed. Any unrelated pre-existing untracked files remain untouched.
