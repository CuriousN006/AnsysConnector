from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ansys_connector.core import build_registry, detect_environment
from ansys_connector.core.execution import open_managed_session
from ansys_connector.products.base import AdapterError

from .fluent import workflow_definition_map
from .models import WorkflowOperation, WorkflowProgress
from .runtime import WorkflowService


class WorkflowCancelled(RuntimeError):
    """Raised when a workflow run has been cancelled at a chunk boundary."""


def _progress_for_operation(phase: str, percent: float, message: str, *, last_chunk: dict[str, Any] | None = None) -> WorkflowProgress:
    return WorkflowProgress(percent=percent, message=f"{phase}: {message}", last_chunk=last_chunk)


def _progress_for_iterations(completed: int, total: int, *, phase: str, chunk_size: int) -> WorkflowProgress:
    percent = 100.0 * completed / total if total else 0.0
    return WorkflowProgress(
        percent=percent,
        message=f"{phase}: completed {completed}/{total} iterations",
        completed_iterations=completed,
        target_iterations=total,
        last_chunk={"kind": "iterations", "chunk_size": chunk_size, "completed": completed, "remaining": max(total - completed, 0)},
    )


def _progress_for_steps(completed: int, total: int, *, phase: str, chunk_size: int, time_step_size: float) -> WorkflowProgress:
    percent = 100.0 * completed / total if total else 0.0
    current_time = completed * time_step_size
    return WorkflowProgress(
        percent=percent,
        message=f"{phase}: completed {completed}/{total} time steps",
        completed_steps=completed,
        target_steps=total,
        current_time=current_time,
        last_chunk={
            "kind": "time_steps",
            "chunk_size": chunk_size,
            "completed": completed,
            "remaining": max(total - completed, 0),
            "current_time": current_time,
        },
    )


def _append_output(summary: dict[str, Any], file_name: str | None) -> None:
    if not file_name:
        return
    outputs = list(summary.get("outputs", []))
    if file_name not in outputs:
        outputs.append(file_name)
    summary["outputs"] = outputs


def _update_summary_from_result(summary: dict[str, Any], action: str, result: dict[str, Any]) -> None:
    if action == "collect_reports":
        summary["reports"] = dict(result.get("reports", {}))
        return
    if action == "export_results":
        for item in result.get("exports", []):
            _append_output(summary, item.get("file_name"))
        return
    if action == "checkpoint_case_data":
        checkpoints = list(summary.get("checkpoints", []))
        file_name = result.get("kwargs", {}).get("file_name")
        if file_name:
            checkpoints.append(file_name)
            summary["checkpoints"] = checkpoints
            _append_output(summary, file_name)
        return
    if action in {"write_case", "write_case_data", "start_transcript"}:
        _append_output(summary, result.get("kwargs", {}).get("file_name"))
        return
    if action == "get_solver_health":
        summary["last_health"] = result


def _checkpoint_path(template: str, *, completed_iterations: int | None = None, completed_steps: int | None = None, chunk_index: int) -> str:
    return template.format(
        completed_iterations=completed_iterations if completed_iterations is not None else 0,
        completed_steps=completed_steps if completed_steps is not None else 0,
        chunk_index=chunk_index,
    )


def _execute_chunked_operation(
    service: WorkflowService,
    run_id: str,
    session: Any,
    operation: WorkflowOperation,
    *,
    summary: dict[str, Any],
) -> None:
    completed = 0
    total = int(operation.total or 0)
    chunk_index = 0
    while completed < total:
        if service.is_cancel_requested(run_id):
            raise WorkflowCancelled("cancel requested")

        chunk_index += 1
        chunk_size = min(int(operation.chunk_size or total), total - completed)
        if operation.mode == "iterations":
            result = session.execute(operation.action, {"count": chunk_size})
            completed += chunk_size
            progress = _progress_for_iterations(completed, total, phase=operation.phase, chunk_size=chunk_size)
        else:
            result = session.execute(
                operation.action,
                {
                    "step_count": chunk_size,
                    "max_iterations_per_step": operation.params["max_iterations_per_step"],
                    "time_step_size": operation.params["time_step_size"],
                },
            )
            completed += chunk_size
            progress = _progress_for_steps(
                completed,
                total,
                phase=operation.phase,
                chunk_size=chunk_size,
                time_step_size=float(operation.params["time_step_size"]),
            )

        _update_summary_from_result(summary, operation.action, result)
        if operation.report_requests:
            report_result = session.execute("collect_reports", {"reports": operation.report_requests})
            _update_summary_from_result(summary, "collect_reports", report_result)
        health_result = session.execute("get_solver_health", {})
        _update_summary_from_result(summary, "get_solver_health", health_result)

        if operation.checkpoint_every and operation.checkpoint_template and chunk_index % operation.checkpoint_every == 0:
            checkpoint_name = _checkpoint_path(
                operation.checkpoint_template,
                completed_iterations=completed if operation.mode == "iterations" else None,
                completed_steps=completed if operation.mode == "time_steps" else None,
                chunk_index=chunk_index,
            )
            checkpoint_result = session.execute("checkpoint_case_data", {"file_name": checkpoint_name})
            _update_summary_from_result(summary, "checkpoint_case_data", checkpoint_result)

        service.merge_summary(run_id, summary)
        service.mark_running(run_id, phase=operation.phase, progress=progress)


def _run_workflow(run_id: str, *, state_dir: str | Path | None = None) -> None:
    service = WorkflowService(state_dir=state_dir)
    session = None
    summary: dict[str, Any] = {
        "outputs": [],
        "reports": {},
        "checkpoints": [],
        "last_health": None,
    }
    transcript_started = False
    try:
        definitions = workflow_definition_map()
        record = service.mark_starting(run_id, pid=os.getpid())
        if service.is_cancel_requested(run_id):
            raise WorkflowCancelled("cancel requested")
        definition = definitions[record.workflow]
        spec = service.load_spec(run_id)
        output_dir = Path(record.output_dir)
        workspace = Path(record.workspace)
        program = definition.compile_program(spec, output_dir)
        env = detect_environment(record.version)
        registry = build_registry()
        adapter = registry.get("fluent")
        source_parent = Path(spec["source"]["path"]).resolve(strict=False).parent
        session = open_managed_session(
            adapter=adapter,
            env=env,
            options={},
            profile="safe",
            allowed_roots=[str(source_parent), str(output_dir)],
            workspace=workspace,
            session_label=f"workflow:{run_id}",
        )

        if program.transcript:
            transcript_result = session.execute("start_transcript", {"file_name": program.transcript["file_name"]})
            _update_summary_from_result(summary, "start_transcript", transcript_result)
            transcript_started = True
            service.merge_summary(run_id, summary)

        for operation in program.operations:
            if operation.mode == "once":
                progress = _progress_for_operation(operation.phase, 0.0, f"running {operation.action}")
                service.mark_running(run_id, phase=operation.phase, progress=progress)
                result = session.execute(operation.action, dict(operation.params))
                _update_summary_from_result(summary, operation.action, result)
                if operation.action != "get_solver_health":
                    health_result = session.execute("get_solver_health", {})
                    _update_summary_from_result(summary, "get_solver_health", health_result)
                service.merge_summary(run_id, summary)
                continue

            _execute_chunked_operation(
                service,
                run_id,
                session,
                operation,
                summary=summary,
            )

        terminal_progress = WorkflowProgress(percent=100.0, message="completed")
        service.mark_terminal(
            run_id,
            status="succeeded",
            phase="completed",
            progress=terminal_progress,
            error=None,
            summary=summary,
        )
    except WorkflowCancelled as exc:
        current = service.get_run(run_id)
        progress = WorkflowProgress.from_dict(dict(current["progress"]))
        service.mark_terminal(
            run_id,
            status="cancelled",
            phase="cancelled",
            progress=WorkflowProgress(
                percent=progress.percent,
                message="cancelled",
                completed_iterations=progress.completed_iterations,
                target_iterations=progress.target_iterations,
                completed_steps=progress.completed_steps,
                target_steps=progress.target_steps,
                current_time=progress.current_time,
                last_chunk=progress.last_chunk,
            ),
            error=str(exc),
            summary=summary,
        )
    except Exception as exc:
        current = service.get_run(run_id)
        progress = WorkflowProgress.from_dict(dict(current["progress"]))
        service.mark_terminal(
            run_id,
            status="failed",
            phase="failed",
            progress=WorkflowProgress(
                percent=progress.percent,
                message="failed",
                completed_iterations=progress.completed_iterations,
                target_iterations=progress.target_iterations,
                completed_steps=progress.completed_steps,
                target_steps=progress.target_steps,
                current_time=progress.current_time,
                last_chunk=progress.last_chunk,
            ),
            error=str(exc),
            summary=summary,
        )
        raise
    finally:
        try:
            if transcript_started and session is not None:
                session.execute("stop_transcript", {})
        except Exception:
            pass
        try:
            if session is not None:
                session.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ansys_connector.workflows.templates.worker")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--state-dir")
    args = parser.parse_args(argv)
    _run_workflow(args.run_id, state_dir=args.state_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
