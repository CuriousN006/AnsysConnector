from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal


WorkflowRunStatus = Literal[
    "queued",
    "starting",
    "running",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
]
OperationMode = Literal["once", "iterations", "time_steps"]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class WorkflowProgress:
    percent: float
    message: str
    completed_iterations: int | None = None
    target_iterations: int | None = None
    completed_steps: int | None = None
    target_steps: int | None = None
    current_time: float | None = None
    last_chunk: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "percent": float(self.percent),
            "message": self.message,
            "completed_iterations": self.completed_iterations,
            "target_iterations": self.target_iterations,
            "completed_steps": self.completed_steps,
            "target_steps": self.target_steps,
            "current_time": self.current_time,
            "last_chunk": dict(self.last_chunk) if self.last_chunk is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowProgress":
        return cls(
            percent=float(payload.get("percent", 0.0)),
            message=str(payload.get("message", "")),
            completed_iterations=payload.get("completed_iterations"),
            target_iterations=payload.get("target_iterations"),
            completed_steps=payload.get("completed_steps"),
            target_steps=payload.get("target_steps"),
            current_time=payload.get("current_time"),
            last_chunk=dict(payload.get("last_chunk", {})) if isinstance(payload.get("last_chunk"), dict) else None,
        )


@dataclass(frozen=True)
class WorkflowOperation:
    phase: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    mode: OperationMode = "once"
    total: int | None = None
    chunk_size: int | None = None
    checkpoint_every: int | None = None
    checkpoint_template: str | None = None
    report_requests: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "action": self.action,
            "params": dict(self.params),
            "mode": self.mode,
            "total": self.total,
            "chunk_size": self.chunk_size,
            "checkpoint_every": self.checkpoint_every,
            "checkpoint_template": self.checkpoint_template,
            "report_requests": [dict(item) for item in self.report_requests],
        }


@dataclass(frozen=True)
class WorkflowProgram:
    workflow: str
    operations: list[WorkflowOperation]
    transcript: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "operations": [operation.to_dict() for operation in self.operations],
            "transcript": dict(self.transcript) if self.transcript is not None else None,
        }


@dataclass(frozen=True)
class WorkflowDefinition:
    name: str
    product: str
    description: str
    summary: str
    spec_sections: tuple[str, ...]
    load_spec: Callable[[dict[str, Any], Path], dict[str, Any]]
    compile_program: Callable[[dict[str, Any], Path], WorkflowProgram]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "product": self.product,
            "description": self.description,
            "summary": self.summary,
            "spec_sections": list(self.spec_sections),
        }


@dataclass(frozen=True)
class WorkflowRunRecord:
    run_id: str
    workflow: str
    status: WorkflowRunStatus
    phase: str
    progress: WorkflowProgress
    workspace: str
    output_dir: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    error: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    version: str | None = None
    worker_pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "workflow": self.workflow,
            "status": self.status,
            "phase": self.phase,
            "progress": self.progress.to_dict(),
            "workspace": self.workspace,
            "output_dir": self.output_dir,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "summary": dict(self.summary),
            "version": self.version,
            "worker_pid": self.worker_pid,
        }

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        workflow: str,
        workspace: Path,
        output_dir: Path,
        version: str | None = None,
    ) -> "WorkflowRunRecord":
        return cls(
            run_id=run_id,
            workflow=workflow,
            status="queued",
            phase="queued",
            progress=WorkflowProgress(percent=0.0, message="queued"),
            workspace=str(workspace.resolve(strict=False)),
            output_dir=str(output_dir.resolve(strict=False)),
            created_at=utc_now_iso(),
            version=version,
            summary={
                "outputs": [],
                "reports": {},
                "checkpoints": [],
                "last_health": None,
            },
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkflowRunRecord":
        return cls(
            run_id=str(payload["run_id"]),
            workflow=str(payload["workflow"]),
            status=str(payload["status"]),
            phase=str(payload.get("phase", payload["status"])),
            progress=WorkflowProgress.from_dict(dict(payload.get("progress", {}))),
            workspace=str(payload["workspace"]),
            output_dir=str(payload["output_dir"]),
            created_at=str(payload["created_at"]),
            started_at=payload.get("started_at"),
            ended_at=payload.get("ended_at"),
            error=payload.get("error"),
            summary=dict(payload.get("summary", {})),
            version=payload.get("version"),
            worker_pid=payload.get("worker_pid"),
        )
