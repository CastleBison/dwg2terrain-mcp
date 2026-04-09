from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from ezdxf.filemanagement import readfile
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from scipy.ndimage import convolve
from scipy.spatial import Delaunay, KDTree


@dataclass(frozen=True)
class MeshBuildError(Exception):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def _polyline_vertices(entity: Any) -> list[tuple[float, float, float]]:
    return [
        (float(vertex.dxf.location.x), float(vertex.dxf.location.y), float(vertex.dxf.location.z))
        for vertex in entity.vertices
    ]


def _segment_lengths(points: np.ndarray) -> np.ndarray:
    if len(points) < 2:
        return np.array([], dtype=float)
    return np.linalg.norm(points[1:, :2] - points[:-1, :2], axis=1)


def _densify_polyline(points: list[tuple[float, float, float]], max_segment_length: float) -> list[tuple[float, float, float]]:
    if len(points) < 2 or max_segment_length <= 0:
        return points

    result: list[tuple[float, float, float]] = [points[0]]
    for start, end in zip(points, points[1:]):
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        dz = end[2] - start[2]
        distance = float(np.hypot(dx, dy))
        if distance <= max_segment_length:
            result.append(end)
            continue
        steps = int(np.ceil(distance / max_segment_length))
        for step in range(1, steps):
            t = step / steps
            result.append((start[0] + dx * t, start[1] + dy * t, start[2] + dz * t))
        result.append(end)
    return result


def _load_contour_points(input_path: Path, densify_max_segment_length: float) -> tuple[list[list[tuple[float, float, float]]], dict[str, Any]]:
    doc = readfile(input_path)
    msp = doc.modelspace()
    polylines: list[list[tuple[float, float, float]]] = []
    segment_lengths: list[float] = []
    sampled_point_count = 0

    for entity in msp:
        if entity.dxftype().upper() != "POLYLINE":
            continue
        points = _polyline_vertices(entity)
        if len(points) < 2:
            continue
        points = _densify_polyline(points, densify_max_segment_length)
        sampled_point_count += len(points)
        segment_lengths.extend(_segment_lengths(np.asarray(points, dtype=float)).tolist())
        polylines.append(points)

    if not polylines:
        raise MeshBuildError("MESH_INPUT_EMPTY", "No usable 3D contour polylines found in DXF")

    z_levels = sorted({round(point[2], 6) for polyline in polylines for point in polyline})
    z_diffs = [b - a for a, b in zip(z_levels, z_levels[1:]) if b > a]
    stats = {
        "polyline_count": len(polylines),
        "sampled_point_count": sampled_point_count,
        "segment_length_min": min(segment_lengths) if segment_lengths else 0.0,
        "segment_length_median": float(np.median(segment_lengths)) if segment_lengths else 0.0,
        "segment_length_max": max(segment_lengths) if segment_lengths else 0.0,
        "contour_interval": float(np.median(z_diffs)) if z_diffs else 0.0,
    }
    return polylines, stats


def _dedupe_points(polylines: list[list[tuple[float, float, float]]], xy_tolerance: float) -> tuple[np.ndarray, dict[str, int]]:
    index_by_xy: dict[tuple[int, int], int] = {}
    vertices: list[tuple[float, float, float]] = []
    duplicate_count = 0
    scale = 1.0 / xy_tolerance

    for polyline in polylines:
        for x, y, z in polyline:
            key = (int(round(x * scale)), int(round(y * scale)))
            if key in index_by_xy:
                duplicate_count += 1
                existing = vertices[index_by_xy[key]]
                if abs(existing[2] - z) > 1e-6:
                    raise MeshBuildError(
                        "MESH_XY_Z_CONFLICT",
                        f"Same XY has conflicting Z values: {existing[0]}, {existing[1]} -> {existing[2]} vs {z}",
                    )
                continue
            index_by_xy[key] = len(vertices)
            vertices.append((x, y, z))

    if len(vertices) < 3:
        raise MeshBuildError("MESH_INPUT_EMPTY", "Need at least 3 unique points to build mesh")

    return np.asarray(vertices, dtype=float), {"duplicate_xy_points": duplicate_count, "unique_point_count": len(vertices)}


def _triangle_metrics(vertices: np.ndarray, simplices: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    triangles = vertices[simplices]
    edge_a = np.linalg.norm(triangles[:, 1, :2] - triangles[:, 0, :2], axis=1)
    edge_b = np.linalg.norm(triangles[:, 2, :2] - triangles[:, 1, :2], axis=1)
    edge_c = np.linalg.norm(triangles[:, 0, :2] - triangles[:, 2, :2], axis=1)
    max_edge = np.maximum(np.maximum(edge_a, edge_b), edge_c)
    area2 = np.abs(
        (triangles[:, 1, 0] - triangles[:, 0, 0]) * (triangles[:, 2, 1] - triangles[:, 0, 1])
        - (triangles[:, 1, 1] - triangles[:, 0, 1]) * (triangles[:, 2, 0] - triangles[:, 0, 0])
    )
    return max_edge, area2 * 0.5


def _build_tin_faces(vertices: np.ndarray, config: dict[str, Any], segment_length_median: float) -> tuple[np.ndarray, dict[str, int], dict[str, float]]:
    triangulation = Delaunay(vertices[:, :2])
    simplices = triangulation.simplices
    if len(simplices) == 0:
        raise MeshBuildError("MESH_TRIANGULATION_EMPTY", "XY triangulation produced no triangles")

    max_edge_factor = float(config.get("max_edge_factor", 6.0))
    centroid_factor = float(config.get("centroid_distance_factor", 1.8))
    min_area = float(config.get("min_triangle_area", 0.01))
    absolute_max_edge = float(config.get("absolute_max_edge_length", 0.0))
    max_edge_threshold = absolute_max_edge if absolute_max_edge > 0 else segment_length_median * max_edge_factor
    centroid_threshold = segment_length_median * centroid_factor if segment_length_median > 0 else 0.0

    max_edge, areas = _triangle_metrics(vertices, simplices)
    tree = KDTree(vertices[:, :2])
    centroid = vertices[simplices][:, :, :2].mean(axis=1)
    nearest_distance, _ = tree.query(centroid, k=1)

    keep_mask = np.ones(len(simplices), dtype=bool)
    rejected = {"max_edge": 0, "centroid_distance": 0, "min_area": 0}

    if max_edge_threshold > 0:
        edge_mask = max_edge <= max_edge_threshold
        rejected["max_edge"] = int(np.count_nonzero(~edge_mask))
        keep_mask &= edge_mask
    if centroid_threshold > 0:
        centroid_mask = nearest_distance <= centroid_threshold
        rejected["centroid_distance"] = int(np.count_nonzero(~centroid_mask))
        keep_mask &= centroid_mask
    if min_area > 0:
        area_mask = areas >= min_area
        rejected["min_area"] = int(np.count_nonzero(~area_mask))
        keep_mask &= area_mask

    kept = simplices[keep_mask]
    if len(kept) == 0:
        raise MeshBuildError("MESH_TRIANGULATION_EMPTY", "Triangle filtering removed all faces")

    metrics = {
        "raw_triangle_count": int(len(simplices)),
        "kept_triangle_count": int(len(kept)),
        "max_edge_threshold": float(max_edge_threshold),
        "centroid_threshold": float(centroid_threshold),
        "min_triangle_area": float(min_area),
        "grid_spacing": 0.0,
    }
    return kept, rejected, metrics


def _derive_grid_spacing(bounds_min: np.ndarray, bounds_max: np.ndarray, segment_length_median: float, config: dict[str, Any]) -> float:
    configured = float(config.get("grid_spacing", 0.0))
    if configured > 0:
        return configured
    extent = max(float(bounds_max[0] - bounds_min[0]), float(bounds_max[1] - bounds_min[1]))
    candidate = max(segment_length_median * 2.5, extent / 300.0)
    return max(2.0, candidate)


def _fill_small_grid_holes(
    z_grid: np.ndarray,
    valid_grid: np.ndarray,
    nearest: NearestNDInterpolator,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    support_grid: np.ndarray,
    config: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    max_passes = int(config.get("small_hole_fill_passes", 2))
    min_neighbors = int(config.get("small_hole_min_neighbors", 5))
    if max_passes <= 0:
        return z_grid, valid_grid

    kernel = np.ones((3, 3), dtype=float)
    z_work = z_grid.copy()
    valid_work = valid_grid.copy()

    for _ in range(max_passes):
        neighbor_count = convolve(valid_work.astype(float), kernel, mode="constant", cval=0.0)
        neighbor_sum = convolve(np.where(valid_work, z_work, 0.0), kernel, mode="constant", cval=0.0)
        candidate_mask = (~valid_work) & support_grid & (neighbor_count >= float(min_neighbors))
        if not np.any(candidate_mask):
            break

        avg_values = np.divide(
            neighbor_sum,
            neighbor_count,
            out=np.zeros_like(neighbor_sum),
            where=neighbor_count > 0,
        )
        rows, cols = np.where(candidate_mask)
        nearest_values = nearest(grid_x[rows, cols], grid_y[rows, cols])
        nearest_values = np.asarray(nearest_values, dtype=float)
        blended = (avg_values[rows, cols] + nearest_values) * 0.5
        z_work[rows, cols] = blended
        valid_work[rows, cols] = True

    return z_work, valid_work


def _smooth_valid_grid(z_grid: np.ndarray, valid_grid: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    passes = int(config.get("smoothing_passes", 0))
    blend = float(config.get("smoothing_blend", 0.25))
    if passes <= 0 or blend <= 0:
        return z_grid

    kernel = np.array(
        [
            [1.0, 2.0, 1.0],
            [2.0, 4.0, 2.0],
            [1.0, 2.0, 1.0],
        ],
        dtype=float,
    )
    z_work = z_grid.copy()
    valid_float = valid_grid.astype(float)

    for _ in range(passes):
        weighted_sum = convolve(np.where(valid_grid, z_work, 0.0), kernel, mode="nearest")
        weighted_count = convolve(valid_float, kernel, mode="nearest")
        smoothed = np.divide(
            weighted_sum,
            weighted_count,
            out=z_work.copy(),
            where=weighted_count > 0,
        )
        z_work = np.where(valid_grid, (1.0 - blend) * z_work + blend * smoothed, z_work)

    return z_work


def _build_grid_faces(vertices: np.ndarray, config: dict[str, Any], stats: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, int], dict[str, float]]:
    bounds_min = vertices.min(axis=0)
    bounds_max = vertices.max(axis=0)
    spacing = _derive_grid_spacing(bounds_min, bounds_max, stats["segment_length_median"], config)

    xs = np.arange(bounds_min[0], bounds_max[0] + spacing, spacing)
    ys = np.arange(bounds_min[1], bounds_max[1] + spacing, spacing)
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="xy")
    sample_xy = vertices[:, :2]
    sample_z = vertices[:, 2]

    linear = LinearNDInterpolator(sample_xy, sample_z, fill_value=np.nan)
    nearest = NearestNDInterpolator(sample_xy, sample_z)
    hull = Delaunay(sample_xy)

    flat_x = grid_x.ravel()
    flat_y = grid_y.ravel()
    flat_xy = np.column_stack((flat_x, flat_y))
    linear_z = linear(flat_x, flat_y)
    linear_z = np.asarray(linear_z, dtype=float)

    tree = KDTree(sample_xy)
    nearest_distance, _ = tree.query(flat_xy, k=1)
    max_support_factor = float(config.get("grid_support_distance_factor", 2.5))
    support_threshold = spacing * max_support_factor
    mask_mode = str(config.get("grid_mask_mode", "hull")).strip().lower()
    if mask_mode == "support":
        supported_mask = nearest_distance <= support_threshold
    else:
        inside_hull = hull.find_simplex(flat_xy) >= 0
        supported_mask = inside_hull

    fill_nearest = bool(config.get("grid_fill_nearest", False))
    if fill_nearest:
        fill_mask = ~np.isfinite(linear_z) & supported_mask
        if np.any(fill_mask):
            linear_z[fill_mask] = nearest(flat_x[fill_mask], flat_y[fill_mask])

    valid_mask = np.isfinite(linear_z) & supported_mask
    z_grid = linear_z.reshape(grid_x.shape)
    valid_grid = valid_mask.reshape(grid_x.shape)
    support_grid = supported_mask.reshape(grid_x.shape)

    z_grid, valid_grid = _fill_small_grid_holes(z_grid, valid_grid, nearest, grid_x, grid_y, support_grid, config)
    z_grid = _smooth_valid_grid(z_grid, valid_grid, config)

    contour_interval = max(float(stats.get("contour_interval", 0.0)), 1e-9)
    max_cell_z_levels = float(config.get("max_cell_z_levels", 3.0))
    max_cell_z_span = contour_interval * max_cell_z_levels

    grid_vertices: list[tuple[float, float, float]] = []
    vertex_index = -np.ones(grid_x.shape, dtype=int)
    valid_indices = np.argwhere(valid_grid)
    for row, col in valid_indices:
        vertex_index[row, col] = len(grid_vertices)
        grid_vertices.append((float(grid_x[row, col]), float(grid_y[row, col]), float(z_grid[row, col])))

    faces: list[tuple[int, int, int]] = []
    rejected = {
        "unsupported_cell": 0,
        "z_span": 0,
        "degenerate": 0,
    }

    rows, cols = grid_x.shape
    for row in range(rows - 1):
        for col in range(cols - 1):
            corners = [(row, col), (row, col + 1), (row + 1, col), (row + 1, col + 1)]
            if not all(valid_grid[r, c] for r, c in corners):
                rejected["unsupported_cell"] += 1
                continue

            z_values = [z_grid[r, c] for r, c in corners]
            if max(z_values) - min(z_values) > max_cell_z_span:
                rejected["z_span"] += 1
                continue

            a = int(vertex_index[row, col])
            b = int(vertex_index[row, col + 1])
            c = int(vertex_index[row + 1, col])
            d = int(vertex_index[row + 1, col + 1])
            if min(a, b, c, d) < 0:
                rejected["degenerate"] += 1
                continue

            faces.append((a, b, c))
            faces.append((b, d, c))

    if not faces:
        raise MeshBuildError("MESH_TRIANGULATION_EMPTY", "Grid interpolation produced no usable faces")

    grid_vertices_np = np.asarray(grid_vertices, dtype=float)
    faces_np = np.asarray(faces, dtype=int)
    metrics = {
        "raw_triangle_count": int((rows - 1) * (cols - 1) * 2),
        "kept_triangle_count": int(len(faces_np)),
        "max_edge_threshold": float(spacing * np.sqrt(2.0)),
        "centroid_threshold": float(support_threshold),
        "min_triangle_area": float((spacing * spacing) * 0.5),
        "grid_spacing": float(spacing),
    }
    return grid_vertices_np, faces_np, rejected, metrics


def _write_obj(output_path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# dwg2terrain terrain mesh\n")
        for x, y, z in vertices:
            handle.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        for a, b, c in faces:
            handle.write(f"f {a + 1} {b + 1} {c + 1}\n")


def validate_mesh_report(mesh_path: Path, report_path: Path) -> bool:
    if not mesh_path.exists() or not report_path.exists():
        return False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    vertex_count = 0
    face_count = 0
    with mesh_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("v "):
                vertex_count += 1
            elif line.startswith("f "):
                face_count += 1
    return vertex_count == report.get("unique_point_count") and face_count == report.get("kept_triangle_count") and vertex_count > 0 and face_count > 0


def build_terrain_mesh(input_path: Path, output_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    densify_max_segment_length = float(config.get("densify_max_segment_length", 0.0))
    xy_tolerance = float(config.get("xy_tolerance", 1e-6))
    method = str(config.get("method", "grid")).strip().lower()

    polylines, stats = _load_contour_points(input_path, densify_max_segment_length=densify_max_segment_length)
    source_vertices, dedupe_stats = _dedupe_points(polylines, xy_tolerance=xy_tolerance)

    if method == "tin":
        mesh_vertices = source_vertices
        faces, rejected, mesh_metrics = _build_tin_faces(
            source_vertices,
            config=config,
            segment_length_median=max(stats["segment_length_median"], 1e-9),
        )
    else:
        mesh_vertices, faces, rejected, mesh_metrics = _build_grid_faces(source_vertices, config=config, stats=stats)

    try:
        _write_obj(output_path, mesh_vertices, faces)
    except OSError as exc:
        raise MeshBuildError("MESH_EXPORT_FAILED", str(exc)) from exc

    bounds_min = mesh_vertices.min(axis=0)
    bounds_max = mesh_vertices.max(axis=0)
    return {
        "status": "ok",
        "format": "obj",
        "method": method,
        "input_dxf": str(input_path),
        "output_obj": str(output_path),
        "polyline_count": stats["polyline_count"],
        "sampled_point_count": stats["sampled_point_count"],
        "source_unique_point_count": dedupe_stats["unique_point_count"],
        "unique_point_count": int(len(mesh_vertices)),
        "duplicate_xy_points": dedupe_stats["duplicate_xy_points"],
        "contour_interval": stats["contour_interval"],
        "raw_triangle_count": mesh_metrics["raw_triangle_count"],
        "kept_triangle_count": mesh_metrics["kept_triangle_count"],
        "rejected_triangle_counts": rejected,
        "bounds": {
            "min": bounds_min.tolist(),
            "max": bounds_max.tolist(),
        },
        "filters": {
            "densify_max_segment_length": densify_max_segment_length,
            "xy_tolerance": xy_tolerance,
            "max_edge_threshold": mesh_metrics["max_edge_threshold"],
            "centroid_threshold": mesh_metrics["centroid_threshold"],
            "min_triangle_area": mesh_metrics["min_triangle_area"],
            "grid_spacing": mesh_metrics["grid_spacing"],
        },
    }
