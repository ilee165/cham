"""config.toml loading — offline, no secrets."""
import pytest

from ddi_reconciler.config import ConfigError, load_config

VALID = """
[spatium]
base_url = "http://spatium.test:8000/"

[azure]
resource_group = "rg-x"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "Azure.DWSolution.co."
managed_keys = [["azure.dwsolution.co", "APP.", "a"]]
"""


def test_load_valid_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID)
    config = load_config(path)
    assert config.spatium_base_url == "http://spatium.test:8000/"
    assert config.azure_resource_group == "rg-x"
    edge = config.edges[0]
    assert edge.zone == "azure.dwsolution.co"          # normalized
    assert edge.managed_keys == frozenset({("azure.dwsolution.co", "app", "A")})


def test_missing_file_is_config_error(tmp_path):
    with pytest.raises(ConfigError, match="config file not found"):
        load_config(tmp_path / "nope.toml")


def test_unknown_provider_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace('provider = "azure"', 'provider = "route53"'))
    with pytest.raises(ConfigError, match="unknown provider"):
        load_config(path)


def test_no_edges_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[spatium]\nbase_url = 'x'\n")
    with pytest.raises(ConfigError, match="no edges"):
        load_config(path)


def test_duplicate_edge_names_rejected(tmp_path):
    """Duplicate names collapse in the CLI's {edge.name: provider} dict, so one
    edge is handed another edge's provider — and therefore another edge's zone."""
    path = tmp_path / "config.toml"
    path.write_text(VALID + """
[[edges]]
name = "azure-private"
provider = "cloudflare"
zone = "other-tenant.example"
managed_keys = [["other-tenant.example", "demo", "CNAME"]]
""")
    with pytest.raises(ConfigError, match="duplicate edge name"):
        load_config(path)


def test_managed_key_outside_edge_zone_rejected(tmp_path):
    """Caught at load time, not deep inside diff_records — which is after
    provider credentials have been read and the edge API already called."""
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace(
        'managed_keys = [["azure.dwsolution.co", "APP.", "a"]]',
        'managed_keys = [["dwsolution.co", "demo", "CNAME"]]'))
    with pytest.raises(ConfigError, match="outside the edge zone"):
        load_config(path)


def test_non_string_zone_is_config_error_not_attributeerror(tmp_path):
    """`entry["zone"].strip()` on a TOML integer used to escape as a bare
    AttributeError, giving the operator a traceback instead of `error: ...`."""
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace('zone = "Azure.DWSolution.co."', "zone = 42"))
    with pytest.raises(ConfigError, match="'zone' must be a non-empty string"):
        load_config(path)


def test_non_string_edge_name_is_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace('name = "azure-private"', "name = 7"))
    with pytest.raises(ConfigError, match="'name' must be a non-empty string"):
        load_config(path)


def test_unicode_zone_agrees_with_its_punycode_managed_keys(tmp_path):
    """The edge zone and its managed keys must go through one canonicalizer,
    or a unicode zone and its A-label keys read as two different zones."""
    path = tmp_path / "config.toml"
    path.write_text("""
[[edges]]
name = "cf"
provider = "cloudflare"
zone = "démo.example"
managed_keys = [["xn--dmo-bma.example", "app", "A"]]
""", encoding="utf-8")
    edge = load_config(path).edges[0]
    assert edge.zone == "xn--dmo-bma.example"
    assert edge.managed_keys == frozenset({("xn--dmo-bma.example", "app", "A")})


def test_empty_managed_keys_rejected(tmp_path):
    """An edge that owns nothing is a silent no-op, not a valid edge."""
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace(
        'managed_keys = [["azure.dwsolution.co", "APP.", "a"]]', "managed_keys = []"))
    with pytest.raises(ConfigError, match="'managed_keys' must be a non-empty list"):
        load_config(path)


def test_malformed_managed_key_is_config_error(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(VALID.replace(
        'managed_keys = [["azure.dwsolution.co", "APP.", "a"]]',
        'managed_keys = [["azure.dwsolution.co", "app"]]'))
    with pytest.raises(ConfigError, match="invalid edge entry"):
        load_config(path)


def test_repo_config_toml_is_valid():
    from pathlib import Path
    repo_config = Path(__file__).parent.parent / "config.toml"
    config = load_config(repo_config)
    assert {e.name for e in config.edges} == {"azure-private", "cloudflare-public"}
