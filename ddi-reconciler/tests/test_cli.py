"""CLI contract tests that execute the real entry point."""
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mode", ["--dry-run", "--apply"])
def test_unimplemented_modes_fail_closed(mode):
    result = subprocess.run(
        [sys.executable, "-m", "ddi_reconciler.cli", mode],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "not implemented" in result.stderr.lower()
