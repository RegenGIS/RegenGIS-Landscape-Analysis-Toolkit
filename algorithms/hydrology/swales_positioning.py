"""
Model exported as python.
Name : Swales positioning
With QGIS : 34005
"""

from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorDestination
from qgis.core import QgsExpression
import processing


class SwalesPositioning(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterNumber('desired_height_distance_between_swales_m', 'Desired height distance between swales (m)', type=QgsProcessingParameterNumber.Double, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Swales_contours', 'Swales_contours', type=QgsProcessing.TypeVectorLine, createByDefault=True, defaultValue=''))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
        results = {}
        outputs = {}

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': None,
            'EXPRESSION': '"A@1"',
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'LAYERS': parameters['digital_terrain_model_dtm'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RasterCalculator'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Fill NoData
        alg_params = {
            'BAND': 1,
            'DISTANCE': 10,
            'EXTRA': None,
            'INPUT': outputs['RasterCalculator']['OUTPUT'],
            'ITERATIONS': 0,
            'MASK_LAYER': None,
            'OPTIONS': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FillNodata'] = processing.run('gdal:fillnodata', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Contour
        alg_params = {
            'BAND': 1,
            'CREATE_3D': False,
            'EXTRA': None,
            'FIELD_NAME': 'ELEV',
            'IGNORE_NODATA': False,
            'INPUT': outputs['FillNodata']['OUTPUT'],
            'INTERVAL': parameters['desired_height_distance_between_swales_m'],
            'NODATA': None,
            'OFFSET': 0,
            'OUTPUT': parameters['Swales_contours']
        }
        outputs['Contour'] = processing.run('gdal:contour', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Swales_contours'] = outputs['Contour']['OUTPUT']
        return results

    def name(self):
        return 'swales_positioning'

    def displayName(self):
        return 'Swales positioning'

    def createInstance(self):
        return SwalesPositioning()
