# dwg2terrain-mcp

`dwg2terrain-mcp`는 `DWG/DXF -> 등고선 추출 -> 지형 메쉬 생성` 파이프라인을 CLI와 stdio MCP 서버로 제공하는 Python 패키지입니다.

주요 워크플로우는 다음과 같습니다.

1. 로컬 `ODA File Converter`를 이용해 `DWG`를 `DXF`로 변환
2. 고도값이 있는 등고선 후보를 스캔하고 분리
3. 블렌더에서 쓰기 좋은 `OBJ` 지형 메쉬 생성

## 설치

```bash
python -m pip install -e .
```

런타임 의존성은 `ezdxf`, `numpy`, `scipy`, `mcp` 입니다.

## CLI 빠른 시작

```bash
dwg2terrain doctor --input "C:\path\sample.dwg" --json
dwg2terrain convert "C:\path\sample.dwg" --out "work\converted\sample.dxf" --json
dwg2terrain scan "work\converted\sample.dxf" --json
dwg2terrain extract "work\converted\sample.dxf" --config "config\default.json" --out "output\contours\sample_contours.dxf" --json
dwg2terrain mesh "output\contours\sample_contours.dxf" --config "config\mesh.highres.json" --out "output\terrain\sample_terrain.obj" --json
dwg2terrain validate-mesh --mesh "output\terrain\sample_terrain.obj" --report "output\reports\sample.mesh.json"
```

## MCP 서버

stdio MCP 서버는 아래처럼 실행합니다.

```bash
dwg2terrain-mcp
```

노출되는 도구는 다음과 같습니다.

- `doctor`
- `convert`
- `scan`
- `extract`
- `mesh`
- `pipeline`

MCP 레이어는 의도적으로 얇게 유지했고, CLI에서 쓰는 동일한 핵심 함수들을 감싸는 방식입니다.

## ODA 관련 안내

`DWG` 변환은 선택 기능이며, 로컬에 `ODA File Converter`가 설치되어 있어야 합니다.

ODA 실행 파일은 다음 순서로 찾습니다.

1. explicit CLI/MCP `oda_exe`
2. `ODA_FILE_CONVERTER_EXE`
3. common install paths under `C:\Program Files`
4. `PATH`

이미 `DXF`가 있다면 이후 파이프라인은 ODA 없이도 동작합니다.

## 블렌더 관련 안내

지형 메쉬 단계는 `OBJ`를 출력합니다. 실제로는 등고선이 정리된 뒤 고해상도 블렌더용 설정으로 내보낼 때 가장 안정적인 결과를 얻기 쉽습니다.

## 개발

```bash
python -m pip install -e .[dev]
pytest -q
python -m build
python -m twine check dist/*
```
