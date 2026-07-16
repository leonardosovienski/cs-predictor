# Avaliação Tier 1 — H4 experimental

## Protocolo

Avaliação prequential global de 199 MD3 em seis eventos Tier 1 de 2026.
Os ratings são reconstruídos cronologicamente a partir de semente neutra 1400;
nenhum ranking futuro, calibrador Platt materializado, banco ou rating de
runtime é usado como entrada.

| Modelo | Acerto | Brier |
|---|---:|---:|
| H1 Elo de série, cru | 69,35% | 0,193428 |
| H3 Elo por mapa pós-veto | 52,76% | 0,282464 |
| H4 shrinkage + recência + proxy de veto pré-jogo | **72,36%** | **0,192871** |

H4 usa Elo por mapa com decaimento de meia-vida de 60 dias e shrinkage de 12
observações para o Elo de série. O proxy de veto cria cenários a partir da
ocorrência histórica dos mapas dos dois times, usando somente jogos anteriores
à série avaliada.

## Leitura

H4 melhorou Brier em `0,000557` e acertou seis vencedores a mais que H1 no
recorte. O efeito é pequeno e não foi submetido a teste estatístico ou a uma
janela temporal adicional; portanto permanece experimento, não substitui
Elo H1 + Platt H2 nem entra na cadeia forward.

O H3 simples foi pior mesmo recebendo os mapas efetivamente jogados. Isso
reforça que rating por mapa sem shrinkage e sem modelagem de veto não deve ser
usado isoladamente.

Reprodução:

```powershell
.venv\Scripts\python.exe scripts\evaluate_tier1_events.py
```

Implementações: `src/model_maps_shrunk.py` e
`scripts/evaluate_tier1_events.py`.
