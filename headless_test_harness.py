"""Minimal headless provider smoke harness for RegenGIS.

This module deliberately keeps fixture execution out of Milestone 0. It validates
provider loading and emits a machine-readable diagnostic for later regression
scenarios.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
import shutil
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROVIDER_ID = "regengis_toolbox"
REPORT_FILENAME = "regengis-headless-report.json"
PLUGIN_ROOT = Path(__file__).resolve().parent
FIXTURE_CONTRACT_FILENAME = "regengis-fixture-contract.json"
EXPECTED_ALGORITHM_IDS = sorted([
    f"{PROVIDER_ID}:{name}" for name in (
        "about_regengis", "height_contours", "prepare_raster_for_analysis",
        "recommend_analysis_crs", "solar_radiation", "topographic_wetness_index",
        "water_flow",
    )
])


@dataclass(frozen=True)
class HarnessPaths:
    input_root: Path | None
    artifact_root: Path
    plugin_root: Path


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def validate_paths(
    input_root: str | Path | None,
    artifact_root: str | Path,
    plugin_root: str | Path | None = None,
    qgis_prefix_path: str | Path | None = None,
) -> HarnessPaths:
    """Validate explicit plugin/runtime roots and create external artifacts."""
    if plugin_root is None:
        raise ValueError("plugin root must be supplied explicitly")
    plugin = _resolved(Path(plugin_root))
    input_path = _resolved(Path(input_root)) if input_root is not None else None
    artifact = _resolved(Path(artifact_root))
    if not plugin.is_dir():
        raise ValueError(f"plugin root is not a directory: {plugin}")
    required = ("__init__.py", "metadata.txt", "processing_provider.py", "algorithms")
    missing = [name for name in required if not (plugin / name).exists()]
    if missing:
        raise ValueError(f"plugin root has invalid package structure; missing: {', '.join(missing)}")
    if artifact == plugin or plugin in artifact.parents:
        raise ValueError("artifact root must be outside the plugin source directory")
    if input_path is not None and not input_path.is_dir():
        raise ValueError(f"input/test-data root is not a directory: {input_path}")
    if qgis_prefix_path is not None and not _resolved(Path(qgis_prefix_path)).is_dir():
        raise ValueError(f"qgis prefix path is not a directory: {_resolved(Path(qgis_prefix_path))}")
    artifact.mkdir(parents=True, exist_ok=True)
    return HarnessPaths(input_path, artifact, plugin)


def new_report(
    *,
    qgis_version: str | None,
    provider_id: str,
    algorithm_ids: list[str],
    load_issues: list[dict[str, Any]],
    grass_available: bool | None,
    fixture_status: str,
    diagnostic: str,
    status: str | None = None,
    provider_health: str = "healthy",
) -> dict[str, Any]:
    """Build the stable report shape without importing QGIS."""
    if status is None:
        if provider_health != "healthy" or load_issues:
            status = "failed"
        elif fixture_status != "ready":
            status = "blocked"
        else:
            status = "ok"
    return {
        "status": status,
        "qgis_version": qgis_version,
        "provider_id": provider_id,
        "algorithm_ids": sorted(algorithm_ids),
        "load_issues": load_issues,
        "grass_provider_present": grass_available,
        "fixture_status": fixture_status,
        "diagnostic": diagnostic,
    }


def write_report(artifact_root: Path, report: dict[str, Any]) -> Path:
    """Write one structured JSON report and return its path."""
    path = artifact_root / REPORT_FILENAME
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _issue_dict(issue: Any) -> dict[str, Any]:
    if hasattr(issue, "__dataclass_fields__"):
        return asdict(issue)
    return {"error_message": str(issue)}


def _default_artifact_root() -> Path:
    configured = os.environ.get("REGENGIS_ARTIFACT_ROOT")
    if configured:
        return Path(configured)
    return Path(tempfile.gettempdir()) / "regengis-headless-artifacts"


def _fixture_status(input_root: Path | None) -> tuple[str, str]:
    if input_root is None:
        return "blocked", "Input/test-data root is absent; fixture validation was not run."
    contract = input_root / FIXTURE_CONTRACT_FILENAME
    if not contract.is_file():
        return "blocked", f"Fixture contract is missing: {contract}"
    try:
        payload = json.loads(contract.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "blocked", f"Fixture contract is unreadable: {exc}"
    project = payload.get("project") if isinstance(payload, dict) else None
    if not isinstance(project, str) or not project.strip():
        return "blocked", "Fixture contract must define a project path"
    project_path = _resolved(input_root / project)
    if input_root not in project_path.parents and project_path != input_root:
        return "blocked", "Fixture project must remain inside the input root"
    if not project_path.is_file():
        return "blocked", f"Fixture project does not exist: {project_path}"
    return "ready", f"Fixture contract verified: project={project_path}"


fixture_status = _fixture_status


@contextmanager
def _temporary_provider_copy(plugin_root: Path):
    """Yield an external provider copy and remove it after the run."""
    with tempfile.TemporaryDirectory(prefix="regengis-provider-") as temp_dir:
        runtime_root = Path(temp_dir) / plugin_root.name
        shutil.copytree(plugin_root, runtime_root)
        yield runtime_root


def _import_provider(plugin_root: Path):
    """Import the provider as part of the mounted plugin package.

    The repository entry point is also executable directly.  In that mode the
    repository parent is added temporarily so package-relative imports in the
    provider continue to work, just as they do when QGIS loads the plugin.
    """
    if __package__:
        return importlib.import_module(f"{__package__}.processing_provider").ModelToolboxProvider
    package_name = plugin_root.name
    if not package_name.isidentifier():
        raise ImportError(f"plugin directory is not a valid Python package name: {package_name}")
    parent = str(plugin_root.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    return importlib.import_module(f"{package_name}.processing_provider").ModelToolboxProvider


def run_harness(
    *,
    input_root: str | Path | None,
    artifact_root: str | Path,
    plugin_root: str | Path | None = None,
    qgis_prefix_path: str | None = None,
) -> tuple[int, Path]:
    """Run provider registration and write a report; return (exit_code, path)."""
    paths = validate_paths(input_root, artifact_root, plugin_root, qgis_prefix_path)
    fixture_status, diagnostic = _fixture_status(paths.input_root)
    try:
        from qgis.core import Qgis, QgsApplication
        from processing.core.Processing import Processing
    except ImportError as exc:
        report = new_report(
            qgis_version=None,
            provider_id=PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[{"error_type": type(exc).__name__, "error_message": str(exc)}],
            grass_available=None,
            fixture_status=fixture_status,
            diagnostic=f"QGIS runtime is unavailable: {exc}",
            status="blocked",
        )
        return 2, write_report(paths.artifact_root, report)
    try:
        # The provider's legacy load-status hooks target its package directory.
        # Load a temporary external copy so a read-only mounted source is never
        # written; the report records this harness-side redirection explicitly.
        with _temporary_provider_copy(paths.plugin_root) as runtime_root:
            ModelToolboxProvider = _import_provider(runtime_root)
            app = None
            provider = None
            try:
                if qgis_prefix_path:
                    QgsApplication.setPrefixPath(str(qgis_prefix_path), True)
                app = QgsApplication([], False)
                app.initQgis()
                Processing.initialize()
                provider = ModelToolboxProvider()
                registered = QgsApplication.processingRegistry().addProvider(provider)
                loaded_provider = QgsApplication.processingRegistry().providerById(PROVIDER_ID)
                issue_dicts = [_issue_dict(issue) for issue in provider.load_issues()]
                algorithm_ids = [algorithm.id() for algorithm in provider.algorithms()]
                registration_issues = [] if registered and loaded_provider is not None else [{
                    "error_type": "ProviderRegistrationError",
                    "error_message": "provider was not accepted by the QGIS processing registry",
                }]
                all_issues = registration_issues + issue_dicts
                if not all_issues and sorted(algorithm_ids) != EXPECTED_ALGORITHM_IDS:
                    all_issues.append({
                        "error_type": "AlgorithmInventoryError",
                        "error_message": f"expected exactly {EXPECTED_ALGORITHM_IDS}, got {sorted(algorithm_ids)}",
                    })
                report = new_report(
                    qgis_version=Qgis.QGIS_VERSION,
                    provider_id=PROVIDER_ID,
                    algorithm_ids=algorithm_ids,
                    load_issues=all_issues,
                    grass_available=QgsApplication.processingRegistry().providerById("grass") is not None,
                    fixture_status=fixture_status,
                    diagnostic=diagnostic + "; provider load-status writes redirected to an external temporary copy",
                )
                code = 0 if report["status"] == "ok" else (2 if report["status"] == "blocked" else 1)
                return code, write_report(paths.artifact_root, report)
            except Exception as exc:
                report = new_report(
                    qgis_version=getattr(Qgis, "QGIS_VERSION", None),
                    provider_id=PROVIDER_ID,
                    algorithm_ids=[algorithm.id() for algorithm in provider.algorithms()] if provider else [],
                    load_issues=[{"error_type": type(exc).__name__, "error_message": str(exc)}],
                    grass_available=None,
                    fixture_status=fixture_status,
                    diagnostic=f"Provider registration failed: {exc}",
                    status="failed",
                )
                return 1, write_report(paths.artifact_root, report)
            finally:
                if app is not None:
                    app.exitQgis()
    except Exception as exc:
        report = new_report(
            qgis_version=getattr(Qgis, "QGIS_VERSION", None), provider_id=PROVIDER_ID,
            algorithm_ids=[], load_issues=[{"error_type": type(exc).__name__, "error_message": str(exc)}],
            grass_available=None, fixture_status=fixture_status,
            diagnostic=f"Provider import failed; source writes redirected externally: {exc}",
            status="failed", provider_health="failed",
        )
        return 1, write_report(paths.artifact_root, report)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", default=os.environ.get("REGENGIS_INPUT_ROOT"))
    parser.add_argument("--artifact-root", default=_default_artifact_root())
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--qgis-prefix-path", default=os.environ.get("QGIS_PREFIX_PATH"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        code, report_path = run_harness(
            input_root=args.input_root,
            artifact_root=args.artifact_root,
            plugin_root=args.plugin_root,
            qgis_prefix_path=args.qgis_prefix_path,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(report_path)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
