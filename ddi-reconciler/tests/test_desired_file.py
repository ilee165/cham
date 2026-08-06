"""Snapshot round-trip — the CI drift mode's data source (ADR-006)."""
import json

import pytest

from ddi_reconciler import desired_file
from ddi_reconciler.desired_file import SnapshotError, load_desired, save_desired
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


def _rec(name):
    return CanonicalRecord(zone="z.co", name=name, rtype="A", values=("1.1.1.1",))


def test_export_refuses_to_shrink_an_existing_snapshot(tmp_path):
    """SpatiumDDI restarted with an empty DB exports [] and exits 0; the
    committed snapshot then becomes a standing wipe order for the next apply."""
    path = tmp_path / "desired.json"
    save_desired([_rec("a"), _rec("b"), _rec("c")], path)

    with pytest.raises(SnapshotError, match="refusing to shrink"):
        save_desired([], path)
    with pytest.raises(SnapshotError, match="refusing to shrink"):
        save_desired([_rec("a")], path)

    assert len(load_desired(path)) == 3  # untouched


def test_export_shrink_is_allowed_with_explicit_opt_in(tmp_path):
    path = tmp_path / "desired.json"
    save_desired([_rec("a"), _rec("b")], path)
    save_desired([_rec("a")], path, allow_shrink=True)
    assert [r.name for r in load_desired(path)] == ["a"]


def test_export_may_grow_or_stay_the_same_size(tmp_path):
    path = tmp_path / "desired.json"
    save_desired([_rec("a")], path)
    save_desired([_rec("b"), _rec("c")], path)          # grew
    save_desired([_rec("d"), _rec("e")], path)          # same size, new content
    assert [r.name for r in load_desired(path)] == ["d", "e"]


def test_failed_write_leaves_the_committed_snapshot_intact(tmp_path, monkeypatch):
    """write_text() truncates in place: an interrupted export used to leave a
    partial file that CI then reads as truth."""
    path = tmp_path / "desired.json"
    save_desired([_rec("a"), _rec("b")], path)
    before = path.read_text()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(desired_file.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        save_desired([_rec("a"), _rec("b"), _rec("c")], path)
    assert path.read_text() == before


def test_missing_field_names_the_field_not_an_env_var(tmp_path):
    """A KeyError from snapshot data used to surface as
    'missing required environment variable: ttl'."""
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"zone": "z.co", "name": "x", "rtype": "A",
                                 "values": ["1.1.1.1"]}]))
    with pytest.raises(ValueError, match="entry 0 is missing field\\(s\\): ttl"):
        load_desired(path)


@pytest.mark.parametrize("body", ['{"zone": "z.co"}', "[1, 2]", '[{"values": "x"}]', "not json"])
def test_malformed_snapshot_is_a_clear_value_error(tmp_path, body):
    path = tmp_path / "bad.json"
    path.write_text(body)
    with pytest.raises(ValueError, match="invalid snapshot"):
        load_desired(path)
