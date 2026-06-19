from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from regengis_processing_plugin.runtime_env import (
    ensure_proj_runtime_env,
    proj_lib_candidate_from_gdal_data,
)


class RuntimeEnvTests(unittest.TestCase):
    def test_proj_lib_candidate_replaces_gdal_path_segment(self):
        candidate = proj_lib_candidate_from_gdal_data("/usr/share/qgis/resources/gdal")
        self.assertEqual(candidate, "/usr/share/qgis/resources/proj")

    def test_proj_lib_candidate_returns_none_when_gdal_segment_missing(self):
        self.assertIsNone(proj_lib_candidate_from_gdal_data("/usr/share/qgis/resources"))

    def test_ensure_proj_runtime_env_keeps_existing_proj_lib(self):
        env = {
            "PROJ_LIB": "/custom/proj",
            "GDAL_DATA": "/usr/share/qgis/resources/gdal",
        }
        result = ensure_proj_runtime_env(env)
        self.assertEqual(result, "/custom/proj")
        self.assertEqual(env["PROJ_LIB"], "/custom/proj")

    def test_ensure_proj_runtime_env_infers_proj_lib_from_gdal_data(self):
        env = {"GDAL_DATA": "/usr/share/qgis/resources/gdal"}
        result = ensure_proj_runtime_env(env)
        self.assertEqual(result, "/usr/share/qgis/resources/proj")
        self.assertEqual(env["PROJ_LIB"], "/usr/share/qgis/resources/proj")

    def test_ensure_proj_runtime_env_returns_none_without_safe_inference(self):
        env = {"GDAL_DATA": "/usr/share/qgis/resources"}
        result = ensure_proj_runtime_env(env)
        self.assertIsNone(result)
        self.assertNotIn("PROJ_LIB", env)


if __name__ == "__main__":
    unittest.main()
