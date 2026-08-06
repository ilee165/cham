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
