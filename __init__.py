# =============================================================================
# MODULE: __init__.py
# =============================================================================

def classFactory(iface):  # noqa: N802 (QGIS naming convention)
    """QGIS calls this function to instantiate the plugin."""
    from .plugin import ModelToolboxPlugin  # pylint: disable=import-outside-toplevel

    return ModelToolboxPlugin(iface)