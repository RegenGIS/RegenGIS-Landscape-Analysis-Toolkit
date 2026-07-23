"""Small helpers for temporary analysis outputs and labels."""

from __future__ import annotations

from pathlib import Path
import re


def slugify_for_layer_name(value: str, *, fallback: str = "autocrs") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (value or "")).strip("_")
    return cleaned or fallback


def stable_temporary_layer_name(base_name: str, suffix: str) -> str:
    base = slugify_for_layer_name(base_name)
    suffix_token = slugify_for_layer_name(suffix)
    return f"{base}_{suffix_token}"


def derived_output_basename(source_name: str, suffix: str, extension: str = "") -> str:
    stem = Path(source_name or "layer").stem
    name = stable_temporary_layer_name(stem, suffix)
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return f"{name}{extension}"


def temporary_output_value(output, temporary_output_marker):
    return output if output not in (None, "") else temporary_output_marker
