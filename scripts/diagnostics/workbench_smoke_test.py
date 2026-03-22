from __future__ import annotations

from pathlib import Path

from ansys.workbench.core import launch_workbench


def main() -> int:
    workdir = Path.cwd() / "outputs" / "workbench"
    workdir.mkdir(parents=True, exist_ok=True)

    wb = launch_workbench(
        show_gui=False,
        version="261",
        client_workdir=str(workdir),
        server_workdir=str(workdir),
    )

    try:
        print(f"Connected to Workbench client: {type(wb).__name__}")
        print(f"Workbench server version: {wb.server_version}")
    finally:
        close = getattr(wb, "exit", None) or getattr(wb, "close", None)
        if callable(close):
            close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
