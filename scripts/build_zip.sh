#!/usr/bin/env bash
#
# Build a clean release zip of the QGIS plugin in dist/.
# Excludes generated files, IDE/OS junk, local-only state, and dev tooling
# per https://plugins.qgis.org/publish/ guidelines.
#
# Usage:
#   ./scripts/build_zip.sh
#
# Output:
#   dist/<plugin-folder>-<version>.zip
# where <plugin-folder> matches the GitHub repository name and <version>
# comes from metadata.txt. The zip root is exactly that folder name so
# QGIS installs the plugin under the right name.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
METADATA="$ROOT/metadata.txt"

if [[ ! -f "$METADATA" ]]; then
  echo "ERROR: metadata.txt not found at $METADATA" >&2
  exit 1
fi

get_field() {
  local key="$1"
  local line
  line=$(grep -E "^${key}=" "$METADATA" | head -1 || true)
  if [[ -z "$line" ]]; then
    echo "ERROR: '$key=' not found in metadata.txt" >&2
    exit 1
  fi
  echo "${line#${key}=}"
}

VERSION=$(get_field version)
# Plugin folder name inside the zip. Keep in sync with the GitHub repo name.
PLUGIN_DIR="RegenGIS-Landscape-Analysis-Toolkit"

OUT_DIR="$ROOT/dist"
OUT="$OUT_DIR/${PLUGIN_DIR}-${VERSION}.zip"

STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

mkdir -p "$STAGE"
DEST="$STAGE/$PLUGIN_DIR"
mkdir -p "$DEST"

# Copy publishable files, excluding everything QGIS forbids or that is
# local-only / dev-only.
rsync -a \
  --exclude='__pycache__' \
  --exclude='__pycache__/**' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.pyd' \
  --exclude='.DS_Store' \
  --exclude='Thumbs.db' \
  --exclude='.git' \
  --exclude='.git/**' \
  --exclude='.gitignore' \
  --exclude='.hermes' \
  --exclude='.hermes/**' \
  --exclude='.autocrs-cache' \
  --exclude='.autocrs-cache/**' \
  --exclude='.vscode' \
  --exclude='.vscode/**' \
  --exclude='.idea' \
  --exclude='.idea/**' \
  --exclude='scripts' \
  --exclude='scripts/**' \
  --exclude='docs' \
  --exclude='docs/**' \
  --exclude='test' \
  --exclude='test/**' \
  --exclude='dist' \
  --exclude='dist/**' \
  --exclude='venv' \
  --exclude='venv/**' \
  --exclude='.venv' \
  --exclude='.venv/**' \
  --exclude='env' \
  --exclude='env/**' \
  --exclude='__MACOSX' \
  --exclude='__MACOSX/**' \
  --exclude='*.zip' \
  --exclude='*.tar.gz' \
  --exclude='*.tgz' \
  --exclude='algorithms/TEST' \
  --exclude='algorithms/TEST/**' \
  "$ROOT/" "$DEST/"

# Build the zip from inside the staging dir so its root is PLUGIN_DIR/.
mkdir -p "$OUT_DIR"
( cd "$STAGE" && zip -r -q "$OUT" "$PLUGIN_DIR" )

# macOS and Linux stat differ; pick the right flag.
if SIZE=$(stat -f%z "$OUT" 2>/dev/null); then :; else SIZE=$(stat -c%s "$OUT"); fi

# QGIS hard limit per https://plugins.qgis.org/publish/
MAX=20971520
if [[ "$SIZE" -gt "$MAX" ]]; then
  echo "ERROR: zip is $SIZE bytes, exceeds QGIS 20 MB limit ($MAX)" >&2
  exit 1
fi

SHA=$(shasum -a 256 "$OUT" 2>/dev/null | awk '{print $1}' \
       || sha256sum "$OUT" | awk '{print $1}')

echo "Built:   $OUT"
printf "Size:    %s bytes (%.2f MB)\n" "$SIZE" "$(awk -v s="$SIZE" 'BEGIN{printf "%.2f", s/1048576}')"
echo "SHA-256: $SHA"

echo
echo "Sanity check (should print nothing below this line):"
unzip -l "$OUT" | grep -E '__pycache__|\.DS_Store|\.git/|/\.hermes/|/\.autocrs-cache/|scripts/|__MACOSX/' \
  && { echo "FAIL: zip contains excluded entries" >&2; exit 1; } \
  || echo "OK: no excluded entries found"