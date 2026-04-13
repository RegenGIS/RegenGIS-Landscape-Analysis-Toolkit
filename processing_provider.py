# =============================================================================
# MODULE: processing_provider.py
# =============================================================================

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from pathlib import Path
from typing import Optional

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
        
        Recursively discovers QgsProcessingAlgorithm subclasses in the algorithms
        package and subfolders, using folder names as group names.
        """
        package = algorithms_pkg
        self._load_algorithms_from_package(package, group_prefix="")

    def _load_algorithms_from_package(self, package, group_prefix: str = "") -> None:
        """Recursively load algorithms from package and subfolders."""
        # Load algorithms directly in this package
        for finder, name, ispkg in pkgutil.iter_modules(package.__path__):
            if ispkg:
                # Skip subpackages here; they'll be handled separately
                continue

            module_name = f"{package.__name__}.{name}"
            self._load_algorithm_from_module(module_name, group_prefix)

        # Recursively load from subpackages (subfolders)
        for finder, name, ispkg in pkgutil.iter_modules(package.__path__):
            if not ispkg:
                continue

            subpackage_name = f"{package.__name__}.{name}"
            try:
                subpackage = importlib.import_module(subpackage_name)
                # Use folder name as group prefix
                new_group = name.replace("_", " ").title()
                if group_prefix:
                    new_group = f"{group_prefix}/{new_group}"
                self._load_algorithms_from_package(subpackage, new_group)
            except Exception as e:
                logger.warning(f"Failed to import subpackage '{subpackage_name}': {e}")
                continue

    def _load_algorithm_from_module(self, module_name: str, group_prefix: str = "") -> None:
        """Load and register algorithms from a single module."""
        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"Failed to import algorithm module '{module_name}': {e}")
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
