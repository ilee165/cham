# Smell remediation plan — Primitive Obsession + Opaque Comprehension

**Source:** standards-axis review of `7c853aa...HEAD` (2026-08-15), findings 4
and 5. Items 1–3 (Duplicated Code) were resolved by PR #32. This plan covers
the two remaining judgement-call smells. Executed 2026-08-15, landed as
PR #33; the invariant-guard fix-up from PR #33's own review followed.

**Nature of the work:** pure refactor. Neither finding is a defect; both are
readability/shape debts wrapped around security-critical logic (CR-02
pagination fail-closed, CR-04 type-conflict refusal). That inverts the usual
TDD rule: the existing regression suites ARE the spec, and the strongest
evidence of correctness is that **the refactor commits change zero test
files** while every existing test stays green.

## Global constraints

- **Zero observable behavior change.** Same exceptions, same messages, same
  fail-closed decisions, same wire traffic. Any test edit inside a refactor
  commit is a red flag that behavior moved — split it out or stop.
- No weakening of a fail-closed property (standing repo rule). The CR-02
  malformed-latch and CR-04 refusal semantics are load-bearing.
- Branch `refactor/smell-remediation`, one PR, atomic commit per finding,
  through the normal gate. Public-repo rules apply (no secrets in fixtures).

## Task P1 — Primitive Obsession in `spatium.py` pagination parsing

**Current shape:** `_first_int_field` returns
`tuple[tuple[str, int] | None, bool]`, `_first_int` (a Middle Man that
delegates and drops the key) narrows it to `tuple[int | None, bool]`, and
`_next_url` threads four parallel `bad_pages/bad_page/bad_size/bad_offset`
booleans it ORs into one `malformed`. The tri-state semantics
(*found/absent/malformed*, malformed poisons the lot) live in comments, not
in a type.

- [x] **P1.1: introduce the result type.** A small frozen dataclass in
  `spatium.py` (module-private; it is provider-adapter vocabulary, not model
  vocabulary):

  ```python
  @dataclass(frozen=True, slots=True)
  class _FieldLookup:
      """Tri-state pagination-metadata lookup (CR-02): found/absent/malformed.

      `malformed` poisons the lot — a later alias must not restore what a
      malformed earlier key forfeited. The key travels with the value because
      a page-size echoed into the next request must reuse the name this
      deployment answers to.
      """
      key: str | None
      value: int | None
      malformed: bool
      # constructors: found(key, value) / absent() / malformed_()
  ```

  New unit tests for the type itself (new code ⇒ new tests is allowed and
  required): the three states are mutually exclusive; `found` carries key and
  value; `malformed` carries neither.
- [x] **P1.2: migrate `_first_int_field` to return `_FieldLookup`; delete
  `_first_int`.** Callers read `.value` / `.key` / `.malformed` directly —
  the Middle Man dissolves instead of being wrapped. Docstring semantics move
  onto the type; call-site comments that restate them are deleted, not
  duplicated.
- [x] **P1.3: collapse `_next_url`'s boolean plumbing.** The four `bad_*`
  locals become `lookups = [...]` and
  `malformed = any(l.malformed for l in lookups)`. The function's return
  contract `(next_url | None, malformed)` is consumed by the fetch loop's
  latch and stays UNCHANGED in this pass — widening the refactor into the
  latch loop trades a contained change for a risky one with no smell left to
  pay for it.
- [x] **P1.4: evidence gate (see Testing evidence).**

## Task P2 — Opaque comprehension in `runner.py` `_check_type_conflicts`

**Current shape:** the `edge_conflicts` comprehension smuggles two
let-bindings through single-element-list `for` clauses
(`for observed in [observed_by_owner.get(...)]`,
`for others in [{...}]`) — the hardest-to-read six lines of a CR-04 refusal
path that exists to be auditable.

- [x] **P2.1: rewrite as a plain loop.** Same variables, same names, same
  message format, then one `sorted()` at the end:

  ```python
  edge_conflicts = []
  for record in desired:
      observed = observed_by_owner.get((record.zone, record.name), set())
      if record.rtype in observed:
          continue
      others = {rtype for rtype in observed if "CNAME" in (rtype, record.rtype)}
      if others:
          edge_conflicts.append(
              f"{record.zone}/{record.name}: desired {record.rtype} vs edge "
              f"{' and '.join(sorted(others))}")
  edge_conflicts.sort()
  ```

  The docstring (which is good) stays byte-identical. Note `sorted()` on the
  generator becomes an explicit `.sort()` — same ordering, pinned by the
  multi-conflict message tests.
- [x] **P2.2: evidence gate (see Testing evidence).**

## Testing evidence — what proves what

1. **Test-file immutability.** `git diff --stat` of each refactor commit
   shows zero lines changed under `tests/` except the NEW `_FieldLookup`
   unit tests (which land in their own hunk and touch no existing test).
   This is the primary proof that behavior did not move: the CR-02 suite
   (fractional totals, alias fall-through, cross-page latching, the review's
   exact repro) and the CR-04 suite (CNAME→A / A→CNAME under both ownership
   configs, blocked/unparseable-key conflicts, truth-side CNAME+A) were
   written against the pre-refactor code and pass unmodified against the
   post-refactor code.
2. **Guard-still-guards mutations** (run red, then restore — same discipline
   as every prior wave):
   - P1: make `_parse_count` accept floats via `int(value)` truncation → the
     CR-02 tests must go red (proves the suite still detects the original
     defect through the new type).
   - P1: make `_FieldLookup` treat malformed-then-valid-alias as found → the
     `{"total": 1.9, "count": 1}` test must go red (proves the poison
     semantics survived the move into the type).
   - P2: drop `blocked_keys`/`unparseable_keys` from the observed set at the
     call site → the hidden-conflict CR-04 tests must go red.
   - P2: gate updates as well as creates (`record.rtype in observed` check
     removed) → the cleanly-convergent-plan tests must go red.
3. **Full gates:** `uv run pytest -q` (457+ tests) green, `uv run ruff
   check .` clean, both before and after each commit.
4. **No-wire-change spot check:** the CR-02 tests already assert on request
   URLs/params via mocked HTTP; their passing unchanged is the proof that
   the `key` handed back by `_FieldLookup` still reaches the next-page query
   under the deployment's own parameter name.

## Exit criteria

1. `_first_int` no longer exists; exactly one tri-state type carries the
   found/absent/malformed semantics, and no `tuple[... , bool]` malformed
   plumbing remains in `spatium.py` pagination helpers.
2. `_check_type_conflicts` contains no single-element-list `for`-binding;
   the refusal logic reads as a plain loop with the same docstring.
3. Every existing CR-02 and CR-04 regression test passes without
   modification; refactor commits touch no existing test file.
4. All four guard-still-guards mutations verified red then restored green.
5. Full suite + ruff green; PR through the gate; no direct push to main.
6. Follow-up honesty check: if any step forces a test edit or a message
   change, stop and re-review — that is a behavior change, and this plan
   does not authorize one.
