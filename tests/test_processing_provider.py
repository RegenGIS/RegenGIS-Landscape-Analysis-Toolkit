from __future__ import annotations

import importlib
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = PLUGIN_ROOT.parent
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))


class _DummyProcessingAlgorithm:
    def displayName(self):
        return getattr(self, "_display_name", self.__class__.__name__)

    def group(self):
        return getattr(self, "_group_name", "")

    def icon(self):
        return None


class _DummyProcessingProvider:
    def __init__(self):
        self.added_algorithms = []

    def addAlgorithm(self, algorithm):
        self.added_algorithms.append(algorithm)

    def icon(self):
        return None


class _DummyQIcon:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs


class ProcessingProviderDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_pyqt5 = sys.modules.get("PyQt5")
        cls._old_pyqt5_qtgui = sys.modules.get("PyQt5.QtGui")
        cls._old_qgis = sys.modules.get("qgis")
        cls._old_qgis_core = sys.modules.get("qgis.core")

        fake_pyqt5 = types.ModuleType("PyQt5")
        fake_qtgui = types.ModuleType("PyQt5.QtGui")
        setattr(fake_qtgui, "QIcon", _DummyQIcon)
        setattr(fake_pyqt5, "QtGui", fake_qtgui)

        fake_qgis = types.ModuleType("qgis")
        fake_qgis_core = types.ModuleType("qgis.core")
        setattr(fake_qgis_core, "QgsProcessingAlgorithm", _DummyProcessingAlgorithm)
        setattr(fake_qgis_core, "QgsProcessingProvider", _DummyProcessingProvider)
        setattr(fake_qgis, "core", fake_qgis_core)

        sys.modules["PyQt5"] = fake_pyqt5
        sys.modules["PyQt5.QtGui"] = fake_qtgui
        sys.modules["qgis"] = fake_qgis
        sys.modules["qgis.core"] = fake_qgis_core

        cls.provider_module = importlib.import_module("regengis_processing_plugin.processing_provider")
        cls.provider_module = importlib.reload(cls.provider_module)

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("regengis_processing_plugin.processing_provider", None)

        if cls._old_pyqt5 is not None:
            sys.modules["PyQt5"] = cls._old_pyqt5
        else:
            sys.modules.pop("PyQt5", None)

        if cls._old_pyqt5_qtgui is not None:
            sys.modules["PyQt5.QtGui"] = cls._old_pyqt5_qtgui
        else:
            sys.modules.pop("PyQt5.QtGui", None)

        if cls._old_qgis is not None:
            sys.modules["qgis"] = cls._old_qgis
        else:
            sys.modules.pop("qgis", None)

        if cls._old_qgis_core is not None:
            sys.modules["qgis.core"] = cls._old_qgis_core
        else:
            sys.modules.pop("qgis.core", None)

    def setUp(self):
        self.provider = self.provider_module.ModelToolboxProvider()
        self.temp_root = Path(tempfile.mkdtemp(prefix="provider-diag-", dir=PLUGIN_ROOT / "tests"))
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    def _write_module(self, relative_path: str, content: str) -> Path:
        path = self.temp_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_import_failure_records_structured_issue_and_cleans_sys_modules(self):
        module_path = self._write_module(
            "algorithms/broken_import.py",
            'raise RuntimeError("import boom")\n',
        )

        self.provider._load_algorithm_from_path(module_path)

        issues = self.provider.load_issues()
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.stage, "import")
        self.assertEqual(issue.error_type, "RuntimeError")
        self.assertEqual(issue.error_message, "import boom")
        self.assertIn("broken_import", issue.module_name)
        self.assertIn("RuntimeError", issue.traceback_text)
        self.assertEqual(self.provider.added_algorithms, [])
        self.assertNotIn(issue.module_name, sys.modules)

    def test_instantiation_failure_records_class_name(self):
        module_path = self._write_module(
            "algorithms/broken_init.py",
            "from qgis.core import QgsProcessingAlgorithm\n"
            "class BrokenAlgorithm(QgsProcessingAlgorithm):\n"
            "    def __init__(self):\n"
            "        raise ValueError('init boom')\n",
        )

        self.provider._load_algorithm_from_path(module_path)

        issues = self.provider.load_issues()
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.stage, "instantiate")
        self.assertEqual(issue.class_name, "BrokenAlgorithm")
        self.assertEqual(issue.error_type, "ValueError")
        self.assertEqual(issue.error_message, "init boom")
        self.assertEqual(self.provider.added_algorithms, [])

    def test_load_issues_returns_copy(self):
        self.provider._load_issues.append(
            self.provider_module.AlgorithmLoadIssue(
                stage="import",
                module_path="x.py",
                module_name="x",
                class_name=None,
                error_type="RuntimeError",
                error_message="boom",
                traceback_text="trace",
            )
        )

        issues = self.provider.load_issues()
        issues.append("mutated")
        self.assertEqual(len(self.provider.load_issues()), 1)

    def test_loaded_algorithms_receive_shared_plugin_icon(self):
        module_path = self._write_module(
            "algorithms/with_icon.py",
            "from qgis.core import QgsProcessingAlgorithm\n"
            "class IconAlgorithm(QgsProcessingAlgorithm):\n"
            "    pass\n",
        )

        with mock.patch.object(self.provider_module, "PLUGIN_ICON_PATH", PLUGIN_ROOT / "icon.png"):
            self.provider._load_algorithm_from_path(module_path)

        self.assertEqual(len(self.provider.added_algorithms), 1)
        algorithm = self.provider.added_algorithms[0]
        icon = algorithm.icon()
        self.assertIsInstance(icon, _DummyQIcon)
        self.assertEqual(icon.args, (str(PLUGIN_ROOT / "icon.png"),))


if __name__ == "__main__":
    unittest.main()
