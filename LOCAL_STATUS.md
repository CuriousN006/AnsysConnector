# 로컬 상태

이 파일은 현재 working copy에 대한 이 컴퓨터 전용 검증 기록입니다. 다른 Ansys
설치 환경에서도 동일하게 동작한다는 일반적인 보장은 아닙니다.

## 이 컴퓨터에서 검증된 항목

- `ansys_env_check.py`: 통과
- `fluent_smoke_test.py`: Ansys Fluent 2026 R1 기준 통과
- `workbench_smoke_test.py`: Workbench server version 261 기준 통과
- `ansysctl call fluent version`: 검증됨
- `ansysctl list-workflows fluent`: 검증됨
- `ansysctl describe-workflow fluent.steady_run`: 검증됨
- `ansysctl call fluent scheme` in safe mode: launch 전에 빠르게 실패하는 것 확인
- `ansysctl call fluent scheme --profile expert --option allow_raw_actions=true`: 검증됨
- `ansysctl call workbench version`: 검증됨
- MCP 방식의 persistent Workbench `open_session` / `get_session` / `close_session`: 검증됨
- 공식 workflow metadata와 worker lifecycle: unit 및 interface test로 커버됨

## 알려진 로컬 공백

- `mechanical_smoke_test.py`: launch 시 licensing은 시작되지만 로컬 gRPC port가
  아직 올라오지 않습니다.
- Mechanical support는 CLI에 연결되어 있지만, 이 컴퓨터의 local launch는 추가
  조사가 필요합니다.
- Mechanical local launch는 기본 retry가 1회입니다. 부분적으로 시작된 launch가
  Student demo seat를 점유할 수 있기 때문입니다.

## 로컬 가정

- 로컬 Ansys Student 설치가 `AWP_ROOT261`을 노출합니다.
- Fluent는 high-level settings와 raw TUI/Scheme 실행을 모두 지원하므로 현재
  가장 강한 target입니다.
- Workbench와 Mechanical은 이 milestone에서 experimental surface로 남아
  있습니다.
