from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "algorithms" / "0 data preperation" / "recommend_analysis_crs.py"


class _DummyProcessingAlgorithm:
    def addParameter(self, _param):
        return None

    def addOutput(self, _output):
        return None

    def parameterAsRasterLayer(self, parameters, name, context):
        return parameters.get(name)


class _DummyProcessingOutputBoolean:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyProcessingOutputNumber(_DummyProcessingOutputBoolean):
    pass


class _DummyProcessingOutputString(_DummyProcessingOutputBoolean):
    pass


class _DummyProcessingParameterRasterLayer(_DummyProcessingOutputBoolean):
    pass


class _DummyFeedback:
    def __init__(self):
        self.messages = []

    def pushInfo(self, message: str):
        self.messages.append(message)


class _Recommendation:
    def __init__(self):
        self.authid = "EPSG:28992"
        self.description = "Amersfoort / RD New"
        self.proj4 = "+proj=sterea"
        self.strategy = "national_grid"
        self.distortion_ppm = 0.0
        self.is_utm_or_ups = False


class RecommendAnalysisCrsAlgorithmTests(unittest.TestCase):
    def _load_module(self, include_autocrs=True):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        fake_core.QgsProcessingAlgorithm = _DummyProcessingAlgorithm
        fake_core.QgsProcessingOutputBoolean = _DummyProcessingOutputBoolean
        fake_core.QgsProcessingOutputNumber = _DummyProcessingOutputNumber
        fake_core.QgsProcessingOutputString = _DummyProcessingOutputString
        fake_core.QgsProcessingParameterRasterLayer = _DummyProcessingParameterRasterLayer
        fake_qgis.core = fake_core

        old_qgis = sys.modules.get("qgis")
        old_qgis_core = sys.modules.get("qgis.core")
        old_autocrs = sys.modules.get("regengis_processing_plugin.autocrs")
        sys.modules["qgis"] = fake_qgis
        sys.modules["qgis.core"] = fake_core
        if include_autocrs:
            fake_autocrs = types.ModuleType("regengis_processing_plugin.autocrs")
            fake_autocrs.recommend_analysis_crs_for_layer = lambda layer, feedback=None: None
            sys.modules["regengis_processing_plugin.autocrs"] = fake_autocrs
        else:
            sys.modules.pop("regengis_processing_plugin.autocrs", None)
        try:
            spec = importlib.util.spec_from_file_location("recommend_analysis_crs_test_module", MODULE_PATH)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            return module
        finally:
            if old_qgis is not None:
                sys.modules["qgis"] = old_qgis
            else:
                sys.modules.pop("qgis", None)
            if old_qgis_core is not None:
                sys.modules["qgis.core"] = old_qgis_core
            else:
                sys.modules.pop("qgis.core", None)
            if old_autocrs is not None:
                sys.modules["regengis_processing_plugin.autocrs"] = old_autocrs
            else:
                sys.modules.pop("regengis_processing_plugin.autocrs", None)

    def test_module_import_does_not_require_autocrs_package(self):
        module = self._load_module(include_autocrs=False)
        self.assertTrue(hasattr(module, "RecommendAnalysisCrs"))

    def test_algorithm_uses_recommend_analysis_helper(self):
        module = self._load_module()
        algorithm = module.RecommendAnalysisCrs()
        layer = object()
        feedback = _DummyFeedback()
        recommendation = _Recommendation()

        with mock.patch.object(algorithm, "parameterAsRasterLayer", return_value=layer), \
             mock.patch.object(module, "_recommend_analysis_crs_for_layer", return_value=recommendation) as helper_mock:
            result = algorithm.processAlgorithm(
                parameters={module.RecommendAnalysisCrs.INPUT: "dummy"},
                context=object(),
                feedback=feedback,
            )

        helper_mock.assert_called_once_with(layer, feedback=feedback)
        self.assertEqual(result[module.RecommendAnalysisCrs.OUTPUT_CRS], "EPSG:28992")
        self.assertEqual(result[module.RecommendAnalysisCrs.OUTPUT_STRATEGY], "national_grid")
        self.assertTrue(any("EPSG:28992" in message for message in feedback.messages))


if __name__ == "__main__":
    unittest.main()
