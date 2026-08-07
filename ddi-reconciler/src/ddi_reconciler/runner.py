"""Per-edge reconcile pass: filter truth to the edge's managed set, diff, apply.

Provider duck-type contract:
    fetch_actual(zones: set[str]) -> list[CanonicalRecord]
    apply(diff: Diff) -> None
Both raise RuntimeError with a readable message on API failure.

The allowlist bounds *which* keys may change. It says nothing about whether the
desired set is trustworthy, so the guards below cover the cases where an absent
desired record means "we were not told" rather than "delete this":

* empty truth — no managed record at all (EmptyTruthError);
* partial truth — a read that cannot be proven complete (UnverifiedTruthError);
* a desired record that names a managed key but was written so it does not
  match one (OwnershipError).

All three are one rule seen from three angles: DELETE is the destructive
direction, so it needs positive evidence that truth is whole. ADD and UPDATE
need no such evidence and are never gated by them — the worst an incomplete
truth can do through those is leave a record un-updated. There is deliberately
no delete ceiling anywhere: "more than N deletions" is a guess about magnitude,
while these are statements about whether the read happened.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord, Diff, RecordKey, RecordUpdate
from ddi_reconciler.reconcile import diff_records


class ConvergenceError(RuntimeError):
    """apply() ran but a re-fetch still shows drift."""


class EmptyTruthError(RuntimeError):
    """Truth carries no managed record for an edge that still serves some."""


class UnverifiedTruthError(RuntimeError):
    """A deletion was planned from a truth read that cannot be proven whole."""


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
    # Managed keys the provider reported as carrying disagreeing per-record
    # TTLs. Kept so the CLI can say why an RRset is being updated to the TTL
    # it already appears to have.
    split_ttl_keys: tuple[RecordKey, ...] = field(default_factory=tuple)


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

    That harm needs the key to end up with NO desired state, which is why a
    near miss is only a near miss when nothing else covers the key. Reading
    `record.name` as an FQDN regardless of `record.zone` otherwise trips over
    legitimate data: a record in azure.dwsolution.co named demo.dwsolution.co
    "names" the cloudflare edge's demo key, and used to abort that edge even
    with the real demo record sitting right there in truth.
    """
    managed: list[CanonicalRecord] = []
    dropped: list[CanonicalRecord] = []
    candidates: list[tuple[CanonicalRecord, RecordKey]] = []
    for record in desired_all:
        if record.zone == edge.zone and record.key in edge.managed_keys:
            managed.append(record)
            continue
        key = _near_miss_key(record, edge)
        if key is not None:
            candidates.append((record, key))
        elif record.zone == edge.zone:
            dropped.append(record)

    covered = {record.key for record in managed}
    near_misses: list[tuple[CanonicalRecord, RecordKey]] = []
    for record, key in candidates:
        if key in covered:
            # The key has proper desired state, so ignoring this record cannot
            # empty it — it is just an unowned record like any other.
            if record.zone == edge.zone:
                dropped.append(record)
        else:
            near_misses.append((record, key))
    return managed, dropped, near_misses


def _force_split_ttl_updates(diff: Diff, split_keys: tuple[RecordKey, ...],
                             desired: list[CanonicalRecord],
                             actual: list[CanonicalRecord]) -> None:
    """Make a split-TTL RRset drift even when its reported TTL matches desired.

    The provider reports one real TTL for an RRset that holds several, so a
    desired TTL equal to that one compares equal and the set reads converged
    while still serving two lifetimes. The split rides in split_ttl_keys rather
    than in the TTL scalar precisely so this cannot be papered over by choosing
    a number, and this is where that flag is spent: an UPDATE whose desired and
    actual values are identical still drives the provider's per-record TTL
    normalization.
    """
    pending = ({record.key for record in diff.to_add}
               | {update.desired.key for update in diff.to_update}
               | {record.key for record in diff.to_delete})
    desired_by_key = {record.key: record for record in desired}
    actual_by_key = {record.key: record for record in actual}
    for key in split_keys:
        if key in pending:
            continue  # already drifting for another reason
        want, have = desired_by_key.get(key), actual_by_key.get(key)
        if want is not None and have is not None:
            diff.to_update.append(RecordUpdate(desired=want, actual=have))


def plan_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider,
              *, truth_complete: bool = False, allow_empty_truth: bool = False,
              allow_unverified_truth: bool = False) -> EdgeResult:
    """Plan one edge. No writes.

    `truth_complete` is the caller's answer to "was the read that produced
    desired_all provably whole?" — a SpatiumDDI response that declared a count
    the adapter checked, or a snapshot whose own count and checksum verified.
    It defaults to False so a caller that has not established it cannot delete
    by omission; callers holding truth they constructed themselves (tests) pass
    True.
    """
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

    split_keys = tuple(sorted(
        set(getattr(provider, "split_ttl_keys", ())) & set(edge.managed_keys)))
    _force_split_ttl_updates(diff, split_keys, desired, actual)

    # Fail closed on empty truth. "Truth returned nothing" and "these records
    # should not exist" are indistinguishable in the diff, and only one of them
    # should be allowed to delete every record the edge owns.
    if not desired and edge.managed_keys and diff.to_delete and not allow_empty_truth:
        raise EmptyTruthError(
            f"edge {edge.name!r}: desired state carries no record for any managed key in "
            f"zone {edge.zone!r}, but the edge still serves {len(diff.to_delete)} managed "
            "record(s). Refusing to read empty truth as a delete order — this is what a "
            "SpatiumDDI outage, a re-scoped token, or a truncated snapshot looks like. "
            "Re-run with --allow-empty-truth if the zone really should be emptied.")

    # Fail closed on PARTIAL truth, which empty truth is only the extreme case
    # of. A read that carries some managed records but cannot prove it carries
    # all of them is silent about the rest, and silence is not a delete order.
    # Adds and updates are untouched by this: the check is on to_delete alone,
    # so an unprovable read still converges everything it does say.
    if diff.to_delete and not truth_complete and not allow_unverified_truth:
        raise UnverifiedTruthError(
            f"edge {edge.name!r}: planning {len(diff.to_delete)} deletion(s) from a desired "
            "state whose read could not be proven complete. A SpatiumDDI response that "
            "declares no total, or a snapshot with no count and checksum, cannot tell a "
            "whole read from a truncated one — and a managed record missing from a "
            "truncated read is indistinguishable from one truth says to remove. Re-export "
            "the snapshot with `cham-reconcile --export`, or re-run with "
            "--allow-unverified-truth to accept the deletion(s) anyway. Adds and updates "
            "are unaffected and need no flag.")

    return EdgeResult(edge=edge, diff=diff, dropped_desired=tuple(dropped),
                      split_ttl_keys=split_keys)


def apply_edge(edge: EdgeConfig, desired_all: list[CanonicalRecord], provider,
               *, truth_complete: bool = False, allow_empty_truth: bool = False,
               allow_unverified_truth: bool = False,
               on_mutate: Callable[[str], None] | None = None) -> EdgeResult:
    """Plan, apply, and verify one edge.

    `on_mutate` is called with the edge name immediately before the first write
    and only then, so the CLI can tell a refusal that provably wrote nothing
    from a failure that may have left the edge half-changed.
    """
    guards = dict(truth_complete=truth_complete, allow_empty_truth=allow_empty_truth,
                  allow_unverified_truth=allow_unverified_truth)
    result = plan_edge(edge, desired_all, provider, **guards)
    if result.diff.is_converged:
        return result
    if on_mutate is not None:
        on_mutate(edge.name)
    provider.apply(result.diff)
    check = plan_edge(edge, desired_all, provider, **guards)
    if not check.diff.is_converged:
        raise ConvergenceError(f"edge {edge.name!r} still drifted after apply")
    return result
