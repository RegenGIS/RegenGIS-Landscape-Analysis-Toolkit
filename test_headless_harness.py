from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import headless_test_harness as harness


class HeadlessHarnessUnitTests(unittest.TestCase):
    def _valid_plugin(self, root: Path) -> Path:
        root.mkdir()
        (root / "__init__.py").write_text("")
        (root / "metadata.txt").write_text("[general]\nname=fixture\n")
        (root / "processing_provider.py").write_text("")
        (root / "algorithms").mkdir()
        return root

    def test_plugin_root_must_exist_and_have_package_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts", Path(temp_dir) / "missing")
            incomplete = Path(temp_dir) / "incomplete"
            incomplete.mkdir()
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts2", incomplete)

    def test_qgis_prefix_path_must_be_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = self._valid_plugin(Path(temp_dir) / "plugin")
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts", plugin, Path(temp_dir) / "missing")

    def test_empty_input_root_is_blocked_until_fixture_contract_is_valid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            status, diagnostic = harness.fixture_status(input_root)
            self.assertEqual(status, "blocked")
            self.assertIn("contract", diagnostic.lower())

    def test_fixture_contract_requires_existing_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            (input_root / harness.FIXTURE_CONTRACT_FILENAME).write_text('{"project": "missing.qgz"}')
            status, diagnostic = harness.fixture_status(input_root)
            self.assertEqual(status, "blocked")
            self.assertIn("project", diagnostic.lower())

    def test_provider_import_failure_is_failed_not_blocked(self):
        report = harness.new_report(
            qgis_version="3.44.14", provider_id=harness.PROVIDER_ID,
            algorithm_ids=[], load_issues=[{"error_type": "ImportError", "error_message": "broken"}],
            grass_available=None, fixture_status="blocked", diagnostic="provider import failed",
            provider_health="failed",
        )
        self.assertEqual(report["status"], "failed")
    def test_artifact_root_must_not_be_inside_plugin_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "plugin"
            artifact_root = plugin_root / "artifacts"
            self._valid_plugin(plugin_root)

            with self.assertRaises(ValueError):
                harness.validate_paths(
                    input_root=None,
                    artifact_root=artifact_root,
                    plugin_root=plugin_root,
                )

    def test_validate_paths_creates_external_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "plugin"
            self._valid_plugin(plugin_root)
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            artifact_root = Path(temp_dir) / "artifacts"

            paths = harness.validate_paths(input_root, artifact_root, plugin_root)

            self.assertEqual(paths.input_root, input_root)
            self.assertEqual(paths.artifact_root, artifact_root)
            self.assertTrue(artifact_root.is_dir())

    def test_fixture_status_is_blocked_when_input_root_is_absent(self):
        report = harness.new_report(
            qgis_version=None,
            provider_id=harness.PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[],
            grass_available=None,
            fixture_status="blocked",
            diagnostic="Input/test-data root is absent.",
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["fixture_status"], "blocked")
        self.assertIn("absent", report["diagnostic"])

    def test_load_issues_make_report_failed(self):
        report = harness.new_report(
            qgis_version="3.44.14",
            provider_id=harness.PROVIDER_ID,
            algorithm_ids=["regengis_toolbox:example"],
            load_issues=[{"error_type": "ImportError", "error_message": "broken"}],
            grass_available=False,
            fixture_status="ready",
            diagnostic="provider loaded with issues",
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["algorithm_ids"], ["regengis_toolbox:example"])
        self.assertEqual(report["load_issues"][0]["error_type"], "ImportError")

    def test_temporary_provider_copy_is_removed_after_provider_run_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = self._valid_plugin(Path(temp_dir) / "plugin")
            artifact_root = Path(temp_dir) / "artifacts"
            artifact_root.mkdir()

            with harness._temporary_provider_copy(plugin_root) as runtime_root:
                self.assertTrue(runtime_root.is_dir())
                (runtime_root / "run-marker").write_text("provider ran")

            self.assertFalse(runtime_root.exists())
            self.assertTrue(plugin_root.is_dir())
            self.assertTrue(artifact_root.is_dir())

    def test_temporary_provider_copy_is_removed_when_provider_run_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = self._valid_plugin(Path(temp_dir) / "plugin")
            artifact_root = Path(temp_dir) / "artifacts"
            artifact_root.mkdir()

            with self.assertRaisesRegex(RuntimeError, "simulated provider failure"):
                with harness._temporary_provider_copy(plugin_root) as runtime_root:
                    self.assertTrue(runtime_root.is_dir())
                    raise RuntimeError("simulated provider failure")

            self.assertFalse(runtime_root.exists())
            self.assertTrue(plugin_root.is_dir())
            self.assertTrue(artifact_root.is_dir())

    def test_write_report_writes_structured_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = harness.write_report(
                Path(temp_dir),
                {"status": "blocked", "provider_id": harness.PROVIDER_ID},
            )

            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(report_path.read_text()), {
                "status": "blocked",
                "provider_id": harness.PROVIDER_ID,
            })


if __name__ == "__main__":
    unittest.main()
