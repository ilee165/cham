"""SpatiumDDI adapter — the SOURCE OF TRUTH side.

Reads zones/records from the SpatiumDDI REST API (FastAPI control plane)
and maps them into CanonicalRecord. Read-only: truth is never written to
by the reconciler.

TODO(phase 4):
  - auth: token from SPATIUM_API_TOKEN env
  - GET zones, GET records per zone
  - map names to zone-relative form ("@" for apex); value normalization
    (IP canonicalization, case, sorting) is CanonicalRecord's job, not
    the adapter's
"""
from ddi_reconciler.model import CanonicalRecord


class SpatiumProvider:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def fetch_desired(self, zones: set[str]) -> list[CanonicalRecord]:
        raise NotImplementedError("Phase 4")
