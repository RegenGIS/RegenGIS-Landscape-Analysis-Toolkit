"""Opt-in functional integration checks for the real fixture contract."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

import headless_test_harness as harness


_QGIS_AVAILABLE = importlib.util.find_spec("qgis") is not None
_RUN_INTEGRATION = os.environ.get("REGENGIS_RUN_QGIS_INTEGRATION") == "1"
_FIXTURE_ROOT = Path("/jarvis/hermes_coop/qgis/testdata")


def _probe_qgis_runtime(qgs_application_class, processing_class) -> bool:
    """Probe QGIS/Processing and always clean up a created application."""
    app = None
    try:
        app = qgs_application_class([], False)
        app.initQgis()
        processing_class.initialize()
        registry = qgs_application_class.processingRegistry()
        required = ("grass:r.topidx", "grass:r.flow", "grass:r.sun.insoltime")
        return registry.providerById("grass") is not None and all(registry.algorithmById(item) for item in required)
    except Exception:
        return False
    finally:
        if app is not None:
            try:
                app.exitQgis()
            except Exception:
                pass


def _qualified_runtime() -> bool:
    """Return true only when QGIS and every declared GRASS prerequisite exist."""
    if not _QGIS_AVAILABLE or not _RUN_INTEGRATION:
        return False
    try:
        from qgis.core import QgsApplication
        from processing.core.Processing import Processing
        return _probe_qgis_runtime(QgsApplication, Processing)
    except Exception:
        return False


@unittest.skipUnless(
    _qualified_runtime(),
    "requires QGIS, all declared GRASS algorithms, and REGENGIS_RUN_QGIS_INTEGRATION=1",
)
class HeadlessQgisIntegrationTests(unittest.TestCase):
    """Require successful execution rather than accepting a failed report."""

    def test_provider_harness_reports_exact_functional_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "artifacts"
            code, report_path = harness.run_harness(
                input_root=_FIXTURE_ROOT,
                artifact_root=artifact_root,
                plugin_root=harness.PLUGIN_ROOT,
            )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertEqual(report["status"], "ok")
            non_gui = [entry for entry in report["functional_checks"] if entry["id"] != harness.ABOUT_CASE_ID]
            self.assertEqual(len(non_gui), 6)
            self.assertTrue(all(entry["status"] == "passed" for entry in non_gui))
            about = next(entry for entry in report["functional_checks"] if entry["id"] == harness.ABOUT_CASE_ID)
            self.assertEqual(about["status"], "skipped")
            self.assertIn("GUI", about["reason"])
            self.assertEqual(report["algorithm_ids"], harness.EXPECTED_ALGORITHM_IDS)
            self.assertEqual(report["load_issues"], [])
            self.assertIsInstance(report["qgis_version"], str)
            for entry in non_gui:
                self.assertTrue(entry["assertions"])
                for output in entry.get("outputs", {}).values():
                    output_path = Path(output["path"])
                    self.assertTrue(output["contained"])
                    self.assertTrue(output_path.is_file())


if __name__ == "__main__":
    unittest.main()
