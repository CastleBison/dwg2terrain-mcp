from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import ezdxf

from .extract import extract_contours
from .mesh import MeshBuildError, build_terrain_mesh, validate_mesh_report
from .models import (
    EXIT_CONTOUR_FILTER_EMPTY,
    EXIT_DXF_READ_FAILED,
    EXIT_MESH_EXPORT_FAILED,
    EXIT_MESH_INPUT_EMPTY,
    EXIT_MESH_TRIANGULATION_EMPTY,
    EXIT_MESH_XY_Z_CONFLICT,
    EXIT_ODA_CONVERSION_FAILED,
    EXIT_ODA_NOT_FOUND,
    EXIT_OK,
    EXIT_PROXY_GEOMETRY_BLOCKED,
    EXIT_UNSUPPORTED_INPUT,
)
from .oda import convert_dwg_to_dxf, resolve_oda_executable
from .scan import scan_dxf
from .settings import load_config, resolve_oda_hint


def _print_payload(payload: dict[str, Any], json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(payload)


def _write_report(payload: dict[str, Any], report_path: str | None) -> None:
    if not report_path:
        return
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _doctor(args: argparse.Namespace) -> int:
    input_path = Path(args.input) if args.input else None
    oda_resolution = resolve_oda_executable(resolve_oda_hint(args.oda_exe))
    payload = {
        "status": "ok",
        "python": "ok",
        "ezdxf": "ok" if ezdxf else "missing",
        "oda": "ok" if oda_resolution.status == "ok" else "missing",
        "oda_path": str(oda_resolution.path) if oda_resolution.path else None,
        "input_exists": input_path.exists() if input_path else False,
        "platform": platform.platform(),
    }
    _write_report(payload, args.report)
    _print_payload(payload, args.json)
    return EXIT_OK


def _convert(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    suffix = input_path.suffix.lower()
    if suffix not in {".dwg", ".dxf"}:
        payload = {"status": "error", "code": "UNSUPPORTED_INPUT", "input": str(input_path)}
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_UNSUPPORTED_INPUT

    output_path = Path(args.out)
    if suffix == ".dxf":
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(input_path.read_bytes())
        payload = {
            "status": "ok",
            "mode": "dxf_passthrough",
            "input": str(input_path),
            "output": str(output_path),
        }
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_OK

    oda_resolution = resolve_oda_executable(resolve_oda_hint(args.oda_exe))
    if oda_resolution.status != "ok" or oda_resolution.path is None:
        payload = {
            "status": "error",
            "code": "ODA_NOT_FOUND",
            "input": str(input_path),
            "oda_path": str(oda_resolution.path) if oda_resolution.path else None,
        }
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_ODA_NOT_FOUND

    result = convert_dwg_to_dxf(input_path=input_path, output_path=output_path, oda_path=oda_resolution.path)
    payload = {
        "status": result.status,
        "code": result.code,
        "mode": result.mode,
        "input": str(result.input_path),
        "output": str(result.output_path) if result.output_path else None,
        "oda_path": str(result.oda_path) if result.oda_path else None,
        "detail": result.detail,
    }
    _write_report(payload, args.report)
    _print_payload(payload, args.json)
    return EXIT_OK if result.status == "ok" else EXIT_ODA_CONVERSION_FAILED


def _scan(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    try:
        payload = scan_dxf(input_path)
    except Exception as exc:
        payload = {"status": "error", "code": "DXF_READ_FAILED", "detail": str(exc)}
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_DXF_READ_FAILED
    _write_report(payload, args.report)
    _print_payload(payload, args.json)
    return EXIT_OK


def _extract(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    config = load_config(args.config)
    try:
        scan_payload = scan_dxf(input_path)
    except Exception as exc:
        payload = {"status": "error", "code": "DXF_READ_FAILED", "detail": str(exc)}
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_DXF_READ_FAILED

    if scan_payload["proxy_entity_count"] > 0 and args.block_on_proxy:
        payload = {
            "status": "error",
            "code": "PROXY_GEOMETRY_BLOCKED",
            "proxy_entity_count": scan_payload["proxy_entity_count"],
        }
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_PROXY_GEOMETRY_BLOCKED

    payload = extract_contours(input_path=input_path, output_path=Path(args.out), config=config)
    if payload["status"] != "ok":
        payload["code"] = "CONTOUR_FILTER_EMPTY"
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        return EXIT_CONTOUR_FILTER_EMPTY

    _write_report(payload, args.report)
    _print_payload(payload, args.json)
    return EXIT_OK


def _run(args: argparse.Namespace) -> int:
    convert_args = argparse.Namespace(
        input=args.input,
        out=args.converted,
        oda_exe=args.oda_exe,
        json=False,
        report=args.convert_report,
    )
    exit_code = _convert(convert_args)
    if exit_code != EXIT_OK:
        return exit_code

    scan_args = argparse.Namespace(input=args.converted, json=False, report=args.scan_report)
    exit_code = _scan(scan_args)
    if exit_code != EXIT_OK:
        return exit_code

    extract_args = argparse.Namespace(
        input=args.converted,
        out=args.out,
        config=args.config,
        json=args.json,
        report=args.extract_report,
        block_on_proxy=args.block_on_proxy,
    )
    return _extract(extract_args)


def _mesh(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    config = load_config(args.config)
    try:
        payload = build_terrain_mesh(input_path=input_path, output_path=Path(args.out), config=config)
    except MeshBuildError as exc:
        payload = {
            "status": "error",
            "code": exc.code,
            "detail": exc.detail,
            "input_dxf": str(input_path),
            "output_obj": str(Path(args.out)),
        }
        _write_report(payload, args.report)
        _print_payload(payload, args.json)
        exit_codes = {
            "MESH_INPUT_EMPTY": EXIT_MESH_INPUT_EMPTY,
            "MESH_XY_Z_CONFLICT": EXIT_MESH_XY_Z_CONFLICT,
            "MESH_TRIANGULATION_EMPTY": EXIT_MESH_TRIANGULATION_EMPTY,
            "MESH_EXPORT_FAILED": EXIT_MESH_EXPORT_FAILED,
        }
        return exit_codes.get(exc.code, EXIT_MESH_EXPORT_FAILED)

    _write_report(payload, args.report)
    _print_payload(payload, args.json)
    return EXIT_OK


def _validate_mesh(args: argparse.Namespace) -> int:
    ok = validate_mesh_report(Path(args.mesh), Path(args.report))
    if ok:
        print("MESH_REPORT_OK")
        return EXIT_OK
    print("MESH_REPORT_INVALID")
    return EXIT_MESH_EXPORT_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dwg2terrain")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--input")
    doctor.add_argument("--oda-exe")
    doctor.add_argument("--json", action="store_true")
    doctor.add_argument("--report")
    doctor.set_defaults(func=_doctor)

    convert = subparsers.add_parser("convert")
    convert.add_argument("input")
    convert.add_argument("--out", required=True)
    convert.add_argument("--oda-exe")
    convert.add_argument("--json", action="store_true")
    convert.add_argument("--report")
    convert.set_defaults(func=_convert)

    scan = subparsers.add_parser("scan")
    scan.add_argument("input")
    scan.add_argument("--json", action="store_true")
    scan.add_argument("--report")
    scan.set_defaults(func=_scan)

    extract = subparsers.add_parser("extract")
    extract.add_argument("input")
    extract.add_argument("--out", required=True)
    extract.add_argument("--config")
    extract.add_argument("--json", action="store_true")
    extract.add_argument("--report")
    extract.add_argument("--block-on-proxy", action="store_true")
    extract.set_defaults(func=_extract)

    mesh = subparsers.add_parser("mesh")
    mesh.add_argument("input")
    mesh.add_argument("--out", required=True)
    mesh.add_argument("--config")
    mesh.add_argument("--json", action="store_true")
    mesh.add_argument("--report")
    mesh.set_defaults(func=_mesh)

    validate_mesh = subparsers.add_parser("validate-mesh")
    validate_mesh.add_argument("--mesh", required=True)
    validate_mesh.add_argument("--report", required=True)
    validate_mesh.set_defaults(func=_validate_mesh)

    run = subparsers.add_parser("run")
    run.add_argument("input")
    run.add_argument("--converted", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--config")
    run.add_argument("--oda-exe")
    run.add_argument("--json", action="store_true")
    run.add_argument("--convert-report")
    run.add_argument("--scan-report")
    run.add_argument("--extract-report")
    run.add_argument("--block-on-proxy", action="store_true")
    run.set_defaults(func=_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
