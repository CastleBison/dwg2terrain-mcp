from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "auto_detect_layers": True,
    "include_layers": [],
    "exclude_layers": [],
    "include_entity_types": ["LWPOLYLINE", "POLYLINE", "SPLINE"],
    "min_vertices": 2,
    "flatten_splines": True,
    "spline_segments": 32,
    "require_layer_match": False,
    "allow_zero_elevation": False,
}

DEFAULT_MESH_CONFIG = {
    "method": "grid",
    "densify_max_segment_length": 10.0,
    "xy_tolerance": 0.000001,
    "grid_spacing": 3.0,
    "grid_mask_mode": "hull",
    "grid_support_distance_factor": 4.5,
    "grid_fill_nearest": True,
    "small_hole_fill_passes": 2,
    "small_hole_min_neighbors": 5,
    "smoothing_passes": 2,
    "smoothing_blend": 0.3,
    "max_cell_z_levels": 4.0,
    "max_edge_factor": 6.0,
    "centroid_distance_factor": 1.8,
    "min_triangle_area": 0.01,
    "absolute_max_edge_length": 0.0,
}

HIGHRES_MESH_CONFIG = {
    "method": "grid",
    "densify_max_segment_length": 5.0,
    "xy_tolerance": 0.000001,
    "grid_spacing": 1.5,
    "grid_mask_mode": "hull",
    "grid_support_distance_factor": 4.5,
    "grid_fill_nearest": True,
    "small_hole_fill_passes": 2,
    "small_hole_min_neighbors": 5,
    "smoothing_passes": 1,
    "smoothing_blend": 0.2,
    "max_cell_z_levels": 4.0,
    "max_edge_factor": 6.0,
    "centroid_distance_factor": 1.8,
    "min_triangle_area": 0.01,
    "absolute_max_edge_length": 0.0,
}

ENV_ODA_KEY = "ODA_FILE_CONVERTER_EXE"


def load_config(config_path: str | None) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if not config_path:
        return config
    path = Path(config_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    config.update(payload)
    return config


def resolve_oda_hint(cli_value: str | None) -> str | None:
    if cli_value:
        return cli_value
    return os.environ.get(ENV_ODA_KEY)


def merge_config(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    config = dict(base)
    if override:
        config.update(override)
    return config
