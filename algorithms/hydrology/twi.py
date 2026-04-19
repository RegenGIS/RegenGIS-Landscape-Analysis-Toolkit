"""
Generated from twi.py for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterRasterDestination
import processing


class TopographicWetnessIndex(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('TopographicWetnessIndexTwi', 'Topographic Wetness Index (TWI)', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(1, model_feedback)
        results = {}
        outputs = {}

        # r.topidx
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'input': parameters['digital_terrain_model_dtm'],
            'output': parameters['TopographicWetnessIndexTwi']
        }
        outputs['Rtopidx'] = processing.run('grass:r.topidx', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['TopographicWetnessIndexTwi'] = outputs['Rtopidx']['output']
        return results

    def name(self):
        return 'topographic_wetness_index'
    def displayName(self):
        return 'Topographic Wetness Index'
    def createInstance(self):
        return TopographicWetnessIndex()
