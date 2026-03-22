from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import yaml

from ansys_connector.core.execution.broker import exclusive_file_lock, resolve_broker_state_dir
from ansys_connector.core.execution.managed_session import resolve_workspace
from ansys_connector.products.base import AdapterError

from .fluent import load_workflow_spec_payload, workflow_definition_map
from .models import WorkflowDefinition, WorkflowProgress, WorkflowRunRecord, utc_now_iso


_TERMINAL_WORKFLOW_STATUSES = {"cancelled", "succeeded", "failed"}


def workflow_runs_root(state_dir: str | Path | None = None) -> Path:
    root = resolve_broker_state_dir(state_dir)
    run_root = root / "workflow-runs"
    run_root.mkdir(parents=True, exist_ok=True)
    return run_root


def _spawn_worker_process(run_id: str, state_dir: Path) -> subprocess.Popen[str]:
    run_dir = workflow_runs_root(state_dir) / run_id
    log_path = run_dir / "worker.log"
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    log_stream = log_path.open("a", encoding="utf-8")
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "ansys_connector.workflows.templates.worker",
            "--run-id",
            run_id,
            "--state-dir",
            str(state_dir),
        ],
        cwd=str(run_dir),
        stdout=log_stream,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creationflags,
    )


class WorkflowService:
    def __init__(
        self,
        *,
        state_dir: str | Path | None = None,
        definitions_factory: Callable[[], dict[str, WorkflowDefinition]] = workflow_definition_map,
        worker_launcher: Callable[[str, Path], subprocess.Popen[str]] = _spawn_worker_process,
    ) -> None:
        self._state_dir = resolve_broker_state_dir(state_dir)
        self._definitions = definitions_factory()
        self._worker_launcher = worker_launcher

    @property
    def state_dir(self) -> Path:
        return self._state_dir

    def list_workflows(self, product: str | None = None) -> list[dict[str, Any]]:
        definitions = list(self._definitions.values())
        if product is not None:
            definitions = [definition for definition in definitions if definition.product == product]
        return [definition.to_dict() for definition in sorted(definitions, key=lambda item: item.name)]

    def describe_workflow(self, name: str) -> dict[str, Any]:
        definition = self._get_definition(name)
        return definition.to_dict()

    def list_runs(self) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for run_dir in sorted(workflow_runs_root(self._state_dir).iterdir()):
            if not run_dir.is_dir():
                continue
            try:
                runs.append(self.get_run(run_dir.name))
            except FileNotFoundError:
                continue
        runs.sort(key=lambda item: item["created_at"], reverse=True)
        return runs

    def start_workflow(
        self,
        name: str,
        spec: dict[str, Any] | str | Path,
        *,
        version: str | None = None,
        workspace: str | Path | None = None,
    ) -> dict[str, Any]:
        definition = self._get_definition(name)
        workspace_path = resolve_workspace(workspace)
        run_id = str(uuid4())
        run_dir = workflow_runs_root(self._state_dir) / run_id
        output_dir = (workspace_path / "outputs" / "workflow-runs" / run_id).resolve(strict=False)
        output_dir.mkdir(parents=True, exist_ok=True)
        payload = load_workflow_spec_payload(spec)
        normalized_spec = definition.load_spec(payload, workspace_path)
        compiled_program = definition.compile_program(normalized_spec, output_dir)

        run_dir.mkdir(parents=True, exist_ok=True)
        record = WorkflowRunRecord.create(
            run_id=run_id,
            workflow=name,
            workspace=workspace_path,
            output_dir=output_dir,
            version=version,
        )
        self._write_yaml(self._spec_file(run_id), normalized_spec)
        self._write_json(self._program_file(run_id), compiled_program.to_dict())
        self._write_run_record(record)
        self.append_event(run_id, {"type": "queued", "workflow": name, "workspace": str(workspace_path)})

        process = self._worker_launcher(run_id, self._state_dir)
        record = self._update_record(
            run_id,
            lambda current: WorkflowRunRecord.from_dict(
                {
                    **current.to_dict(),
                    "worker_pid": process.pid,
                }
            ),
        )
        self.append_event(run_id, {"type": "worker_spawned", "pid": process.pid})
        return self._decorate_run(record)

    def get_run(self, run_id: str) -> dict[str, Any]:
        record = self._read_run_record(run_id)
        return self._decorate_run(record)

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        def mutate(current: WorkflowRunRecord) -> WorkflowRunRecord:
            if current.status in _TERMINAL_WORKFLOW_STATUSES:
                return current
            payload = current.to_dict()
            payload["status"] = "cancel_requested"
            if payload["phase"] == "queued":
                payload["phase"] = "cancel_requested"
            progress = dict(payload["progress"])
            progress["message"] = "cancel requested"
            payload["progress"] = progress
            return WorkflowRunRecord.from_dict(payload)

        updated = self._update_record(run_id, mutate)
        self.append_event(run_id, {"type": "cancel_requested"})
        return self._decorate_run(updated)

    def wait_for_run(self, run_id: str, *, poll_interval: float = 1.0, timeout_seconds: float | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_seconds if timeout_seconds is not None else None
        while True:
            run = self.get_run(run_id)
            if run["status"] in _TERMINAL_WORKFLOW_STATUSES:
                return run
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for workflow run {run_id}.")
            time.sleep(poll_interval)

    def load_spec(self, run_id: str) -> dict[str, Any]:
        path = self._spec_file(run_id)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise AdapterError(f"Workflow run spec for {run_id} is invalid.")
        return data

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        event_path = self._event_file(run_id)
        payload = {"timestamp": utc_now_iso(), **event}
        with event_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, default=str))
            stream.write("\n")

    def mark_starting(self, run_id: str, *, pid: int) -> WorkflowRunRecord:
        def mutate(current: WorkflowRunRecord) -> WorkflowRunRecord:
            payload = current.to_dict()
            payload["status"] = "starting" if current.status != "cancel_requested" else "cancel_requested"
            payload["phase"] = "starting"
            payload["started_at"] = utc_now_iso()
            payload["worker_pid"] = pid
            payload["progress"] = WorkflowProgress(
                percent=0.0,
                message="cancel requested before launch" if current.status == "cancel_requested" else "starting",
            ).to_dict()
            return WorkflowRunRecord.from_dict(payload)

        record = self._update_record(run_id, mutate)
        self.append_event(run_id, {"type": "starting", "pid": pid})
        return record

    def mark_running(self, run_id: str, *, phase: str, progress: WorkflowProgress) -> WorkflowRunRecord:
        def mutate(current: WorkflowRunRecord) -> WorkflowRunRecord:
            payload = current.to_dict()
            payload["status"] = "running" if current.status != "cancel_requested" else "cancel_requested"
            payload["phase"] = phase
            payload["progress"] = progress.to_dict()
            return WorkflowRunRecord.from_dict(payload)

        record = self._update_record(run_id, mutate)
        self.append_event(run_id, {"type": "progress", "phase": phase, "progress": progress.to_dict()})
        return record

    def merge_summary(self, run_id: str, summary_patch: dict[str, Any]) -> WorkflowRunRecord:
        def mutate(current: WorkflowRunRecord) -> WorkflowRunRecord:
            payload = current.to_dict()
            merged = dict(payload.get("summary", {}))
            for key, value in summary_patch.items():
                merged[key] = value
            payload["summary"] = merged
            return WorkflowRunRecord.from_dict(payload)

        return self._update_record(run_id, mutate)

    def mark_terminal(
        self,
        run_id: str,
        *,
        status: str,
        phase: str,
        progress: WorkflowProgress,
        error: str | None,
        summary: dict[str, Any],
    ) -> WorkflowRunRecord:
        if status not in _TERMINAL_WORKFLOW_STATUSES:
            raise AdapterError(f"Unsupported terminal workflow status: {status}")

        def mutate(current: WorkflowRunRecord) -> WorkflowRunRecord:
            payload = current.to_dict()
            payload["status"] = status
            payload["phase"] = phase
            payload["progress"] = progress.to_dict()
            payload["ended_at"] = utc_now_iso()
            payload["error"] = error
            payload["summary"] = dict(summary)
            return WorkflowRunRecord.from_dict(payload)

        record = self._update_record(run_id, mutate)
        self.append_event(run_id, {"type": status, "phase": phase, "error": error, "summary": summary})
        return record

    def is_cancel_requested(self, run_id: str) -> bool:
        return self._read_run_record(run_id).status == "cancel_requested"

    def _get_definition(self, name: str) -> WorkflowDefinition:
        try:
            return self._definitions[name]
        except KeyError as exc:
            raise KeyError(f"Unknown workflow: {name}") from exc

    def _decorate_run(self, record: WorkflowRunRecord) -> dict[str, Any]:
        payload = record.to_dict()
        payload["recent_events"] = self._read_recent_events(record.run_id)
        return payload

    def _read_recent_events(self, run_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        event_path = self._event_file(run_id)
        if not event_path.exists():
            return []
        lines = event_path.read_text(encoding="utf-8").splitlines()
        events: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return events

    def _run_dir(self, run_id: str) -> Path:
        return workflow_runs_root(self._state_dir) / run_id

    def _run_lock(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "run.lock"

    def _run_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "run.json"

    def _spec_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "spec.yaml"

    def _program_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "program.json"

    def _event_file(self, run_id: str) -> Path:
        return self._run_dir(run_id) / "events.jsonl"

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_yaml(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    def _write_run_record(self, record: WorkflowRunRecord) -> None:
        self._write_json(self._run_file(record.run_id), record.to_dict())

    def _read_run_record(self, run_id: str) -> WorkflowRunRecord:
        path = self._run_file(run_id)
        if not path.exists():
            raise FileNotFoundError(f"Unknown workflow run: {run_id}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise AdapterError(f"Workflow run metadata for {run_id} is invalid.")
        return WorkflowRunRecord.from_dict(payload)

    def _update_record(
        self,
        run_id: str,
        mutate: Callable[[WorkflowRunRecord], WorkflowRunRecord],
    ) -> WorkflowRunRecord:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Unknown workflow run: {run_id}")
        with exclusive_file_lock(self._run_lock(run_id), timeout_seconds=30.0, poll_interval=0.1):
            current = self._read_run_record(run_id)
            updated = mutate(current)
            self._write_run_record(updated)
            return updated
