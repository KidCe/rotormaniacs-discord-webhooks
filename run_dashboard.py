from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / "Scripts" / "python.exe"
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".pitchbot-requirements"


def ensure_runtime() -> None:
    if not VENV_PYTHON.exists():
        print("Creating the local Python environment...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)

    expected = REQUIREMENTS.read_text(encoding="utf-8")
    installed = STAMP.read_text(encoding="utf-8") if STAMP.exists() else ""
    if installed != expected:
        print("Installing Pitch Bot dependencies...", flush=True)
        subprocess.run(
            [str(VENV_PYTHON), "-m", "pip", "install", "-r", str(REQUIREMENTS)],
            cwd=ROOT,
            check=True,
        )
        STAMP.write_text(expected, encoding="utf-8")


def main() -> None:
    ensure_runtime()
    # The Windows Python launcher can detach its real interpreter, which makes
    # the Dashboard think the service exited. Load the isolated site-packages
    # into this process so the Dashboard owns the actual listener process.
    sys.path.insert(0, str(VENV / "Lib" / "site-packages"))
    sys.path.insert(0, str(ROOT / "src"))
    from pitchbot.cli import main as pitchbot_main

    raise SystemExit(pitchbot_main(["serve"]))


if __name__ == "__main__":
    main()
