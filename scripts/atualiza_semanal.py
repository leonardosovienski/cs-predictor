"""Refresh semanal do cs-predictor — pensado para o Task Scheduler.

Sequência (idempotente):
  1. python -m src.ingest_hltv --until <35 dias atrás>   (incremental;
     match_id é PK — re-visitar páginas recentes só faz upsert)
  2. scripts/backtest_walkforward.py   (re-materializa data/ratings.json
     com o Elo vivido até hoje)
  3. scripts/backtest_calibracao.py    (re-ajusta o Platt do serving e
     atualiza o resultado da trial N+1 — mesmos params = update legal)

Log em data/atualiza_semanal.log. Falha num passo não impede os seguintes.

Agendamento: schtasks semanal (segunda 08:00) — ver SINERGIAS_ECOSSISTEMA.md.
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "data" / "atualiza_semanal.log"


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{stamp} {msg}", flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp} {msg}\n")


def main() -> int:
    corte = (datetime.now(timezone.utc) - timedelta(days=35)).strftime("%Y-%m-%d")
    passos = [
        ("ingest", [sys.executable, "-X", "utf8", "-m", "src.ingest_hltv",
                    "--until", corte], 3600),
        ("ratings", [sys.executable, "-X", "utf8",
                     str(ROOT / "scripts" / "backtest_walkforward.py")], 900),
        ("platt", [sys.executable, "-X", "utf8",
                   str(ROOT / "scripts" / "backtest_calibracao.py")], 900),
    ]
    log("=== atualiza_semanal: inicio ===")
    pior = 0
    for nome, cmd, timeout in passos:
        try:
            r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=timeout)
            for ln in (r.stdout or "").strip().splitlines()[-2:]:
                log(f"  [{nome}] {ln}")
            if r.returncode != 0:
                log(f"  [{nome}] FALHOU exit {r.returncode}: "
                    f"{(r.stderr or '').strip()[-200:]}")
                pior = 1
            else:
                log(f"  [{nome}] OK")
        except Exception as e:
            log(f"  [{nome}] EXCECAO: {e}")
            pior = 1
    log(f"=== atualiza_semanal: fim (exit {pior}) ===")
    return pior


if __name__ == "__main__":
    sys.exit(main())
