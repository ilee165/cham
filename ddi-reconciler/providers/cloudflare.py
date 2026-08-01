"""Cloudflare adapter — reconciled edge for the PUBLIC zone only.

Scoped API token (Zone:DNS:Edit on the one zone). The reconciler manages a
declared subset of public records; everything else in the zone is ignored
through the explicit managed-record key set passed to diff_records.

API shape warning: Cloudflare models one API record PER VALUE — a two-value
A RRset is two API records sharing (name, type). This adapter owns the
translation in both directions:
  - fetch_actual: group API records by (name, type) and aggregate their
    contents into ONE CanonicalRecord per RRset. A naive 1:1 mapping yields
    duplicate canonical keys and diff_records fails the whole run.
  - apply: fan each RRset-level change back out into per-record API calls
    (create missing values, delete removed ones, patch TTLs record by
    record).

TODO(phase 4): fetch_actual(), apply(diff)
"""
from ddi_reconciler.model import CanonicalRecord, Diff


class CloudflareProvider:
    def __init__(self, zone_name: str, api_token: str):
        self.zone_name = zone_name
        self.api_token = api_token

    def fetch_actual(self, zones: set[str]) -> list[CanonicalRecord]:
        raise NotImplementedError("Phase 4")

    def apply(self, diff: Diff) -> None:
        raise NotImplementedError("Phase 4")
