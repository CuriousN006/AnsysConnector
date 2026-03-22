from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_AWP_ROOT_PATTERN = re.compile(r"^AWP_ROOT(?P<version>\d+)$")
_MODULE_NAMES = (
    "ansys.fluent.core",
    "ansys.mechanical.core",
    "ansys.workbench.core",
)


@dataclass(frozen=True)
class EnvironmentInfo:
    """Detected local Ansys and Python environment."""

    python_executable: str
    python_version: str
    version: str | None
    awp_root_env: str | None
    awp_root: Path | None
    fluent_exe: Path | None
    workbench_exe: Path | None
    workbench_bat: Path | None
    mechanical_exe: Path | None
    module_versions: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "python": {
                "executable": self.python_executable,
                "version": self.python_version,
            },
            "ansys": {
                "version": self.version,
                "awp_root_env": self.awp_root_env,
                "awp_root": str(self.awp_root) if self.awp_root else None,
                "fluent_exe": str(self.fluent_exe) if self.fluent_exe else None,
                "workbench_exe": str(self.workbench_exe) if self.workbench_exe else None,
                "workbench_bat": str(self.workbench_bat) if self.workbench_bat else None,
                "mechanical_exe": str(self.mechanical_exe) if self.mechanical_exe else None,
            },
            "modules": dict(self.module_versions),
        }


def _find_awp_roots() -> list[tuple[int, str, Path]]:
    matches: list[tuple[int, str, Path]] = []
    for key, value in os.environ.items():
        match = _AWP_ROOT_PATTERN.match(key)
        if not match:
            continue
        root = Path(value)
        if root.exists():
            matches.append((int(match.group("version")), key, root))
    return sorted(matches, key=lambda item: item[0], reverse=True)


def _maybe(path: Path | None) -> Path | None:
    if path and path.exists():
        return path
    return None


def _import_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _MODULE_NAMES:
        try:
            module = importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - environment dependent
            versions[name] = f"error: {exc}"
            continue
        versions[name] = getattr(module, "__version__", "ok")
    return versions


def detect_environment(version: str | None = None) -> EnvironmentInfo:
    """Detect the best available local Ansys installation."""

    awp_roots = _find_awp_roots()
    selected: tuple[int, str, Path] | None = None

    if version is not None:
        target = int(version)
        for item in awp_roots:
            if item[0] == target:
                selected = item
                break
    elif awp_roots:
        selected = awp_roots[0]

    awp_root_env = selected[1] if selected else None
    awp_root = selected[2] if selected else None
    detected_version = str(selected[0]) if selected else None

    return EnvironmentInfo(
        python_executable=os.sys.executable,
        python_version=os.sys.version,
        version=detected_version,
        awp_root_env=awp_root_env,
        awp_root=awp_root,
        fluent_exe=_maybe(
            awp_root / "fluent" / "ntbin" / "win64" / "fluent.exe" if awp_root else None
        ),
        workbench_exe=_maybe(
            awp_root / "Framework" / "bin" / "Win64" / "RunWB2.exe" if awp_root else None
        ),
        workbench_bat=_maybe(
            awp_root / "Framework" / "bin" / "Win64" / "runwb2.bat" if awp_root else None
        ),
        mechanical_exe=_maybe(
            awp_root / "aisol" / "bin" / "winx64" / "AnsysWBU.exe" if awp_root else None
        ),
        module_versions=_import_versions(),
    )
