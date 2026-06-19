"""Pure-Python heuristics for choosing a metric CRS from a WGS84 extent."""

from __future__ import annotations

from dataclasses import dataclass
import math


UPS_NORTH_EPSG = 32661
UPS_SOUTH_EPSG = 32761

POLAR_NORTH_LAT = 84.0
POLAR_SOUTH_LAT = -80.0
LOCAL_UTM_MAX_LONGITUDE_SPAN = 7.0
LOCAL_UTM_MAX_LATITUDE_SPAN = 8.0


@dataclass(frozen=True)
class NationalGridSpec:
    epsg: int
    identifier: str
    description: str
    proj4: str
    west: float
    south: float
    east: float
    north: float

    @property
    def bbox_area(self) -> float:
        return max(0.0, self.east - self.west) * max(0.0, self.north - self.south)


NATIONAL_GRID_SPECS = (
    NationalGridSpec(
        epsg=28992,
        identifier="EPSG:28992",
        description="Amersfoort / RD New",
        proj4="+proj=sterea +lat_0=52.1561605555556 +lon_0=5.38763888888889 +k=0.9999079 +x_0=155000 +y_0=463000 +ellps=bessel +units=m +no_defs +type=crs",
        west=3.2,
        south=50.75,
        east=7.22,
        north=53.7,
    ),
    NationalGridSpec(
        epsg=3812,
        identifier="EPSG:3812",
        description="ETRS89 / Belgian Lambert 2008",
        proj4="+proj=lcc +lat_0=50.797815 +lon_0=4.35921583333333 +lat_1=49.8333333333333 +lat_2=51.1666666666667 +x_0=649328 +y_0=665262 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs +type=crs",
        west=2.5,
        south=49.5,
        east=6.4,
        north=51.51,
    ),
    NationalGridSpec(
        epsg=2056,
        identifier="EPSG:2056",
        description="CH1903+ / LV95",
        proj4="+proj=somerc +lat_0=46.9524055555556 +lon_0=7.43958333333333 +k_0=1 +x_0=2600000 +y_0=1200000 +ellps=bessel +towgs84=674.374,15.056,405.346,0,0,0,0 +units=m +no_defs +type=crs",
        west=5.95,
        south=45.81,
        east=10.5,
        north=47.81,
    ),
    NationalGridSpec(
        epsg=29903,
        identifier="EPSG:29903",
        description="TM75 / Irish Grid",
        proj4="+proj=tmerc +lat_0=53.5 +lon_0=-8 +k=1.000035 +x_0=200000 +y_0=250000 +a=6377340.189 +rf=299.3249646 +units=m +no_defs +type=crs",
        west=-10.56,
        south=51.39,
        east=-5.34,
        north=55.43,
    ),
    NationalGridSpec(
        epsg=27700,
        identifier="EPSG:27700",
        description="OSGB36 / British National Grid",
        proj4="+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 +x_0=400000 +y_0=-100000 +ellps=airy +units=m +no_defs +type=crs",
        west=-9.01,
        south=49.75,
        east=2.01,
        north=61.01,
    ),
    NationalGridSpec(
        epsg=2154,
        identifier="EPSG:2154",
        description="RGF93 v1 / Lambert-93",
        proj4="+proj=lcc +lat_0=46.5 +lon_0=3 +lat_1=49 +lat_2=44 +x_0=700000 +y_0=6600000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs +type=crs",
        west=-9.86,
        south=41.15,
        east=10.38,
        north=51.56,
    ),
)


@dataclass(frozen=True)
class Extent:
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def latitude_min(self) -> float:
        return min(self.ymin, self.ymax)

    @property
    def latitude_max(self) -> float:
        return max(self.ymin, self.ymax)

    @property
    def latitude_span(self) -> float:
        return abs(self.ymax - self.ymin)

    @property
    def longitude_interval(self) -> tuple[float, float]:
        start = normalize_longitude(self.xmin)
        end = normalize_longitude(self.xmax)
        if end < start:
            end += 360.0
        return start, end

    @property
    def longitude_span(self) -> float:
        start, end = self.longitude_interval
        return end - start

    @property
    def center_lon(self) -> float:
        start, end = self.longitude_interval
        center = start + ((end - start) / 2.0)
        return normalize_longitude_for_zone(center)

    @property
    def center_lat(self) -> float:
        return (self.latitude_min + self.latitude_max) / 2.0


@dataclass(frozen=True)
class MetricCrsChoice:
    strategy: str
    identifier: str
    description: str
    proj4: str
    epsg: int | None

    @property
    def is_utm_or_ups(self) -> bool:
        return self.strategy in {"utm", "ups"}


def normalize_longitude(lon: float) -> float:
    normalized = ((lon + 180.0) % 360.0) - 180.0
    if normalized == -180.0 and lon > 0.0:
        return 180.0
    return normalized


def normalize_longitude_for_zone(lon: float) -> float:
    if lon >= 180.0:
        return math.nextafter(180.0, 0.0)
    if lon < -180.0:
        return normalize_longitude(lon)
    return lon


def utm_zone_from_longitude(lon: float) -> int:
    lon = normalize_longitude_for_zone(lon)
    zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    return max(1, min(60, zone))


def utm_epsg(lon: float, lat: float) -> int | None:
    if lat < POLAR_SOUTH_LAT or lat > POLAR_NORTH_LAT:
        return None
    zone = utm_zone_from_longitude(lon)
    return (32600 if lat >= 0.0 else 32700) + zone


def utm_description(zone: int, north: bool) -> str:
    return f"WGS 84 / UTM zone {zone}{'N' if north else 'S'}"


def ups_description(north: bool) -> str:
    return f"WGS 84 / UPS {'North' if north else 'South'}"


def utm_proj4(zone: int, north: bool) -> str:
    south_flag = "" if north else " +south"
    return f"+proj=utm +zone={zone}{south_flag} +datum=WGS84 +units=m +no_defs +type=crs"


def custom_local_metric_proj(lon: float, lat: float) -> str:
    return (
        f"+proj=aeqd +lat_0={lat:.8f} +lon_0={lon:.8f} "
        "+datum=WGS84 +units=m +no_defs +type=crs"
    )


def _extent_within_bbox(extent: Extent, west: float, south: float, east: float, north: float) -> bool:
    return (
        extent.longitude_span <= 180.0
        and extent.xmin >= west
        and extent.xmax <= east
        and extent.latitude_min >= south
        and extent.latitude_max <= north
    )


def _bbox_center_distance(extent: Extent, spec: NationalGridSpec) -> float:
    spec_center_lon = (spec.west + spec.east) / 2.0
    spec_center_lat = (spec.south + spec.north) / 2.0
    return math.hypot(extent.center_lon - spec_center_lon, extent.center_lat - spec_center_lat)


def _best_matching_national_grid(extent: Extent) -> NationalGridSpec | None:
    candidates = [
        spec for spec in NATIONAL_GRID_SPECS
        if _extent_within_bbox(extent, spec.west, spec.south, spec.east, spec.north)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda spec: (_bbox_center_distance(extent, spec), spec.bbox_area, spec.identifier))


def choose_metric_crs(extent: Extent) -> MetricCrsChoice:
    center_lon = extent.center_lon
    center_lat = extent.center_lat

    if extent.latitude_max >= POLAR_NORTH_LAT:
        return MetricCrsChoice(
            strategy="ups",
            identifier=f"EPSG:{UPS_NORTH_EPSG}",
            description=ups_description(True),
            proj4="+proj=ups +lat_0=90 +datum=WGS84 +units=m +no_defs +type=crs",
            epsg=UPS_NORTH_EPSG,
        )

    if extent.latitude_min <= POLAR_SOUTH_LAT:
        return MetricCrsChoice(
            strategy="ups",
            identifier=f"EPSG:{UPS_SOUTH_EPSG}",
            description=ups_description(False),
            proj4="+proj=ups +lat_0=-90 +datum=WGS84 +units=m +no_defs +type=crs",
            epsg=UPS_SOUTH_EPSG,
        )

    national_grid = _best_matching_national_grid(extent)
    if national_grid is not None:
        return MetricCrsChoice(
            strategy="national_grid",
            identifier=national_grid.identifier,
            description=national_grid.description,
            proj4=national_grid.proj4,
            epsg=national_grid.epsg,
        )

    if (
        extent.longitude_span <= LOCAL_UTM_MAX_LONGITUDE_SPAN
        and extent.latitude_span <= LOCAL_UTM_MAX_LATITUDE_SPAN
    ):
        epsg = utm_epsg(center_lon, center_lat)
        if epsg is None:
            epsg = (32600 if center_lat >= 0.0 else 32700) + utm_zone_from_longitude(center_lon)
        zone = epsg % 100
        north = center_lat >= 0.0
        return MetricCrsChoice(
            strategy="utm",
            identifier=f"EPSG:{epsg}",
            description=utm_description(zone, north),
            proj4=utm_proj4(zone, north),
            epsg=epsg,
        )

    return MetricCrsChoice(
        strategy="custom_local_metric",
        identifier="CUSTOM:LOCAL_AEQD",
        description="Custom local metric projection (azimuthal equidistant centered on extent)",
        proj4=custom_local_metric_proj(center_lon, center_lat),
        epsg=None,
    )
