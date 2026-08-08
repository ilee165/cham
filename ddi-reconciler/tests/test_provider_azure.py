"""Azure adapter — fake SDK client injected; no credentials, no network."""
from types import SimpleNamespace

import pytest

from ddi_reconciler.config import EdgeConfig
from ddi_reconciler.model import CanonicalRecord, Diff, RecordUpdate
from ddi_reconciler.providers.azure import AzureProvider
from ddi_reconciler.runner import UnwritableKeyError, apply_edge

Z = "azure.dwsolution.co"

# "the SDK model does not carry the attribute at all" — distinct from None.
UNSET = object()


def record_set(name, rtype, *, ips=(), ttl=300, auto=False, cname=None, txt=()):
    fields = dict(
        name=name,
        type=f"Microsoft.Network/privateDnsZones/{rtype}",
        ttl=ttl,
        a_records=[SimpleNamespace(ipv4_address=v) for v in ips] or None,
        aaaa_records=None,
        cname_record=SimpleNamespace(cname=cname) if cname else None,
        ptr_records=None,
        txt_records=[SimpleNamespace(value=[t]) for t in txt] or None,
    )
    if auto is not UNSET:
        fields["is_auto_registered"] = auto
    return SimpleNamespace(**fields)


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
    # Dropped, but not forgotten: the key is blocked for writes as well.
    assert provider.blocked_keys == {(Z, "vm-test-app", "A")}


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
    provider.fetch_actual({Z})
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    gone = CanonicalRecord(zone=Z, name="old", rtype="A", values=("10.0.0.1",))
    provider.apply(Diff(to_add=[add], to_delete=[gone]))
    assert client.record_sets.upserts == [
        (Z, "A", "app",
         {"properties": {"ttl": 300, "aRecords": [{"ipv4Address": "10.10.4.30"}]}})]
    assert client.record_sets.deletes == [(Z, "A", "old")]


def test_apply_updates_desired_record():
    provider, client = make_provider([])
    provider.fetch_actual({Z})
    desired = CanonicalRecord(zone=Z, name="web", rtype="A", values=("10.10.5.1",), ttl=600)
    actual = CanonicalRecord(zone=Z, name="web", rtype="A", values=("10.10.4.1",))
    provider.apply(Diff(to_update=[RecordUpdate(desired=desired, actual=actual)]))
    assert client.record_sets.upserts == [
        (Z, "A", "web",
         {"properties": {"ttl": 600, "aRecords": [{"ipv4Address": "10.10.5.1"}]}})]
    assert client.record_sets.deletes == []


@pytest.mark.parametrize("rtype,values,read_back", [
    ("A", ("10.10.4.30",), lambda rs: [r.ipv4_address for r in rs.a_records or []]),
    ("AAAA", ("2001:db8::1",), lambda rs: [r.ipv6_address for r in rs.aaaa_records or []]),
    ("CNAME", ("www.dwsolution.co",), lambda rs: [rs.cname_record.cname]),
    ("PTR", ("host.lab.dwsolution.co.",), lambda rs: [r.ptrdname for r in rs.ptr_records or []]),
    ("TXT", ("managed-by=ddi-reconciler",), lambda rs: [v for r in rs.txt_records or [] for v in r.value]),
])
def test_record_set_body_deserializes_into_sdk_model(rtype, values, read_back):
    """The write body must survive the real SDK model, not just our fake client.

    Regression test for a live-only defect: `_record_set_body` emitted the
    RecordSet model's *Python attribute* names flat at the top level
    (`{"ttl": 300, "a_records": [{"ipv4_address": …}]}`). The serializer maps
    those attributes to wire paths under `properties`, so every field was
    dropped, `create_or_update` still returned success, and Azure created the
    record set with `ttl: 0` and no values. The fake client in these tests
    stores whatever dict it is handed, so nothing here failed — the whole
    suite stayed green while `--apply` silently wrote empty record sets.

    Constructing the SDK's own RecordSet from the body closes that gap and
    needs no credentials or network. Under the old shape this asserts
    `ttl is None` and an empty value list.
    """
    RecordSet = pytest.importorskip("azure.mgmt.privatedns.models").RecordSet
    record = CanonicalRecord(zone=Z, name="x", rtype=rtype, values=values, ttl=300)
    rs = RecordSet(AzureProvider._record_set_body(record))
    assert rs.ttl == 300
    # against record.values, not the literal input: CanonicalRecord normalizes
    # (PTR loses its trailing dot), and the body is built from the canonical form.
    assert read_back(rs) == list(record.values)


def test_api_failure_is_runtime_error():
    class Exploding:
        def list(self, resource_group, zone):
            raise Exception("boom")
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=Exploding()))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.fetch_actual({Z})


def test_apply_error_on_create_or_update():
    class FailingRecordSets:
        def list(self, resource_group, zone):
            return iter(())
        def create_or_update(self, *args, **kwargs):
            raise Exception("create failed")
        def delete(self, *args, **kwargs):
            pass
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=FailingRecordSets()))
    provider.fetch_actual({Z})
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[add]))


def test_apply_error_on_delete():
    class FailingRecordSets:
        def list(self, resource_group, zone):
            return iter(())
        def create_or_update(self, *args, **kwargs):
            pass
        def delete(self, *args, **kwargs):
            raise Exception("delete failed")
    provider = AzureProvider("sub-id", "rg", client=SimpleNamespace(record_sets=FailingRecordSets()))
    provider.fetch_actual({Z})
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


# --- CR-6: auto-registered record sets are blocked, not merely hidden -------

@pytest.mark.parametrize("auto,manual", [
    (UNSET, False),   # attribute absent entirely (older API version)
    (None, False),    # SDK declares Optional[bool]; None is a real service state
    (True, False),
    ("true", False),  # a truthy non-bool must not read as "manual" either
    (False, True),    # only an explicit False means "manual, safe to write"
])
def test_auto_registration_guard_fails_closed(auto, manual):
    provider, _ = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=auto)])
    records = provider.fetch_actual({Z})
    assert bool(records) is manual
    assert ((Z, "app", "A") in provider.blocked_keys) is not manual


@pytest.mark.parametrize("auto", [UNSET, None, True, "true"])
def test_apply_never_writes_a_blocked_key(auto):
    """The whole point of CR-6: the key reads as *absent*, so the diff says ADD.
    The write must still be refused, and refused loudly."""
    provider, client = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=auto)])
    assert provider.fetch_actual({Z}) == []          # invisible to the diff...
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[add]))           # ...but not writable
    assert client.record_sets.upserts == []
    assert client.record_sets.deletes == []


def test_apply_never_updates_or_deletes_a_blocked_key():
    provider, client = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=True)])
    provider.fetch_actual({Z})
    want = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    have = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.99",))
    with pytest.raises(RuntimeError, match="auto-registration"):
        provider.apply(Diff(to_update=[RecordUpdate(desired=want, actual=have)]))
    with pytest.raises(RuntimeError, match="auto-registration"):
        provider.apply(Diff(to_delete=[have]))
    assert client.record_sets.upserts == []
    assert client.record_sets.deletes == []


def test_blocked_key_aborts_the_whole_diff_before_any_write():
    """All-or-nothing: a per-record check would let the writes ordered ahead of
    the blocked one land before the refusal."""
    provider, client = make_provider([
        record_set("app", "A", ips=["10.10.4.99"], auto=True),
        record_set("web", "A", ips=["10.10.4.1"]),
    ])
    provider.fetch_actual({Z})
    safe = CanonicalRecord(zone=Z, name="web", rtype="A", values=("10.10.5.1",))
    blocked = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[safe, blocked]))
    assert client.record_sets.upserts == []


def test_apply_requires_fetch_actual_in_the_same_run():
    """Without the read there is no blocked_keys to consult, so the refusal
    would be vacuous — refuse the write instead."""
    provider, client = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=True)])
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="requires fetch_actual"):
        provider.apply(Diff(to_add=[add]))
    assert client.record_sets.upserts == []


def test_apply_edge_refuses_to_clobber_an_auto_registered_collision():
    """CR-6 reproduction through the real plan/apply path: managed key
    ('azure.dwsolution.co','app','A') collides with a VM that auto-registered
    the same name. Previously: ADD -> create_or_update -> exit 0.

    The refusal now comes from runner.plan_edge, which consults blocked_keys
    and stops before a plan is even produced — so --dry-run tells the truth
    too, instead of printing ADD for a write that could never land. The
    provider-side guard below remains as defense in depth for any caller that
    reaches apply() directly."""
    provider, client = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=True)])
    edge = EdgeConfig(name="azure-private", provider="azure", zone=Z,
                      managed_keys=frozenset({(Z, "app", "A")}))
    desired = [CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))]
    with pytest.raises(UnwritableKeyError, match="will not write them"):
        apply_edge(edge, desired, provider)
    assert client.record_sets.upserts == []
    assert client.record_sets.deletes == []


def test_provider_still_refuses_the_collision_when_apply_is_called_directly():
    """Defense in depth: the runner hook is not the only thing standing between
    an auto-registered record set and a create_or_update."""
    provider, client = make_provider([record_set("app", "A", ips=["10.10.4.99"], auto=True)])
    provider.fetch_actual({Z})
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[add]))
    assert client.record_sets.upserts == []
    assert client.record_sets.deletes == []


# --- WR-3: one unowned malformed record must not abort the run -------------

def test_unparseable_unowned_record_is_skipped_and_surfaced(capsys):
    provider, _ = make_provider([
        record_set("someone-elses", "A", ips=[None]),   # null ipv4_address
        record_set("app", "A", ips=["10.10.4.30"]),
    ])
    records = provider.fetch_actual({Z})
    assert [r.key for r in records] == [(Z, "app", "A")]
    assert (Z, "someone-elses", "A") in provider.unparseable_keys
    warning = capsys.readouterr().err
    assert "someone-elses" in warning and "azure" in warning


def test_apply_refuses_a_managed_key_that_could_not_be_read():
    """Skipping is only safe for records the reconciler does not own: writing
    blind over one it does own is the CR-6 shape again."""
    provider, client = make_provider([record_set("app", "A", ips=[None])])
    provider.fetch_actual({Z})
    add = CanonicalRecord(zone=Z, name="app", rtype="A", values=("10.10.4.30",))
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.apply(Diff(to_add=[add]))
    assert client.record_sets.upserts == []


# --- SDK-shape audit: no bare AttributeError escapes the exit contract ------

def test_record_set_without_value_attribute_is_azure_api_error():
    rs = SimpleNamespace(name="app", type="Microsoft.Network/privateDnsZones/A",
                         ttl=300, is_auto_registered=False)   # no a_records at all
    provider, _ = make_provider([rs])
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.fetch_actual({Z})


def test_record_set_without_name_is_azure_api_error():
    rs = SimpleNamespace(type="Microsoft.Network/privateDnsZones/A", ttl=300,
                         is_auto_registered=False)
    provider, _ = make_provider([rs])
    with pytest.raises(RuntimeError, match="azure API error"):
        provider.fetch_actual({Z})


def test_non_integer_ttl_is_skipped_not_a_traceback(capsys):
    provider, _ = make_provider([record_set("app", "A", ips=["10.10.4.30"], ttl="soon")])
    assert provider.fetch_actual({Z}) == []
    assert (Z, "app", "A") in provider.unparseable_keys
    assert "app" in capsys.readouterr().err
