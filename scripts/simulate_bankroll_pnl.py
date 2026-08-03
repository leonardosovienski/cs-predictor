"""Simulação de P&L (paper) do modelo Elo contra preços reais do Polymarket.

Lê data/historical_market_sample.jsonl (gerado por
docs/evidence/market_shadow/scripts/backtest_market_historical.py) e simula,
em ordem cronológica, uma banca fictícia que aposta apenas quando o modelo
diverge do preço de mercado (edge positivo), usando staking Kelly fracionário
(default: mesmos parâmetros de src/betting.py — quarter-Kelly, cap 2%).

Suporta duas correções empíricas para o overconfidence do modelo nas pontas
(medido no walk-forward): --min-edge mais alto (filtra ruído de calibração) e
--blend-market (encolhe a probabilidade do modelo em direção à do mercado,
que historicamente é melhor calibrado — brier_market < brier_model).

Isto é PURAMENTE RETROSPECTIVO e PAPEL — nenhuma aposta real é feita ou
sugerida. Resultado não substitui os gates forward-only do projeto.

Uso:
    uv run python scripts/simulate_bankroll_pnl.py
    uv run python scripts/simulate_bankroll_pnl.py --min-edge 0.10 --blend-market 0.5
    uv run python scripts/simulate_bankroll_pnl.py --sweep
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_rows(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"arquivo nao encontrado: {path} — rode primeiro "
                  "docs/evidence/market_shadow/scripts/backtest_market_historical.py")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows.sort(key=lambda r: r["match_ts"])
    return rows


def kelly_stake(prob: float, odds: float, bankroll: float, shrink: float, cap: float) -> float:
    if not 0 < prob < 1 or odds <= 1 or bankroll <= 0:
        raise ValueError("prob, odds ou bankroll invalidos")
    raw = max(0.0, (prob * odds - 1) / (odds - 1))
    return round(bankroll * min(raw * shrink, cap), 2)


def simulate(rows: list[dict], bankroll0: float, min_edge: float,
             kelly_shrink: float, kelly_cap: float, blend_market: float) -> dict:
    bankroll = bankroll0
    peak = bankroll0
    max_drawdown_pct = 0.0
    bets = []

    for row in rows:
        market_a = row["market_probability_a"]
        outcome_a = row["outcome_a"]
        # blend_market=0 -> puro modelo; 1 -> puro mercado (aposta zero, sem edge)
        model_a = (1 - blend_market) * row["model_probability_a"] + blend_market * market_a

        odds_a = 1.0 / market_a
        odds_b = 1.0 / (1.0 - market_a)

        edge_a = model_a * odds_a - 1
        edge_b = (1 - model_a) * odds_b - 1

        if edge_a <= min_edge and edge_b <= min_edge:
            continue

        if edge_a >= edge_b:
            side, prob, odds, won = "A", model_a, odds_a, outcome_a == 1
        else:
            side, prob, odds, won = "B", 1 - model_a, odds_b, outcome_a == 0

        try:
            stake = kelly_stake(prob, odds, bankroll, kelly_shrink, kelly_cap)
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
                   "kelly_shrink": kelly_shrink, "kelly_cap_pct_banca": kelly_cap,
                   "blend_market": blend_market},
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


SWEEP_GRID = [
    # (min_edge, kelly_shrink, kelly_cap, blend_market, label)
    (0.02, 0.25, 0.02, 0.0, "baseline (original)"),
    (0.10, 0.25, 0.02, 0.0, "edge alto (>=10%)"),
    (0.15, 0.25, 0.02, 0.0, "edge muito alto (>=15%)"),
    (0.02, 0.10, 0.01, 0.0, "Kelly conservador"),
    (0.02, 0.25, 0.02, 0.5, "blend 50% mercado"),
    (0.02, 0.25, 0.02, 0.8, "blend 80% mercado"),
    (0.10, 0.10, 0.01, 0.5, "edge alto + Kelly conservador + blend 50%"),
]


def _print_grid(rows: list[dict], bankroll0: float) -> None:
    header = (f"{'config':40} {'apostas':>8} {'win%':>7} {'roi%':>9} "
              f"{'drawdown%':>10} {'bankroll_final':>15}")
    print(header)
    print("-" * len(header))
    for min_edge, shrink, cap, blend, label in SWEEP_GRID:
        r = simulate(rows, bankroll0, min_edge, shrink, cap, blend)
        win_pct = f"{r['win_rate_apostado']*100:.1f}" if r["win_rate_apostado"] is not None else "-"
        print(f"{label:40} {r['apostas_feitas']:>8} {win_pct:>7} "
              f"{r['roi_sobre_banca_inicial_pct']:>9.1f} {r['max_drawdown_pct']:>10.1f} "
              f"{r['bankroll_final']:>15.2f}")


def run_sweep(rows: list[dict], bankroll0: float) -> None:
    """Grid direto na amostra inteira. AVISO: qualquer config vencedora aqui foi
    escolhida olhando os mesmos dados usados pra medi-la (data snooping) —
    use --holdout pra validar antes de acreditar em qualquer resultado positivo."""
    _print_grid(rows, bankroll0)


def run_holdout(rows: list[dict], bankroll0: float) -> None:
    """Escolhe a config vencedora só na primeira metade cronológica (calibração)
    e aplica, sem re-escolher nada, na segunda metade (validação) — sem
    lookahead, igual ao resto do backtest prequential do projeto."""
    cut = len(rows) // 2
    calib_rows, val_rows = rows[:cut], rows[cut:]
    print(f"calibração: {len(calib_rows)} casos ({calib_rows[0]['date']}..{calib_rows[-1]['date']})")
    print(f"validação:  {len(val_rows)} casos ({val_rows[0]['date']}..{val_rows[-1]['date']})\n")

    print("=== grid na metade de CALIBRAÇÃO (só pra escolher a config) ===")
    _print_grid(calib_rows, bankroll0)

    best = max(SWEEP_GRID, key=lambda cfg: simulate(calib_rows, bankroll0, *cfg[:4])["roi_sobre_banca_inicial_pct"])
    min_edge, shrink, cap, blend, label = best
    print(f"\nvencedora na calibração: {label!r}")

    print("\n=== mesma config aplicada na metade de VALIDAÇÃO (sem re-escolher nada) ===")
    r = simulate(val_rows, bankroll0, min_edge, shrink, cap, blend)
    print(json.dumps({k: v for k, v in r.items() if k != "bets"}, ensure_ascii=False, indent=2))
    if r["roi_sobre_banca_inicial_pct"] <= 0:
        print("\n=> ROI positivo na calibração NÃO se sustentou na validação: "
              "era ruído/overfitting, não edge real.")
    else:
        print("\n=> ROI positivo se manteve fora da amostra de calibração — "
              "ainda é pouco dado pra confiança alta, mas é um sinal melhor que o grid sozinho.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=ROOT / "data" / "historical_market_sample.jsonl")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--min-edge", type=float, default=0.02,
                     help="edge mínimo (prob_model*odds - 1) pra considerar apostar")
    ap.add_argument("--kelly-shrink", type=float, default=0.25,
                     help="fração do Kelly completo a usar (default 0.25, igual src/betting.py)")
    ap.add_argument("--kelly-cap", type=float, default=0.02,
                     help="teto de stake como fração da banca (default 0.02)")
    ap.add_argument("--blend-market", type=float, default=0.0,
                     help="0=probabilidade pura do modelo; 1=pura do mercado; "
                          "valores intermediários encolhem o modelo em direção "
                          "ao mercado (correção pro overconfidence nas pontas)")
    ap.add_argument("--sweep", action="store_true",
                     help="roda uma grade de configurações e imprime tabela comparativa "
                          "(AVISO: escolher a melhor aqui e' data snooping — use --holdout)")
    ap.add_argument("--holdout", action="store_true",
                     help="escolhe a melhor config numa metade cronológica e valida "
                          "sem lookahead na outra metade")
    ap.add_argument("--output", type=Path, default=ROOT / "data" / "bankroll_simulation.json")
    args = ap.parse_args(argv)

    rows = load_rows(args.input)

    if args.holdout:
        run_holdout(rows, args.bankroll)
        return 0

    if args.sweep:
        run_sweep(rows, args.bankroll)
        return 0

    result = simulate(rows, args.bankroll, args.min_edge,
                       args.kelly_shrink, args.kelly_cap, args.blend_market)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {k: v for k, v in result.items() if k != "bets"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n(detalhe aposta a aposta em {args.output})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
