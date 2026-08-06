"""Azure Private DNS adapter — reconciled edge for azure.dwsolution.co.

CRITICAL SAFETY: record sets with is_auto_registered=True belong to Azure VM
auto-registration and are dropped at fetch time — combined with the
managed-key allowlist in diff_records they can never be updated or deleted.

Auth: DefaultAzureCredential (az login locally; OIDC-federated in CI).
"""
from __future__ import annotations

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord, Diff


class AzureProvider:
    def __init__(self, subscription_id: str, resource_group: str, client=None):
        self.resource_group = resource_group
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
            try:
                record_sets = list(self._client.record_sets.list(self.resource_group, zone))
            except Exception as exc:  # azure.core exceptions -> CLI error contract
                raise RuntimeError(f"azure API error listing {zone}: {exc}") from exc
            for rs in record_sets:
                rtype = rs.type.rsplit("/", 1)[-1].upper()  # ".../privateDnsZones/A" -> "A"
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                if getattr(rs, "is_auto_registered", False):
                    continue
                values = self._values(rtype, rs)
                if not values:
                    continue
                records.append(CanonicalRecord(zone=zone, name=rs.name, rtype=rtype,
                                               values=values, ttl=int(rs.ttl) if rs.ttl is not None else 300))
        return records

    @staticmethod
    def _record_set_body(record: CanonicalRecord) -> dict:
        body: dict = {"ttl": record.ttl}
        if record.rtype == "A":
            body["a_records"] = [{"ipv4_address": v} for v in record.values]
        elif record.rtype == "AAAA":
            body["aaaa_records"] = [{"ipv6_address": v} for v in record.values]
        elif record.rtype == "CNAME":
            body["cname_record"] = {"cname": record.values[0]}
        elif record.rtype == "PTR":
            body["ptr_records"] = [{"ptrdname": v} for v in record.values]
        elif record.rtype == "TXT":
            body["txt_records"] = [{"value": [v]} for v in record.values]
        return body

    def apply(self, diff: Diff) -> None:
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
