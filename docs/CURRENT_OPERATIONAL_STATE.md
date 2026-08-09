# Estado operacional vigente

Vigência: 2026-08-09.

Este documento é a declaração operacional canônica do `cs-predictor`.

- Modo científico e operacional autorizado: `COLLECTION_ONLY`.
- Único job de produção permitido: `cs-archival-collection`.
- Beyond Market: `CLOSED_BY_HUMAN_DECISION` e `NO_GO`.
- Operações financeiras, ordens, apostas, market shadow e settlement de
  mercado: não autorizados.
- `cs-settle`: bloqueado, informativo e sempre encerra com código 2.
- `cs-predict` e `cs-ingest-hltv`: somente laboratório; exigem
  `--laboratory` ou `CS_LABORATORY=1`.
- `cs-collect` e `cs-scheduler`: superfícies autorizadas exclusivamente para
  coleta arquivística.

Um processo `SUCCEEDED` significa apenas que a execução operacional terminou
corretamente. Ele não promove coleta a evidência, não muda `ScientificState` e
não autoriza capital.

A decisão de encerramento está selada em
[`records/beyond_market_closure.json`](records/beyond_market_closure.json). Os
datasets científicos estão identificados pelos protocolos em
[`records/protocol_db_cutoff.json`](records/protocol_db_cutoff.json) e
[`records/protocol_db_full.json`](records/protocol_db_full.json).

Qualquer mudança deste estado exige decisão humana explícita, novo registro de
governança versionado e revisão dos controles fail-closed. A existência de
código histórico em `docs/evidence/` não constitui autorização operacional.
