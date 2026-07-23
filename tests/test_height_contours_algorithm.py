from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "algorithms" / "1 Landscape" / "height_contours.py"


class _DummySink:
    def __init__(self):
        self.features = []

    def addFeatures(self, features):
        self.features.extend(list(features))
        return True


class _DummyContext:
    def getMapLayer(self, dest_id):
        return None


class _DummyProcessingAlgorithm:
    def addParameter(self, _param):
        return None

    def parameterAsRasterLayer(self, parameters, name, context):
        return parameters.get(name)


class _DummyProcessing:
    TEMPORARY_OUTPUT = "TEMP"
    TypeVectorLine = "line"


class _DummyProcessingMultiStepFeedback:
    def __init__(self, steps, feedback):
        self.steps = steps
        self.feedback = feedback
        self.current_step = 0
        self.messages = []

    def setCurrentStep(self, step):
        self.current_step = step

    def isCanceled(self):
        return False

    def pushInfo(self, message):
        self.messages.append(message)
        return None


class _DummyProcessingParameterNumber:
    Double = "double"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyProcessingParameterRasterLayer(_DummyProcessingParameterNumber):
    pass


class _DummyProcessingParameterVectorDestination(_DummyProcessingParameterNumber):
    pass


class _DummyCrs:
    def __init__(self, authid: str):
        self._authid = authid

    def authid(self):
        return self._authid


class _DummyExtent:
    pass


class _DummyRasterLayer:
    def __init__(self, authid: str = "EPSG:28992"):
        self._crs = _DummyCrs(authid)
        self._extent = _DummyExtent()

    def crs(self):
        return self._crs

    def extent(self):
        return self._extent


class _DummyVectorLayer:
    def __init__(self, path, name, provider):
        self.path = path
        self.name = name
        self.provider = provider

    def isValid(self):
        return True

    def fields(self):
        return ["ID", "ELEV"]

    def wkbType(self):
        return "LineString"

    def crs(self):
        return _DummyCrs("EPSG:28992")

    def getFeatures(self):
        yield {"id": 1}
        yield {"id": 2}


class _DummyProject:
    @staticmethod
    def instance():
        return _DummyProject()

    def transformContext(self):
        return object()


class HeightContoursAlgorithmTests(unittest.TestCase):
    def _load_module(self):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        setattr(fake_core, "QgsProcessing", _DummyProcessing)
        setattr(fake_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_core, "QgsProcessingMultiStepFeedback", _DummyProcessingMultiStepFeedback)
        setattr(fake_core, "QgsProcessingParameterNumber", _DummyProcessingParameterNumber)
        setattr(fake_core, "QgsProcessingParameterRasterLayer", _DummyProcessingParameterRasterLayer)
        setattr(fake_core, "QgsProcessingParameterVectorDestination", _DummyProcessingParameterVectorDestination)
        setattr(fake_core, "QgsProject", _DummyProject)
        setattr(fake_core, "QgsVectorLayer", _DummyVectorLayer)
        setattr(fake_qgis, "core", fake_core)

        fake_processing = types.ModuleType("processing")
        setattr(fake_processing, "run", lambda *args, **kwargs: None)

        old_qgis = sys.modules.get("qgis")
        old_qgis_core = sys.modules.get("qgis.core")
        old_processing = sys.modules.get("processing")
        sys.modules["qgis"] = fake_qgis
        sys.modules["qgis.core"] = fake_core
        sys.modules["processing"] = fake_processing
        try:
            spec = importlib.util.spec_from_file_location("height_contours_test_module", MODULE_PATH)
            assert spec is not None
            assert spec.loader is not None
            module = importlib.util.module_from_spec(spec)
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
            if old_processing is not None:
                sys.modules["processing"] = old_processing
            else:
                sys.modules.pop("processing", None)

    def test_process_algorithm_returns_memory_sink_with_map_extent(self):
        module = self._load_module()
        algorithm = module.HeightContours()
        input_layer = _DummyRasterLayer()
        map_extent = _DummyExtent()
        ctx = _DummyContext()
        rastercalc_calls = []
        contour_calls = []

        def _run(algorithm_id, alg_params, **kwargs):
            if algorithm_id == "native:modelerrastercalc":
                rastercalc_calls.append((alg_params, kwargs))
                return {"OUTPUT": "clip.tif"}
            if algorithm_id == "gdal:fillnodata":
                return {"OUTPUT": "fill.tif"}
            if algorithm_id == "gdal:contour":
                contour_calls.append((alg_params, kwargs))
                return {"OUTPUT": "temp_contours.shp"}
            raise AssertionError(f"Unexpected algorithm id: {algorithm_id}")

        with mock.patch.object(module, "_current_map_extent_in_layer_crs", return_value=map_extent), \
             mock.patch.object(module.processing, "run", side_effect=_run):
            result = algorithm.processAlgorithm(
                parameters={
                    "digital_terrain_model_dtm": input_layer,
                    "desired_height_distance_between_contours_m": 1.0,
                    "Height_contours": "height_contours_out.shp",
                },
                context=ctx,
                model_feedback=object(),
            )

        self.assertEqual(rastercalc_calls[0][0]["CRS"].authid(), "EPSG:28992")
        self.assertIs(rastercalc_calls[0][0]["EXTENT"], map_extent)
        self.assertEqual(contour_calls[0][0]["INTERVAL"], 1.0)
        self.assertEqual(contour_calls[0][0]["OUTPUT"], "height_contours_out.shp")
        self.assertEqual(result["Height_contours"], "temp_contours.shp")

    def test_process_algorithm_returns_requested_file_destination_for_qgis_loading(self):
        module = self._load_module()
        algorithm = module.HeightContours()
        input_layer = _DummyRasterLayer()
        ctx = _DummyContext()

        def _run(algorithm_id, alg_params, **kwargs):
            if algorithm_id == "native:modelerrastercalc":
                return {"OUTPUT": "clip.tif"}
            if algorithm_id == "gdal:fillnodata":
                return {"OUTPUT": "fill.tif"}
            if algorithm_id == "gdal:contour":
                return {"OUTPUT": "temp_contours.shp"}
            raise AssertionError(f"Unexpected algorithm id: {algorithm_id}")

        with mock.patch.object(module, "_current_map_extent_in_layer_crs", return_value=_DummyExtent()), \
             mock.patch.object(module.processing, "run", side_effect=_run):
            result = algorithm.processAlgorithm(
                parameters={
                    "digital_terrain_model_dtm": input_layer,
                    "desired_height_distance_between_contours_m": 1.0,
                    "Height_contours": "height_contours_out.gpkg",
                },
                context=ctx,
                model_feedback=object(),
            )

        self.assertEqual(result["Height_contours"], 'temp_contours.shp')


if __name__ == "__main__":
    unittest.main()
