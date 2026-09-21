from __future__ import annotations

import importlib.util
import os
import json
import tempfile
import unittest
from pathlib import Path

import headless_test_harness as harness


_QGIS_AVAILABLE = importlib.util.find_spec("qgis") is not None
_RUN_INTEGRATION = os.environ.get("REGENGIS_RUN_QGIS_INTEGRATION") == "1"


@unittest.skipUnless(
    _QGIS_AVAILABLE and _RUN_INTEGRATION,
    "requires a QGIS Python runtime and REGENGIS_RUN_QGIS_INTEGRATION=1",
)
class HeadlessQgisIntegrationTests(unittest.TestCase):
    def test_provider_harness_reports_exact_healthy_inventory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fixture_root = root / "fixtures"
            fixture_root.mkdir()
            (fixture_root / "project.qgz").write_bytes(b"fixture project marker")
            (fixture_root / harness.FIXTURE_CONTRACT_FILENAME).write_text(
                json.dumps({"project": "project.qgz"})
            )
            artifact_root = root / "artifacts"
            code, report_path = harness.run_harness(
                input_root=fixture_root,
                artifact_root=artifact_root,
                plugin_root=harness.PLUGIN_ROOT,
            )
            self.assertEqual(code, 0)
            report = json.loads(report_path.read_text())
            self.assertEqual(report["status"], "ok")
            self.assertEqual(report["provider_id"], harness.PROVIDER_ID)
            self.assertEqual(report["algorithm_ids"], harness.EXPECTED_ALGORITHM_IDS)
            self.assertEqual(report["load_issues"], [])
            self.assertIsInstance(report["qgis_version"], str)
            self.assertIn("grass_provider_present", report)


if __name__ == "__main__":
    unittest.main()
