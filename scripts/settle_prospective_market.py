"""Liquidação EM PAPEL da coorte shadow: resultado oficial (Sports DB) -> Market DB shadow.

Isto é liquidação científica (Brier/log-loss do modelo contra a última cotação
Polymarket pré-evento), não financeira: nunca move capital, nunca chama
`record_bet(real=True)` e nunca escreve em `data/market.db` (que permanece
exclusivamente sob o encerramento de 2026-07-23). Grava apenas em
`data/market_shadow.db`, sob o gate `SHADOW_ONLY_NO_CAPITAL`.

Correção de nomenclatura (2026-08-14): a cotação usada como referência de
"closing" é a última observação do próprio Polymarket antes do início — não
uma closing line externa, independente e líquida. Isso mede divergência
modelo-mercado (Brier/log-loss), não CLV verdadeiro. Ver
`ProspectiveStore.status()["clv_available"]` (sempre `False`).

O resultado oficial vem do Sports DB (`data/cs.db`, alimentado por
`src.ingest_hltv`). Este script NÃO inventa resultado: evento sem partida
correspondente permanece `RESULT_PENDING`, que é o estado correto.

`result_available_at` é o instante desta liquidação — quando o resultado ficou
disponível PARA NÓS. É conservador de propósito: nunca antecipa disponibilidade,
portanto não pode fabricar lookahead.

Uso:
    python scripts/settle_prospective_market.py            # liquida o que der
    python scripts/settle_prospective_market.py --dry-run  # só relata
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import identity_key  # noqa: E402
from src.market_db import ContractError  # noqa: E402
from src.prospective_market import ProspectiveStore  # noqa: E402

SPORTS_DB = ROOT / "data" / "cs.db"
MARKET_DB = ROOT / "data" / "market_shadow.db"


def official_result(sports: sqlite3.Connection, team_a: str, team_b: str,
                    match_start_at: str) -> dict | None:
    """Partida oficial correspondente, com +-1 dia de folga no calendário.

    A folga cobre fuso e partida que vira o dia. A identidade segue o MESMO
    contrato de `EloModel._elo` (`src/model.py`): caixa exata resolve primeiro;
    casamento por `identity_key` só é aceito quando é ÚNICO na janela. O HLTV
    tem organizações DISTINTAS que diferem só pela caixa (LEO/Leo, CHAOS/Chaos,
    WINNERS/Winners) — resolver essas por aproximação devolveria o resultado da
    equipe errada. Ambiguidade vira ausência, nunca escolha."""
    day = match_start_at[:10]
    janela = sports.execute(
        "SELECT match_id, team_a, team_b, score_a, score_b, event FROM matches "
        "WHERE date BETWEEN date(?, '-1 day') AND date(?, '+1 day')",
        (day, day)).fetchall()

    def _casa(cand_a: str, cand_b: str, exato: bool) -> bool:
        if exato:
            return {cand_a, cand_b} == {team_a, team_b}
        return ({identity_key(cand_a), identity_key(cand_b)}
                == {identity_key(team_a), identity_key(team_b)})

    row = [r for r in janela if _casa(r[1], r[2], exato=True)]
    if not row:  # sem caixa exata: aceita casefold só se for único
        row = [r for r in janela if _casa(r[1], r[2], exato=False)]
    if len(row) != 1:            # 0 = ausente, >1 = ambíguo: ambos falham fechado
        return None
    match_id, s_a, s_b, score_a, score_b, event = row[0]
    if score_a == score_b:       # empate (BO2) não tem vencedor: não liquida
        return None
    # Normaliza a orientação do placar para a do evento de mercado. A comparação
    # usa identity_key porque o casamento acima pode ter sido por caixa
    # (HEROIC/Heroic): comparar cru inverteria o placar e o vencedor.
    if identity_key(s_a) == identity_key(team_a):
        placar = {"team_a": score_a, "team_b": score_b}
        vencedor = team_a if score_a > score_b else team_b
    else:
        placar = {"team_a": score_b, "team_b": score_a}
        vencedor = team_b if score_a > score_b else team_a
    return {"match_id": match_id, "winner": vencedor, "score": placar, "event": event}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="relata sem escrever")
    ap.add_argument("--sports-db", type=Path, default=SPORTS_DB)
    ap.add_argument("--market-db", type=Path, default=MARKET_DB)
    args = ap.parse_args(argv)

    sports = sqlite3.connect(f"file:{args.sports_db}?mode=ro", uri=True)
    store = ProspectiveStore(args.market_db)
    conn = store.connect()
    agora = datetime.now(UTC).isoformat(timespec="seconds")
    contagem = {"maturados": 0, "sem_resultado": 0, "ja_maturado": 0, "erro": 0}
    try:
        pendentes = conn.execute(
            "SELECT event_key, team_a, team_b, match_start_at, event_state "
            "FROM prospective_events WHERE mapping_status IN ('RULE_BASED','REVIEWED') "
            "AND event_state != 'MATURED' ORDER BY match_start_at").fetchall()
        for event_key, team_a, team_b, start, estado in pendentes:
            if start >= agora:                       # ainda não aconteceu
                continue
            achado = official_result(sports, team_a, team_b, start)
            if achado is None:
                contagem["sem_resultado"] += 1
                print(f"  PENDENTE  {team_a} x {team_b} ({start[:10]}) — sem resultado oficial")
                continue
            if args.dry_run:
                contagem["maturados"] += 1
                print(f"  [dry-run] {team_a} x {team_b} -> vencedor {achado['winner']} "
                      f"{json.dumps(achado['score'])}")
                continue
            try:
                store.record_result(conn, event_key=event_key, winner=achado["winner"],
                                    score=achado["score"],
                                    result_source=f"hltv:{achado['match_id']}",
                                    result_available_at=agora)
                estado_final = store.settle(conn, event_key=event_key)
                if estado_final == "MATURED":
                    contagem["maturados"] += 1
                else:
                    contagem["erro"] += 1
                print(f"  {estado_final:<16} {team_a} x {team_b} -> {achado['winner']}")
            except (ContractError, ValueError) as exc:
                contagem["erro"] += 1
                print(f"  ERRO      {team_a} x {team_b}: {exc}")
        print(json.dumps(contagem, sort_keys=True))
        return 0 if contagem["erro"] == 0 else 1
    finally:
        conn.close()
        sports.close()


if __name__ == "__main__":
    raise SystemExit(main())
