"""Diff-logic tests — these run today, before any provider exists.
Being able to test the core with zero cloud credentials is part of the
design story."""
import pytest

from ddi_reconciler.model import CanonicalRecord, RecordUpdate
from ddi_reconciler.reconcile import diff_records

Z = "azure.dwsolution.co"
MANAGED = {Z}


def rec(name, *values, ttl=300, rtype="A", zone=Z):
    return CanonicalRecord(zone=zone, name=name, rtype=rtype,
                           values=tuple(values), ttl=ttl)


def test_managed_record_set_is_required():
    with pytest.raises(TypeError, match="managed_keys"):
        diff_records([], [], MANAGED)


def test_converged_is_noop():
    a = [rec("db", "10.10.4.20")]
    assert diff_records(a, a, MANAGED, managed_keys={a[0].key}).is_converged


def test_missing_record_is_add():
    desired = rec("db", "10.10.4.20")
    d = diff_records([desired], [], MANAGED, managed_keys={desired.key})
    assert d.to_add == [desired]
    assert not d.to_update
    assert not d.to_delete


def test_changed_value_is_update_not_add_delete():
    desired = rec("db", "10.10.4.99")
    drifted = rec("db", "10.10.4.20")
    d = diff_records([desired], [drifted], MANAGED, managed_keys={desired.key})

    assert d.to_update == [RecordUpdate(desired=desired, actual=drifted)]
    assert not d.to_add and not d.to_delete


def test_unmanaged_zone_untouched():
    stray = rec("vm1", "10.10.4.50", zone="other.zone")
    d = diff_records([], [stray], MANAGED, managed_keys=set())
    assert d.is_converged  # never delete what we don't own


def test_desired_record_outside_managed_zones_is_rejected():
    stray = rec("vm1", "10.10.4.50", zone="other.zone")

    with pytest.raises(ValueError, match="desired record is outside managed zones"):
        diff_records([stray], [], MANAGED, managed_keys={stray.key})


def test_unmanaged_record_inside_managed_zone_is_untouched():
    unrelated = rec("terraform-seed", "10.10.4.10")

    d = diff_records(
        [],
        [unrelated],
        MANAGED,
        managed_keys={(Z, "reconciled-record", "A")},
    )

    assert d.is_converged


def test_removed_managed_record_is_deleted():
    removed = rec("old-record", "10.10.4.10")

    d = diff_records([], [removed], MANAGED, managed_keys={removed.key})

    assert d.to_delete == [removed]
    assert not d.to_add
    assert not d.to_update


def test_desired_record_outside_managed_record_set_is_rejected():
    unexpected = rec("unexpected", "10.10.4.50")

    with pytest.raises(ValueError, match="desired record is outside managed record set"):
        diff_records(
            [unexpected],
            [],
            MANAGED,
            managed_keys={(Z, "expected", "A")},
        )


def test_managed_record_key_outside_managed_zones_is_rejected():
    with pytest.raises(ValueError, match="managed record key is outside managed zones"):
        diff_records(
            [],
            [],
            MANAGED,
            managed_keys={("other.zone", "db", "A")},
        )


def test_duplicate_desired_record_keys_are_rejected():
    first = rec("db", "10.10.4.20")
    duplicate = rec("DB", "10.10.4.21")

    with pytest.raises(ValueError, match="duplicate desired record key"):
        diff_records([first, duplicate], [], MANAGED, managed_keys={first.key})


def test_duplicate_actual_record_keys_are_rejected():
    first = rec("db", "10.10.4.20")
    duplicate = rec("DB", "10.10.4.21")

    with pytest.raises(ValueError, match="duplicate actual record key"):
        diff_records(
            [first],
            [first, duplicate],
            MANAGED,
            managed_keys={first.key},
        )


def test_value_order_does_not_create_false_drift():
    desired = CanonicalRecord(
        zone=Z,
        name="api",
        rtype="A",
        values=("10.10.4.10", "10.10.4.11"),
    )
    actual = CanonicalRecord(
        zone=Z,
        name="api",
        rtype="A",
        values=("10.10.4.11", "10.10.4.10"),
    )

    assert diff_records(
        [desired],
        [actual],
        MANAGED,
        managed_keys={desired.key},
    ).is_converged


def test_dns_identity_is_case_and_trailing_dot_insensitive():
    desired = CanonicalRecord(
        zone="Azure.DWSolution.co.",
        name="DB",
        rtype="a",
        values=("10.10.4.20",),
    )
    actual = rec("db", "10.10.4.20")

    assert diff_records(
        [desired],
        [actual],
        {"AZURE.DWSOLUTION.CO."},
        managed_keys={desired.key},
    ).is_converged


def test_managed_record_keys_use_canonical_dns_identity():
    record = rec("db", "10.10.4.20")

    d = diff_records(
        [record],
        [record],
        MANAGED,
        managed_keys={("AZURE.DWSOLUTION.CO.", "DB.", "a")},
    )

    assert d.is_converged


def test_duplicate_values_do_not_create_false_drift():
    desired = CanonicalRecord(
        zone=Z,
        name="api",
        rtype="A",
        values=("10.10.4.10", "10.10.4.10"),
    )
    actual = rec("api", "10.10.4.10")

    assert diff_records(
        [desired],
        [actual],
        MANAGED,
        managed_keys={desired.key},
    ).is_converged


def test_domain_name_values_are_case_and_trailing_dot_insensitive():
    desired = CanonicalRecord(
        zone=Z,
        name="app",
        rtype="CNAME",
        values=("Target.Example.COM.",),
    )
    actual = CanonicalRecord(
        zone=Z,
        name="app",
        rtype="CNAME",
        values=("target.example.com",),
    )

    assert diff_records(
        [desired],
        [actual],
        MANAGED,
        managed_keys={desired.key},
    ).is_converged


def test_a_record_values_are_whitespace_stripped():
    assert rec("db", " 10.10.4.20 ").values == ("10.10.4.20",)


def test_invalid_a_record_value_is_rejected():
    with pytest.raises(ValueError, match="invalid A record value"):
        rec("db", "not-an-ip")


def test_aaaa_values_are_canonicalized():
    record = rec("v6", "2001:DB8:0:0:0:0:0:1", rtype="AAAA")

    assert record.values == ("2001:db8::1",)


def test_aaaa_representation_does_not_create_false_drift():
    desired = rec("v6", "2001:DB8::1", rtype="AAAA")
    actual = rec("v6", "2001:db8:0:0:0:0:0:1", rtype="AAAA")

    assert diff_records(
        [desired],
        [actual],
        MANAGED,
        managed_keys={desired.key},
    ).is_converged


def test_invalid_aaaa_record_value_is_rejected():
    with pytest.raises(ValueError, match="invalid AAAA record value"):
        rec("v6", "10.10.4.20", rtype="AAAA")


def test_cname_root_value_is_rejected():
    with pytest.raises(ValueError, match="record values must be non-empty strings"):
        rec("app", ".", rtype="CNAME")


def test_multi_value_cname_is_rejected():
    with pytest.raises(ValueError, match="CNAME records must have exactly one value"):
        rec("app", "a.example.com", "b.example.com", rtype="CNAME")


def test_cname_duplicate_spellings_collapse_to_one_value():
    record = rec("app", "Target.Example.COM.", "target.example.com", rtype="CNAME")

    assert record.values == ("target.example.com",)


def test_txt_values_strip_whitespace_but_keep_case_and_dots():
    record = rec("info", "  v=spf1 Example.COM.  ", rtype="TXT")

    assert record.values == ("v=spf1 Example.COM.",)


def test_ttl_only_change_is_update():
    desired = rec("db", "10.10.4.20", ttl=60)

    d = diff_records(
        [desired],
        [rec("db", "10.10.4.20", ttl=300)],
        MANAGED,
        managed_keys={desired.key},
    )

    assert len(d.to_update) == 1 and not d.to_add and not d.to_delete


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"zone": ""}, "zone must not be empty"),
        ({"name": ""}, "name must not be empty"),
        ({"rtype": ""}, "record type must not be empty"),
        ({"rtype": "BOGUS"}, "unsupported record type"),
        ({"values": ()}, "values must not be empty"),
        ({"values": ("",)}, "record values must be non-empty strings"),
        ({"values": (" ",)}, "record values must be non-empty strings"),
        ({"ttl": -1}, "TTL must be a non-negative integer"),
    ],
)
def test_invalid_canonical_records_are_rejected(overrides, message):
    fields = {
        "zone": Z,
        "name": "db",
        "rtype": "A",
        "values": ("10.10.4.20",),
        "ttl": 300,
    }
    fields.update(overrides)

    with pytest.raises(ValueError, match=message):
        CanonicalRecord(**fields)
