# =============================================================================
# MODULE: processing_provider.py
# =============================================================================

from __future__ import annotations

import importlib.util
import inspect
import logging
import sys
from pathlib import Path

from PyQt5.QtGui import QIcon
from qgis.core import QgsProcessingAlgorithm, QgsProcessingProvider

from . import algorithms as algorithms_pkg

logger = logging.getLogger(__name__)


class ModelToolboxProvider(QgsProcessingProvider):
    """Processing provider that exposes the packaged algorithms."""

    def id(self) -> str:
        return "regengis_toolbox"

    def name(self) -> str:
        return "Landscape Analysis Toolkit - RegenGIS.com"

    def longName(self) -> str:
        return "Landscape Analysis Toolkit - RegenGIS.com"

    def icon(self) -> QIcon:
        """Return the provider icon from icon.png if available."""
        icon_path = Path(__file__).parent / "icon.png"
        if icon_path.exists():
            return QIcon(str(icon_path))
        return super().icon()

    def loadAlgorithms(self) -> None:
        """Register algorithms shipped with this plugin.

        Recursively discovers QgsProcessingAlgorithm subclasses from Python files
        under the algorithms folder, using folder names as group names.
        """
        algorithms_dir = Path(algorithms_pkg.__file__).resolve().parent
        for module_path in sorted(self._iter_algorithm_files(algorithms_dir)):
            group_prefix = self._group_prefix_for_path(algorithms_dir, module_path)
            self._load_algorithm_from_path(module_path, group_prefix)

    def _iter_algorithm_files(self, algorithms_dir: Path):
        """Yield candidate algorithm files from disk."""
        for path in algorithms_dir.rglob("*.py"):
            if path.name == "__init__.py":
                continue
            if "__pycache__" in path.parts:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            yield path

    def _group_prefix_for_path(self, algorithms_dir: Path, module_path: Path) -> str:
        """Return the display group derived from the module's relative folder path."""
        relative_parent = module_path.relative_to(algorithms_dir).parent
        if str(relative_parent) == ".":
            return ""

        return "/".join(part.replace("_", " ").title() for part in relative_parent.parts)

    def _load_algorithm_from_path(self, module_path: Path, group_prefix: str = "") -> None:
        """Load and register algorithms from a single Python file."""
        relative_module = module_path.relative_to(Path(__file__).resolve().parent)
        module_name = ".".join((__package__,) + relative_module.with_suffix("").parts)

        try:
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not create import spec for '{module_path}'.")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(module_name, None)
                raise
        except Exception as e:
            logger.warning(f"Failed to import algorithm module '{module_path}': {e}")
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            try:
                if issubclass(obj, QgsProcessingAlgorithm) and obj is not QgsProcessingAlgorithm:
                    # Instantiate the algorithm
                    alg = obj()
                    # Override the group if we have a folder-based group name
                    if group_prefix:
                        alg.group = lambda: group_prefix
                        alg.groupId = lambda: group_prefix.lower().replace(" ", "_").replace("/", "_")
                    self.addAlgorithm(alg)
                    logger.debug(f"Registered algorithm: {alg.displayName()} (group: {alg.group()})")
            except Exception as e:
                logger.warning(f"Failed to instantiate algorithm '{obj.__name__}': {e}")
                continue
