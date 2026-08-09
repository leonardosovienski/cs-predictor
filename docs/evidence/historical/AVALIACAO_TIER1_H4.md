# Avaliação Tier 1 — H4 experimental

## Protocolo corrigido em 2026-07-16

Avaliação prequential global de 195 BO3 válidas em seis eventos Tier 1 de
2026. Os ratings são reconstruídos cronologicamente a partir da semente neutra
1400; nenhum ranking futuro, calibrador Platt materializado, banco ou rating de
runtime é usado como entrada.

| Modelo | n | Acerto | Brier |
|---|---:|---:|---:|
| H1 Elo de série, cru | 195 | 69,74% | 0,195761 |
| H3 Elo por mapa pós-veto | 80 | 65,00% | 0,225973 |
| H4 shrinkage + recência + proxy de veto pré-jogo | 195 | **70,77%** | **0,194765** |

H4 usa Elo por mapa com decaimento de meia-vida de 60 dias e shrinkage de 12
observações para o Elo de série. O proxy de veto cria cenários a partir da
ocorrência histórica dos mapas dos dois times, usando somente jogos anteriores
à série avaliada.

## Correção da avaliação anterior

A avaliação anterior aceitava somente os dois mapas jogados de séries 2–0 e
deixava massa probabilística no estado não terminal 1–1. Isso afetava 115 de
199 registros. Agora uma BO3 exige três mapas potenciais.

O banco histórico não contém o terceiro mapa planejado das séries encerradas
em 2–0. Por isso H3 só é calculado nos 80 registros completos de três mapas e
fica explicitamente classificado como diagnóstico condicionado ao resultado,
sem comparação direta de Brier contra H1.

H4 melhorou o Brier em `0,000996` contra H1. O efeito continua pequeno, sem
teste estatístico e sem holdout temporal independente. Portanto H4 permanece
experimental, não substitui Elo H1 + Platt H2 nem entra na cadeia forward.

Reprodução read-only:

```powershell
.venv\Scripts\python.exe scripts\evaluate_tier1_events.py
```

Implementações: `src/model_maps_shrunk.py` e
`scripts/evaluate_tier1_events.py`.
