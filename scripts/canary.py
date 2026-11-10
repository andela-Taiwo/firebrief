#!/usr/bin/env python3
"""Run a canary: break one behaviour, prove a test that should fail does fail.

The point is not to run tests again. It is to prove the test is load-bearing. Two
failure modes this exists to prevent, both of which happened here:

- the patch does not match the file, so nothing changes and the "canary" passes
- the test passes anyway because something else satisfies it

It refuses to run unless the test is green *before* the patch, and it always
restores the file, even when the test run fails.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

UV = ["uv", "run", "pytest", "-q"]


def run_test(target: str) -> bool:
    # Fixed argv: the pytest target comes from the developer running the tool.
    return subprocess.run([*UV, target], check=False).returncode == 0  # noqa: S603


def apply(path: Path, old: str, new: str) -> str:
    original = path.read_text()
    if old not in original:
        raise SystemExit(
            f"canary: anchor not found in {path}\n"
            "Nothing was changed, so this canary would have proved nothing.\n"
            f"Anchor (first 120 chars): {old[:120]!r}"
        )
    path.write_text(original.replace(old, new, 1))
    return original


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--old", required=True, help="text to replace; must exist")
    parser.add_argument("--new", required=True, help="what to replace it with")
    parser.add_argument("--test", required=True, help="pytest target that should now fail")
    parser.add_argument(
        "--no-precheck",
        action="store_true",
        help="skip the green run before patching (not recommended)",
    )
    args = parser.parse_args(argv)

    if not args.no_precheck and not run_test(args.test):
        print("canary: the test is already failing; fix that before canarying", file=sys.stderr)
        return 1

    original = apply(args.file, args.old, args.new)
    try:
        failed = not run_test(args.test)
    finally:
        args.file.write_text(original)

    if failed:
        print(f"canary PASS: {args.test} fails when the behaviour is removed")
        return 0

    print(
        f"canary FAILED: {args.test} still passes with the behaviour removed.\n"
        "Either the test is not load-bearing, or the patch did not change the behaviour.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
