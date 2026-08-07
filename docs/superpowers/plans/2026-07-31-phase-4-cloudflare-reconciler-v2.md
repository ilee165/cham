# Phase 4 — Cloudflare + Reconciler v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The public half of the split horizon live on Cloudflare, and a working reconciler that converges both edges (Azure Private DNS, Cloudflare) toward SpatiumDDI truth — never touching records outside its explicit managed set.

**Architecture:** Three tracks. **Track A** (infra): apply `terraform/cloudflare` (separate state per ADR-004), point `www` at a public page, add the internal `www` override in SpatiumDDI, give the hub an internal-only web page — the split-horizon pair. **Track B** (code): repair the broken packaging, then implement config → providers (Spatium read-only truth, Azure edge, Cloudflare edge) → per-edge runner → CLI with a CI-grade exit-code contract, all TDD with zero-credential tests. **Track C** (integration): seed truth records in SpatiumDDI, converge live, prove tamper-healing and ownership safety, run the split-horizon demo. A committed desired-state snapshot (`desired-records.json`) is introduced so Phase 5's nightly CI can detect edge drift without reaching the laptop (new ADR-006).

**Tech Stack:** Python ≥ 3.10 (uv + hatchling), `requests`, `azure-identity`, `azure-mgmt-privatedns`, `pytest` + `responses` (dev), Terraform cloudflare provider ~> 4.x, SpatiumDDI REST API (FastAPI), GitHub Pages (public www target).

## Global Constraints

- Runtime deps exactly: `requests`, `azure-identity`, `azure-mgmt-privatedns`. Dev deps: `pytest`, `responses`. Nothing else without an ADR.
- All unit tests run offline with zero credentials (`responses` for HTTP, injected fake clients for the Azure SDK). This is part of the design story — keep it true.
- Canonical record names are **zone-relative**, `"@"` for the apex. Every adapter converts to/from this form at its boundary. `CanonicalRecord` owns value normalization — adapters never pre-normalize values.
- Providers translate their library/API errors into `RuntimeError` with a readable message; the CLI turns those into exit 1. **Exit-code contract: 0 = converged, 2 = drift found (dry-run), 1 = operational error.** Phase 5's drift workflow depends on this exactly.
- Ownership (ADR-005): the reconciler's managed sets are **disjoint** from Terraform seeds (`db` in Azure, `www`/`external-check` in Cloudflare) and can never touch auto-registered records. `diff_records` already enforces the allowlist; the live tests must prove it.
- Secrets only via env: `SPATIUM_API_TOKEN`, `CLOUDFLARE_API_TOKEN`, `AZURE_SUBSCRIPTION_ID` (+ `az login` / OIDC). `config.toml` is committed and contains no secrets.
- Commit after every green test cycle (per-task commits shown).

## Target File Structure (Track B)

```
ddi-reconciler/
├── pyproject.toml                    # + deps, + wheel packages mapping
├── config.toml                       # committed edge/zone/managed-key config (no secrets)
├── desired-records.json              # committed truth snapshot for CI (Track C)
├── src/ddi_reconciler/
│   ├── __init__.py                   # (moved, unchanged)
│   ├── model.py                      # (moved; key bug + messages fixed)
│   ├── reconcile.py                  # (moved, unchanged)
│   ├── config.py                     # NEW — load config.toml
│   ├── desired_file.py               # NEW — snapshot save/load
│   ├── runner.py                     # NEW — per-edge plan/apply orchestration
│   ├── cli.py                        # REWRITTEN — wiring + exit codes
│   └── providers/
│       ├── __init__.py               # (moved, empty)
│       ├── spatium.py                # IMPLEMENTED — truth, read-only
│       ├── azure.py                  # IMPLEMENTED — edge
│       └── cloudflare.py             # IMPLEMENTED — edge
└── tests/
    ├── test_reconcile.py             # (unchanged — must pass as-is)
    ├── test_config.py                # NEW
    ├── test_desired_file.py          # NEW
    ├── test_runner.py                # NEW
    ├── test_cli.py                   # REWRITTEN
    ├── test_provider_spatium.py      # NEW
    ├── test_provider_azure.py        # NEW
    └── test_provider_cloudflare.py   # NEW
```

## Task Dependency / Parallelism Map

```
Track A (infra)                     Track B (code — no cloud needed)
A1 CF zone + token                  B1 packaging repair + bug fixes
A2 tf edits (www CNAME,             B2 config.py + desired_file.py   [after B1]
   hub nginx, NSG 130)              B3 runner.py                     [after B2]
A3 Spatium www override             B4 cli.py rewrite                [after B3]
A4 apply cloudflare stack           B5 spatium provider  ─┐
   [after A1, A2,                   B6 azure provider     ├─ parallel [after B1;
    Phase 2 Task 3 backend]         B7 cloudflare provider┘  B5 also after B2 imports nothing new]
                                    (B5/B6/B7 independent of B3/B4)
Track A ∥ Track B entirely.
Track C (integration): C1 → C2 → C3   [needs ALL of A and B, plus Phase 2 applied;
                                       C3's browser demo also needs Phase 3 tunnel]
```

---

## Track B — Reconciler implementation

### Task B1: Packaging repair + the three found bugs

The package cannot build (`hatchling: Unable to determine which files to ship`), `CanonicalRecord.key` crashes at runtime, and 21 of 37 tests fail. Fix all of it before writing any new code.

**Files:**
- Move: `src/{__init__,model,reconcile,cli}.py` → `src/ddi_reconciler/`; `providers/` → `src/ddi_reconciler/providers/`
- Modify: `pyproject.toml`, `src/ddi_reconciler/model.py`, `src/ddi_reconciler/cli.py`, `src/ddi_reconciler/providers/azure.py`

**Interfaces:**
- Produces: importable `ddi_reconciler` package; `CanonicalRecord.key` returning a real tuple; error messages matching `tests/test_reconcile.py` exactly. Every later task consumes this.

- [ ] **Step 1: Run the suite to record the baseline failure**

Run: `cd ddi-reconciler && uv run pytest -q`
Expected: FAILS during build — `Unable to determine which files to ship inside the wheel`.

- [ ] **Step 2: Restructure to a real src layout**

```bash
mkdir -p src/ddi_reconciler
git mv src/__init__.py src/ddi_reconciler/__init__.py
git mv src/model.py src/ddi_reconciler/model.py
git mv src/reconcile.py src/ddi_reconciler/reconcile.py
git mv src/cli.py src/ddi_reconciler/cli.py
git mv providers src/ddi_reconciler/providers
```

- [ ] **Step 3: Pin the wheel mapping and dependencies in `pyproject.toml`**

Replace the `dependencies` line and add the wheel table + dev deps:

```toml
[project]
name = "ddi-reconciler"
version = "0.1.0"
description = "Reconciler v2 — converges Azure Private DNS and Cloudflare toward SpatiumDDI truth"
requires-python = ">=3.10"
dependencies = [
  "requests>=2.32",
  "azure-identity>=1.17",
  "azure-mgmt-privatedns>=1.1",
]

[tool.hatch.build.targets.wheel]
packages = ["src/ddi_reconciler"]

[dependency-groups]
dev = ["pytest", "responses>=0.25"]
```

(Keep the existing `[build-system]`, `[project.scripts]`, and ruff sections as they are.)

- [ ] **Step 4: Fix `CanonicalRecord.key` (model.py:89)**

`RecordKey` is a `TypeAlias` for `tuple[str, str, str]`; calling it with three arguments is a runtime `TypeError` ("tuple expected at most 1 argument"). Replace:

```python
    @property
    def key(self) -> RecordKey:
        """Identity key: two records with the same key are the 'same' record
        and diff only in values/ttl (an UPDATE, not ADD and DELETE)"""
        return (self.zone, self.name, self.rtype)
```

- [ ] **Step 5: Align the five validation messages with the test suite (tests are the spec)**

In `src/ddi_reconciler/model.py` `__post_init__`:
- `"zone is required"` → `"zone must not be empty"`
- `"name is required"` → `"name must not be empty"`
- `"rtype is required"` → `"record type must not be empty"`
- `"values are required"` → `"values must not be empty"`
- `"ttl must be a non-negative integer"` → `"TTL must be a non-negative integer"`

- [ ] **Step 6: Clean the two stub blemishes**

- `src/ddi_reconciler/cli.py` docstring: `python -m cham.ddi-reconciler.cli` → `python -m ddi_reconciler.cli`.
- `src/ddi_reconciler/providers/azure.py`: replace the whole file with a clean stub (docstring preserved, importable):

```python
"""Azure Private DNS adapter — reconciled edge for azure.dwsolution.co.

CRITICAL SAFETY: record sets with is_auto_registered=True belong to Azure VM
auto-registration and are dropped at fetch time — combined with the
managed-key allowlist in diff_records they can never be updated or deleted.

Auth: DefaultAzureCredential (az login locally; OIDC-federated in CI).
"""
from ddi_reconciler.model import CanonicalRecord, Diff


class AzureProvider:
    def __init__(self, subscription_id: str, resource_group: str, client=None):
        self.resource_group = resource_group
        self._client = client  # real client construction lands in Task B6

    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        raise NotImplementedError("Task B6")

    def apply(self, diff: Diff) -> None:
        raise NotImplementedError("Task B6")
```

- [ ] **Step 7: Verify green, entry point intact, commit**

Run:
```bash
uv sync
uv run pytest -q
uv run cham-reconcile --dry-run; echo "exit=$?"
```
Expected: `37 passed`; the CLI still prints the not-implemented error and `exit=1`.

```bash
git add -A .
git commit -m "fix(reconciler): src-layout packaging, key-property TypeError, spec-aligned messages"
```

---

### Task B2: `config.py` + `desired_file.py` (+ committed `config.toml`)

*Depends on B1.*

**Files:**
- Create: `ddi-reconciler/config.toml`, `src/ddi_reconciler/config.py`, `src/ddi_reconciler/desired_file.py`, `tests/test_config.py`, `tests/test_desired_file.py`

**Interfaces:**
- Consumes: `canonical_record_key`, `CanonicalRecord` from `ddi_reconciler.model`.
- Produces (exact names later tasks use): `EdgeConfig(name, provider, zone, managed_keys: frozenset[RecordKey])`, `Config(spatium_base_url, azure_resource_group, edges: tuple[EdgeConfig, ...])`, `ConfigError(ValueError)`, `load_config(path) -> Config`; `save_desired(records, path)`, `load_desired(path) -> list[CanonicalRecord]`.

- [ ] **Step 1: Write the committed `ddi-reconciler/config.toml`**

```toml
# Reconciler configuration — NO SECRETS in this file. Identity comes from env:
#   SPATIUM_API_TOKEN, CLOUDFLARE_API_TOKEN, AZURE_SUBSCRIPTION_ID (+ az login/OIDC)
# managed_keys is the ADR-005 ownership allowlist: the reconciler can never
# add, update, or DELETE a record whose (zone, name, type) is not listed here.
# Terraform seeds (db / www / external-check) are deliberately absent.

[spatium]
base_url = "http://localhost:8000"

[azure]
resource_group = "rg-cham-lab"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "azure.dwsolution.co"
managed_keys = [
  ["azure.dwsolution.co", "app", "A"],
]

[[edges]]
name = "cloudflare-public"
provider = "cloudflare"
zone = "dwsolution.co"
managed_keys = [
  ["dwsolution.co", "demo", "CNAME"],
  ["dwsolution.co", "reconciler-check", "TXT"],
]
```

- [ ] **Step 2: Write the failing tests — `tests/test_config.py`**

```python
"""config.toml loading — offline, no secrets."""
import pytest

from ddi_reconciler.config import ConfigError, load_config

VALID = """
[spatium]
base_url = "http://spatium.test:8000/"

[azure]
resource_group = "rg-x"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "Azure.DWSolution.co."
managed_keys = [["azure.dwsolution.co", "APP.", "a"]]
"""


def test_load_valid_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID)
    config = load_config(path)
    assert config.spatium_base_url == "http://spatium.test:8000/"
    assert config.azure_resource_group == "rg-x"
    edge = config.edges[0]
    assert edge.zone == "azure.dwsolution.co"          # normalized
    assert edge.managed_keys == frozenset({("azure.dwsolution.co", "app", "A")})


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml")


def test_unknown_provider_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace('provider = "azure"', 'provider = "route53"'))
    with pytest.raises(ConfigError, match="unknown provider"):
        load_config(path)


def test_no_edges_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[spatium]\nbase_url = 'x'\n")
    with pytest.raises(ConfigError, match="no edges"):
        load_config(path)


def test_repo_config_toml_is_valid():
    from pathlib import Path
    repo_config = Path(__file__).parent.parent / "config.toml"
    config = load_config(repo_config)
    assert {e.name for e in config.edges} == {"azure-private", "cloudflare-public"}
```

Run: `uv run pytest tests/test_config.py -q` — Expected: FAIL (`ModuleNotFoundError: ddi_reconciler.config`).

- [ ] **Step 3: Implement `src/ddi_reconciler/config.py`**

```python
"""Load reconciler configuration (config.toml) — no secrets in the file.

Secrets/identity come from the environment at provider-construction time:
SPATIUM_API_TOKEN, CLOUDFLARE_API_TOKEN, AZURE_SUBSCRIPTION_ID.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ddi_reconciler.model import RecordKey, canonical_record_key


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EdgeConfig:
    name: str
    provider: str  # "azure" | "cloudflare"
    zone: str
    managed_keys: frozenset[RecordKey]


@dataclass(frozen=True)
class Config:
    spatium_base_url: str
    azure_resource_group: str
    edges: tuple[EdgeConfig, ...]


def load_config(path: Path) -> Config:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc

    edges: list[EdgeConfig] = []
    for entry in raw.get("edges", []):
        try:
            edge = EdgeConfig(
                name=entry["name"],
                provider=entry["provider"],
                zone=entry["zone"].strip().rstrip(".").lower(),
                managed_keys=frozenset(
                    canonical_record_key(zone, name, rtype)
                    for zone, name, rtype in entry["managed_keys"]
                ),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"invalid edge entry {entry!r}: {exc}") from exc
        if edge.provider not in {"azure", "cloudflare"}:
            raise ConfigError(f"unknown provider {edge.provider!r} for edge {edge.name!r}")
        edges.append(edge)
    if not edges:
        raise ConfigError("config declares no edges")

    return Config(
        spatium_base_url=raw.get("spatium", {}).get("base_url", "http://localhost:8000"),
        azure_resource_group=raw.get("azure", {}).get("resource_group", "rg-cham-lab"),
        edges=tuple(edges),
    )
```

Run: `uv run pytest tests/test_config.py -q` — Expected: 5 passed.

- [ ] **Step 4: Tests then implementation for the snapshot file — `tests/test_desired_file.py`**

```python
"""Snapshot round-trip — the CI drift mode's data source (ADR-006)."""
import pytest

from ddi_reconciler.desired_file import load_desired, save_desired
from ddi_reconciler.model import CanonicalRecord


def test_round_trip_preserves_records(tmp_path):
    records = [
        CanonicalRecord(zone="dwsolution.co", name="demo", rtype="CNAME",
                        values=("www.dwsolution.co",), ttl=300),
        CanonicalRecord(zone="azure.dwsolution.co", name="app", rtype="A",
                        values=("10.10.4.30",), ttl=300),
    ]
    path = tmp_path / "desired.json"
    save_desired(records, path)
    assert load_desired(path) == sorted(records, key=lambda r: r.key)


def test_snapshot_is_sorted_and_stable(tmp_path):
    a = CanonicalRecord(zone="z.co", name="b", rtype="A", values=("1.1.1.1",))
    b = CanonicalRecord(zone="z.co", name="a", rtype="A", values=("1.1.1.2",))
    p1, p2 = tmp_path / "one.json", tmp_path / "two.json"
    save_desired([a, b], p1)
    save_desired([b, a], p2)
    assert p1.read_text() == p2.read_text()  # committed file must diff cleanly


def test_invalid_record_in_file_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('[{"zone": "z.co", "name": "x", "rtype": "BOGUS", "values": ["v"], "ttl": 300}]')
    with pytest.raises(ValueError, match="unsupported record type"):
        load_desired(path)
```

Implement `src/ddi_reconciler/desired_file.py`:

```python
"""Desired-state snapshot: CanonicalRecords <-> committed JSON file.

Nightly CI cannot reach the laptop's SpatiumDDI API, so sessions export truth
to ddi-reconciler/desired-records.json and drift runs compare edges against
that committed snapshot (ADR-006).
"""
from __future__ import annotations

import json
from pathlib import Path

from ddi_reconciler.model import CanonicalRecord


def save_desired(records: list[CanonicalRecord], path: Path) -> None:
    payload = [
        {"zone": r.zone, "name": r.name, "rtype": r.rtype,
         "values": list(r.values), "ttl": r.ttl}
        for r in sorted(records, key=lambda r: r.key)
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_desired(path: Path) -> list[CanonicalRecord]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [
        CanonicalRecord(zone=e["zone"], name=e["name"], rtype=e["rtype"],
                        values=tuple(e["values"]), ttl=e["ttl"])
        for e in entries
    ]
```

Run: `uv run pytest tests/test_desired_file.py -q` — Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ddi-reconciler/config.toml ddi-reconciler/src/ddi_reconciler/{config,desired_file}.py ddi-reconciler/tests/{test_config,test_desired_file}.py
git commit -m "feat(reconciler): edge config with managed-key allowlist + desired-state snapshot"
```

---

### Task B3: `runner.py` — per-edge plan/apply with post-apply verification

*Depends on B2.*

**Files:**
- Create: `src/ddi_reconciler/runner.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `EdgeConfig`, `diff_records`, `Diff`.
- Produces: `EdgeResult(edge, diff)`, `ConvergenceError(RuntimeError)`, `plan_edge(edge, desired_all, provider) -> EdgeResult`, `apply_edge(edge, desired_all, provider) -> EdgeResult` (returns the pre-apply diff). Provider duck-type contract: `fetch_actual(zones: set[str]) -> list[CanonicalRecord]`, `apply(diff: Diff) -> None`, raising `RuntimeError` on API failure.

- [ ] **Step 1: Write the failing tests — `tests/test_runner.py`**

```python
"""Per-edge orchestration with a fake provider — offline."""
import pytest

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord
from ddi_reconciler.runner import ConvergenceError, apply_edge, plan_edge

Z = "azure.dwsolution.co"
EDGE = EdgeConfig(name="azure-private", provider="azure", zone=Z,
                  managed_keys=frozenset({(Z, "app", "A")}))


def rec(name, value, zone=Z):
    return CanonicalRecord(zone=zone, name=name, rtype="A", values=(value,))


class FakeProvider:
    def __init__(self, actual, stubborn=False):
        self.actual = list(actual)
        self.stubborn = stubborn
        self.apply_calls = 0

    def fetch_actual(self, zones):
        return list(self.actual)

    def apply(self, diff):
        self.apply_calls += 1
        if self.stubborn:
            return
        for r in diff.to_delete:
            self.actual = [a for a in self.actual if a.key != r.key]
        for u in diff.to_update:
            self.actual = [a for a in self.actual if a.key != u.actual.key] + [u.desired]
        self.actual.extend(diff.to_add)


def test_plan_edge_filters_desired_to_managed_set():
    desired_all = [rec("app", "10.10.4.30"), rec("db", "10.10.4.20"),
                   rec("other", "1.2.3.4", zone="unrelated.zone")]
    result = plan_edge(EDGE, desired_all, FakeProvider([]))
    assert [r.name for r in result.diff.to_add] == ["app"]  # db + other filtered out


def test_apply_edge_converges_and_reports_pre_apply_diff():
    provider = FakeProvider([])
    result = apply_edge(EDGE, [rec("app", "10.10.4.30")], provider)
    assert provider.apply_calls == 1
    assert [r.name for r in result.diff.to_add] == ["app"]
    assert plan_edge(EDGE, [rec("app", "10.10.4.30")], provider).diff.is_converged


def test_apply_edge_skips_apply_when_converged():
    provider = FakeProvider([rec("app", "10.10.4.30")])
    apply_edge(EDGE, [rec("app", "10.10.4.30")], provider)
    assert provider.apply_calls == 0


def test_apply_edge_raises_when_still_drifted():
    provider = FakeProvider([], stubborn=True)
    with pytest.raises(ConvergenceError, match="still drifted after apply"):
        apply_edge(EDGE, [rec("app", "10.10.4.30")], provider)
```

Run: `uv run pytest tests/test_runner.py -q` — Expected: FAIL (module missing).

- [ ] **Step 2: Implement `src/ddi_reconciler/runner.py`**

```python
"""Per-edge reconcile pass: filter truth to the edge's managed set, diff, apply.

Provider duck-type contract:
    fetch_actual(zones: set[str]) -> list[CanonicalRecord]
    apply(diff: Diff) -> None
Both raise RuntimeError with a readable message on API failure.
"""
from __future__ import annotations

from dataclasses import dataclass

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord, Diff
from ddi_reconciler.reconcile import diff_records


class ConvergenceError(RuntimeError):
    """apply() ran but a re-fetch still shows drift."""


@dataclass(frozen=True)
class EdgeResult:
    edge: EdgeConfig
    diff: Diff


def plan_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider) -> EdgeResult:
    # Ownership filter: SpatiumDDI may model more records in the zone than the
    # reconciler owns; only the managed subset is desired state for this edge.
    desired = [r for r in desired_all
               if r.zone == edge.zone and r.key in edge.managed_keys]
    actual = provider.fetch_actual({edge.zone})
    diff = diff_records(desired, actual, {edge.zone}, set(edge.managed_keys))
    return EdgeResult(edge=edge, diff=diff)


def apply_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider) -> EdgeResult:
    result = plan_edge(edge, desired_all, provider)
    if result.diff.is_converged:
        return result
    provider.apply(result.diff)
    check = plan_edge(edge, desired_all, provider)
    if not check.diff.is_converged:
        raise ConvergenceError(f"edge {edge.name!r} still drifted after apply")
    return result
```

Run: `uv run pytest tests/test_runner.py -q` — Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add ddi-reconciler/src/ddi_reconciler/runner.py ddi-reconciler/tests/test_runner.py
git commit -m "feat(reconciler): per-edge runner with post-apply convergence check"
```

---

### Task B4: CLI rewrite — wiring, modes, exit-code contract

*Depends on B3. (Providers may still be stubs — tests inject fakes.)*

**Files:**
- Modify: `src/ddi_reconciler/cli.py` (full rewrite)
- Modify: `tests/test_cli.py` (full rewrite — the old fail-closed test is superseded)

**Interfaces:**
- Consumes: `load_config`, `load_desired`/`save_desired`, `plan_edge`/`apply_edge`, provider constructors.
- Produces: `main(argv: list[str] | None = None) -> int`; flags `--dry-run | --apply | --export PATH`, `--config PATH` (default `config.toml`), `--desired-from-file PATH`, `--edge NAME` (repeatable); `_build_providers(config)` (monkeypatch seam for tests and Phase 5 docs); diff line format `[edge] ADD|UPDATE|DELETE name TYPE values ttl=N`.

- [ ] **Step 1: Write the failing tests — `tests/test_cli.py` (replaces the old file)**

```python
"""CLI contract tests — in-process with fake providers, plus one subprocess test."""
import json
import subprocess
import sys

import pytest

from ddi_reconciler import cli
from ddi_reconciler.model import CanonicalRecord

Z = "azure.dwsolution.co"

CONFIG = """
[spatium]
base_url = "http://spatium.invalid"

[azure]
resource_group = "rg-cham-lab"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "azure.dwsolution.co"
managed_keys = [["azure.dwsolution.co", "app", "A"]]
"""


class FakeProvider:
    def __init__(self, actual):
        self.actual = list(actual)
        self.applied = False

    def fetch_actual(self, zones):
        return list(self.actual)

    def apply(self, diff):
        self.applied = True
        self.actual = list(diff.to_add)


@pytest.fixture
def files(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(CONFIG)
    desired = tmp_path / "desired.json"
    desired.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A",
          "values": ["10.10.4.30"], "ttl": 300}]))
    return config, desired


def run_cli(monkeypatch, provider, config, desired, mode):
    monkeypatch.setattr(cli, "_build_providers",
                        lambda cfg: {"azure-private": provider})
    return cli.main([mode, "--config", str(config),
                     "--desired-from-file", str(desired)])


def test_dry_run_drift_exits_2_and_prints_diff(files, monkeypatch, capsys):
    config, desired = files
    assert run_cli(monkeypatch, FakeProvider([]), config, desired, "--dry-run") == 2
    out = capsys.readouterr().out
    assert "[azure-private] ADD    app A 10.10.4.30 ttl=300" in out
    assert "summary: 1 add, 0 update, 0 delete" in out


def test_dry_run_converged_exits_0(files, monkeypatch):
    config, desired = files
    actual = [CanonicalRecord(zone=Z, name="app", rtype="A",
                              values=("10.10.4.30",), ttl=300)]
    assert run_cli(monkeypatch, FakeProvider(actual), config, desired, "--dry-run") == 0


def test_apply_converges_and_exits_0(files, monkeypatch):
    config, desired = files
    provider = FakeProvider([])
    assert run_cli(monkeypatch, provider, config, desired, "--apply") == 0
    assert provider.applied


def test_unknown_edge_filter_is_error(files, monkeypatch, capsys):
    config, desired = files
    monkeypatch.setattr(cli, "_build_providers", lambda cfg: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired), "--edge", "nope"])
    assert code == 1
    assert "unknown edge" in capsys.readouterr().err


def test_missing_desired_file_is_operational_error(files, monkeypatch, capsys):
    config, _ = files
    monkeypatch.setattr(cli, "_build_providers", lambda cfg: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", "does-not-exist.json"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_subprocess_entrypoint_contract():
    result = subprocess.run(
        [sys.executable, "-m", "ddi_reconciler.cli", "--dry-run",
         "--config", "missing-config.toml"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "error:" in result.stderr
```

Run: `uv run pytest tests/test_cli.py -q` — Expected: FAIL (old CLI has no such flags).

- [ ] **Step 2: Rewrite `src/ddi_reconciler/cli.py`**

```python
"""cham-reconcile CLI.

Exit codes (contract used by nightly-drift CI — do not change casually):
  0 — converged (dry-run found no drift, or apply converged)
  1 — operational error (config, network, auth, convergence failure)
  2 — drift found (dry-run only)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ddi_reconciler.config import Config, ConfigError, load_config
from ddi_reconciler.desired_file import load_desired, save_desired
from ddi_reconciler.model import CanonicalRecord, Diff
from ddi_reconciler.runner import ConvergenceError, apply_edge, plan_edge


def _build_providers(config: Config) -> dict:
    """Edge name -> constructed provider. Lazy imports keep file-mode dry-runs
    from paying the Azure SDK import cost. Tests monkeypatch this function."""
    from ddi_reconciler.providers.azure import AzureProvider
    from ddi_reconciler.providers.cloudflare import CloudflareProvider

    providers = {}
    for edge in config.edges:
        if edge.provider == "azure":
            providers[edge.name] = AzureProvider(
                subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
                resource_group=config.azure_resource_group)
        elif edge.provider == "cloudflare":
            providers[edge.name] = CloudflareProvider(
                zone_name=edge.zone,
                api_token=os.environ["CLOUDFLARE_API_TOKEN"])
    return providers


def _fetch_desired(config: Config, args: argparse.Namespace) -> list[CanonicalRecord]:
    if args.desired_from_file:
        return load_desired(Path(args.desired_from_file))
    from ddi_reconciler.providers.spatium import SpatiumProvider
    spatium = SpatiumProvider(base_url=config.spatium_base_url,
                              token=os.environ.get("SPATIUM_API_TOKEN", ""))
    return spatium.fetch_desired({edge.zone for edge in config.edges})


def _print_diff(edge_name: str, diff: Diff) -> None:
    for r in sorted(diff.to_add, key=lambda r: r.key):
        print(f"[{edge_name}] ADD    {r.name} {r.rtype} {','.join(r.values)} ttl={r.ttl}")
    for u in sorted(diff.to_update, key=lambda u: u.desired.key):
        print(f"[{edge_name}] UPDATE {u.desired.name} {u.desired.rtype} "
              f"{','.join(u.actual.values)} ttl={u.actual.ttl} -> "
              f"{','.join(u.desired.values)} ttl={u.desired.ttl}")
    for r in sorted(diff.to_delete, key=lambda r: r.key):
        print(f"[{edge_name}] DELETE {r.name} {r.rtype} {','.join(r.values)} ttl={r.ttl}")
    if diff.is_converged:
        print(f"[{edge_name}] converged (0 changes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cham-reconcile",
        description="Converge DNS edges toward SpatiumDDI truth")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print diff; exit 2 on drift")
    mode.add_argument("--apply", action="store_true", help="apply changes, verify convergence")
    mode.add_argument("--export", metavar="PATH",
                      help="write SpatiumDDI truth snapshot as JSON and exit")
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument("--desired-from-file", metavar="PATH",
                        help="read desired state from a JSON snapshot instead of SpatiumDDI (CI mode)")
    parser.add_argument("--edge", action="append", metavar="NAME",
                        help="limit to named edge(s); repeatable")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))

        if args.export:
            records = _fetch_desired(config, args)
            save_desired(records, Path(args.export))
            print(f"exported {len(records)} records to {args.export}")
            return 0

        edges = config.edges
        if args.edge:
            unknown = set(args.edge) - {e.name for e in edges}
            if unknown:
                raise ConfigError(f"unknown edge(s): {', '.join(sorted(unknown))}")
            edges = tuple(e for e in edges if e.name in set(args.edge))

        desired_all = _fetch_desired(config, args)
        providers = _build_providers(config)

        adds = updates = deletes = 0
        for edge in edges:
            run = apply_edge if args.apply else plan_edge
            result = run(edge, desired_all, providers[edge.name])
            _print_diff(edge.name, result.diff)
            adds += len(result.diff.to_add)
            updates += len(result.diff.to_update)
            deletes += len(result.diff.to_delete)

        drifted = bool(adds or updates or deletes)
        applied = " — applied" if args.apply and drifted else ""
        print(f"summary: {adds} add, {updates} update, {deletes} delete "
              f"across {len(edges)} edge(s){applied}")
        return 2 if (args.dry_run and drifted) else 0
    except (ConfigError, ConvergenceError, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

(`KeyError` covers a missing env var like `CLOUDFLARE_API_TOKEN`; `RuntimeError` is the provider failure contract; `OSError` covers unreadable files.)

- [ ] **Step 3: Run and commit**

Run: `uv run pytest -q` — Expected: all pass (config/desired/runner/cli plus the original 37).

```bash
git add ddi-reconciler/src/ddi_reconciler/cli.py ddi-reconciler/tests/test_cli.py
git commit -m "feat(reconciler): CLI with dry-run/apply/export and 0/2/1 exit contract"
```

---

### Task B5: Spatium provider (truth, read-only)

*Depends on B1. Parallelizable with B3/B4/B6/B7.*

**Files:**
- Modify: `src/ddi_reconciler/providers/spatium.py` (implement)
- Create: `tests/test_provider_spatium.py`

**Interfaces:**
- Produces: `SpatiumProvider(base_url, token)` with `fetch_desired(zones: set[str]) -> list[CanonicalRecord]`. Module constants `ZONES_PATH`, `RECORDS_PATH` are the adjust-here seam for API-shape differences.

**Reality check first:** the endpoint paths below are the expected FastAPI shape. Before trusting them, run `curl -s http://localhost:8000/openapi.json | python3 -m json.tool | grep '"/'` against the running Phase 1 stack and adjust `ZONES_PATH`/`RECORDS_PATH` (and the field names in `_get`/`fetch_desired`) to match — then make the test fixtures mirror the real payloads.

- [ ] **Step 1: Write the failing tests — `tests/test_provider_spatium.py`**

```python
"""Spatium adapter — HTTP mocked with responses; no live stack needed."""
import pytest
import responses

from ddi_reconciler.providers.spatium import SpatiumProvider

BASE = "http://spatium.test"


@responses.activate
def test_fetch_desired_maps_groups_and_filters():
    responses.get(f"{BASE}/api/v1/dns/zones", json=[
        {"id": 1, "name": "azure.dwsolution.co."},
        {"id": 2, "name": "not-wanted.zone"},   # its records URL is never called
    ])
    responses.get(f"{BASE}/api/v1/dns/zones/1/records", json=[
        {"name": "app.azure.dwsolution.co.", "type": "A", "value": "10.10.4.30", "ttl": 300},
        {"name": "api.azure.dwsolution.co.", "type": "A", "value": "10.10.4.11", "ttl": 300},
        {"name": "api.azure.dwsolution.co.", "type": "a", "value": "10.10.4.10", "ttl": 300},
        {"name": "azure.dwsolution.co.", "type": "TXT", "value": "zone-marker", "ttl": 600},
        {"name": "srv.azure.dwsolution.co.", "type": "SRV", "value": "0 0 0 x"},
    ])
    records = SpatiumProvider(BASE, token="t").fetch_desired({"azure.dwsolution.co"})
    by_key = {r.key: r for r in records}
    assert by_key[("azure.dwsolution.co", "app", "A")].values == ("10.10.4.30",)
    assert by_key[("azure.dwsolution.co", "api", "A")].values == ("10.10.4.10", "10.10.4.11")
    assert by_key[("azure.dwsolution.co", "@", "TXT")].ttl == 600
    assert len(records) == 3  # SRV skipped; unwanted zone never fetched


@responses.activate
def test_api_failure_is_runtime_error():
    responses.get(f"{BASE}/api/v1/dns/zones", status=500)
    with pytest.raises(RuntimeError, match="spatium API error"):
        SpatiumProvider(BASE, token="").fetch_desired({"azure.dwsolution.co"})


@responses.activate
def test_auth_header_sent_when_token_present():
    responses.get(f"{BASE}/api/v1/dns/zones", json=[])
    SpatiumProvider(BASE, token="sekrit").fetch_desired({"azure.dwsolution.co"})
    assert responses.calls[0].request.headers["Authorization"] == "Bearer sekrit"
```

Run: `uv run pytest tests/test_provider_spatium.py -q` — Expected: FAIL (`NotImplementedError`).

- [ ] **Step 2: Implement `src/ddi_reconciler/providers/spatium.py`**

```python
"""SpatiumDDI adapter — the SOURCE OF TRUTH side. Read-only: truth is never
written to by the reconciler.

Endpoint paths are a per-deployment seam: confirm against the running stack
(`curl -s $BASE/openapi.json`) and adjust the two constants if the release
differs. Value normalization (IP canonicalization, case, sorting) is
CanonicalRecord's job, not the adapter's.
"""
from __future__ import annotations

import requests

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord

ZONES_PATH = "/api/v1/dns/zones"
RECORDS_PATH = "/api/v1/dns/zones/{zone_id}/records"
_TIMEOUT = 10


class SpatiumProvider:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str) -> list[dict]:
        try:
            resp = self._session.get(f"{self.base_url}{path}", timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"spatium API error on {path}: {exc}") from exc
        body = resp.json()
        return body["items"] if isinstance(body, dict) and "items" in body else body

    @staticmethod
    def _relative(fqdn: str, zone: str) -> str:
        fqdn = fqdn.rstrip(".").lower()
        if fqdn == zone:
            return "@"
        if fqdn.endswith("." + zone):
            return fqdn[: -(len(zone) + 1)]
        return fqdn  # already zone-relative

    def fetch_desired(self, zones: set[str]) -> list[CanonicalRecord]:
        wanted = {z.strip().rstrip(".").lower() for z in zones}
        grouped: dict[tuple[str, str, str], dict] = {}
        for zone in self._get(ZONES_PATH):
            zone_name = zone["name"].strip().rstrip(".").lower()
            if zone_name not in wanted:
                continue
            for rec in self._get(RECORDS_PATH.format(zone_id=zone["id"])):
                rtype = rec["type"].strip().upper()
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                name = self._relative(rec["name"], zone_name)
                entry = grouped.setdefault(
                    (zone_name, name, rtype),
                    {"values": [], "ttl": int(rec.get("ttl") or 300)})
                entry["values"].append(str(rec["value"]))
        return [
            CanonicalRecord(zone=z, name=n, rtype=t,
                            values=tuple(e["values"]), ttl=e["ttl"])
            for (z, n, t), e in grouped.items()
        ]
```

Run: `uv run pytest tests/test_provider_spatium.py -q` — Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add ddi-reconciler/src/ddi_reconciler/providers/spatium.py ddi-reconciler/tests/test_provider_spatium.py
git commit -m "feat(reconciler): SpatiumDDI truth adapter (read-only)"
```

---

### Task B6: Azure Private DNS provider

*Depends on B1. Parallelizable with B3/B4/B5/B7.*

**Files:**
- Modify: `src/ddi_reconciler/providers/azure.py` (implement over the B1 stub)
- Create: `tests/test_provider_azure.py`

**Interfaces:**
- Produces: `AzureProvider(subscription_id, resource_group, client=None)` — `client` injection is the test seam; `fetch_actual(zones) -> list[CanonicalRecord]` (skips `is_auto_registered`), `apply(diff) -> None`.

- [ ] **Step 1: Write the failing tests — `tests/test_provider_azure.py`**

```python
"""Azure adapter — fake SDK client injected; no credentials, no network."""
from types import SimpleNamespace

import pytest

from ddi_reconciler.model import CanonicalRecord, Diff
from ddi_reconciler.providers.azure import AzureProvider

Z = "azure.dwsolution.co"


def record_set(name, rtype, *, ips=(), ttl=300, auto=False, cname=None, txt=()):
    return SimpleNamespace(
        name=name,
        type=f"Microsoft.Network/privateDnsZones/{rtype}",
        ttl=ttl,
        is_auto_registered=auto,
        a_records=[SimpleNamespace(ipv4_address=v) for v in ips] or None,
        aaaa_records=None,
        cname_record=SimpleNamespace(cname=cname) if cname else None,
        ptr_records=None,
        txt_records=[SimpleNamespace(value=[t]) for t in txt] or None,
    )


class FakeRecordSets:
    def __init__(self, listing):
        self.listing = listing
        self.upserts = []
        self.deletes = []

    def list(self, resource_group, zone):
        return iter(self.listing)

    def create_or_update(self, resource_group, zone, rtype, name, body):
        self.upserts.append((zone, rtype, name, body))

    def delete(self, resource_group, zone, rtype, name):
        self.deletes.append((zone, rtype, name))


def make_provider(listing):
    client = SimpleNamespace(record_sets=FakeRecordSets(listing))
    return AzureProvider("sub-id", "rg-cham-lab", client=client), client


def test_fetch_skips_auto_registered_and_unsupported():
    provider, _ = make_provider([
        record_set("app", "A", ips=["10.10.4.30"]),
        record_set("vm-test-app", "A", ips=["10.10.4.5"], auto=True),
        record_set("@", "SOA"),
    ])
    records = provider.fetch_actual({Z})
    assert [r.key for r in records] == [(Z, "app", "A")]


def test_fetch_maps_cname_and_txt():
    provider, _ = make_provider([
        record_set("alias", "CNAME", cname="Target.Example.com."),
        record_set("info", "TXT", txt=["marker"]),
    ])
    by_key = {r.key: r for r in provider.fetch_actual({Z})}
    assert by_key[(Z, "alias", "CNAME")].values == ("target.example.com",)
    assert by_key[(Z, "info", "TXT")].values == ("marker",)


def test_apply_upserts_adds_updates_and_deletes():
    provider, client = make_provider([])
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    gone = CanonicalRecord(zone=Z, name="old", rtype="A", values=("10.0.0.1",))
    provider.apply(Diff(to_add=[add], to_delete=[gone]))
    assert client.record_sets.upserts == [
        (Z, "A", "app", {"ttl": 300, "a_records": [{"ipv4_address": "10.10.4.30"}]})]
    assert client.record_sets.deletes == [(Z, "A", "old")]


def test_api_failure_is_runtime_error():
    class Exploding:
        def list(self, resource_group, zone):
            raise Exception("boom")
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=Exploding()))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.fetch_actual({Z})
```

Run: `uv run pytest tests/test_provider_azure.py -q` — Expected: FAIL (`NotImplementedError`).

- [ ] **Step 2: Implement `src/ddi_reconciler/providers/azure.py`** (keep the B1 docstring)

```python
"""Azure Private DNS adapter — reconciled edge for azure.dwsolution.co.

CRITICAL SAFETY: record sets with is_auto_registered=True belong to Azure VM
auto-registration and are dropped at fetch time — combined with the
managed-key allowlist in diff_records they can never be updated or deleted.

Auth: DefaultAzureCredential (az login locally; OIDC-federated in CI).
"""
from __future__ import annotations

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord, Diff


class AzureProvider:
    def __init__(self, subscription_id: str, resource_group: str, client=None):
        self.resource_group = resource_group
        if client is None:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.privatedns import PrivateDnsManagementClient
            client = PrivateDnsManagementClient(DefaultAzureCredential(), subscription_id)
        self._client = client

    @staticmethod
    def _values(rtype: str, rs) -> tuple[str, ...]:
        if rtype == "A":
            return tuple(r.ipv4_address for r in rs.a_records or [])
        if rtype == "AAAA":
            return tuple(r.ipv6_address for r in rs.aaaa_records or [])
        if rtype == "CNAME":
            return (rs.cname_record.cname,) if rs.cname_record else ()
        if rtype == "PTR":
            return tuple(r.ptrdname for r in rs.ptr_records or [])
        if rtype == "TXT":
            return tuple("".join(r.value) for r in rs.txt_records or [])
        return ()

    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        records: list[CanonicalRecord] = []
        for zone in zones:
            try:
                record_sets = list(self._client.record_sets.list(self.resource_group, zone))
            except Exception as exc:  # azure.core exceptions -> CLI error contract
                raise RuntimeError(f"azure API error listing {zone}: {exc}") from exc
            for rs in record_sets:
                rtype = rs.type.rsplit("/", 1)[-1].upper()  # ".../privateDnsZones/A" -> "A"
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                if getattr(rs, "is_auto_registered", False):
                    continue
                values = self._values(rtype, rs)
                if not values:
                    continue
                records.append(CanonicalRecord(zone=zone, name=rs.name, rtype=rtype,
                                               values=values, ttl=int(rs.ttl or 300)))
        return records

    @staticmethod
    def _record_set_body(record: CanonicalRecord) -> dict:
        body: dict = {"ttl": record.ttl}
        if record.rtype == "A":
            body["a_records"] = [{"ipv4_address": v} for v in record.values]
        elif record.rtype == "AAAA":
            body["aaaa_records"] = [{"ipv6_address": v} for v in record.values]
        elif record.rtype == "CNAME":
            body["cname_record"] = {"cname": record.values[0]}
        elif record.rtype == "PTR":
            body["ptr_records"] = [{"ptrdname": v} for v in record.values]
        elif record.rtype == "TXT":
            body["txt_records"] = [{"value": [v]} for v in record.values]
        return body

    def apply(self, diff: Diff) -> None:
        try:
            for record in diff.to_add + [u.desired for u in diff.to_update]:
                self._client.record_sets.create_or_update(
                    self.resource_group, record.zone, record.rtype, record.name,
                    self._record_set_body(record))
            for record in diff.to_delete:
                self._client.record_sets.delete(
                    self.resource_group, record.zone, record.rtype, record.name)
        except Exception as exc:
            raise RuntimeError(f"azure API error applying diff: {exc}") from exc
```

Run: `uv run pytest tests/test_provider_azure.py -q` — Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add ddi-reconciler/src/ddi_reconciler/providers/azure.py ddi-reconciler/tests/test_provider_azure.py
git commit -m "feat(reconciler): Azure Private DNS adapter with auto-registration safety"
```

---

### Task B7: Cloudflare provider (the RRset↔per-record translation)

*Depends on B1. Parallelizable with B3/B4/B5/B6.*

**Files:**
- Modify: `src/ddi_reconciler/providers/cloudflare.py` (implement; keep the API-shape-warning docstring)
- Create: `tests/test_provider_cloudflare.py`

**Interfaces:**
- Produces: `CloudflareProvider(zone_name, api_token)`; `fetch_actual(zones)` (groups per-value API records into RRsets, builds the record-id index), `apply(diff)` (fans RRset changes back out per value). Statefulness contract: `apply` uses the id-index from the immediately preceding `fetch_actual` in the same run — the runner's plan-then-apply ordering guarantees this.

- [ ] **Step 1: Write the failing tests — `tests/test_provider_cloudflare.py`**

```python
"""Cloudflare adapter — HTTP mocked with responses. Exercises the RRset
grouping the docstring warns about."""
import pytest
import responses

from ddi_reconciler.model import CanonicalRecord, Diff, RecordUpdate
from ddi_reconciler.providers.cloudflare import CloudflareProvider

API = "https://api.cloudflare.com/client/v4"
Z = "dwsolution.co"


def register_zone():
    responses.get(f"{API}/zones?name={Z}",
                  json={"success": True, "result": [{"id": "zid"}]})


def register_records(result, total_pages=1):
    responses.get(f"{API}/zones/zid/dns_records?per_page=100&page=1",
                  json={"success": True, "result": result,
                        "result_info": {"total_pages": total_pages}})


@responses.activate
def test_fetch_groups_rrsets_dequotes_txt_and_maps_apex():
    register_zone()
    register_records([
        {"id": "1", "type": "A", "name": "api.dwsolution.co", "content": "1.1.1.1", "ttl": 300},
        {"id": "2", "type": "A", "name": "api.dwsolution.co", "content": "1.1.1.2", "ttl": 300},
        {"id": "3", "type": "TXT", "name": "dwsolution.co", "content": "\"marker\"", "ttl": 300},
        {"id": "4", "type": "MX", "name": "dwsolution.co", "content": "mail.x", "ttl": 300},
    ])
    records = CloudflareProvider(Z, "token").fetch_actual({Z})
    by_key = {r.key: r for r in records}
    assert by_key[(Z, "api", "A")].values == ("1.1.1.1", "1.1.1.2")   # ONE RRset, not two
    assert by_key[(Z, "@", "TXT")].values == ("marker",)
    assert len(records) == 2  # MX ignored


@responses.activate
def test_apply_fans_out_add_and_delete_per_value():
    register_zone()
    register_records([
        {"id": "old1", "type": "A", "name": "demo.dwsolution.co", "content": "9.9.9.9", "ttl": 300},
    ])
    provider = CloudflareProvider(Z, "token")
    actual = provider.fetch_actual({Z})[0]
    desired = CanonicalRecord(zone=Z, name="demo", rtype="A",
                              values=("9.9.9.8",), ttl=300)
    created = responses.post(f"{API}/zones/zid/dns_records",
                             json={"success": True, "result": {"id": "new1"}})
    deleted = responses.delete(f"{API}/zones/zid/dns_records/old1",
                               json={"success": True, "result": {"id": "old1"}})
    provider.apply(Diff(to_update=[RecordUpdate(desired=desired, actual=actual)]))
    assert created.call_count == 1
    assert deleted.call_count == 1


@responses.activate
def test_delete_removes_every_value_record():
    register_zone()
    register_records([
        {"id": "d1", "type": "A", "name": "gone.dwsolution.co", "content": "1.1.1.1", "ttl": 300},
        {"id": "d2", "type": "A", "name": "gone.dwsolution.co", "content": "1.1.1.2", "ttl": 300},
    ])
    provider = CloudflareProvider(Z, "token")
    actual = provider.fetch_actual({Z})[0]
    del1 = responses.delete(f"{API}/zones/zid/dns_records/d1", json={"success": True, "result": {}})
    del2 = responses.delete(f"{API}/zones/zid/dns_records/d2", json={"success": True, "result": {}})
    provider.apply(Diff(to_delete=[actual]))
    assert del1.call_count == 1 and del2.call_count == 1


@responses.activate
def test_api_error_is_runtime_error():
    responses.get(f"{API}/zones?name={Z}",
                  json={"success": False, "errors": [{"code": 9109, "message": "bad token"}]},
                  status=403)
    with pytest.raises(RuntimeError, match="cloudflare API"):
        CloudflareProvider(Z, "token").fetch_actual({Z})
```

Run: `uv run pytest tests/test_provider_cloudflare.py -q` — Expected: FAIL (`NotImplementedError`).

- [ ] **Step 2: Implement `src/ddi_reconciler/providers/cloudflare.py`** (replace the stub body; keep and extend the docstring)

```python
"""Cloudflare adapter — reconciled edge for the PUBLIC zone only.

API shape warning (the whole point of this adapter): Cloudflare models one
API record PER VALUE — a two-value A RRset is two API records sharing
(name, type). fetch_actual() groups API records into ONE CanonicalRecord per
RRset and builds a record-id index; apply() fans RRset-level changes back out
into per-record calls using that index. apply() therefore requires a
fetch_actual() earlier in the same run (the runner's plan-then-apply
ordering guarantees it).

Token: scoped API token — Zone.Zone:Read + Zone.DNS:Edit on this zone only.
"""
from __future__ import annotations

import requests

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord, Diff

API = "https://api.cloudflare.com/client/v4"
_TIMEOUT = 10


class CloudflareProvider:
    def __init__(self, zone_name: str, api_token: str):
        self.zone_name = zone_name.strip().rstrip(".").lower()
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_token}"
        self._zone_id: str | None = None
        self._api_records: dict[tuple[str, str, str], list[dict]] = {}

    # --- plumbing -----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._session.request(method, f"{API}{path}", timeout=_TIMEOUT, **kwargs)
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"cloudflare API error on {path}: {exc}") from exc
        if not resp.ok or not body.get("success", False):
            raise RuntimeError(
                f"cloudflare API {resp.status_code} on {path}: {body.get('errors')}")
        return body

    def _zone(self) -> str:
        if self._zone_id is None:
            result = self._request("GET", f"/zones?name={self.zone_name}")["result"]
            if not result:
                raise RuntimeError(f"cloudflare zone not found: {self.zone_name}")
            self._zone_id = result[0]["id"]
        return self._zone_id

    def _relative(self, fqdn: str) -> str:
        fqdn = fqdn.rstrip(".").lower()
        if fqdn == self.zone_name:
            return "@"
        suffix = "." + self.zone_name
        return fqdn[: -len(suffix)] if fqdn.endswith(suffix) else fqdn

    def _fqdn(self, name: str) -> str:
        return self.zone_name if name == "@" else f"{name}.{self.zone_name}"

    @staticmethod
    def _content(raw: dict) -> str:
        content = raw["content"]
        if raw["type"].upper() == "TXT" and len(content) >= 2 and content[0] == content[-1] == '"':
            content = content[1:-1]  # the API returns TXT content quoted
        return content

    @staticmethod
    def _match_key(rtype: str, content: str) -> str:
        # Mirror CanonicalRecord's domain-value normalization so canonical
        # values can look up raw API records regardless of case/trailing dot.
        return content.rstrip(".").lower() if rtype in {"CNAME", "PTR"} else content

    # --- provider contract --------------------------------------------------
    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        zone_id = self._zone()
        raw_records: list[dict] = []
        page = 1
        while True:
            body = self._request(
                "GET", f"/zones/{zone_id}/dns_records?per_page=100&page={page}")
            raw_records.extend(body["result"])
            if page >= body.get("result_info", {}).get("total_pages", 1):
                break
            page += 1

        self._api_records.clear()
        grouped: dict[tuple[str, str, str], dict] = {}
        for raw in raw_records:
            rtype = raw["type"].upper()
            if rtype not in SUPPORTED_RECORD_TYPES:
                continue
            key = (self.zone_name, self._relative(raw["name"]), rtype)
            self._api_records.setdefault(key, []).append(raw)
            entry = grouped.setdefault(key, {"values": [], "ttl": int(raw["ttl"])})
            entry["values"].append(self._content(raw))
        return [
            CanonicalRecord(zone=z, name=n, rtype=t,
                            values=tuple(e["values"]), ttl=e["ttl"])
            for (z, n, t), e in grouped.items()
        ]

    def _create(self, record: CanonicalRecord, value: str) -> None:
        self._request("POST", f"/zones/{self._zone()}/dns_records", json={
            "type": record.rtype, "name": self._fqdn(record.name),
            "content": value, "ttl": record.ttl, "proxied": False,
        })

    def apply(self, diff: Diff) -> None:
        zone_id = self._zone()
        for record in diff.to_add:
            for value in record.values:
                self._create(record, value)
        for update in diff.to_update:
            want, have = update.desired, update.actual
            existing = {
                self._match_key(want.rtype, self._content(r)): r
                for r in self._api_records.get(want.key, [])
            }
            for value in set(want.values) - set(have.values):
                self._create(want, value)
            for value in set(have.values) - set(want.values):
                self._request("DELETE", f"/zones/{zone_id}/dns_records/{existing[value]['id']}")
            if want.ttl != have.ttl:
                for value in set(want.values) & set(have.values):
                    self._request("PATCH", f"/zones/{zone_id}/dns_records/{existing[value]['id']}",
                                  json={"ttl": want.ttl})
        for record in diff.to_delete:
            for raw in self._api_records.get(record.key, []):
                self._request("DELETE", f"/zones/{zone_id}/dns_records/{raw['id']}")
```

Run: `uv run pytest tests/test_provider_cloudflare.py -q` — Expected: 4 passed. Then `uv run pytest -q` — full suite green.

- [ ] **Step 3: Commit**

```bash
git add ddi-reconciler/src/ddi_reconciler/providers/cloudflare.py ddi-reconciler/tests/test_provider_cloudflare.py
git commit -m "feat(reconciler): Cloudflare adapter — RRset grouping and per-value fan-out"
```

---

## Track A — Cloudflare infrastructure + split-horizon targets

### Task A1: Cloudflare zone and scoped token (manual, console)

*No repo changes. Parallelizable with all of Track B.*

- [ ] **Step 1:** Add `dwsolution.co` to the Cloudflare account (Free plan); at the registrar, set the nameservers to the two assigned `*.ns.cloudflare.com` hosts.
- [ ] **Step 2:** Verify activation: `dig +short NS dwsolution.co` → the two Cloudflare NS hosts (propagation can take hours — start this task early).
- [ ] **Step 3:** Create an API token: template "Edit zone DNS", permissions **Zone.Zone:Read + Zone.DNS:Edit**, zone resource limited to `dwsolution.co` only. Export it in the shell profile used for lab sessions: `export CLOUDFLARE_API_TOKEN=...` (never in the repo).
- [ ] **Step 4:** Verify the token:
```bash
curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones?name=dwsolution.co" | python3 -c "import json,sys; b=json.load(sys.stdin); print(b['success'], len(b['result']))"
```
Expected: `True 1`.

### Task A2: Terraform edits — public www target + internal page on the hub

*Repo changes; parallelizable with Track B. The hub cloud-init change forces a hub VM replace on next apply (custom_data) — schedule with a normal session destroy/apply cycle, and re-run the Phase 3 Task 1 key install after.*

**Files:**
- Modify: `terraform/cloudflare/main.tf` (www record → CNAME), `terraform/cloudflare/variables.tf`
- Modify: `terraform/modules/hub/cloud-init.yml.tpl` (nginx + internal page)
- Modify: `terraform/modules/hub/main.tf` (NSG rule 130)

- [ ] **Step 1: Public page host.** Create a GitHub Pages site to be the public www target:
```bash
gh repo create www-dwsolution --public
printf '<h1>PUBLIC — resolved via Cloudflare</h1>\n' > /tmp/index.html
# push index.html to main, then:
gh api repos/{owner}/www-dwsolution/pages -X POST -f 'source[branch]=main' -f 'source[path]=/'
gh api repos/{owner}/www-dwsolution/pages -X PUT -f cname=www.dwsolution.co
```
(Any static host works; GitHub Pages is free and needs only a CNAME.)

- [ ] **Step 2: Swap the www record to a CNAME.** In `terraform/cloudflare/main.tf` replace `resource "cloudflare_record" "www"`:

```hcl
# The public answer for www — the split-horizon counterpart lives in the
# internal BIND9 override zone and returns the hub's private IP for the
# same name.
resource "cloudflare_record" "www" {
  zone_id = data.cloudflare_zone.apex.id
  name    = "www"
  type    = "CNAME"
  content = var.www_public_target
  ttl     = 300
  proxied = false # keep dig-able; proxying returns Cloudflare edge IPs
}
```

In `terraform/cloudflare/variables.tf` replace `www_public_ip` with:

```hcl
variable "www_public_target" {
  description = "Public www target hostname (GitHub Pages site)"
  type        = string
  default     = "ilee165.github.io"
}
```

- [ ] **Step 3: Internal page on the hub.** In `terraform/modules/hub/cloud-init.yml.tpl`: add `nginx` to the `packages:` list and this entry under `write_files:`:

```yaml
  - path: /var/www/html/index.html
    content: |
      <h1>INTERNAL — served from the hub over the tunnel</h1>
```

In `terraform/modules/hub/main.tf`, add to the NSG (after the DNS rule):

```hcl
  security_rule {
    name                       = "AllowHTTPInternal"
    priority                   = 130
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefixes    = ["10.10.0.0/16", "10.20.0.0/16", "172.16.0.0/24"]
    destination_address_prefix = "*"
  }
```

(`DenyAllOtherInbound` still blocks the internet — the page is reachable only from inside the lab.)

- [ ] **Step 4: Validate and commit**

```bash
terraform -chdir=terraform/cloudflare init -backend=false && terraform -chdir=terraform/cloudflare validate
terraform -chdir=terraform/envs/lab init -backend=false && terraform -chdir=terraform/envs/lab validate
terraform fmt -check -recursive terraform/
git add terraform/
git commit -m "feat(terraform): www CNAME to public page, internal page on hub for split-horizon demo"
```

### Task A3: Internal www override zone in SpatiumDDI

*Needs only the Phase 1 stack. Parallelizable with A4.*

- [ ] **Step 1:** In the SpatiumDDI control plane, create an authoritative (master) zone `www.dwsolution.co` on the lab DNS group with a single record: `@ A 10.10.0.10` (the hub VM — where the internal page lives). This single-name-zone technique overrides just `www` while every other `dwsolution.co` name still resolves publicly.
- [ ] **Step 2:** Verify locally (tunnel state irrelevant for resolution itself):
```bash
dig +short @localhost www.dwsolution.co        # → 10.10.0.10 (internal answer)
dig +short @1.1.1.1 www.dwsolution.co          # → GitHub Pages addresses (public answer)
```
Both answers existing simultaneously **is** the split horizon.

### Task A4: Apply the Cloudflare stack

*Depends on A1, A2, and Phase 2 Task 3 (backend storage account pinned).*

- [x] **Step 1: Init + plan + apply** — done 2026-08-07

```bash
cd terraform/cloudflare
terraform init -backend-config=backend.auto.tfbackend
terraform plan    # expect: 2 to add (www CNAME, external-check TXT)
terraform apply
```
(The provider reads `CLOUDFLARE_API_TOKEN` from the environment; the backend uses the same storage account as the lab stack with key `cloudflare.tfstate` — ADR-004's split-state story.)

`init` needs the explicit `-backend-config` because `plan.yml`'s static job
inits this directory with `-backend=false`, which leaves a `.terraform/`
carrying providers but no backend.

Plan matched the expectation exactly — `2 to add, 0 to change, 0 to destroy`
— and applied clean: `lab_marker` `87842aa4…`, `www` `108aa676…`. A second
`plan -detailed-exitcode` returned 0, so the stack is idempotent.

**`dwsolution.co` is a live production zone, not a lab one.** It carries the
Microsoft 365 records this domain's mail actually depends on: `MX` →
`dwsolution-co.mail.protection.outlook.com`, the SPF `TXT`, the `MS=`
verification `TXT`, plus `autodiscover` / `sip` / `lyncdiscover` /
`enterpriseenrollment` / `enterpriseregistration` and two `SRV` records.
Nothing here may ever delete by magnitude or by sweep. Two properties keep
that true, and both were verified against the live zone after this apply:

- Terraform manages only the two resources in its own state and has no
  `cloudflare_zone` resource, so it cannot remove a record it did not
  create. `allow_overwrite = false` means a surprise collision fails the
  apply rather than clobbering the incumbent.
- The reconciler's ADR-005 `managed_keys` for this edge is `demo`/CNAME and
  `reconciler-check`/TXT — disjoint from every record above, including the
  two this task creates. A dry-run against the post-apply zone read all 12
  records and reported `2 add, 0 update, 0 delete`. Zero deletes is the
  allowlist proving itself on real infrastructure rather than on a fixture.

- [x] **Step 2: Verify from the outside world** — DNS verified; HTTPS pending cert

```bash
dig +short www.dwsolution.co @1.1.1.1
dig +short TXT external-check.dwsolution.co @1.1.1.1
curl -s https://www.dwsolution.co | head -1
```
Expected: CNAME chain to the Pages host resolving to real IPs; `"resolved-via=cloudflare-public"`; `<h1>PUBLIC — resolved via Cloudflare</h1>` (allow time for the Pages TLS cert after A2 Step 1).

`www.dwsolution.co` → `ilee165.github.io` → `185.199.108-111.153` (+ AAAA), and
`external-check.dwsolution.co` returns `"resolved-via=cloudflare-public"`, both
from `1.1.1.1`. The page serves the expected `<h1>PUBLIC — resolved via
Cloudflare</h1>` over **HTTP**.

**HTTPS is not yet available**, and the reason is ordering rather than
misconfiguration: `repos/ilee165/www-dwsolution/pages` already had
`cname: www.dwsolution.co` set on 2026-08-06, a day before this apply created
the DNS record. GitHub requests a Let's Encrypt certificate only once the
custom domain resolves, so that first attempt had nothing to validate and
`https_certificate` is still `NONE`; the TLS handshake falls back to the
`*.github.io` wildcard, whose SANs do not cover this domain. Now that the
CNAME resolves, GitHub re-provisions on its own. If it has not within ~24h,
remove and re-add the custom domain in repo settings to force revalidation.
`https_enforced` can only be turned on after the certificate exists.

- [x] **Step 3: Verify the state split** — done 2026-08-07

```bash
az storage blob list --account-name <stchamtfXXXXXX> -c tfstate --auth-mode login -o table
```
Expected: two blobs — `lab.tfstate` and `cloudflare.tfstate`.

Both present in `rg-cham-tfstate` / `<stchamtfXXXXXX>`: `lab.tfstate` (3238 B)
and `cloudflare.tfstate` (3670 B, written by this apply). Confirms ADR-004's
split — the Cloudflare stack shares the backend but not the state file, so a
destroy of the lab stack cannot touch public DNS.

---

## Track C — Live convergence and the demo

### Task C1: Seed truth in SpatiumDDI and commit the snapshot

*Depends on: all of Track B, A1–A4, Phase 2 applied (Azure zone exists), Phase 1 stack up.*

- [ ] **Step 1:** In the SpatiumDDI control plane create the reconciler-managed truth records (zones are *modeled* — Spatium doesn't serve them publicly; it is the system of record):
  - Zone `azure.dwsolution.co` (create if not present): `app A 10.10.4.30`, TTL 300.
  - Zone `dwsolution.co` (create if not present): `demo CNAME www.dwsolution.co`, TTL 300; `reconciler-check TXT "managed-by=ddi-reconciler"`, TTL 300.

  These names exactly match `config.toml`'s `managed_keys` — anything else in those zones is invisible to the reconciler.

- [ ] **Step 2:** Export and commit the snapshot (ADR-006, consumed by Phase 5 CI):

```bash
cd ddi-reconciler
uv run cham-reconcile --export desired-records.json
git add desired-records.json
git commit -m "feat(reconciler): desired-state snapshot for CI drift detection"
```
Expected: `exported 3 records to desired-records.json`; the file content is sorted and stable.

### Task C2: Live convergence, idempotency, tamper-healing, ownership safety

*Depends on C1. Run with `az login` active, `CLOUDFLARE_API_TOKEN` and `AZURE_SUBSCRIPTION_ID` exported.*

- [ ] **Step 1: Record the pre-state of protected records** (evidence for the safety claim):

```bash
mkdir -p ../docs/evidence/phase4
az network private-dns record-set a list -g rg-cham-lab -z azure.dwsolution.co -o table | tee ../docs/evidence/phase4/protected-before.txt
```
Expected: `db` (seed) and the auto-registered `vm-test-*` records present.

- [ ] **Step 2: First convergence**

```bash
uv run cham-reconcile --dry-run; echo "exit=$?"     # expect diff: 3 ADDs, exit=2
uv run cham-reconcile --apply;   echo "exit=$?"     # expect applied, exit=0
uv run cham-reconcile --dry-run; echo "exit=$?"     # expect converged, exit=0  (idempotent)
```
Capture all three to `../docs/evidence/phase4/first-convergence.txt` with `tee -a`.

- [ ] **Step 3: Verify on the edges directly**

```bash
az network private-dns record-set a show -g rg-cham-lab -z azure.dwsolution.co -n app --query aRecords -o tsv   # 10.10.4.30
dig +short demo.dwsolution.co @1.1.1.1        # CNAME → www → Pages IPs
dig +short TXT reconciler-check.dwsolution.co @1.1.1.1   # "managed-by=ddi-reconciler"
```

- [ ] **Step 4: Tamper-and-heal, Azure edge**

```bash
az network private-dns record-set a delete -g rg-cham-lab -z azure.dwsolution.co -n app --yes
uv run cham-reconcile --dry-run; echo "exit=$?"   # expect ADD app, exit=2
uv run cham-reconcile --apply                     # heals
```

- [ ] **Step 5: Tamper-and-heal, Cloudflare edge** — in the Cloudflare dashboard change `demo`'s target to `example.com`, then:

```bash
uv run cham-reconcile --dry-run; echo "exit=$?"   # expect UPDATE demo ... -> www.dwsolution.co, exit=2
uv run cham-reconcile --apply && uv run cham-reconcile --dry-run; echo "exit=$?"   # healed, exit=0
```

- [ ] **Step 6: Ownership safety proof** — after all applies:

```bash
az network private-dns record-set a list -g rg-cham-lab -z azure.dwsolution.co -o table | tee ../docs/evidence/phase4/protected-after.txt
diff ../docs/evidence/phase4/protected-before.txt ../docs/evidence/phase4/protected-after.txt
```
Expected: `db` and every `vm-test-*` auto-registered record byte-identical (the only difference between the two files is the reconciler's own `app` record). Also confirm `www` and `external-check` never appeared in any diff output. Commit the evidence.

### Task C3: Split-horizon demo, docs, ADR-006

*Depends on C2 + Phase 3 (tunnel) for the internal half.*

**Files:**
- Modify: `README.md:46` (check Phase 4 box), `docs/decisions.md` (ADR-006), `docs/runbook.md` (demo steps verified)

- [ ] **Step 1: Run the runbook split-horizon demo end to end**

1. Tunnel DOWN (`sudo wg-quick down wg0`): `curl -s https://www.dwsolution.co | head -1` → `PUBLIC — resolved via Cloudflare`.
2. `sudo wg-quick up wg0`, then `dig +short @localhost www.dwsolution.co` → `10.10.0.10`.
3. `curl -s --resolve www.dwsolution.co:80:10.10.0.10 http://www.dwsolution.co | head -1` → `INTERNAL — served from the hub over the tunnel` (deterministic curl form; a browser pointed at the Spatium resolver shows the same).
4. Capture both answers side by side into `docs/evidence/phase4/split-horizon.txt`.

- [ ] **Step 2: Append ADR-006 to `docs/decisions.md`**

```markdown
## ADR-006: CI drift detection compares edges to a committed desired-state snapshot
- **Context:** Nightly CI cannot reach the laptop's SpatiumDDI API (home NAT,
  stack usually down), but edge drift is exactly what CI should catch.
- **Decision:** Sessions end with `cham-reconcile --export desired-records.json`
  (committed). Nightly drift runs
  `cham-reconcile --dry-run --desired-from-file desired-records.json` and keys
  off the exit code (0 converged / 2 drift / 1 error).
- **Tradeoff accepted:** The snapshot can lag live truth between sessions, so
  CI detects "edge vs last-exported truth". Acceptable: truth only changes
  during sessions, and sessions end with an export.
```

- [ ] **Step 3: Close out**

Check `- [x] Phase 4 — Cloudflare + reconciler v2` in README; commit README + docs + evidence:

```bash
git add README.md docs/
git commit -m "docs: phase 4 complete — split-horizon live, reconciler converging both edges"
```

---

## Exit Criteria (all must hold)

1. `uv run pytest -q` green — model/diff, config, snapshot, runner, CLI, and all three providers — with **no network and no credentials** (verifiable: run it with `CLOUDFLARE_API_TOKEN` unset and no `az login`).
2. Exit-code contract proven live: dry-run returns 2 on drift, 0 when converged, 1 on operational error (e.g., bad token) — captured in evidence.
3. First convergence applied the 3 seeded records; an immediately repeated apply/dry-run is a no-op (idempotency).
4. Tamper on each edge (Azure record deleted, Cloudflare record altered) detected and healed by the reconciler.
5. Ownership safety: byte-identical before/after listings for the `db` seed and auto-registered records; `www`/`external-check` never surfaced in any diff.
6. `terraform/cloudflare` applied from its own `cloudflare.tfstate` in the shared storage account, using only the scoped token.
7. Split horizon demonstrable per runbook: `www.dwsolution.co` answers publicly (Cloudflare→Pages) and internally (BIND override→hub page), both captured in evidence.
8. `desired-records.json` committed, ADR-006 recorded, README Phase 4 checked.

## What Completion Looks Like

`cham-reconcile --dry-run` is a one-command answer to "does the world match intent?" across two DNS providers, and `--apply` makes it so — provably unable to touch anything it doesn't own, from Terraform's seeds to Azure's auto-registered VM records. The test suite demonstrates the design story (a trivial loop, all the work in the adapters — each adapter's translation quirk pinned by an offline test). The public internet and the lab disagree about `www.dwsolution.co`, on purpose, with both answers under version control. And a committed snapshot of truth means Phase 5's nightly CI can spot edge tampering without any path back to the laptop.
