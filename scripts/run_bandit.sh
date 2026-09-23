#!/usr/bin/env bash
# Run the release security gate with a pinned, isolated Bandit environment.
# uv creates/reuses the environment outside the repository; no system pip is needed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Keep this list aligned with publishable Python source. Tests, build output,
# caches, diagnostics, and virtual environments are not shipped in the release zip.
SOURCE_PATHS=(
  algorithms
  autocrs
  __init__.py
  community.py
  community_dialog.py
  plugin.py
  processing_provider.py
  runtime_env.py
)

# Fail closed on every Bandit finding, regardless of severity or confidence.
# This is the deterministic fail-zero pre-upload gate: QGIS repository findings
# that are LOW/HIGH (including B110) must fail locally too. Do not add
# --exit-zero or severity/confidence filters here; any rare false positive must
# be fixed narrowly or justified with a specific, local # nosec annotation.
BANDIT_VERSION="bandit==1.8.6"
uv run --quiet --with "$BANDIT_VERSION" bandit \
  -r "${SOURCE_PATHS[@]}"
