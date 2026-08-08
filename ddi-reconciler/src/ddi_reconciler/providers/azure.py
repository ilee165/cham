"""Azure Private DNS adapter — reconciled edge for azure.dwsolution.co.

CRITICAL SAFETY — record sets owned by Azure VM auto-registration are never
written. Dropping them at fetch time is not protection on its own: a dropped
record set is *invisible*, so a managed key that collides with an
auto-registered name reads as absent, becomes an ADD, and `create_or_update`
is a replace at the API level — the VM's own registration is clobbered while
the run reports success. The drop is therefore paired with a write-side
refusal: every dropped key is recorded in `blocked_keys`, and `apply()`
refuses the whole diff — before issuing any call — if it touches one.

`is_auto_registered` is `Optional[bool]` and read-only in the SDK, so anything
that is not exactly `False` (attribute missing, `None`, a string) is unknown
ownership and is blocked. Only an explicit `False` means "manual, safe to
write". Blocking is sticky for the life of the provider: over-blocking is the
safe direction, under-blocking is the bug this guard exists for.

`apply()` also requires that `fetch_actual()` read each written zone in the
same run — without that read `blocked_keys` is empty and the refusal would be
vacuous.

Record sets the model cannot canonicalize are skipped rather than fatal (the
reconciler disclaims ownership of most of the zone), but every skip is
surfaced on stderr and recorded, so `apply()` refuses to write blind over one
the reconciler *does* own.

Auth: DefaultAzureCredential (az login locally; OIDC-federated in CI).
"""
from __future__ import annotations

import sys

from ddi_reconciler.model import (
    SUPPORTED_RECORD_TYPES,
    CanonicalRecord,
    Diff,
    RecordKey,
    canonical_name,
    canonical_record_key,
)


class AzureProvider:
    def __init__(self, subscription_id: str, resource_group: str, client=None):
        self.resource_group = resource_group
        # (zone, name, rtype) keys that Azure VM auto-registration owns, or
        # whose ownership this run could not establish. apply() refuses them.
        self.blocked_keys: set[RecordKey] = set()
        # Edge record sets that failed canonicalization, key -> reason. Unowned
        # ones are none of the reconciler's business; owned ones must not be
        # written over blind, so apply() refuses those too.
        self.unparseable_keys: dict[RecordKey, str] = {}
        # Zones fetch_actual() actually read in this run.
        self._fetched_zones: set[str] = set()
        if client is None:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.privatedns import PrivateDnsManagementClient
            client = PrivateDnsManagementClient(DefaultAzureCredential(), subscription_id)
        self._client = client

    @staticmethod
    def _values(rtype: str, rs) -> tuple[str, ...]:
        if rtype == "A":
            return tuple(r.ipv4_address for r in rs.a_records or [])
        if rtype == "AAAA":
            return tuple(r.ipv6_address for r in rs.aaaa_records or [])
        if rtype == "CNAME":
            return (rs.cname_record.cname,) if rs.cname_record else ()
        if rtype == "PTR":
            return tuple(r.ptrdname for r in rs.ptr_records or [])
        if rtype == "TXT":
            return tuple("".join(r.value) for r in rs.txt_records or [])
        return ()

    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        records: list[CanonicalRecord] = []
        for zone in zones:
            zone_key = canonical_name(zone)
            try:
                record_sets = list(self._client.record_sets.list(self.resource_group, zone))
            except Exception as exc:  # azure.core exceptions -> CLI error contract
                raise RuntimeError(f"azure API error listing {zone}: {exc}") from exc
            self._fetched_zones.add(zone_key)
            for rs in record_sets:
                # A record set whose shape the SDK does not honour is an API
                # contract break, not a data problem: fail loud rather than
                # letting a bare AttributeError escape the exit-code contract.
                try:
                    rtype = str(rs.type).rsplit("/", 1)[-1].strip().upper()
                    name = str(rs.name)
                    raw_ttl = rs.ttl
                except (AttributeError, TypeError) as exc:
                    raise RuntimeError(
                        f"azure API error listing {zone}: record set is missing "
                        f"name/type/ttl ({exc})") from exc
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                key = canonical_record_key(zone_key, name, rtype)
                # Fail closed: only an explicit False is "manual, safe to write".
                if getattr(rs, "is_auto_registered", None) is not False:
                    self.blocked_keys.add(key)
                    continue
                try:
                    values = self._values(rtype, rs)
                except (AttributeError, TypeError) as exc:
                    raise RuntimeError(
                        f"azure API error listing {zone}: record set {name}/{rtype} has an "
                        f"unreadable value ({exc})") from exc
                if not values:
                    continue
                try:
                    records.append(CanonicalRecord(
                        zone=zone_key, name=name, rtype=rtype, values=values,
                        ttl=int(raw_ttl) if raw_ttl is not None else 300))
                except (TypeError, ValueError) as exc:
                    # WR-3: most of the zone is not ours. One malformed record
                    # the reconciler disclaims must not abort the whole run —
                    # but it is never swallowed: it is named on stderr and
                    # apply() refuses it if it turns out to be a managed key.
                    self.unparseable_keys[key] = str(exc)
                    print(f"warning: [azure] skipping unparseable record set "
                          f"{'/'.join(key)}: {exc}", file=sys.stderr)
        return records

    @staticmethod
    def _record_set_body(record: CanonicalRecord) -> dict:
        """Build the create_or_update body in the SDK's *wire* shape.

        This must be wire JSON — `{"properties": {"ttl": …, "aRecords": …}}` —
        not the RecordSet model's Python attribute names. The serializer maps
        each model attribute to a wire path (`ttl` -> `properties.ttl`,
        `a_records` -> `properties.aRecords`), and a flat snake_case dict
        matches neither, so *every field is silently dropped*: the call still
        returns 201 and Azure creates the record set with `ttl: 0` and an
        empty value list. Nothing raises; the record simply has no content.

        Measured against the live API — flat `{"ttl": 300, "a_records":
        [{"ipv4_address": …}]}` produced `ttl=0 a_records=[]`, while this
        shape and an explicit `RecordSet(...)` model both round-tripped
        correctly. A dict is kept (rather than importing the models) so the
        body stays a pure value that offline tests can assert on; see
        `test_record_set_body_deserializes_into_sdk_model`, which pins the
        shape against the real SDK model so a future rename cannot
        reintroduce a silently-empty write.
        """
        props: dict = {"ttl": record.ttl}
        if record.rtype == "A":
            props["aRecords"] = [{"ipv4Address": v} for v in record.values]
        elif record.rtype == "AAAA":
            props["aaaaRecords"] = [{"ipv6Address": v} for v in record.values]
        elif record.rtype == "CNAME":
            props["cnameRecord"] = {"cname": record.values[0]}
        elif record.rtype == "PTR":
            props["ptrRecords"] = [{"ptrdname": v} for v in record.values]
        elif record.rtype == "TXT":
            props["txtRecords"] = [{"value": [v]} for v in record.values]
        return {"properties": props}

    def _guard(self, records: list[CanonicalRecord]) -> None:
        """Refuse the whole diff before any call is issued.

        A per-record check would still let the writes ahead of the refused one
        land, so every write in the diff is vetted first and the diff is
        all-or-nothing.
        """
        unread = sorted({record.zone for record in records} - self._fetched_zones)
        if unread:
            raise RuntimeError(
                f"azure API error: apply() was asked to write zone(s) {unread} that "
                "fetch_actual() did not read in this run, so VM auto-registration state is "
                "unknown; apply() requires fetch_actual() in the same run")

        blocked = sorted({record.key for record in records} & self.blocked_keys)
        if blocked:
            raise RuntimeError(
                "azure API error: refusing to write record set(s) owned by Azure VM "
                f"auto-registration, or whose ownership is unknown: "
                f"{[' / '.join(key) for key in blocked]}. create_or_update is a replace, so "
                "this would clobber the VM's own registration. Rename the VM or remove the "
                "key from managed_keys.")

        unparseable = sorted({record.key for record in records} & set(self.unparseable_keys))
        if unparseable:
            detail = "; ".join(f"{'/'.join(key)}: {self.unparseable_keys[key]}"
                               for key in unparseable)
            raise RuntimeError(
                "azure API error: refusing to write managed record set(s) that could not be "
                f"read at the edge, so the diff for them is not trustworthy — {detail}")

    def apply(self, diff: Diff) -> None:
        self._guard([*diff.to_add, *(u.desired for u in diff.to_update), *diff.to_delete])
        try:
            for record in diff.to_add + [u.desired for u in diff.to_update]:
                self._client.record_sets.create_or_update(
                    self.resource_group, record.zone, record.rtype, record.name,
                    self._record_set_body(record))
            for record in diff.to_delete:
                self._client.record_sets.delete(
                    self.resource_group, record.zone, record.rtype, record.name)
        except Exception as exc:
            raise RuntimeError(f"azure API error applying diff: {exc}") from exc
