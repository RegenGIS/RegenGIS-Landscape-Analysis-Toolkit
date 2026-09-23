from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

import headless_test_harness as harness
import test_headless_integration as integration


class HeadlessHarnessUnitTests(unittest.TestCase):
    def _valid_plugin(self, root: Path) -> Path:
        root.mkdir()
        (root / "__init__.py").write_text("")
        (root / "metadata.txt").write_text("[general]\nname=fixture\n")
        (root / "processing_provider.py").write_text("")
        (root / "algorithms").mkdir()
        return root

    def test_plugin_root_must_exist_and_have_package_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts", Path(temp_dir) / "missing")
            incomplete = Path(temp_dir) / "incomplete"
            incomplete.mkdir()
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts2", incomplete)

    def test_qgis_prefix_path_must_be_an_existing_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin = self._valid_plugin(Path(temp_dir) / "plugin")
            with self.assertRaises(ValueError):
                harness.validate_paths(None, Path(temp_dir) / "artifacts", plugin, Path(temp_dir) / "missing")

    def test_empty_input_root_is_blocked_until_fixture_contract_is_valid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            status, diagnostic = harness.fixture_status(input_root)
            self.assertEqual(status, "blocked")
            self.assertIn("contract", diagnostic.lower())

    def test_fixture_contract_requires_existing_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            (input_root / harness.FIXTURE_CONTRACT_FILENAME).write_text('{"project": "missing.qgz"}')
            status, diagnostic = harness.fixture_status(input_root)
            self.assertEqual(status, "blocked")
            self.assertIn("project", diagnostic.lower())

    def test_solar_contract_declares_all_four_plugin_outputs(self):
        input_root = Path(__file__).resolve().parents[1] / "testdata"
        contract = harness._load_contract(input_root)
        solar = next(case for case in contract["execution_cases"] if case["id"] == "solar_radiation_rdnew")
        self.assertEqual(
            solar["expected"]["output_keys"],
            ["Aspect", "Slope", "Shade_intensity", "Solar_hours"],
        )
        self.assertNotIn("Shade_intensity", solar["expected"].get("optional_output_keys", []))

    def test_provider_import_failure_is_failed_not_blocked(self):
        report = harness.new_report(
            qgis_version="3.44.14", provider_id=harness.PROVIDER_ID,
            algorithm_ids=[], load_issues=[{"error_type": "ImportError", "error_message": "broken"}],
            grass_available=None, fixture_status="blocked", diagnostic="provider import failed",
            provider_health="failed",
        )
        self.assertEqual(report["status"], "failed")
    def test_artifact_root_must_not_be_inside_plugin_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "plugin"
            artifact_root = plugin_root / "artifacts"
            self._valid_plugin(plugin_root)

            with self.assertRaises(ValueError):
                harness.validate_paths(
                    input_root=None,
                    artifact_root=artifact_root,
                    plugin_root=plugin_root,
                )

    def test_validate_paths_creates_external_artifact_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = Path(temp_dir) / "plugin"
            self._valid_plugin(plugin_root)
            input_root = Path(temp_dir) / "fixtures"
            input_root.mkdir()
            artifact_root = Path(temp_dir) / "artifacts"

            paths = harness.validate_paths(input_root, artifact_root, plugin_root)

            self.assertEqual(paths.input_root, input_root)
            self.assertEqual(paths.artifact_root, artifact_root)
            self.assertTrue(artifact_root.is_dir())

    def test_fixture_status_is_blocked_when_input_root_is_absent(self):
        report = harness.new_report(
            qgis_version=None,
            provider_id=harness.PROVIDER_ID,
            algorithm_ids=[],
            load_issues=[],
            grass_available=None,
            fixture_status="blocked",
            diagnostic="Input/test-data root is absent.",
        )

        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["fixture_status"], "blocked")
        self.assertIn("absent", report["diagnostic"])

    def test_load_issues_make_report_failed(self):
        report = harness.new_report(
            qgis_version="3.44.14",
            provider_id=harness.PROVIDER_ID,
            algorithm_ids=["regengis_toolbox:example"],
            load_issues=[{"error_type": "ImportError", "error_message": "broken"}],
            grass_available=False,
            fixture_status="ready",
            diagnostic="provider loaded with issues",
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["algorithm_ids"], ["regengis_toolbox:example"])
        self.assertEqual(report["load_issues"][0]["error_type"], "ImportError")

    def test_temporary_provider_copy_is_removed_after_provider_run_lifecycle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = self._valid_plugin(Path(temp_dir) / "plugin")
            artifact_root = Path(temp_dir) / "artifacts"
            artifact_root.mkdir()

            with harness._temporary_provider_copy(plugin_root) as runtime_root:
                self.assertTrue(runtime_root.is_dir())
                self.assertEqual(runtime_root.name, harness.PLUGIN_PACKAGE_ID)
                self.assertNotEqual(runtime_root.name, plugin_root.name)
                (runtime_root / "run-marker").write_text("provider ran")

            self.assertFalse(runtime_root.exists())
            self.assertTrue(plugin_root.is_dir())
            self.assertTrue(artifact_root.is_dir())

    def test_temporary_provider_copy_is_removed_when_provider_run_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            plugin_root = self._valid_plugin(Path(temp_dir) / "plugin")
            artifact_root = Path(temp_dir) / "artifacts"
            artifact_root.mkdir()

            with self.assertRaisesRegex(RuntimeError, "simulated provider failure"):
                with harness._temporary_provider_copy(plugin_root) as runtime_root:
                    self.assertTrue(runtime_root.is_dir())
                    raise RuntimeError("simulated provider failure")

            self.assertFalse(runtime_root.exists())
            self.assertTrue(plugin_root.is_dir())
            self.assertTrue(artifact_root.is_dir())

    def test_returned_output_path_must_be_contained(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "artifacts"
            root.mkdir()
            self.assertEqual(harness._validate_returned_output(root / "case" / "out.tif", root), root / "case" / "out.tif")
            with self.assertRaises(ValueError):
                harness._validate_returned_output(Path(temp_dir) / "escape.tif", root)

    def test_grass_prerequisites_use_exact_registry_ids(self):
        class Registry:
            def __init__(self, available):
                self.available = set(available)

            def providerById(self, provider_id):
                return object() if provider_id == "grass" else None

            def algorithmById(self, algorithm_id):
                return object() if algorithm_id in self.available else None

        case = {"prerequisites": ["GRASS provider present", "GRASS r.sun.insoltime available"]}
        self.assertEqual(harness._grass_prerequisites(case, Registry({"grass:r.sun.insoltime"})), [])
        # The old prose prerequisite named a non-registered algorithm and must
        # remain rejected rather than being silently treated as satisfied.
        old_case = {"prerequisites": ["GRASS r.sun.insoltime and r.sun.daily available"]}
        self.assertEqual(
            harness._grass_prerequisites(old_case, Registry({"grass:r.sun.insoltime"})),
            ["grass:r.sun.daily"],
        )

    def test_qgis_probe_exits_app_when_initialization_raises(self):
        class FakeApplication:
            exited = False

            def __init__(self, *args):
                pass

            def initQgis(self):
                raise RuntimeError("incomplete QGIS runtime")

            def exitQgis(self):
                type(self).exited = True

        class FakeProcessing:
            @staticmethod
            def initialize():
                raise AssertionError("must not initialize after init failure")

        self.assertFalse(integration._probe_qgis_runtime(FakeApplication, FakeProcessing))
        self.assertTrue(FakeApplication.exited)

    def test_write_report_writes_structured_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = harness.write_report(
                Path(temp_dir),
                {"status": "blocked", "provider_id": harness.PROVIDER_ID},
            )

            self.assertTrue(report_path.is_file())
            self.assertEqual(json.loads(report_path.read_text()), {
                "status": "blocked",
                "provider_id": harness.PROVIDER_ID,
            })

    def test_temporary_imports_override_source_package_and_restore_import_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_parent = root / "source"
            source_package = self._import_fixture_package(source_parent)
            runtime_parent = root / "runtime"
            runtime_package = runtime_parent / "regengis_processing_plugin"
            import shutil
            shutil.copytree(source_package["root"], runtime_package)

            # The mounted source parent is intentionally still live on sys.path.
            original_path = list(sys.path)
            self.assertIn(str(source_parent), original_path)
            original_modules = {
                name: sys.modules[name]
                for name in (
                    "regengis_processing_plugin",
                    "regengis_processing_plugin.plugin",
                    "regengis_processing_plugin.processing_provider",
                )
            }

            with harness._temporary_plugin_imports(runtime_package, source_package["root"]) as imported:
                live_path = [Path(entry).resolve() for entry in sys.path if entry]
                self.assertNotIn(source_package["root"].resolve(), live_path)
                self.assertNotIn(source_parent.resolve(), live_path)
                self.assertIn(runtime_parent.resolve(), live_path)
                self.assertTrue(Path(imported["plugin"].__file__).resolve().is_relative_to(runtime_package.resolve()))
                self.assertTrue(Path(imported["provider"].__file__).resolve().is_relative_to(runtime_package.resolve()))
                # This models the lazy algorithm import that occurs after QGIS
                # has registered the provider: it must resolve from the copy.
                (runtime_package / "lazy_algorithm.py").write_text("ORIGIN = 'runtime-copy'\n")
                lazy = importlib.import_module("regengis_processing_plugin.lazy_algorithm")
                self.assertEqual(lazy.ORIGIN, "runtime-copy")
                self.assertTrue(Path(lazy.__file__).resolve().is_relative_to(runtime_package.resolve()))
                self.assertIsNot(imported["plugin"], original_modules["regengis_processing_plugin.plugin"])
                self.assertIsNot(imported["provider"], original_modules["regengis_processing_plugin.processing_provider"])

            self.assertEqual(sys.path, original_path)
            for name, module in original_modules.items():
                self.assertIs(sys.modules[name], module)
            self.assertNotIn("regengis_processing_plugin.lazy_algorithm", sys.modules)
            sys.path.remove(str(source_parent))

    def test_alias_mount_named_plugin_resolves_fixed_lazy_package_from_temporary_copy(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            alias_mount = root / "plugin"
            alias_mount.mkdir()
            (alias_mount / "__init__.py").write_text("")
            (alias_mount / "metadata.txt").write_text("[general]\nname=fixture\n")
            (alias_mount / "plugin.py").write_text("class QAction: pass\n")
            (alias_mount / "processing_provider.py").write_text("class ModelToolboxProvider: pass\n")
            autocrs = alias_mount / "autocrs"
            autocrs.mkdir()
            (autocrs / "__init__.py").write_text("")
            (autocrs / "prepare.py").write_text("ORIGIN = 'temporary-copy'\n")
            sys.path.insert(0, str(alias_mount.parent))
            try:
                with harness._temporary_provider_copy(alias_mount) as runtime_root:
                    self.assertEqual(runtime_root.name, harness.PLUGIN_PACKAGE_ID)
                    with harness._temporary_plugin_imports(runtime_root, alias_mount) as imported:
                        lazy = importlib.import_module(
                            f"{harness.PLUGIN_PACKAGE_ID}.autocrs.prepare"
                        )
                        self.assertEqual(lazy.ORIGIN, "temporary-copy")
                        self.assertTrue(
                            Path(lazy.__file__).resolve().is_relative_to(runtime_root.resolve())
                        )
                        self.assertTrue(
                            Path(imported["provider"].__file__).resolve().is_relative_to(runtime_root.resolve())
                        )
            finally:
                sys.path.remove(str(alias_mount.parent))

    def test_qgis_native_plugin_registration_resolves_lazy_import_and_restores(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_package = self._import_fixture_package(root / "source")["root"]
            runtime_package = root / "runtime" / "regengis_processing_plugin"
            import shutil
            shutil.copytree(source_package, runtime_package)

            class FakeQgisUtils:
                plugin_paths = [str(root / "source")]
                available_plugins = ["existing"]
                update_calls = 0

                @classmethod
                def updateAvailablePlugins(cls):
                    cls.update_calls += 1
                    cls.available_plugins = [
                        "regengis_processing_plugin"
                        for path in cls.plugin_paths
                        if (Path(path) / "regengis_processing_plugin" / "metadata.txt").is_file()
                    ]

                @classmethod
                def loadPlugin(cls, name):
                    if name not in cls.available_plugins:
                        return False
                    importlib.import_module(name)
                    return True

                @classmethod
                def _import(cls, name, globals=None, locals=None, fromlist=None, level=0):
                    if name.split(".", 1)[0] not in cls.available_plugins:
                        raise ModuleNotFoundError(name)
                    return importlib.import_module(name)

            original_paths = list(FakeQgisUtils.plugin_paths)
            original_available = list(FakeQgisUtils.available_plugins)
            with harness._temporary_plugin_imports(runtime_package, source_package, FakeQgisUtils):
                self.assertIn(str(runtime_package.parent), FakeQgisUtils.plugin_paths)
                self.assertIn("regengis_processing_plugin", FakeQgisUtils.available_plugins)
                (runtime_package / "lazy_algorithm.py").write_text("ORIGIN = 'runtime-copy'\n")
                lazy = FakeQgisUtils._import("regengis_processing_plugin.lazy_algorithm")
                self.assertEqual(lazy.ORIGIN, "runtime-copy")
                self.assertTrue(Path(lazy.__file__).resolve().is_relative_to(runtime_package.resolve()))
            self.assertEqual(FakeQgisUtils.plugin_paths, original_paths)
            self.assertEqual(FakeQgisUtils.available_plugins, original_available)
            self.assertEqual(FakeQgisUtils.update_calls, 2)

    def test_temporary_imports_restore_path_and_modules_after_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_package = self._import_fixture_package(root / "source")["root"]
            runtime_package = root / "runtime" / "regengis_processing_plugin"
            import shutil
            shutil.copytree(source_package, runtime_package)
            original_path = list(sys.path)
            original_modules = {
                name: sys.modules[name]
                for name in sys.modules
                if name == "regengis_processing_plugin" or name.startswith("regengis_processing_plugin.")
            }
            with self.assertRaisesRegex(RuntimeError, "functional failure"):
                with harness._temporary_plugin_imports(runtime_package, source_package):
                    importlib.import_module("regengis_processing_plugin.plugin")
                    raise RuntimeError("functional failure")
            self.assertEqual(sys.path, original_path)
            for name, module in original_modules.items():
                self.assertIs(sys.modules[name], module)
            self.assertNotIn("regengis_processing_plugin.lazy_algorithm", sys.modules)

    def _import_fixture_package(self, parent: Path):
        package = parent / "regengis_processing_plugin"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "metadata.txt").write_text("[general]\nname=fixture\n")
        (package / "plugin.py").write_text("class QAction: pass\n")
        (package / "processing_provider.py").write_text("class ModelToolboxProvider: pass\n")
        sys.path.insert(0, str(parent))
        import importlib
        pkg = importlib.import_module("regengis_processing_plugin")
        plugin = importlib.import_module("regengis_processing_plugin.plugin")
        provider = importlib.import_module("regengis_processing_plugin.processing_provider")
        return {"root": package, "package": pkg, "plugin": plugin, "provider": provider}


    def test_no_data_only_raster_fails_numeric_output_assertion(self):
        class Stats:
            All = 1
        class Provider:
            def bandStatistics(self, *_args):
                return types.SimpleNamespace(elementCount=0, minimumValue=float("nan"), maximumValue=float("nan"))
        layer = types.SimpleNamespace(dataProvider=lambda: Provider(), extent=lambda: object())
        old_core = sys.modules.get("qgis.core")
        core = types.ModuleType("qgis.core")
        core.QgsRasterBandStats = Stats
        sys.modules["qgis.core"] = core
        try:
            passed, evidence = harness._raster_has_valid_numeric_samples(layer)
        finally:
            if old_core is None:
                sys.modules.pop("qgis.core", None)
            else:
                sys.modules["qgis.core"] = old_core
        self.assertFalse(passed)
        self.assertEqual(evidence["valid_count"], 0)


if __name__ == "__main__":
    unittest.main()
