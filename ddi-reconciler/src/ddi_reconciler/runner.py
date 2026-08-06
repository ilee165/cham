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
