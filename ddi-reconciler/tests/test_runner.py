"""Per-edge orchestration with a fake provider — offline."""
import pytest

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord
from ddi_reconciler.runner import (
    ConvergenceError,
    EmptyTruthError,
    OwnershipError,
    UnwritableKeyError,
    apply_edge,
    plan_edge,
)

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


# --- CR-1: empty truth is not a delete order -------------------------------

def test_empty_truth_refuses_to_delete_every_managed_record():
    """Spatium reset / re-scoped token / truncated snapshot all look exactly
    like 'these records should not exist'. Only one of them may delete."""
    provider = FakeProvider([rec("app", "10.10.4.30")])
    with pytest.raises(EmptyTruthError, match="--allow-empty-truth"):
        plan_edge(EDGE, [], provider)


def test_empty_truth_guard_also_covers_apply_and_runs_before_any_mutation():
    provider = FakeProvider([rec("app", "10.10.4.30")])
    with pytest.raises(EmptyTruthError):
        apply_edge(EDGE, [], provider)
    assert provider.apply_calls == 0
    assert provider.actual  # nothing deleted


def test_empty_truth_guard_ignores_records_for_other_zones():
    """Truth that carries only another edge's zone is still empty for us."""
    provider = FakeProvider([rec("app", "10.10.4.30")])
    with pytest.raises(EmptyTruthError):
        plan_edge(EDGE, [rec("elsewhere", "1.2.3.4", zone="other.zone")], provider)


def test_empty_truth_is_allowed_with_explicit_opt_in():
    provider = FakeProvider([rec("app", "10.10.4.30")])
    result = apply_edge(EDGE, [], provider, allow_empty_truth=True)
    assert [r.name for r in result.diff.to_delete] == ["app"]
    assert provider.actual == []


def test_empty_truth_guard_does_not_fire_when_there_is_nothing_to_delete():
    """An edge that already serves nothing is converged, not a data-loss risk."""
    assert plan_edge(EDGE, [], FakeProvider([])).diff.is_converged


# --- WR-12: a desired record that names a managed key must not be dropped ---

def test_desired_record_written_as_an_fqdn_is_rejected_not_silently_dropped():
    """The key pre-filter used to drop this, leaving the managed key with an
    empty desired set — which deletes the live record and exits 0."""
    typo = CanonicalRecord(zone=Z, name=f"app.{Z}", rtype="A", values=("10.10.4.30",))
    provider = FakeProvider([rec("app", "10.10.4.30")])
    with pytest.raises(OwnershipError, match="names managed key"):
        plan_edge(EDGE, [typo], provider)


def test_desired_record_with_the_wrong_zone_name_split_is_rejected():
    """Same DNS name, different (zone, name) split: app.azure + dwsolution.co
    is the same name as app + azure.dwsolution.co."""
    split = CanonicalRecord(zone="dwsolution.co", name="app.azure", rtype="A",
                            values=("10.10.4.30",))
    with pytest.raises(OwnershipError, match="names managed key"):
        plan_edge(EDGE, [split], FakeProvider([rec("app", "10.10.4.30")]))


def test_unowned_records_in_the_managed_zone_are_reported_not_rejected():
    """Truth legitimately models more than the reconciler owns (Terraform
    seeds), so those are dropped — but visibly, not silently."""
    result = plan_edge(EDGE, [rec("app", "10.10.4.30"), rec("db", "10.10.4.20")],
                       FakeProvider([]))
    assert [r.name for r in result.diff.to_add] == ["app"]
    assert [r.name for r in result.dropped_desired] == ["db"]


def test_records_for_other_zones_are_not_reported_as_dropped():
    result = plan_edge(EDGE, [rec("app", "10.10.4.30"),
                              rec("other", "1.2.3.4", zone="unrelated.zone")],
                       FakeProvider([]))
    assert result.dropped_desired == ()


class BlockingProvider(FakeProvider):
    """A provider that read a record set it refuses to write — Azure VM
    auto-registration owns it, or it could not be parsed. Such keys are absent
    from fetch_actual(), so the diff cannot see them."""

    def __init__(self, actual, blocked_keys=(), unparseable_keys=()):
        super().__init__(actual)
        self.blocked_keys = set(blocked_keys)
        self.unparseable_keys = set(unparseable_keys)


@pytest.mark.parametrize("attr", ["blocked_keys", "unparseable_keys"])
def test_managed_key_the_provider_will_not_write_fails_the_plan(attr):
    """Without this the key plans as ADD — an upsert onto an auto-registered
    record set — and only fails at apply, after the plan claimed it would work."""
    provider = BlockingProvider([], **{attr: {(Z, "app", "A")}})
    with pytest.raises(UnwritableKeyError, match="will not write them"):
        plan_edge(EDGE, [rec("app", "10.10.4.30")], provider)


def test_unwritable_keys_outside_the_managed_set_are_ignored():
    """The reconciler disclaims them, so they are none of its business."""
    provider = BlockingProvider([], blocked_keys={(Z, "vm-test-01", "A")})
    result = plan_edge(EDGE, [rec("app", "10.10.4.30")], provider)
    assert [r.name for r in result.diff.to_add] == ["app"]


def test_providers_without_the_attributes_are_unaffected():
    """The hook is duck-typed: Cloudflare exposes neither set."""
    assert plan_edge(EDGE, [rec("app", "10.10.4.30")], FakeProvider([])).diff.to_add
