#!/usr/bin/env python3
"""Dependency licence gate.

Extraction is delegated to pip-licenses, a maintained tool. This script only
decides pass/fail against an exact-match allowlist, which is the rule in §14.2
of the engineering playbook. Anything not listed fails until it has been
reviewed and added here deliberately.

A gate that checked nothing must fail: if pip-licenses returns no packages, the
script exits non-zero rather than reporting success.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

# Exact strings only. Compound expressions are added verbatim after review
# (§14.2). Copyleft (GPL, AGPL, LGPL, SSPL) is deliberately absent.
ALLOWLIST: frozenset[str] = frozenset(
    {
        "MIT",
        "MIT License",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "Apache Software License",
        "Apache-2.0 OR BSD-2-Clause",
        "MIT AND PSF-2.0",  # reviewed: greenlet, pulled in by SQLAlchemy
        "ISC",
        "PSF-2.0",
        "MPL-2.0",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "FSL-1.1-ALv2",
    }
)

# Reviewed exceptions, keyed by package, for metadata that names a licence only
# generically. Each entry is a decision, not a wildcard.
EXCEPTIONS: dict[str, str] = {
    "httpx": "runtime; upstream is BSD-3-Clause, metadata says 'BSD License'",
    "grimp": "dev-only; upstream is BSD-3-Clause, metadata says 'BSD License'",
    "import-linter": "dev-only; upstream is BSD-2-Clause, metadata says 'BSD License'",
    "nodeenv": "dev-only; upstream is BSD-3-Clause, metadata says 'BSD License'",
}


def load() -> list[dict[str, str]]:
    executable = shutil.which("pip-licenses")
    if executable is None:
        print("licence gate: pip-licenses is not installed — refusing to pass", file=sys.stderr)
        raise SystemExit(1)
    # Fixed argv, no shell, executable resolved by which().
    result = subprocess.run(  # noqa: S603
        [executable, "--format=json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"licence gate: pip-licenses failed:\n{result.stderr}", file=sys.stderr)
        raise SystemExit(1)
    packages: list[dict[str, str]] = json.loads(result.stdout or "[]")
    return packages


def main() -> int:
    packages = load()
    if not packages:
        print("licence gate: scanned zero packages — refusing to pass", file=sys.stderr)
        return 1

    offenders: list[tuple[str, str]] = []
    for package in packages:
        name = package.get("Name", "?")
        licence = package.get("License", "UNKNOWN")
        if licence in ALLOWLIST or name in EXCEPTIONS:
            continue
        offenders.append((name, licence))

    if offenders:
        print("licence gate: unapproved licences found", file=sys.stderr)
        for name, licence in offenders:
            print(f"  {name}: {licence}", file=sys.stderr)
        print(
            "\nReview each dependency and add its licence to ALLOWLIST (exact match) "
            "or the package to EXCEPTIONS with a reason.",
            file=sys.stderr,
        )
        return 1

    print(f"licence gate: {len(packages)} packages, all approved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
