# Stake Ranked Episode 3 — comparação retrospectiva

## Estado de evidência temporal: BLOCKED

Este documento compara a fixture EP3 preservada no commit `71e01ab` com os
resultados. Não é um PRE_EVENT, não cria MATURED e não é evidência forward.
Nenhum resultado abaixo pode ser promovido ao core ou usado para métricas de
produção.

| Série BO3 | Probabilidade do favorito na fixture | Resultado oficial | Acerto | Brier |
|---|---:|---|---:|---:|
| Ninjas in Pyjamas × K27 | NIP 53,45% | NIP 2–0 K27 | sim | 0,21669025 |
| 3DMAX × HEROIC | HEROIC 54,23% | 3DMAX 1–2 HEROIC | sim | 0,20948929 |
| Wildcard × Gentle Mates | Wildcard 57,58% | Wildcard 0–2 Gentle Mates | não | 0,33154564 |
| paiN × Phantom | paiN 62,36% | paiN 1–2 Phantom | não | 0,38887696 |

Resumo retrospectivo: 2/4 acertos; Brier médio `0,28665054`.

## Proveniência e limitações

- Predições reproduzidas de `data/fixtures/stake_ranked_ep3.json` pelo script
  somente-leitura `scripts/predict_matches.py`, com Elo H1 e Platt H2
  canônicos; nenhuma atualização de rating, banco ou modelo foi feita.
- Resultados: [NIP × K27](https://www.hltv.org/matches/2395696/ninjas-in-pyjamas-vs-k27-stake-ranked-episode-3), [3DMAX × HEROIC](https://www.hltv.org/matches/2395697/3dmax-vs-heroic-stake-ranked-episode-3), [Wildcard × Gentle Mates](https://www.hltv.org/matches/2395698/wildcard-vs-gentle-mates-stake-ranked-episode-3) e [paiN × Phantom](https://www.hltv.org/matches/2395699/pain-vs-phantom-stake-ranked-episode-3).
- Sem pool/veto, odds, ajuste manual de roster ou ajuste regional. Não há OPEN,
  SETTLED, closing, shadow econômico, CLV ou ROI.
