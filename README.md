# dwg2terrain-mcp

`dwg2terrain-mcp` is a Python package that exposes a DWG/DXF terrain pipeline as both a CLI and a stdio MCP server.

It focuses on one workflow:

1. convert `DWG` to `DXF` with local ODA File Converter support
2. scan and isolate contour-like geometry with elevation
3. generate Blender-friendly terrain meshes as `OBJ`

## Install

```bash
python -m pip install -e .
```

Runtime dependencies are `ezdxf`, `numpy`, `scipy`, and `mcp`.

## CLI Quickstart

```bash
dwg2terrain doctor --input "C:\path\sample.dwg" --json
dwg2terrain convert "C:\path\sample.dwg" --out "work\converted\sample.dxf" --json
dwg2terrain scan "work\converted\sample.dxf" --json
dwg2terrain extract "work\converted\sample.dxf" --config "config\default.json" --out "output\contours\sample_contours.dxf" --json
dwg2terrain mesh "output\contours\sample_contours.dxf" --config "config\mesh.highres.json" --out "output\terrain\sample_terrain.obj" --json
dwg2terrain validate-mesh --mesh "output\terrain\sample_terrain.obj" --report "output\reports\sample.mesh.json"
```

## MCP Server

Start the stdio MCP server with:

```bash
dwg2terrain-mcp
```

Exposed tools:

- `doctor`
- `convert`
- `scan`
- `extract`
- `mesh`
- `pipeline`

The MCP layer is intentionally thin and wraps the same core functions used by the CLI.

## ODA Notes

`DWG` conversion is optional and depends on a local ODA File Converter installation.

Resolution order:

1. explicit CLI/MCP `oda_exe`
2. `ODA_FILE_CONVERTER_EXE`
3. common install paths under `C:\Program Files`
4. `PATH`

If you already have `DXF`, the rest of the pipeline works without ODA.

## Blender Notes

The terrain mesh stage exports `OBJ`. In practice, the most stable results come from the high-resolution Blender-targeted export configuration after contours have been cleaned and extracted.

## Development

```bash
python -m pip install -e .[dev]
pytest -q
python -m build
python -m twine check dist/*
```
