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

Discover the official Fluent workflow templates:

```powershell
ansysctl list-workflows fluent
ansysctl describe-workflow fluent.steady_run
ansysctl describe-workflow fluent.reflow_melting
```

Start a Fluent workflow run from an existing case or mesh:

```powershell
ansysctl start-workflow fluent.steady_run --spec .\examples\workflows\fluent\steady_run.yaml --workspace .\runs\steady-demo
ansysctl start-workflow fluent.reflow_melting --spec .\examples\workflows\fluent\reflow_melting.yaml --workspace .\runs\reflow-demo
ansysctl get-workflow-run <run_id>
ansysctl cancel-workflow-run <run_id>
```

Call adapters directly:

```powershell
ansysctl call fluent version
ansysctl call workbench version
ansysctl call fluent describe --param path=setup.general
ansysctl call fluent scheme --profile expert --option allow_raw_actions=true --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent start_transcript --param file_name="outputs/fluent.txt"
ansysctl call fluent version --workspace .\runs\fluent-session-01
```

Run the low-level product example plans only when you want manual action sequencing:

```powershell
ansysctl run-plan .\examples\products\fluent\version.yaml
ansysctl run-plan .\examples\products\fluent\version_and_scheme.yaml
ansysctl run-plan .\examples\products\workbench\version.yaml
```

## Profiles and action policy

The bridge has two execution profiles:

- `safe`: default. Only typed actions are allowed and safe file actions are restricted to the workspace plus `outputs\` unless extra roots are provided.
- `expert`: opt-in. Unlocks expert actions, but raw script, Scheme, TUI, and callable-path execution still require `allow_raw_actions=true`.

Examples:

```powershell
ansysctl call fluent scheme --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent scheme --profile expert --option allow_raw_actions=true --param mode=string_eval --param command="(cx-version)"
ansysctl call fluent write_case --param file_name="outputs\case.cas.h5"
ansysctl call fluent write_case --allowed-root "D:\ExternalCases" --param file_name="D:\ExternalCases\case.cas.h5"
```

The first `scheme` call fails fast because it tries an expert-only action in the safe profile.
Even in expert mode, raw actions require the explicit session option `allow_raw_actions=true`.

## Adapter actions

The Fluent adapter exposes typed safe actions plus raw expert actions:

- Safe: `version`, `describe`, `get_state`, `set_state`, `read_case`, `read_case_data`, `read_mesh`, `write_case`, `write_case_data`, `write_data`, `start_transcript`, `stop_transcript`, `hybrid_initialize`, `iterate`, `initialize_solution`, `run_iterations`, `run_time_steps`, `collect_reports`, `export_results`, `checkpoint_case_data`, `get_solver_health`
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

## Fluent workflow templates

Fluent is the first product with an official high-level workflow surface.
These workflow runs are the preferred API for real solves because they own their own Fluent session,
write file-backed run metadata, and support asynchronous polling plus cooperative cancellation.

Supported workflows:

- `fluent.steady_run`
  - Start from an existing `mesh`, `case`, or `case_data`
  - Apply curated setup changes
  - Initialize the solver
  - Run chunked steady iterations
  - Collect reports, export images, and write final case-data
- `fluent.reflow_melting`
  - Start from an existing `mesh` or `case`
  - Apply multiphase, VOF, wall adhesion, and melting-related state changes
  - Run chunked transient time steps with optional checkpoints
  - Collect reports, export images, and write final case-data

Workflow runs always open their own Fluent session and close it on success, failure, or cancellation.
They do not reuse `open_session` persistent sessions.
Cancellation is cooperative and only takes effect at iteration/time-step chunk boundaries.

Each workflow spec is strict and uses a typed structure instead of raw Scheme or TUI:

- `source`
- `setup` or `physics`/`zones`
- `solve`
- `outputs`

The `setup`, `physics`, and `zones` blocks are lists of `{path, state}` changes grouped by section.
See the example specs under `examples\workflows\fluent\`.

These examples are intentionally workflow-first:

- [steady_run.yaml](examples/workflows/fluent/steady_run.yaml)
- [reflow_melting.yaml](examples/workflows/fluent/reflow_melting.yaml)

Fluent workflow v1 does not include:

- geometry import or meshing
- Workbench handoff
- chemistry, flux, or IMC growth modeling
- Mechanical handoff after reflow
- hard mid-call interrupts

Those are deferred to later milestones.

## CLI structure

- `ansysctl env`: report Python and local Ansys installation details
- `ansysctl adapters`: list which adapters are currently usable, their maturity, and which actions are safe vs expert
- `ansysctl call <adapter> <action>`: run one action with optional `--profile`, `--workspace`, `--allowed-root`, `--option`, and `--param`
- `ansysctl list-workflows [product]`: list high-level workflow templates
- `ansysctl describe-workflow <name>`: inspect one workflow template
- `ansysctl start-workflow <name> --spec <path>`: start an asynchronous workflow-owned run
- `ansysctl get-workflow-run <run_id>`: inspect workflow progress, recent events, outputs, and summary
- `ansysctl cancel-workflow-run <run_id>`: request cooperative cancellation for a workflow run
- `ansysctl run-plan <file>`: execute a low-level YAML or JSON action plan

`ansysctl call` and `ansysctl run-plan` now emit YAML by default for readable terminal output.
Add `--json` when another tool needs machine-readable output.

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
      allow_raw_actions: true
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
Session launch options must now live under `options`; hidden top-level option fallback is rejected.

Step params can also reference prior step results or session metadata:

```yaml
steps:
  - session: fluent_main
    action: start_transcript
    label: transcript_start
    params:
      file_name: ${sessions.fluent_main.workspace}/outputs/session.log

  - session: fluent_main
    action: set_state
    params:
      path: file.start_transcript
      state:
        file_name: ${steps.transcript_start.data.params.file_name}
```

References support:

- `${sessions.<handle>.workspace}`
- `${sessions.<handle>.adapter}`
- `${steps.<label>.data...}`
- `${steps.<label>.ok}` / `${steps.<label>.error}`

Step labels are now treated as reference keys, so they must be unique within a plan and may not contain `.`.

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
- `list_workflows`
- `describe_workflow`
- `start_workflow`
- `list_workflow_runs`
- `get_workflow_run`
- `cancel_workflow_run`

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
Raw expert actions are also appended to `raw-actions.jsonl` in that broker state directory by default.
Remote sessions owned by another live process are preserved in broker metadata and still count toward session limits,
but they cannot be closed from a different process until adapter-specific reattach support exists.

Workflow run metadata is also file-backed under `workflow-runs\` in that broker state directory.
Each run stores:

- `run.json`
- `spec.yaml`
- `program.json`
- `events.jsonl`
- `worker.log`

The output directory for a workflow run defaults to `${workspace}\outputs\workflow-runs\<run_id>\`.

Recommended agent flow for Fluent:

1. `describe_actions(adapter="fluent", profile="safe")`
2. `open_session(adapter="fluent", profile="safe")`
3. `get_session(session_id=...)`
4. `execute_session(..., action="describe", params={"path":"setup.general"})`
5. `execute_session(..., action="set_state" | "start_transcript" | "iterate", ...)`
6. `close_session(...)`

Raw control requires an explicit expert session:

1. `open_session(adapter="fluent", profile="expert", options={"allow_raw_actions": true})`
2. `execute_session(..., action="scheme" | "tui" | "command", ...)`
3. `close_session(...)`

Recommended agent flow for official Fluent workflows:

1. `list_workflows(product="fluent")`
2. `describe_workflow(name="fluent.steady_run" | "fluent.reflow_melting")`
3. `start_workflow(...)`
4. `get_workflow_run(run_id=...)`
5. `cancel_workflow_run(run_id=...)` when needed

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
- `ansysctl list-workflows fluent`: verified
- `ansysctl describe-workflow fluent.steady_run`: verified
- `ansysctl call fluent scheme` in safe mode: verified to fail fast before launch
- `ansysctl call fluent scheme --profile expert --option allow_raw_actions=true`: verified
- `ansysctl call workbench version`: verified
- MCP-style persistent Workbench `open_session` / `get_session` / `close_session`: verified
- `python -m unittest discover -s tests -v`: currently passing
- official workflow metadata and worker lifecycle: covered by unit and interface tests
- `mechanical_smoke_test.py`: launch attempt starts licensing, but the local gRPC port does not come up yet

## Notes

- These tools assume the local Ansys Student installation exposes `AWP_ROOT261`.
- Fluent is the strongest first target because PyFluent supports both high-level settings and raw TUI/Scheme execution.
- `ansysctl adapters` reports maturity so external agents can treat Workbench and Mechanical as more experimental surfaces.
- Declarative plans now support named session handles, so one workflow can keep multiple sessions for the same product alive.
- Fluent launch is serialized with both in-process and broker file locks so separate `ansysctl` processes coordinate on startup.
- Official Fluent workflows run only in the safe profile and do not require raw-action opt-in.
- Reflow workflow v1 targets solver-side VOF/melting reproduction only; chemistry and Mechanical handoff remain v2 work.
- Mechanical support is wired into the CLI, but local launch still needs extra investigation on this machine.
- Mechanical local launch defaults to a single attempt because partially started launches can consume the Student demo seat.
