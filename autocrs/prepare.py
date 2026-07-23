"""Raster preparation helpers for analysis-ready AutoCRS workflows."""

from __future__ import annotations

from dataclasses import dataclass
import os
import tempfile
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

from .selector import (
    AutoCrsRecommendation,
    _is_metric_projected_crs,
    _proj_string_for_crs,
    qgis_crs_from_recommendation,
    recommend_metric_crs_for_extent,
    recommend_metric_crs_for_layer,
)
from .temp_layers import temporary_output_value

try:
    import processing
    from qgis.core import (
        QgsCoordinateReferenceSystem,
        QgsCoordinateTransform,
        QgsProcessing,
        QgsProject,
        QgsRectangle,
        QgsRasterFileWriter,
        QgsRasterPipe,
    )
    try:
        from qgis.utils import iface
    except Exception:  # pragma: no cover - iface is GUI-only
        iface = None
except ModuleNotFoundError as exc:  # pragma: no cover - allows import outside QGIS
    if not getattr(exc, "name", "").startswith("qgis") and getattr(exc, "name", "") != "processing":
        raise
    processing = None
    QgsCoordinateReferenceSystem = None
    QgsCoordinateTransform = None
    QgsProcessing = None
    QgsProject = None
    QgsRectangle = None
    QgsRasterFileWriter = None
    QgsRasterPipe = None
    iface = None


@dataclass(frozen=True)
class PreparedRaster:
    layer_or_path: object
    source_crs_authid: str
    target_crs_authid: str
    was_reprojected: bool
    recommendation: AutoCrsRecommendation
    pixel_size_x: float | None = None
    pixel_size_y: float | None = None


def _require_qgis(function_name: str) -> None:
    if (
        QgsCoordinateReferenceSystem is None
        or QgsCoordinateTransform is None
        or QgsProject is None
        or QgsRectangle is None
        or QgsRasterFileWriter is None
        or QgsRasterPipe is None
    ):
        raise RuntimeError(f"{function_name} requires a QGIS runtime with PyQGIS available.")


def _project_file_path() -> Path | None:
    if QgsProject is None:
        return None
    project = QgsProject.instance()
    if project is None or not hasattr(project, "fileName"):
        return None
    file_name = project.fileName()
    if not file_name:
        return None
    path = Path(file_name)
    return path if path.exists() else None


def _parse_project_mapcanvas_extent():
    _require_qgis("_parse_project_mapcanvas_extent")
    project_path = _project_file_path()
    if project_path is None:
        return None, None

    try:
        if project_path.suffix.lower() == ".qgz":
            with zipfile.ZipFile(project_path) as archive:
                project_member = next((name for name in archive.namelist() if name.endswith('.qgs')), None)
                if project_member is None:
                    return None, None
                raw_xml = archive.read(project_member)
        else:
            raw_xml = project_path.read_bytes()
        root = ET.fromstring(raw_xml)
    except Exception:
        return None, None

    mapcanvas = root.find('.//mapcanvas')
    if mapcanvas is None:
        return None, None

    extent_node = mapcanvas.find('./extent')
    if extent_node is None:
        return None, None

    xmin_text = extent_node.findtext('xmin')
    ymin_text = extent_node.findtext('ymin')
    xmax_text = extent_node.findtext('xmax')
    ymax_text = extent_node.findtext('ymax')
    if xmin_text is None or ymin_text is None or xmax_text is None or ymax_text is None:
        return None, None

    try:
        xmin = float(xmin_text)
        ymin = float(ymin_text)
        xmax = float(xmax_text)
        ymax = float(ymax_text)
    except ValueError:
        return None, None

    if xmax <= xmin or ymax <= ymin:
        return None, None

    extent = QgsRectangle(xmin, ymin, xmax, ymax)

    destination_crs = None
    wkt = mapcanvas.findtext('./destinationsrs/spatialrefsys/wkt')
    if wkt:
        destination_crs = QgsCoordinateReferenceSystem()
        if hasattr(destination_crs, 'createFromWkt'):
            if not destination_crs.createFromWkt(wkt):
                destination_crs = None
        elif not destination_crs.isValid():
            destination_crs = None

    if destination_crs is None or not destination_crs.isValid():
        project = QgsProject.instance()
        destination_crs = project.crs() if project is not None and hasattr(project, 'crs') else None

    return extent, destination_crs


def _require_processing(function_name: str) -> None:
    if processing is None:
        raise RuntimeError(f"{function_name} requires the QGIS processing module.")


def extent_in_wgs84_for_layer(layer):
    _require_qgis("extent_in_wgs84_for_layer")
    if layer is None:
        raise ValueError("Layer is required.")

    source_crs = layer.crs()
    extent = layer.extent()
    wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)

    if source_crs.authid() == "EPSG:4326":
        return extent

    transform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
    return transform.transformBoundingBox(extent, handle180Crossover=True)


def _epsg_from_authid(authid: str) -> int | None:
    if not authid.startswith("EPSG:"):
        return None
    try:
        return int(authid.split(":", 1)[1])
    except Exception:
        return None


def _is_utm_or_ups_authid_or_description(authid: str, description: str) -> bool:
    lowered = f"{authid} {description}".lower()
    return "utm" in lowered or "ups" in lowered


def _source_crs(layer):
    if layer is None:
        raise ValueError("Layer is required.")
    crs = layer.crs()
    if crs is None or not hasattr(crs, "isValid") or not crs.isValid():
        raise ValueError(
            "Input raster CRS is missing or invalid. Assign the correct source CRS before using RegenGIS AutoCRS tools."
        )
    return crs


def _existing_metric_crs_recommendation(layer, feedback=None) -> AutoCrsRecommendation | None:
    crs = _source_crs(layer)
    if not _is_metric_projected_crs(crs):
        return None

    authid = crs.authid() or ""
    description = crs.description() or authid or "Projected metric CRS"
    recommendation = AutoCrsRecommendation(
        authid=authid,
        description=description,
        proj4=_proj_string_for_crs(crs),
        epsg=_epsg_from_authid(authid),
        strategy="existing_metric_crs",
        distortion_ppm=0.0,
        is_utm_or_ups=_is_utm_or_ups_authid_or_description(authid, description),
    )
    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(
            "Input raster already uses a valid projected metric CRS, so RegenGIS is keeping that CRS for analysis: "
            f"{recommendation.authid or recommendation.description}."
        )
    return recommendation


def recommend_analysis_crs_for_layer(layer, feedback=None) -> AutoCrsRecommendation:
    """Recommend an analysis CRS from the smallest intended working area.

    For WCS/provider-backed rasters, CRS selection should follow the same
    working-area priority as staging:
    1. explicit analysis extent when available upstream
    2. current map extent as the best interactive proxy
    3. full layer extent only as a fallback

    This avoids letting a very large service extent dominate CRS choice when the
    user is clearly working within a smaller map window.
    """
    _source_crs(layer)

    map_extent = _current_map_extent_in_layer_crs(layer, feedback=feedback)
    if _extent_is_usable(map_extent):
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo(
                "RegenGIS is using the current map extent to choose the analysis CRS, so broad source projections do not dominate local analysis."
            )
        map_extent_wgs84 = _transform_extent(
            map_extent,
            layer.crs(),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        return recommend_metric_crs_for_extent(map_extent_wgs84, feedback=feedback)

    provider_type = _layer_provider_type(layer)
    if provider_type == "wcs":
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo(
                "Input raster comes from a WCS provider, but the current map extent was not available, so RegenGIS is falling back to the full layer extent for analysis CRS selection."
            )

    existing_metric = _existing_metric_crs_recommendation(layer, feedback=feedback)
    if existing_metric is not None:
        return existing_metric

    return recommend_metric_crs_for_layer(layer, feedback=feedback)


def layer_needs_reprojection(layer, target_crs) -> bool:
    if layer is None:
        raise ValueError("Layer is required.")

    if hasattr(target_crs, "authid"):
        target_authid = target_crs.authid()
    else:
        target_authid = str(target_crs)

    source_authid = layer.crs().authid()
    return bool(source_authid and target_authid and source_authid != target_authid)


def _target_crs_from_input(target_crs, recommendation: AutoCrsRecommendation):
    _require_qgis("_target_crs_from_input")
    if target_crs is None:
        return qgis_crs_from_recommendation(recommendation)
    if isinstance(target_crs, AutoCrsRecommendation):
        return qgis_crs_from_recommendation(target_crs)
    if hasattr(target_crs, "authid"):
        return target_crs

    target_authid = str(target_crs)
    crs = QgsCoordinateReferenceSystem(target_authid)
    if crs.isValid():
        return crs
    raise RuntimeError(f"Could not construct target CRS from '{target_authid}'.")


def _pixel_size(layer) -> tuple[float | None, float | None]:
    raster_units_per_pixel_x = getattr(layer, "rasterUnitsPerPixelX", None)
    raster_units_per_pixel_y = getattr(layer, "rasterUnitsPerPixelY", None)
    x_size = raster_units_per_pixel_x() if callable(raster_units_per_pixel_x) else None
    y_size = raster_units_per_pixel_y() if callable(raster_units_per_pixel_y) else None
    return x_size, y_size


def _layer_provider_type(layer) -> str:
    provider_type = getattr(layer, "providerType", None)
    value = provider_type() if callable(provider_type) else provider_type
    return str(value or "").lower()


def _layer_source(layer) -> str:
    source = getattr(layer, "source", None)
    value = source() if callable(source) else source
    return str(value or "")


def _is_probably_local_raster_source(source: str) -> bool:
    if not source:
        return False
    lower_source = source.lower()
    if lower_source.startswith("file://"):
        return True
    if lower_source.startswith(("wcs://", "wms://", "xyz://", "http://", "https://", "ftp://")):
        return False
    if "://" in source:
        return False
    if source.startswith(("/", "./", "../", "~/")):
        return True
    if len(source) >= 3 and source[1:3] == ':\\':
        return True
    return True


def _extent_is_usable(extent) -> bool:
    if extent is None:
        return False
    is_null = getattr(extent, "isNull", None)
    if callable(is_null) and is_null():
        return False
    is_empty = getattr(extent, "isEmpty", None)
    if callable(is_empty) and is_empty():
        return False
    width = getattr(extent, "width", None)
    height = getattr(extent, "height", None)
    width_value = width() if callable(width) else width
    height_value = height() if callable(height) else height
    if width_value is not None and width_value <= 0:
        return False
    if height_value is not None and height_value <= 0:
        return False
    return True


def _transform_extent(extent, source_crs, target_crs):
    _require_qgis("_transform_extent")
    if not _extent_is_usable(extent):
        return None
    if source_crs is None or target_crs is None:
        return extent

    source_authid = source_crs.authid() if hasattr(source_crs, "authid") else str(source_crs)
    target_authid = target_crs.authid() if hasattr(target_crs, "authid") else str(target_crs)
    if source_authid and target_authid and source_authid == target_authid:
        return extent

    transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
    return transform.transformBoundingBox(extent, handle180Crossover=True)


def _current_map_extent_in_layer_crs(layer, feedback=None):
    _require_qgis("_current_map_extent_in_layer_crs")
    canvas = iface.mapCanvas() if iface is not None and hasattr(iface, "mapCanvas") else None

    if canvas is not None:
        canvas_extent = canvas.extent() if hasattr(canvas, "extent") else None
        if _extent_is_usable(canvas_extent):
            map_settings = canvas.mapSettings() if hasattr(canvas, "mapSettings") else None
            canvas_crs = map_settings.destinationCrs() if map_settings is not None and hasattr(map_settings, "destinationCrs") else None
            try:
                extent_in_layer_crs = _transform_extent(canvas_extent, canvas_crs, layer.crs())
            except Exception as exc:
                if feedback is not None and hasattr(feedback, "pushInfo"):
                    feedback.pushInfo(
                        "Could not transform current map extent into the raster CRS, so RegenGIS will try the stored project map extent next. "
                        f"Details: {exc}"
                    )
            else:
                if _extent_is_usable(extent_in_layer_crs):
                    return extent_in_layer_crs

    project_extent, project_extent_crs = _parse_project_mapcanvas_extent()
    if _extent_is_usable(project_extent):
        try:
            extent_in_layer_crs = _transform_extent(project_extent, project_extent_crs, layer.crs())
        except Exception as exc:
            if feedback is not None and hasattr(feedback, "pushInfo"):
                feedback.pushInfo(
                    "Could not transform the stored project map extent into the raster CRS, so RegenGIS will fall back to the full layer extent. "
                    f"Details: {exc}"
                )
            return None
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo("Using the stored map extent from the current QGIS project for headless processing.")
        return extent_in_layer_crs if _extent_is_usable(extent_in_layer_crs) else None

    return None


def _resolve_materialization_extent(layer, requested_extent=None, requested_extent_crs=None, feedback=None):
    """Choose the smallest intended working extent for raster staging.

    Priority order:
    1. explicit analysis/requested extent
    2. current map extent
    3. full layer extent

    This keeps online/provider-backed rasters such as WCS bounded to the user's
    working window when possible, while preserving deterministic fallbacks for
    headless runs or missing canvas state.
    """
    requested_in_layer_crs = None
    if _extent_is_usable(requested_extent):
        try:
            requested_in_layer_crs = _transform_extent(requested_extent, requested_extent_crs, layer.crs())
        except Exception as exc:
            if feedback is not None and hasattr(feedback, "pushInfo"):
                feedback.pushInfo(
                    "Could not transform the requested analysis extent into the raster CRS, so RegenGIS will try the current map extent instead. "
                    f"Details: {exc}"
                )
            requested_in_layer_crs = None

    if _extent_is_usable(requested_in_layer_crs):
        return requested_in_layer_crs

    map_extent = _current_map_extent_in_layer_crs(layer, feedback=feedback)
    if _extent_is_usable(map_extent):
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo("No explicit analysis extent was provided, so RegenGIS is using the current map extent to limit WCS staging.")
        return map_extent

    return layer.extent()


def _write_layer_to_temp_geotiff(layer, context, feedback, *, extent=None) -> str:
    _require_qgis("_write_layer_to_temp_geotiff")
    provider_getter = getattr(layer, "dataProvider", None)
    provider = provider_getter() if callable(provider_getter) else provider_getter
    if provider is None:
        raise RuntimeError("Input raster does not expose a data provider for temporary staging.")

    provider_clone = provider.clone() if hasattr(provider, "clone") else None
    if provider_clone is None:
        raise RuntimeError("Input raster provider could not be cloned for temporary staging.")

    pipe = QgsRasterPipe()
    if not pipe.set(provider_clone):
        raise RuntimeError("Could not initialize a raster pipe for temporary staging.")

    fd, temp_path = tempfile.mkstemp(prefix="autocrs_source_", suffix=".tif")
    os.close(fd)

    writer = QgsRasterFileWriter(temp_path)
    if hasattr(writer, "setOutputProviderKey"):
        writer.setOutputProviderKey("gdal")
    if hasattr(writer, "setOutputFormat"):
        writer.setOutputFormat("GTiff")

    transform_context = (
        context.transformContext()
        if context is not None and hasattr(context, "transformContext")
        else QgsProject.instance().transformContext()
    )
    target_extent = extent if _extent_is_usable(extent) else layer.extent()
    output_width = layer.width()
    output_height = layer.height()
    pixel_size_x, pixel_size_y = _pixel_size(layer)
    pixel_size_x = abs(pixel_size_x) if pixel_size_x is not None else None
    pixel_size_y = abs(pixel_size_y) if pixel_size_y is not None else None
    if target_extent is not None and _extent_is_usable(target_extent) and pixel_size_x and pixel_size_y:
        extent_width = target_extent.width() if hasattr(target_extent, "width") else None
        extent_height = target_extent.height() if hasattr(target_extent, "height") else None
        if extent_width is not None and extent_height is not None:
            output_width = max(1, int(round(extent_width / pixel_size_x)))
            output_height = max(1, int(round(extent_height / pixel_size_y)))
    result = writer.writeRaster(
        pipe,
        output_width,
        output_height,
        target_extent,
        layer.crs(),
        transform_context,
    )
    no_error = getattr(QgsRasterFileWriter, "NoError", 0)
    if result != no_error:
        raise RuntimeError(f"Could not stage raster input for GDAL processing (writer error code {result}).")

    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(f"Staged non-file raster input to local GeoTIFF for GDAL compatibility: {temp_path}")
    return temp_path


def _stage_raster_via_native_rastercalc(layer, context, feedback, *, extent=None) -> str:
    _require_processing("_stage_raster_via_native_rastercalc")
    output_value = temporary_output_value(
        None,
        QgsProcessing.TEMPORARY_OUTPUT if QgsProcessing is not None else "TEMPORARY_OUTPUT",
    )
    alg_params = {
        "CELL_SIZE": None,
        "CRS": layer.crs(),
        "EXPRESSION": '"A@1"',
        "EXTENT": extent if _extent_is_usable(extent) else layer.extent(),
        "LAYERS": layer,
        "OUTPUT": output_value,
    }
    result = processing.run(
        "native:modelerrastercalc",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    staged_output = result["OUTPUT"]
    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(
            f"Staged raster input via QGIS raster calculator for provider compatibility: {staged_output}"
        )
    return staged_output


def _stage_nonlocal_raster_input(layer, context, feedback, *, extent=None, intro_message: str | None = None):
    if intro_message and feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(intro_message)
    try:
        return _write_layer_to_temp_geotiff(layer, context, feedback, extent=extent)
    except RuntimeError as exc:
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo(
                "Direct temporary GeoTIFF staging failed, so RegenGIS is retrying through QGIS raster calculator with the working extent. "
                f"Details: {exc}"
            )
        return _stage_raster_via_native_rastercalc(layer, context, feedback, extent=extent)


def _materialize_gdal_input(layer, context, feedback, requested_extent=None, requested_extent_crs=None):
    provider_type = _layer_provider_type(layer)
    source = _layer_source(layer)
    if provider_type == "wcs":
        extent = _resolve_materialization_extent(
            layer,
            requested_extent=requested_extent,
            requested_extent_crs=requested_extent_crs,
            feedback=feedback,
        )
        return _stage_nonlocal_raster_input(
            layer,
            context,
            feedback,
            extent=extent,
            intro_message=(
                "Input raster comes from a WCS provider, so RegenGIS is staging a local GeoTIFF before GDAL processing and limiting the request to the working extent when possible."
            ),
        )

    if _is_probably_local_raster_source(source):
        return layer

    extent = _resolve_materialization_extent(
        layer,
        requested_extent=requested_extent,
        requested_extent_crs=requested_extent_crs,
        feedback=feedback,
    )
    return _stage_nonlocal_raster_input(
        layer,
        context,
        feedback,
        extent=extent,
        intro_message=(
            f"Input raster provider '{provider_type or 'unknown'}' is not a direct local file source, so RegenGIS is staging a local GeoTIFF before GDAL processing."
        ),
    )


def _copy_raster_output(layer, context, feedback, output):
    _require_processing("_copy_raster_output")
    output_value = temporary_output_value(output, QgsProcessing.TEMPORARY_OUTPUT if QgsProcessing is not None else "TEMPORARY_OUTPUT")
    layer_crs = layer.crs() if layer is not None and hasattr(layer, "crs") else None
    target_crs = layer_crs if layer_crs is not None and hasattr(layer_crs, "isValid") and layer_crs.isValid() else None
    alg_params = {
        "COPY_SUBDATASETS": False,
        "DATA_TYPE": 0,
        "EXTRA": "",
        "INPUT": layer,
        "NODATA": None,
        "OPTIONS": "",
        "OUTPUT": output_value,
        "TARGET_CRS": target_crs,
    }
    result = processing.run(
        "gdal:translate",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    return result["OUTPUT"]


def _reproject_raster_output(layer, context, feedback, output, *, target_crs=None):
    _require_processing("_reproject_raster_output")
    output_value = temporary_output_value(output, QgsProcessing.TEMPORARY_OUTPUT if QgsProcessing is not None else "TEMPORARY_OUTPUT")
    alg_params = {
        "DATA_TYPE": 0,
        "EXTRA": "",
        "INPUT": layer,
        "MULTITHREADING": False,
        "NODATA": None,
        "OPTIONS": "",
        "OUTPUT": output_value,
        "RESAMPLING": 0,
        "SOURCE_CRS": None,
        "TARGET_CRS": target_crs,
        "TARGET_EXTENT": None,
        "TARGET_EXTENT_CRS": None,
        "TARGET_RESOLUTION": None,
    }
    result = processing.run(
        "gdal:warpreproject",
        alg_params,
        context=context,
        feedback=feedback,
        is_child_algorithm=True,
    )
    return result["OUTPUT"]


def _output_requested(output) -> bool:
    return output not in (None, "")


def _materialize_input_if_needed(
    layer,
    context,
    feedback,
    *,
    output,
    analysis_extent=None,
    analysis_extent_crs=None,
):
    if not _output_requested(output):
        return layer
    return _materialize_gdal_input(
        layer,
        context,
        feedback,
        requested_extent=analysis_extent,
        requested_extent_crs=analysis_extent_crs,
    )


def _copy_output_if_requested(layer, context, feedback, output):
    if not _output_requested(output):
        return layer
    return _copy_raster_output(layer, context, feedback, output)


def _build_prepared_raster(
    layer_or_path,
    *,
    source_crs_authid,
    target_crs_authid,
    was_reprojected,
    recommendation,
    pixel_size_x,
    pixel_size_y,
) -> PreparedRaster:
    return PreparedRaster(
        layer_or_path=layer_or_path,
        source_crs_authid=source_crs_authid,
        target_crs_authid=target_crs_authid,
        was_reprojected=was_reprojected,
        recommendation=recommendation,
        pixel_size_x=pixel_size_x,
        pixel_size_y=pixel_size_y,
    )


def prepare_raster_for_analysis(
    layer,
    context,
    feedback,
    target_crs=None,
    auto_select=True,
    output=None,
    analysis_extent=None,
    analysis_extent_crs=None,
) -> PreparedRaster:
    _require_qgis("prepare_raster_for_analysis")
    _require_processing("prepare_raster_for_analysis")

    if layer is None:
        raise ValueError("Layer is required.")

    recommendation = recommend_analysis_crs_for_layer(layer, feedback=feedback)
    target_crs_object = _target_crs_from_input(target_crs, recommendation)
    source_crs = layer.crs()
    source_authid = source_crs.authid() or ""
    target_authid = target_crs_object.authid() or recommendation.authid
    pixel_size_x, pixel_size_y = _pixel_size(layer)
    output_requested = _output_requested(output)

    if not auto_select and target_crs is None:
        prepared_output = _copy_output_if_requested(
            _materialize_input_if_needed(
                layer,
                context,
                feedback,
                output=output,
                analysis_extent=analysis_extent,
                analysis_extent_crs=analysis_extent_crs,
            ),
            context,
            feedback,
            output,
        )
        if feedback is not None and hasattr(feedback, "pushInfo") and output_requested:
            feedback.pushInfo(
                "Automatic CRS selection is disabled and no manual target CRS was provided, so RegenGIS created an output copy in the source CRS."
            )
        return _build_prepared_raster(
            prepared_output,
            source_crs_authid=source_authid,
            target_crs_authid=source_authid,
            was_reprojected=False,
            recommendation=recommendation,
            pixel_size_x=pixel_size_x,
            pixel_size_y=pixel_size_y,
        )

    if not layer_needs_reprojection(layer, target_crs_object):
        if feedback is not None and hasattr(feedback, "pushInfo"):
            feedback.pushInfo(f"Input raster already uses the selected analysis CRS ({target_authid}).")
        prepared_output = _copy_output_if_requested(
            _materialize_input_if_needed(
                layer,
                context,
                feedback,
                output=output,
                analysis_extent=analysis_extent,
                analysis_extent_crs=analysis_extent_crs,
            ),
            context,
            feedback,
            output,
        )
        if feedback is not None and hasattr(feedback, "pushInfo") and output_requested:
            feedback.pushInfo("Creating an analysis-ready output copy without reprojection.")
        return _build_prepared_raster(
            prepared_output,
            source_crs_authid=source_authid,
            target_crs_authid=target_authid,
            was_reprojected=False,
            recommendation=recommendation,
            pixel_size_x=pixel_size_x,
            pixel_size_y=pixel_size_y,
        )

    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(
            f"Preparing raster for analysis by reprojecting from {source_authid or 'unknown CRS'} to {target_authid}."
        )

    prepared_output = _reproject_raster_output(
        _materialize_gdal_input(
            layer,
            context,
            feedback,
            requested_extent=analysis_extent,
            requested_extent_crs=analysis_extent_crs,
        ),
        context,
        feedback,
        output,
        target_crs=target_crs_object,
    )

    return _build_prepared_raster(
        prepared_output,
        source_crs_authid=source_authid,
        target_crs_authid=target_authid,
        was_reprojected=True,
        recommendation=recommendation,
        pixel_size_x=pixel_size_x,
        pixel_size_y=pixel_size_y,
    )
