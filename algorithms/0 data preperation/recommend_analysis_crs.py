"""Recommend a suitable metric analysis CRS for an input raster layer."""

from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingOutputBoolean
from qgis.core import QgsProcessingOutputNumber
from qgis.core import QgsProcessingOutputString
from qgis.core import QgsProcessingParameterRasterLayer


def _recommend_analysis_crs_for_layer(layer, feedback=None):
    from regengis_processing_plugin.autocrs.prepare import recommend_analysis_crs_for_layer

    return recommend_analysis_crs_for_layer(layer, feedback=feedback)


class RecommendAnalysisCrs(QgsProcessingAlgorithm):
    INPUT = "INPUT"
    OUTPUT_CRS = "OUTPUT_CRS"
    OUTPUT_DESCRIPTION = "OUTPUT_DESCRIPTION"
    OUTPUT_PROJ = "OUTPUT_PROJ"
    OUTPUT_STRATEGY = "OUTPUT_STRATEGY"
    OUTPUT_DISTORTION_PPM = "OUTPUT_DISTORTION_PPM"
    OUTPUT_IS_UTM = "OUTPUT_IS_UTM"

    def initAlgorithm(self, config=None):
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUT,
                "Input raster for CRS recommendation",
                defaultValue=None,
            )
        )
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_CRS, "Recommended CRS"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_DESCRIPTION, "CRS description"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_PROJ, "PROJ string"))
        self.addOutput(QgsProcessingOutputString(self.OUTPUT_STRATEGY, "Selection strategy"))
        self.addOutput(QgsProcessingOutputNumber(self.OUTPUT_DISTORTION_PPM, "Linear distortion (ppm)"))
        self.addOutput(QgsProcessingOutputBoolean(self.OUTPUT_IS_UTM, "Is UTM / UPS"))

    def processAlgorithm(self, parameters, context, feedback):
        layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        if layer is None:
            raise ValueError("Input raster layer is required.")

        recommendation = _recommend_analysis_crs_for_layer(layer, feedback=feedback)

        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo(
                "RegenGIS selected a suitable metric analysis CRS automatically: "
                f"{recommendation.authid} ({recommendation.description})."
            )

        return {
            self.OUTPUT_CRS: recommendation.authid,
            self.OUTPUT_DESCRIPTION: recommendation.description,
            self.OUTPUT_PROJ: recommendation.proj4,
            self.OUTPUT_STRATEGY: recommendation.strategy,
            self.OUTPUT_DISTORTION_PPM: recommendation.distortion_ppm,
            self.OUTPUT_IS_UTM: recommendation.is_utm_or_ups,
        }

    def name(self):
        return "recommend_analysis_crs"

    def displayName(self):
        return "Recommend Analysis CRS"

    def group(self):
        return "Data Preparation"

    def groupId(self):
        return "data_preparation"

    def shortHelpString(self):
        return (
            "Recommend a suitable metric analysis CRS for an input raster. "
            "RegenGIS chooses the CRS from the smallest intended working area: explicit analysis extent when available, "
            "otherwise the current map extent for WCS/provider-backed rasters, and only then the full layer extent."
        )

    def createInstance(self):
        return RecommendAnalysisCrs()
