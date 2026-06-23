"""
Generated from a QGIS-model for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsExpression
import processing


class WaterFlow(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Water_flow', 'Water flow', createByDefault=True, defaultValue=''))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}

        # Raster calculator extract
        alg_params = {
            'CELL_SIZE': None,
            'CRS': None,
            'EXPRESSION': '"A@1"',
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'LAYERS': parameters['digital_terrain_model_dtm'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RasterCalculatorExtract'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Fill NoData
        alg_params = {
            'BAND': 1,
            'DISTANCE': 10,
            'EXTRA': None,
            'INPUT': outputs['RasterCalculatorExtract']['OUTPUT'],
            'ITERATIONS': 0,
            'MASK_LAYER': None,
            'OPTIONS': None,
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['FillNodata'] = processing.run('gdal:fillnodata', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # r.flow
        alg_params = {
            '-3': False,
            '-m': False,
            '-u': False,
            'GRASS_OUTPUT_TYPE_PARAMETER': 0,  # auto
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'GRASS_VECTOR_DSCO': None,
            'GRASS_VECTOR_EXPORT_NOCAT': False,
            'GRASS_VECTOR_LCO': None,
            'aspect': None,
            'barrier': None,
            'bound': None,
            'elevation': outputs['FillNodata']['OUTPUT'],
            'flowlength': '././flow_path_length',
            'flowline': '././flow_line',
            'skip': None,
            'flowaccumulation': QgsProcessing.TEMPORARY_OUTPUT,
            'flowlength': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Rflow'] = processing.run('grass:r.flow', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Raster calculator log10
        alg_params = {
            'CELL_SIZE': None,
            'CRS': None,
            'EXPRESSION': ' log10 ( "A@1")',
            'EXTENT': None,
            'LAYERS': outputs['Rflow']['flowaccumulation'],
            'OUTPUT': parameters['Water_flow']
        }
        outputs['RasterCalculatorLog10'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Water_flow'] = outputs['RasterCalculatorLog10']['OUTPUT']
        return results

    def name(self):
        return 'water_flow'
    def displayName(self):
        return 'Water Flow'
    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">A </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Digital Terrain Model (DTM)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> is a grid-based map in which each cell stores the height of the bare ground surface. It represents the terrain itself, without buildings or vegetation, and shows hills, slopes, valleys, and flat areas.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Water Flow</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> analysis uses a DTM to estimate how water is likely to move across the land surface. It creates a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">water flow map</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> by modelling the direction and accumulation of overland flow based on terrain shape.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">The input is a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">DTM. </span><span style=" font-family:'Helvetica Neue'; color:#000000;">The output is a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">water flow map</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, showing the likely flow paths and areas where water may concentrate</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">This is useful for identifying </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">drainage patterns</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">runoff routes</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">erosion risk</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and places where water may collect or move more strongly across the landscape. It can support work in </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">hydrology</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">landscape design</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">restoration</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">site planning</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">water management</span><span style=" font-family:'Helvetica Neue'; color:#000000;">.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />A water flow map is not a direct measurement of actual water movement in the field. Instead, it is a terrain-based model that shows how water is expected to flow based on the shape of the land.</span> </p></body></html></p>
<br></body></html>"""

    def createInstance(self):
        return WaterFlow()
