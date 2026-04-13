"""
Model exported as python.
Name : Solar radiation
With QGIS : 34005
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
        self.addParameter(QgsProcessingParameterRasterLayer('digital_surface_model_dsm', 'Digital Surface Model (DSM)', defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Shade_intensity', 'Shade_intensity', optional=True, createByDefault=True, defaultValue=''))
        self.addParameter(QgsProcessingParameterRasterDestination('Solar_hours', 'Solar_hours', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Aspect', 'Aspect', createByDefault=True, defaultValue=None))
        self.addParameter(QgsProcessingParameterRasterDestination('Slope', 'Slope', createByDefault=True, defaultValue=None))

    def processAlgorithm(self, parameters, context, model_feedback):
        # Use a multi-step feedback, so that individual child algorithm progress reports are adjusted for the
        # overall progress through the model
        feedback = QgsProcessingMultiStepFeedback(4, model_feedback)
        results = {}
        outputs = {}
        date_value = self.parameterAsDateTime(parameters, 'date', context)
        day_of_year = date_value.date().dayOfYear() if date_value.isValid() else None

        # Raster calculator
        alg_params = {
            'CELL_SIZE': None,
            'CRS': None,
            'EXPRESSION': '"A@1"',
            'EXTENT': QgsExpression(' @map_extent ').evaluate(),
            'LAYERS': parameters['digital_surface_model_dsm'],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
        }
        outputs['RasterCalculator'] = processing.run('native:modelerrastercalc', alg_params, context=context, feedback=feedback, is_child_algorithm=True)

        feedback.setCurrentStep(1)
        if feedback.isCanceled():
            return {}

        # Slope
        alg_params = {
            'INPUT': outputs['RasterCalculator']['OUTPUT'],
            'Z_FACTOR': 1,
            'OUTPUT': parameters['Slope']
        }
        outputs['Slope'] = processing.run('native:slope', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Slope'] = outputs['Slope']['OUTPUT']

        feedback.setCurrentStep(2)
        if feedback.isCanceled():
            return {}

        # Aspect
        alg_params = {
            'INPUT': outputs['RasterCalculator']['OUTPUT'],
            'Z_FACTOR': 1,
            'OUTPUT': parameters['Aspect']
        }
        outputs['Aspect'] = processing.run('native:aspect', alg_params, context=context, feedback=feedback, is_child_algorithm=True)
        results['Aspect'] = outputs['Aspect']['OUTPUT']

        feedback.setCurrentStep(3)
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
            'aspect_value': 270,
            'civil_time': None,
            'coeff_bh': None,
            'coeff_dh': None,
            'day': day_of_year,
            'declination': None,
            'distance_step': 1,
            'elevation': parameters['digital_surface_model_dsm'],
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

    def createInstance(self):
        return SolarRadiation()
