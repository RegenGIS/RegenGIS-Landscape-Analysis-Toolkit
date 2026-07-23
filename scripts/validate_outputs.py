#!/usr/bin/env python3
"""Validate RegenGIS test scenarios and output artifacts.

Phase 1 scope:
- validate scenario/contract YAML shape (`--spec-only`)
- validate metadata result JSON files when present
- validate vector/raster outputs with `ogrinfo` / `gdalinfo` when paths exist

This script is intentionally runner-agnostic: it validates outputs after a scenario
was executed by `qgis_process`, PyQGIS, or another harness.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return data


def expand_vars(value: str | None) -> str | None:
    if value is None:
        return None
    return os.path.expandvars(value)


def load_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_json_command(command: list[str]) -> dict:
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)


def extract_epsg_tokens(text: str) -> set[str]:
    tokens = {f"EPSG:{match}" for match in re.findall(r"EPSG[\"', ]+([0-9]{3,6})", text)}
    tokens.update(
        f"EPSG:{match}"
        for match in re.findall(r'"authority"\s*:\s*"EPSG"\s*,\s*"code"\s*:\s*([0-9]{3,6})', text)
    )
    return tokens


def raster_crs_tokens(info: dict) -> set[str]:
    coordinate_system = info.get("coordinateSystem") or {}
    tokens = extract_epsg_tokens(json.dumps(coordinate_system))
    wkt = coordinate_system.get("wkt") or ""
    data_axis = coordinate_system.get("dataAxisToSRSAxisMapping")
    if isinstance(wkt, str):
        tokens.update(extract_epsg_tokens(wkt))
    if isinstance(data_axis, list):
        tokens.update(extract_epsg_tokens(json.dumps(data_axis)))
    return tokens


def vector_crs_tokens(layer: dict) -> set[str]:
    tokens = extract_epsg_tokens(json.dumps(layer))
    geometry_fields = layer.get("geometryFields") or []
    tokens.update(extract_epsg_tokens(json.dumps(geometry_fields)))
    return tokens


def scenario_contract_path(scenario_path: Path, scenario: dict) -> Path:
    contract_rel = scenario.get("contract")
    if not contract_rel:
        raise ValueError(f"Scenario is missing contract path: {scenario_path}")
    return (scenario_path.parent / contract_rel).resolve()


def validate_contract_schema(contract_path: Path, contract: dict) -> list[str]:
    errors: list[str] = []
    required = ["version", "contract_id", "algorithm_id", "display_name", "kind"]
    for key in required:
        if key not in contract:
            errors.append(f"{contract_path}: missing contract key '{key}'")
    kind = contract.get("kind")
    if kind not in {"metadata", "raster", "vector", "multi_raster", "raster_with_metadata"}:
        errors.append(f"{contract_path}: unsupported contract kind '{kind}'")
    return errors


def validate_scenario_schema(scenario_path: Path, scenario: dict) -> list[str]:
    errors: list[str] = []
    required = ["version", "scenario_id", "algorithm_id", "description", "contract"]
    for key in required:
        if key not in scenario:
            errors.append(f"{scenario_path}: missing scenario key '{key}'")
    return errors


def validate_suite_manifest(suite_path: Path) -> list[str]:
    suite = load_yaml(suite_path)
    errors: list[str] = []
    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        return [f"{suite_path}: suite must contain a non-empty scenarios list"]
    for rel in scenarios:
        candidate = (suite_path.parent / rel).resolve()
        if not candidate.exists():
            errors.append(f"{suite_path}: missing scenario file '{rel}'")
            continue
        scenario = load_yaml(candidate)
        errors.extend(validate_scenario_schema(candidate, scenario))
        contract_path = scenario_contract_path(candidate, scenario)
        if not contract_path.exists():
            errors.append(f"{candidate}: missing contract file '{contract_path}'")
            continue
        contract = load_yaml(contract_path)
        errors.extend(validate_contract_schema(contract_path, contract))
    return errors


def validate_metadata_result(contract: dict, result: dict | None) -> list[str]:
    errors: list[str] = []
    if result is None:
        return ["Missing metadata result JSON"]
    for key, spec in contract.get("required_result_keys", {}).items():
        if spec.get("required", False) and key not in result:
            errors.append(f"Missing result key: {key}")
            continue
        if key not in result:
            continue
        value = result[key]
        expected_type = spec.get("type")
        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"Result key {key} must be a string")
        if expected_type == "string" and spec.get("non_empty") and isinstance(value, str) and not value.strip():
            errors.append(f"Result key {key} must be non-empty")
        if expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"Result key {key} must be numeric")
        if expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"Result key {key} must be boolean")
        if "equals" in spec and value != spec["equals"]:
            errors.append(f"Result key {key} must equal {spec['equals']!r}")
    if contract.get("kind") == "raster_with_metadata":
        source = result.get("OUTPUT_SOURCE_CRS")
        target = result.get("OUTPUT_TARGET_CRS")
        reprojected = result.get("OUTPUT_WAS_REPROJECTED")
        if reprojected is False and source and target and source != target:
            errors.append("OUTPUT_WAS_REPROJECTED=False but source and target CRS differ")
    return errors


def raster_info(path: Path) -> dict:
    return run_json_command(["gdalinfo", "-json", str(path)])


def vector_info(path: Path) -> dict:
    return run_json_command(["ogrinfo", "-json", "-so", "-al", str(path)])


def validate_raster_output(output_name: str, spec: dict, path: Path, expected_crs: str | None) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Missing raster output: {output_name} -> {path}"]
    try:
        info = raster_info(path)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        return [f"Raster output {output_name} is unreadable: {stderr or exc}"]
    size = info.get("size") or []
    if len(size) != 2 or size[0] <= 0 or size[1] <= 0:
        errors.append(f"Raster {output_name} has invalid size")
    bands = info.get("bands") or []
    if len(bands) < int(spec.get("min_band_count", 1)):
        errors.append(f"Raster {output_name} has too few bands")
    actual_tokens = raster_crs_tokens(info)
    if expected_crs and expected_crs not in actual_tokens:
        errors.append(
            f"Raster {output_name} CRS tokens {sorted(actual_tokens)} do not include expected token '{expected_crs}'"
        )
    return errors


def validate_vector_output(output_name: str, spec: dict, path: Path, expected_crs: str | None) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"Missing vector output: {output_name} -> {path}"]
    try:
        info = vector_info(path)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or "").strip()
        return [f"Vector output {output_name} is unreadable: {stderr or exc}"]
    layers = info.get("layers") or []
    if not layers:
        return [f"Vector output {output_name} has no layers"]
    layer = layers[0]
    geometry_fields = layer.get("geometryFields") or []
    geometry_type = layer.get("geometryType")
    if geometry_fields and isinstance(geometry_fields[0], dict):
        geometry_type = geometry_fields[0].get("type") or geometry_type
    allowed = set(spec.get("geometry_type_any_of", []))
    if allowed and geometry_type not in allowed:
        errors.append(f"Vector {output_name} geometry type '{geometry_type}' not in {sorted(allowed)}")
    field_names = {field.get("name") for field in layer.get("fields", [])}
    for field in spec.get("required_fields", []):
        if field not in field_names:
            errors.append(f"Vector {output_name} missing required field '{field}'")
    actual_tokens = vector_crs_tokens(layer)
    if expected_crs and expected_crs not in actual_tokens:
        errors.append(
            f"Vector {output_name} CRS tokens {sorted(actual_tokens)} do not include expected token '{expected_crs}'"
        )
    return errors


def expected_crs_for(contract: dict, scenario: dict, result: dict | None) -> str | None:
    rule = contract.get("crs_rule") or {}
    rule_type = rule.get("type")
    if rule_type == "equals_result_key" and result is not None:
        return result.get(rule.get("result_key"))
    if rule_type == "equals_input":
        inputs = scenario.get("inputs", {})
        input_spec = inputs.get(rule.get("input_parameter"), {})
        return input_spec.get("crs")
    return None


def validate_outputs_for_scenario(scenario_path: Path) -> dict:
    scenario = load_yaml(scenario_path)
    contract_path = scenario_contract_path(scenario_path, scenario)
    contract = load_yaml(contract_path)

    errors = []
    errors.extend(validate_scenario_schema(scenario_path, scenario))
    errors.extend(validate_contract_schema(contract_path, contract))
    if errors:
        return {"scenario": scenario.get("scenario_id"), "status": "FAIL", "errors": errors}

    result_json_path = None
    result = None
    if isinstance(scenario.get("result_capture"), dict):
        result_json_path = expand_vars(scenario["result_capture"].get("path"))
        if result_json_path:
            result = load_json_if_exists(Path(result_json_path))

    errors.extend(validate_metadata_result(contract, result) if contract.get("kind") in {"metadata", "raster_with_metadata"} else [])

    expected_crs = expected_crs_for(contract, scenario, result)
    for output_name, spec in (contract.get("outputs") or {}).items():
        scenario_output = ((scenario.get("outputs") or {}).get(output_name) or {}).get("path")
        if not scenario_output:
            errors.append(f"Scenario missing output path for {output_name}")
            continue
        output_path_text = expand_vars(scenario_output)
        if not output_path_text:
            errors.append(f"Scenario output path for {output_name} resolved to empty value")
            continue
        output_path = Path(output_path_text)
        if not output_path.exists() and spec.get("required", True) is False:
            continue
        kind = spec.get("kind")
        if kind == "raster":
            errors.extend(validate_raster_output(output_name, spec, output_path, expected_crs))
        elif kind == "vector":
            errors.extend(validate_vector_output(output_name, spec, output_path, expected_crs))

    return {
        "scenario": scenario.get("scenario_id"),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "contract": str(contract_path),
        "result_json": result_json_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate RegenGIS scenarios and outputs")
    parser.add_argument("--suite", type=Path, help="Path to regression_suite.yaml")
    parser.add_argument("--scenario", type=Path, help="Path to one scenario YAML")
    parser.add_argument("--spec-only", action="store_true", help="Validate only YAML manifest/schema wiring")
    args = parser.parse_args()

    if not args.suite and not args.scenario:
        parser.error("Provide --suite or --scenario")

    if args.suite:
        errors = validate_suite_manifest(args.suite)
        if args.spec_only:
            print(json.dumps({"suite": str(args.suite), "status": "PASS" if not errors else "FAIL", "errors": errors}, indent=2))
            return 0 if not errors else 1
        suite = load_yaml(args.suite)
        results = []
        for rel in suite.get("scenarios", []):
            results.append(validate_outputs_for_scenario((args.suite.parent / rel).resolve()))
        failed = [r for r in results if r["status"] != "PASS"]
        print(json.dumps({"suite": str(args.suite), "status": "PASS" if not failed else "FAIL", "results": results}, indent=2))
        return 0 if not failed else 1

    if args.spec_only:
        scenario = load_yaml(args.scenario)
        contract = load_yaml(scenario_contract_path(args.scenario, scenario))
        errors = validate_scenario_schema(args.scenario, scenario) + validate_contract_schema(scenario_contract_path(args.scenario, scenario), contract)
        print(json.dumps({"scenario": str(args.scenario), "status": "PASS" if not errors else "FAIL", "errors": errors}, indent=2))
        return 0 if not errors else 1

    result = validate_outputs_for_scenario(args.scenario)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())