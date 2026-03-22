from __future__ import annotations

import os
from pathlib import Path

import ansys.fluent.core as pyfluent


def main() -> int:
    awp_root = os.environ.get("AWP_ROOT261")
    if not awp_root:
        raise RuntimeError("AWP_ROOT261 is not set.")

    fluent_exe = Path(awp_root) / "fluent" / "ntbin" / "win64" / "fluent.exe"
    if not fluent_exe.exists():
        raise FileNotFoundError(f"Fluent executable not found: {fluent_exe}")

    print(f"Using Fluent executable: {fluent_exe}")
    session = pyfluent.launch_fluent(
        product_version=261,
        mode="solver",
        dimension=3,
        precision="double",
        processor_count=2,
        ui_mode="no_gui",
        start_timeout=180,
        start_transcript=False,
        cleanup_on_exit=True,
        fluent_path=str(fluent_exe),
        cwd=str(Path.cwd()),
    )

    try:
        version = session.get_fluent_version()
        print(f"Connected to Fluent {version}")
        print("Smoke test command completed.")
    finally:
        session.exit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
