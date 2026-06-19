from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "algorithms" / "3 microclimates" / "solar_radiation.py"


class _DummyProcessingAlgorithm:
    def addParameter(self, _param):
        return None

    def parameterAsDateTime(self, parameters, name, context):
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


class _DummyProcessingParameterDateTime:
    Date = "date"

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyProcessingParameterRasterLayer(_DummyProcessingParameterDateTime):
    pass


class _DummyProcessingParameterRasterDestination(_DummyProcessingParameterDateTime):
    pass


class _DummyExpression:
    def __init__(self, expression):
        self.expression = expression

    def evaluate(self):
        return "MAP_EXTENT"


class _DummyQDateTime:
    def __init__(self, value: datetime):
        self._value = value

    def toPyDateTime(self):
        return self._value


class SolarRadiationAlgorithmTests(unittest.TestCase):
    def _load_module(self):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        setattr(fake_core, "QgsProcessing", _DummyProcessing)
        setattr(fake_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_core, "QgsProcessingMultiStepFeedback", _DummyProcessingMultiStepFeedback)
        setattr(fake_core, "QgsProcessingParameterDateTime", _DummyProcessingParameterDateTime)
        setattr(fake_core, "QgsProcessingParameterRasterLayer", _DummyProcessingParameterRasterLayer)
        setattr(fake_core, "QgsProcessingParameterRasterDestination", _DummyProcessingParameterRasterDestination)
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
            spec = importlib.util.spec_from_file_location("solar_radiation_test_module", MODULE_PATH)
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

    def test_day_of_year_uses_calendar_day_number(self):
        module = self._load_module()
        self.assertEqual(module._day_of_year(date(2026, 6, 21)), 172)
        self.assertEqual(module._day_of_year(datetime(2026, 3, 21, 14, 30)), 80)
        self.assertEqual(module._day_of_year(date(2024, 2, 29)), 60)

    def test_day_of_year_accepts_qdatetime_like_values(self):
        module = self._load_module()
        self.assertEqual(module._day_of_year(_DummyQDateTime(datetime(2026, 12, 21, 9, 0))), 355)

    def test_process_algorithm_passes_explicit_day_of_year_to_grass(self):
        module = self._load_module()
        algorithm = module.SolarRadiation()
        grass_calls = []

        def _run(algorithm_id, alg_params, **kwargs):
            if algorithm_id == "native:modelerrastercalc":
                return {"OUTPUT": "clip.tif"}
            if algorithm_id == "gdal:fillnodata":
                return {"OUTPUT": "fill.tif"}
            if algorithm_id == "native:aspect":
                return {"OUTPUT": "aspect.tif"}
            if algorithm_id == "native:slope":
                return {"OUTPUT": "slope.tif"}
            if algorithm_id == "grass:r.sun.insoltime":
                grass_calls.append(alg_params)
                return {"glob_rad": "shade.tif", "insol_time": "hours.tif"}
            raise AssertionError(f"Unexpected algorithm id: {algorithm_id}")

        with mock.patch.object(module.processing, "run", side_effect=_run):
            result = algorithm.processAlgorithm(
                parameters={
                    "date": date(2026, 6, 21),
                    "digital_surface_model_dsm_or_digital_terrain_model_dtm": "dsm.tif",
                    "Shade_intensity": "shade_out.tif",
                    "Solar_hours": "hours_out.tif",
                    "Aspect": "aspect_out.tif",
                    "Slope": "slope_out.tif",
                },
                context=object(),
                model_feedback=object(),
            )

        self.assertEqual(len(grass_calls), 1)
        self.assertEqual(grass_calls[0]["day"], 172)
        self.assertEqual(result["Shade_intensity"], "shade.tif")
        self.assertEqual(result["Solar_hours"], "hours.tif")


if __name__ == "__main__":
    unittest.main()
