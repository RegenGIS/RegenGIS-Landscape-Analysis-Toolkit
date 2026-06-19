from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from regengis_processing_plugin.autocrs.heuristics import Extent
from regengis_processing_plugin.autocrs.selector import (
    CatalogIndexEntry,
    _candidate_pre_rank_key,
    _BoundsProxy,
    _catalog_pre_candidate,
    _catalog_cache_identity,
    _catalog_cache_rebuild_message,
    _extent_matches_bounds,
    _load_catalog_index_cache_status,
    _plugin_root,
    _preferred_national_grid_authid,
    _save_catalog_index_cache,
    _specificity_rank,
)


class AutoCrsSelectorTests(unittest.TestCase):
    def test_extent_match_prefers_contains_over_overlap(self):
        extent = Extent(4.3, 51.8, 5.2, 52.1)
        self.assertEqual(_extent_matches_bounds(extent, _BoundsProxy(3.0, 50.0, 6.0, 53.0)), 0)
        self.assertEqual(_extent_matches_bounds(extent, _BoundsProxy(5.0, 51.0, 7.0, 53.0)), 1)
        self.assertIsNone(_extent_matches_bounds(extent, _BoundsProxy(10.0, 40.0, 12.0, 41.0)))

    def test_specificity_rank_prefers_named_national_grids_over_utm(self):
        self.assertEqual(_specificity_rank("Amersfoort / RD New"), 0)
        self.assertEqual(_specificity_rank("ETRS89 / Generic Metric CRS"), 1)
        self.assertEqual(_specificity_rank("WGS 84 / UTM zone 31N"), 2)

    def test_preferred_national_grid_authid_matches_southern_netherlands_expectation(self):
        extent = Extent(5.0, 51.0, 5.8, 51.4)
        self.assertEqual(_preferred_national_grid_authid(extent), "EPSG:28992")

    def test_catalog_pre_rank_prefers_pure_heuristic_national_grid_choice(self):
        extent = Extent(5.0, 51.0, 5.8, 51.4)
        preferred_authid = _preferred_national_grid_authid(extent)

        rd_entry = CatalogIndexEntry(
            srs_id=28992,
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            deprecated_rank=0,
            area_size=11.859,
            specificity_rank=0,
            is_utm_or_ups=False,
            west=3.2,
            south=50.75,
            east=7.22,
            north=53.7,
        )
        be_entry = CatalogIndexEntry(
            srs_id=3812,
            authid="EPSG:3812",
            description="ETRS89 / Belgian Lambert 2008",
            deprecated_rank=0,
            area_size=7.839,
            specificity_rank=0,
            is_utm_or_ups=False,
            west=2.5,
            south=49.5,
            east=6.4,
            north=51.51,
        )

        rd_candidate = _catalog_pre_candidate(rd_entry, extent, preferred_national_grid_authid=preferred_authid)
        be_candidate = _catalog_pre_candidate(be_entry, extent, preferred_national_grid_authid=preferred_authid)

        self.assertIsNotNone(rd_candidate)
        self.assertIsNotNone(be_candidate)
        self.assertLess(_candidate_pre_rank_key(rd_candidate), _candidate_pre_rank_key(be_candidate))

    def test_catalog_cache_identity_has_expected_keys(self):
        identity = _catalog_cache_identity()
        self.assertIn("version", identity)
        self.assertIn("qgis_version", identity)

    def test_load_catalog_index_cache_status_reports_qgis_version_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)
            cache_dir = fake_root / ".autocrs-cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = cache_dir / "qgis-crs-index-v1-unknown.json"
            cache_file.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "qgis_version": "different-version",
                        "entries": [
                            {
                                "srs_id": 1,
                                "authid": "EPSG:28992",
                                "description": "Amersfoort / RD New",
                                "deprecated_rank": 0,
                                "area_size": 1.0,
                                "specificity_rank": 0,
                                "is_utm_or_ups": False,
                                "west": 3.0,
                                "south": 50.0,
                                "east": 7.0,
                                "north": 54.0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch("regengis_processing_plugin.autocrs.selector._plugin_root", return_value=fake_root):
                entries, status = _load_catalog_index_cache_status()
            self.assertIsNone(entries)
            self.assertEqual(status["reason"], "qgis-version-mismatch")

    def test_catalog_cache_roundtrip(self):
        entry = CatalogIndexEntry(
            srs_id=28992,
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            deprecated_rank=0,
            area_size=10.0,
            specificity_rank=0,
            is_utm_or_ups=False,
            west=3.2,
            south=50.75,
            east=7.22,
            north=53.7,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake_root = Path(tmp_dir)
            with mock.patch("regengis_processing_plugin.autocrs.selector._plugin_root", return_value=fake_root):
                _save_catalog_index_cache([entry])
                entries, status = _load_catalog_index_cache_status()
            self.assertEqual(status["reason"], "loaded")
            self.assertEqual(entries, [entry])

    def test_catalog_cache_rebuild_message_mentions_one_time_rebuild(self):
        message = _catalog_cache_rebuild_message({"reason": "missing"})
        self.assertIn("should only happen once", message)


if __name__ == "__main__":
    unittest.main()
