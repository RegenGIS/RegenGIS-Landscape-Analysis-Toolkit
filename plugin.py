# =============================================================================
# MODULE: plugin.py
# =============================================================================

from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QAction
from qgis.core import QgsApplication
from qgis.gui import QgisInterface

from .community import community_dialog_dismissed
from .community import reset_community_dialog
from .community import show_community_dialog
from .processing_provider import ModelToolboxProvider
from .runtime_env import ensure_proj_runtime_env

# Defensive workaround for installations where GDAL_DATA exists but PROJ_LIB is
# missing, which can leave child GDAL processes unable to find proj.db.
ensure_proj_runtime_env()


class ModelToolboxPlugin:
    """Main QGIS plugin class that registers/unregisters the Processing provider."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface: QgisInterface = iface
        self._provider: Optional[ModelToolboxProvider] = None
        self._about_action: Optional[QAction] = None

    def show_community_dialog(self) -> None:
        """Show the community dialog popup. Useful for testing."""
        show_community_dialog(parent=self.iface.mainWindow())

    @staticmethod
    def reset_community_dialog() -> None:
        """Reset the community dialog flag so it shows again on next plugin load."""
        reset_community_dialog()

    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        """Called by QGIS when the plugin is enabled."""
        action = QAction("About RegenGIS", self.iface.mainWindow())
        action.triggered.connect(self.show_community_dialog)
        self.iface.addPluginToMenu("RegenGIS", action)
        self._about_action = action

        if not community_dialog_dismissed():
            self.show_community_dialog()

        self._provider = ModelToolboxProvider()
        QgsApplication.processingRegistry().addProvider(self._provider)

    def unload(self) -> None:
        """Called by QGIS when the plugin is disabled/unloaded."""
        if self._about_action is not None:
            self.iface.removePluginMenu("RegenGIS", self._about_action)
            self._about_action = None
        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None