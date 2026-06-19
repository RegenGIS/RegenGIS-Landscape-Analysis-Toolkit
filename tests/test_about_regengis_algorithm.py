from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PLUGIN_ROOT / "algorithms" / "about_regengis.py"


class _DummyProcessingAlgorithm:
    def addOutput(self, _output):
        return None


class _DummyProcessingOutputBoolean:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class _DummyFeedback:
    def __init__(self):
        self.messages = []

    def pushInfo(self, message):
        self.messages.append(message)


class AboutRegenGisAlgorithmTests(unittest.TestCase):
    def _load_module(self):
        fake_qgis = types.ModuleType("qgis")
        fake_core = types.ModuleType("qgis.core")
        setattr(fake_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_core, "QgsProcessingOutputBoolean", _DummyProcessingOutputBoolean)
        setattr(fake_qgis, "core", fake_core)

        old_qgis = sys.modules.get("qgis")
        old_qgis_core = sys.modules.get("qgis.core")
        sys.modules["qgis"] = fake_qgis
        sys.modules["qgis.core"] = fake_core
        try:
            spec = importlib.util.spec_from_file_location("about_regengis_test_module", MODULE_PATH)
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

    def test_process_algorithm_opens_dialog_and_returns_success(self):
        module = self._load_module()
        algorithm = module.AboutRegenGis()
        feedback = _DummyFeedback()

        with mock.patch.object(module, "_show_community_dialog") as show_dialog:
            result = algorithm.processAlgorithm(parameters={}, context=object(), feedback=feedback)

        show_dialog.assert_called_once_with()
        self.assertEqual(result[module.AboutRegenGis.OPENED], True)
        self.assertTrue(any("community dialog" in message.lower() for message in feedback.messages))

    def test_algorithm_is_exposed_at_provider_root_without_group_folder(self):
        module = self._load_module()
        algorithm = module.AboutRegenGis()

        self.assertEqual(algorithm.group(), "")
        self.assertEqual(algorithm.groupId(), "")


if __name__ == "__main__":
    unittest.main()
