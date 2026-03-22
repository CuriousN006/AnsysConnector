# AnsysConnector

Generic local automation tooling for Ansys products.

The project is now organized around four internal layers:

- `src/ansys_connector/core/`: environment detection, policy, managed sessions, execution
- `src/ansys_connector/interfaces/`: CLI and MCP entrypoints
- `src/ansys_connector/products/`: product adapters and per-product session logic
- `src/ansys_connector/workflows/`: declarative plans and future workflow templates

Compatibility shims remain in the old module paths under `src/ansys_connector/` and `src/ansys_connector/adapters/`, so existing imports and console entrypoints continue to work.

## What is set up

- A local virtual environment at `.\.venv`
- PyAnsys client packages for Fluent, Mechanical, and Workbench
- A Python package under `src\ansys_connector`
- Product examples under `examples\products\`
- Diagnostics under `scripts\diagnostics\`

## Quick start

Activate the virtual environment in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the local package in editable mode:

```powershell
python -m pip install -e .
```

Inspect the detected environment:

```powershell
ansysctl env
ansysctl adapters
```

Run the product example plans:

```powershell
ansysctl run-plan .\examples\products\fluent\version.yaml
ansysctl run-plan .\examples\products\fluent\version_and_scheme.yaml
ansysctl run-plan .\examples\products\workbench\version.yaml
```

Call adapters directly:

```powershell
ansysctl call fluent version
ansysctl call workbench version
ansysctl call fluent describe --param path=setup.general
ansysctl call fluent scheme --profile expert --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent start_transcript --param file_name="outputs/fluent.txt"
ansysctl call fluent version --workspace .\runs\fluent-session-01
```

## Profiles and action policy

The bridge has two execution profiles:

- `safe`: default. Only typed actions are allowed and safe file actions are restricted to the workspace plus `outputs\` unless extra roots are provided.
- `expert`: opt-in. Unlocks raw script, Scheme, TUI, and callable-path execution.

Examples:

```powershell
ansysctl call fluent scheme --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent scheme --profile expert --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent write_case --param file_name="outputs\case.cas.h5"
ansysctl call fluent write_case --allowed-root "D:\ExternalCases" --param file_name="D:\ExternalCases\case.cas.h5"
```

The first `scheme` call fails fast because it tries an expert-only action in the safe profile.

## Adapter actions

The Fluent adapter exposes typed safe actions plus raw expert actions:

- Safe: `version`, `describe`, `get_state`, `set_state`, `read_case`, `read_case_data`, `read_mesh`, `write_case`, `write_case_data`, `write_data`, `start_transcript`, `stop_transcript`, `hybrid_initialize`, `iterate`
- Expert: `scheme`, `tui`, `command`

Use Python-style settings paths such as `setup.general`, `solution.initialization`, or `file.start_transcript`.
`fluent command` now accepts only explicit `path`, `args`, and `kwargs`; implicit top-level kwargs are rejected.

Workbench and Mechanical intentionally keep a smaller safe surface in this milestone:

- Workbench safe: `version`
- Workbench expert: `script`
- Mechanical safe: `version`
- Mechanical expert: `python`

Current adapter maturity:

- Fluent: `beta`
- Workbench: `experimental`
- Mechanical: `experimental`

## CLI structure

- `ansysctl env`: report Python and local Ansys installation details
- `ansysctl adapters`: list which adapters are currently usable, their maturity, and which actions are safe vs expert
- `ansysctl call <adapter> <action>`: run one action with optional `--profile`, `--workspace`, `--allowed-root`, `--option`, and `--param`
- `ansysctl run-plan <file>`: execute a YAML or JSON workflow plan

Plan session config supports `adapter`, `profile`, `workspace`, `allowed_roots`, and `options`:

```yaml
sessions:
  fluent_main:
    adapter: fluent
    profile: expert
    workspace: runs/fluent-session-01
    allowed_roots:
      - outputs
    options:
      processor_count: 2
      ui_mode: no_gui
```

Step objects are strict and only accept:

- `session`
- `action`
- `params`
- `label`
- `continue_on_error`

Legacy `adapters` and step-level `adapter` keys are still accepted for backward compatibility, but new plans should prefer `sessions` and `session`.

## MCP server

Start the MCP server over stdio:

```powershell
.\.venv\Scripts\ansysctl-mcp.exe
```

The MCP server exposes persistent session tools:

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

Managed session metadata includes:

- `profile`
- `workspace`
- `allowed_roots`
- `status`
- `live_session`
- `can_execute`
- `created_at`
- `last_used_at`
- `expires_at`

Broker state is persisted locally so managed sessions can be rediscovered as `orphaned` after a process restart.
By default the broker stores metadata under `%LOCALAPPDATA%\AnsysConnector\broker` on Windows
or `~/.ansys_connector/broker` elsewhere. Set `ANSYS_CONNECTOR_STATE_DIR` to override it.

Recommended agent flow for Fluent:

1. `describe_actions(adapter="fluent", profile="safe")`
2. `open_session(adapter="fluent", profile="safe")`
3. `get_session(session_id=...)`
4. `execute_session(..., action="describe", params={"path":"setup.general"})`
5. `execute_session(..., action="set_state" | "start_transcript" | "iterate", ...)`
6. `close_session(...)`

Raw control requires an explicit expert session:

1. `open_session(adapter="fluent", profile="expert")`
2. `execute_session(..., action="scheme" | "tui" | "command", ...)`
3. `close_session(...)`

## Diagnostics

Run the environment check:

```powershell
python .\scripts\diagnostics\ansys_env_check.py
```

Run individual smoke tests:

```powershell
python .\scripts\diagnostics\fluent_smoke_test.py
python .\scripts\diagnostics\workbench_smoke_test.py
python .\scripts\diagnostics\mechanical_smoke_test.py
```

## Current status on this machine

- `ansys_env_check.py`: passed
- `fluent_smoke_test.py`: passed against Ansys Fluent 2026 R1
- `workbench_smoke_test.py`: passed against Workbench server version 261
- `ansysctl call fluent version`: verified
- `ansysctl call fluent scheme` in safe mode: verified to fail fast before launch
- `ansysctl call fluent scheme --profile expert`: verified
- `ansysctl call workbench version`: verified
- MCP-style persistent Workbench `open_session` / `get_session` / `close_session`: verified
- `python -m unittest discover -s tests -v`: currently passing
- `mechanical_smoke_test.py`: launch attempt starts licensing, but the local gRPC port does not come up yet

## Notes

- These tools assume the local Ansys Student installation exposes `AWP_ROOT261`.
- Fluent is the strongest first target because PyFluent supports both high-level settings and raw TUI/Scheme execution.
- `ansysctl adapters` reports maturity so external agents can treat Workbench and Mechanical as more experimental surfaces.
- Declarative plans now support named session handles, so one workflow can keep multiple sessions for the same product alive.
- Fluent launch is serialized with both in-process and broker file locks so separate `ansysctl` processes coordinate on startup.
- Mechanical support is wired into the CLI, but local launch still needs extra investigation on this machine.
