"""CLI contract tests — in-process with fake providers, plus one subprocess test."""
import json
import subprocess
import sys
import types

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


# --- WR-2: data KeyErrors are not environment errors -----------------------

def test_malformed_snapshot_is_not_reported_as_a_missing_env_var(files, monkeypatch, capsys):
    """The unscoped `except KeyError` sent operators to check environment
    variables for a missing field in a JSON file."""
    config, desired = files
    desired.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A", "values": ["10.10.4.30"]}]))
    monkeypatch.setattr(cli, "_build_providers", lambda cfg, edges=None: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired)])
    err = capsys.readouterr().err
    assert code == 1
    assert "environment variable" not in err
    assert "missing field(s): ttl" in err


# --- CR-1: empty truth end-to-end ------------------------------------------

def test_empty_snapshot_refuses_to_delete_and_exits_1(files, monkeypatch, capsys):
    config, desired = files
    desired.write_text("[]")
    actual = [CanonicalRecord(zone=Z, name="app", rtype="A",
                              values=("10.10.4.30",), ttl=300)]
    provider = FakeProvider(actual)
    assert run_cli(monkeypatch, provider, config, desired, "--apply") == 1
    assert "--allow-empty-truth" in capsys.readouterr().err
    assert not provider.applied
    assert provider.actual == actual  # nothing deleted


def test_empty_snapshot_deletes_only_with_the_opt_in_flag(files, monkeypatch, capsys):
    config, desired = files
    desired.write_text("[]")
    provider = FakeProvider([CanonicalRecord(zone=Z, name="app", rtype="A",
                                             values=("10.10.4.30",), ttl=300)])
    monkeypatch.setattr(cli, "_build_providers",
                        lambda cfg, edges=None: {"azure-private": provider})
    code = cli.main(["--apply", "--config", str(config),
                     "--desired-from-file", str(desired), "--allow-empty-truth"])
    assert code == 0
    assert "0 add, 0 update, 1 delete" in capsys.readouterr().out
    assert provider.applied


def test_export_refuses_to_shrink_a_committed_snapshot(files, tmp_path, capsys):
    """SpatiumDDI restarted empty -> --export writes [] -> the committed
    snapshot becomes a standing wipe order."""
    config, desired = files
    snapshot = tmp_path / "committed.json"
    snapshot.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A", "values": ["10.10.4.30"], "ttl": 300},
         {"zone": Z, "name": "db", "rtype": "A", "values": ["10.10.4.20"], "ttl": 300}]))
    before = snapshot.read_text()

    code = cli.main(["--export", str(snapshot), "--config", str(config),
                     "--desired-from-file", str(desired)])
    assert code == 1
    assert "refusing to shrink" in capsys.readouterr().err
    assert snapshot.read_text() == before

    assert cli.main(["--export", str(snapshot), "--config", str(config),
                     "--desired-from-file", str(desired),
                     "--allow-snapshot-shrink"]) == 0
    assert len(json.loads(snapshot.read_text())) == 1


# --- WR-12: a mis-spelled desired record must not become a deletion --------

def test_fqdn_spelled_snapshot_entry_does_not_delete_the_live_record(
        files, monkeypatch, capsys):
    config, desired = files
    desired.write_text(json.dumps(
        [{"zone": Z, "name": f"app.{Z}", "rtype": "A",
          "values": ["10.10.4.30"], "ttl": 300}]))
    actual = [CanonicalRecord(zone=Z, name="app", rtype="A",
                              values=("10.10.4.30",), ttl=300)]
    provider = FakeProvider(actual)
    assert run_cli(monkeypatch, provider, config, desired, "--apply") == 1
    assert "names managed key" in capsys.readouterr().err
    assert provider.actual == actual


def test_unowned_desired_records_are_printed_as_skips(files, monkeypatch, capsys):
    config, desired = files
    desired.write_text(json.dumps(
        [{"zone": Z, "name": "app", "rtype": "A", "values": ["10.10.4.30"], "ttl": 300},
         {"zone": Z, "name": "db", "rtype": "A", "values": ["10.10.4.20"], "ttl": 300}]))
    run_cli(monkeypatch, FakeProvider([]), config, desired, "--dry-run")
    assert "[azure-private] SKIP   db A (not in managed_keys)" in capsys.readouterr().out


# --- WR-8 / CR-4 / IN-1: multi-edge accounting and edge scoping ------------

TWO_EDGE_CONFIG = CONFIG + """
[[edges]]
name = "cloudflare-public"
provider = "cloudflare"
zone = "dwsolution.co"
managed_keys = [["dwsolution.co", "demo", "CNAME"]]
"""

TWO_EDGE_DESIRED = [
    {"zone": Z, "name": "app", "rtype": "A", "values": ["10.10.4.30"], "ttl": 300},
    {"zone": "dwsolution.co", "name": "demo", "rtype": "CNAME",
     "values": ["www.dwsolution.co"], "ttl": 300},
]


class ExplodingProvider:
    def fetch_actual(self, zones):
        raise RuntimeError("cloudflare API 500 on /zones")

    def apply(self, diff):  # pragma: no cover - never reached
        raise AssertionError


@pytest.fixture
def two_edge_files(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text(TWO_EDGE_CONFIG)
    desired = tmp_path / "desired.json"
    desired.write_text(json.dumps(TWO_EDGE_DESIRED))
    return config, desired


def test_partial_apply_reports_which_edges_were_mutated(two_edge_files, monkeypatch, capsys):
    """A mid-loop failure used to exit 1 with no account of what had already
    landed at the edges that succeeded."""
    config, desired = two_edge_files
    first = FakeProvider([])
    monkeypatch.setattr(cli, "_build_providers", lambda cfg, edges=None: {
        "azure-private": first, "cloudflare-public": ExplodingProvider()})
    code = cli.main(["--apply", "--config", str(config),
                     "--desired-from-file", str(desired)])
    captured = capsys.readouterr()
    assert code == 1
    assert first.applied
    assert "[azure-private] applied 1 change(s)" in captured.out
    assert "edge 'cloudflare-public' did not complete" in captured.err
    assert "fully applied before it: azure-private" in captured.err


def test_missing_provider_for_a_selected_edge_is_an_operational_error(
        two_edge_files, monkeypatch, capsys):
    """Before duplicate edge names were rejected, a collapsed providers dict
    silently handed one edge another edge's provider (and zone)."""
    config, desired = two_edge_files
    monkeypatch.setattr(cli, "_build_providers",
                        lambda cfg, edges=None: {"azure-private": FakeProvider([])})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired)])
    assert code == 1
    assert "no provider constructed for edge(s): cloudflare-public" in capsys.readouterr().err


def _install_fake_spatium(monkeypatch, seen):
    module = types.ModuleType("ddi_reconciler.providers.spatium")

    class FakeSpatium:
        def __init__(self, base_url, token):
            pass

        def fetch_desired(self, zones):
            seen["zones"] = set(zones)
            return [CanonicalRecord(zone=Z, name="app", rtype="A",
                                    values=("10.10.4.30",), ttl=300)]

    module.SpatiumProvider = FakeSpatium
    monkeypatch.setitem(sys.modules, "ddi_reconciler.providers.spatium", module)


def test_edge_filter_scopes_the_truth_query(two_edge_files, monkeypatch):
    """--edge should not require SpatiumDDI to serve zones the run is not
    touching; the truth query used to be built from every configured edge."""
    config, _ = two_edge_files
    seen = {}
    _install_fake_spatium(monkeypatch, seen)
    monkeypatch.setattr(cli, "_build_providers",
                        lambda cfg, edges=None: {"azure-private": FakeProvider([])})
    cli.main(["--dry-run", "--config", str(config), "--edge", "azure-private"])
    assert seen["zones"] == {Z}


def test_export_honours_the_edge_filter(two_edge_files, tmp_path, monkeypatch):
    config, _ = two_edge_files
    seen = {}
    _install_fake_spatium(monkeypatch, seen)
    out = tmp_path / "snapshot.json"
    assert cli.main(["--export", str(out), "--config", str(config),
                     "--edge", "azure-private"]) == 0
    assert seen["zones"] == {Z}
