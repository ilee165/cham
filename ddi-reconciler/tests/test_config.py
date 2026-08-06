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


def test_repo_config_toml_is_valid():
    from pathlib import Path
    repo_config = Path(__file__).parent.parent / "config.toml"
    config = load_config(repo_config)
    assert {e.name for e in config.edges} == {"azure-private", "cloudflare-public"}
