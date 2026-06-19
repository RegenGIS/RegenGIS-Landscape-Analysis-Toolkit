from __future__ import annotations

import sys
import unittest
from pathlib import Path

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from regengis_processing_plugin.autocrs.heuristics import Extent, choose_metric_crs, utm_zone_from_longitude


class AutoCrsHeuristicsTests(unittest.TestCase):
    def test_netherlands_prefers_rd_new_over_utm(self):
        extent = Extent(4.2, 51.7, 5.4, 52.2)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.identifier, "EPSG:28992")
        self.assertEqual(choice.strategy, "national_grid")

    def test_southern_netherlands_still_prefers_rd_new_over_belgian_grid(self):
        extent = Extent(5.0, 51.0, 5.8, 51.4)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.identifier, "EPSG:28992")
        self.assertEqual(choice.strategy, "national_grid")

    def test_central_belgium_prefers_belgian_national_grid(self):
        extent = Extent(4.0, 50.7, 4.8, 51.1)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.identifier, "EPSG:3812")
        self.assertEqual(choice.strategy, "national_grid")

    def test_utm_zone_selection_uses_extent_center(self):
        extent = Extent(6.1, 46.0, 11.8, 47.0)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.identifier, "EPSG:32632")
        self.assertEqual(choice.strategy, "utm")

    def test_antimeridian_extent_still_selects_local_utm(self):
        extent = Extent(179.2, -17.8, -179.4, -16.9)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.strategy, "utm")
        self.assertEqual(choice.identifier, "EPSG:32760")

    def test_polar_extent_prefers_ups(self):
        extent = Extent(-30.0, 84.2, 40.0, 86.0)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.strategy, "ups")
        self.assertEqual(choice.identifier, "EPSG:32661")

    def test_large_extent_uses_custom_local_metric_projection(self):
        extent = Extent(-10.0, 35.0, 20.0, 60.0)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.strategy, "custom_local_metric")
        self.assertEqual(choice.identifier, "CUSTOM:LOCAL_AEQD")

    def test_southern_hemisphere_utm_proj_includes_south_flag(self):
        extent = Extent(30.1, -35.5, 31.3, -34.4)
        choice = choose_metric_crs(extent)
        self.assertEqual(choice.strategy, "utm")
        self.assertIn("+south", choice.proj4)

    def test_longitude_zone_wraps_180_to_zone_60(self):
        self.assertEqual(utm_zone_from_longitude(180.0), 60)


if __name__ == "__main__":
    unittest.main()
