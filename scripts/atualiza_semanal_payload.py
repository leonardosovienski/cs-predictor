"""Domain payload for the weekly CS refresh; deliberately unaware of Scheduler."""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "atualiza_semanal.log"
WORKSPACE = ROOT.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))
from tools.secret_redaction import collect_sensitive_values, safe_redact_text

SENSITIVE_VALUES = collect_sensitive_values()


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{stamp} {safe_redact_text(msg, SENSITIVE_VALUES)}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def build_steps(corte: str):
    return [
        ("ingest", [sys.executable, "-X", "utf8", "-m", "src.ingest_hltv", "--until", corte], 3600),
        ("ratings", [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "backtest_walkforward.py"),
                     "--write-artifacts"], 900),
        ("platt", [sys.executable, "-X", "utf8", str(ROOT / "scripts" / "backtest_calibracao.py")], 900),
    ]


def main() -> int:
    corte = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%d")
    steps = build_steps(corte)
    log("=== atualiza_semanal: inicio ===")
    worst = 0
    for name, command, timeout in steps:
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            for line in (result.stdout or "").strip().splitlines()[-2:]:
                log(f"  [{name}] {line}")
            if result.returncode != 0:
                log(f"  [{name}] FALHOU exit {result.returncode}: {(result.stderr or '').strip()[-200:]}")
                worst = 1
            else:
                log(f"  [{name}] OK")
        except subprocess.TimeoutExpired:
            log(f"  [{name}] TIMEOUT ({timeout}s)")
            worst = 1
        except Exception as exc:
            log(f"  [{name}] EXCECAO: {exc}")
            worst = 1
    log(f"=== atualiza_semanal: fim (exit {worst}) ===")
    return worst


if __name__ == "__main__":
    sys.exit(main())
