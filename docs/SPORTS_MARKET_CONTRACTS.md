# Sports DB, Market DB e Beyond Market

## Separação obrigatória

`data/cs.db` é o **Sports DB**: séries e mapas HLTV que medem capacidade
esportiva. Não contém odds e não pode, sozinho, sustentar ROI, CLV ou edge.
`data/market.db` é o **Market DB** local: somente moneylines de série com
provedor, bookmaker, timestamp, lote, proveniência e mapeamento canônico.

Os snapshots `PRE_EVENT`/`MATURED` continuam em `snapshots/` e preservam seu
hash de vínculo local; não foram substituídos por este contrato.

## Sports DB

`sports_series_metadata` registra, para cada série materializada, `source`,
`source_event_id`, `match_start_at`, IDs das equipes, formato, competição,
roster conhecido, `result_available_at`, lote de ingestão e SHA-256 de
proveniência. Resultado anterior ao início, formato inválido, identidade
colapsada ou hash inválido são rejeitados.

Roster é point-in-time: ausência é registrada como ausência; nunca se aplica o
roster final retrospectivamente.

## Market DB

Uma cotação só é aceita se for `moneyline` de `series`, possuir bookmaker,
odds decimais e probabilidades finitas, e tiver sido capturada antes do início.
`opening` e `closing` devem declarar a versão da definição. Dataset sem
timestamp confiável é classificado como não econômico e fica fora do Market DB.

O arquivo JSONL histórico de shadow anterior a este contrato permanece como
telemetria legada e não é promovido automaticamente: faltam competição e
mapeamento revisado para parte das linhas.

## Event Mapping

`canonical_event_id` é SHA-256 truncado de: versão de canonicalização, IDs de
equipe, início UTC arredondado ao minuto, formato, competição e escopo. A ordem
dos lados não muda o identificador. Estados permitidos: `EXACT`, `RULE_BASED`,
`MANUAL_CONFIRMED`, `AMBIGUOUS`, `REJECTED`. Só os três primeiros liberam uma
cotação para análise; academy/principal, mapa/série, formato divergente ou mais
de uma partida candidata são rejeitados.

## Beyond Market e gates

O validador divide por tempo: treina o blend mercado+modelo numa janela anterior
e mede log loss, Brier e acerto em janela posterior. Compara mercado, modelo e
combinação; nunca treina e testa no mesmo período. Seu melhor resultado é
`GATE_PASSED_FOR_PROSPECTIVE_SHADOW` e continua com `counts_toward_financial_gate=false`.

O gate econômico exige CLV, ROI líquido, custos, IC95, cobertura e concentração
prospectivos. Nenhum arquivo, teste ou comando libera capital automaticamente;
`record_bet(real=True)` sempre falha fechada.

## Migração e settlement prospectivo

`python scripts/migrate_prospective_market.py --backup-dir backups/<nome>` cria
backup consistente antes de materializar o contrato. Séries históricas sem
roster point-in-time ou `result_available_at` exato recebem `PARTIAL`, nunca
campos inventados. Quotes legados sem `source_event_id` e competição recebem
`REJECTED_MAPPING`; não são eliminados do log, mas ficam fora da avaliação.

Estados de evento: `PRE_EVENT`, `EVENT_TIME_PASSED`, `RESULT_PENDING`,
`RESULT_VALIDATED`, `CLOSING_PENDING`, `SETTLEMENT_READY`, `MATURED`, `VOID`,
`REJECTED`. `EVENT_TIME_PASSED` não é maturidade. Closing é a última cotação
elegível estritamente anterior ao início (`last-valid-pre-event/1`); resultado
validado + closing + modelo congelado produzem settlement idempotente.
