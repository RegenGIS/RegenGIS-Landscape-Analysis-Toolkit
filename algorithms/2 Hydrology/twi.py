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
from qgis.core import QgsProcessingContext
from qgis.core import QgsProcessingUtils
import processing


def _current_map_extent_in_layer_crs(layer, feedback=None):
    from regengis_processing_plugin.autocrs.prepare import _current_map_extent_in_layer_crs as helper

    return helper(layer, feedback=feedback)


def _set_layer_name_on_completion(context, output_path, layer_name):
    """Set the display name for the declared final output in QGIS 3 and 4."""
    if not output_path or context is None:
        return
    try:
        details = context.layerToLoadOnCompletionDetails(output_path)
    except Exception:
        details = None
    if details is None:
        try:
            details = QgsProcessingContext.LayerDetails(layer_name, None, '')
        except Exception:
            return
    details.name = layer_name
    try:
        context.addLayerToLoadOnCompletion(output_path, details)
    except Exception:
        return


class TopographicWetnessIndex(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer('digital_terrain_model_dtm', 'Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('TopographicWetnessIndexTwi', 'Topographic Wetness Index (TWI)', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(3, model_feedback)
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

        # r.topidx
        # Use an explicit file so the GRASS child cannot return a nominal
        # temporary path which disappears before materialization.
        grass_output = QgsProcessingUtils.generateTempFilename('regengis_twi_grass.tif')
        alg_params = {
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': working_extent,
            'input': outputs['FillNodata']['OUTPUT'],
            'output': grass_output
        }
        outputs['Rtopidx'] = processing.run('grass:r.topidx', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        # Register before the final GDAL child starts. Its default completion
        # label is "Converted"; QGIS uses an existing parent completion entry
        # when loading the declared final destination.
        final_output = self.parameterAsOutputLayer(parameters, 'TopographicWetnessIndexTwi', context)
        _set_layer_name_on_completion(context, final_output, 'TWI')
        results['TopographicWetnessIndexTwi'] = processing.run(
            'gdal:translate',
            {
                'COPY_SUBDATASETS': False,
                'DATA_TYPE': 0,
                'EXTRA': '',
                'INPUT': outputs['Rtopidx']['output'],
                'NODATA': None,
                'OPTIONS': '',
                'OUTPUT': parameters['TopographicWetnessIndexTwi'],
                'TARGET_CRS': input_crs,
            },
            context=context,
            feedback=feedback,
            is_child_algorithm=True,
        )['OUTPUT']
        _set_layer_name_on_completion(context, results['TopographicWetnessIndexTwi'], 'TWI')
        return results

    def name(self):
        return 'topographic_wetness_index'
    def displayName(self):
        return 'Topographic Wetness Index'
    def group(self):
        return 'Hydrology'

    def groupId(self):
        return 'hydrology'

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">A </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Digital Terrain Model (DTM)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> is a grid-based map in which each cell stores the height of the bare ground at that location. Unlike models that may include trees or buildings, a DTM represents the land surface itself. In simple terms, it is a digital 3D picture of the terrain, showing hills, slopes, valleys, and flat areas.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />The </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Topographic Wetness Index (TWI)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> is a map derived from a DTM that helps estimate where water is more likely to collect in the landscape. It is calculated by combining two things:  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">1. how much land drains toward a location, and  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">2. how steep the slope is there.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">Areas with a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">high TWI</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> are places where water is more likely to accumulate and remain wet, such as valley bottoms or depressions. Areas with a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">low TWI</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> are usually drier, such as ridges or steep slopes.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />TWI is useful for identifying </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">wet zones</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">drainage patterns</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">soil moisture differences</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and places that may be suitable or unsuitable for farming, planting, restoration, or water management. It is not a direct measurement of soil water, but a terrain-based indicator of potential wetness.</span> </p></body></html></p>
<h2>Input parameters</h2>
<h3>Digital Terrain Model (DTM)</h3>
<p>A Digital Terrain Model (DTM) is a grid-based map in which each cell stores the height of the bare ground at that location. Unlike models that may include trees or buildings, a DTM represents the land surface itself. In simple terms, it is a digital 3D picture of the terrain, showing hills, slopes, valleys, and flat areas.</p>
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><br /></p></body></html></p><br></body></html>"""

    def createInstance(self):
        return TopographicWetnessIndex()
