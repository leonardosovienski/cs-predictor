"""Coleta mapa a mapa de cada partida já em data/cs.db → data/match_maps.

Complementa src.ingest_hltv (que só grava o placar da SÉRIE). Aqui vai-se
match_id a match_id à página de detalhe (/matches/<id>/x — HLTV ignora o
slug e redireciona pro canônico), pega os mapas JOGADOS (mapname + placar
por mapa) e persiste incrementalmente (commit a cada partida — queda no
meio não perde nada). Idempotente: só busca match_id que ainda não está em
match_maps (db.match_ids_missing_maps).

17 mil partidas x ~2s de cortesia = horas. Rode em background; reexecução
retoma de onde parou sozinha.

Uso:
    python -m src.ingest_hltv_maps [--limit N]
    python -m src.ingest_hltv_maps --teams "paiN,NiP,3DMAX,HEROIC,Wildcard"
"""
import argparse
import sys
import time

from . import db
from .config import ROOT, load_config


def run(limit: int | None = None, teams: list[str] | None = None) -> None:
    from .data.hltv_provider import HltvProvider
    cfg = load_config()
    provider = HltvProvider(delay=cfg.get("hltv", {}).get("scraper_delay"))
    conn = db.connect(str(ROOT / cfg.get("database", "data/cs.db")))

    pending = db.match_ids_missing_maps(conn, teams=teams)
    if limit:
        pending = pending[:limit]
    total = len(pending)
    print(f"faltam {total} partidas sem mapa a mapa", flush=True)

    ok = falhas = 0
    t0 = time.time()
    for i, mid in enumerate(pending, 1):
        try:
            maps = provider.fetch_match_maps(mid)
            if maps:
                db.upsert_match_maps(conn, mid, maps)
                ok += 1
            else:
                falhas += 1
        except Exception as e:
            falhas += 1
            print(f"  [{i}/{total}] match {mid} FALHOU: {e}", flush=True)
        if i % 50 == 0 or i == total:
            dt = time.time() - t0
            rate = i / dt if dt > 0 else 0
            eta_min = (total - i) / rate / 60 if rate > 0 else float("nan")
            print(f"  [{i}/{total}] ok={ok} falhas={falhas} "
                  f"({rate:.2f}/s, ETA {eta_min:.0f} min)", flush=True)

    n = conn.execute("SELECT COUNT(DISTINCT match_id) FROM match_maps").fetchone()[0]
    print(f"match_maps: {n} partidas com mapa a mapa ({ok} novas, {falhas} falhas)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="processa só as N primeiras partidas pendentes")
    ap.add_argument("--teams", default=None,
                    help="restringe a partidas com pelo menos um desses "
                         "times (separados por vírgula)")
    args = ap.parse_args()
    teams = [t.strip() for t in args.teams.split(",")] if args.teams else None
    sys.exit(run(args.limit, teams=teams))
