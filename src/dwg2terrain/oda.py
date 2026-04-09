from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from .models import ConversionResult, ODAResolution


COMMON_ODA_PATHS = [
    Path(r"C:\Program Files\ODA\ODAFileConverter\ODAFileConverter.exe"),
    Path(r"C:\Program Files\ODA\ODAFileConverter 27.1.0\ODAFileConverter.exe"),
    Path(r"C:\Program Files (x86)\ODA\ODAFileConverter\ODAFileConverter.exe"),
]


def resolve_oda_executable(explicit_path: str | None) -> ODAResolution:
    if explicit_path:
        path = Path(explicit_path)
        if path.exists():
            return ODAResolution(status="ok", path=path, source="explicit")
        return ODAResolution(status="missing", path=path, source="explicit")

    for path in COMMON_ODA_PATHS:
        if path.exists():
            return ODAResolution(status="ok", path=path, source="common_path")

    on_path = shutil.which("ODAFileConverter.exe") or shutil.which("ODAFileConverter")
    if on_path:
        return ODAResolution(status="ok", path=Path(on_path), source="path")

    return ODAResolution(status="missing", path=None, source="not_found")


def convert_dwg_to_dxf(
    input_path: Path,
    output_path: Path,
    oda_path: Path,
    output_version: str = "ACAD2018",
    audit: bool = True,
    timeout_sec: int = 180,
) -> ConversionResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dwg2terrain_in_") as input_dir, tempfile.TemporaryDirectory(
        prefix="dwg2terrain_out_"
    ) as out_dir:
        staged_input = Path(input_dir) / input_path.name
        shutil.copy2(input_path, staged_input)

        command = [
            str(oda_path),
            str(Path(input_dir)),
            str(Path(out_dir)),
            output_version,
            "DXF",
            "0",
            "1" if audit else "0",
            input_path.name,
        ]

        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                startupinfo=startupinfo,
            )
        except subprocess.TimeoutExpired:
            return ConversionResult(
                status="error",
                code="ODA_CONVERSION_FAILED",
                mode="dwg_to_dxf",
                input_path=input_path,
                output_path=None,
                oda_path=oda_path,
                detail="ODA conversion timed out",
            )

        staged_output = Path(out_dir) / f"{input_path.stem}.dxf"
        if completed.returncode != 0 or not staged_output.exists():
            detail = (completed.stderr or completed.stdout or "ODA conversion failed").strip()
            return ConversionResult(
                status="error",
                code="ODA_CONVERSION_FAILED",
                mode="dwg_to_dxf",
                input_path=input_path,
                output_path=None,
                oda_path=oda_path,
                detail=detail,
            )

        shutil.move(str(staged_output), str(output_path))
        return ConversionResult(
            status="ok",
            code=None,
            mode="dwg_to_dxf",
            input_path=input_path,
            output_path=output_path,
            oda_path=oda_path,
            detail=None,
        )
