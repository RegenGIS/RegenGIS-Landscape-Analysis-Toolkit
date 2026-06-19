# =============================================================================
# MODULE: plugin.py
# =============================================================================

from __future__ import annotations

from typing import Optional

from qgis.core import QgsApplication
from qgis.gui import QgisInterface
from .community_dialog import CommunityDialog
from PyQt5.QtCore import QSettings

from .processing_provider import ModelToolboxProvider

# TEMPORARY WORKAROUND for a misconfiguration in some installations of QGIS
# where the PROJ_LIB path in GDAL is missing or misconfigured.
# This causes GDAL processes to not be able to find the proj.db 
# and generating faulty projections
import os
try:
    os.environ["PROJ_LIB"]
except:
    gdalpath = os.environ["GDAL_DATA"]
    os.environ["PROJ_LIB"]=gdalpath.replace("gdal", "proj")


class ModelToolboxPlugin:
    """Main QGIS plugin class that registers/unregisters the Processing provider."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface: QgisInterface = iface
        self._provider: Optional[ModelToolboxProvider] = None

    @staticmethod
    def show_community_dialog() -> None:
        """Show the community dialog popup. Useful for testing."""
        dialog = CommunityDialog()
        dialog.exec_()
        QSettings().setValue("regengis/community_dialog_dismissed", True)

    @staticmethod
    def reset_community_dialog() -> None:
        """Reset the community dialog flag so it shows again on next plugin load."""
        QSettings().remove("regengis/community_dialog_dismissed")

    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        """Called by QGIS when the plugin is enabled."""
        settings = QSettings()
        if not settings.value("regengis/community_dialog_dismissed", False, type=bool):
            dialog = CommunityDialog()
            dialog.exec_()
            settings.setValue("regengis/community_dialog_dismissed", True)

        self._provider = ModelToolboxProvider()
        QgsApplication.processingRegistry().addProvider(self._provider)

    def unload(self) -> None:
        """Called by QGIS when the plugin is disabled/unloaded."""
        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None