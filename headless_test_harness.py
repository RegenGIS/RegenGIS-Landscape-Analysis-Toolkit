"""Fixed, contract-driven headless provider harness for RegenGIS.

The harness keeps source files read-only by executing a temporary provider copy,
then validates the fixed fixture contract and records evidence in one JSON report.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterator

PROVIDER_ID = "regengis_toolbox"
PLUGIN_PACKAGE_ID = "regengis_processing_plugin"
REPORT_FILENAME = "regengis-headless-report.json"
PLUGIN_ROOT = Path(__file__).resolve().parent
FIXTURE_CONTRACT_FILENAME = "regengis-fixture-contract.json"
EXECUTION_CASE_IDS = (
    "recommend_analysis_crs_rdnew",
    "prepare_raster_wgs84_auto",
    "height_contours_rdnew",
    "twi_rdnew",
    "water_flow_rdnew",
    "solar_radiation_rdnew",
)
ABOUT_CASE_ID = "about_regengis"
EXPECTED_ALGORITHM_IDS = sorted(
    f"{PROVIDER_ID}:{name}"
    for name in (
        ABOUT_CASE_ID,
        "height_contours",
        "prepare_raster_for_analysis",
        "recommend_analysis_crs",
        "solar_radiation",
        "topographic_wetness_index",
        "water_flow",
    )
)


@dataclass(frozen=True)
class HarnessPaths:
    """Resolved roots used by one harness run."""

    input_root: Path | None
    artifact_root: Path
    plugin_root: Path


def _resolved(path: Path) -> Path:
    """Resolve a path without requiring it to exist first."""
    return path.expanduser().resolve()


def _is_inside(path: Path, root: Path) -> bool:
    """Return whether the resolved path is contained by the resolved root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_returned_output(path: str | Path, artifact_root: Path) -> Path:
    """Resolve a returned output and reject paths outside the artifact root."""
    resolved_path = _resolved(Path(path))
    root = _resolved(artifact_root)
    if not _is_inside(resolved_path, root):
        raise ValueError(f"returned output escaped artifact root: {resolved_path}")
    return resolved_path


def validate_paths(
    input_root: str | Path | None,
    artifact_root: str | Path,
    plugin_root: str | Path | None = None,
    qgis_prefix_path: str | Path | None = None,
) -> HarnessPaths:
    """Validate explicit roots and create the external artifact directory."""
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


def _load_contract(input_root: Path) -> dict[str, Any]:
    """Load and validate the fixed contract, including dataset containment."""
    contract_path = input_root / FIXTURE_CONTRACT_FILENAME
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("execution_cases"), list):
        raise ValueError("fixture contract must declare execution_cases")
    datasets = payload.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError("fixture contract must define datasets")
    root = _resolved(input_root)
    for name, spec in datasets.items():
        filename = spec.get("filename") if isinstance(spec, dict) else None
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError(f"dataset {name} has no filename")
        dataset_path = _resolved(root / filename)
        if not _is_inside(dataset_path, root):
            raise ValueError(f"dataset {name} escaped input root: {dataset_path}")
        if not dataset_path.is_file():
            raise ValueError(f"dataset {name} is missing: {dataset_path}")
    cases = {case.get("id"): case for case in payload["execution_cases"] if isinstance(case, dict)}
    required_cases = (*EXECUTION_CASE_IDS, ABOUT_CASE_ID)
    missing = [case_id for case_id in required_cases if case_id not in cases]
    if missing:
        raise ValueError(f"fixture contract missing declared cases: {', '.join(missing)}")
    for case_id in required_cases:
        case = cases[case_id]
        expected_algorithm = f"{PROVIDER_ID}:about_regengis" if case_id == ABOUT_CASE_ID else case_id_to_algorithm(case_id)
        if case.get("algorithm_id") != expected_algorithm:
            raise ValueError(f"case {case_id} has unexpected algorithm_id: {case.get('algorithm_id')}")
        for dataset_name in (case.get("input") or {}).values():
            if dataset_name not in datasets:
                raise ValueError(f"case {case_id} references undeclared dataset: {dataset_name}")
    about = cases[ABOUT_CASE_ID]
    failure = about.get("failure_assertion", {}).get("headless", "")
    if "GUI" not in failure or "skip" not in failure.lower():
        raise ValueError("About case must declare an explicit headless GUI skip contract")
    return payload


def case_id_to_algorithm(case_id: str) -> str:
    """Map fixed scenario IDs to their declared provider algorithm IDs."""
    mapping = {
        "recommend_analysis_crs_rdnew": "recommend_analysis_crs",
        "prepare_raster_wgs84_auto": "prepare_raster_for_analysis",
        "height_contours_rdnew": "height_contours",
        "twi_rdnew": "topographic_wetness_index",
        "water_flow_rdnew": "water_flow",
        "solar_radiation_rdnew": "solar_radiation",
    }
    try:
        return f"{PROVIDER_ID}:{mapping[case_id]}"
    except KeyError as exc:
        raise ValueError(f"unknown fixed execution case: {case_id}") from exc


def _fixture_status(input_root: Path | None) -> tuple[str, str]:
    """Return the established blocked/ready fixture status and diagnostic."""
    if input_root is None:
        return "blocked", "Input/test-data root is absent; fixture validation was not run."
    contract = input_root / FIXTURE_CONTRACT_FILENAME
    if not contract.is_file():
        return "blocked", f"Fixture contract is missing: {contract}"
    try:
        payload = json.loads(contract.read_text(encoding="utf-8"))
        project = payload.get("project") if isinstance(payload, dict) else None
        if not isinstance(project, str) or not project.strip():
            raise ValueError("fixture contract must define a project path")
        project_path = _resolved(input_root / project)
        if not _is_inside(project_path, _resolved(input_root)) or not project_path.is_file():
            raise ValueError(f"fixture project must exist inside input root: {project_path}")
        _load_contract(input_root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return "blocked", f"Fixture contract is unreadable or invalid: {exc}"
    return "ready", f"Fixture contract verified: project={project_path}"


fixture_status = _fixture_status


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
    plugin_import: dict[str, Any] | None = None,
    functional_checks: list[dict[str, Any]] | None = None,
    grass_baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the stable machine-readable report and aggregate check status."""
    checks = list(functional_checks or [])
    plugin = plugin_import or {"status": "not_run"}
    if status is None:
        if provider_health != "healthy" or load_issues or plugin.get("status") == "failed":
            status = "failed"
        elif any(check.get("status") == "failed" for check in checks):
            status = "failed"
        elif (grass_baseline or {}).get("status") in {"failed", "materialization_failed", "unavailable"}:
            status = "failed"
        elif fixture_status != "ready":
            status = "blocked"
        else:
            status = "ok"
    if plugin.get("status") == "failed":
        status = "failed"
    return {
        "status": status,
        "qgis_version": qgis_version,
        "provider_id": provider_id,
        "algorithm_ids": sorted(algorithm_ids),
        "load_issues": load_issues,
        "grass_provider_present": grass_available,
        "fixture_status": fixture_status,
        "diagnostic": diagnostic,
        "plugin_import": plugin,
        "functional_checks": checks,
        "grass_baseline": grass_baseline or {"status": "not_run"},
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
    return Path(configured) if configured else Path(tempfile.gettempdir()) / "regengis-headless-artifacts"


@contextmanager
def _temporary_provider_copy(plugin_root: Path) -> Iterator[Path]:
    """Yield an external provider copy and remove it even after a failure."""
    with tempfile.TemporaryDirectory(prefix="regengis-provider-") as temp_dir:
        runtime_root = Path(temp_dir) / PLUGIN_PACKAGE_ID
        shutil.copytree(plugin_root, runtime_root)
        yield runtime_root


@contextmanager
def _temporary_plugin_imports(
    runtime_plugin_root: Path,
    source_plugin_root: Path,
    qgis_utils: Any | None = None,
) -> Iterator[dict[str, Any]]:
    """Import plugin modules from a copy while registering it with QGIS.

    QGIS discovers Python plugins through ``qgis.utils.plugin_paths`` and tracks
    loaded plugin packages in ``available_plugins``. Its ``_import`` wrapper
    relies on that registration while lazy Processing imports happen. Keep both
    QGIS state and the temporary import root alive for the complete execution.
    """
    runtime_plugin_root = _resolved(runtime_plugin_root)
    source_plugin_root = _resolved(source_plugin_root)
    package_name = PLUGIN_PACKAGE_ID
    if runtime_plugin_root.name != package_name:
        raise ValueError(
            f"temporary plugin root must be named {package_name}: {runtime_plugin_root}"
        )
    package_prefix = f"{package_name}."
    original_path = list(sys.path)
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == package_name or name.startswith(package_prefix)
    }
    original_plugin_paths = list(getattr(qgis_utils, "plugin_paths", [])) if qgis_utils is not None else None
    original_available_plugins = list(getattr(qgis_utils, "available_plugins", [])) if qgis_utils is not None else None
    original_plugin_modules = dict(getattr(qgis_utils, "_plugin_modules", {})) if qgis_utils is not None else None

    def normalise_path_entry(entry: str) -> Path:
        # An empty sys.path entry means the current working directory.
        return _resolved(Path(entry or os.curdir))

    source_paths = {source_plugin_root, source_plugin_root.parent}
    try:
        sys.path[:] = [
            entry for entry in sys.path
            if normalise_path_entry(entry) not in source_paths
        ]
        # This is the sole import root added for the temporary package.
        sys.path.insert(0, str(runtime_plugin_root.parent))
        # Remove any source-loaded package before QGIS loadPlugin() so its
        # native loader cannot reuse modules from the mounted source root.
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_prefix):
                del sys.modules[name]
        if qgis_utils is not None:
            plugin_paths = list(getattr(qgis_utils, "plugin_paths", []))
            if str(runtime_plugin_root.parent) not in plugin_paths:
                plugin_paths.insert(0, str(runtime_plugin_root.parent))
            qgis_utils.plugin_paths = plugin_paths
            # QGIS's native registration path refreshes available_plugins from
            # metadata.txt, which is consulted by qgis.utils._import.
            qgis_utils.updateAvailablePlugins()
            sys.path_importer_cache.clear()
            # QGIS's loader establishes the package in the same way as normal
            # plugin discovery.  This is required for the lazy import wrapper,
            # not just for the provider registry.
            load_plugin = getattr(qgis_utils, "loadPlugin", None)
            if load_plugin is not None and not load_plugin(package_name):
                raise ImportError(f"QGIS could not load registered plugin package: {package_name}")
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_prefix):
                del sys.modules[name]
        plugin = importlib.import_module(f"{package_name}.plugin")
        provider = importlib.import_module(f"{package_name}.processing_provider")
        yield {"plugin": plugin, "provider": provider}
    finally:
        sys.path[:] = original_path
        for name in list(sys.modules):
            if name == package_name or name.startswith(package_prefix):
                del sys.modules[name]
        sys.modules.update(original_modules)
        if qgis_utils is not None:
            qgis_utils.plugin_paths = original_plugin_paths
            qgis_utils.updateAvailablePlugins()
            qgis_utils.available_plugins = original_available_plugins
            if original_plugin_modules is not None:
                qgis_utils._plugin_modules = original_plugin_modules
            sys.path_importer_cache.clear()


def _import_provider(plugin_root: Path):
    """Import the provider as a package, as QGIS does."""
    if __package__:
        return importlib.import_module(f"{PLUGIN_PACKAGE_ID}.processing_provider").ModelToolboxProvider
    if str(plugin_root.parent) not in sys.path:
        sys.path.insert(0, str(plugin_root.parent))
    return importlib.import_module(f"{PLUGIN_PACKAGE_ID}.processing_provider").ModelToolboxProvider


def _import_plugin(plugin_root: Path) -> dict[str, Any]:
    """Import plugin.py and preserve the approved QAction evidence."""
    module = importlib.import_module(f"{PLUGIN_PACKAGE_ID}.plugin")
    return {"status": "ok", "qaction_module": module.QAction.__module__}


def _qgis_lazy_import_proof(qgis_utils: Any, runtime_plugin_root: Path) -> dict[str, Any]:
    """Exercise QGIS's actual import wrapper and return redacted fixed evidence."""
    module_name = f"{PLUGIN_PACKAGE_ID}.autocrs.prepare"
    runtime_root = _resolved(runtime_plugin_root)
    package_name = PLUGIN_PACKAGE_ID
    package = sys.modules.get(package_name)
    state: dict[str, Any] = {
        "module": module_name,
        "registered_package": package_name in getattr(qgis_utils, "available_plugins", []),
        "package_loaded": package is not None,
        "runtime_parent_on_sys_path": str(runtime_root.parent) in {
            str(_resolved(Path(entry or os.curdir))) for entry in sys.path
        },
    }
    if package is not None:
        package_path = getattr(package, "__path__", [])
        state["package_path_in_temporary_copy"] = any(
            _is_inside(_resolved(Path(entry)), runtime_root) for entry in package_path
        )
    try:
        module = qgis_utils._import(module_name, {}, {}, ["*"], 0)
        module_path = _resolved(Path(module.__file__))
        state.update(
            status="ok",
            module_path=str(module_path),
            from_temporary_copy=_is_inside(module_path, runtime_root),
        )
    except Exception as exc:
        state.update(
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc).replace(str(runtime_root), "<runtime-copy>"),
        )
    return state


def _output_path(artifact_root: Path, case_id: str, key: str) -> Path:
    """Create a deterministic destination below the artifact root."""
    suffix = ".gpkg" if key == "Height_contours" else ".tif"
    path = _validate_returned_output(artifact_root / case_id / f"{key}{suffix}", artifact_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _case_entry(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "algorithm_id": case["algorithm_id"],
        "status": "failed",
        "assertions": [],
        "failure": None,
    }


def _assert(check: dict[str, Any], outcome: bool, assertion: str, evidence: Any = None) -> None:
    """Record one explicit contract assertion and its evidence."""
    item: dict[str, Any] = {"assertion": assertion, "passed": bool(outcome)}
    if evidence is not None:
        item["evidence"] = evidence
    check["assertions"].append(item)
    if not outcome and check["failure"] is None:
        check["failure"] = assertion


def _declared_output_keys(expected: dict[str, Any]) -> list[str]:
    keys = list(expected.get("output_keys", []))
    if expected.get("output_key"):
        keys.append(expected["output_key"])
    return keys


def _optional_output_keys(expected: dict[str, Any]) -> list[str]:
    """Return optional output keys that are present in the contract."""
    return list(expected.get("optional_output_keys", []))


def _check_metadata_assertions(check: dict[str, Any], expected: dict[str, Any], result: dict[str, Any]) -> None:
    """Evaluate every declared metadata assertion with explicit mappings."""
    required = expected.get("required_result_keys", [])
    for key in required:
        _assert(check, key in result, f"result key {key} exists")
    rules = {
        "OUTPUT_CRS": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_DESCRIPTION": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_PROJ": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_STRATEGY": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_DISTORTION_PPM": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
        "OUTPUT_IS_UTM": lambda value: isinstance(value, bool),
        "OUTPUT_SOURCE_CRS": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_TARGET_CRS": lambda value: isinstance(value, str) and bool(value.strip()),
        "OUTPUT_WAS_REPROJECTED": lambda value: isinstance(value, bool),
    }
    for key, rule in rules.items():
        if key in required:
            _assert(check, key in result and rule(result[key]), f"{key} has the declared value type/readability rule", result.get(key))
    for assertion in expected.get("assertions", []):
        if assertion == "OUTPUT_CRS is non-empty":
            _assert(check, isinstance(result.get("OUTPUT_CRS"), str) and bool(result["OUTPUT_CRS"].strip()), assertion)
        elif assertion == "OUTPUT_STRATEGY is non-empty":
            _assert(check, isinstance(result.get("OUTPUT_STRATEGY"), str) and bool(result["OUTPUT_STRATEGY"].strip()), assertion)
        elif assertion == "OUTPUT_IS_UTM is boolean":
            _assert(check, isinstance(result.get("OUTPUT_IS_UTM"), bool), assertion)
        elif assertion == "OUTPUT_TARGET_CRS equals the reported target CRS":
            _assert(check, isinstance(result.get("OUTPUT_TARGET_CRS"), str) and bool(result["OUTPUT_TARGET_CRS"].strip()), assertion)
        elif assertion == "source and target differ implies OUTPUT_WAS_REPROJECTED=true":
            source = result.get("OUTPUT_SOURCE_CRS")
            target = result.get("OUTPUT_TARGET_CRS")
            _assert(check, source == target or result.get("OUTPUT_WAS_REPROJECTED") is True, assertion)
        elif assertion == "OPENED=true only when a GUI dialog can be opened":
            _assert(check, False, "About is explicitly skipped in headless mode")
        elif assertion == "OUTPUT exists and is readable":
            _assert(check, expected_output_key(result) in result, assertion)
        else:
            _assert(check, False, f"unrecognized contract assertion: {assertion}")


def expected_output_key(result: dict[str, Any]) -> str:
    """Return the fixed raster output key used by the preparation case."""
    return "OUTPUT"


def _raster_has_valid_numeric_samples(layer: Any) -> tuple[bool, dict[str, Any]]:
    """Return numeric-data evidence without imposing dataset-specific value ranges."""
    provider = layer.dataProvider()
    try:
        from qgis.core import QgsRasterBandStats
        stats = provider.bandStatistics(1, QgsRasterBandStats.All, layer.extent(), 0)
        valid_count = getattr(stats, "elementCount", getattr(stats, "count", 0))
        minimum = getattr(stats, "minimumValue", getattr(stats, "minimum", None))
        maximum = getattr(stats, "maximumValue", getattr(stats, "maximum", None))
        import math
        valid = int(valid_count or 0) > 0 and minimum is not None and maximum is not None
        valid = valid and math.isfinite(float(minimum)) and math.isfinite(float(maximum))
        return bool(valid), {"valid_count": int(valid_count or 0), "minimum": minimum, "maximum": maximum}
    except Exception as exc:
        return False, {"error": f"band statistics unavailable: {type(exc).__name__}: {exc}"}


def _check_returned_raster(
    check: dict[str, Any],
    key: str,
    value: Any,
    artifact_root: Path,
    expected_crs: str,
) -> Any:
    """Validate one returned raster path, including containment and numeric data."""
    path = _validate_returned_output(value, artifact_root)
    check.setdefault("outputs", {})[key] = {
        "path": str(path),
        "contained": _is_inside(path, _resolved(artifact_root)),
    }
    from qgis.core import QgsRasterLayer

    layer = QgsRasterLayer(str(path), key)
    _assert(check, path.is_file(), f"{key} path exists", str(path))
    _assert(check, layer.isValid(), f"{key} is QGIS-readable", layer.isValid())
    if layer.isValid():
        _assert(check, layer.width() > 0 and layer.height() > 0, f"{key} dimensions are non-empty", [layer.width(), layer.height()])
        _assert(check, not layer.extent().isEmpty(), f"{key} extent is non-empty", layer.extent().toString())
        _assert(check, layer.crs().authid() == expected_crs, f"{key} CRS matches contract", layer.crs().authid())
        has_numeric_data, numeric_evidence = _raster_has_valid_numeric_samples(layer)
        _assert(check, has_numeric_data, f"{key} contains valid non-NoData numeric samples", numeric_evidence)
    return layer


def _check_case_outputs(
    check: dict[str, Any],
    case: dict[str, Any],
    result: dict[str, Any],
    contract: dict[str, Any],
    input_root: Path,
    artifact_root: Path,
) -> None:
    expected = case.get("expected", {})
    datasets = contract["datasets"]
    declared_input = next(iter((case.get("input") or {}).values()))
    input_crs = datasets[declared_input]["crs"]
    output_keys = _declared_output_keys(expected)
    for key in output_keys:
        _assert(check, key in result, f"result key {key} exists")
    if expected.get("kind") == "metadata":
        _check_metadata_assertions(check, expected, result)
        return
    if expected.get("kind") == "raster_with_metadata":
        _check_metadata_assertions(check, expected, result)
        target_crs = result.get("OUTPUT_TARGET_CRS")
        if isinstance(target_crs, str):
            layer = _check_returned_raster(check, expected["output_key"], result.get(expected["output_key"]), artifact_root, target_crs)
            _assert(
                check,
                layer.isValid() and layer.crs().authid() == target_crs,
                "OUTPUT_TARGET_CRS equals the returned raster CRS",
                layer.crs().authid() if layer.isValid() else None,
            )
        return
    if expected.get("kind") == "vector":
        path = _validate_returned_output(result.get(expected["output_key"]), artifact_root)
        check.setdefault("outputs", {})[expected["output_key"]] = {
            "path": str(path),
            "contained": _is_inside(path, _resolved(artifact_root)),
        }
        from qgis.core import QgsVectorLayer

        layer = QgsVectorLayer(str(path), "contours", "ogr")
        _assert(check, path.is_file() and layer.isValid(), "vector output is readable", str(path))
        if layer.isValid():
            _assert(check, layer.geometryType() == 1, "vector geometry is line")
            required_fields = expected.get("required_fields", [])
            field_names = [field.name() for field in layer.fields()]
            for field_name in required_fields:
                _assert(check, field_name in field_names, f"{field_name} field exists")
            _assert(check, layer.crs().authid() == input_crs, "contour CRS equals declared input CRS", layer.crs().authid())
        return
    if expected.get("kind") in ("raster", "multi_raster"):
        layers = []
        actual_output_keys = output_keys + [key for key in _optional_output_keys(expected) if key in result]
        for key in actual_output_keys:
            if key in result:
                layers.append(_check_returned_raster(check, key, result[key], artifact_root, input_crs))
        _assert(check, bool(layers), "declared raster outputs are present")
        if expected.get("same_crs_dimensions_extent") and len(layers) > 1:
            signatures = {(layer.width(), layer.height(), layer.extent().toString(), layer.crs().authid()) for layer in layers if layer.isValid()}
            _assert(check, len(signatures) == 1, "multi-raster outputs share CRS/dimensions/extent")


def _grass_prerequisites(case: dict[str, Any], registry: Any) -> list[str]:
    """Check exact qualified GRASS registry IDs declared by the contract."""
    missing: list[str] = []
    for prerequisite in case.get("prerequisites", []):
        if prerequisite == "GRASS provider present":
            if registry.providerById("grass") is None:
                missing.append("grass")
            continue
        if prerequisite.startswith("GRASS ") and prerequisite.endswith(" available"):
            names = prerequisite[len("GRASS ") : -len(" available")]
            algorithm_ids = [f"grass:{name.strip()}" for name in names.split(" and ")]
            missing.extend(algorithm_id for algorithm_id in algorithm_ids if registry.algorithmById(algorithm_id) is None)
    return missing


def _processing_value(value: Any) -> Any:
    """Convert QGIS Processing values into stable JSON evidence."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_processing_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _processing_value(item) for key, item in value.items()}
    return str(value)


def _grass_parameter_definition(definition: Any) -> dict[str, Any]:
    """Record the portable parts of one QGIS Processing parameter definition."""
    payload: dict[str, Any] = {}
    for method_name, key in (("name", "name"), ("description", "description"),
                             ("type", "type"), ("defaultValue", "default")):
        try:
            value = getattr(definition, method_name)()
        except Exception as exc:
            value = f"<unavailable: {type(exc).__name__}: {exc}>"
        payload[key] = _processing_value(value)
    return payload


def _grass_baseline_feedback(feedback_class: Any) -> Any:
    """Create a real QgsProcessingFeedback subclass so SIP accepts it."""
    class CapturingFeedback(feedback_class):
        def __init__(self) -> None:
            super().__init__()
            self.messages: list[dict[str, str]] = []

        def _record(self, kind: str, message: Any) -> None:
            self.messages.append({"kind": kind, "message": str(message)})

        def reportError(self, error: Any, fatalError: bool = False) -> None:
            self._record("error", error)
            try:
                super().reportError(error, fatalError)
            except TypeError:
                super().reportError(error)

        def pushInfo(self, info: Any) -> None:
            self._record("info", info)
            super().pushInfo(info)

        def pushWarning(self, warning: Any) -> None:
            self._record("warning", warning)
            super().pushWarning(warning)

        def pushCommandInfo(self, info: Any) -> None:
            self._record("command", info)
            super().pushCommandInfo(info)

        def pushConsoleInfo(self, info: Any) -> None:
            self._record("console", info)
            super().pushConsoleInfo(info)

        def pushDebugInfo(self, info: Any) -> None:
            self._record("debug", info)
            super().pushDebugInfo(info)

        def setProgressText(self, text: Any) -> None:
            self._record("progress", text)
            super().setProgressText(text)

    return CapturingFeedback()


def _run_grass_baseline(
    input_root: Path,
    artifact_root: Path,
    contract: dict[str, Any],
    registry: Any,
    processing: Any,
    feedback_class: Any,
    context: Any,
) -> dict[str, Any]:
    """Run one direct GRASS call as a provider/runtime discriminator."""
    algorithm_id = "grass:r.topidx"
    baseline: dict[str, Any] = {
        "id": "grass_r_topidx_direct_baseline",
        "algorithm_id": algorithm_id,
        "status": "not_run",
        "feedback": [],
        # Fixed, read-only runtime probes: they distinguish a missing GRASS/GDAL
        # executable from a plugin parameterisation defect without exposing a shell.
        "runtime_executables": {
            "grass": shutil.which("grass"),
            "grass84": shutil.which("grass84"),
            "gdal_translate": shutil.which("gdal_translate"),
        },
    }
    provider = registry.providerById("grass")
    algorithm = registry.algorithmById(algorithm_id)
    if provider is None or algorithm is None:
        baseline["status"] = "unavailable"
        baseline["failure"] = "GRASS provider or grass:r.topidx is not registered"
        return baseline

    dtm_name = "dtm_rdnew"
    dtm_path = _resolved(input_root / contract["datasets"][dtm_name]["filename"])
    output_path = _resolved(artifact_root / "grass_baseline" / "r_topidx_direct.tif")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    parameter_definitions = list(algorithm.parameterDefinitions())
    output_definitions = list(algorithm.outputDefinitions())
    baseline["parameter_definitions"] = [_grass_parameter_definition(item) for item in parameter_definitions]
    baseline["output_definitions"] = [_grass_parameter_definition(item) for item in output_definitions]
    names = {item["name"] for item in baseline["parameter_definitions"]}
    output_name = "output" if "output" in names else next(
        (name for name in names if name.lower() in {"output", "result"}), None
    )
    input_name = "elevation" if "elevation" in names else next(
        (name for name in names if name.lower() in {"input", "elevation", "map"}), None
    )
    baseline["parameter_names"] = sorted(names)
    baseline["selected_input_parameter"] = input_name
    baseline["selected_output_parameter"] = output_name
    if input_name is None or output_name is None:
        baseline["status"] = "failed"
        baseline["failure"] = "Could not identify fixed r.topidx input/output parameter names"
        return baseline

    params: dict[str, Any] = {input_name: str(dtm_path), output_name: str(output_path)}
    for name, value in (("GRASS_RASTER_FORMAT_OPT", ""), ("GRASS_RASTER_FORMAT_META", "")):
        if name in names:
            params[name] = value
    baseline["parameters"] = _processing_value(params)
    feedback = _grass_baseline_feedback(feedback_class)
    try:
        result = processing.run(algorithm_id, params, context=context, feedback=feedback)
        baseline["result"] = _processing_value(result)
        baseline["requested_output"] = str(output_path)
        baseline["path_exists"] = output_path.is_file()
        result_output = result.get(output_name) if isinstance(result, dict) else None
        if result_output is not None:
            result_path = _resolved(Path(str(result_output)))
            baseline["result_output_path"] = str(result_path)
            baseline["result_output_exists"] = result_path.is_file()
        from qgis.core import QgsRasterLayer
        layer = QgsRasterLayer(str(output_path), "grass_r_topidx_direct_baseline")
        baseline["readable_raster"] = bool(layer.isValid())
        if layer.isValid():
            baseline["raster"] = {
                "width": layer.width(), "height": layer.height(),
                "bands": layer.bandCount(), "crs": layer.crs().authid(),
                "extent": layer.extent().toString(),
            }
        baseline["status"] = "passed" if baseline["path_exists"] and baseline["readable_raster"] else "materialization_failed"
    except Exception as exc:
        baseline["status"] = "failed"
        baseline["failure"] = f"{type(exc).__name__}: {exc}"
    baseline["feedback"] = feedback.messages
    return baseline


def _run_functional_cases(
    contract: dict[str, Any],
    input_root: Path,
    artifact_root: Path,
    registry: Any,
    processing: Any,
    context: Any,
    feedback: Any,
) -> list[dict[str, Any]]:
    """Execute only the six fixed cases and record the explicit About skip."""
    datasets = contract["datasets"]
    cases = {case["id"]: case for case in contract["execution_cases"]}
    checks: list[dict[str, Any]] = []
    for case_id in (*EXECUTION_CASE_IDS, ABOUT_CASE_ID):
        case = cases[case_id]
        check = _case_entry(case)
        if case_id == ABOUT_CASE_ID:
            check.update(
                status="skipped",
                reason=case["failure_assertion"]["headless"],
            )
            checks.append(check)
            continue
        missing = _grass_prerequisites(case, registry)
        if missing:
            check["failure"] = f"Missing declared prerequisite registry IDs: {', '.join(missing)}"
            check["diagnostic"] = "Prerequisites are a failed diagnostic; the case was not silently skipped."
            checks.append(check)
            continue
        try:
            params: dict[str, Any] = {}
            for parameter, dataset_name in (case.get("input") or {}).items():
                params[parameter] = str(_resolved(input_root / datasets[dataset_name]["filename"]))
            params.update(case.get("parameters") or {})
            for key in _declared_output_keys(case.get("expected", {})):
                params[key] = str(_output_path(artifact_root, case_id, key))
            algorithm_id = case["algorithm_id"]
            result = processing.run(algorithm_id, params, context=context, feedback=feedback)
            check["result_keys"] = sorted(result)
            _check_case_outputs(check, case, result, contract, input_root, artifact_root)
            check["status"] = "passed" if all(item["passed"] for item in check["assertions"]) else "failed"
        except Exception as exc:
            check["failure"] = f"{type(exc).__name__}: {exc}"
        checks.append(check)
    return checks


def run_harness(
    *,
    input_root: str | Path | None,
    artifact_root: str | Path,
    plugin_root: str | Path | None = None,
    qgis_prefix_path: str | Path | None = None,
) -> tuple[int, Path]:
    """Run fixture, provider, plugin-import, and functional checks safely."""
    paths = validate_paths(input_root, artifact_root, plugin_root, qgis_prefix_path)
    fixture_state, diagnostic = _fixture_status(paths.input_root)
    if fixture_state != "ready":
        report = new_report(
            qgis_version=None,
            provider_id=PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[],
            grass_available=None,
            fixture_status=fixture_state,
            diagnostic=diagnostic,
        )
        return 2, write_report(paths.artifact_root, report)
    try:
        from qgis.core import Qgis, QgsApplication, QgsProcessingContext, QgsProcessingFeedback
        from processing.core.Processing import Processing
    except ImportError as exc:
        report = new_report(
            qgis_version=None,
            provider_id=PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[{"error_type": type(exc).__name__, "error_message": str(exc)}],
            grass_available=None,
            fixture_status=fixture_state,
            diagnostic=f"QGIS runtime is unavailable: {exc}",
            status="blocked",
        )
        return 2, write_report(paths.artifact_root, report)

    app = None
    try:
        assert paths.input_root is not None
        with _temporary_provider_copy(paths.plugin_root) as runtime_root:
            if qgis_prefix_path:
                QgsApplication.setPrefixPath(str(qgis_prefix_path), True)
            app = QgsApplication([], False)
            app.initQgis()
            Processing.initialize()
            # Keep this import context open through Processing execution. Algorithm
            # modules are imported lazily by QGIS/Processing, so restoring sys.path
            # immediately after provider registration makes the copied package
            # disappear and reproduces ModuleNotFoundError.
            import qgis.utils as qgis_utils
            with _temporary_plugin_imports(runtime_root, paths.plugin_root, qgis_utils):
                plugin_import = _import_plugin(runtime_root)
                lazy_proof = _qgis_lazy_import_proof(qgis_utils, runtime_root)
                plugin_import["qgis_lazy_import_proof"] = lazy_proof
                if lazy_proof.get("status") != "ok" or not lazy_proof.get("from_temporary_copy"):
                    plugin_import["status"] = "failed"
                provider_class = _import_provider(runtime_root)
                provider = provider_class()
                registered = QgsApplication.processingRegistry().addProvider(provider)
                registry = QgsApplication.processingRegistry()
                load_issues = [_issue_dict(issue) for issue in provider.load_issues()]
                algorithm_ids = [algorithm.id() for algorithm in provider.algorithms()]
                if not registered or registry.providerById(PROVIDER_ID) is None:
                    load_issues.append({
                        "error_type": "ProviderRegistrationError",
                        "error_message": "provider was not accepted by the QGIS processing registry",
                    })
                if not load_issues and sorted(algorithm_ids) != EXPECTED_ALGORITHM_IDS:
                    load_issues.append({
                        "error_type": "AlgorithmInventoryError",
                        "error_message": f"expected exactly {EXPECTED_ALGORITHM_IDS}, got {sorted(algorithm_ids)}",
                    })
                checks = []
                grass_baseline = {"status": "not_run", "reason": "plugin provider load failed"}
                contract = _load_contract(paths.input_root)
                import processing
                if not load_issues:
                    checks = _run_functional_cases(
                        contract,
                        paths.input_root,
                        paths.artifact_root,
                        registry,
                        processing,
                        QgsProcessingContext(),
                        QgsProcessingFeedback(),
                    )
                # This is intentionally one fixed direct GRASS call. It is a
                # runtime/provider discriminator, not a plugin API or user option.
                grass_baseline = _run_grass_baseline(
                    paths.input_root,
                    paths.artifact_root,
                    contract,
                    registry,
                    processing,
                    QgsProcessingFeedback,
                    QgsProcessingContext(),
                )
                report = new_report(
                    qgis_version=Qgis.QGIS_VERSION,
                    provider_id=PROVIDER_ID,
                    algorithm_ids=algorithm_ids,
                    load_issues=load_issues,
                    grass_available=registry.providerById("grass") is not None,
                    fixture_status=fixture_state,
                    diagnostic=diagnostic + "; provider load-status writes redirected to an external temporary copy",
                    plugin_import=plugin_import,
                    functional_checks=checks,
                    grass_baseline=grass_baseline,
                )
                code = 0 if report["status"] == "ok" else 1
                return code, write_report(paths.artifact_root, report)
    except Exception as exc:
        report = new_report(
            qgis_version=locals().get("Qgis", None) and getattr(Qgis, "QGIS_VERSION", None),
            provider_id=PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[{"error_type": type(exc).__name__, "error_message": str(exc)}],
            grass_available=None,
            fixture_status=fixture_state,
            diagnostic=f"Provider import or functional execution failed: {exc}",
            status="failed",
            provider_health="failed",
            plugin_import={"status": "failed", "error_type": type(exc).__name__, "error_message": str(exc)},
        )
        return 1, write_report(paths.artifact_root, report)
    finally:
        if app is not None:
            app.exitQgis()


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
