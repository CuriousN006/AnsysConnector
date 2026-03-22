from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from ansys_connector.products.base import AdapterError

from .models import WorkflowDefinition, WorkflowOperation, WorkflowProgram


_STEADY_ALLOWED_TOP_LEVEL = {"source", "setup", "solve", "outputs"}
_REFLOW_ALLOWED_TOP_LEVEL = {"source", "physics", "zones", "solve", "outputs"}


def _validate_fields(payload: dict[str, Any], allowed: set[str], label: str) -> None:
    extras = sorted(set(payload) - allowed)
    if extras:
        raise AdapterError(f"{label} contains unsupported fields: {', '.join(extras)}")


def _resolve_source_path(path: str, workspace: Path) -> str:
    source = Path(path).expanduser()
    if not source.is_absolute():
        source = workspace / source
    return str(source.resolve(strict=False))


def _normalize_source(payload: Any, workspace: Path, *, allowed_kinds: set[str]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AdapterError("Workflow source must be an object.")
    _validate_fields(payload, {"kind", "path"}, "Workflow source")
    kind = payload.get("kind")
    path = payload.get("path")
    if not isinstance(kind, str) or kind not in allowed_kinds:
        raise AdapterError(f"Workflow source kind must be one of: {', '.join(sorted(allowed_kinds))}")
    if not isinstance(path, str) or not path.strip():
        raise AdapterError("Workflow source requires a non-empty 'path'.")
    return {
        "kind": kind,
        "path": _resolve_source_path(path, workspace),
    }


def _normalize_change_list(payload: Any, label: str) -> list[dict[str, Any]]:
    if payload in (None, []):
        return []
    if not isinstance(payload, list):
        raise AdapterError(f"{label} must be a list of workflow changes.")
    changes: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise AdapterError(f"{label} item {index} must be an object.")
        _validate_fields(item, {"path", "state"}, f"{label} item {index}")
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            raise AdapterError(f"{label} item {index} requires a non-empty 'path'.")
        if "state" not in item:
            raise AdapterError(f"{label} item {index} requires a 'state' payload.")
        changes.append({"path": path.strip(), "state": item["state"]})
    return changes


def _normalize_section_map(payload: Any, label: str, *, allowed: set[str]) -> dict[str, list[dict[str, Any]]]:
    if payload in (None, {}):
        return {}
    if not isinstance(payload, dict):
        raise AdapterError(f"{label} must be an object.")
    _validate_fields(payload, allowed, label)
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key, value in payload.items():
        normalized[key] = _normalize_change_list(value, f"{label}.{key}")
    return normalized


def _normalize_positive_int(payload: dict[str, Any], key: str, label: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AdapterError(f"{label} field '{key}' must be a positive integer.")
    return value


def _normalize_positive_number(payload: dict[str, Any], key: str, label: str) -> float:
    value = payload.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise AdapterError(f"{label} field '{key}' must be a positive number.")
    return float(value)


def _normalize_optional_positive_int(payload: dict[str, Any], key: str, label: str, *, default: int) -> int:
    if key not in payload:
        return default
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AdapterError(f"{label} field '{key}' must be a positive integer.")
    return value


def _normalize_transcript_output(payload: Any) -> dict[str, Any]:
    if payload is False:
        return {"enabled": False, "file_name": None}
    if payload in (None, True):
        return {"enabled": True, "file_name": None}
    if isinstance(payload, str):
        return {"enabled": True, "file_name": payload}
    if not isinstance(payload, dict):
        raise AdapterError("Workflow outputs.transcript must be false, true, a path, or an object.")
    _validate_fields(payload, {"enabled", "file_name"}, "Workflow outputs.transcript")
    enabled = bool(payload.get("enabled", True))
    file_name = payload.get("file_name")
    if file_name is not None and not isinstance(file_name, str):
        raise AdapterError("Workflow outputs.transcript.file_name must be a string.")
    return {"enabled": enabled, "file_name": file_name}


def _normalize_file_output(payload: Any, label: str) -> dict[str, Any]:
    if payload is False:
        return {"enabled": False, "file_name": None}
    if payload in (None, True):
        return {"enabled": False if payload is None else True, "file_name": None}
    if isinstance(payload, str):
        return {"enabled": True, "file_name": payload}
    if not isinstance(payload, dict):
        raise AdapterError(f"{label} must be false, true, a path, or an object.")
    _validate_fields(payload, {"enabled", "file_name"}, label)
    enabled = bool(payload.get("enabled", True))
    file_name = payload.get("file_name")
    if file_name is not None and not isinstance(file_name, str):
        raise AdapterError(f"{label}.file_name must be a string.")
    return {"enabled": enabled, "file_name": file_name}


def _normalize_reports(payload: Any) -> list[dict[str, Any]]:
    if payload in (None, []):
        return []
    if not isinstance(payload, list):
        raise AdapterError("Workflow outputs.reports must be a list.")
    reports: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise AdapterError(f"Workflow outputs.reports item {index} must be an object.")
        _validate_fields(item, {"name", "command_path", "args", "kwargs"}, f"Workflow outputs.reports item {index}")
        name = item.get("name")
        command_path = item.get("command_path")
        if not isinstance(name, str) or not name.strip():
            raise AdapterError(f"Workflow outputs.reports item {index} requires 'name'.")
        if not isinstance(command_path, str) or not command_path.startswith("results.report."):
            raise AdapterError(
                f"Workflow outputs.reports item {index} must use a command_path under 'results.report.'."
            )
        args = item.get("args", [])
        kwargs = item.get("kwargs", {})
        if not isinstance(args, list):
            raise AdapterError(f"Workflow outputs.reports item {index} field 'args' must be a list.")
        if not isinstance(kwargs, dict):
            raise AdapterError(f"Workflow outputs.reports item {index} field 'kwargs' must be an object.")
        reports.append(
            {
                "name": name.strip(),
                "command_path": command_path,
                "args": list(args),
                "kwargs": dict(kwargs),
            }
        )
    return reports


def _normalize_images(payload: Any) -> list[dict[str, Any]]:
    if payload in (None, []):
        return []
    if not isinstance(payload, list):
        raise AdapterError("Workflow outputs.images must be a list.")
    images: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise AdapterError(f"Workflow outputs.images item {index} must be an object.")
        _validate_fields(item, {"name", "kind", "file_name", "picture_state", "contour"}, f"Workflow outputs.images item {index}")
        name = item.get("name")
        file_name = item.get("file_name")
        kind = str(item.get("kind", "picture"))
        if not isinstance(name, str) or not name.strip():
            raise AdapterError(f"Workflow outputs.images item {index} requires 'name'.")
        if not isinstance(file_name, str) or not file_name.strip():
            raise AdapterError(f"Workflow outputs.images item {index} requires 'file_name'.")
        if kind not in {"picture", "contour"}:
            raise AdapterError(f"Workflow outputs.images item {index} kind must be 'picture' or 'contour'.")
        picture_state = item.get("picture_state", {})
        if not isinstance(picture_state, dict):
            raise AdapterError(f"Workflow outputs.images item {index} field 'picture_state' must be an object.")
        normalized: dict[str, Any] = {
            "name": name.strip(),
            "kind": kind,
            "file_name": file_name,
            "picture_state": dict(picture_state),
        }
        if "contour" in item:
            contour = item["contour"]
            if not isinstance(contour, dict):
                raise AdapterError(f"Workflow outputs.images item {index} contour must be an object.")
            _validate_fields(contour, {"object_name", "state"}, f"Workflow outputs.images item {index}.contour")
            object_name = contour.get("object_name")
            if not isinstance(object_name, str) or not object_name.strip():
                raise AdapterError(f"Workflow outputs.images item {index} contour requires 'object_name'.")
            state = contour.get("state", {})
            if not isinstance(state, dict):
                raise AdapterError(f"Workflow outputs.images item {index} contour state must be an object.")
            normalized["contour"] = {"object_name": object_name.strip(), "state": dict(state)}
        images.append(normalized)
    return images


def _normalize_checkpoints(payload: Any) -> dict[str, Any]:
    if payload in (None, False):
        return {"enabled": False, "every_chunks": None, "file_name_template": None}
    if payload is True:
        return {"enabled": True, "every_chunks": 1, "file_name_template": None}
    if not isinstance(payload, dict):
        raise AdapterError("Workflow outputs.checkpoints must be false, true, or an object.")
    _validate_fields(payload, {"enabled", "every_chunks", "file_name_template"}, "Workflow outputs.checkpoints")
    enabled = bool(payload.get("enabled", True))
    every_chunks = payload.get("every_chunks", 1 if enabled else None)
    if every_chunks is not None and (not isinstance(every_chunks, int) or isinstance(every_chunks, bool) or every_chunks <= 0):
        raise AdapterError("Workflow outputs.checkpoints.every_chunks must be a positive integer.")
    file_name_template = payload.get("file_name_template")
    if file_name_template is not None and not isinstance(file_name_template, str):
        raise AdapterError("Workflow outputs.checkpoints.file_name_template must be a string.")
    return {"enabled": enabled, "every_chunks": every_chunks, "file_name_template": file_name_template}


def _normalize_outputs(payload: Any) -> dict[str, Any]:
    if payload in (None, {}):
        payload = {}
    if not isinstance(payload, dict):
        raise AdapterError("Workflow outputs must be an object.")
    _validate_fields(
        payload,
        {"transcript", "final_case", "final_case_data", "checkpoints", "reports", "images"},
        "Workflow outputs",
    )
    return {
        "transcript": _normalize_transcript_output(payload.get("transcript")),
        "final_case": _normalize_file_output(payload.get("final_case"), "Workflow outputs.final_case"),
        "final_case_data": _normalize_file_output(payload.get("final_case_data", True), "Workflow outputs.final_case_data"),
        "checkpoints": _normalize_checkpoints(payload.get("checkpoints")),
        "reports": _normalize_reports(payload.get("reports")),
        "images": _normalize_images(payload.get("images")),
    }


def _resolve_output_file(output_dir: Path, configured: str | None, default_name: str) -> str:
    target = Path(configured) if configured else Path(default_name)
    if not target.is_absolute():
        target = output_dir / target
    return str(target.resolve(strict=False))


def _changes_to_operations(blocks: dict[str, list[dict[str, Any]]], phase_prefix: str) -> list[WorkflowOperation]:
    operations: list[WorkflowOperation] = []
    for block_name, changes in blocks.items():
        for change in changes:
            operations.append(
                WorkflowOperation(
                    phase=f"{phase_prefix}.{block_name}",
                    action="set_state",
                    params={"path": change["path"], "state": change["state"]},
                )
            )
    return operations


def load_fluent_steady_run_spec(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AdapterError("Workflow spec must be an object.")
    _validate_fields(payload, _STEADY_ALLOWED_TOP_LEVEL, "fluent.steady_run spec")
    solve = payload.get("solve")
    if not isinstance(solve, dict):
        raise AdapterError("fluent.steady_run solve block must be an object.")
    _validate_fields(solve, {"initialization", "iterations", "iteration_chunk_size"}, "fluent.steady_run.solve")
    initialization = str(solve.get("initialization", "hybrid"))
    if initialization not in {"hybrid", "standard"}:
        raise AdapterError("fluent.steady_run solve.initialization must be 'hybrid' or 'standard'.")
    return {
        "source": _normalize_source(payload.get("source"), workspace, allowed_kinds={"mesh", "case", "case_data"}),
        "setup": _normalize_section_map(
            payload.get("setup"),
            "fluent.steady_run.setup",
            allowed={"models", "materials", "cell_zones", "boundary_conditions", "reference_values"},
        ),
        "solve": {
            "initialization": initialization,
            "iterations": _normalize_positive_int(solve, "iterations", "fluent.steady_run.solve"),
            "iteration_chunk_size": _normalize_optional_positive_int(
                solve,
                "iteration_chunk_size",
                "fluent.steady_run.solve",
                default=50,
            ),
        },
        "outputs": _normalize_outputs(payload.get("outputs")),
    }


def load_fluent_reflow_melting_spec(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise AdapterError("Workflow spec must be an object.")
    _validate_fields(payload, _REFLOW_ALLOWED_TOP_LEVEL, "fluent.reflow_melting spec")
    solve = payload.get("solve")
    if not isinstance(solve, dict):
        raise AdapterError("fluent.reflow_melting solve block must be an object.")
    _validate_fields(
        solve,
        {"initialization", "time_step_size", "step_count", "max_iterations_per_step", "time_step_chunk_size"},
        "fluent.reflow_melting.solve",
    )
    initialization = str(solve.get("initialization", "hybrid"))
    if initialization not in {"hybrid", "standard"}:
        raise AdapterError("fluent.reflow_melting solve.initialization must be 'hybrid' or 'standard'.")
    return {
        "source": _normalize_source(payload.get("source"), workspace, allowed_kinds={"mesh", "case"}),
        "physics": _normalize_section_map(
            payload.get("physics"),
            "fluent.reflow_melting.physics",
            allowed={"energy", "multiphase", "phases", "surface_tension", "wall_adhesion", "melting"},
        ),
        "zones": _normalize_section_map(
            payload.get("zones"),
            "fluent.reflow_melting.zones",
            allowed={"materials", "boundary_conditions", "operating_conditions", "gravity", "patch"},
        ),
        "solve": {
            "initialization": initialization,
            "time_step_size": _normalize_positive_number(solve, "time_step_size", "fluent.reflow_melting.solve"),
            "step_count": _normalize_positive_int(solve, "step_count", "fluent.reflow_melting.solve"),
            "max_iterations_per_step": _normalize_positive_int(
                solve, "max_iterations_per_step", "fluent.reflow_melting.solve"
            ),
            "time_step_chunk_size": _normalize_optional_positive_int(
                solve,
                "time_step_chunk_size",
                "fluent.reflow_melting.solve",
                default=1,
            ),
        },
        "outputs": _normalize_outputs(payload.get("outputs")),
    }


def compile_fluent_steady_run(spec: dict[str, Any], output_dir: Path) -> WorkflowProgram:
    source_action = {
        "mesh": "read_mesh",
        "case": "read_case",
        "case_data": "read_case_data",
    }[spec["source"]["kind"]]
    outputs = spec["outputs"]
    operations: list[WorkflowOperation] = [
        WorkflowOperation(phase="source", action=source_action, params={"file_name": spec["source"]["path"]}),
        *_changes_to_operations(spec["setup"], "setup"),
        WorkflowOperation(
            phase="initialization",
            action="initialize_solution",
            params={"method": spec["solve"]["initialization"]},
        ),
        WorkflowOperation(
            phase="solve",
            action="run_iterations",
            params={"count": spec["solve"]["iterations"]},
            mode="iterations",
            total=spec["solve"]["iterations"],
            chunk_size=spec["solve"]["iteration_chunk_size"],
            report_requests=outputs["reports"],
        ),
    ]

    if outputs["reports"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.reports",
                action="collect_reports",
                params={"reports": outputs["reports"]},
            )
        )
    if outputs["images"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.images",
                action="export_results",
                params={
                    "images": [
                        {
                            **image,
                            "file_name": _resolve_output_file(output_dir, image.get("file_name"), f"{image['name']}.png"),
                        }
                        for image in outputs["images"]
                    ]
                },
            )
        )
    if outputs["final_case"]["enabled"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.final_case",
                action="write_case",
                params={"file_name": _resolve_output_file(output_dir, outputs["final_case"]["file_name"], "final.cas.h5")},
            )
        )
    if outputs["final_case_data"]["enabled"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.final_case_data",
                action="write_case_data",
                params={
                    "file_name": _resolve_output_file(
                        output_dir,
                        outputs["final_case_data"]["file_name"],
                        "final-data.cas.h5",
                    )
                },
            )
        )

    transcript = outputs["transcript"]
    if transcript["enabled"]:
        transcript = {
            "enabled": True,
            "file_name": _resolve_output_file(output_dir, transcript["file_name"], "transcript.log"),
        }
    return WorkflowProgram(
        workflow="fluent.steady_run",
        operations=operations,
        transcript=transcript if transcript["enabled"] else None,
    )


def compile_fluent_reflow_melting(spec: dict[str, Any], output_dir: Path) -> WorkflowProgram:
    source_action = {"mesh": "read_mesh", "case": "read_case"}[spec["source"]["kind"]]
    outputs = spec["outputs"]
    checkpoints = outputs["checkpoints"]
    operations: list[WorkflowOperation] = [
        WorkflowOperation(phase="source", action=source_action, params={"file_name": spec["source"]["path"]}),
        *_changes_to_operations(spec["physics"], "physics"),
        *_changes_to_operations(spec["zones"], "zones"),
        WorkflowOperation(
            phase="initialization",
            action="initialize_solution",
            params={"method": spec["solve"]["initialization"]},
        ),
        WorkflowOperation(
            phase="solve",
            action="run_time_steps",
            params={
                "step_count": spec["solve"]["step_count"],
                "max_iterations_per_step": spec["solve"]["max_iterations_per_step"],
                "time_step_size": spec["solve"]["time_step_size"],
            },
            mode="time_steps",
            total=spec["solve"]["step_count"],
            chunk_size=spec["solve"]["time_step_chunk_size"],
            checkpoint_every=checkpoints["every_chunks"] if checkpoints["enabled"] else None,
            checkpoint_template=_resolve_output_file(
                output_dir,
                checkpoints["file_name_template"],
                "checkpoint-step-{completed_steps:04d}.cas.h5",
            )
            if checkpoints["enabled"]
            else None,
            report_requests=outputs["reports"],
        ),
    ]

    if outputs["reports"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.reports",
                action="collect_reports",
                params={"reports": outputs["reports"]},
            )
        )
    if outputs["images"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.images",
                action="export_results",
                params={
                    "images": [
                        {
                            **image,
                            "file_name": _resolve_output_file(output_dir, image.get("file_name"), f"{image['name']}.png"),
                        }
                        for image in outputs["images"]
                    ]
                },
            )
        )
    if outputs["final_case"]["enabled"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.final_case",
                action="write_case",
                params={"file_name": _resolve_output_file(output_dir, outputs["final_case"]["file_name"], "final.cas.h5")},
            )
        )
    if outputs["final_case_data"]["enabled"]:
        operations.append(
            WorkflowOperation(
                phase="outputs.final_case_data",
                action="write_case_data",
                params={
                    "file_name": _resolve_output_file(
                        output_dir,
                        outputs["final_case_data"]["file_name"],
                        "final-data.cas.h5",
                    )
                },
            )
        )

    transcript = outputs["transcript"]
    if transcript["enabled"]:
        transcript = {
            "enabled": True,
            "file_name": _resolve_output_file(output_dir, transcript["file_name"], "transcript.log"),
        }
    return WorkflowProgram(
        workflow="fluent.reflow_melting",
        operations=operations,
        transcript=transcript if transcript["enabled"] else None,
    )


FLUENT_WORKFLOW_DEFINITIONS: tuple[WorkflowDefinition, ...] = (
    WorkflowDefinition(
        name="fluent.steady_run",
        product="fluent",
        description="Run a steady single-phase Fluent solve from an existing mesh, case, or case-data source.",
        summary="Existing mesh/case -> apply setup changes -> initialize -> run steady iterations -> collect reports/exports.",
        spec_sections=("source", "setup", "solve", "outputs"),
        load_spec=load_fluent_steady_run_spec,
        compile_program=compile_fluent_steady_run,
    ),
    WorkflowDefinition(
        name="fluent.reflow_melting",
        product="fluent",
        description="Run a transient multiphase reflow/melting Fluent workflow from an existing mesh or case.",
        summary="Existing mesh/case -> apply physics/zones -> initialize -> run transient chunks with checkpoints -> collect reports/exports.",
        spec_sections=("source", "physics", "zones", "solve", "outputs"),
        load_spec=load_fluent_reflow_melting_spec,
        compile_program=compile_fluent_reflow_melting,
    ),
)


def workflow_definition_map() -> dict[str, WorkflowDefinition]:
    return {definition.name: definition for definition in FLUENT_WORKFLOW_DEFINITIONS}


def load_workflow_spec_payload(spec: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(spec, dict):
        return dict(spec)
    path = Path(spec)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise AdapterError("Workflow spec file must deserialize to an object.")
    return data
