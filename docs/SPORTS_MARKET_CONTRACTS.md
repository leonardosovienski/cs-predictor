# Sports DB, Market DB e Beyond Market

> **Estado canonico (atualizado 2026-08-14):** `data/market.db` (producao) e
> seu lifecycle permanecem preservados como evidencia historica e
> permanentemente fechados a capital: nenhuma mutacao, settlement financeiro
> ou avaliacao que autorize dinheiro real e aceita, sob nenhuma circunstancia.
> Por decisao humana separada e versionada
> (`docs/records/beyond_market_shadow_reopening.json`), a coleta e a
> liquidacao EM PAPEL foram reabertas num banco distinto,
> `data/market_shadow.db`, exclusivamente para completar a amostra minima que
> o encerramento de 2026-07-23 exigia e nao atingiu. Este documento descreve
> o contrato de dados; ele vale igualmente para `market.db` (fechado) e
> `market_shadow.db` (shadow), exceto onde dito o contrario.

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

### Encerramento humano da coorte de 2026-07-23 (capital — permanente)

Esta coorte esta `CLOSED_BY_HUMAN_DECISION`, com operacao real `NO_GO`. Foi
encerrada antes de atingir 50 settlements e 30 dias prospectivos; nao equivale
a aprovacao ou refutacao cientifica. O registro versionado e auditavel esta em
`docs/records/beyond_market_closure.json`. Enquanto ele existir — e ele nunca
e removido —, `assert_beyond_market_open()` falha fechado
incondicionalmente para `data/market.db` e para capital real
(`record_bet(real=True)`, `cs-settle`). Nada neste documento reabre essa
trava; ela e permanente.

### Reabertura shadow-only de 2026-08-14 (coleta e liquidacao em papel)

Por decisao humana explicita e SEPARADA, registrada em
`docs/records/beyond_market_shadow_reopening.json`
(`REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY` / `SHADOW_ONLY_NO_CAPITAL`), a
coleta Polymarket e a liquidacao EM PAPEL foram reabertas contra um banco
fisicamente distinto, `data/market_shadow.db`. O portao de codigo e outro —
`assert_market_shadow_collection_open()` — e nunca relaxa
`assert_beyond_market_open()`: mesmo com a reabertura shadow valida, o portao
de capital continua recusando `data/market.db` incondicionalmente. A
reabertura exige os tres campos auditaveis (`reopened_at_utc`,
`reopening_decision`, `supersedes_commit`); qualquer campo ausente falha
fechado, exatamente como o encerramento original. Atingir a amostra minima em
shadow (50 liquidacoes / 30 dias) nao autoriza capital — apenas informaria uma
decisao humana futura, com novo registro versionado proprio.

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
