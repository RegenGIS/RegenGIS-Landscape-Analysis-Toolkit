from __future__ import annotations

from qgis.PyQt.QtCore import QSettings

COMMUNITY_DIALOG_DISMISSED_KEY = "regengis/community_dialog_dismissed"


def show_community_dialog(*, parent=None) -> int:
    """Open the RegenGIS community dialog and persist the dismissed flag."""
    from .community_dialog import CommunityDialog

    dialog = CommunityDialog(parent)
    result = dialog.exec()
    QSettings().setValue(COMMUNITY_DIALOG_DISMISSED_KEY, True)
    return result


def reset_community_dialog() -> None:
    """Reset the stored dismissed flag so the dialog shows again on plugin load."""
    QSettings().remove(COMMUNITY_DIALOG_DISMISSED_KEY)


def community_dialog_dismissed() -> bool:
    """Return whether the community dialog has already been shown/dismissed."""
    return QSettings().value(COMMUNITY_DIALOG_DISMISSED_KEY, False, type=bool)
