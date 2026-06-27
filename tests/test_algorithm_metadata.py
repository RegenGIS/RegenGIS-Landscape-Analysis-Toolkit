from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
ALGORITHM_MODULES = [
    (
        "height_contours_test_module",
        PLUGIN_ROOT / "algorithms" / "1 Landscape" / "height_contours.py",
        "HeightContours",
        "Height Contours",
        "Landscape",
        "landscape",
    ),
    (
        "twi_test_module",
        PLUGIN_ROOT / "algorithms" / "2 Hydrology" / "twi.py",
        "TopographicWetnessIndex",
        "Topographic Wetness Index",
        "Hydrology",
        "hydrology",
    ),
    (
        "water_flow_test_module",
        PLUGIN_ROOT / "algorithms" / "2 Hydrology" / "water_flow.py",
        "WaterFlow",
        "Water Flow",
        "Hydrology",
        "hydrology",
    ),
    (
        "solar_radiation_metadata_test_module",
        PLUGIN_ROOT / "algorithms" / "3 microclimates" / "solar_radiation.py",
        "SolarRadiation",
        "Solar Radiation",
        "Microclimates",
        "microclimates",
    ),
]


class _DummyProcessingAlgorithm:
    def addParameter(self, _param):
        return None


class _DummyProcessing:
    TEMPORARY_OUTPUT = "TEMP"
    TypeVectorLine = "vector-line"


class _DummyProcessingMultiStepFeedback:
    def __init__(self, steps, feedback):
        self.steps = steps
        self.feedback = feedback

    def setCurrentStep(self, step):
        self.step = step

    def isCanceled(self):
        return False


class _DummyParameter:
    Date = "date"
    Double = "double"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyExpression:
    def __init__(self, expression):
        self.expression = expression

    def evaluate(self):
        return "MAP_EXTENT"


class AlgorithmMetadataTests(unittest.TestCase):
    def _load_module(self, module_name: str, module_path: Path):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        setattr(fake_core, "QgsProcessing", _DummyProcessing)
        setattr(fake_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_core, "QgsProcessingMultiStepFeedback", _DummyProcessingMultiStepFeedback)
        setattr(fake_core, "QgsProcessingParameterDateTime", _DummyParameter)
        setattr(fake_core, "QgsProcessingParameterNumber", _DummyParameter)
        setattr(fake_core, "QgsProcessingParameterRasterLayer", _DummyParameter)
        setattr(fake_core, "QgsProcessingParameterRasterDestination", _DummyParameter)
        setattr(fake_core, "QgsProcessingParameterVectorDestination", _DummyParameter)
        setattr(fake_core, "QgsExpression", _DummyExpression)
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
            spec = importlib.util.spec_from_file_location(module_name, module_path)
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

    def test_algorithm_metadata_is_english_and_category_specific(self):
        for module_name, module_path, class_name, display_name, group_name, group_id in ALGORITHM_MODULES:
            with self.subTest(module=module_name):
                module = self._load_module(module_name, module_path)
                algorithm = getattr(module, class_name)()
                self.assertEqual(algorithm.displayName(), display_name)
                self.assertEqual(algorithm.group(), group_name)
                self.assertEqual(algorithm.groupId(), group_id)


if __name__ == "__main__":
    unittest.main()
