"""SpatiumDDI adapter — the SOURCE OF TRUTH side. Read-only: truth is never
written to by the reconciler.

Endpoint paths are a per-deployment seam: confirm against the running stack
(`curl -s $BASE/openapi.json`) and adjust the two constants if the release
differs. Value normalization (IP canonicalization, case, sorting) is
CanonicalRecord's job, not the adapter's.
"""
from __future__ import annotations

import requests

from ddi_reconciler.model import SUPPORTED_RECORD_TYPES, CanonicalRecord

ZONES_PATH = "/api/v1/dns/zones"
RECORDS_PATH = "/api/v1/dns/zones/{zone_id}/records"
_TIMEOUT = 10


class SpatiumProvider:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str) -> list[dict]:
        try:
            resp = self._session.get(f"{self.base_url}{path}", timeout=_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"spatium API error on {path}: {exc}") from exc
        body = resp.json()
        return body["items"] if isinstance(body, dict) and "items" in body else body

    @staticmethod
    def _relative(fqdn: str, zone: str) -> str:
        fqdn = fqdn.rstrip(".").lower()
        if fqdn == zone:
            return "@"
        if fqdn.endswith("." + zone):
            return fqdn[: -(len(zone) + 1)]
        return fqdn  # already zone-relative

    def fetch_desired(self, zones: set[str]) -> list[CanonicalRecord]:
        wanted = {z.strip().rstrip(".").lower() for z in zones}
        grouped: dict[tuple[str, str, str], dict] = {}
        for zone in self._get(ZONES_PATH):
            zone_name = zone["name"].strip().rstrip(".").lower()
            if zone_name not in wanted:
                continue
            for rec in self._get(RECORDS_PATH.format(zone_id=zone["id"])):
                rtype = rec["type"].strip().upper()
                if rtype not in SUPPORTED_RECORD_TYPES:
                    continue
                name = self._relative(rec["name"], zone_name)
                entry = grouped.setdefault(
                    (zone_name, name, rtype),
                    {"values": [], "ttl": int(rec["ttl"]) if rec.get("ttl") is not None else 300})
                entry["values"].append(str(rec["value"]))
        return [
            CanonicalRecord(zone=z, name=n, rtype=t,
                            values=tuple(e["values"]), ttl=e["ttl"])
            for (z, n, t), e in grouped.items()
        ]
