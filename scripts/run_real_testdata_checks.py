from __future__ import annotations

import json
import shutil
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from qgis.PyQt.QtCore import QDate
from qgis.core import (
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFeatureRequest,
    QgsMapLayerType,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsVectorLayer,
    QgsWkbTypes,
)

PLUGIN_ROOT = Path('/mnt/ugreen/hermes_coop/qgis/regengis_processing_plugin')
if str(PLUGIN_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT.parent))

import processing  # noqa: E402
from processing.core.Processing import Processing  # noqa: E402
from regengis_processing_plugin.processing_provider import ModelToolboxProvider  # noqa: E402

PROJECT_PATH = Path('/mnt/ugreen/hermes_coop/qgis/regengis_plugin_testdata/werkkaart.qgz')
OUTPUT_ROOT = PLUGIN_ROOT / 'tests' / 'output' / 'real_testdata'
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


class CollectingFeedback(QgsProcessingFeedback):
    def __init__(self):
        super().__init__()
        self.messages: list[str] = []

    def pushInfo(self, info: str):
        self.messages.append(f'INFO: {info}')
        super().pushInfo(info)

    def reportError(self, error: str, fatalError: bool = False):
        self.messages.append(f"ERROR{' FATAL' if fatalError else ''}: {error}")
        super().reportError(error, fatalError)

    def pushWarning(self, warning: str):
        self.messages.append(f'WARNING: {warning}')
        super().pushWarning(warning)

    def pushDebugInfo(self, info: str):
        self.messages.append(f'DEBUG: {info}')
        super().pushDebugInfo(info)

    def pushCommandInfo(self, info: str):
        self.messages.append(f'COMMAND: {info}')
        super().pushCommandInfo(info)

    def pushConsoleInfo(self, info: str):
        self.messages.append(f'CONSOLE: {info}')
        super().pushConsoleInfo(info)


def layer_info(layer) -> dict:
    extent = layer.extent()
    info = {
        'name': layer.name(),
        'provider': layer.providerType(),
        'source': layer.source(),
        'crs_authid': layer.crs().authid(),
        'crs_valid': layer.crs().isValid(),
        'extent': {
            'xmin': extent.xMinimum(),
            'ymin': extent.yMinimum(),
            'xmax': extent.xMaximum(),
            'ymax': extent.yMaximum(),
        },
    }
    if layer.type() == QgsMapLayerType.RasterLayer:
        info['width'] = layer.width()
        info['height'] = layer.height()
    return info


def parse_project_map_extent(project_path: Path) -> tuple[QgsRectangle, QgsCoordinateReferenceSystem]:
    with zipfile.ZipFile(project_path) as archive:
        member = next(name for name in archive.namelist() if name.endswith('.qgs'))
        root = ET.fromstring(archive.read(member))
    mapcanvas = root.find('.//mapcanvas')
    assert mapcanvas is not None, 'project mapcanvas missing'
    extent_node = mapcanvas.find('./extent')
    assert extent_node is not None, 'project extent missing'
    xmin_text = extent_node.findtext('xmin')
    ymin_text = extent_node.findtext('ymin')
    xmax_text = extent_node.findtext('xmax')
    ymax_text = extent_node.findtext('ymax')
    assert xmin_text is not None and ymin_text is not None and xmax_text is not None and ymax_text is not None, 'project extent coordinates missing'
    xmin = float(xmin_text)
    ymin = float(ymin_text)
    xmax = float(xmax_text)
    ymax = float(ymax_text)
    extent = QgsRectangle(xmin, ymin, xmax, ymax)
    crs = QgsCoordinateReferenceSystem()
    wkt = mapcanvas.findtext('./destinationsrs/spatialrefsys/wkt')
    assert wkt, 'project map canvas CRS missing'
    ok = crs.createFromWkt(wkt)
    assert ok and crs.isValid(), 'project map canvas CRS invalid'
    return extent, crs


def raster_validation(path: str | None, expected_crs: str | None) -> dict:
    result = {
        'path': path,
        'file_exists': False,
        'layer_opens': False,
        'provider': None,
        'crs_authid': None,
        'crs_matches_expected': None,
        'width': None,
        'height': None,
        'band_count': None,
        'band_read_ok': False,
        'extent_is_sane': False,
        'errors': [],
    }
    if not path:
        result['errors'].append('Missing output path')
        return result
    p = Path(path)
    result['file_exists'] = p.exists()
    if not p.exists():
        result['errors'].append('Output file does not exist')
        return result
    layer = QgsRasterLayer(str(p), p.name)
    result['layer_opens'] = layer.isValid()
    if not layer.isValid():
        result['errors'].append('Output raster could not be opened')
        return result
    result['provider'] = layer.providerType()
    result['crs_authid'] = layer.crs().authid()
    if expected_crs:
        result['crs_matches_expected'] = result['crs_authid'] == expected_crs
        if not result['crs_matches_expected']:
            result['errors'].append(f"CRS mismatch: expected {expected_crs}, got {result['crs_authid']}")
    result['width'] = layer.width()
    result['height'] = layer.height()
    provider = layer.dataProvider()
    if provider is not None:
        result['band_count'] = provider.bandCount()
        try:
            block = provider.block(1, layer.extent(), max(1, min(layer.width(), 10)), max(1, min(layer.height(), 10)))
            result['band_read_ok'] = block is not None and not block.isEmpty()
        except Exception as exc:
            result['errors'].append(f'Band read failed: {exc}')
    if not result['band_read_ok']:
        result['errors'].append('Raster band data could not be read')
    result['extent_is_sane'] = not layer.extent().isNull() and not layer.extent().isEmpty()
    if not result['extent_is_sane']:
        result['errors'].append('Raster extent is null or empty')
    return result


def vector_validation(path: str | None, expected_crs: str | None, required_fields: list[str], geometry_any_of: list[str]) -> dict:
    result = {
        'path': path,
        'file_exists': False,
        'layer_opens': False,
        'provider': None,
        'crs_authid': None,
        'crs_matches_expected': None,
        'feature_count': None,
        'geometry_type': None,
        'geometry_ok': False,
        'required_fields_present': None,
        'errors': [],
    }
    if not path:
        result['errors'].append('Missing output path')
        return result
    p = Path(path)
    result['file_exists'] = p.exists()
    if not p.exists():
        result['errors'].append('Output vector does not exist')
        return result
    layer = QgsVectorLayer(str(p), p.stem, 'ogr')
    result['layer_opens'] = layer.isValid()
    if not layer.isValid():
        result['errors'].append('Output vector could not be opened')
        return result
    result['provider'] = layer.providerType()
    result['crs_authid'] = layer.crs().authid()
    if expected_crs:
        result['crs_matches_expected'] = result['crs_authid'] == expected_crs
        if not result['crs_matches_expected']:
            result['errors'].append(f"CRS mismatch: expected {expected_crs}, got {result['crs_authid']}")
    result['feature_count'] = layer.featureCount()
    result['geometry_type'] = QgsWkbTypes.displayString(layer.wkbType())
    result['geometry_ok'] = any(name in result['geometry_type'] for name in geometry_any_of)
    if not result['geometry_ok']:
        result['errors'].append(f"Unexpected geometry type: {result['geometry_type']}")
    field_names = {field.name() for field in layer.fields()}
    result['required_fields_present'] = all(name in field_names for name in required_fields)
    if not result['required_fields_present']:
        missing = [name for name in required_fields if name not in field_names]
        result['errors'].append(f'Missing required fields: {missing}')
    return result


def same_extent(a: dict, b: dict, tol: float = 1e-6) -> bool:
    for key in ('xmin', 'ymin', 'xmax', 'ymax'):
        if abs(a[key] - b[key]) > tol:
            return False
    return True


def multi_raster_validation(outputs: dict[str, str], expected_crs: str | None) -> dict:
    validations = {name: raster_validation(path, expected_crs) for name, path in outputs.items()}
    available = [v for v in validations.values() if v['layer_opens']]
    same_crs = len({v['crs_authid'] for v in available}) <= 1 if available else False
    same_dimensions = len({(v['width'], v['height']) for v in available}) <= 1 if available else False
    extents = []
    for path in outputs.values():
        layer = QgsRasterLayer(path, Path(path).name)
        if layer.isValid():
            extent = layer.extent()
            extents.append({'xmin': extent.xMinimum(), 'ymin': extent.yMinimum(), 'xmax': extent.xMaximum(), 'ymax': extent.yMaximum()})
    same_ext = all(same_extent(extents[0], item) for item in extents[1:]) if extents else False
    return {
        'outputs': validations,
        'cross_output_rules': {
            'same_crs': same_crs,
            'same_dimensions': same_dimensions,
            'same_extent': same_ext,
        },
    }


def run_case(case_id: str, algorithm_id: str, params: dict) -> dict:
    feedback = CollectingFeedback()
    case_output_dir = OUTPUT_ROOT / case_id
    if case_output_dir.exists():
        shutil.rmtree(case_output_dir)
    case_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = processing.run(algorithm_id, params, context=context, feedback=feedback)
        status = 'PASS'
        error = None
    except Exception as exc:
        result = None
        status = 'FAIL'
        error = {'type': type(exc).__name__, 'message': str(exc)}
    return {
        'case_id': case_id,
        'algorithm_id': algorithm_id,
        'status': status,
        'error': error,
        'result': result,
        'logs': feedback.messages,
    }


app = QgsApplication([], False)
app.initQgis()
Processing.initialize()
provider = ModelToolboxProvider()
provider.loadAlgorithms()
QgsApplication.processingRegistry().addProvider(provider)
project = QgsProject.instance()
project.read(str(PROJECT_PATH))
context = QgsProcessingContext()
context.setProject(project)
project_extent, project_extent_crs = parse_project_map_extent(PROJECT_PATH)

layers = {layer.name(): layer for layer in project.mapLayers().values()}
local_rd = layers['DSM_epsg28992']
local_eur = layers['dsm_eur']
wcs = layers['DSM_WCS']

cases = [
    run_case('recommend_local_rdnew', 'regengis_toolbox:recommend_analysis_crs', {'INPUT': local_rd}),
    run_case('recommend_metric_europe', 'regengis_toolbox:recommend_analysis_crs', {'INPUT': local_eur}),
    run_case('recommend_wcs_rdnew', 'regengis_toolbox:recommend_analysis_crs', {'INPUT': wcs}),
    run_case(
        'prepare_local_rdnew_project_extent',
        'regengis_toolbox:prepare_raster_for_analysis',
        {
            'INPUT': local_rd,
            'AUTO_SELECT_ANALYSIS_CRS': True,
            'TARGET_CRS': None,
            'ANALYSIS_EXTENT': project_extent,
            'ANALYSIS_EXTENT_CRS': project_extent_crs,
            'OUTPUT': str(OUTPUT_ROOT / 'prepare_local_rdnew_project_extent' / 'prepared.tif'),
        },
    ),
    run_case(
        'prepare_metric_europe_project_extent',
        'regengis_toolbox:prepare_raster_for_analysis',
        {
            'INPUT': local_eur,
            'AUTO_SELECT_ANALYSIS_CRS': True,
            'TARGET_CRS': None,
            'ANALYSIS_EXTENT': project_extent,
            'ANALYSIS_EXTENT_CRS': project_extent_crs,
            'OUTPUT': str(OUTPUT_ROOT / 'prepare_metric_europe_project_extent' / 'prepared.tif'),
        },
    ),
    run_case(
        'prepare_wcs_project_extent',
        'regengis_toolbox:prepare_raster_for_analysis',
        {
            'INPUT': wcs,
            'AUTO_SELECT_ANALYSIS_CRS': True,
            'TARGET_CRS': None,
            'ANALYSIS_EXTENT': project_extent,
            'ANALYSIS_EXTENT_CRS': project_extent_crs,
            'OUTPUT': str(OUTPUT_ROOT / 'prepare_wcs_project_extent' / 'prepared.tif'),
        },
    ),
    run_case(
        'height_contours_project_extent',
        'regengis_toolbox:height_contours',
        {
            'digital_terrain_model_dtm': local_rd,
            'desired_height_distance_between_contours_m': 1.0,
            'Height_contours': str(OUTPUT_ROOT / 'height_contours_project_extent' / 'height_contours.gpkg'),
        },
    ),
    run_case(
        'topographic_wetness_index_project_extent',
        'regengis_toolbox:topographic_wetness_index',
        {
            'digital_terrain_model_dtm': local_rd,
            'TopographicWetnessIndexTwi': str(OUTPUT_ROOT / 'topographic_wetness_index_project_extent' / 'twi.tif'),
        },
    ),
    run_case(
        'water_flow_project_extent',
        'regengis_toolbox:water_flow',
        {
            'digital_terrain_model_dtm': local_rd,
            'Water_flow': str(OUTPUT_ROOT / 'water_flow_project_extent' / 'water_flow.tif'),
        },
    ),
    run_case(
        'solar_radiation_project_extent',
        'regengis_toolbox:solar_radiation',
        {
            'date': QDate(2026, 6, 21),
            'digital_surface_model_dsm_or_digital_terrain_model_dtm': local_rd,
            'Shade_intensity': str(OUTPUT_ROOT / 'solar_radiation_project_extent' / 'shade_intensity.tif'),
            'Solar_hours': str(OUTPUT_ROOT / 'solar_radiation_project_extent' / 'solar_hours.tif'),
            'Aspect': str(OUTPUT_ROOT / 'solar_radiation_project_extent' / 'aspect.tif'),
            'Slope': str(OUTPUT_ROOT / 'solar_radiation_project_extent' / 'slope.tif'),
        },
    ),
]

report = {
    'project_path': str(PROJECT_PATH),
    'project_crs': project.crs().authid(),
    'project_map_extent': {
        'xmin': project_extent.xMinimum(),
        'ymin': project_extent.yMinimum(),
        'xmax': project_extent.xMaximum(),
        'ymax': project_extent.yMaximum(),
    },
    'project_map_extent_crs': project_extent_crs.authid(),
    'layers': {name: layer_info(layer) for name, layer in layers.items()},
    'cases': cases,
}

for case in report['cases']:
    if case['status'] != 'PASS' or not case['result']:
        continue
    case_id = case['case_id']
    result = case['result']
    if case['algorithm_id'] == 'regengis_toolbox:prepare_raster_for_analysis':
        case['raster_validation'] = raster_validation(result.get('OUTPUT'), result.get('OUTPUT_TARGET_CRS'))
    elif case['algorithm_id'] == 'regengis_toolbox:height_contours':
        case['vector_validation'] = vector_validation(
            result.get('Height_contours'),
            local_rd.crs().authid(),
            required_fields=['ELEV'],
            geometry_any_of=['LineString', 'MultiLineString'],
        )
    elif case['algorithm_id'] == 'regengis_toolbox:topographic_wetness_index':
        case['raster_validation'] = raster_validation(result.get('TopographicWetnessIndexTwi'), local_rd.crs().authid())
    elif case['algorithm_id'] == 'regengis_toolbox:water_flow':
        case['raster_validation'] = raster_validation(result.get('Water_flow'), local_rd.crs().authid())
    elif case['algorithm_id'] == 'regengis_toolbox:solar_radiation':
        case['multi_raster_validation'] = multi_raster_validation(
            {
                'Aspect': result.get('Aspect'),
                'Slope': result.get('Slope'),
                'Shade_intensity': result.get('Shade_intensity'),
                'Solar_hours': result.get('Solar_hours'),
            },
            local_rd.crs().authid(),
        )

print(json.dumps(report, indent=2))

QgsApplication.processingRegistry().removeProvider(provider)
app.exitQgis()
