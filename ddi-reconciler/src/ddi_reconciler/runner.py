"""Per-edge reconcile pass: filter truth to the edge's managed set, diff, apply.

Provider duck-type contract:
    fetch_actual(zones: set[str]) -> list[CanonicalRecord]
    apply(diff: Diff) -> None
Both raise RuntimeError with a readable message on API failure.

The allowlist bounds *which* keys may change. It says nothing about whether
the desired set is trustworthy, so the two guards below cover the cases where
an absent desired record means "we were not told" rather than "delete this":
empty truth (EmptyTruthError) and a desired record that names a managed key
but was written so it does not match one (OwnershipError).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord, Diff, RecordKey
from ddi_reconciler.reconcile import diff_records


class ConvergenceError(RuntimeError):
    """apply() ran but a re-fetch still shows drift."""


class EmptyTruthError(RuntimeError):
    """Truth carries no managed record for an edge that still serves some."""


class OwnershipError(RuntimeError):
    """A desired record names a managed key but does not match one."""


class UnwritableKeyError(RuntimeError):
    """A managed key exists at the edge but the provider refuses to write it."""


@dataclass(frozen=True)
class EdgeResult:
    edge: EdgeConfig
    diff: Diff
    # Desired records in this edge's zone that are not in managed_keys. Kept
    # so the CLI can show what truth carried but the reconciler disclaims.
    dropped_desired: tuple[CanonicalRecord, ...] = field(default_factory=tuple)


def _candidate_fqdns(record: CanonicalRecord) -> tuple[str, ...]:
    """The DNS names this desired record could be describing: its own
    (zone, name) split read literally, and — because writing a full FQDN where
    a zone-relative name belongs is the common snapshot mistake — its `name`
    read as an FQDN in its own right."""
    literal = record.zone if record.name == "@" else f"{record.name}.{record.zone}"
    return (literal, record.name)


def _relative_to(fqdn: str, zone: str) -> str | None:
    """Zone-relative name for `fqdn` under `zone`, or None if it is not in it."""
    if fqdn == zone:
        return "@"
    if fqdn.endswith(f".{zone}"):
        return fqdn[: -len(zone) - 1]
    return None


def _near_miss_key(record: CanonicalRecord, edge: EdgeConfig) -> RecordKey | None:
    """The managed key this desired record names but does not match, if any."""
    for fqdn in _candidate_fqdns(record):
        relative = _relative_to(fqdn, edge.zone)
        if relative is None:
            continue
        key = (edge.zone, relative, record.rtype)
        if key in edge.managed_keys:
            return key
    return None


def _partition_desired(
    edge: EdgeConfig, desired_all: list[CanonicalRecord]
) -> tuple[list[CanonicalRecord], list[CanonicalRecord], list[tuple[CanonicalRecord, RecordKey]]]:
    """Split truth into (managed, dropped, near-misses) for this edge.

    SpatiumDDI legitimately models more records than the reconciler owns, so
    dropping an unowned record is normal. What is *not* normal is a desired
    record whose DNS name is exactly a managed key's but whose (zone, name)
    split is written differently — an FQDN where a zone-relative name belongs,
    say. Dropping that one silently empties the key's desired set, and an empty
    desired set for a live managed key is a delete order.
    """
    managed: list[CanonicalRecord] = []
    dropped: list[CanonicalRecord] = []
    near_misses: list[tuple[CanonicalRecord, RecordKey]] = []
    for record in desired_all:
        if record.zone == edge.zone and record.key in edge.managed_keys:
            managed.append(record)
            continue
        key = _near_miss_key(record, edge)
        if key is not None:
            near_misses.append((record, key))
        elif record.zone == edge.zone:
            dropped.append(record)
    return managed, dropped, near_misses


def plan_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider,
              *, allow_empty_truth: bool = False) -> EdgeResult:
    # Ownership filter: SpatiumDDI may model more records in the zone than the
    # reconciler owns; only the managed subset is desired state for this edge.
    desired, dropped, near_misses = _partition_desired(edge, desired_all)
    if near_misses:
        detail = "; ".join(
            f"{r.zone}/{r.name}/{r.rtype} names managed key {'/'.join(key)}"
            for r, key in sorted(near_misses, key=lambda pair: pair[1])
        )
        raise OwnershipError(
            f"edge {edge.name!r}: desired record(s) name a managed key without matching "
            f"it — {detail}. Ignoring them would leave the managed key with no desired "
            "state, which deletes the live record; fix the zone/name split in truth.")

    actual = provider.fetch_actual({edge.zone})

    # Keys the provider read but will not write: Azure VM auto-registration owns
    # them, or their record set could not be parsed. Either way they are absent
    # from `actual`, so a managed one would plan as ADD and fail only at apply.
    unwritable = sorted(
        ({*getattr(provider, "blocked_keys", ()), *getattr(provider, "unparseable_keys", ())})
        & set(edge.managed_keys))
    if unwritable:
        raise UnwritableKeyError(
            f"edge {edge.name!r}: managed key(s) {unwritable} are owned by the provider "
            "(Azure VM auto-registration) or unreadable at the edge, so the reconciler will "
            "not write them. Rename the VM or remove the key from managed_keys.")

    diff = diff_records(desired, actual, {edge.zone}, set(edge.managed_keys))

    # Fail closed on empty truth. "Truth returned nothing" and "these records
    # should not exist" are indistinguishable in the diff, and only one of them
    # should be allowed to delete every record the edge owns. No delete ceiling
    # is applied: a partial truth is WR-11/WR-12 territory, not a heuristic's.
    if not desired and edge.managed_keys and diff.to_delete and not allow_empty_truth:
        raise EmptyTruthError(
            f"edge {edge.name!r}: desired state carries no record for any managed key in "
            f"zone {edge.zone!r}, but the edge still serves {len(diff.to_delete)} managed "
            "record(s). Refusing to read empty truth as a delete order — this is what a "
            "SpatiumDDI outage, a re-scoped token, or a truncated snapshot looks like. "
            "Re-run with --allow-empty-truth if the zone really should be emptied.")

    return EdgeResult(edge=edge, diff=diff, dropped_desired=tuple(dropped))


def apply_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider,
               *, allow_empty_truth: bool = False) -> EdgeResult:
    result = plan_edge(edge, desired_all, provider, allow_empty_truth=allow_empty_truth)
    if result.diff.is_converged:
        return result
    provider.apply(result.diff)
    check = plan_edge(edge, desired_all, provider, allow_empty_truth=allow_empty_truth)
    if not check.diff.is_converged:
        raise ConvergenceError(f"edge {edge.name!r} still drifted after apply")
    return result
