"""
Generated from a QGIS-model for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterDateTime
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterRasterDestination
from qgis.core import QgsExpression
import processing


class SolarRadiation(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterDateTime('date', 'Date', type=QgsProcessingParameterDateTime.Date, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('digital_surface_model_dsm_or_digital_terrain_model_dtm', 'Digital Surface Model (DSM) or Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Shade_intensity', 'Shade_intensity', optional=True, createByDefault=True, defaultValue=''))
        self.addParameter(QgsProcessingParameterRasterDestination('Solar_hours', 'Solar_hours', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Aspect', 'Aspect', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Slope', 'Slope', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(5, model_feedback)
        results = {}
        outputs = {}

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': None,
            'EXPRESSION': '"A@1"',
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'LAYERS': parameters['digital_surface_model_dsm_or_digital_terrain_model_dtm'],
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

        # Aspect
        alg_params = {
            'INPUT': outputs['FillNodata']['OUTPUT'],
            'Z_FACTOR': 1,
            'OUTPUT': parameters['Aspect']
        }
        outputs['Aspect'] = processing.run('native:aspect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Aspect'] = outputs['Aspect']['OUTPUT']

        feedback.setCurrentStep(3)
        if feedback.isCanceled():
            return {}

        # Slope
        alg_params = {
            'INPUT': outputs['FillNodata']['OUTPUT'],
            'Z_FACTOR': 1,
            'OUTPUT': parameters['Slope']
        }
        outputs['Slope'] = processing.run('native:slope', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Slope'] = outputs['Slope']['OUTPUT']

        feedback.setCurrentStep(4)
        if feedback.isCanceled():
            return {}

        # r.sun.insoltime
        alg_params = {
            '-m': False,
            '-p': False,
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': None,
            'albedo': None,
            'albedo_value': None,
            'aspect': outputs['Aspect']['OUTPUT'],
            'aspect_value': None,
            'civil_time': None,
            'coeff_bh': None,
            'coeff_dh': None,
            'day': QgsExpression("day(age(to_string(@date), to_string(year(@date)) + '-01-01'))").evaluate(),
            'declination': None,
            'distance_step': 1,
            'elevation': outputs['FillNodata']['OUTPUT'],
            'horizon_basemap': None,
            'horizon_step': None,
            'lat': None,
            'linke': None,
            'long': None,
            'npartitions': 1,
            'slope': outputs['Slope']['OUTPUT'],
            'slope_value': 0,
            'step': 0.5,
            'glob_rad': parameters['Shade_intensity'],
            'insol_time': parameters['Solar_hours']
        }
        outputs['Rsuninsoltime'] = processing.run('grass:r.sun.insoltime', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Shade_intensity'] = outputs['Rsuninsoltime']['glob_rad']
        results['Solar_hours'] = outputs['Rsuninsoltime']['insol_time']
        return results

    def name(self):
        return 'solar_radiation'
    def displayName(self):
        return 'Solar radiation'
    def group(self):
        return 'Voedselbos'

    def groupId(self):
        return 'Voedselbos'

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

    def createInstance(self):
        return SolarRadiation()
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
</style></head><body style=" font-family:'.AppleSystemUIFont'; font-size:13pt; font-weight:400; font-style:normal;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">A </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Digital Terrain Model (DTM)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> or </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Digital Surface Model (DSM)</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> is a grid-based map in which each cell stores elevation. A </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">DTM</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> represents the bare ground surface, while a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">DSM</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> also includes features on top of the ground, such as trees and buildings. For solar analysis, a DSM is used when shading from existing vegetation and structures should be included; a DTM is used when only the terrain is considered.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Solar Radiation</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> analysis estimates how sunlight is distributed across the landscape for a given </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">reference date</span><span style=" font-family:'Helvetica Neue'; color:#000000;">. This helps show where places are sunnier or more shaded at a specific time of year.</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">The tool uses:  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">1. a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">DTM or DSM</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, depending on whether shading objects should be included, and  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">2. a </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">reference date</span><span style=" font-family:'Helvetica Neue'; color:#000000;">.</span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;"><br />It produces four outputs:  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">- </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Slope</span><span style=" font-family:'Helvetica Neue'; color:#000000;">: how steep the terrain is  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">- </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Aspect</span><span style=" font-family:'Helvetica Neue'; color:#000000;">: the direction the slope faces  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">- </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Shade intensity</span><span style=" font-family:'Helvetica Neue'; color:#000000;">: how strongly an area is affected by shade  </span></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">- </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">Solar hours</span><span style=" font-family:'Helvetica Neue'; color:#000000;">: the number of hours an area receives sunlight, calculated with </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">GRASS </span><span style=" font-family:'.AppleSystemUIFontMonospaced'; color:#000000;">r.sun.insoltime</span></p>
<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px; font-family:'Helvetica Neue'; color:#000000;"><br /></p>
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-family:'Helvetica Neue'; color:#000000;">This is useful for understanding </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">sun exposure</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">shade patterns</span><span style=" font-family:'Helvetica Neue'; color:#000000;">, and </span><span style=" font-family:'Helvetica Neue'; font-weight:600; color:#000000;">site suitability</span><span style=" font-family:'Helvetica Neue'; color:#000000;"> for planting, agriculture, restoration, and landscape design.</span> </p></body></html></p>
<br></body></html>"""

    def createInstance(self):
        return SolarRadiation()
