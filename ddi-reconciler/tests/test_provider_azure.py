"""Azure adapter — fake SDK client injected; no credentials, no network."""
from types import SimpleNamespace

import pytest

from ddi_reconciler.model import CanonicalRecord, Diff, RecordUpdate
from ddi_reconciler.providers.azure import AzureProvider

Z = "azure.dwsolution.co"


def record_set(name, rtype, *, ips=(), ttl=300, auto=False, cname=None, txt=()):
    return SimpleNamespace(
        name=name,
        type=f"Microsoft.Network/privateDnsZones/{rtype}",
        ttl=ttl,
        is_auto_registered=auto,
        a_records=[SimpleNamespace(ipv4_address=v) for v in ips] or None,
        aaaa_records=None,
        cname_record=SimpleNamespace(cname=cname) if cname else None,
        ptr_records=None,
        txt_records=[SimpleNamespace(value=[t]) for t in txt] or None,
    )


class FakeRecordSets:
    def __init__(self, listing):
        self.listing = listing
        self.upserts = []
        self.deletes = []

    def list(self, resource_group, zone):
        return iter(self.listing)

    def create_or_update(self, resource_group, zone, rtype, name, body):
        self.upserts.append((zone, rtype, name, body))

    def delete(self, resource_group, zone, rtype, name):
        self.deletes.append((zone, rtype, name))


def make_provider(listing):
    client = SimpleNamespace(record_sets=FakeRecordSets(listing))
    return AzureProvider("sub-id", "rg-cham-lab", client=client), client


def test_fetch_skips_auto_registered_and_unsupported():
    provider, _ = make_provider([
        record_set("app", "A", ips=["10.10.4.30"]),
        record_set("vm-test-app", "A", ips=["10.10.4.5"], auto=True),
        record_set("@", "SOA"),
    ])
    records = provider.fetch_actual({Z})
    assert [r.key for r in records] == [(Z, "app", "A")]


def test_fetch_maps_cname_and_txt():
    provider, _ = make_provider([
        record_set("alias", "CNAME", cname="Target.Example.com."),
        record_set("info", "TXT", txt=["marker"]),
    ])
    by_key = {r.key: r for r in provider.fetch_actual({Z})}
    assert by_key[(Z, "alias", "CNAME")].values == ("target.example.com",)
    assert by_key[(Z, "info", "TXT")].values == ("marker",)


def test_apply_upserts_adds_updates_and_deletes():
    provider, client = make_provider([])
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    gone = CanonicalRecord(zone=Z, name="old", rtype="A", values=("10.0.0.1",))
    provider.apply(Diff(to_add=[add], to_delete=[gone]))
    assert client.record_sets.upserts == [
        (Z, "A", "app", {"ttl": 300, "a_records": [{"ipv4_address": "10.10.4.30"}]})]
    assert client.record_sets.deletes == [(Z, "A", "old")]


def test_apply_updates_desired_record():
    provider, client = make_provider([])
    desired = CanonicalRecord(zone=Z, name="web", rtype="A", values=("10.10.5.1",), ttl=600)
    actual = CanonicalRecord(zone=Z, name="web", rtype="A", values=("10.10.4.1",))
    provider.apply(Diff(to_update=[RecordUpdate(desired=desired, actual=actual)]))
    assert client.record_sets.upserts == [
        (Z, "A", "web", {"ttl": 600, "a_records": [{"ipv4_address": "10.10.5.1"}]})]
    assert client.record_sets.deletes == []


def test_api_failure_is_runtime_error():
    class Exploding:
        def list(self, resource_group, zone):
            raise Exception("boom")
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=Exploding()))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.fetch_actual({Z})


def test_apply_error_on_create_or_update():
    class FailingRecordSets:
        def create_or_update(self, *args, **kwargs):
            raise Exception("create failed")
        def delete(self, *args, **kwargs):
            pass
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=FailingRecordSets()))
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[add]))


def test_apply_error_on_delete():
    class FailingRecordSets:
        def create_or_update(self, *args, **kwargs):
            pass
        def delete(self, *args, **kwargs):
            raise Exception("delete failed")
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=FailingRecordSets()))
    gone = CanonicalRecord(zone=Z, name="old", rtype="A", values=("10.0.0.1",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_delete=[gone]))


def test_fetch_preserves_ttl_zero():
    provider, _ = make_provider([
        record_set("edge", "A", ips=["10.10.4.30"], ttl=0),
    ])
    records = provider.fetch_actual({Z})
    assert len(records) == 1
    assert records[0].ttl == 0
