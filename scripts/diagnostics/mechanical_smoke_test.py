from __future__ import annotations

import os
import socket
from pathlib import Path

from ansys.mechanical.core import launch_mechanical


def _find_free_local_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def main() -> int:
    awp_root = os.environ.get("AWP_ROOT261")
    if not awp_root:
        raise RuntimeError("AWP_ROOT261 is not set.")

    exec_file = Path(awp_root) / "aisol" / "bin" / "winx64" / "AnsysWBU.exe"
    if not exec_file.exists():
        raise FileNotFoundError(f"Mechanical executable not found: {exec_file}")

    mechanical = launch_mechanical(
        exec_file=str(exec_file),
        batch=True,
        cleanup_on_exit=True,
        start_timeout=180,
        version=261,
        start_instance=True,
        port=_find_free_local_port(),
    )

    try:
        print(f"Connected to Mechanical session: {type(mechanical).__name__}")
        if hasattr(mechanical, "run_python_script"):
            result = mechanical.run_python_script("ExtAPI.ApplicationVersion")
            print(f"Mechanical version response: {result}")
        else:
            print("Mechanical client does not expose run_python_script().")
    finally:
        exit_fn = getattr(mechanical, "exit", None)
        if callable(exit_fn):
            exit_fn()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
