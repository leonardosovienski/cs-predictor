"""Coleta de resultados do HLTV → data/cs.db (Fase 1).

Pagina /results de hoje para trás até cobrir a janela do backtest
(config hltv.until_date; default 2025-01-01). Persistência incremental
página a página — queda no meio não perde nada; re-execução é idempotente
(match_id é PK).

Uso:
    python -m src.ingest_hltv                # até until_date do config
    python -m src.ingest_hltv --until 2025-06-01
"""
import argparse
import sys

from . import db
from .config import ROOT, load_config


def run(until_date: str) -> None:
    from .data.hltv_provider import HltvProvider
    cfg = load_config()
    provider = HltvProvider(delay=cfg.get("hltv", {}).get("scraper_delay"))
    conn = db.connect(str(ROOT / cfg.get("database", "data/cs.db")))

    total = 0
    for page_rows in provider.fetch_results(until_date):
        db.upsert_matches(conn, page_rows)
        total += len(page_rows)
        oldest = min(r["date"] for r in page_rows)
        print(f"  +{len(page_rows)} (acum {total}) — página mais antiga: {oldest}",
              flush=True)
    n = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    dmin, dmax = conn.execute("SELECT MIN(date), MAX(date) FROM matches").fetchone()
    print(f"matches no banco: {n} ({dmin} .. {dmax})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", default=None,
                    help="coleta até esta data (ISO); default: config hltv.until_date")
    args = ap.parse_args()
    cfg = load_config()
    until = args.until or cfg.get("hltv", {}).get("until_date", "2025-01-01")
    sys.exit(run(until))
