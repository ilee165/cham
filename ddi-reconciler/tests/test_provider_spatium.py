"""Spatium adapter — HTTP mocked with responses; no live stack needed."""
import pytest
import responses

from ddi_reconciler.providers.spatium import SpatiumProvider

BASE = "http://spatium.test"


@responses.activate
def test_fetch_desired_maps_groups_and_filters():
    responses.get(f"{BASE}/api/v1/dns/zones", json=[
        {"id": 1, "name": "azure.dwsolution.co."},
        {"id": 2, "name": "not-wanted.zone"},   # its records URL is never called
    ])
    responses.get(f"{BASE}/api/v1/dns/zones/1/records", json=[
        {"name": "app.azure.dwsolution.co.", "type": "A", "value": "10.10.4.30", "ttl": 300},
        {"name": "api.azure.dwsolution.co.", "type": "A", "value": "10.10.4.11", "ttl": 300},
        {"name": "api.azure.dwsolution.co.", "type": "a", "value": "10.10.4.10", "ttl": 300},
        {"name": "azure.dwsolution.co.", "type": "TXT", "value": "zone-marker", "ttl": 600},
        {"name": "srv.azure.dwsolution.co.", "type": "SRV", "value": "0 0 0 x"},
    ])
    records = SpatiumProvider(BASE, token="t").fetch_desired({"azure.dwsolution.co"})
    by_key = {r.key: r for r in records}
    assert by_key[("azure.dwsolution.co", "app", "A")].values == ("10.10.4.30",)
    assert by_key[("azure.dwsolution.co", "api", "A")].values == ("10.10.4.10", "10.10.4.11")
    assert by_key[("azure.dwsolution.co", "@", "TXT")].ttl == 600
    assert len(records) == 3  # SRV skipped; unwanted zone never fetched


@responses.activate
def test_api_failure_is_runtime_error():
    responses.get(f"{BASE}/api/v1/dns/zones", status=500)
    with pytest.raises(RuntimeError, match="spatium API error"):
        SpatiumProvider(BASE, token="").fetch_desired({"azure.dwsolution.co"})


@responses.activate
def test_auth_header_sent_when_token_present():
    responses.get(f"{BASE}/api/v1/dns/zones", json=[])
    SpatiumProvider(BASE, token="sekrit").fetch_desired({"azure.dwsolution.co"})
    assert responses.calls[0].request.headers["Authorization"] == "Bearer sekrit"


@responses.activate
def test_preserves_explicit_ttl_zero():
    responses.get(f"{BASE}/api/v1/dns/zones", json=[
        {"id": 1, "name": "test.zone."},
    ])
    responses.get(f"{BASE}/api/v1/dns/zones/1/records", json=[
        {"name": "zero.test.zone.", "type": "A", "value": "10.0.0.1", "ttl": 0},
    ])
    records = SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert len(records) == 1
    assert records[0].ttl == 0  # Must preserve explicit 0, not default to 300
