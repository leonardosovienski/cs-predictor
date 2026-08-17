# COLLECTION_ONLY — handoff para tools

> **Documento histórico / superseded (nota adicionada em 2026-08-17).** A
> instalação via `powershell -File ..\tools\install_collection_only_tasks.ps1`
> descrita abaixo depende do repositório irmão `tools`, que
> [`docs/MODERNIZATION.md`](MODERNIZATION.md) registra como "deliberadamente
> não restaurado". Esse caminho de instalação não existe mais neste
> checkout. A operação vigente de coleta arquivística (`cs-archival-collection`)
> é declarada via `jobs.json`/`cs-scheduler` de `predictor_ops`, conforme a
> seção "Migration" de `docs/MODERNIZATION.md` e
> [`docs/CURRENT_OPERATIONAL_STATE.md`](CURRENT_OPERATIONAL_STATE.md). O
> restante deste documento é preservado como registro arquivístico do desenho
> original de handoff e não deve ser seguido literalmente.

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

Instalacao do job: `powershell -File ..\tools\install_collection_only_tasks.ps1`.
O registro canonico instala `cs-archival-collection` por `operational_runner`,
com lock, timeout, heartbeat e event log em
`%LOCALAPPDATA%\predictor-tools\runtime\cs-predictor\cs-archival-collection`.
`cs-market-shadow` deve continuar Disabled. O job consome
`data/collection_only/upstream_events.json`, exportado por fonte esportiva
oficial, e nunca automatiza servicos de apostas.

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
