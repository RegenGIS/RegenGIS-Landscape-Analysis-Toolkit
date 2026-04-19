"""
Generated from drainage_water_level.py for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsExpression
import processing


class DrainageBasedOnSingleWaterLevel(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterNumber('water_level', 'Water Level', optional=True, type=QgsProcessingParameterNumber.Double, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Drainage', 'Drainage', createByDefault=True, defaultValue=''))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}

        # Raster layer properties
        alg_params = {
            'BAND': None,
            'INPUT': parameters['digital_terrain_model_dtm']
        }
        outputs['RasterLayerProperties'] = processing.run('native:rasterlayerproperties', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

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

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Create constant raster layer
        alg_params = {
            'CREATE_OPTIONS': None,
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'NUMBER': parameters['water_level'],
            'OUTPUT_TYPE': 5,  # Float32
            'PIXEL_SIZE': outputs['RasterLayerProperties']['PIXEL_WIDTH'],
            'TARGET_CRS': 'ProjectCrs',
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['CreateConstantRasterLayer'] = processing.run('native:createconstantrasterlayer', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': parameters['digital_terrain_model_dtm'],
            'EXPRESSION': '"A@1" - "B@1"',
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'LAYERS': [outputs['RasterCalculator']['OUTPUT'],outputs['CreateConstantRasterLayer']['OUTPUT']],
            'OUTPUT': parameters['Drainage']
        }
        outputs['RasterCalculator'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Drainage'] = outputs['RasterCalculator']['OUTPUT']
        return results

    def name(self):
        return 'drainage_based_on_single_water_level'
    def displayName(self):
        return 'Drainage based on single water level'
    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

    def createInstance(self):
        return DrainageBasedOnSingleWaterLevel()
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
p, li { white-space: pre-wrap; }
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><br /></p></body></html></p>
<br></body></html>"""

    def createInstance(self):
        return DrainageBasedOnSingleWaterLevel()
