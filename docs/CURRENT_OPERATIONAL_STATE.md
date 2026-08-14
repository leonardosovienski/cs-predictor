# Estado operacional vigente

Vigência: 2026-08-14.

Este documento é a declaração operacional canônica do `cs-predictor`.

- Modo científico e operacional esportivo: `COLLECTION_ONLY`.
- Job de produção esportiva: `cs-archival-collection`.
- Beyond Market — **capital real**: `CLOSED_BY_HUMAN_DECISION` e `NO_GO`,
  permanentemente. Operações financeiras, ordens, apostas reais e settlement
  financeiro de mercado: não autorizados, sob nenhuma circunstância.
- Beyond Market — **coleta e liquidação em papel**: reaberto em 2026-08-14
  como `REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY` / `SHADOW_ONLY_NO_CAPITAL`,
  exclusivamente para completar a amostra mínima que o encerramento de
  2026-07-23 exigia e não atingiu (50 liquidações maturadas / 30 dias
  corridos). Jobs autorizados: `cs-market-shadow-collect`,
  `cs-market-shadow-import`, `cs-market-shadow-settle`. Gravam somente em
  `data/market_shadow.db`; a produção `data/market.db` permanece sob o
  encerramento original e não é tocada por esta reabertura.
- `cs-settle`: bloqueado, informativo e sempre encerra com código 2 — não
  muda com a reabertura shadow.
- `cs-predict` e `cs-ingest-hltv`: somente laboratório; exigem
  `--laboratory` ou `CS_LABORATORY=1`.
- `cs-collect` e `cs-scheduler`: superfícies autorizadas para coleta
  arquivística esportiva e, adicionalmente, para a coleta/liquidação shadow
  acima.

Um processo `SUCCEEDED` significa apenas que a execução operacional terminou
corretamente. Ele não promove coleta a evidência, não muda `ScientificState` e
não autoriza capital — nem no fluxo esportivo, nem no shadow.

A decisão de encerramento de capital está selada em
[`records/beyond_market_closure.json`](records/beyond_market_closure.json) e
nunca é alterada. A decisão de reabertura shadow-only está em
[`records/beyond_market_shadow_reopening.json`](records/beyond_market_shadow_reopening.json).
Os datasets científicos estão identificados pelos protocolos em
[`records/protocol_db_cutoff.json`](records/protocol_db_cutoff.json) e
[`records/protocol_db_full.json`](records/protocol_db_full.json).

Qualquer mudança deste estado exige decisão humana explícita, novo registro de
governança versionado e revisão dos controles fail-closed. A existência de
código histórico em `docs/evidence/` não constitui autorização operacional.
Atingir a amostra mínima em shadow **não** autoriza capital por si só: uma
decisão humana nova e um registro versionado adicional seriam exigidos, e o
portão de capital (`assert_beyond_market_open`) permanece incondicional e
alheio a qualquer registro de reabertura shadow.
