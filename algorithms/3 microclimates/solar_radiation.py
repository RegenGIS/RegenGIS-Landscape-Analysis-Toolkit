"""
Generated from a QGIS-model for the RegenGIS processing plugin.

The conversion keeps the exported model logic intact while normalizing
the algorithm id, display name and class boilerplate for plugin use.
"""

from __future__ import annotations

from datetime import date, datetime


from qgis.core import QgsProcessing
from qgis.core import QgsProcessingAlgorithm
from qgis.core import QgsProcessingContext
from qgis.core import QgsProcessingMultiStepFeedback
from qgis.core import QgsProcessingParameterDateTime
from qgis.core import QgsProcessingParameterRasterLayer
from qgis.core import QgsProcessingParameterRasterDestination
import processing


def _coerce_python_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    to_py_datetime = getattr(value, "toPyDateTime", None)
    if callable(to_py_datetime):
        py_datetime = to_py_datetime()
        if isinstance(py_datetime, datetime):
            return py_datetime.date()
        if isinstance(py_datetime, date):
            return py_datetime

    to_py_date = getattr(value, "toPyDate", None)
    if callable(to_py_date):
        py_date = to_py_date()
        if isinstance(py_date, date):
            return py_date

    raise TypeError(f"Unsupported date value for solar analysis: {value!r}")


def _day_of_year(value) -> int:
    return _coerce_python_date(value).timetuple().tm_yday


def _current_map_extent_in_layer_crs(layer, feedback=None):
    from regengis_processing_plugin.autocrs.prepare import _current_map_extent_in_layer_crs as helper

    return helper(layer, feedback=feedback)


def _translate_raster_to_input_crs(input_raster, output_raster, input_crs, context, feedback):
    output_value = output_raster or QgsProcessing.TEMPORARY_OUTPUT
    result = processing.run(
        'gdal:translate',
        {
            'COPY_SUBDATASETS': False,
            'DATA_TYPE': 0,
            'EXTRA': '',
            'INPUT': input_raster,
            'NODATA': None,
            'OPTIONS': '',
            'OUTPUT': output_value,
            'TARGET_CRS': input_crs,
        },
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    return result['OUTPUT']


def _set_layer_name_on_completion(context, output_path, layer_name):
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


class SolarRadiation(QgsProcessingAlgorithm):

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterDateTime('date', 'Date', type=QgsProcessingParameterDateTime.Date, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterLayer('digital_surface_model_dsm_or_digital_terrain_model_dtm', 'Digital Surface Model (DSM) or Digital Terrain Model (DTM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Shade_intensity', 'Shade intensity', optional=True, createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Solar_hours', 'Solar hours', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Aspect', 'Aspect', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Slope', 'Slope', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(5, model_feedback)
        results = {}
        outputs = {}
        analysis_date = self.parameterAsDateTime(parameters, 'date', context)
        analysis_day = _day_of_year(analysis_date)
        input_layer = self.parameterAsRasterLayer(parameters, 'digital_surface_model_dsm_or_digital_terrain_model_dtm', context)
        if input_layer is None:
            raise ValueError('Input raster layer is required.')

        input_crs = input_layer.crs()
        working_extent = _current_map_extent_in_layer_crs(input_layer, feedback=feedback)
        if working_extent is not None:
            if hasattr(feedback, 'pushInfo'):
                feedback.pushInfo('RegenGIS is clipping the DSM/DTM to the current map extent, transformed into the raster CRS.')
        else:
            working_extent = input_layer.extent()
            if hasattr(feedback, 'pushInfo'):
                feedback.pushInfo('Current map extent was unavailable, so RegenGIS is clipping the DSM/DTM to the full raster extent.')

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': input_crs,
            'EXPRESSION': '"A@1"',
            'EXTENT': working_extent,
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

        # Stamp/stabilize the rasters before handing them to GRASS. On Windows
        # QGIS 3.44 the temporary rastercalc/aspect/slope outputs can reach
        # GRASS without readable projection metadata, causing r.sun to fail
        # with "Can't get projection info of current project".
        outputs['GrassElevation'] = _translate_raster_to_input_crs(
            outputs['FillNodata']['OUTPUT'],
            QgsProcessing.TEMPORARY_OUTPUT,
            input_crs,
            context,
            feedback,
        )
        outputs['GrassAspect'] = _translate_raster_to_input_crs(
            outputs['Aspect']['OUTPUT'],
            QgsProcessing.TEMPORARY_OUTPUT,
            input_crs,
            context,
            feedback,
        )
        outputs['GrassSlope'] = _translate_raster_to_input_crs(
            outputs['Slope']['OUTPUT'],
            QgsProcessing.TEMPORARY_OUTPUT,
            input_crs,
            context,
            feedback,
        )

        # r.sun.insoltime
        alg_params = {
            '-m': False,
            '-p': False,
            'GRASS_RASTER_FORMAT_META': None,
            'GRASS_RASTER_FORMAT_OPT': None,
            'GRASS_REGION_CELLSIZE_PARAMETER': 0,
            'GRASS_REGION_PARAMETER': working_extent,
            'albedo': None,
            'albedo_value': None,
            'aspect': outputs['GrassAspect'],
            'aspect_value': None,
            'civil_time': None,
            'coeff_bh': None,
            'coeff_dh': None,
            'day': analysis_day,
            'declination': None,
            'distance_step': 1,
            'elevation': outputs['GrassElevation'],
            'horizon_basemap': None,
            'horizon_step': None,
            'lat': None,
            'linke': None,
            'long': None,
            'npartitions': 1,
            'slope': outputs['GrassSlope'],
            'slope_value': 0,
            'step': 0.5,
            'glob_rad': QgsProcessing.TEMPORARY_OUTPUT,
            'insol_time': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['Rsuninsoltime'] = processing.run('grass:r.sun.insoltime', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Shade_intensity'] = _translate_raster_to_input_crs(
            outputs['Rsuninsoltime']['glob_rad'],
            parameters['Shade_intensity'],
            input_crs,
            context,
            feedback,
        )
        _set_layer_name_on_completion(context, results['Shade_intensity'], 'Shade intensity')

        results['Solar_hours'] = _translate_raster_to_input_crs(
            outputs['Rsuninsoltime']['insol_time'],
            parameters['Solar_hours'],
            input_crs,
            context,
            feedback,
        )
        _set_layer_name_on_completion(context, results['Solar_hours'], 'Solar hours')
        return results

    def name(self):
        return 'solar_radiation'
    def displayName(self):
        return 'Solar Radiation'
    def group(self):
        return 'Microclimates'

    def groupId(self):
        return 'microclimates'

    def shortHelpString(self):
        return """<html><body><p><!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">

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
