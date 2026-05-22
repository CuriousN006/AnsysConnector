# AnsysConnector

Ansys 제품을 로컬에서 자동화하기 위한 범용 브리지입니다.

AnsysConnector는 로컬 Ansys 설치 환경을 점검하고, 관리형 제품 세션을 열고,
안전한 typed action을 실행하고, 파일 기반 Fluent workflow를 시작할 수 있는
CLI와 MCP 서버를 제공합니다.

현재 가장 성숙한 adapter는 Fluent입니다. Workbench와 Mechanical은 더 작은
실험적 기능 표면으로 제공됩니다.

## 프로젝트 구조

- `src/ansys_connector/core/`: 환경 감지, action policy, 관리형 세션, 실행 로직
- `src/ansys_connector/interfaces/`: CLI와 MCP 진입점
- `src/ansys_connector/products/`: 제품 adapter와 live session wrapper
- `src/ansys_connector/workflows/`: 선언형 plan과 고수준 workflow template
- `examples/`: 제품 action plan과 Fluent workflow spec
- `scripts/diagnostics/`: 로컬 환경 점검 및 smoke test helper

기존 import와 console entrypoint가 계속 동작하도록
`src/ansys_connector/`와 `src/ansys_connector/adapters/` 아래의 예전 경로에는
호환 shim이 남아 있습니다.

## 설치

Python 3.12 이상 환경을 만들고 활성화한 뒤, 패키지를 editable mode로
설치합니다.

```powershell
python -m pip install -e .
```

`requirements.txt` 기반으로 설치하려면 다음을 실행합니다.

```powershell
python -m pip install -r requirements.txt
```

이 프로젝트는 자동화하려는 제품에 맞는 PyAnsys 패키지와, `AWP_ROOT261`처럼
`AWP_ROOT...` 환경 변수를 노출하는 로컬 Ansys 설치를 전제로 합니다.

## 빠른 시작

로컬 환경과 사용 가능한 adapter를 확인합니다.

```powershell
ansysctl env
ansysctl adapters
```

안전한 adapter action을 호출합니다.

```powershell
ansysctl call fluent version
ansysctl call workbench version
ansysctl call fluent describe --param path=setup.general
```

기존 case 또는 mesh에서 Fluent workflow를 시작합니다.

```powershell
ansysctl list-workflows fluent
ansysctl describe-workflow fluent.steady_run
ansysctl start-workflow fluent.steady_run --spec .\examples\workflows\fluent\steady_run.yaml --workspace .\runs\steady-demo
ansysctl get-workflow-run <run_id>
```

수동 action sequencing이 필요할 때만 저수준 action plan을 실행합니다.

```powershell
ansysctl run-plan .\examples\products\fluent\version.yaml
ansysctl run-plan .\examples\products\workbench\version.yaml
```

## Adapter 성숙도

| Adapter | 성숙도 | Safe actions | Expert actions |
| --- | --- | --- | --- |
| Fluent | beta | solver, file, report, export, workflow 중심의 넓은 typed surface | `scheme`, `tui`, `command` |
| Workbench | experimental | `version` | `script` |
| Mechanical | experimental | `version` | `python` |

현재 설치 환경에서 노출되는 정확한 action 목록은 `ansysctl adapters`로 확인합니다.

## 안전 모델

브리지는 두 가지 실행 profile을 사용합니다.

- `safe`: 기본값입니다. typed action만 허용합니다. 안전한 file action은 세션
  workspace와 `outputs/`, 그리고 명시적으로 전달한 `--allowed-root` 값
  안으로 제한됩니다.
- `expert`: opt-in profile입니다. expert action을 열지만, raw script, Scheme,
  TUI, callable-path 실행은 여전히 `allow_raw_actions=true`가 필요합니다.

예시:

```powershell
ansysctl call fluent scheme --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent scheme --profile expert --option allow_raw_actions=true --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent write_case --param file_name="outputs\case.cas.h5"
ansysctl call fluent write_case --allowed-root "D:\ExternalCases" --param file_name="D:\ExternalCases\case.cas.h5"
```

첫 번째 `scheme` 호출은 safe profile에서 expert-only action을 요청하므로 즉시
실패합니다. Raw expert action은 기본적으로 broker state directory의
`raw-actions.jsonl`에도 기록됩니다.

## Fluent Workflow

Fluent는 공식 고수준 workflow template이 가장 먼저 제공된 제품입니다.
Workflow run은 자체 Fluent 세션을 소유하고, run metadata를 파일로 저장하며,
비동기 polling과 cooperative cancellation을 지원합니다.

지원 workflow:

- `fluent.steady_run`
  - `mesh`, `case`, `case_data`에서 시작
  - curated setup change 적용
  - solver 초기화
  - chunk 단위 steady iteration 실행
  - report 수집, image export, final case-data 작성
- `fluent.reflow_melting`
  - `mesh` 또는 `case`에서 시작
  - multiphase, VOF, wall adhesion, melting 관련 state change 적용
  - optional checkpoint와 함께 chunk 단위 transient time step 실행
  - report 수집, image export, final case-data 작성

Workflow spec은 raw Scheme이나 TUI 대신 typed section을 사용하는 엄격한
구조입니다.

- `source`
- `setup` 또는 `physics`/`zones`
- `solve`
- `outputs`

예시:

- [steady_run.yaml](examples/workflows/fluent/steady_run.yaml)
- [reflow_melting.yaml](examples/workflows/fluent/reflow_melting.yaml)

Workflow v1에는 geometry import, meshing, Workbench handoff, Mechanical
handoff, chemistry, flux, IMC growth modeling, hard mid-call interrupt가
포함되어 있지 않습니다.

## Plan

선언형 plan은 하나 이상의 named session을 유지하면서 여러 step을 실행할 수
있습니다.

```yaml
sessions:
  fluent_main:
    adapter: fluent
    profile: expert
    workspace: runs/fluent-session-01
    allowed_roots:
      - outputs
    options:
      allow_raw_actions: true
      processor_count: 2
      ui_mode: no_gui
steps:
  - session: fluent_main
    action: start_transcript
    label: transcript_start
    params:
      file_name: ${sessions.fluent_main.workspace}/outputs/session.log
```

Step object는 `session`, `action`, `params`, `label`,
`continue_on_error`만 허용합니다. Label은 reference key로 쓰이므로 plan 안에서
고유해야 하며 `.`을 포함할 수 없습니다.

지원 reference:

- `${sessions.<handle>.workspace}`
- `${sessions.<handle>.adapter}`
- `${steps.<label>.data...}`
- `${steps.<label>.ok}` 및 `${steps.<label>.error}`

이전 호환성을 위해 legacy `adapters`와 step-level `adapter` key도 아직
허용하지만, 새 plan은 `sessions`와 `session`을 사용하는 편이 좋습니다.

## MCP 서버

MCP 서버를 stdio로 시작합니다.

```powershell
ansysctl-mcp
```

MCP 서버는 다음 tool을 제공합니다.

- `environment`
- `adapters`
- `describe_actions`
- `open_session`
- `list_sessions`
- `get_session`
- `execute_session`
- `close_session`
- `call_once`
- `run_plan`
- `list_workflows`
- `describe_workflow`
- `start_workflow`
- `list_workflow_runs`
- `get_workflow_run`
- `cancel_workflow_run`

관리형 session metadata는 파일 기반으로 저장되므로 프로세스 재시작 후에도
`orphaned` 상태로 다시 발견할 수 있습니다. 기본 broker state 경로는 Windows의
`%LOCALAPPDATA%\AnsysConnector\broker`, 그 외 환경의
`~/.ansys_connector/broker`입니다. `ANSYS_CONNECTOR_STATE_DIR`로 경로를
override할 수 있습니다.

Workflow metadata도 같은 broker state directory의 `workflow-runs/` 아래에
저장됩니다. 각 run은 `run.json`, `spec.yaml`, `program.json`,
`events.jsonl`, `worker.log`를 저장합니다.

## 진단

환경 점검을 실행합니다.

```powershell
python .\scripts\diagnostics\ansys_env_check.py
```

제품별 smoke test를 실행합니다.

```powershell
python .\scripts\diagnostics\fluent_smoke_test.py
python .\scripts\diagnostics\workbench_smoke_test.py
python .\scripts\diagnostics\mechanical_smoke_test.py
```

이 컴퓨터에 특화된 검증 기록은 공개 README에 섞지 않습니다. 현재 working copy의
최신 로컬 상태는 [LOCAL_STATUS.md](LOCAL_STATUS.md)를 확인하세요.
