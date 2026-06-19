from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

import regengis_processing_plugin.autocrs.prepare as prepare_module
from regengis_processing_plugin.autocrs.prepare import prepare_raster_for_analysis
from regengis_processing_plugin.autocrs.selector import AutoCrsRecommendation


class _DummyCrs:
    def __init__(self, authid: str):
        self._authid = authid

    def authid(self) -> str:
        return self._authid

    def isValid(self) -> bool:
        return True


class _DummyExtent:
    def __init__(self, width: float = 100.0, height: float = 100.0):
        self._width = width
        self._height = height

    def isNull(self):
        return False

    def isEmpty(self):
        return False

    def width(self):
        return self._width

    def height(self):
        return self._height


class _DummyLayer:
    def __init__(self, authid: str, *, provider_type: str = "gdal", source: str = "/tmp/input.tif"):
        self._crs = _DummyCrs(authid)
        self._provider_type = provider_type
        self._source = source
        self._extent = _DummyExtent()

    def crs(self):
        return self._crs

    def providerType(self):
        return self._provider_type

    def source(self):
        return self._source

    def extent(self):
        return self._extent


class _DummyFeedback:
    def __init__(self):
        self.messages = []

    def pushInfo(self, message: str):
        self.messages.append(message)


class AutoCrsPrepareTests(unittest.TestCase):
    def test_no_reprojection_with_output_uses_copy_not_reproject(self):
        layer = _DummyLayer("EPSG:28992")
        feedback = _DummyFeedback()
        recommendation = AutoCrsRecommendation(
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            proj4="proj4",
            epsg=28992,
            strategy="national_grid",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._require_qgis"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._require_processing"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_analysis_crs_for_layer", return_value=recommendation), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._target_crs_from_input", return_value=_DummyCrs("EPSG:28992")), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._pixel_size", return_value=(1.0, 1.0)), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.layer_needs_reprojection", return_value=False), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._copy_raster_output", return_value="/tmp/prepared.tif", create=True) as copy_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._reproject_raster_output", create=True) as reproject_mock:
            prepared = prepare_raster_for_analysis(
                layer,
                context=object(),
                feedback=feedback,
                target_crs=None,
                auto_select=True,
                output="/tmp/requested-output.tif",
            )

        copy_mock.assert_called_once()
        reproject_mock.assert_not_called()
        self.assertEqual(prepared.layer_or_path, "/tmp/prepared.tif")
        self.assertFalse(prepared.was_reprojected)
        self.assertEqual(prepared.target_crs_authid, "EPSG:28992")
        self.assertTrue(any("output copy" in message.lower() for message in feedback.messages))

    def test_no_reprojection_without_output_reuses_input_layer(self):
        layer = _DummyLayer("EPSG:28992")
        recommendation = AutoCrsRecommendation(
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            proj4="proj4",
            epsg=28992,
            strategy="national_grid",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._require_qgis"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._require_processing"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_analysis_crs_for_layer", return_value=recommendation), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._target_crs_from_input", return_value=_DummyCrs("EPSG:28992")), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._pixel_size", return_value=(1.0, 1.0)), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.layer_needs_reprojection", return_value=False), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._copy_raster_output", create=True) as copy_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._reproject_raster_output", create=True) as reproject_mock:
            prepared = prepare_raster_for_analysis(
                layer,
                context=object(),
                feedback=None,
                target_crs=None,
                auto_select=True,
                output=None,
            )

        copy_mock.assert_not_called()
        reproject_mock.assert_not_called()
        self.assertIs(prepared.layer_or_path, layer)
        self.assertFalse(prepared.was_reprojected)

    def test_reprojection_with_output_uses_reproject_path(self):
        layer = _DummyLayer("EPSG:4326")
        feedback = _DummyFeedback()
        recommendation = AutoCrsRecommendation(
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            proj4="proj4",
            epsg=28992,
            strategy="national_grid",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._require_qgis"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._require_processing"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_analysis_crs_for_layer", return_value=recommendation), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._target_crs_from_input", return_value=_DummyCrs("EPSG:28992")), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._pixel_size", return_value=(1.0, 1.0)), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.layer_needs_reprojection", return_value=True), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._copy_raster_output", create=True) as copy_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._reproject_raster_output", return_value="/tmp/reprojected.tif", create=True) as reproject_mock:
            prepared = prepare_raster_for_analysis(
                layer,
                context=object(),
                feedback=feedback,
                target_crs=None,
                auto_select=True,
                output="/tmp/requested-output.tif",
            )

        copy_mock.assert_not_called()
        reproject_mock.assert_called_once()
        self.assertEqual(prepared.layer_or_path, "/tmp/reprojected.tif")
        self.assertTrue(prepared.was_reprojected)

    def test_wcs_reprojection_stages_local_input_before_gdal_and_forwards_extent(self):
        layer = _DummyLayer(
            "EPSG:28992",
            provider_type="wcs",
            source="wcs://cache=AlwaysNetwork&crs=EPSG:28992&identifier=dtm_05m&url=https://service.pdok.nl/example/wcs",
        )
        recommendation = AutoCrsRecommendation(
            authid="EPSG:5643",
            description="ED50 / SPBA LCC",
            proj4="proj4",
            epsg=5643,
            strategy="catalog_epsg",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )
        analysis_extent = _DummyExtent(width=50.0, height=40.0)
        analysis_extent_crs = _DummyCrs("EPSG:28992")

        with mock.patch("regengis_processing_plugin.autocrs.prepare._require_qgis"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._require_processing"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_analysis_crs_for_layer", return_value=recommendation), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._target_crs_from_input", return_value=_DummyCrs("EPSG:5643")), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._pixel_size", return_value=(1.0, 1.0)), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.layer_needs_reprojection", return_value=True), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._materialize_gdal_input", return_value="/tmp/staged-input.tif", create=True) as stage_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._reproject_raster_output", return_value="/tmp/reprojected.tif", create=True) as reproject_mock:
            prepared = prepare_raster_for_analysis(
                layer,
                context=object(),
                feedback=None,
                target_crs=None,
                auto_select=True,
                output="/tmp/requested-output.tif",
                analysis_extent=analysis_extent,
                analysis_extent_crs=analysis_extent_crs,
            )

        stage_mock.assert_called_once_with(
            layer,
            mock.ANY,
            None,
            requested_extent=analysis_extent,
            requested_extent_crs=analysis_extent_crs,
        )
        reproject_mock.assert_called_once()
        self.assertEqual(reproject_mock.call_args.args[0], "/tmp/staged-input.tif")
        self.assertEqual(prepared.layer_or_path, "/tmp/reprojected.tif")

    def test_local_file_reprojection_skips_staging(self):
        layer = _DummyLayer("EPSG:4326", provider_type="gdal", source="/tmp/input.tif")
        recommendation = AutoCrsRecommendation(
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            proj4="proj4",
            epsg=28992,
            strategy="national_grid",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._require_qgis"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._require_processing"), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_analysis_crs_for_layer", return_value=recommendation), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._target_crs_from_input", return_value=_DummyCrs("EPSG:28992")), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._pixel_size", return_value=(1.0, 1.0)), \
             mock.patch("regengis_processing_plugin.autocrs.prepare.layer_needs_reprojection", return_value=True), \
             mock.patch("regengis_processing_plugin.autocrs.prepare._materialize_gdal_input", side_effect=lambda layer, context, feedback, **kwargs: layer, create=True) as stage_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._reproject_raster_output", return_value="/tmp/reprojected.tif", create=True) as reproject_mock:
            prepare_raster_for_analysis(
                layer,
                context=object(),
                feedback=None,
                target_crs=None,
                auto_select=True,
                output="/tmp/requested-output.tif",
            )

        stage_mock.assert_called_once_with(
            layer,
            mock.ANY,
            None,
            requested_extent=None,
            requested_extent_crs=None,
        )
        self.assertIs(reproject_mock.call_args.args[0], layer)

    def test_resolve_materialization_extent_prefers_explicit_extent(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs")
        requested_extent = _DummyExtent(width=25.0, height=30.0)
        transformed_extent = _DummyExtent(width=20.0, height=15.0)

        with mock.patch("regengis_processing_plugin.autocrs.prepare._transform_extent", return_value=transformed_extent) as transform_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._current_map_extent_in_layer_crs") as map_extent_mock:
            result = prepare_module._resolve_materialization_extent(
                layer,
                requested_extent=requested_extent,
                requested_extent_crs=_DummyCrs("EPSG:28992"),
                feedback=None,
            )

        transform_mock.assert_called_once()
        map_extent_mock.assert_not_called()
        self.assertIs(result, transformed_extent)

    def test_resolve_materialization_extent_falls_back_to_map_extent(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs")
        feedback = _DummyFeedback()
        map_extent = _DummyExtent(width=10.0, height=10.0)

        with mock.patch("regengis_processing_plugin.autocrs.prepare._current_map_extent_in_layer_crs", return_value=map_extent) as map_extent_mock:
            result = prepare_module._resolve_materialization_extent(layer, feedback=feedback)

        map_extent_mock.assert_called_once_with(layer, feedback=feedback)
        self.assertIs(result, map_extent)
        self.assertTrue(any("current map extent" in message.lower() for message in feedback.messages))

    def test_materialize_wcs_uses_resolved_extent_for_staging(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs", source="wcs://example")
        feedback = _DummyFeedback()
        limited_extent = _DummyExtent(width=12.0, height=8.0)

        with mock.patch("regengis_processing_plugin.autocrs.prepare._resolve_materialization_extent", return_value=limited_extent) as extent_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._write_layer_to_temp_geotiff", return_value="/tmp/wcs-stage.tif") as write_mock:
            result = prepare_module._materialize_gdal_input(
                layer,
                context=object(),
                feedback=feedback,
                requested_extent=None,
                requested_extent_crs=None,
            )

        extent_mock.assert_called_once_with(
            layer,
            requested_extent=None,
            requested_extent_crs=None,
            feedback=feedback,
        )
        write_mock.assert_called_once_with(layer, mock.ANY, feedback, extent=limited_extent)
        self.assertEqual(result, "/tmp/wcs-stage.tif")
        self.assertTrue(any("working extent" in message.lower() for message in feedback.messages))

    def test_materialize_wcs_falls_back_to_native_rastercalc_when_writer_fails(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs", source="wcs://example")
        feedback = _DummyFeedback()
        limited_extent = _DummyExtent(width=12.0, height=8.0)

        with mock.patch("regengis_processing_plugin.autocrs.prepare._resolve_materialization_extent", return_value=limited_extent), \
             mock.patch(
                 "regengis_processing_plugin.autocrs.prepare._write_layer_to_temp_geotiff",
                 side_effect=RuntimeError("writer error code 3"),
             ) as write_mock, \
             mock.patch(
                 "regengis_processing_plugin.autocrs.prepare._stage_raster_via_native_rastercalc",
                 return_value="/tmp/wcs-rastercalc-stage.tif",
             ) as rastercalc_mock:
            result = prepare_module._materialize_gdal_input(
                layer,
                context=object(),
                feedback=feedback,
                requested_extent=None,
                requested_extent_crs=None,
            )

        write_mock.assert_called_once_with(layer, mock.ANY, feedback, extent=limited_extent)
        rastercalc_mock.assert_called_once_with(layer, mock.ANY, feedback, extent=limited_extent)
        self.assertEqual(result, "/tmp/wcs-rastercalc-stage.tif")
        self.assertTrue(any("retrying through qgis raster calculator" in message.lower() for message in feedback.messages))

    def test_recommend_analysis_crs_for_wcs_prefers_current_map_extent(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs", source="wcs://example")
        feedback = _DummyFeedback()
        map_extent = _DummyExtent(width=12.0, height=8.0)
        map_extent_wgs84 = _DummyExtent(width=1.0, height=1.0)
        recommendation = AutoCrsRecommendation(
            authid="EPSG:32631",
            description="WGS 84 / UTM zone 31N",
            proj4="proj4",
            epsg=32631,
            strategy="utm",
            distortion_ppm=0.0,
            is_utm_or_ups=True,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._current_map_extent_in_layer_crs", return_value=map_extent) as map_extent_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare._transform_extent", return_value=map_extent_wgs84) as transform_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_metric_crs_for_extent", return_value=recommendation) as extent_recommendation_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_metric_crs_for_layer") as layer_recommendation_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare.QgsCoordinateReferenceSystem") as qcrs_mock:
            qcrs_mock.fromEpsgId.return_value = _DummyCrs("EPSG:4326")
            result = prepare_module.recommend_analysis_crs_for_layer(layer, feedback=feedback)

        map_extent_mock.assert_called_once_with(layer, feedback=feedback)
        transform_mock.assert_called_once_with(map_extent, layer.crs(), qcrs_mock.fromEpsgId.return_value)
        extent_recommendation_mock.assert_called_once_with(map_extent_wgs84, feedback=feedback)
        layer_recommendation_mock.assert_not_called()
        self.assertIs(result, recommendation)
        self.assertTrue(any("current map extent" in message.lower() for message in feedback.messages))

    def test_recommend_analysis_crs_for_wcs_falls_back_to_full_layer_extent_when_map_extent_missing(self):
        layer = _DummyLayer("EPSG:28992", provider_type="wcs", source="wcs://example")
        feedback = _DummyFeedback()
        recommendation = AutoCrsRecommendation(
            authid="EPSG:28992",
            description="Amersfoort / RD New",
            proj4="proj4",
            epsg=28992,
            strategy="national_grid",
            distortion_ppm=0.0,
            is_utm_or_ups=False,
        )

        with mock.patch("regengis_processing_plugin.autocrs.prepare._current_map_extent_in_layer_crs", return_value=None) as map_extent_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_metric_crs_for_layer", return_value=recommendation) as layer_recommendation_mock, \
             mock.patch("regengis_processing_plugin.autocrs.prepare.recommend_metric_crs_for_extent") as extent_recommendation_mock:
            result = prepare_module.recommend_analysis_crs_for_layer(layer, feedback=feedback)

        map_extent_mock.assert_called_once_with(layer, feedback=feedback)
        layer_recommendation_mock.assert_called_once_with(layer, feedback=feedback)
        extent_recommendation_mock.assert_not_called()
        self.assertIs(result, recommendation)
        self.assertTrue(any("falling back to the full layer extent" in message.lower() for message in feedback.messages))


if __name__ == "__main__":
    unittest.main()
