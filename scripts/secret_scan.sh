#!/usr/bin/env bash
# Secret scan over the full git history.
#
# A scanner that scanned nothing must fail (playbook §16, lesson 4), so the
# commit count is checked before the scan runs and a missing scanner is an
# error, never a silent pass.
set -euo pipefail
cd "$(dirname "$0")/.."

GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks@sha256:691af3c7c5a48b16f187ce3446d5f194838f91238f27270ed36eef6359a574d9"

commits=$(git rev-list --all --count 2>/dev/null || echo 0)
if [ "${commits}" -eq 0 ]; then
  echo "secret scan: no commits in history — refusing to pass" >&2
  exit 1
fi
echo "secret scan: ${commits} commit(s) in history"

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect --source . --redact --no-banner --log-opts="--all" --exit-code 1
elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  docker run --rm -v "${PWD}:/repo" -w /repo "${GITLEAKS_IMAGE}" \
    detect --source . --redact --no-banner --log-opts="--all" --exit-code 1
else
  echo "secret scan: gitleaks and docker are both unavailable — refusing to pass" >&2
  exit 1
fi
