"""AutoCRS core package for the RegenGIS processing plugin."""

from .heuristics import Extent, MetricCrsChoice, NationalGridSpec, choose_metric_crs
from .prepare import PreparedRaster, prepare_raster_for_analysis, recommend_analysis_crs_for_layer
from .selector import AutoCrsRecommendation, qgis_crs_from_recommendation, recommend_metric_crs_for_extent, recommend_metric_crs_for_layer

__all__ = [
    "AutoCrsRecommendation",
    "Extent",
    "MetricCrsChoice",
    "NationalGridSpec",
    "PreparedRaster",
    "choose_metric_crs",
    "prepare_raster_for_analysis",
    "qgis_crs_from_recommendation",
    "recommend_analysis_crs_for_layer",
    "recommend_metric_crs_for_extent",
    "recommend_metric_crs_for_layer",
]
