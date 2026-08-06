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
