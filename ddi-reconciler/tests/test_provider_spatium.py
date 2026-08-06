"""Spatium adapter — HTTP mocked with responses; no live stack needed."""
import pytest
import responses

from ddi_reconciler.providers.spatium import SpatiumProvider

BASE = "http://spatium.test"
ZONES = f"{BASE}/api/v1/dns/zones"
RECORDS = f"{BASE}/api/v1/dns/zones/1/records"


def rec(name, value="10.0.0.1", rtype="A", ttl=300):
    return {"name": f"{name}.test.zone.", "type": rtype, "value": value, "ttl": ttl}


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


# --- WR-11: read every page, and prove afterwards that the read was whole ---

@responses.activate
def test_wrapped_single_page_still_works():
    responses.get(ZONES, json={"items": [{"id": 1, "name": "test.zone."}], "total": 1})
    responses.get(RECORDS, json={"items": [rec("a")], "total": 1})
    records = SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert [r.name for r in records] == ["a"]


@responses.activate
def test_follows_an_explicit_next_link():
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a", "10.0.0.1")], "total": 2,
                                 "next": "/api/v1/dns/zones/1/records?page=2"})
    responses.get(RECORDS, json={"items": [rec("b", "10.0.0.2")], "total": 2, "next": None})
    records = SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert {r.name for r in records} == {"a", "b"}   # page 2 is not a delete order
    assert "page=2" in responses.calls[-1].request.url


@responses.activate
def test_follows_a_page_numbered_envelope():
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a", "10.0.0.1")],
                                 "page": 1, "pages": 2, "size": 1, "total": 2})
    responses.get(RECORDS, json={"items": [rec("b", "10.0.0.2")],
                                 "page": 2, "pages": 2, "size": 1, "total": 2})
    records = SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert {r.name for r in records} == {"a", "b"}
    assert "page=2" in responses.calls[-1].request.url


@responses.activate
def test_follows_an_offset_limit_envelope():
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a", "10.0.0.1")],
                                 "total": 2, "limit": 1, "offset": 0})
    responses.get(RECORDS, json={"items": [rec("b", "10.0.0.2")],
                                 "total": 2, "limit": 1, "offset": 1})
    records = SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert {r.name for r in records} == {"a", "b"}
    assert "offset=1" in responses.calls[-1].request.url


@responses.activate
def test_short_read_against_a_declared_total_is_fatal():
    """The whole WR-11 point: page 1 only, and 'absent from truth' downstream
    means to_delete. Fail closed instead."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a")], "total": 5, "next": None})
    with pytest.raises(RuntimeError, match="spatium API error.*declares 5"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


@responses.activate
def test_unrecognized_envelope_is_fatal_not_an_empty_page():
    responses.get(ZONES, json={"payload": [{"id": 1, "name": "test.zone."}]})
    with pytest.raises(RuntimeError, match="unrecognized response envelope"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


@responses.activate
def test_collection_key_holding_a_non_list_is_fatal():
    responses.get(ZONES, json={"items": {"id": 1}})
    with pytest.raises(RuntimeError, match="spatium API error"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


@responses.activate
def test_next_link_off_the_configured_host_is_refused():
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a")], "total": 2,
                                 "next": "http://evil.test/api/v1/dns/zones/1/records"})
    with pytest.raises(RuntimeError, match="leaves the configured base_url"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert len(responses.calls) == 2   # the bearer token never left the host


@responses.activate
def test_pagination_that_does_not_advance_is_fatal():
    """An envelope this adapter walks the wrong way must not silently loop or
    silently duplicate — it must stop the run."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a")], "total": 4, "limit": 1, "offset": 0})
    with pytest.raises(RuntimeError, match="did not advance"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


# --- CR-1: a read that cannot be checked is unproven, not "probably whole" --

@responses.activate
def test_a_declared_total_the_adapter_checked_marks_the_read_verified():
    responses.get(ZONES, json={"items": [{"id": 1, "name": "test.zone."}], "total": 1})
    responses.get(RECORDS, json={"items": [rec("a"), rec("b", "10.0.0.2")], "total": 2})
    provider = SpatiumProvider(BASE, token="t")
    assert len(provider.fetch_desired({"test.zone"})) == 2
    assert provider.read_verified is True


@responses.activate
def test_a_bare_list_body_leaves_the_read_unproven():
    """Nothing in a bare list distinguishes 'that was everything' from 'the
    server truncated it'. Downstream, the difference is a delete order."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json=[rec("a")])
    provider = SpatiumProvider(BASE, token="t")
    assert [r.name for r in provider.fetch_desired({"test.zone"})] == ["a"]
    assert provider.read_verified is False


@responses.activate
def test_an_envelope_with_no_total_leaves_the_read_unproven():
    responses.get(ZONES, json={"items": [{"id": 1, "name": "test.zone."}], "total": 1})
    responses.get(RECORDS, json={"items": [rec("a")]})
    provider = SpatiumProvider(BASE, token="t")
    provider.fetch_desired({"test.zone"})
    assert provider.read_verified is False


@responses.activate
def test_an_unproven_zone_listing_taints_the_whole_read():
    """A zone that never arrives drops every record in it, so the records
    endpoint declaring its own total is not enough."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json={"items": [rec("a")], "total": 1})
    provider = SpatiumProvider(BASE, token="t")
    provider.fetch_desired({"test.zone"})
    assert provider.read_verified is False


@responses.activate
def test_one_unproven_page_among_verified_ones_taints_the_read():
    responses.get(ZONES, json={"items": [{"id": 1, "name": "test.zone."},
                                         {"id": 2, "name": "other.zone."}],
                               "total": 2})
    responses.get(RECORDS, json={"items": [rec("a")], "total": 1})
    responses.get(f"{BASE}/api/v1/dns/zones/2/records", json=[rec("b", "10.0.0.2")])
    provider = SpatiumProvider(BASE, token="t")
    provider.fetch_desired({"test.zone", "other.zone"})
    assert provider.read_verified is False


def test_an_unread_provider_has_proven_nothing():
    assert SpatiumProvider(BASE, token="t").read_verified is False


# --- malformed payloads land on the exit contract, not on a traceback ------

@responses.activate
@pytest.mark.parametrize("zones_json", [
    [{"id": 1}],                       # zone entry without a name
    [{"name": "test.zone."}],          # zone entry without an id
    ["test.zone."],                    # not an object at all
])
def test_malformed_zone_payload_is_spatium_api_error(zones_json):
    responses.get(ZONES, json=zones_json)
    responses.get(RECORDS, json=[])
    with pytest.raises(RuntimeError, match="spatium API error"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


@responses.activate
@pytest.mark.parametrize("record_json", [
    {"name": "a.test.zone.", "value": "10.0.0.1", "ttl": 300},   # no type
    {"type": "A", "value": "10.0.0.1", "ttl": 300},              # no name
    {"name": "a.test.zone.", "type": "A", "ttl": 300},           # no value
    {"name": "a.test.zone.", "type": "A", "value": "10.0.0.1", "ttl": "soon"},
    "a.test.zone. A 10.0.0.1",                                   # not an object
])
def test_malformed_record_payload_is_spatium_api_error(record_json):
    """Regression: these were bare KeyErrors, which now escape the CLI's
    handled tuple entirely and print a traceback instead of exiting 1."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json=[record_json])
    with pytest.raises(RuntimeError, match="spatium API error"):
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})


@responses.activate
def test_unreadable_truth_record_is_named_and_fatal():
    """Truth side, unlike the edge side, must not skip: a desired record that
    never arrives is a delete order for that key."""
    responses.get(ZONES, json=[{"id": 1, "name": "test.zone."}])
    responses.get(RECORDS, json=[rec("broken", value="   ")])
    with pytest.raises(RuntimeError, match="spatium API error") as exc:
        SpatiumProvider(BASE, token="t").fetch_desired({"test.zone"})
    assert "test.zone/broken/A" in str(exc.value)


# --- IN-2: plaintext bearer token ------------------------------------------

def test_plaintext_non_loopback_base_url_warns(capsys):
    SpatiumProvider("http://spatium.internal:8000", token="sekrit")
    assert "plaintext" in capsys.readouterr().err


@pytest.mark.parametrize("base_url", [
    "http://localhost:8000",     # the documented lab setup must stay quiet
    "http://127.0.0.1:8000",
    "http://[::1]:8000",
    "https://spatium.example",
])
def test_loopback_or_tls_base_url_does_not_warn(base_url, capsys):
    SpatiumProvider(base_url, token="sekrit")
    assert capsys.readouterr().err == ""


def test_no_token_means_nothing_to_leak(capsys):
    SpatiumProvider("http://spatium.internal:8000", token="")
    assert capsys.readouterr().err == ""
