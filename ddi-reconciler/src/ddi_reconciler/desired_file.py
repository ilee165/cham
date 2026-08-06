"""Desired-state snapshot: CanonicalRecords <-> committed JSON file.

Nightly CI cannot reach the laptop's SpatiumDDI API, so sessions export truth
to ddi-reconciler/desired-records.json and drift runs compare edges against
that committed snapshot (ADR-006).

The snapshot is a delete order for everything it omits, so writes are atomic
(a truncated file is a partial wipe order) and shrinking one requires an
explicit opt-in.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ddi_reconciler.model import CanonicalRecord

_REQUIRED_FIELDS = ("zone", "name", "rtype", "values", "ttl")


class SnapshotError(RuntimeError):
    """A snapshot write was refused because it would lose records."""


def _entry_count(path: Path) -> int | None:
    """Records in an existing snapshot, or None when there is nothing
    comparable there (absent, unreadable, or not a JSON list)."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return len(entries) if isinstance(entries, list) else None


def save_desired(records: list[CanonicalRecord], path: Path,
                 *, allow_shrink: bool = False) -> None:
    if not path.name:
        raise ValueError(f"invalid snapshot path: {str(path)!r}")

    # A SpatiumDDI restarted with an empty DB exports [] and exits 0; the
    # committed snapshot then becomes a standing wipe order for the next
    # --apply. Refuse to lose records unless the operator says so.
    prior = _entry_count(path)
    if prior is not None and len(records) < prior and not allow_shrink:
        raise SnapshotError(
            f"refusing to shrink {path}: it holds {prior} record(s) and this export "
            f"has {len(records)}. Truth may be empty, truncated, or scoped to fewer "
            "zones — a shorter snapshot is a delete order for every record it drops. "
            "Re-run with --allow-snapshot-shrink if the loss is intended.")

    payload = [
        {"zone": r.zone, "name": r.name, "rtype": r.rtype,
         "values": list(r.values), "ttl": r.ttl}
        for r in sorted(records, key=lambda r: r.key)
    ]
    # Write-then-rename: an interrupted write (Ctrl-C, disk full) must not
    # leave a truncated snapshot in place of the committed one.
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def load_desired(path: Path) -> list[CanonicalRecord]:
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid snapshot {path}: {exc}") from exc
    if not isinstance(entries, list):
        raise ValueError(f"invalid snapshot {path}: expected a JSON list of records")

    records: list[CanonicalRecord] = []
    for index, entry in enumerate(entries):
        # Schema-check before construction: a bare KeyError here reads as a
        # missing environment variable by the time it reaches the CLI.
        if not isinstance(entry, dict):
            raise ValueError(f"invalid snapshot {path}: entry {index} is not an object")
        missing = [field for field in _REQUIRED_FIELDS if field not in entry]
        if missing:
            raise ValueError(f"invalid snapshot {path}: entry {index} is missing "
                             f"field(s): {', '.join(missing)}")
        if not isinstance(entry["values"], list):
            raise ValueError(f"invalid snapshot {path}: entry {index} 'values' "
                             "must be a list")
        records.append(
            CanonicalRecord(zone=entry["zone"], name=entry["name"], rtype=entry["rtype"],
                            values=tuple(entry["values"]), ttl=entry["ttl"]))
    return records
