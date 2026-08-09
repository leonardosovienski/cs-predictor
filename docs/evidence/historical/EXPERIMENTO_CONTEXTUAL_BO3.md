# Laboratório contextual de BO3

O módulo `src.contextual_bo3` é uma extensão experimental, somente leitura.
Ele não substitui Elo H1 + Platt H2, não grava `cs.db`, `ratings.json`,
`ratings_maps.json` nem o ledger de previsões.

Ele combina Elo por mapa H3 com cenários explícitos de veto. Cada cenário
informa os três mapas e um peso; os pesos devem somar 1. A probabilidade de
série crua é a média ponderada dos cenários, e Platt é aplicado uma única vez
depois da agregação.

O contexto registra confirmação de lineup, jogos do core e dias desde a última
partida. Esses sinais geram `VERIFIED` ou `BLOCKED`; não modificam a
probabilidade até passarem por backtest prequential próprio.

Exemplo de entrada:

```json
{
  "team_a": "3DMAX",
  "team_b": "HEROIC",
  "veto_scenarios": [
    {"maps": ["Inferno", "Cache", "Nuke"], "weight": 1.0}
  ],
  "context": {
    "team_a": {"lineup_status": "confirmed", "days_since_last": 11, "core_matches": 10},
    "team_b": {"lineup_status": "confirmed", "days_since_last": 41, "core_matches": 5}
  }
}
```

Execute com:

```powershell
.venv\Scripts\python.exe scripts\predict_contextual_bo3.py --input evento.json
```

Para promoção futura, o próximo requisito é um backtest walk-forward de
séries que compare este laboratório com H1/H2 fora da amostra. Até então,
continue a usar H1/H2 para evidência forward canônica.
