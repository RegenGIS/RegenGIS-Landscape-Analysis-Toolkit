# =============================================================================
# MODULE: plugin.py
# =============================================================================

from __future__ import annotations

from typing import Optional

from qgis.core import QgsApplication
from qgis.gui import QgisInterface

from .processing_provider import ModelToolboxProvider


class ModelToolboxPlugin:
    """Main QGIS plugin class that registers/unregisters the Processing provider."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface: QgisInterface = iface
        self._provider: Optional[ModelToolboxProvider] = None

    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        """Called by QGIS when the plugin is enabled."""
        self._provider = ModelToolboxProvider()
        QgsApplication.processingRegistry().addProvider(self._provider)

    def unload(self) -> None:
        """Called by QGIS when the plugin is disabled/unloaded."""
        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None