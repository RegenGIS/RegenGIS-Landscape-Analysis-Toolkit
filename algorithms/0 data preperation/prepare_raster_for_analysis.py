"""Prepare a raster in a suitable projected CRS for spatial analysis."""

from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingOutputBoolean
from qgis.core import QgsProcessingOutputString
from qgis.core import QgsProcessingParameterBoolean
from qgis.core import QgsProcessingParameterCrs
from qgis.core import QgsProcessingParameterExtent
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsProcessingParameterRasterLayer

from regengis_processing_plugin.autocrs import prepare_raster_for_analysis


class PrepareRasterForAnalysis(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    AUTO_SELECT_ANALYSIS_CRS = "AUTO_SELECT_ANALYSIS_CRS"
    TARGET_CRS = "TARGET_CRS"
    ANALYSIS_EXTENT = "ANALYSIS_EXTENT"
    OUTPUT = "OUTPUT"
    OUTPUT_SOURCE_CRS = "OUTPUT_SOURCE_CRS"
    OUTPUT_TARGET_CRS = "OUTPUT_TARGET_CRS"
    OUTPUT_WAS_REPROJECTED = "OUTPUT_WAS_REPROJECTED"
    OUTPUT_STRATEGY = "OUTPUT_STRATEGY"
    OUTPUT_DESCRIPTION = "OUTPUT_DESCRIPTION"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT,
                "Input raster to prepare for analysis",
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterBoolean(
                self.AUTO_SELECT_ANALYSIS_CRS,
                "Automatically select a suitable analysis CRS",
                defaultValue=True,
            )
        )
        self.addParameter(
            QgsProcessingParameterCrs(
                self.TARGET_CRS,
                "Optional manual target CRS override",
                optional=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterExtent(
                self.ANALYSIS_EXTENT,
                "Optional working extent for provider-backed rasters (defaults to current map extent when available)",
                optional=True,
                defaultValue=None,
            )
        )
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT,
                "Prepared raster for analysis",
                createByDefault=True,
                defaultValue=None,
            )
        )
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_SOURCE_CRS, "Source CRS"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_TARGET_CRS, "Target CRS"))
        self.addOutput(QgsProcessingOutputBoolean(self.OUTPUT_WAS_REPROJECTED, "Was reprojected"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_STRATEGY, "Selection strategy"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_DESCRIPTION, "Selected CRS description"))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        if layer is None:
            raise ValueError("Input raster layer is required.")

        auto_select = self.parameterAsBoolean(parameters, self.AUTO_SELECT_ANALYSIS_CRS, context)
        target_crs = self.parameterAsCrs(parameters, self.TARGET_CRS, context)
        if target_crs is not None and hasattr(target_crs, "isValid") and not target_crs.isValid():
            target_crs = None

        analysis_extent = self.parameterAsExtent(parameters, self.ANALYSIS_EXTENT, context)
        analysis_extent_crs = self.parameterAsExtentCrs(parameters, self.ANALYSIS_EXTENT, context)
        output = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
        prepared = prepare_raster_for_analysis(
            layer,
            context=context,
            feedback=feedback,
            target_crs=target_crs,
            auto_select=auto_select,
            output=output,
            analysis_extent=analysis_extent,
            analysis_extent_crs=analysis_extent_crs,
        )

        if feedback is not None and hasattr(feedback, "pushInfo"):
            if prepared.was_reprojected:
                feedback.pushInfo(
                    "RegenGIS prepared the raster in a suitable metric analysis CRS: "
                    f"{prepared.target_crs_authid}."
                )
            else:
                feedback.pushInfo(
                    "RegenGIS determined that the input raster already uses the selected analysis CRS."
                )

        return {
            self.OUTPUT: prepared.layer_or_path,
            self.OUTPUT_SOURCE_CRS: prepared.source_crs_authid,
            self.OUTPUT_TARGET_CRS: prepared.target_crs_authid,
            self.OUTPUT_WAS_REPROJECTED: prepared.was_reprojected,
            self.OUTPUT_STRATEGY: prepared.recommendation.strategy,
            self.OUTPUT_DESCRIPTION: prepared.recommendation.description,
        }

    def name(self):
        return "prepare_raster_for_analysis"

    def displayName(self):
        return "Prepare Raster for Analysis"

    def group(self):
        return "Data Preparation"

    def groupId(self):
        return "data_preparation"

    def shortHelpString(self):
        return (
            "Prepare an input raster in a suitable projected CRS for spatial analysis. "
            "By default RegenGIS chooses a metric analysis CRS automatically and reprojects the raster only when needed. "
            "For provider-backed rasters such as WCS, you can optionally limit staging to the current work extent."
        )

    def createInstance(self):
        return PrepareRasterForAnalysis()
