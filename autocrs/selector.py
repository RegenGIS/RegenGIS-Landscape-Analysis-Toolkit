"""QGIS-aware catalog-first CRS selector for RegenGIS AutoCRS."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

from .heuristics import Extent, MetricCrsChoice, choose_metric_crs

try:
    from qgis.core import Qgis, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject
except ModuleNotFoundError as exc:  # pragma: no cover - allows import outside QGIS
    if not getattr(exc, "name", "").startswith("qgis"):
        raise
    Qgis = None
    QgsCoordinateReferenceSystem = None
    QgsCoordinateTransform = None
    QgsPointXY = None
    QgsProject = None


@dataclass(frozen=True)
class AutoCrsRecommendation:
    authid: str
    description: str
    proj4: str
    epsg: int | None
    strategy: str
    distortion_ppm: float
    is_utm_or_ups: bool


@dataclass(frozen=True)
class CatalogCandidate:
    authid: str
    description: str
    proj4: str
    epsg: int | None
    coverage_rank: int
    deprecated_rank: int
    area_size: float
    specificity_rank: int
    preferred_national_grid_rank: int
    distortion_ppm: float
    is_utm_or_ups: bool

    @property
    def rank_key(self) -> tuple:
        return (
            self.coverage_rank,
            self.deprecated_rank,
            self.specificity_rank,
            self.preferred_national_grid_rank,
            self.area_size,
            self.distortion_ppm,
            self.is_utm_or_ups,
            self.authid,
        )


@dataclass(frozen=True)
class CatalogIndexEntry:
    srs_id: int
    authid: str
    description: str
    deprecated_rank: int
    area_size: float
    specificity_rank: int
    is_utm_or_ups: bool
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True)
class CatalogPreCandidate:
    srs_id: int
    authid: str
    description: str
    deprecated_rank: int
    area_size: float
    specificity_rank: int
    preferred_national_grid_rank: int
    is_utm_or_ups: bool
    coverage_rank: int


_CATALOG_INDEX_CACHE: list[CatalogIndexEntry] | None = None
_CATALOG_CACHE_VERSION = 1
_CATALOG_PREFILTER_LIMIT = 8
_CATALOG_DISTORTION_LIMIT = 4


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _cache_dir() -> Path:
    return _plugin_root() / ".autocrs-cache"


def _sanitize_cache_token(value: str) -> str:
    token = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in (value or "unknown"))
    return token or "unknown"


def _qgis_version_token() -> str:
    if Qgis is None:
        return "unknown"
    for attr in ("QGIS_VERSION", "QGIS_DEV_VERSION"):
        value = getattr(Qgis, attr, None)
        if isinstance(value, str) and value:
            return _sanitize_cache_token(value)
    version_fn = getattr(Qgis, "version", None)
    if callable(version_fn):
        try:
            value = version_fn()
        except Exception:
            value = None
        if isinstance(value, str) and value:
            return _sanitize_cache_token(value)
    return "unknown"


def _catalog_cache_filename() -> str:
    return f"qgis-crs-index-v{_CATALOG_CACHE_VERSION}-{_qgis_version_token()}.json"


def _catalog_cache_identity() -> dict:
    return {
        "version": _CATALOG_CACHE_VERSION,
        "qgis_version": _qgis_version_token(),
    }


def _catalog_cache_file() -> Path:
    return _cache_dir() / _catalog_cache_filename()


def _catalog_index_entry_to_dict(entry: CatalogIndexEntry) -> dict:
    return {
        "srs_id": entry.srs_id,
        "authid": entry.authid,
        "description": entry.description,
        "deprecated_rank": entry.deprecated_rank,
        "area_size": entry.area_size,
        "specificity_rank": entry.specificity_rank,
        "is_utm_or_ups": entry.is_utm_or_ups,
        "west": entry.west,
        "south": entry.south,
        "east": entry.east,
        "north": entry.north,
    }


def _catalog_index_entry_from_dict(payload: dict) -> CatalogIndexEntry:
    return CatalogIndexEntry(
        srs_id=int(payload["srs_id"]),
        authid=str(payload["authid"]),
        description=str(payload["description"]),
        deprecated_rank=int(payload["deprecated_rank"]),
        area_size=float(payload["area_size"]),
        specificity_rank=int(payload["specificity_rank"]),
        is_utm_or_ups=bool(payload["is_utm_or_ups"]),
        west=float(payload["west"]),
        south=float(payload["south"]),
        east=float(payload["east"]),
        north=float(payload["north"]),
    )


def _load_catalog_index_cache_status() -> tuple[list[CatalogIndexEntry] | None, dict]:
    cache_file = _catalog_cache_file()
    expected_identity = _catalog_cache_identity()

    if not cache_file.exists():
        return None, {"reason": "missing", "path": cache_file}

    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None, {"reason": "unreadable", "path": cache_file}

    if not isinstance(payload, dict):
        return None, {"reason": "invalid-payload", "path": cache_file}

    if payload.get("version") != expected_identity["version"]:
        return None, {"reason": "version-mismatch", "path": cache_file}

    if payload.get("qgis_version") != expected_identity["qgis_version"]:
        return None, {"reason": "qgis-version-mismatch", "path": cache_file}

    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries:
        return None, {"reason": "empty", "path": cache_file}

    try:
        parsed_entries = [_catalog_index_entry_from_dict(entry) for entry in entries]
    except Exception:
        return None, {"reason": "invalid-entry", "path": cache_file}

    return parsed_entries, {"reason": "loaded", "path": cache_file}


def _catalog_cache_rebuild_message(status: dict) -> str:
    reason = status.get("reason")
    if reason == "version-mismatch":
        why = "the cache schema version no longer matches this plugin build"
    elif reason == "qgis-version-mismatch":
        why = "the saved cache was built for a different QGIS version"
    elif reason in {"unreadable", "invalid-payload", "invalid-entry", "empty"}:
        why = "the saved cache is not usable"
    else:
        why = "no saved cache was found"
    return (
        "Building CRS catalog cache now because "
        f"{why}. This is expected after a fresh install or QGIS/plugin update and should only happen once."
    )


def _save_catalog_index_cache(entries: list[CatalogIndexEntry]) -> None:
    payload = {
        **_catalog_cache_identity(),
        "entries": [_catalog_index_entry_to_dict(entry) for entry in entries],
    }
    serialized = json.dumps(payload, separators=(",", ":"))
    cache_file = _catalog_cache_file()
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(serialized, encoding="utf-8")
    except Exception:
        return


def _safe_bbox_area(west: float, south: float, east: float, north: float) -> float:
    return max(0.0, east - west) * max(0.0, north - south)


class _BoundsProxy:
    def __init__(self, west: float, south: float, east: float, north: float):
        self._west = west
        self._south = south
        self._east = east
        self._north = north

    def xMinimum(self):
        return self._west

    def yMinimum(self):
        return self._south

    def xMaximum(self):
        return self._east

    def yMaximum(self):
        return self._north


def _extent_matches_bounds(extent: Extent, bounds) -> int | None:
    west = bounds.xMinimum()
    south = bounds.yMinimum()
    east = bounds.xMaximum()
    north = bounds.yMaximum()

    contains = (
        extent.longitude_span <= 180.0
        and extent.xmin >= west
        and extent.xmax <= east
        and extent.latitude_min >= south
        and extent.latitude_max <= north
    )
    if contains:
        return 0

    overlaps = not (
        extent.xmax < west
        or extent.xmin > east
        or extent.latitude_max < south
        or extent.latitude_min > north
    )
    if overlaps:
        return 1
    return None


def _specificity_rank(description: str) -> int:
    name = (description or "").lower()
    if any(token in name for token in ("national grid", "lambert", "rd new", "irish grid", "lv95")):
        return 0
    if "utm" in name or "ups" in name:
        return 2
    return 1


def _preferred_national_grid_authid(extent: Extent) -> str | None:
    choice = choose_metric_crs(extent)
    if choice.strategy != "national_grid":
        return None
    return choice.identifier


def _require_qgis(function_name: str) -> None:
    if QgsCoordinateReferenceSystem is None or QgsCoordinateTransform is None or QgsProject is None:
        raise RuntimeError(f"{function_name} requires a QGIS runtime with PyQGIS available.")


def _extent_from_qgis_rectangle(extent) -> Extent:
    return Extent(extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())


def _extent_from_wgs84_input(extent_wgs84) -> tuple[Extent, object | None]:
    if isinstance(extent_wgs84, Extent):
        return extent_wgs84, None
    if hasattr(extent_wgs84, "xMinimum") and hasattr(extent_wgs84, "xMaximum"):
        return _extent_from_qgis_rectangle(extent_wgs84), extent_wgs84
    raise TypeError("extent_wgs84 must be an AutoCRS Extent or a QGIS rectangle-like object.")


def _scale_factor_with_transform(xform, lon: float, lat: float) -> float:
    center = xform.transform(QgsPointXY(lon, lat))
    delta = 0.001
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    north = xform.transform(QgsPointXY(lon, lat + delta))
    south = xform.transform(QgsPointXY(lon, lat - delta))
    east = xform.transform(QgsPointXY(lon + delta / cos_lat, lat))
    west = xform.transform(QgsPointXY(lon - delta / cos_lat, lat))
    d_n = math.hypot(north.x() - center.x(), north.y() - center.y())
    d_s = math.hypot(south.x() - center.x(), south.y() - center.y())
    d_e = math.hypot(east.x() - center.x(), east.y() - center.y())
    d_w = math.hypot(west.x() - center.x(), west.y() - center.y())
    ref = delta * 111000.0
    return abs(((d_n + d_s + d_e + d_w) / 4.0) / ref - 1.0)


def _crs_transform_from_wgs84(crs):
    _require_qgis("_crs_transform_from_wgs84")
    wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
    return QgsCoordinateTransform(wgs84, crs, QgsProject.instance())


def _max_scale_factor_over_extent_with_transform(xform, extent_wgs84) -> float:
    helper_extent, qgis_extent = _extent_from_wgs84_input(extent_wgs84)
    if qgis_extent is None:
        raise TypeError("Distortion scoring requires a QGIS rectangle-like extent.")

    cx = helper_extent.center_lon
    cy = helper_extent.center_lat
    lons = [cx, qgis_extent.xMinimum(), qgis_extent.xMaximum(), qgis_extent.xMinimum(), qgis_extent.xMaximum()]
    lats = [cy, qgis_extent.yMinimum(), qgis_extent.yMinimum(), qgis_extent.yMaximum(), qgis_extent.yMaximum()]
    return max(_scale_factor_with_transform(xform, lon, lat) for lon, lat in zip(lons, lats))


def _epsg_from_authid(authid: str) -> int | None:
    if not authid.startswith("EPSG:"):
        return None
    try:
        return int(authid.split(":", 1)[1])
    except Exception:
        return None


def _is_metric_projected_crs(crs) -> bool:
    if not crs.isValid() or Qgis is None:
        return False
    try:
        if crs.type() != Qgis.CrsType.Projected:
            return False
        if crs.mapUnits() != Qgis.DistanceUnit.Meters:
            return False
    except Exception:
        return False
    return True


def _proj_string_for_crs(crs) -> str:
    if hasattr(crs, "toProj"):
        return crs.toProj()
    if hasattr(crs, "toProj4"):
        return crs.toProj4()
    return ""


def _choice_to_qgis_crs(choice: MetricCrsChoice):
    _require_qgis("_choice_to_qgis_crs")
    if choice.epsg is not None:
        crs = QgsCoordinateReferenceSystem.fromEpsgId(choice.epsg)
        if crs.isValid():
            return crs
        raise RuntimeError(f"Failed to construct EPSG:{choice.epsg}.")

    crs = QgsCoordinateReferenceSystem()
    if hasattr(crs, "createFromProj"):
        crs.createFromProj(choice.proj4)
        if crs.isValid():
            return crs
    if hasattr(QgsCoordinateReferenceSystem, "fromProj"):
        crs = QgsCoordinateReferenceSystem.fromProj(choice.proj4)
        if crs.isValid():
            return crs
    raise RuntimeError("QGIS cannot construct a custom CRS from PROJ.")


def qgis_crs_from_recommendation(recommendation: AutoCrsRecommendation):
    return _choice_to_qgis_crs(
        MetricCrsChoice(
            strategy=recommendation.strategy,
            identifier=recommendation.authid,
            description=recommendation.description,
            proj4=recommendation.proj4,
            epsg=recommendation.epsg,
        )
    )


def _catalog_index(feedback=None) -> list[CatalogIndexEntry]:
    global _CATALOG_INDEX_CACHE
    _require_qgis("_catalog_index")

    if _CATALOG_INDEX_CACHE is not None:
        return _CATALOG_INDEX_CACHE

    cached_entries, cache_status = _load_catalog_index_cache_status()
    if cached_entries is not None:
        _CATALOG_INDEX_CACHE = cached_entries
        return cached_entries

    if feedback is not None and hasattr(feedback, "pushInfo"):
        feedback.pushInfo(_catalog_cache_rebuild_message(cache_status))

    entries = []
    for srs_id in QgsCoordinateReferenceSystem.validSrsIds():
        crs = QgsCoordinateReferenceSystem.fromSrsId(srs_id)
        if not _is_metric_projected_crs(crs):
            continue

        authid = crs.authid() or ""
        if not authid.startswith("EPSG:"):
            continue

        try:
            bounds = crs.bounds()
        except Exception:
            continue

        try:
            area_size = _safe_bbox_area(bounds.xMinimum(), bounds.yMinimum(), bounds.xMaximum(), bounds.yMaximum())
        except Exception:
            area_size = float("inf")

        description = crs.description() or ""
        entries.append(
            CatalogIndexEntry(
                srs_id=srs_id,
                authid=authid,
                description=description,
                deprecated_rank=1 if crs.isDeprecated() else 0,
                area_size=area_size,
                specificity_rank=_specificity_rank(description),
                is_utm_or_ups=("utm" in description.lower() or "ups" in description.lower()),
                west=bounds.xMinimum(),
                south=bounds.yMinimum(),
                east=bounds.xMaximum(),
                north=bounds.yMaximum(),
            )
        )

    _CATALOG_INDEX_CACHE = entries
    _save_catalog_index_cache(entries)
    return entries


def _catalog_pre_candidate(
    entry: CatalogIndexEntry,
    helper_extent: Extent,
    preferred_national_grid_authid: str | None = None,
) -> CatalogPreCandidate | None:
    coverage_rank = _extent_matches_bounds(
        helper_extent,
        _BoundsProxy(entry.west, entry.south, entry.east, entry.north),
    )
    if coverage_rank is None:
        return None
    preferred_rank = 1
    if preferred_national_grid_authid is not None and entry.authid == preferred_national_grid_authid:
        preferred_rank = 0
    return CatalogPreCandidate(
        srs_id=entry.srs_id,
        authid=entry.authid,
        description=entry.description,
        deprecated_rank=entry.deprecated_rank,
        area_size=entry.area_size,
        specificity_rank=entry.specificity_rank,
        preferred_national_grid_rank=preferred_rank,
        is_utm_or_ups=entry.is_utm_or_ups,
        coverage_rank=coverage_rank,
    )


def _catalog_candidate_from_pre(pre_candidate: CatalogPreCandidate, extent_wgs84) -> CatalogCandidate | None:
    _require_qgis("_catalog_candidate_from_pre")
    crs = QgsCoordinateReferenceSystem.fromSrsId(pre_candidate.srs_id)
    if not _is_metric_projected_crs(crs):
        return None

    try:
        xform = _crs_transform_from_wgs84(crs)
        distortion_ppm = float(_max_scale_factor_over_extent_with_transform(xform, extent_wgs84)) * 1_000_000.0
    except Exception:
        return None

    return CatalogCandidate(
        authid=pre_candidate.authid,
        description=pre_candidate.description,
        proj4=_proj_string_for_crs(crs),
        epsg=_epsg_from_authid(pre_candidate.authid),
        coverage_rank=pre_candidate.coverage_rank,
        deprecated_rank=pre_candidate.deprecated_rank,
        area_size=pre_candidate.area_size,
        specificity_rank=pre_candidate.specificity_rank,
        preferred_national_grid_rank=pre_candidate.preferred_national_grid_rank,
        distortion_ppm=distortion_ppm,
        is_utm_or_ups=pre_candidate.is_utm_or_ups,
    )


def _candidate_pre_rank_key(candidate: CatalogPreCandidate) -> tuple:
    return (
        candidate.coverage_rank,
        candidate.deprecated_rank,
        candidate.specificity_rank,
        candidate.preferred_national_grid_rank,
        candidate.area_size,
        candidate.authid,
    )


def _select_best_catalog_crs(extent_wgs84, feedback=None) -> CatalogCandidate | None:
    helper_extent, qgis_extent = _extent_from_wgs84_input(extent_wgs84)
    if qgis_extent is None:
        return None

    preferred_national_grid_authid = _preferred_national_grid_authid(helper_extent)
    pre_candidates = []
    for entry in _catalog_index(feedback):
        if feedback is not None and hasattr(feedback, "isCanceled") and feedback.isCanceled():
            return None
        pre_candidate = _catalog_pre_candidate(
            entry,
            helper_extent,
            preferred_national_grid_authid=preferred_national_grid_authid,
        )
        if pre_candidate is not None:
            pre_candidates.append(pre_candidate)

    if not pre_candidates:
        return None

    pre_candidates.sort(key=_candidate_pre_rank_key)
    finalists = pre_candidates[:_CATALOG_PREFILTER_LIMIT]

    candidates = []
    for pre_candidate in finalists:
        candidate = _catalog_candidate_from_pre(pre_candidate, qgis_extent)
        if candidate is not None:
            candidates.append(candidate)
        if len(candidates) >= _CATALOG_DISTORTION_LIMIT:
            break

    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate.rank_key)


def _candidate_to_recommendation(candidate: CatalogCandidate) -> AutoCrsRecommendation:
    strategy = "utm" if candidate.is_utm_or_ups else "catalog_epsg"
    return AutoCrsRecommendation(
        authid=candidate.authid,
        description=candidate.description,
        proj4=candidate.proj4,
        epsg=candidate.epsg,
        strategy=strategy,
        distortion_ppm=candidate.distortion_ppm,
        is_utm_or_ups=candidate.is_utm_or_ups,
    )


def _choice_to_recommendation(choice: MetricCrsChoice, distortion_ppm: float) -> AutoCrsRecommendation:
    return AutoCrsRecommendation(
        authid=choice.identifier,
        description=choice.description,
        proj4=choice.proj4,
        epsg=choice.epsg,
        strategy=choice.strategy,
        distortion_ppm=distortion_ppm,
        is_utm_or_ups=choice.is_utm_or_ups,
    )


def _fallback_recommendation_for_extent(helper_extent: Extent, qgis_extent=None) -> AutoCrsRecommendation:
    choice = choose_metric_crs(helper_extent)
    distortion_ppm = 0.0
    if qgis_extent is not None and QgsCoordinateReferenceSystem is not None:
        try:
            crs = _choice_to_qgis_crs(choice)
            distortion_ppm = float(_max_scale_factor_over_extent_with_transform(_crs_transform_from_wgs84(crs), qgis_extent)) * 1_000_000.0
        except Exception:
            distortion_ppm = 0.0
    return _choice_to_recommendation(choice, distortion_ppm)


def recommend_metric_crs_for_extent(extent_wgs84, feedback=None) -> AutoCrsRecommendation:
    helper_extent, qgis_extent = _extent_from_wgs84_input(extent_wgs84)

    if qgis_extent is not None and QgsCoordinateReferenceSystem is not None:
        catalog_candidate = _select_best_catalog_crs(qgis_extent, feedback)
        if catalog_candidate is not None:
            return _candidate_to_recommendation(catalog_candidate)

    return _fallback_recommendation_for_extent(helper_extent, qgis_extent)


def _layer_wgs84_extent(layer):
    _require_qgis("_layer_wgs84_extent")
    if layer is None:
        raise ValueError("Layer is required.")

    source_crs = layer.crs()
    extent = layer.extent()
    wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)

    if source_crs.authid() == "EPSG:4326":
        return extent

    transform = QgsCoordinateTransform(source_crs, wgs84, QgsProject.instance())
    return transform.transformBoundingBox(extent, handle180Crossover=True)


def recommend_metric_crs_for_layer(layer, feedback=None) -> AutoCrsRecommendation:
    return recommend_metric_crs_for_extent(_layer_wgs84_extent(layer), feedback=feedback)
