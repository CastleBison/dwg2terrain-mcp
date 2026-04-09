from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


EXIT_OK = 0
EXIT_ODA_NOT_FOUND = 20
EXIT_ODA_CONVERSION_FAILED = 21
EXIT_UNSUPPORTED_INPUT = 22
EXIT_DXF_READ_FAILED = 23
EXIT_CONTOUR_FILTER_EMPTY = 24
EXIT_PROXY_GEOMETRY_BLOCKED = 25
EXIT_MESH_INPUT_EMPTY = 30
EXIT_MESH_XY_Z_CONFLICT = 31
EXIT_MESH_TRIANGULATION_EMPTY = 32
EXIT_MESH_EXPORT_FAILED = 33


@dataclass(frozen=True)
class ODAResolution:
    status: str
    path: Path | None
    source: str


@dataclass(frozen=True)
class ConversionResult:
    status: str
    code: str | None
    mode: str
    input_path: Path
    output_path: Path | None
    oda_path: Path | None
    detail: str | None = None
