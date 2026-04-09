from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ezdxf.filemanagement import readfile

SCAN_WARNING_PROXY = "PROXY_GEOMETRY_PRESENT"


def _contour_keyword_score(layer_name: str) -> int:
    keywords = ("contour", "콘타", "등고", "level", "elev", "표고")
    lowered = layer_name.casefold()
    return sum(1 for keyword in keywords if keyword.casefold() in lowered)


def _candidate_score(non_zero_z_entities: int, distinct_z_count: int, keyword_score: int) -> int:
    score = 0
    if non_zero_z_entities >= 100:
        score += 5
    elif non_zero_z_entities >= 30:
        score += 4
    elif non_zero_z_entities >= 10:
        score += 2
    elif non_zero_z_entities >= 3:
        score += 1

    if distinct_z_count >= 20:
        score += 5
    elif distinct_z_count >= 8:
        score += 4
    elif distinct_z_count >= 4:
        score += 2
    elif distinct_z_count >= 2:
        score += 1

    score += keyword_score * 3
    return score


def _is_strong_candidate(score: int, non_zero_z_entities: int, distinct_z_count: int) -> bool:
    return score >= 8 or (non_zero_z_entities >= 30 and distinct_z_count >= 3)


def _polyline_points(entity: Any) -> list[tuple[float, float, float]]:
    dxftype = entity.dxftype()
    if dxftype == "LWPOLYLINE":
        elevation = float(entity.dxf.elevation or 0.0)
        return [(float(x), float(y), elevation) for x, y, *_rest in entity.get_points("xyseb")]
    if dxftype == "POLYLINE":
        return [
            (float(vertex.dxf.location.x), float(vertex.dxf.location.y), float(vertex.dxf.location.z))
            for vertex in entity.vertices
        ]
    if dxftype == "SPLINE":
        return [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in entity.control_points]
    return []


def _entity_summary(entity: Any) -> dict[str, Any]:
    points = _polyline_points(entity)
    z_values = sorted({round(point[2], 6) for point in points})
    has_non_zero_z = any(abs(z) > 1e-9 for z in z_values)
    return {
        "layer": entity.dxf.layer,
        "type": entity.dxftype(),
        "vertex_count": len(points),
        "has_non_zero_z": has_non_zero_z,
        "distinct_z_count": len(z_values),
        "z_values": z_values[:20],
        "is_closed": bool(getattr(entity, "closed", False)),
    }


def scan_dxf(input_path: Path) -> dict[str, Any]:
    doc = readfile(input_path)
    msp = doc.modelspace()

    entity_type_counts: Counter[str] = Counter()
    layer_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "entity_count": 0,
            "entity_types": Counter(),
            "non_zero_z_entities": 0,
            "distinct_z_values": set(),
        }
    )
    proxy_entity_count = 0

    for entity in msp:
        entity_type = entity.dxftype()
        entity_type_counts[entity_type] += 1
        if entity_type == "ACAD_PROXY_ENTITY":
            proxy_entity_count += 1

        layer_name = entity.dxf.layer
        layer_entry = layer_stats[layer_name]
        layer_entry["entity_count"] += 1
        layer_entry["entity_types"][entity_type] += 1

        if entity_type in {"LWPOLYLINE", "POLYLINE", "SPLINE"}:
            summary = _entity_summary(entity)
            if summary["has_non_zero_z"]:
                layer_entry["non_zero_z_entities"] += 1
            for z_value in summary["z_values"]:
                layer_entry["distinct_z_values"].add(z_value)

    candidate_contour_layers = []
    recommended_contour_layers = []
    for layer_name, stats in layer_stats.items():
        entity_types = stats["entity_types"]
        if stats["non_zero_z_entities"] == 0:
            continue
        if not any(entity_types.get(name, 0) for name in ("LWPOLYLINE", "POLYLINE", "SPLINE")):
            continue
        distinct_z_count = len(stats["distinct_z_values"])
        keyword_score = _contour_keyword_score(layer_name)
        score = _candidate_score(stats["non_zero_z_entities"], distinct_z_count, keyword_score)
        candidate = {
            "layer": layer_name,
            "non_zero_z_entities": stats["non_zero_z_entities"],
            "distinct_z_count": distinct_z_count,
            "entity_count": stats["entity_count"],
            "keyword_score": keyword_score,
            "score": score,
            "strong_candidate": _is_strong_candidate(score, stats["non_zero_z_entities"], distinct_z_count),
        }
        candidate_contour_layers.append(candidate)
        if candidate["strong_candidate"]:
            recommended_contour_layers.append(layer_name)

    warnings = []
    if proxy_entity_count:
        warnings.append(SCAN_WARNING_PROXY)

    normalized_layer_stats = {}
    for layer_name, stats in layer_stats.items():
        normalized_layer_stats[layer_name] = {
            "entity_count": stats["entity_count"],
            "entity_types": dict(stats["entity_types"]),
            "non_zero_z_entities": stats["non_zero_z_entities"],
            "distinct_z_count": len(stats["distinct_z_values"]),
            "sample_z_values": sorted(stats["distinct_z_values"])[:20],
        }

    return {
        "status": "ok",
        "entity_type_counts": dict(entity_type_counts),
        "layer_stats": normalized_layer_stats,
        "candidate_contour_layers": sorted(
            candidate_contour_layers,
            key=lambda item: (item["score"], item["non_zero_z_entities"], item["distinct_z_count"], item["entity_count"]),
            reverse=True,
        ),
        "recommended_contour_layers": sorted(recommended_contour_layers),
        "proxy_entity_count": proxy_entity_count,
        "warnings": warnings,
    }
