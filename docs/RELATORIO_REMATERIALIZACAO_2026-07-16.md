# Rematerialização autorizada — 2026-07-16

## Protocolo

Elo H1, Elo por mapa H3 e Platt H2 foram reconstruídos sobre `cs.db` em modo
read-only. O backtest passou a usar semente neutra 1400, normalização de
formato pelo placar/rótulo e ordem estritamente prequential. A escrita dos
artefatos foi autorizada explicitamente e executada pelas flags
`--write-artifacts`.

| Modelo | Resultado corrigido |
|---|---|
| H1 Elo de série | Brier 0,4602; acerto 62,5%; DM p<0,0001; COMPROVADA |
| H2 Platt simétrico | Brier 0,4602 → 0,4538; DM p<0,00001; COMPROVADA |
| H3 Elo por mapa | Brier 0,4892 vs 0,4880; DM p=0,8031; REFUTADA |
| H4 contextual | experimental; não promovida ao core |

Novo Platt: `a=0,662721`, `b=0`. H1 + H2 permanece o modelo canônico. H3
continua apenas experimental mesmo com `ratings_maps.json` reconstruído.

## Hashes depois da rematerialização

| Artefato | SHA-256 |
|---|---|
| `cs.db` | `a7dbef610b176250e3b1d7fe91ac2d79acac13e2c258884c46e35ab0e2c6f2ee` |
| `ratings.json` | `3b2bb5cb916259c66dcebd93f5162fa030c8fbc6c2c8462ba12b10a87918f56` |
| `ratings_maps.json` | `1f2cfb0884ff55599fe96a7f0e4284ddbf9cb863d3a44e4a3c7c188c26074ca` |
| `calibration_platt.json` | `85012b55979e3e3fb289cf5e09f766d407d40a97524b5c995294b479f4e09569` |

## PRE_EVENT já congelados

Os PRE_EVENT de 17 de julho não foram recriados. Eles continuam vinculados aos
hashes e probabilidades originais e devem ser maturados com esses valores:

| Jogo | Probabilidade forward congelada |
|---|---|
| 3DMAX × Gentle Mates | Gentle Mates 69,43% |
| K27 × Phantom | K27 54,04% |
| Ninjas in Pyjamas × HEROIC | Ninjas in Pyjamas 54,69% |

Recalcular hoje produziria números ligeiramente diferentes, mas seria uma nova
execução pós-snapshot e não pode substituir evidência forward existente.
