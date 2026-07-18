# cs-predictor

> **Status: Fase 1 CONCLUÍDA (2026-07-11).** HLTV destravado (curl_cffi
> impersonate); 17.100 séries coletadas e backtest prequential rodado:
> **H1 (Elo vencedor da série) COMPROVADA** — Brier 0,4573 vs semente
> 0,4956, acerto 62,6%, DM p<1e-4 — com **sobreconfiança nas pontas**
> documentada (zebra vence mais que o /400 diz). Elo vivido de 1.227 times
> em `data/ratings.json`. **Sem odds, sem apostas** (Fase 1b exigiria fonte
> de odds). Relatório: `docs/RELATORIO_FASE1.md`. Não é ferramenta de
> investimento.

Laboratório de previsão de **partidas de Counter-Strike 2** (vencedor da
série, handicap e total de mapas), sexto consumidor do ecossistema
`predictor_core`. 100% local (Python 3.13 + arquivos), sem cloud.

## Por que Elo (e não Poisson)

CS2 é jogo de rounds (first to 13 no MR12, com overtime), mas modelar round a
round exige dado que o esqueleto não tem. O Elo captura força relativa a
partir do histórico:

```
P(A vence um MAPA) = 1 / (1 + 10^((elo_B − elo_A)/400))
```

O rating é interpretado **por mapa**; vencedor da série (BO1/BO3/BO5), total
esperado de mapas e handicap (±1.5) saem da combinatória exata da série com
mapas i.i.d. — simplificação declarada da Fase 0. Extensões da Fase 1+:
pontos fortes por mapa, fator CT/TR, forma recente, economia de rounds.

Elo inicial semeado do **ranking HLTV Top 30 de 2026-07-06** (linear:
#1=1600 → #30=1300, regra do prompt de criação). K-factor por formato:
BO1=32, BO3=40, BO5=48. `update_ratings` persiste a evolução em
`data/ratings.json` (soma zero conservada).

## Uso

```bash
.venv\Scripts\python.exe -m src.predict Vitality MOUZ --format bo3
.venv\Scripts\python.exe -m src.predict Falcons Spirit --handicap -1.5 --json
.venv\Scripts\python.exe -m src.predict FURIA paiN --format bo5

# Testes e CI
.venv\Scripts\python.exe -m pytest tests/ -v
.venv\Scripts\python.exe scripts/ci_check.py
```

Toda previsão é carimbada com `PredictionPoint` do core (matures_at = início
+ duração típica do formato: 1h30/3h/5h), registrada em
`data/predictions.jsonl` (append-only, override por env) e emitida na
telemetria (domínio `cs`).

## Estrutura

```
config.yaml                 # game, formato default, K base, banca
src/
  config.py                 # load_config/load_teams/resolve_team (+vendor no path)
  model.py                  # EloModel (predict_match/predict_handicap/update_ratings)
  predict.py                # CLI de serving + PredictionPoint + telemetria
  data/hltv_provider.py     # stub HLTV (403 a cliente simples; Fase 1 decide a via)
data/teams_cs.json          # HLTV Top 30 (2026-07-06) com Elo semente
scripts/ci_check.py         # 3 barreiras: pytest, .ps1 ASCII, parse+smoke
tests/                      # 85 testes (modelo, serving, config, core, higiene)
vendor/predictor_core/      # v1.3.1 via sync_core (NÃO editar à mão)
```

## Roadmap

| Fase | Escopo | Status |
|---|---|---|
| 0 | Esqueleto: estrutura, vendor, Elo base, serving, CI | ✅ |
| 1 | Dados históricos Tier 1 (HLTV) + backtest walk-forward | ✅ H1 comprovada |
| 2 | Governança: harness + TrialRegistry + calibração Platt H2 | ✅ H2 comprovada (Platt calibrado, `data/calibration_platt.json`) |
| 3 | Operação: odds, bet_log, settle | ⏳ (só após GO financeiro — não construído) |
