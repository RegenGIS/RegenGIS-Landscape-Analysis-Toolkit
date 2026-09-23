# =============================================================================
# MODULE: plugin.py
# =============================================================================

from __future__ import annotations

from typing import Optional

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from qgis.PyQt.QtCore import QTimer
try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication
from qgis.gui import QgisInterface

from .processing_provider import ModelToolboxProvider
from .runtime_env import ensure_proj_runtime_env

LOAD_STATUS_PATH = Path(__file__).resolve().parent / ".qgis-load-status.json"


def _load_status_path() -> Path:
    """Use the writable active QGIS profile, never the read-only plugin mount."""
    settings_dir = getattr(QgsApplication, "qgisSettingsDirPath", None)
    if callable(settings_dir):
        try:
            settings_path = settings_dir()
            if isinstance(settings_path, (str, os.PathLike)) and settings_path:
                return Path(settings_path) / "regengis-load-status.json"
        except Exception:
            pass
    return LOAD_STATUS_PATH


def _write_load_status(**payload) -> None:
    try:
        payload = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            **payload,
        }
        status_path = _load_status_path()
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except Exception:
        # Diagnostics must never block QGIS startup.
        pass

# Defensive workaround for installations where GDAL_DATA exists but PROJ_LIB is
# missing, which can leave child GDAL processes unable to find proj.db.
ensure_proj_runtime_env()


def show_community_dialog(*, parent=None) -> int:
    from .community import show_community_dialog as _show_community_dialog

    return _show_community_dialog(parent=parent)


def reset_community_dialog() -> None:
    from .community import reset_community_dialog as _reset_community_dialog

    _reset_community_dialog()


def community_dialog_dismissed() -> bool:
    from .community import community_dialog_dismissed as _community_dialog_dismissed

    return _community_dialog_dismissed()


def _materialize_empty_provider(plugin, registry, provider_id: str):
    """Refresh an empty registered provider, then use its own loader once."""
    provider = registry.providerById(provider_id)
    if provider is None or provider.algorithms():
        return provider

    refresh_algorithms = getattr(provider, "refreshAlgorithms", None)
    if callable(refresh_algorithms):
        plugin._refresh_attempted = True
        try:
            refresh_algorithms()
        except Exception as exc:
            plugin._refresh_error = {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }

    provider = registry.providerById(provider_id)
    if provider is not None and not provider.algorithms():
        load_algorithms = getattr(provider, "loadAlgorithms", None)
        if callable(load_algorithms):
            plugin._direct_load_attempted = True
            try:
                load_algorithms()
            except Exception as exc:
                plugin._direct_load_error = {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }

    return registry.providerById(provider_id)


class ModelToolboxPlugin:
    """Main QGIS plugin class that registers/unregisters the Processing provider."""

    def __init__(self, iface: QgisInterface) -> None:
        self.iface: QgisInterface = iface
        self._provider: Optional[ModelToolboxProvider] = None
        self._about_action: Optional[QAction] = None
        self._refresh_attempted = False
        self._refresh_error: Optional[dict[str, str]] = None
        self._direct_load_attempted = False
        self._direct_load_error: Optional[dict[str, str]] = None

    def show_community_dialog(self) -> None:
        """Show the community dialog popup. Useful for testing."""
        show_community_dialog(parent=self.iface.mainWindow())

    @staticmethod
    def reset_community_dialog() -> None:
        """Reset the community dialog flag so it shows again on next plugin load."""
        reset_community_dialog()

    def initGui(self) -> None:  # noqa: N802 (QGIS API)
        """Called by QGIS when the plugin is enabled."""
        self._refresh_attempted = False
        self._refresh_error = None
        self._direct_load_attempted = False
        self._direct_load_error = None
        from processing.core.Processing import Processing

        Processing.initialize()

        action = QAction("About RegenGIS", self.iface.mainWindow())
        action.triggered.connect(self.show_community_dialog)
        self.iface.addPluginToMenu("RegenGIS", action)
        self._about_action = action

        self._provider = ModelToolboxProvider()
        QgsApplication.processingRegistry().addProvider(self._provider)

        registry = QgsApplication.processingRegistry()
        # Resolve and materialize the registered provider without replacing it.
        _materialize_empty_provider(self, registry, self._provider.id())
        # Resolve the registry entry again because refreshAlgorithms or the
        # direct provider-owned load may replace/materialize the instance.
        provider = registry.providerById(self._provider.id())
        _write_load_status(
            stage="initGui",
            provider_id=self._provider.id(),
            provider_registered=provider is not None,
            provider_class=type(provider).__name__ if provider is not None else None,
            alg_count=len(provider.algorithms()) if provider is not None else None,
            refresh_attempted=self._refresh_attempted,
            refresh_error=self._refresh_error,
            direct_load_attempted=self._direct_load_attempted,
            direct_load_error=self._direct_load_error,
            discovery=provider.discovery() if provider is not None and callable(getattr(provider, "discovery", None)) else None,
        )

        if not community_dialog_dismissed():
            QTimer.singleShot(0, self.show_community_dialog)

    def unload(self) -> None:
        """Called by QGIS when the plugin is disabled/unloaded."""
        if self._about_action is not None:
            self.iface.removePluginMenu("RegenGIS", self._about_action)
            self._about_action = None
        if self._provider is not None:
            QgsApplication.processingRegistry().removeProvider(self._provider)
            self._provider = None