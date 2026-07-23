"""Open the RegenGIS community/about dialog from the Processing toolbox."""

from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingOutputBoolean


def _show_community_dialog():
    from regengis_processing_plugin.community import show_community_dialog

    show_community_dialog()


class AboutRegenGis(QgsProcessingAlgorithm):
    OPENED = "OPENED"

    def initAlgorithm(self, config=None):
        self.addOutput(QgsProcessingOutputBoolean(self.OPENED, "Dialog opened"))

    def processAlgorithm(self, parameters, context, feedback):
        _show_community_dialog()
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo("Opened the RegenGIS community dialog.")
        return {self.OPENED: True}

    def name(self):
        return "about_regengis"

    def displayName(self):
        return "About RegenGIS"

    def group(self):
        return ""

    def groupId(self):
        return ""

    def shortHelpString(self):
        return (
            "Open the RegenGIS community dialog to learn about the plugin, "
            "join the community, and stay updated on RegenGIS products and resources."
        )

    def createInstance(self):
        return AboutRegenGis()
