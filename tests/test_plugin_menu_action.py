from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PARENT = PLUGIN_ROOT.parent
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))


class _DummySignal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self):
        for callback in list(self._callbacks):
            callback()


class _DummyAction:
    def __init__(self, text, parent=None):
        self.text = text
        self.parent = parent
        self.triggered = _DummySignal()


class _DummyRegistry:
    def __init__(self):
        self.added = []
        self.removed = []

    def addProvider(self, provider):
        self.added.append(provider)

    def removeProvider(self, provider):
        self.removed.append(provider)


class _DummyQgsApplication:
    registry = _DummyRegistry()

    @staticmethod
    def processingRegistry():
        return _DummyQgsApplication.registry


class _DummyIface:
    def __init__(self):
        self.menu_additions = []
        self.menu_removals = []
        self.main_window = object()

    def mainWindow(self):
        return self.main_window

    def addPluginToMenu(self, menu_name, action):
        self.menu_additions.append((menu_name, action))

    def removePluginMenu(self, menu_name, action):
        self.menu_removals.append((menu_name, action))


class _DummyProvider:
    pass


class PluginMenuActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_modules = {name: sys.modules.get(name) for name in [
            "PyQt5",
            "PyQt5.QtWidgets",
            "qgis",
            "qgis.core",
            "qgis.gui",
            "regengis_processing_plugin.plugin",
            "regengis_processing_plugin.processing_provider",
            "regengis_processing_plugin.community",
            "regengis_processing_plugin.runtime_env",
        ]}

        fake_pyqt5 = types.ModuleType("PyQt5")
        fake_qtwidgets = types.ModuleType("PyQt5.QtWidgets")
        setattr(fake_qtwidgets, "QAction", _DummyAction)
        setattr(fake_pyqt5, "QtWidgets", fake_qtwidgets)

        fake_qgis = types.ModuleType("qgis")
        fake_qgis_core = types.ModuleType("qgis.core")
        fake_qgis_gui = types.ModuleType("qgis.gui")
        setattr(fake_qgis_core, "QgsApplication", _DummyQgsApplication)
        setattr(fake_qgis_gui, "QgisInterface", _DummyIface)
        setattr(fake_qgis, "core", fake_qgis_core)
        setattr(fake_qgis, "gui", fake_qgis_gui)

        fake_provider_module = types.ModuleType("regengis_processing_plugin.processing_provider")
        setattr(fake_provider_module, "ModelToolboxProvider", _DummyProvider)

        fake_community_module = types.ModuleType("regengis_processing_plugin.community")
        setattr(fake_community_module, "community_dialog_dismissed", lambda: False)
        setattr(fake_community_module, "reset_community_dialog", lambda: None)
        setattr(fake_community_module, "show_community_dialog", lambda parent=None: None)

        fake_runtime_env_module = types.ModuleType("regengis_processing_plugin.runtime_env")
        setattr(fake_runtime_env_module, "ensure_proj_runtime_env", lambda: None)

        sys.modules["PyQt5"] = fake_pyqt5
        sys.modules["PyQt5.QtWidgets"] = fake_qtwidgets
        sys.modules["qgis"] = fake_qgis
        sys.modules["qgis.core"] = fake_qgis_core
        sys.modules["qgis.gui"] = fake_qgis_gui
        sys.modules["regengis_processing_plugin.processing_provider"] = fake_provider_module
        sys.modules["regengis_processing_plugin.community"] = fake_community_module
        sys.modules["regengis_processing_plugin.runtime_env"] = fake_runtime_env_module

        cls.plugin_module = importlib.import_module("regengis_processing_plugin.plugin")
        cls.plugin_module = importlib.reload(cls.plugin_module)

    @classmethod
    def tearDownClass(cls):
        for name, old_value in cls._old_modules.items():
            if old_value is not None:
                sys.modules[name] = old_value
            else:
                sys.modules.pop(name, None)

    def setUp(self):
        _DummyQgsApplication.registry = _DummyRegistry()
        self.iface = _DummyIface()
        self.plugin = self.plugin_module.ModelToolboxPlugin(self.iface)

    def test_init_gui_adds_about_menu_action_and_provider(self):
        with mock.patch.object(self.plugin_module, "community_dialog_dismissed", return_value=True), \
             mock.patch.object(self.plugin_module, "show_community_dialog") as show_dialog:
            self.plugin.initGui()

        self.assertEqual(len(self.iface.menu_additions), 1)
        menu_name, action = self.iface.menu_additions[0]
        self.assertEqual(menu_name, "RegenGIS")
        self.assertEqual(action.text, "About RegenGIS")
        self.assertIs(self.plugin._about_action, action)
        self.assertEqual(len(_DummyQgsApplication.registry.added), 1)
        show_dialog.assert_not_called()

    def test_about_menu_action_opens_community_dialog(self):
        with mock.patch.object(self.plugin_module, "community_dialog_dismissed", return_value=True), \
             mock.patch.object(self.plugin_module, "show_community_dialog") as show_dialog:
            self.plugin.initGui()
            assert self.plugin._about_action is not None
            self.plugin._about_action.triggered.emit()

        show_dialog.assert_called_once_with(parent=self.iface.mainWindow())

    def test_unload_removes_menu_action_and_provider(self):
        with mock.patch.object(self.plugin_module, "community_dialog_dismissed", return_value=True):
            self.plugin.initGui()

        provider = self.plugin._provider
        action = self.plugin._about_action
        self.plugin.unload()

        self.assertEqual(self.iface.menu_removals, [("RegenGIS", action)])
        self.assertEqual(_DummyQgsApplication.registry.removed, [provider])
        self.assertIsNone(self.plugin._about_action)
        self.assertIsNone(self.plugin._provider)


if __name__ == "__main__":
    unittest.main()
