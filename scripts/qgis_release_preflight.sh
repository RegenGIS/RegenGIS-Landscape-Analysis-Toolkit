#!/usr/bin/env bash
# Deterministic local gate for QGIS plugin repository security and approval checks.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SOURCE_PATHS=(algorithms autocrs __init__.py community.py community_dialog.py plugin.py processing_provider.py runtime_env.py)
BANDIT_VERSION='bandit==1.8.6'
SECRETS_VERSION='detect-secrets==1.5.0'
FLAKE8_VERSION='flake8==7.1.1'

usage() { echo "Usage: $0 --source | --zip ZIPFILE" >&2; exit 2; }
[[ $# -eq 1 ]] || usage

run_source() {
  echo "[preflight] Bandit ${BANDIT_VERSION#*=}"
  uv run --quiet --with "$BANDIT_VERSION" bandit -r "${SOURCE_PATHS[@]}"
  echo "[preflight] detect-secrets ${SECRETS_VERSION#*=} (no baseline; findings must be zero)"
  local secrets_json
  secrets_json="$(uv run --quiet --with "$SECRETS_VERSION" detect-secrets scan --no-verify "${SOURCE_PATHS[@]}" __init__.py community.py community_dialog.py plugin.py processing_provider.py runtime_env.py)"
  SECRETS_JSON="$secrets_json" python3 - <<'PY'
import json, os, sys
payload = json.loads(os.environ["SECRETS_JSON"])
findings = [(name, item) for name, entries in payload.get("results", {}).items() for item in entries]
if findings:
    for name, item in findings:
        print(f"{name}: {item}", file=sys.stderr)
    raise SystemExit(f"detect-secrets found {len(findings)} finding(s)")
print("detect-secrets: 0 findings")
PY
  echo "[preflight] Flake8 ${FLAKE8_VERSION#*=}"
  # Flake8 is explicitly reported but remains non-blocking per QGIS guidance;
  # existing source has legacy formatting findings and no suppression config is
  # used to hide them.
  if uv run --quiet --with "$FLAKE8_VERSION" flake8 "${SOURCE_PATHS[@]}"; then
    echo "[preflight] Flake8: clean"
  else
    echo "[preflight] WARNING: Flake8 reported existing non-blocking findings" >&2
  fi
  echo "[preflight] blocking source checks: clean"
}

run_zip() {
  local zip_path="$1"
  ZIP_PATH="$zip_path" python3 - <<'PY'
from pathlib import Path
import hashlib, io, mimetypes, os, re, stat, sys, urllib.error, urllib.request, zipfile

zip_path = Path(os.environ["ZIP_PATH"])
if not zip_path.is_file():
    raise SystemExit(f"ZIP does not exist: {zip_path}")
with zipfile.ZipFile(zip_path) as zf:
    bad = zf.testzip()
    if bad:
        raise SystemExit(f"ZIP integrity failure at {bad}")
    infos = zf.infolist()
    names = [i.filename for i in infos]
    roots = {n.split('/', 1)[0] for n in names if n}
    if len(roots) != 1 or not all(n.startswith(next(iter(roots)) + '/') for n in names):
        raise SystemExit(f"ZIP must have exactly one top-level plugin root: {sorted(roots)}")
    root = next(iter(roots))
    required = {f"{root}/metadata.txt", f"{root}/LICENSE", f"{root}/README.md", f"{root}/CHANGELOG.md", f"{root}/__init__.py"}
    missing = required - set(names)
    if missing:
        raise SystemExit(f"ZIP missing required release files: {sorted(missing)}")
    allowed_hidden = {f"{root}/.bandit", f"{root}/.flake8", f"{root}/.secrets.baseline"}
    forbidden_parts = ("__pycache__", ".git", "scripts/", "tests/", "test/", "dist/", ".pytest_cache", ".scan-venv", ".hermes", ".autocrs-cache")
    forbidden_names = {"qgis_startup.py", "qgis_gui_autoload.py", ".qgis-load-status.json", "headless_test_harness.py", "test_headless_harness.py", "test_headless_integration.py", "test_plugin_provider_fallback.py"}
    binary_ext = {".pyc", ".pyo", ".pyd", ".so", ".dll", ".dylib", ".exe", ".bin", ".zip", ".tar", ".gz", ".tgz", ".7z", ".rar", ".sqlite", ".db"}
    allowed_pngs = {f"{root}/icon.png", f"{root}/logo_regengis.png"}
    png_signature = b"\x89PNG\r\n\x1a\n"
    private_key = re.compile(r"(^|/)(id_rsa|id_dsa|id_ecdsa|id_ed25519|.*\.pem|.*\.key)$", re.I)
    failures = []
    for info in infos:
        name = info.filename
        rel = name[len(root)+1:] if name.startswith(root + '/') else name
        mode = (info.external_attr >> 16) & 0o777
        # ZIP directory entries commonly carry 0777; only release files must
        # be non-executable for QGIS File Analysis.
        file_type = (info.external_attr >> 28) & 0xF
        if file_type == 0xA:
            failures.append(f"unexpected symlink: {name}")
        if not info.is_dir() and mode & 0o111:
            failures.append(f"executable permission: {name} ({mode:o})")
        if any(part.startswith('.') for part in rel.split('/')) and name not in allowed_hidden:
            failures.append(f"hidden file: {name}")
        if any(token in name for token in forbidden_parts) or Path(rel).name in forbidden_names:
            failures.append(f"development/local artifact: {name}")
        is_allowed_png = name in allowed_pngs
        if Path(rel).suffix.lower() in binary_ext or private_key.search(rel):
            failures.append(f"binary/private-key/archive type: {name}")
        if not name.endswith('/'):
            data = zf.read(name)
            if Path(rel).suffix.lower() == ".png":
                if not is_allowed_png or not name.startswith(root + '/') or data[:8] != png_signature:
                    failures.append(f"unapproved or invalid PNG asset: {name}")
            elif b'\x00' in data:
                failures.append(f"binary content: {name}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        raise SystemExit(f"ZIP file analysis failed with {len(failures)} issue(s)")
    metadata = zf.read(f"{root}/metadata.txt").decode("utf-8")
    fields = dict(line.split('=', 1) for line in metadata.splitlines() if '=' in line and not line.startswith('#'))
    if fields.get("icon") != "icon.png" or f"{root}/icon.png" not in names:
        raise SystemExit("metadata icon=icon.png and root icon.png package entry are required")
    version = fields.get("version", "")
    if not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
        raise SystemExit(f"metadata version is not semver-like: {version!r}")
    changelog = zf.read(f"{root}/CHANGELOG.md").decode("utf-8")
    if not re.search(rf"^## {re.escape(version)}$", changelog, re.M):
        raise SystemExit(f"CHANGELOG.md has no exact ## {version} entry")
    for key in ("homepage", "tracker", "repository"):
        url = fields.get(key, "")
        if not re.fullmatch(r"https?://[^\s]+", url):
            raise SystemExit(f"metadata {key} is not a public http(s) URL: {url!r}")
        request = urllib.request.Request(url, headers={"User-Agent": f"RegenGIS-QGIS-release-preflight/{version}"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                final = response.geturl()
                status = response.status
        except (urllib.error.URLError, TimeoutError) as exc:
            raise SystemExit(f"metadata URL check failed for {key}={url}: {exc}") from exc
        if status != 200 or re.search(r"/(login|signin)(/|$)|/404(?:/|$)|RegenGIS/regengis_processing_plugin", final, re.I):
            raise SystemExit(f"metadata URL check failed for {key}: {url} -> {final} HTTP {status}")
        print(f"URL {key}: HTTP {status}, final={final}")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    print(f"ZIP file analysis: clean ({len(names)} entries, one root={root})")
    print(f"ZIP SHA-256: {digest}")
PY
}

case "$1" in
  --source) run_source ;;
  --zip) echo "ERROR: --zip requires a path" >&2; exit 2 ;;
  *)
    if [[ "$1" == --zip=* ]]; then run_zip "${1#--zip=}"; else usage; fi
    ;;
esac
