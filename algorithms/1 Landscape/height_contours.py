"""
Generated from a QGIS-model for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterNumber
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterVectorDestination

import processing


def _current_map_extent_in_layer_crs(layer, feedback=None):
    from regengis_processing_plugin.autocrs.prepare import _current_map_extent_in_layer_crs as helper

    return helper(layer, feedback=feedback)


class HeightContours(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterNumber('desired_height_distance_between_contours_m', 'Desired height distance between contours (m)', type=QgsProcessingParameterNumber.Type.Double, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterVectorDestination('Height_contours', 'Height contours', type=QgsProcessing.SourceType.TypeVectorLine, createByDefault=True, defaultValue=''))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}
        input_layer = self.parameterAsRasterLayer(parameters, 'digital_terrain_model_dtm', context)
        if input_layer is None:
            raise ValueError('Input raster layer is required.')

        input_crs = input_layer.crs()
        working_extent = _current_map_extent_in_layer_crs(input_layer, feedback=feedback)
        if working_extent is not None:
            if hasattr(feedback, 'pushInfo'):
                feedback.pushInfo('RegenGIS is clipping the DTM to the current map extent, transformed into the raster CRS.')
        else:
            working_extent = input_layer.extent()
            if hasattr(feedback, 'pushInfo'):
                feedback.pushInfo('Current map extent was unavailable, so RegenGIS is clipping the DTM to the full raster extent.')

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': input_crs,
            'EXPRESSION': '"A@1"',
            'EXTENT': working_extent,
            'LAYERS': parameters['digital_terrain_model_dtm'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RasterCalculator'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback)

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
        outputs['FillNodata'] = processing.run('gdal:fillnodata', alg_params, context=context, feedback=feedback)

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
            'INTERVAL': parameters['desired_height_distance_between_contours_m'],
            'NODATA': None,
            'OFFSET': 0,
            'OUTPUT': parameters['Height_contours']
        }
        outputs['Contour'] = processing.run('gdal:contour', alg_params, context=context, feedback=feedback)
        results['Height_contours'] = outputs['Contour']['OUTPUT']
        return results

    def name(self):
        return 'height_contours'
    def displayName(self):
        return 'Height Contours'
    def group(self):
        return 'Landscape'

    def groupId(self):
        return 'landscape'

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">A </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Digital Terrain Model (DTM)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> is a grid-based map in which each cell stores the height of the bare ground at that location. It represents the terrain itself, without buildings or vegetation, and shows the shape of hills, slopes, ridges, valleys, and flat areas.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Height contours</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> are lines that connect points of equal elevation. They are calculated from a DTM to make the terrain easier to read and interpret on a map. In </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">GDAL</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, the </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Contour</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> tool creates these lines based on the elevation values in the DTM.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />The input includes:  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">1. a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">DTM</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">2. the </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">desired height distance between contours (m)</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, also called the contour interval.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">For example, if the contour interval is </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">1 meter</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, a contour line is created every 1 meter of elevation difference. If it is </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">5 meters</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, the lines are spaced every 5 meters in height.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />Height contours are useful for understanding </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">terrain shape</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">slope</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">elevation differences</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">landform patterns</span><span style=" font-family:'Helvetica Neue'; color:#000000;">. They are commonly used in mapping, landscape design, hydrology, site planning, and restoration work. A smaller contour interval gives more detail; a larger interval gives a simpler, less crowded map.</span> </p></body></html></p>
<br></body></html>"""

    def createInstance(self):
        return HeightContours()
