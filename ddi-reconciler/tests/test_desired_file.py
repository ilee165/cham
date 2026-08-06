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
