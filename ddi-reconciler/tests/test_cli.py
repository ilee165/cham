"""CLI contract tests — in-process with fake providers, plus one subprocess test."""
import json
import subprocess
import sys

import pytest

from ddi_reconciler import cli
from ddi_reconciler.model import CanonicalRecord

Z = "azure.dwsolution.co"

CONFIG = """
[spatium]
base_url = "http://spatium.invalid"

[azure]
resource_group = "rg-cham-lab"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "azure.dwsolution.co"
managed_keys = [["azure.dwsolution.co", "app", "A"]]
"""


class FakeProvider:
    def __init__(self, actual):
        self.actual = list(actual)
        self.applied = False

    def fetch_actual(self, zones):
        return list(self.actual)

    def apply(self, diff):
        self.applied = True
        self.actual = list(diff.to_add)


@pytest.fixture
def files(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(CONFIG)
    desired = tmp_path / "desired.json"
    desired.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A",
          "values": ["10.10.4.30"], "ttl": 300}]))
    return config, desired


def run_cli(monkeypatch, provider, config, desired, mode):
    monkeypatch.setattr(cli, "_build_providers",
                        lambda cfg, edges=None: {"azure-private": provider})
    return cli.main([mode, "--config", str(config),
                     "--desired-from-file", str(desired)])


def test_dry_run_drift_exits_2_and_prints_diff(files, monkeypatch, capsys):
    config, desired = files
    assert run_cli(monkeypatch, FakeProvider([]), config, desired, "--dry-run") == 2
    out = capsys.readouterr().out
    assert "[azure-private] ADD    app A 10.10.4.30 ttl=300" in out
    assert "summary: 1 add, 0 update, 0 delete" in out


def test_dry_run_converged_exits_0(files, monkeypatch):
    config, desired = files
    actual = [CanonicalRecord(zone=Z, name="app", rtype="A",
                              values=("10.10.4.30",), ttl=300)]
    assert run_cli(monkeypatch, FakeProvider(actual), config, desired, "--dry-run") == 0


def test_apply_converges_and_exits_0(files, monkeypatch):
    config, desired = files
    provider = FakeProvider([])
    assert run_cli(monkeypatch, provider, config, desired, "--apply") == 0
    assert provider.applied


def test_unknown_edge_filter_is_error(files, monkeypatch, capsys):
    config, desired = files
    monkeypatch.setattr(cli, "_build_providers", lambda cfg, edges=None: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired), "--edge", "nope"])
    assert code == 1
    assert "unknown edge" in capsys.readouterr().err


def test_missing_desired_file_is_operational_error(files, monkeypatch, capsys):
    config, _ = files
    monkeypatch.setattr(cli, "_build_providers", lambda cfg, edges=None: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", "does-not-exist.json"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_edge_filter_builds_only_selected_providers(tmp_path, monkeypatch, capsys):
    """Verify that --edge filter prevents building providers for excluded edges.

    This ensures operators don't need env vars (e.g., CLOUDFLARE_API_TOKEN)
    for providers they're not using.
    """
    config_text = """
[spatium]
base_url = "http://spatium.invalid"

[azure]
resource_group = "rg-cham-lab"

[[edges]]
name = "azure-private"
provider = "azure"
zone = "azure.dwsolution.co"
managed_keys = [["azure.dwsolution.co", "app", "A"]]

[[edges]]
name = "cloudflare-prod"
provider = "cloudflare"
zone = "example.com"
managed_keys = [["example.com", "api", "A"]]
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_text)

    desired_file = tmp_path / "desired.json"
    desired_file.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A",
          "values": ["10.10.4.30"], "ttl": 300}]))

    # Mock _build_providers to track which edges it receives
    built_edges = []

    def mock_build(cfg, edges=None):
        if edges is None:
            edges = cfg.edges
        built_edges.extend([e.name for e in edges])
        # Only return the azure provider; cloudflare is not in the returned dict
        return {"azure-private": FakeProvider([])}

    monkeypatch.setattr(cli, "_build_providers", mock_build)

    # Run with --edge azure-private filter
    code = cli.main(["--dry-run", "--config", str(config_file),
                     "--desired-from-file", str(desired_file),
                     "--edge", "azure-private"])

    # Verify: _build_providers received only the filtered edge
    assert built_edges == ["azure-private"], \
        f"Expected only ['azure-private'], got {built_edges}"
    # Dry-run with drift should exit 2
    assert code == 2


def test_subprocess_entrypoint_contract():
    result = subprocess.run(
        [sys.executable, "-m", "ddi_reconciler.cli", "--dry-run",
         "--config", "missing-config.toml"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "error:" in result.stderr


def test_bad_flag_exits_1_not_2(capsys):
    """argparse's default usage-error exit code (2) collides with the
    drift-found contract; usage errors must exit 1 instead."""
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--bogus-flag"])
    assert exc_info.value.code == 1
    assert "error:" in capsys.readouterr().err


def test_export_empty_string_is_not_a_noop(files, capsys):
    """--export "" must not silently fall through to returning 0 despite
    never exporting; it should enter the export branch and fail loudly."""
    config, desired = files
    code = cli.main(["--export", "", "--config", str(config),
                     "--desired-from-file", str(desired)])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_missing_azure_env_var_gives_clear_error(files, monkeypatch, capsys):
    """A missing required env var should render as a clear operational
    error, not a bare KeyError repr — and must fire before any Azure SDK
    import (env read happens before AzureProvider() construction)."""
    config, desired = files
    monkeypatch.delenv("AZURE_SUBSCRIPTION_ID", raising=False)
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired)])
    assert code == 1
    assert ("missing required environment variable: AZURE_SUBSCRIPTION_ID"
            in capsys.readouterr().err)
