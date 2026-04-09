from __future__ import annotations

import json
import importlib
import sys
from pathlib import Path

from ezdxf.filemanagement import new

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

extract_module = importlib.import_module("dwg2terrain.extract")
mesh_module = importlib.import_module("dwg2terrain.mesh")
scan_module = importlib.import_module("dwg2terrain.scan")
settings_module = importlib.import_module("dwg2terrain.settings")

extract_contours = extract_module.extract_contours
build_terrain_mesh = mesh_module.build_terrain_mesh
validate_mesh_report = mesh_module.validate_mesh_report
scan_dxf = scan_module.scan_dxf
DEFAULT_CONFIG = settings_module.DEFAULT_CONFIG
DEFAULT_MESH_CONFIG = settings_module.DEFAULT_MESH_CONFIG


def _write_sample_dxf(path: Path) -> None:
    doc = new("R2018")
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (20, 0)], dxfattribs={"layer": "0-5m콘타", "elevation": 100.0})
    msp.add_lwpolyline([(0, 10), (10, 10), (20, 10)], dxfattribs={"layer": "0-5m콘타", "elevation": 105.0})
    msp.add_lwpolyline([(0, 20), (10, 20), (20, 20)], dxfattribs={"layer": "0-5m콘타", "elevation": 110.0})
    msp.add_text("label", dxfattribs={"layer": "TEXT"})
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(path)


def test_scan_extract_mesh_pipeline(tmp_path: Path) -> None:
    source = tmp_path / "sample.dxf"
    contours = tmp_path / "contours.dxf"
    mesh = tmp_path / "terrain.obj"
    report = tmp_path / "report.json"
    _write_sample_dxf(source)

    scan_payload = scan_dxf(source)
    assert scan_payload["status"] == "ok"
    layer_names = {item["layer"] for item in scan_payload["candidate_contour_layers"]}
    assert "0-5m콘타" in layer_names

    extract_payload = extract_contours(source, contours, dict(DEFAULT_CONFIG))
    assert extract_payload["status"] == "ok"
    assert contours.exists()

    mesh_payload = build_terrain_mesh(contours, mesh, dict(DEFAULT_MESH_CONFIG))
    report.write_text(json.dumps(mesh_payload), encoding="utf-8")
    assert mesh_payload["status"] == "ok"
    assert mesh.exists()
    assert validate_mesh_report(mesh, report)
