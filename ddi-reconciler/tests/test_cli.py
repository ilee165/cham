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
                        lambda cfg: {"azure-private": provider})
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
    monkeypatch.setattr(cli, "_build_providers", lambda cfg: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", str(desired), "--edge", "nope"])
    assert code == 1
    assert "unknown edge" in capsys.readouterr().err


def test_missing_desired_file_is_operational_error(files, monkeypatch, capsys):
    config, _ = files
    monkeypatch.setattr(cli, "_build_providers", lambda cfg: {})
    code = cli.main(["--dry-run", "--config", str(config),
                     "--desired-from-file", "does-not-exist.json"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_subprocess_entrypoint_contract():
    result = subprocess.run(
        [sys.executable, "-m", "ddi_reconciler.cli", "--dry-run",
         "--config", "missing-config.toml"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "error:" in result.stderr
