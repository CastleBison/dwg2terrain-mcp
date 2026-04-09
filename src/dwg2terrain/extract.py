from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ezdxf.filemanagement import new, readfile

from .scan import scan_dxf


SUPPORTED_TYPES = {"LWPOLYLINE", "POLYLINE", "SPLINE"}


def _lwpolyline_points(entity: Any) -> list[tuple[float, float, float]]:
    elevation = float(entity.dxf.elevation or 0.0)
    return [(float(x), float(y), elevation) for x, y, *_rest in entity.get_points("xyseb")]


def _polyline_points(entity: Any) -> list[tuple[float, float, float]]:
    return [
        (float(vertex.dxf.location.x), float(vertex.dxf.location.y), float(vertex.dxf.location.z))
        for vertex in entity.vertices
    ]


def _spline_points(entity: Any, segments: int) -> list[tuple[float, float, float]]:
    points = []
    try:
        construction = entity.construction_tool()
        for point in construction.approximate(segments=segments):
            points.append((float(point.x), float(point.y), float(point.z)))
    except Exception:
        points = [
            (float(point[0]), float(point[1]), float(point[2]) if len(point) > 2 else 0.0)
            for point in entity.control_points
        ]
    return points


def _points_for_entity(entity: Any, spline_segments: int) -> list[tuple[float, float, float]]:
    dxftype = entity.dxftype()
    if dxftype == "LWPOLYLINE":
        return _lwpolyline_points(entity)
    if dxftype == "POLYLINE":
        return _polyline_points(entity)
    if dxftype == "SPLINE":
        return _spline_points(entity, segments=spline_segments)
    return []


def _matches_layer(layer_name: str, include_layers: Iterable[str], exclude_layers: Iterable[str]) -> bool:
    include_set = {name.casefold() for name in include_layers}
    exclude_set = {name.casefold() for name in exclude_layers}
    layer_key = layer_name.casefold()
    if include_set and layer_key not in include_set:
        return False
    if layer_key in exclude_set:
        return False
    return True


def extract_contours(input_path: Path, output_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    scan_payload = scan_dxf(input_path)
    doc = readfile(input_path)
    source_msp = doc.modelspace()
    out_doc = new("R2018")
    out_msp = out_doc.modelspace()

    include_layers = config.get("include_layers", [])
    exclude_layers = config.get("exclude_layers", [])
    include_types = {name.upper() for name in config.get("include_entity_types", list(SUPPORTED_TYPES))}
    min_vertices = int(config.get("min_vertices", 2))
    spline_segments = int(config.get("spline_segments", 32))
    require_layer_match = bool(config.get("require_layer_match", False))
    allow_zero_elevation = bool(config.get("allow_zero_elevation", False))
    auto_detect_layers = bool(config.get("auto_detect_layers", True))

    if not include_layers and auto_detect_layers:
        include_layers = list(scan_payload.get("recommended_contour_layers", []))

    entities_written = 0
    layers_used: set[str] = set()
    unsupported_entities_skipped = 0

    for entity in source_msp:
        dxftype = entity.dxftype().upper()
        if dxftype not in include_types:
            continue
        if dxftype not in SUPPORTED_TYPES:
            unsupported_entities_skipped += 1
            continue

        layer_name = entity.dxf.layer
        if not _matches_layer(layer_name, include_layers, exclude_layers):
            continue

        points = _points_for_entity(entity, spline_segments=spline_segments)
        if len(points) < min_vertices:
            continue

        has_non_zero_z = any(abs(point[2]) > 1e-9 for point in points)
        if require_layer_match and not include_layers:
            continue
        if not allow_zero_elevation and not has_non_zero_z:
            continue

        out_msp.add_polyline3d(points, dxfattribs={"layer": layer_name})
        entities_written += 1
        layers_used.add(layer_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_doc.saveas(output_path)

    return {
        "status": "ok" if entities_written else "error",
        "normalized_entity_kind": "3d_polyline",
        "entities_written": entities_written,
        "layers_used": sorted(layers_used),
        "auto_selected_layers": sorted(include_layers),
        "unsupported_entities_skipped": unsupported_entities_skipped,
        "output_dxf": str(output_path),
    }
