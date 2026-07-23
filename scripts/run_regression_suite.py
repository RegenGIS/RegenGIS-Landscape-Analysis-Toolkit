#!/usr/bin/env python3
"""Run RegenGIS scenario manifests and emit a JSON report.

Designed so it is still useful on machines without QGIS:
- `--dry-run` resolves scenarios and shows the exact commands it would run
- suite/scenario wiring is validated before execution
- GUI-only scenarios (for example about/community actions) are skipped unless
  `--include-gui` is set explicitly

When QGIS is available, the runner supports two backends:
- `qgis_process`
- `pyqgis_direct` (direct provider registration, no plugin-enable step)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent
PLUGIN_PARENT = PLUGIN_ROOT.parent


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [expand(v) for v in value]
    if isinstance(value, dict):
        return {k: expand(v) for k, v in value.items()}
    return value


def discover_qgis_process(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    return shutil.which("qgis_process")


def discover_runner(requested: str, qgis_process_bin: str | None) -> str:
    if requested != "auto":
        return requested
    return "qgis_process" if qgis_process_bin else "pyqgis_direct"


def load_suite_scenarios(suite_path: Path) -> list[Path]:
    suite = load_yaml(suite_path)
    rels = suite.get("scenarios")
    if not isinstance(rels, list) or not rels:
        raise ValueError(f"Suite has no scenarios: {suite_path}")
    return [(suite_path.parent / rel).resolve() for rel in rels]


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def scenario_contract_path(scenario_path: Path, scenario: dict[str, Any]) -> Path:
    contract_rel = scenario.get("contract")
    if not contract_rel:
        raise ValueError(f"Scenario is missing contract path: {scenario_path}")
    return (scenario_path.parent / contract_rel).resolve()


def scenario_is_gui_only(scenario: dict[str, Any]) -> bool:
    requires = scenario.get("requires") or {}
    execution = scenario.get("execution") or {}
    if requires.get("headless_safe_by_default") is False:
        return True
    return execution.get("mode") == "pyqgis_or_gui"


def scenario_requires_grass(scenario: dict[str, Any]) -> bool:
    requires = scenario.get("requires") or {}
    return bool(requires.get("grass_provider"))


def build_parameter_map(scenario: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name, spec in (scenario.get("inputs") or {}).items():
        if isinstance(spec, dict) and "path" in spec:
            params[name] = expand(spec["path"])
    for name, value in (scenario.get("parameters") or {}).items():
        if value is not None:
            params[name] = expand(value)
    for name, spec in (scenario.get("outputs") or {}).items():
        if isinstance(spec, dict) and "path" in spec:
            output_path = Path(expand(spec["path"]))
            ensure_parent(output_path)
            params[name] = str(output_path)
    return params


def qgis_process_command(qgis_process_bin: str, scenario: dict[str, Any]) -> list[str]:
    command = [qgis_process_bin, "run", scenario["algorithm_id"], "--json"]
    for key, value in build_parameter_map(scenario).items():
        command.append(f"--{key}={value}")
    return command


def python_command(script: Path, *args: str) -> list[str]:
    return [sys.executable, str(script), *args]


def run_subprocess(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True)


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    return str(value)


def maybe_write_result_capture(scenario: dict[str, Any], result: dict[str, Any]) -> str | None:
    capture = scenario.get("result_capture") or {}
    raw_path = capture.get("path")
    if not raw_path:
        return None
    expanded_path = expand(raw_path)
    if not isinstance(expanded_path, str) or not expanded_path:
        raise ValueError("result_capture.path must resolve to a non-empty string")
    output_path = Path(expanded_path)
    ensure_parent(output_path)
    output_path.write_text(json.dumps(jsonable(result), indent=2) + "\n", encoding="utf-8")
    return str(output_path)


def run_pyqgis_direct(scenario: dict[str, Any]) -> dict[str, Any]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    if str(PLUGIN_PARENT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_PARENT))

    import qgis  # type: ignore
    import processing  # type: ignore
    from processing.core.Processing import Processing  # type: ignore
    from qgis.core import QgsApplication, QgsProcessingFeedback  # type: ignore
    from regengis_processing_plugin.processing_provider import (  # type: ignore
        ModelToolboxProvider,
    )

    qgis_file = getattr(qgis, "__file__", None)
    if not qgis_file:
        raise RuntimeError("qgis.__file__ is unavailable; cannot infer QGIS prefix path")
    qgis_module_path = Path(qgis_file).resolve()
    prefix_path = os.environ.get("QGIS_PREFIX_PATH") or str(qgis_module_path.parents[4])

    QgsApplication.setPrefixPath(prefix_path, True)
    app = QgsApplication([], False)
    app.initQgis()

    provider = None
    try:
        Processing.initialize()
        registry = QgsApplication.processingRegistry()
        provider = registry.providerById("regengis_toolbox")
        if provider is None:
            provider = ModelToolboxProvider()
            registry.addProvider(provider)

        feedback = QgsProcessingFeedback()
        params = build_parameter_map(scenario)
        result = processing.run(scenario["algorithm_id"], params, feedback=feedback)
        capture_path = maybe_write_result_capture(scenario, result)
        return {
            "exit_code": 0,
            "stdout": json.dumps(jsonable(result), indent=2),
            "stderr": "",
            "result_capture_path": capture_path,
        }
    finally:
        if provider is not None:
            try:
                QgsApplication.processingRegistry().removeProvider(provider)
            except Exception:
                pass
        app.exitQgis()


def validate_with_script(validate_script: Path, scenario_path: Path) -> dict[str, Any]:
    completed = run_subprocess(python_command(validate_script, "--scenario", str(scenario_path)))
    parsed: dict[str, Any]
    try:
        parsed = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        parsed = {
            "status": "FAIL",
            "errors": ["Validator returned non-JSON output"],
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    parsed["validator_exit_code"] = completed.returncode
    return parsed


def run_scenario_in_subprocess(scenario_path: Path, runner: str, validate_script: Path) -> dict[str, Any]:
    completed = run_subprocess(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--scenario",
            str(scenario_path),
            "--runner",
            runner,
            "--validate-script",
            str(validate_script),
        ]
    )
    base_report = {
        "scenario_id": scenario_path.stem,
        "scenario_path": str(scenario_path),
        "algorithm_id": None,
        "requires_grass": None,
        "gui_only": None,
        "runner": runner,
        "command": completed.args,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        return {**base_report, "status": "RUN_FAIL"}

    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {**base_report, "status": "RUN_FAIL"}

    results = report.get("results")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        return {**base_report, "status": "RUN_FAIL"}
    return results[0]


def run_one(
    scenario_path: Path,
    qgis_process_bin: str | None,
    validate_script: Path,
    runner: str,
    dry_run: bool,
    include_gui: bool,
) -> dict[str, Any]:
    scenario = load_yaml(scenario_path)
    contract_path = scenario_contract_path(scenario_path, scenario)
    _ = load_yaml(contract_path)

    report: dict[str, Any] = {
        "scenario_id": scenario.get("scenario_id"),
        "scenario_path": str(scenario_path),
        "contract_path": str(contract_path),
        "algorithm_id": scenario.get("algorithm_id"),
        "requires_grass": scenario_requires_grass(scenario),
        "gui_only": scenario_is_gui_only(scenario),
        "runner": runner,
    }

    if report["gui_only"] and not include_gui:
        report["status"] = "SKIPPED"
        report["reason"] = "GUI-only scenario; rerun with --include-gui to allow it"
        return report

    if runner == "qgis_process":
        command_bin = qgis_process_bin or "qgis_process"
        command = qgis_process_command(command_bin, scenario)
    else:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--scenario",
            str(scenario_path),
            "--runner",
            runner,
        ]
    report["command"] = command

    if dry_run:
        report["status"] = "DRY_RUN"
        if runner == "qgis_process" and not qgis_process_bin:
            report["reason"] = "qgis_process not found locally; command shown as placeholder"
        return report

    if runner == "qgis_process" and not qgis_process_bin:
        report["status"] = "BLOCKED"
        report["reason"] = "qgis_process not found"
        return report

    if runner == "qgis_process":
        completed = run_subprocess(command)
        report["exit_code"] = completed.returncode
        report["stdout"] = completed.stdout
        report["stderr"] = completed.stderr
    else:
        try:
            direct = run_pyqgis_direct(scenario)
            report.update(direct)
        except Exception as exc:
            report["exit_code"] = 1
            report["stdout"] = ""
            report["stderr"] = f"{type(exc).__name__}: {exc}"

    if report.get("exit_code") != 0:
        report["status"] = "RUN_FAIL"
        return report

    validation = validate_with_script(validate_script, scenario_path)
    report["validation"] = validation
    report["status"] = "PASS" if validation.get("status") == "PASS" else "VALIDATION_FAIL"
    return report


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        status = str(result.get("status", "UNKNOWN"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run RegenGIS regression scenarios")
    parser.add_argument("--suite", type=Path, default=Path("tests/scenarios/regression_suite.yaml"), help="Suite manifest path")
    parser.add_argument("--scenario", type=Path, action="append", help="Run one or more scenario YAML files instead of the full suite")
    parser.add_argument("--qgis-process", dest="qgis_process", help="Path to qgis_process")
    parser.add_argument("--runner", choices=["auto", "qgis_process", "pyqgis_direct"], default="auto", help="Execution backend")
    parser.add_argument("--validate-script", type=Path, default=SCRIPT_DIR / "validate_outputs.py", help="Validator script path")
    parser.add_argument("--report", type=Path, help="Write JSON report to this path")
    parser.add_argument("--dry-run", action="store_true", help="Resolve commands but do not execute them")
    parser.add_argument("--include-gui", action="store_true", help="Allow GUI-only scenarios to run")
    args = parser.parse_args()

    scenario_paths = [path.resolve() for path in args.scenario] if args.scenario else load_suite_scenarios(args.suite.resolve())
    qgis_process_bin = discover_qgis_process(args.qgis_process)
    runner = discover_runner(args.runner, qgis_process_bin)
    validate_script = args.validate_script.resolve()

    suite_report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "runner": runner,
        "qgis_process": qgis_process_bin,
        "validate_script": str(validate_script),
        "suite": str(args.suite.resolve()) if not args.scenario else None,
        "scenario_count": len(scenario_paths),
        "results": [],
    }

    isolate_pyqgis_runs = runner == "pyqgis_direct" and len(scenario_paths) > 1 and not args.dry_run

    for scenario_path in scenario_paths:
        if isolate_pyqgis_runs:
            suite_report["results"].append(
                run_scenario_in_subprocess(
                    scenario_path=scenario_path,
                    runner=runner,
                    validate_script=validate_script,
                )
            )
            continue

        suite_report["results"].append(
            run_one(
                scenario_path=scenario_path,
                qgis_process_bin=qgis_process_bin,
                validate_script=validate_script,
                runner=runner,
                dry_run=args.dry_run,
                include_gui=args.include_gui,
            )
        )

    suite_report["summary"] = summarize(suite_report["results"])

    output = json.dumps(suite_report, indent=2)
    print(output)
    if args.report:
        ensure_parent(args.report.resolve())
        args.report.resolve().write_text(output + "\n", encoding="utf-8")

    bad_statuses = {"RUN_FAIL", "VALIDATION_FAIL"}
    if any(result.get("status") in bad_statuses for result in suite_report["results"]):
        return 1
    if any(result.get("status") == "BLOCKED" for result in suite_report["results"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
