"""Argument-construction contract for the Phase 3 VM watchdog (2026-08-13 review).

CR-05: the watchdog used the Azure CLI's ambient default subscription. Resource
group and VM names are not globally unique, so a changed default context could
deallocate identically named VMs in another subscription while the intended lab
VMs stayed running and billing. The fix pins a mandatory, GUID-validated
``SubscriptionId`` into every az invocation.

A live wrong-subscription reproduction is deliberately out of reach from CI
(no Azure credentials here, by design — see reconciler-tests.yml). What CI can
prove is the argument shape: ``-DryRun`` prints the fully formed az argument
vectors the watchdog WOULD run, built by the same functions the live path
splats, so asserting on those lines pins the real invocations rather than a
parallel copy that could drift.

These tests execute the script under ``pwsh`` rather than parsing it: a text
pin on ``--subscription`` would pass even if the flag were built in dead code.
Ubuntu CI runners ship pwsh, so CI always runs the behavioral half.
"""

import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = REPO_ROOT / "scripts" / "phase3-vm-watchdog.ps1"
PWSH = shutil.which("pwsh")

# Any well-formed GUID works: -DryRun never contacts Azure, so nothing checks
# the value against a real subscription. Obviously fake on purpose.
DUMMY_SUBSCRIPTION = "00000000-1111-2222-3333-444444444444"
EXPECTED_RESOURCE_GROUP = "rg-cham-lab"
EXPECTED_VMS = ("vm-hub-ddi", "vm-test-app", "vm-test-mgmt")

ARGV_PREFIX = "watchdog_planned_az_argv: az "

needs_pwsh = pytest.mark.skipif(
    PWSH is None,
    reason=(
        "pwsh is not on PATH, so the watchdog's behavioral contract — "
        "subscription pinning on every az argument vector and the -DryRun "
        "output markers — is NOT verified on this machine. Ubuntu CI runners "
        "ship pwsh, so CI always runs these."
    ),
)


def _future_deadline():
    # Must be in the future and within the watchdog's 60-minute window.
    return (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _run_watchdog(log_path, *, subscription=DUMMY_SUBSCRIPTION, omit_subscription=False):
    argv = [
        PWSH,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(WATCHDOG),
        "-DryRun",
        "-ResourceGroup",
        EXPECTED_RESOURCE_GROUP,
        "-VmNames",
        ",".join(EXPECTED_VMS),
        "-DeadlineUtc",
        _future_deadline(),
        "-LogPath",
        str(log_path),
    ]
    if not omit_subscription:
        argv += ["-SubscriptionId", subscription]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )


@pytest.fixture(scope="module")
def dry_run(tmp_path_factory):
    """One shared -DryRun invocation; the assertions below all read it."""
    log_path = tmp_path_factory.mktemp("watchdog") / "watchdog.log"
    result = _run_watchdog(log_path)
    return result, log_path


def _argv_lines(result):
    return [
        line[len(ARGV_PREFIX):]
        for line in result.stdout.splitlines()
        if line.startswith(ARGV_PREFIX)
    ]


@needs_pwsh
class TestSubscriptionPinning:
    def test_dry_run_exits_zero_and_keeps_its_markers(self, dry_run):
        result, _ = dry_run
        assert result.returncode == 0, result.stderr
        # The pre-existing -DryRun output contract, relied on by the arming
        # procedure, must survive the argv additions.
        assert "watchdog_dry_run_ok=true" in result.stdout
        assert "watchdog_vm_allowlist_ok=true" in result.stdout

    def test_dry_run_prints_every_planned_az_invocation(self, dry_run):
        result, _ = dry_run
        argvs = _argv_lines(result)
        probes = [a for a in argvs if a.startswith("account get-access-token")]
        deallocates = [a for a in argvs if a.startswith("vm deallocate")]
        views = [a for a in argvs if a.startswith("vm get-instance-view")]
        assert len(probes) == 1
        assert len(deallocates) == len(EXPECTED_VMS)
        assert len(views) == len(EXPECTED_VMS)
        # The operation set is deallocate-only: nothing else may appear.
        assert len(argvs) == len(probes) + len(deallocates) + len(views)
        for vm in EXPECTED_VMS:
            assert any(f"--name {vm}" in a for a in deallocates)
            assert any(f"--name {vm}" in a for a in views)

    def test_every_az_invocation_is_subscription_pinned(self, dry_run):
        result, _ = dry_run
        argvs = _argv_lines(result)
        assert argvs, "no planned az argument vectors were printed"
        for argv in argvs:
            assert f"--subscription {DUMMY_SUBSCRIPTION}" in argv, argv

    def test_every_vm_invocation_names_the_pinned_resource_group(self, dry_run):
        result, _ = dry_run
        vm_argvs = [a for a in _argv_lines(result) if a.startswith("vm ")]
        assert vm_argvs
        for argv in vm_argvs:
            assert f"--resource-group {EXPECTED_RESOURCE_GROUP}" in argv, argv

    def test_audit_log_lines_carry_the_subscription(self, dry_run):
        _, log_path = dry_run
        lines = log_path.read_text(encoding="utf-8").splitlines()
        dry_lines = [l for l in lines if "DryRunNoMutation" in l]
        assert len(dry_lines) == len(EXPECTED_VMS)
        for line in dry_lines:
            assert f"subscription={DUMMY_SUBSCRIPTION}" in line, line

    def test_malformed_subscription_id_is_refused(self, tmp_path):
        result = _run_watchdog(
            tmp_path / "watchdog.log", subscription="not-a-guid"
        )
        assert result.returncode != 0
        # Pre-fix, -SubscriptionId was an UNKNOWN parameter, which also exits
        # nonzero — distinguish validation rejection from parameter absence so
        # this test is red on the pre-fix script rather than vacuously green.
        assert "parameter cannot be found" not in result.stderr.lower()

    def test_subscription_id_is_mandatory(self, tmp_path):
        result = _run_watchdog(tmp_path / "watchdog.log", omit_subscription=True)
        assert result.returncode != 0


def test_subscription_guid_shape_is_validated_in_the_script():
    # Structure pin, pwsh-independent: the parameter must carry a GUID
    # ValidatePattern, not merely non-emptiness — a subscription NAME would
    # silently reintroduce ambient-context resolution semantics.
    text = WATCHDOG.read_text(encoding="utf-8")
    param_block = text[text.index("param("):text.index("Set-StrictMode")]
    assert re.search(
        r"\[ValidatePattern\([^)]*\{8\}[^)]*\{4\}[^)]*\{12\}", param_block
    ), "SubscriptionId lacks a GUID-shaped ValidatePattern"
    assert "$SubscriptionId" in param_block
