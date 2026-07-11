# PROMPT — Fase 1 do cs-predictor (dados históricos + backtest walk-forward)

> Rascunho preparado em 2026-07-11, informado pelos ciclos do
> brasileirao-predictor e nba-predictor (ambos concluídos no dia anterior).
> Revisar antes de disparar.

**Projeto**: evoluir o cs-predictor da Fase 0 (Elo semeado pelo ranking) para
um modelo backtestado com dados reais de partidas Tier 1, sob a governança da
plataforma (harness → TrialRegistry → GO/NO-GO).

**Contexto do que já existe**: EloModel por mapa + combinatória de série
(BO1/BO3/BO5), `update_ratings` com K por formato, 30 times semeados do HLTV
Top 30 de 2026-07-06, suíte 26 verdes, CI 3/3, vendor core v1.1.0.

**Regras**:
- Não invente nada; reaproveite os padrões do brasileirão/NBA.
- Governança ANTES de qualquer leitura de resultado: harness de controle
  positivo → pré-registro → só então backtest.
- Nenhuma aposta real nesta fase, qualquer que seja o veredito.

---

## PASSO 0 — Sondagem da fonte (BLOQUEANTE: decide o resto)

O hltv.org responde **403 a cliente HTTP simples** (confirmado 2026-07-10).
Testar NESTA ORDEM e parar na primeira que funcionar:
1. `curl_cffi` com impersonate Chrome (o mesmo truque que destravou o
   Sofascore — portar `src/sofascore.py` do brasileirão como base).
2. Espelhos/API de terceiros (bo3.gg, egamersworld — verificar ToS e
   estabilidade; pley.gg serviu para o ranking).
3. Export manual periódico (última opção; documentar o processo).

Entregável do passo: `src/data/hltv_provider.py` sai de stub para
implementação real de `fetch_results` (partidas Tier 1 com: data, times,
formato, placar da série e POR MAPA se disponível) ou um adaptador com o
mesmo contrato para a fonte alternativa.

## PASSO 1 — Dados históricos

- Janela alvo: **2025-01-01 até hoje** (~18 meses; cobre o ciclo de Majors).
- Escopo: partidas entre os times do Top 30 + adversários que eles
  enfrentaram (o Elo precisa dos confrontos fora do Top 30 também).
- Armazenar em SQLite (`data/cs.db`): tabela `matches` (event_id ou hash,
  date, team_a, team_b, format, score_a, score_b, tier/evento) + tabela
  `maps` se o dado por mapa vier. Schema WAL + read-only P12 (padrão db.py
  do nba-predictor).
- **Odds**: não há fonte gratuita de odds HISTÓRICAS de CS confirmada. A
  Fase 1 se divide honestamente:
  - **1a (este prompt)**: backtest de SKILL sem odds — Brier/log-loss/
    calibração contra baseline (favorito do ranking; coin-flip).
  - **1b (futuro, se 1a passar)**: coleta de odds ao vivo (The Odds API tem
    `esports_csgo`? confirmar no /v4/sports) em modo sombra para acumular
    CLV prospectivo — mesmo desenho da H3 do brasileirão.

## PASSO 2 — Backtest walk-forward (prequential)

O Elo é naturalmente walk-forward: processar as partidas em ordem
cronológica, prever ANTES de atualizar (previsão → `update_ratings`).
- Burn-in: primeiros 3 meses (ratings convergem da semente).
- Métricas (todas do core `measurement/metrics.py`): **Brier**, **log_loss**,
  **calibration_table** (10 bins), acurácia vs baseline "maior Elo vence" e
  vs baseline "posição no ranking HLTV da semana" se disponível.
- Sensibilidade CONTROLADA (cada variação = tentativa N+1 no registro):
  K-factors {32/40/48 vs 24/32/40}, decaimento para a semente após
  inatividade (roster changes são o risco conhecido do Elo em CS).
- Diebold-Mariano (core) para comparar modelo vs baseline.

## PASSO 3 — Governança

1. Harness de controle positivo: série sintética com um time de força
   inflada (+100 Elo verdadeiro não refletido na semente) → o pipeline de
   avaliação (Brier vs baseline + IC bootstrap) tem que detectar; ruído
   (ratings verdadeiros = semente) tem que ser rejeitado. Atestado emitido.
2. Pré-registrar em `data/trials.json` (VERSIONADO, igual nba):
   - **H1-CS**: "Elo por mapa com K {32,40,48} prevê o vencedor da série
     melhor que o baseline de ranking (Brier menor, DM p<0,05) no período
     2025-07→2026-07". GO da fase = métrica probabilística, não ROI (sem
     odds ainda).
3. Rodar o backtest SÓ depois do registro; gravar o resultado na trial.

## PASSO 4 — Recalibração do serving

- `data/ratings.json` materializado da passada prequential completa (o Elo
  de HOJE de cada time) — o serving da Fase 0 passa a usar ratings vividos,
  não semente.
- `scripts/update_ratings_daily.py` (ou instrução de rotina) para manter.

## PASSO 5 — Testes e entrega

- Novos testes: parsers da fonte, prequential sem lookahead (prever antes de
  atualizar), persistência dos ratings, harness.
- Suíte ≥ 40 verdes, CI 3/3, working tree limpa.
- Relatório `docs/RELATORIO_FASE1.md`: dataset, Brier/log-loss vs baselines,
  tabela de calibração, veredito da H1-CS e recomendação sobre a Fase 1b
  (odds ao vivo em sombra) — SEM aposta real em nenhum cenário.
