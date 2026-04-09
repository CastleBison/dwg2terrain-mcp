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

## 다른 컴퓨터에서 처음 시작하기

다른 컴퓨터에서 바로 검증까지 진행하려면 저장소를 받은 뒤 아래 순서로 시작하는 편이 가장 안전합니다.

1. Python 3.11+ 환경을 준비합니다.
2. `python -m pip install -e .` 로 패키지를 설치합니다.
3. `DXF`가 있다면 먼저 `DXF` 기준으로 `doctor -> scan -> extract -> mesh` 흐름을 검증합니다.
4. `DWG` 입력을 다룰 예정이면 그다음 `ODA File Converter` 설치 여부를 확인하고 `doctor -> run -> mesh` 또는 MCP `pipeline`까지 검증합니다.

CLI 기준 첫 점검 예시는 아래와 같습니다.

```bash
dwg2terrain doctor --input "/path/to/sample.dxf" --json
dwg2terrain scan "/path/to/sample.dxf" --json
dwg2terrain extract "/path/to/sample.dxf" --config "config/default.json" --out "work/sample/sample_contours.dxf" --json
dwg2terrain mesh "work/sample/sample_contours.dxf" --config "config/mesh.highres.json" --out "work/sample/sample_terrain.obj" --json
```

`DWG`를 바로 검증할 때는 아래처럼 `run` 다음 `mesh`를 붙여서 확인하면 됩니다.

```bash
dwg2terrain doctor --input "/path/to/sample.dwg" --json
dwg2terrain run "/path/to/sample.dwg" --converted "work/sample/converted.dxf" --out "work/sample/sample_contours.dxf" --json
dwg2terrain mesh "work/sample/sample_contours.dxf" --config "config/mesh.highres.json" --out "work/sample/sample_terrain.obj" --json
```

`DXF`가 이미 준비되어 있다면 `convert` 단계와 ODA 설치는 건너뛰고 `scan`, `extract`, `mesh` 중심으로 진행하면 됩니다. MCP 클라이언트에서는 같은 목적을 `pipeline` 도구로 한 번에 실행할 수 있습니다.

터미널 접근이 가능한 AI 에이전트에 설치부터 초기 검증까지 한 번에 맡기고 싶다면 아래처럼 시작하면 됩니다.

```text
이 저장소를 설치하고 초기 검증해줘.
운영체제는 [Windows/macOS/Linux]이고, 입력 파일은 [파일 경로], 출력 폴더는 [폴더 경로]야.
1. Python 3.11+인지 확인
2. 저장소 루트에서 `python -m pip install -e .` 실행
3. 입력이 `.dwg`이면 ODA File Converter 설치 여부를 먼저 확인하고, `.dxf`이면 ODA 단계는 건너뛰기
4. CLI 검증은 `doctor -> run -> mesh` 또는 `doctor -> scan -> extract -> mesh` 순서로 수행
5. MCP 클라이언트 검증이 필요하면 `pipeline` 도구까지 실행
6. 실패한 단계가 있으면 원인과 해결 방법 정리
```

`DWG` 대신 `DXF`만 사용할 경우에는 프롬프트에서 ODA 확인과 `run` 단계를 생략해도 됩니다.

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
