"""The canary harness has two jobs, and both are tested here:

it must refuse to run when the patch would change nothing, and it must restore the
file whether or not the test fails. A harness that silently does nothing is the
failure it exists to prevent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "canary.py"
TARGET_TEST = "tests/budget/test_pricing.py::test_ceil_div"
TARGET_FILE = "src/firebrief/budget/money.py"


def run_canary(*args: str) -> subprocess.CompletedProcess[str]:
    # Fixed argv: the harness under test.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_missing_anchor_is_refused_and_the_file_is_unchanged() -> None:
    before = (REPO / TARGET_FILE).read_text()

    result = run_canary(
        "--file",
        TARGET_FILE,
        "--old",
        "text that is definitely not in the file",
        "--new",
        "unused",
        "--test",
        TARGET_TEST,
    )

    assert result.returncode != 0
    assert "anchor not found" in result.stderr
    assert (REPO / TARGET_FILE).read_text() == before


def test_a_patch_that_changes_nothing_is_reported_as_a_failed_canary() -> None:
    """A comment change removes no behaviour, so the test still passes."""
    before = (REPO / TARGET_FILE).read_text()

    result = run_canary(
        "--file",
        TARGET_FILE,
        "--old",
        "    return -(-numerator // denominator)",
        "--new",
        "    return -(-numerator // denominator)  # canary",
        "--test",
        TARGET_TEST,
    )

    assert result.returncode != 0
    assert "still passes" in result.stderr
    assert (REPO / TARGET_FILE).read_text() == before, "the harness left the file modified"
