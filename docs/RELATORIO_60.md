# Relatório 60 — primeira cadeia forward real (2026-07-16)

## Estado temporal: PASS

A primeira cadeia real está íntegra e permanece fora do core do preditor:

`PRE_EVENT_CREATED → VERIFIED → MATURED → VALID_FORWARD`

| Campo | Registro |
|---|---|
| Evento | 3DMAX × HEROIC |
| Competição / stage | Stake Ranked / Episode 3 |
| Formato | BO3 |
| PRE_EVENT | `snapshots/pre_event/2026/stake-ranked-episode-3-2026-07-15-3dmax-heroic.json` |
| Hash PRE_EVENT | `19b3cf369e54eb54b010a0336ca28ab6e37b0247861effc2a81ea174395e646e` |
| MATURED | `snapshots/matured/2026/stake-ranked-episode-3-2026-07-15-3dmax-heroic.json` |
| Hash MATURED | `88c8cd790ef43b4337d5b2070785db98757568caefafc2c4c66594d4a4f16881` |
| Aliases | 3DMAX (EXACT), HEROIC (RATINGS_EXACT) |
| Freshness congelada | 3DMAX: 11 dias; HEROIC: 41 dias |
| Resultado | HEROIC venceu por 2–1 |
| Mapas | Inferno 8–13, Cache 13–8, Nuke 8–13 |
| Fonte | HLTV, registro da partida 2395697; consultado em 2026-07-16T16:31:12Z |
| Probabilidade vencedora congelada | 0,5423 (HEROIC) |
| Brier | 0,20948929 |
| Acerto | sim |

## Verificações de integridade

- O PRE_EVENT foi gerado em `2026-07-15T11:10:34Z`, antes do horário previsto nele (`12:30Z`) e antes do horário pós-jogo exibido pela HLTV (`14:00Z`).
- O MATURED referencia diretamente o hash do PRE_EVENT e o verificador aceitou o artefato original.
- `cs.db` permaneceu em `a7dbef610b176250e3b1d7fe91ac2d79acac13e2c258884c46e35ab0e2c6f2ee`; `ratings.json`, em `40379586465d8958957b068f3e65ebb59fec575f6521673e7b9674bcb132e516`.
- A maturação declara `model_reexecuted=false`, `database_write=false` e `ratings_write=false`.

## Limitações e fronteiras

- Há divergência de agenda entre o `scheduled_start_utc` congelado no PRE_EVENT (`12:30Z`) e a página pós-jogo da HLTV (`14:00Z`); ela não viola o forward, pois o PRE_EVENT é anterior aos dois horários, mas deve ser preservada na auditoria.
- Nenhuma odds foi coletada ou usada. Não há OPEN, closing, SETTLED, shadow econômico, CLV ou ROI simulado.
- EP3 continua somente como fixture histórica preservada e não é evidência forward.
