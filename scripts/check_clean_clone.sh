#!/usr/bin/env bash
# Run the full check in a fresh clone.
#
# A dirty working tree can hide a missing file: an untracked package marker once
# made lint pass locally and fail in CI. This is the check that catches it.
set -euo pipefail
cd "$(dirname "$0")/.."

tmp=$(mktemp -d)
trap 'rm -rf "${tmp}"' EXIT

git clone -q "$(git rev-parse --show-toplevel)" "${tmp}/repo"
cd "${tmp}/repo"
export UV_CACHE_DIR="${tmp}/uv-cache"
uv sync --locked --all-groups
make check
