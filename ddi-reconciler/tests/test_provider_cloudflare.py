"""Cloudflare adapter — HTTP mocked with responses. Exercises the RRset
grouping the docstring warns about."""
import pytest
import responses

from ddi_reconciler.model import CanonicalRecord, Diff, RecordUpdate
from ddi_reconciler.providers.cloudflare import CloudflareProvider

API = "https://api.cloudflare.com/client/v4"
Z = "dwsolution.co"


def register_zone():
    responses.get(f"{API}/zones?name={Z}",
                  json={"success": True, "result": [{"id": "zid"}]})


def register_records(result, total_pages=1):
    responses.get(f"{API}/zones/zid/dns_records?per_page=100&page=1",
                  json={"success": True, "result": result,
                        "result_info": {"total_pages": total_pages}})


@responses.activate
def test_fetch_groups_rrsets_dequotes_txt_and_maps_apex():
    register_zone()
    register_records([
        {"id": "1", "type": "A", "name": "api.dwsolution.co", "content": "1.1.1.1", "ttl": 300},
        {"id": "2", "type": "A", "name": "api.dwsolution.co", "content": "1.1.1.2", "ttl": 300},
        {"id": "3", "type": "TXT", "name": "dwsolution.co", "content": "\"marker\"", "ttl": 300},
        {"id": "4", "type": "MX", "name": "dwsolution.co", "content": "mail.x", "ttl": 300},
    ])
    records = CloudflareProvider(Z, "token").fetch_actual({Z})
    by_key = {r.key: r for r in records}
    assert by_key[(Z, "api", "A")].values == ("1.1.1.1", "1.1.1.2")   # ONE RRset, not two
    assert by_key[(Z, "@", "TXT")].values == ("marker",)
    assert len(records) == 2  # MX ignored


@responses.activate
def test_apply_fans_out_add_and_delete_per_value():
    register_zone()
    register_records([
        {"id": "old1", "type": "A", "name": "demo.dwsolution.co", "content": "9.9.9.9", "ttl": 300},
    ])
    provider = CloudflareProvider(Z, "token")
    actual = provider.fetch_actual({Z})[0]
    desired = CanonicalRecord(zone=Z, name="demo", rtype="A",
                              values=("9.9.9.8",), ttl=300)
    created = responses.post(f"{API}/zones/zid/dns_records",
                             json={"success": True, "result": {"id": "new1"}})
    deleted = responses.delete(f"{API}/zones/zid/dns_records/old1",
                               json={"success": True, "result": {"id": "old1"}})
    provider.apply(Diff(to_update=[RecordUpdate(desired=desired, actual=actual)]))
    assert created.call_count == 1
    assert deleted.call_count == 1


@responses.activate
def test_delete_removes_every_value_record():
    register_zone()
    register_records([
        {"id": "d1", "type": "A", "name": "gone.dwsolution.co", "content": "1.1.1.1", "ttl": 300},
        {"id": "d2", "type": "A", "name": "gone.dwsolution.co", "content": "1.1.1.2", "ttl": 300},
    ])
    provider = CloudflareProvider(Z, "token")
    actual = provider.fetch_actual({Z})[0]
    del1 = responses.delete(f"{API}/zones/zid/dns_records/d1", json={"success": True, "result": {}})
    del2 = responses.delete(f"{API}/zones/zid/dns_records/d2", json={"success": True, "result": {}})
    provider.apply(Diff(to_delete=[actual]))
    assert del1.call_count == 1 and del2.call_count == 1


@responses.activate
def test_api_error_is_runtime_error():
    responses.get(f"{API}/zones?name={Z}",
                  json={"success": False, "errors": [{"code": 9109, "message": "bad token"}]},
                  status=403)
    with pytest.raises(RuntimeError, match="cloudflare API"):
        CloudflareProvider(Z, "token").fetch_actual({Z})
