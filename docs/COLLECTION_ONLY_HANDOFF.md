# COLLECTION_ONLY — handoff para tools

## Escopo

`cs-archival-collection` e uma coorte arquivistica CS2 independente. Ela usa
somente fatos de fontes esportivas/resultados oficiais configurados; nao le,
nao grava e nao reabre `market.db`, `market_shadow.jsonl`, Beyond Market ou
`market_gate.json`.

## Armazenamento e operacao

Runtime separado: `data/collection_only/` (`run.json`, `archive.jsonl` e
`source_snapshots/`). O log e append-only via `CollectionArchive` do core.
Cada run recebe `collection_run_id` novo e cada fato traz `canonical_event_id`,
provenance SHA-256, hash do snapshot de fonte, commit e versao do core.

Instalacao do job: `powershell -File scripts/install_archival_collection_task.ps1`.
Ele cria apenas `cs-archival-collection`; `cs-market-shadow` deve continuar
Disabled. O job consome `data/collection_only/upstream_events.json`, exportado
por fonte esportiva oficial, e nunca automatiza servicos de apostas.

## Contrato e lifecycle

Somente series `bo1`, `bo3`, `bo5`, com `scope=series`, duas entidades exatas
e competicao. Academy e principal possuem IDs distintos; identidade ambigua,
formato invalido e mapa/serie misturados sao rejeitados. O lifecycle e:
`DISCOVERED -> VALIDATED -> SNAPSHOT_RECORDED -> EVENT_STARTED ->
OFFICIAL_RESULT_FOUND -> COMPLETE`. Horario passado apenas gera
`EVENT_STARTED`; `COMPLETE` exige `official_result` validado e posterior ao
inicio. Retries identicos sao idempotentes.

## SLO e alertas

`status()` produz `NO_UPSTREAM_EVENTS` se nao houver evento esperado,
`RESULT_INGESTION_STALLED` para evento passado sem resultado oficial e
`COLLECTION_STALLED_48H` quando um evento esperado fica 48h sem avancar.
Esses alertas nao promovem dados para ciencia, trials, gates ou capital.

## Invariantes imutaveis

Beyond Market continua `CLOSED_BY_HUMAN_DECISION`; os hashes e registros em
`docs/records/beyond_market_closure.json` sao somente leitura. Operacao real
permanece `NO_GO`.
