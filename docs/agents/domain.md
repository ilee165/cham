# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, if it exists — the project glossary.
- **`docs/decisions.md`** — this repo's ADR log. Unlike the skills' default
  `docs/adr/` one-file-per-decision layout, all ADRs live in this single file
  as appended sections (ADR-001 through ADR-008 at the time of setup). Read
  the ADR sections that touch the area you're about to work in.

If `CONTEXT.md` doesn't exist, **proceed silently**. Don't flag its absence; don't suggest creating it upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates it lazily when terms or decisions actually get resolved.

## File structure

Single-context repo:

```
/
├── CONTEXT.md            ← created lazily by /domain-modeling
├── docs/decisions.md     ← ADR log, one appended section per ADR
├── ddi-reconciler/
└── terraform/
```

New ADRs are appended to `docs/decisions.md` as `ADR-009`, `ADR-010`, …,
following the format of the existing entries — do not create `docs/adr/`.
Like every doc change in this repo, ADR edits land through a PR, never a
direct push to `main`.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-008 (truth-only DNS group) — but worth reopening because…_
