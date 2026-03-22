from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any


def _installed_paths() -> dict[str, str | None]:
    awp_root = os.environ.get("AWP_ROOT261")
    root = Path(awp_root) if awp_root else None

    def maybe(path: Path | None) -> str | None:
        if path and path.exists():
            return str(path)
        return None

    return {
        "AWP_ROOT261": awp_root,
        "fluent_exe": maybe(root / "fluent" / "ntbin" / "win64" / "fluent.exe" if root else None),
        "runwb2_exe": maybe(root / "Framework" / "bin" / "Win64" / "RunWB2.exe" if root else None),
        "runwb2_bat": maybe(root / "Framework" / "bin" / "Win64" / "runwb2.bat" if root else None),
    }


def _import_status() -> dict[str, str]:
    modules = {
        "ansys.fluent.core": "missing",
        "ansys.mechanical.core": "missing",
        "ansys.workbench.core": "missing",
    }
    for name in modules:
        try:
            module = importlib.import_module(name)
            modules[name] = getattr(module, "__version__", "ok")
        except Exception as exc:  # pragma: no cover - smoke test output path
            modules[name] = f"error: {exc}"
    return modules


def main() -> int:
    payload: dict[str, Any] = {
        "python": {
            "executable": os.sys.executable,
            "version": os.sys.version,
        },
        "env": _installed_paths(),
        "imports": _import_status(),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
