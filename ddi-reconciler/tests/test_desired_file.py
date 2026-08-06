"""Snapshot round-trip — the CI drift mode's data source (ADR-006)."""
import json

import pytest

from ddi_reconciler import desired_file
from ddi_reconciler.desired_file import (
    SNAPSHOT_VERSION,
    SnapshotError,
    load_desired,
    save_desired,
)
from ddi_reconciler.model import CanonicalRecord


def _rec(name, zone="z.co", value="1.1.1.1"):
    return CanonicalRecord(zone=zone, name=name, rtype="A", values=(value,))


def _save(records, path, **kwargs):
    kwargs.setdefault("truth_verified", True)
    save_desired(records, path, **kwargs)


def test_round_trip_preserves_records(tmp_path):
    records = [
        CanonicalRecord(zone="dwsolution.co", name="demo", rtype="CNAME",
                        values=("www.dwsolution.co",), ttl=300),
        CanonicalRecord(zone="azure.dwsolution.co", name="app", rtype="A",
                        values=("10.10.4.30",), ttl=300),
    ]
    path = tmp_path / "desired.json"
    _save(records, path)
    loaded, verified = load_desired(path)
    assert loaded == sorted(records, key=lambda r: r.key)
    assert verified is True


def test_snapshot_is_sorted_and_stable(tmp_path):
    a = _rec("b", value="1.1.1.1")
    b = _rec("a", value="1.1.1.2")
    p1, p2 = tmp_path / "one.json", tmp_path / "two.json"
    _save([a, b], p1)
    _save([b, a], p2)
    assert p1.read_text() == p2.read_text()  # committed file must diff cleanly


def test_invalid_record_in_file_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"zone": "z.co", "name": "x", "rtype": "BOGUS",
                                 "values": ["v"], "ttl": 300}]))
    with pytest.raises(ValueError, match="unsupported record type"):
        load_desired(path)


# --- format v1: the snapshot describes itself so truncation is detectable ---

def test_saved_snapshot_declares_version_count_and_checksum(tmp_path):
    """Phase 5's CI reads this file; the shape is a contract."""
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b")], path)
    body = json.loads(path.read_text())
    assert body["version"] == SNAPSHOT_VERSION
    assert body["count"] == 2 == len(body["records"])
    assert body["checksum"].startswith("sha256:")
    assert body["truth_verified"] is True
    assert body["records"][0] == {"zone": "z.co", "name": "a", "rtype": "A",
                                  "values": ["1.1.1.1"], "ttl": 300}


def test_a_truncated_snapshot_is_an_error_not_a_smaller_truth(tmp_path):
    """CR-1, file half: dropping a record without touching the count is what a
    truncated write or a half-resolved merge leaves behind, and it used to read
    as a delete order for everything it lost."""
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b"), _rec("c")], path)
    body = json.loads(path.read_text())
    body["records"] = body["records"][:2]          # count still says 3
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="declares 3 record\\(s\\) but carries 2"):
        load_desired(path)


def test_an_edited_record_is_caught_by_the_checksum(tmp_path):
    """Count-only integrity passes a swapped record of the same size."""
    path = tmp_path / "desired.json"
    _save([_rec("a")], path)
    body = json.loads(path.read_text())
    body["records"][0]["values"] = ["9.9.9.9"]     # same count, different truth
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="checksum"):
        load_desired(path)


def test_a_deliberate_removal_survives_a_re_export(tmp_path):
    """The integrity check must not make intentional removal inexpressible:
    --export rewrites records, count and checksum together."""
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b")], path)
    _save([_rec("a")], path, allow_shrink=True)
    records, verified = load_desired(path)
    assert [r.name for r in records] == ["a"]
    assert verified is True


def test_an_unknown_version_is_refused(tmp_path):
    path = tmp_path / "desired.json"
    _save([_rec("a")], path)
    body = json.loads(path.read_text())
    body["version"] = 99
    path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="snapshot version is 99"):
        load_desired(path)


def test_a_bare_list_loads_but_is_not_verified(tmp_path, capsys):
    """The pre-v1 shape, and what a hand-written snapshot looks like. Readable,
    because refusing it would break a dry-run that never deletes — but it can
    prove nothing, so runner.plan_edge will not delete from it."""
    path = tmp_path / "desired.json"
    path.write_text(json.dumps([{"zone": "z.co", "name": "a", "rtype": "A",
                                 "values": ["1.1.1.1"], "ttl": 300}]))
    records, verified = load_desired(path)
    assert [r.name for r in records] == ["a"]
    assert verified is False
    assert "cannot be proven complete" in capsys.readouterr().err


def test_an_export_from_an_unproven_read_stays_unverified(tmp_path):
    """Provenance travels with the data: an unprovable SpatiumDDI read must not
    launder into a checksum-clean snapshot that CI then trusts to delete."""
    path = tmp_path / "desired.json"
    save_desired([_rec("a")], path, truth_verified=False)
    records, verified = load_desired(path)
    assert [r.name for r in records] == ["a"]
    assert verified is False


# --- --export shrink refusal ------------------------------------------------

def test_export_refuses_to_shrink_an_existing_snapshot(tmp_path):
    """SpatiumDDI restarted with an empty DB exports [] and exits 0; the
    committed snapshot then becomes a standing wipe order for the next apply."""
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b"), _rec("c")], path)

    with pytest.raises(SnapshotError, match="refusing to shrink"):
        _save([], path)
    with pytest.raises(SnapshotError, match="refusing to shrink"):
        _save([_rec("a")], path)

    assert len(load_desired(path).records) == 3  # untouched


def test_export_shrink_is_allowed_with_explicit_opt_in(tmp_path):
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b")], path)
    _save([_rec("a")], path, allow_shrink=True)
    assert [r.name for r in load_desired(path).records] == ["a"]


def test_export_may_grow_or_stay_the_same_size(tmp_path):
    path = tmp_path / "desired.json"
    _save([_rec("a")], path)
    _save([_rec("b"), _rec("c")], path)          # grew
    _save([_rec("d"), _rec("e")], path)          # same size, new content
    assert [r.name for r in load_desired(path).records] == ["d", "e"]


def test_export_still_shrink_checks_a_pre_v1_bare_list_prior(tmp_path):
    path = tmp_path / "desired.json"
    path.write_text(json.dumps([
        {"zone": "z.co", "name": "a", "rtype": "A", "values": ["1.1.1.1"], "ttl": 300},
        {"zone": "z.co", "name": "b", "rtype": "A", "values": ["1.1.1.1"], "ttl": 300},
    ]))
    with pytest.raises(SnapshotError, match="refusing to shrink"):
        _save([_rec("a")], path)


@pytest.mark.parametrize("body", [
    "",                                   # a half-written or emptied file
    "not json",                           # a hand-edit gone wrong
    '<<<<<<< HEAD\n[]\n=======\n[]\n',    # an unresolved merge conflict
    '{"version": 1, "count": 2, "checksum": "sha256:x", "records": []}',
    '{"version": 1, "records": [], "checksum": "sha256:x"}',   # no count
    '"a string"',
])
def test_export_refuses_to_overwrite_a_prior_it_cannot_read(tmp_path, body):
    """An unreadable prior used to be treated as 'nothing to lose' and silently
    overwritten with [] at exit 0."""
    path = tmp_path / "desired.json"
    path.write_text(body)
    with pytest.raises(SnapshotError, match="refusing to overwrite"):
        _save([], path)
    assert path.read_text() == body  # untouched


def test_overwriting_an_unreadable_prior_needs_the_explicit_opt_in(tmp_path):
    path = tmp_path / "desired.json"
    path.write_text("not json")
    _save([_rec("a")], path, allow_shrink=True)
    assert [r.name for r in load_desired(path).records] == ["a"]


def test_export_to_a_new_path_needs_no_prior(tmp_path):
    path = tmp_path / "brand-new.json"
    _save([], path)
    assert load_desired(path).records == []


def test_failed_write_leaves_the_committed_snapshot_intact(tmp_path, monkeypatch):
    """write_text() truncates in place: an interrupted export used to leave a
    partial file that CI then reads as truth."""
    path = tmp_path / "desired.json"
    _save([_rec("a"), _rec("b")], path)
    before = path.read_text()

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(desired_file.os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        _save([_rec("a"), _rec("b"), _rec("c")], path)
    assert path.read_text() == before


# --- malformed entries land on the exit contract, not on a traceback --------

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


@pytest.mark.parametrize("field", ["zone", "name", "rtype"])
def test_a_non_string_name_field_is_a_value_error_not_an_attributeerror(tmp_path, field):
    """`canonical_name(42)` raises AttributeError: 'int' object has no attribute
    'strip', which escapes the CLI's handled tuple and prints a traceback.
    config.py already closed this class; the snapshot path must match."""
    entry = {"zone": "z.co", "name": "x", "rtype": "A", "values": ["1.1.1.1"], "ttl": 300}
    entry[field] = 42
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([entry]))
    with pytest.raises(ValueError, match=f"{field!r} must be a string, got int"):
        load_desired(path)


@pytest.mark.parametrize("ttl", [["300"], {"seconds": 300}, None])
def test_a_non_integer_ttl_is_a_value_error_not_a_traceback(tmp_path, ttl):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"zone": "z.co", "name": "x", "rtype": "A",
                                 "values": ["1.1.1.1"], "ttl": ttl}]))
    with pytest.raises(ValueError, match="invalid snapshot"):
        load_desired(path)
