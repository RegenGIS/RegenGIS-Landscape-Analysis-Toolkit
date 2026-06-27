"""Small runtime-environment helpers for QGIS/GDAL integration."""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
import os


EnvMapping = MutableMapping[str, str]


def proj_lib_candidate_from_gdal_data(gdal_data: str | None) -> str | None:
    """Infer a plausible PROJ data directory from GDAL_DATA.

    Returns None when no safe sibling path can be inferred.
    """
    if not gdal_data:
        return None

    gdal_path = Path(gdal_data)
    gdal_index = next(
        (index for index, part in enumerate(gdal_path.parts) if part.lower() == "gdal"),
        None,
    )
    if gdal_index is None:
        return None

    candidate = Path(*gdal_path.parts[:gdal_index], "proj", *gdal_path.parts[gdal_index + 1 :])
    return str(candidate)


def ensure_proj_runtime_env(env: EnvMapping | None = None) -> str | None:
    """Set PROJ_LIB from GDAL_DATA when QGIS/GDAL is misconfigured.

    Returns the effective PROJ_LIB value when present or inferred, otherwise None.
    """
    env = os.environ if env is None else env

    existing_proj_lib = env.get("PROJ_LIB")
    if existing_proj_lib:
        return existing_proj_lib

    inferred_proj_lib = proj_lib_candidate_from_gdal_data(env.get("GDAL_DATA"))
    if not inferred_proj_lib:
        return None

    env["PROJ_LIB"] = inferred_proj_lib
    return inferred_proj_lib
