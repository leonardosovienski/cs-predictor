"""Observable Task Scheduler entrypoint for the weekly CS refresh."""
from __future__ import annotations

import subprocess
import sys
import argparse
from pathlib import Path

# `pythonw.exe` (executavel de toda tarefa agendada) nao tem console: um
# processo de console filho ganharia janela VISIVEL na tela do dono.
# Saida ja e capturada, entao a flag nao esconde nada.
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
RUNNER = WORKSPACE / "tools" / "operational_runner.py"
PAYLOAD = Path(__file__).with_name("atualiza_semanal_payload.py")
LOG_DIR = ROOT / "logs" / "operations"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CS weekly refresh with the operational envelope.")
    parser.parse_args(argv)
    if not RUNNER.is_file() or not PAYLOAD.is_file():
        print("operational entrypoint is incomplete", file=sys.stderr)
        return 3
    command = [
        sys.executable, str(RUNNER), "run", "--task", "cs-ratings-semanal",
        "--project", "cs-predictor", "--cwd", str(ROOT),
        "--log", str(LOG_DIR / "cs-ratings-semanal.log"),
        "--event-log", str(LOG_DIR / "events.jsonl"),
        "--heartbeat", str(LOG_DIR / "cs-ratings-semanal.heartbeat.json"),
        "--expected-artifact", str(ROOT / "data" / "ratings.json"),
        "--timeout", "9000", "--", sys.executable, "-X", "utf8", str(PAYLOAD),
    ]
    return subprocess.run(command, cwd=ROOT, check=False,
                          creationflags=_NO_WINDOW).returncode


if __name__ == "__main__":
    raise SystemExit(main())
