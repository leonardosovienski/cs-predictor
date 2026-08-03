"""Simulação de P&L (paper) do modelo Elo contra preços reais do Polymarket.

Lê data/historical_market_sample.jsonl (gerado por
docs/evidence/market_shadow/scripts/backtest_market_historical.py) e simula,
em ordem cronológica, uma banca fictícia que aposta apenas quando o modelo
diverge do preço de mercado (edge positivo), usando o mesmo staking
(quarter-Kelly, cap 2% da banca) já implementado em src/betting.py.

Isto é PURAMENTE RETROSPECTIVO e PAPEL — nenhuma aposta real é feita ou
sugerida. Resultado não substitui os gates forward-only do projeto.

Uso:
    uv run python scripts/simulate_bankroll_pnl.py
    uv run python scripts/simulate_bankroll_pnl.py --input data/historical_market_sample.jsonl \
        --bankroll 1000 --min-edge 0.02
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.betting import kelly_stake  # noqa: E402


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"arquivo nao encontrado: {path} — rode primeiro "
                  "docs/evidence/market_shadow/scripts/backtest_market_historical.py")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.sort(key=lambda r: r["match_ts"])
    return rows


def simulate(rows: list[dict], bankroll0: float, min_edge: float) -> dict:
    bankroll = bankroll0
    peak = bankroll0
    max_drawdown_pct = 0.0
    bets = []

    for row in rows:
        model_a = row["model_probability_a"]
        market_a = row["market_probability_a"]
        outcome_a = row["outcome_a"]

        # decimal odds implícitas do preço Polymarket (sem vig separado; preço
        # binário já é a probabilidade "de casa" do mercado)
        odds_a = 1.0 / market_a
        odds_b = 1.0 / (1.0 - market_a)

        edge_a = model_a * odds_a - 1
        edge_b = (1 - model_a) * odds_b - 1

        if edge_a <= min_edge and edge_b <= min_edge:
            continue  # sem edge suficiente dos dois lados: não aposta

        if edge_a >= edge_b:
            side, prob, odds, won = "A", model_a, odds_a, outcome_a == 1
        else:
            side, prob, odds, won = "B", 1 - model_a, odds_b, outcome_a == 0

        try:
            stake = kelly_stake(prob, odds, bankroll)
        except ValueError:
            continue
        if stake <= 0:
            continue

        pnl = stake * (odds - 1) if won else -stake
        bankroll += pnl
        peak = max(peak, bankroll)
        drawdown_pct = (peak - bankroll) / peak * 100 if peak > 0 else 0
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)

        bets.append({
            "match_id": row["match_id"], "date": row["date"],
            "team_a": row["team_a"], "team_b": row["team_b"],
            "side": side, "prob_model": round(prob, 4), "odds": round(odds, 4),
            "edge": round(prob * odds - 1, 4), "stake": stake, "won": won,
            "pnl": round(pnl, 2), "bankroll_after": round(bankroll, 2),
        })

        if bankroll <= 0:
            break

    n = len(bets)
    wins = sum(1 for b in bets if b["won"])
    total_staked = sum(b["stake"] for b in bets)
    total_pnl = bankroll - bankroll0

    return {
        "config": {"bankroll_inicial": bankroll0, "min_edge": min_edge,
                   "kelly_shrink": 0.25, "kelly_cap_pct_banca": 0.02},
        "candidatos_avaliados": len(rows),
        "apostas_feitas": n,
        "apostas_vencidas": wins,
        "win_rate_apostado": round(wins / n, 4) if n else None,
        "total_staked": round(total_staked, 2),
        "bankroll_final": round(bankroll, 2),
        "pnl_total": round(total_pnl, 2),
        "roi_sobre_banca_inicial_pct": round(total_pnl / bankroll0 * 100, 2),
        "roi_sobre_total_staked_pct": round(total_pnl / total_staked * 100, 2) if total_staked else None,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "media_edge_apostado": round(st.mean(b["edge"] for b in bets), 4) if n else None,
        "bets": bets,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "historical_market_sample.jsonl")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--min-edge", type=float, default=0.02,
                     help="edge mínimo (prob_model*odds - 1) pra considerar apostar")
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "bankroll_simulation.json")
    args = ap.parse_args(argv)

    rows = load_rows(args.input)
    result = simulate(rows, args.bankroll, args.min_edge)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {k: v for k, v in result.items() if k != "bets"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n(detalhe aposta a aposta em {args.output})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
