"""Cloudflare adapter — reconciled edge for the PUBLIC zone only.

API shape warning (the whole point of this adapter): Cloudflare models one
API record PER VALUE — a two-value A RRset is two API records sharing
(name, type). fetch_actual() groups API records into ONE CanonicalRecord per
RRset and builds a record-id index; apply() fans RRset-level changes back out
into per-record calls using that index. apply() therefore requires a
fetch_actual() earlier in the same run (the runner's plan-then-apply
ordering guarantees it).

Token: scoped API token — Zone.Zone:Read + Zone.DNS:Edit on this zone only.
"""
from __future__ import annotations

import ipaddress
import requests

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord, Diff

API = "https://api.cloudflare.com/client/v4"
_TIMEOUT = 10


class CloudflareProvider:
    def __init__(self, zone_name: str, api_token: str):
        self.zone_name = zone_name.strip().rstrip(".").lower()
        self._session = requests.Session()
        self._session.headers["Authorization"] = f"Bearer {api_token}"
        self._zone_id: str | None = None
        self._api_records: dict[tuple[str, str, str], list[dict]] = {}

    # --- plumbing -----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._session.request(method, f"{API}{path}", timeout=_TIMEOUT, **kwargs)
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"cloudflare API error on {path}: {exc}") from exc
        if not resp.ok or not body.get("success", False):
            raise RuntimeError(
                f"cloudflare API {resp.status_code} on {path}: {body.get('errors')}")
        return body

    def _zone(self) -> str:
        if self._zone_id is None:
            result = self._request("GET", f"/zones?name={self.zone_name}")["result"]
            if not result:
                raise RuntimeError(f"cloudflare API error: zone not found: {self.zone_name}")
            self._zone_id = result[0]["id"]
        return self._zone_id

    def _relative(self, fqdn: str) -> str:
        fqdn = fqdn.rstrip(".").lower()
        if fqdn == self.zone_name:
            return "@"
        suffix = "." + self.zone_name
        return fqdn[: -len(suffix)] if fqdn.endswith(suffix) else fqdn

    def _fqdn(self, name: str) -> str:
        return self.zone_name if name == "@" else f"{name}.{self.zone_name}"

    @staticmethod
    def _content(raw: dict) -> str:
        content = raw["content"]
        if raw["type"].upper() == "TXT" and len(content) >= 2 and content[0] == content[-1] == '"':
            content = content[1:-1]  # the API returns TXT content quoted
        return content

    @staticmethod
    def _match_key(rtype: str, content: str) -> str:
        # Mirror CanonicalRecord's domain-value normalization so canonical
        # values can look up raw API records regardless of case/trailing dot.
        # CNAME/PTR: lowercase and strip trailing dot.
        # AAAA: normalize IPv6 via ipaddress.IPv6Address (canonical form).
        if rtype in {"CNAME", "PTR"}:
            return content.rstrip(".").lower()
        elif rtype == "AAAA":
            try:
                return str(ipaddress.IPv6Address(content))
            except ValueError:
                # Invalid IPv6; fall back to raw content to avoid crashing fetch-only paths
                return content
        else:
            return content

    # --- provider contract --------------------------------------------------
    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        zone_id = self._zone()
        raw_records: list[dict] = []
        page = 1
        while True:
            body = self._request(
                "GET", f"/zones/{zone_id}/dns_records?per_page=100&page={page}")
            raw_records.extend(body["result"])
            if page >= body.get("result_info", {}).get("total_pages", 1):
                break
            page += 1

        self._api_records.clear()
        grouped: dict[tuple[str, str, str], dict] = {}
        for raw in raw_records:
            rtype = raw["type"].upper()
            if rtype not in SUPPORTED_RECORD_TYPES:
                continue
            key = (self.zone_name, self._relative(raw["name"]), rtype)
            self._api_records.setdefault(key, []).append(raw)
            entry = grouped.setdefault(key, {"values": [], "ttl": int(raw["ttl"])})
            entry["values"].append(self._content(raw))
        return [
            CanonicalRecord(zone=z, name=n, rtype=t,
                            values=tuple(e["values"]), ttl=e["ttl"])
            for (z, n, t), e in grouped.items()
        ]

    def _create(self, record: CanonicalRecord, value: str) -> None:
        self._request("POST", f"/zones/{self._zone()}/dns_records", json={
            "type": record.rtype, "name": self._fqdn(record.name),
            "content": value, "ttl": record.ttl, "proxied": False,
        })

    def apply(self, diff: Diff) -> None:
        zone_id = self._zone()
        for record in diff.to_add:
            for value in record.values:
                self._create(record, value)
        for update in diff.to_update:
            want, have = update.desired, update.actual
            existing = {
                self._match_key(want.rtype, self._content(r)): r
                for r in self._api_records.get(want.key, [])
            }
            for value in set(want.values) - set(have.values):
                self._create(want, value)
            for value in set(have.values) - set(want.values):
                if value not in existing:
                    raise RuntimeError(
                        f"cloudflare API state error: value {value!r} not in fetched index for {want.key}; "
                        f"apply() requires fetch_actual() in the same run")
                self._request("DELETE", f"/zones/{zone_id}/dns_records/{existing[value]['id']}")
            if want.ttl != have.ttl:
                for value in set(want.values) & set(have.values):
                    if value not in existing:
                        raise RuntimeError(
                            f"cloudflare API state error: value {value!r} not in fetched index for {want.key}; "
                            f"apply() requires fetch_actual() in the same run")
                    self._request("PATCH", f"/zones/{zone_id}/dns_records/{existing[value]['id']}",
                                  json={"ttl": want.ttl})
        for record in diff.to_delete:
            if record.key not in self._api_records or not self._api_records[record.key]:
                raise RuntimeError(
                    f"cloudflare API state error: no fetched records for {record.key}; "
                    f"apply() requires fetch_actual() in the same run")
            for raw in self._api_records.get(record.key, []):
                self._request("DELETE", f"/zones/{zone_id}/dns_records/{raw['id']}")
