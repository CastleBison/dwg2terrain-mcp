from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from .extract import extract_contours
from .mesh import build_terrain_mesh
from .oda import convert_dwg_to_dxf, resolve_oda_executable
from .scan import scan_dxf
from .settings import DEFAULT_CONFIG, DEFAULT_MESH_CONFIG, HIGHRES_MESH_CONFIG, merge_config

mcp = FastMCP("dwg2terrain")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _serialize_error(exc: Exception) -> ToolError:
    print(str(exc), file=sys.stderr)
    return ToolError(str(exc))


@mcp.tool()
def doctor(input_path: str | None = None, oda_exe: str | None = None) -> dict[str, Any]:
    """Check Python and ODA availability for DWG processing."""
    target = Path(input_path) if input_path else None
    oda = resolve_oda_executable(oda_exe)
    return {
        "status": "ok",
        "oda": oda.status,
        "oda_path": str(oda.path) if oda.path else None,
        "input_exists": target.exists() if target else False,
    }


@mcp.tool()
def convert(input_path: str, output_path: str, oda_exe: str | None = None) -> dict[str, Any]:
    """Convert DWG to DXF, or pass DXF through unchanged."""
    source = Path(input_path)
    target = Path(output_path)
    _ensure_parent(target)
    if source.suffix.lower() == ".dxf":
        target.write_bytes(source.read_bytes())
        return {"status": "ok", "mode": "dxf_passthrough", "output": str(target)}
    oda = resolve_oda_executable(oda_exe)
    if oda.status != "ok" or oda.path is None:
        raise ToolError("ODA File Converter not found")
    result = convert_dwg_to_dxf(source, target, oda.path)
    if result.status != "ok":
        raise ToolError(result.detail or "DWG conversion failed")
    return {"status": "ok", "mode": result.mode, "output": str(target)}


@mcp.tool()
def scan(input_path: str) -> dict[str, Any]:
    """Scan a DXF file and return contour-candidate layer analysis."""
    try:
        return scan_dxf(Path(input_path))
    except Exception as exc:
        raise _serialize_error(exc)


@mcp.tool()
def extract(
    input_path: str,
    output_path: str,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract contour-like geometry from a DXF into a contour-only DXF."""
    try:
        payload = extract_contours(Path(input_path), Path(output_path), merge_config(DEFAULT_CONFIG, config))
        if payload["status"] != "ok":
            raise ToolError(json.dumps(payload, ensure_ascii=False))
        return payload
    except Exception as exc:
        if isinstance(exc, ToolError):
            raise exc
        raise _serialize_error(exc)


@mcp.tool()
def mesh(
    input_path: str,
    output_path: str,
    highres: bool = False,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a terrain OBJ from contour DXF input."""
    base = HIGHRES_MESH_CONFIG if highres else DEFAULT_MESH_CONFIG
    try:
        return build_terrain_mesh(Path(input_path), Path(output_path), merge_config(base, config))
    except Exception as exc:
        raise _serialize_error(exc)


@mcp.tool()
def pipeline(
    input_path: str,
    output_dir: str,
    oda_exe: str | None = None,
    highres: bool = False,
) -> dict[str, Any]:
    """Run the full DWG/DXF -> contour DXF -> terrain OBJ pipeline."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    source = Path(input_path)

    converted = root / f"{source.stem}.dxf"
    contours = root / f"{source.stem}_contours.dxf"
    terrain = root / f"{source.stem}_terrain.obj"

    convert_result = convert(str(source), str(converted), oda_exe=oda_exe)
    scan_result = scan(str(converted))
    extract_result = extract(str(converted), str(contours))
    mesh_result = mesh(str(contours), str(terrain), highres=highres)

    return {
        "status": "ok",
        "convert": convert_result,
        "scan": scan_result,
        "extract": extract_result,
        "mesh": mesh_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="dwg2terrain-mcp", add_help=True)
    parser.add_argument("--transport", default="stdio", choices=["stdio"], help="Server transport")
    args = parser.parse_args()
    if args.transport != "stdio":
        raise SystemExit("Only stdio transport is supported")
    mcp.run()


if __name__ == "__main__":
    main()
