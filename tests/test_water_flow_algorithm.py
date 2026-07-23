from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "algorithms" / "2 Hydrology" / "water_flow.py"


class _DummyProcessingAlgorithm:
    def addParameter(self, _param):
        return None

    def parameterAsRasterLayer(self, parameters, name, context):
        return parameters.get(name)


class _DummyProcessing:
    TEMPORARY_OUTPUT = "TEMP"


class _DummyProcessingMultiStepFeedback:
    def __init__(self, steps, feedback):
        self.steps = steps
        self.feedback = feedback
        self.current_step = 0

    def setCurrentStep(self, step):
        self.current_step = step

    def isCanceled(self):
        return False


class _DummyProcessingParameterRasterLayer:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyProcessingParameterRasterDestination(_DummyProcessingParameterRasterLayer):
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


class WaterFlowAlgorithmTests(unittest.TestCase):
    def _load_module(self):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        setattr(fake_core, "QgsProcessing", _DummyProcessing)
        setattr(fake_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_core, "QgsProcessingMultiStepFeedback", _DummyProcessingMultiStepFeedback)
        setattr(fake_core, "QgsProcessingParameterRasterLayer", _DummyProcessingParameterRasterLayer)
        setattr(fake_core, "QgsProcessingParameterRasterDestination", _DummyProcessingParameterRasterDestination)
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
            spec = importlib.util.spec_from_file_location("water_flow_test_module", MODULE_PATH)
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

    def test_process_algorithm_uses_layer_crs_and_transformed_map_extent(self):
        module = self._load_module()
        algorithm = module.WaterFlow()
        input_layer = _DummyRasterLayer()
        map_extent = _DummyExtent()
        rastercalc_calls = []
        grass_calls = []

        def _run(algorithm_id, alg_params, **kwargs):
            if algorithm_id == "native:modelerrastercalc":
                rastercalc_calls.append(alg_params)
                return {"OUTPUT": "clip.tif" if len(rastercalc_calls) == 1 else "log10.tif"}
            if algorithm_id == "gdal:fillnodata":
                return {"OUTPUT": "fill.tif"}
            if algorithm_id == "grass:r.flow":
                grass_calls.append(alg_params)
                return {"flowaccumulation": "flow_accum.tif", "flowlength": "flow_length.tif"}
            raise AssertionError(f"Unexpected algorithm id: {algorithm_id}")

        with mock.patch.object(module, "_current_map_extent_in_layer_crs", return_value=map_extent), \
             mock.patch.object(module.processing, "run", side_effect=_run):
            result = algorithm.processAlgorithm(
                parameters={
                    "digital_terrain_model_dtm": input_layer,
                    "Water_flow": "water_flow_out.tif",
                },
                context=object(),
                model_feedback=object(),
            )

        self.assertEqual(rastercalc_calls[0]["CRS"].authid(), "EPSG:28992")
        self.assertIs(rastercalc_calls[0]["EXTENT"], map_extent)
        self.assertIs(grass_calls[0]["GRASS_REGION_PARAMETER"], map_extent)
        self.assertEqual(rastercalc_calls[1]["CRS"].authid(), "EPSG:28992")
        self.assertIs(rastercalc_calls[1]["EXTENT"], map_extent)
        self.assertEqual(result["Water_flow"], "log10.tif")


if __name__ == "__main__":
    unittest.main()
