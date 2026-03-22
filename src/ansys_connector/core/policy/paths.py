from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ansys_connector.products.base import ActionExecutionContext, AdapterError


def normalize_allowed_roots(
    allowed_roots: list[str] | tuple[str, ...] | str | Path | None = None,
    *,
    cwd: Path | None = None,
) -> tuple[Path, ...]:
    workspace = (cwd or Path.cwd()).resolve(strict=False)
    roots: list[Path] = [workspace, (workspace / "outputs").resolve(strict=False)]

    if allowed_roots is None:
        extras: list[str | Path] = []
    elif isinstance(allowed_roots, (str, Path)):
        extras = [allowed_roots]
    else:
        extras = list(allowed_roots)

    for extra in extras:
        roots.append(_normalize_path(extra, workspace))

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = os.path.normcase(str(root))
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def _normalize_path(value: str | Path, cwd: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = cwd / path
    return path.resolve(strict=False)


def _path_within(candidate: Path, root: Path) -> bool:
    candidate_text = os.path.normcase(str(candidate.resolve(strict=False)))
    root_text = os.path.normcase(str(root.resolve(strict=False)))
    return candidate_text == root_text or candidate_text.startswith(root_text + os.sep)


def normalize_path_value(value: Any, context: ActionExecutionContext) -> Any:
    if isinstance(value, list):
        return [normalize_path_value(item, context) for item in value]
    if not isinstance(value, (str, Path)):
        raise AdapterError(
            f"Path parameter for {context.adapter} must be a string or path-like value, got {type(value).__name__}."
        )

    normalized = _normalize_path(value, context.cwd)
    if not any(_path_within(normalized, root) for root in context.allowed_roots):
        allowed = ", ".join(str(root) for root in context.allowed_roots)
        raise AdapterError(
            f"Path '{normalized}' is outside the allowed roots for {context.adapter}: {allowed}"
        )
    return str(normalized)
