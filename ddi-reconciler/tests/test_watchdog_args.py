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
from datetime import UTC, datetime, timedelta
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
    return (datetime.now(UTC) + timedelta(minutes=5)).strftime(
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
    # check=False: several tests assert on NONZERO exits (refusal paths).
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
        check=False,
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


class TestReissueStateMachine:
    """Structure pins for CR-06 (2026-08-13 review).

    ``az vm deallocate --no-wait`` exits 0 when Azure ACCEPTS the long-running
    operation, not when the VM reaches ``deallocated``. The pre-fix script
    permanently removed a VM from its pending set on acceptance and a separate
    later loop only polled — an accepted-then-failed or stalled operation left
    the cost-bearing VM running until the verify budget threw.

    The failure needs Azure to accept an operation and then stall it, which no
    offline test can produce, and a faked-CLI behavioral test would take
    minutes of wall clock (15-second poll cycles, a 3-minute stall window).
    So, as with C1's resolver pin, these are structure pins that fail on the
    pre-fix script: request and verification must be one per-VM state machine
    with a reissue transition, not two sequential loops.
    """

    TEXT = WATCHDOG.read_text(encoding="utf-8")

    def test_per_vm_phases_exist(self):
        for phase in ("'pending-request'", "'pending-verify'", "'done'"):
            assert phase in self.TEXT, f"missing state-machine phase {phase}"

    def test_stalled_acceptance_is_reissued(self):
        assert "deallocate_reissued" in self.TEXT
        # The stall window that separates "operation in flight" from
        # "accepted but going nowhere" must exist as an explicit bound.
        assert "$stallReissueAfter" in self.TEXT

    def test_acceptance_is_not_terminal(self):
        # The pre-fix shape: acceptance removed the VM from a request-only
        # pending set, after which nothing could ever reissue. That set's
        # disappearance is the structural witness that request and verify
        # are now one machine.
        assert "$pendingDeallocations" not in self.TEXT

    def test_budget_exhaustion_still_fails_loudly(self):
        # CR-06's fix must not weaken the existing fail-closed property: the
        # 30-minute budget keeps its loud terminal throw and its markers for
        # both phases, and success still prints the verified marker.
        assert "AddMinutes(30)" in self.TEXT
        assert "deallocate_FAILED_budget_exhausted" in self.TEXT
        assert "verify_FAILED_budget_exhausted" in self.TEXT
        assert "watchdog_deallocation_UNVERIFIED=true" in self.TEXT
        assert "watchdog_deallocation_verified=true" in self.TEXT
        assert re.search(r"throw 'Watchdog retry budget exhausted", self.TEXT)

    def test_exhaustion_classification_keeps_acceptance_history(self):
        # WD-02 (PR #28 review): a VM that was accepted, stalled, and
        # reissued back to pending-request would otherwise be classified at
        # budget exhaustion by its CURRENT phase alone — reported as
        # deallocate_FAILED_budget_exhausted, with the UNVERIFIED stdout
        # marker skippable entirely — erasing from the audit trail that
        # Azure accepted a deallocate whose outcome was never verified.
        # Acceptance must latch, and the exhaustion classification must
        # consult that latch, not just the phase.
        assert "EverAccepted = $true" in self.TEXT
        exhaustion = self.TEXT[
            self.TEXT.index("$anyUnverified"):
            self.TEXT.index("throw 'Watchdog retry budget exhausted")
        ]
        assert "EverAccepted" in exhaustion, (
            "budget-exhaustion classification ignores acceptance history"
        )


def test_runbook_arming_snippet_matches_the_tested_invocation_shape():
    # WD-01 (PR #28 review): the watchdog is launched hidden via Start-Process
    # and "proved" armed by a HasExited check two seconds later. Without
    # -NonInteractive, an omitted mandatory parameter (such as the new
    # -SubscriptionId) leaves pwsh WAITING at an invisible prompt — not
    # exited — so the arm-proof reports an armed watchdog that will never
    # deallocate anything. The runbook must therefore carry a concrete arming
    # argv using the same invocation shape this test file exercises:
    # -NonInteractive so a contract drift fails loudly at arm time.
    runbook = (REPO_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
    blocks = [
        block
        for block in re.findall(r"```powershell\n(.*?)```", runbook, re.DOTALL)
        if "phase3-vm-watchdog.ps1" in block
    ]
    assert blocks, "runbook has no concrete watchdog arming snippet"
    for block in blocks:
        assert "'-NonInteractive'" in block, block
        assert "'-SubscriptionId'" in block, block


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
