# Relatório da Fase 1 — cs-predictor (2026-07-11)

> **Registro histórico, superado pela auditoria de 2026-07-16.** A execução
> original usou o Top 30 de julho/2026 como semente de partidas anteriores e
> continha formatos inconsistentes. O backtest corrigido usa semente neutra,
> normaliza formato sem escrever no banco e, em execução read-only, obteve
> Brier 0,4602, acerto 62,5% e DM p<0,0001. Os ratings e a calibração canônicos
> foram rematerializados com autorização em 2026-07-16; veja
> `RELATORIO_REMATERIALIZACAO_2026-07-16.md` (neste mesmo diretório histórico).

> **Nao usar como resultado canonico atual.** O replay precisa ser refeito
> apos a correcao de 2026-07-29: o update Elo agora compara vencedor da serie
> com P(vencer a serie), e nao com P(vencer um mapa).

## Fonte e dataset

**HLTV de primeira mão**: o 403 da Fase 0 caiu com curl_cffi + impersonate
Chrome (mesma técnica do Sofascore na plataforma). `src/data/hltv_provider.py`
pagina `/results` com 2s de cortesia; **17.100 séries** coletadas
(2024-12-22 → 2026-07-11; bo1 4.238, bo3 12.729, bo5 133; 1.008+ times de
todas as tiers).

## Metodologia

Backtest **prequential** (prever antes de atualizar): Elo por MAPA, P(série)
pela combinatória exata do formato real, update com K por formato (32/40/48)
— o contrato exato do `EloModel` da Fase 0. Semente = HLTV Top 30 de
2026-07-06; desconhecidos em 1400. Burn-in 90 dias; métrica só conta série
com ambos os times ≥10 de histórico (**n medido = 10.671**). Governança
completa: harness do critério PASSOU → H1-CS pré-registrada → só então o
backtest rodou.

## H1-CS — Elo vivido vs ranking-semente congelado

| Métrica | Modelo | Baseline semente | Coin-flip |
|---|---|---|---|
| Brier | **0,4573** | 0,4956 | 0,5000 |
| Log-loss | **0,6506** | 0,6886 | 0,6931 |
| Acerto | 62,6% | — | 50% |
| Diebold-Mariano | **p < 0,0001** (stat −9,13) | | |

**VEREDITO: COMPROVADA.** O Elo vivido carrega informação real — e repare
que o baseline-semente é quase coin-flip (0,4956): fora do Top 30 ele não
distingue ninguém, então a prova é de que o Elo APRENDE dos resultados, não
só herda o ranking.

### Calibração — o achado que importa

| Faixa prevista | n | Previsto | Real |
|---|---:|---:|---:|
| 0,0–0,1 | 89 | 0,07 | **0,19** |
| 0,1–0,2 | 412 | 0,16 | **0,27** |
| 0,5–0,6 | 1.903 | 0,55 | 0,55 |
| 0,8–0,9 | 901 | 0,84 | **0,77** |
| 0,9–1,0 | 236 | 0,93 | **0,88** |

O modelo é **sobreconfiante nas duas pontas**: zebras de CS vencem bem mais
do que a logística /400 prevê. Leitura de domínio: variância de mapa
(veto/side/forma do dia) e roster changes comprimem a distância real entre
os times. Correções candidatas — escala maior que 400, K menor, regressão à
média em inatividade — são TODAS tentativas N+1 no registro (o DSR
desconta); nenhuma foi rodada.

## Serving materializado

`data/ratings.json` — Elo vivido de **1.227 times**; o `predict` da Fase 0
passa a usá-lo automaticamente (ratings_file sobrepõe a semente).

### Correção de simetria do Platt (2026-07-17 UTC)

O Platt original permitia intercepto não-zero (`b=0,095752`), fazendo a
probabilidade depender da ordem team_a/team_b. A tentativa
`h2-cs-elo-platt-symmetric-prequential` fixou `b=0` e tornou obrigatório
`cal(1-p)=1-cal(p)`.

No backtest expanding forward-only com 10.699 séries, o calibrador simétrico
permaneceu **COMPROVADO**: Brier `0,4570 → 0,4523`, Diebold-Mariano
`p<0,00001`. O serving foi rematerializado com `a=0,702036` e `b=0`.

## Fase 1b (futura)

Sem odds históricas gratuitas de CS. Caminho para mercado: coleta de odds
ao vivo em modo sombra (padrão H3 do brasileirão) com o vencedor da série
como modelo — e ciente da sobreconfiança nas pontas ANTES de precificar
qualquer coisa.
