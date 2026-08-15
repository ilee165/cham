"""Unit tests for the _FieldLookup tri-state (2026-08-15 smell remediation).

These pin the TYPE, not the CR-02 behavior — the pagination-verification
suite in test_provider_spatium.py owns the behavior and passed unmodified
across the refactor that introduced this type. What must hold here is that
the three states stay mutually exclusive and that the poison rule lives in
the lookup itself, so a future caller cannot quietly read a value out of a
malformed result.
"""

from ddi_reconciler.providers.spatium import _first_int_field


def test_found_carries_key_and_value():
    lookup = _first_int_field({"total": "5"}, ("total", "count"))
    assert lookup.key == "total"
    assert lookup.value == 5
    assert not lookup.malformed


def test_absent_carries_nothing():
    lookup = _first_int_field({}, ("total", "count"))
    assert lookup.key is None
    assert lookup.value is None
    assert not lookup.malformed


def test_malformed_carries_nothing():
    # A malformed lookup must not expose a key or value: navigation code that
    # checks `.value is not None` then treats malformed exactly like absent,
    # while the latch still sees `.malformed`.
    lookup = _first_int_field({"total": 1.9}, ("total",))
    assert lookup.malformed
    assert lookup.key is None
    assert lookup.value is None


def test_malformed_poisons_later_aliases():
    # {"total": 1.9, "count": 1} must not certify via "count" (CR-02): the
    # poison rule is a property of the lookup, not of its call sites.
    lookup = _first_int_field({"total": 1.9, "count": 1}, ("total", "count"))
    assert lookup.malformed
    assert lookup.value is None


def test_first_recognized_key_wins():
    lookup = _first_int_field({"count": 2, "total": 3}, ("total", "count"))
    assert lookup.key == "total"
    assert lookup.value == 3
