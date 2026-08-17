# cs-predictor

Laboratório local de previsão de partidas de Counter-Strike 2 e consumidor dos
pacotes `predictor-core==2.3.0` e `predictor-ops==3.1.0`. Requer Python 3.13; Python 3.14 é
experimental. Não é uma ferramenta de investimento.

Desde a versão 3.1.0, a atualização de ratings usa o `RatingBook` do core. A
expectativa combinatória de séries BO1/BO3/BO5 continua no domínio CS2; replay
diferencial confirmou compatibilidade exata com os 1.233 ratings canônicos.

## Situação atual

O modo operacional de produção esportiva é **`COLLECTION_ONLY`**: o job
`cs-archival-collection` arquiva eventos esportivos sem consultar mercados,
executar apostas ou promover a coleta a evidência científica.

Capital real permanece permanentemente **`CLOSED_BY_HUMAN_DECISION`** e
`NO_GO`: ordens, settlement financeiro e uso de capital não são operações
permitidas em nenhuma circunstância. O registro original dessa decisão está em
[`docs/records/beyond_market_closure.json`](docs/records/beyond_market_closure.json)
e nunca é alterado.

Em 2026-08-14, por decisão humana explícita e separada, a **coleta e a
liquidação em papel** do Beyond Market foram reabertas em modo
**`REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY`** — só para completar a amostra
mínima que o encerramento de 2026-07-23 definiu e nunca atingiu (50
liquidações maturadas / 30 dias corridos; 0/50 e 2/30 quando fechou). Isso
não reabre capital: é um portão de código separado
(`assert_market_shadow_collection_open`) que nunca toca o portão de capital
(`assert_beyond_market_open`), e que só grava em `data/market_shadow.db` —
nunca na produção `data/market.db`. Ver
[`docs/records/beyond_market_shadow_reopening.json`](docs/records/beyond_market_shadow_reopening.json).
A declaração operacional completa está em
[`docs/CURRENT_OPERATIONAL_STATE.md`](docs/CURRENT_OPERATIONAL_STATE.md).

## Resultado científico canônico

Em 2026-08-09, H1 e H2 foram reexecutadas com a correção que atualiza o Elo de
série usando a probabilidade de vencer a série, e não a probabilidade latente
de vencer um único mapa.

O replay canônico usa cutoff inclusivo em **2026-07-11**:

| Medida | Resultado |
|---|---:|
| Séries no banco | 17.169 |
| Séries na janela de medição | 10.789 |
| Brier H1, Elo bruto | 0,4537 |
| Brier da referência | 0,5000 |
| Acurácia | 62,3% |
| Diebold–Mariano H1 | p < 0,0001 |
| Brier H2, Platt prequential | 0,4525 |
| Diebold–Mariano H2 | p = 0,00324 |
| Platt materializado | a = 0,8181; b = 0 |

H1 e H2 permanecem comprovadas segundo os critérios registrados. O protocolo
do dataset canônico está em
[`docs/records/protocol_db_cutoff.json`](docs/records/protocol_db_cutoff.json),
com SHA-256
`747b09077e15154caaf44c15fd0713f3375279de3fcae7ddc0b9d30dfb072b40`.

### Limite da evidência

O banco original do experimento H1 não foi preservado. O dataset atual foi
**rematerializado a partir do HLTV**, recortado em 2026-07-11, e contém 17.169
partidas — 69 a mais que o total histórico aproximado de 17.100. Portanto,
esta é uma nova materialização com o mesmo recorte temporal, não uma reprodução
byte a byte do banco original.

O banco complementar, sem cutoff, contém 17.999 partidas até 2026-08-08. Seu
protocolo está em
[`docs/records/protocol_db_full.json`](docs/records/protocol_db_full.json), mas
ele não é a base dos artefatos científicos canônicos.

## Reprodução

Instale exatamente o ambiente travado:

```bash
uv sync --frozen --extra dev
```

Quando não houver backup do banco original, rematerialize e derive o cutoff:

```bash
uv run --frozen python -m src.ingest_hltv --until 2025-01-01
uv run --frozen python scripts/derive_cutoff_db.py data/cs.db replay_data/cs_cutoff.db --cutoff 2026-07-11
uv run --frozen python scripts/protocol_db.py replay_data/cs_cutoff.db --output replay_data/protocol.json
```

Execute primeiro em modo somente leitura:

```bash
uv run --frozen python scripts/backtest_walkforward.py
uv run --frozen python scripts/backtest_calibracao.py
```

Os scripts usam `data/cs.db`. Para reproduzir o resultado canônico, faça isso
em um checkout isolado e coloque uma cópia do banco de cutoff nesse caminho.
Após revisar as métricas, materialize os derivados:

```bash
uv run --frozen python scripts/backtest_walkforward.py --write-artifacts
uv run --frozen python scripts/backtest_calibracao.py --write-artifacts
uv run --frozen --extra dev pytest -q
```

`data/ratings.json` e `data/walkforward_summary.json` são derivados
determinísticos e permanecem fora do Git. Para obter os ratings canônicos,
regenere-os sobre o banco cujo SHA-256 consta no protocolo de cutoff.

## Superfícies operacionais

Produção:

- `cs-collect`: coleta arquivística a partir do transporte configurado;
- `cs-scheduler`: `cs-archival-collection` (esportivo) ou, sob a reabertura
  shadow, `cs-market-shadow-collect` / `cs-market-shadow-import` /
  `cs-market-shadow-settle` (`--job <id>`);
- `cs-predictor health`: informa saúde e estado de governança.

Laboratório, sem autorização de produção:

- `cs-predict --laboratory`: previsão Elo/Platt e consultas de handicap;
- `cs-ingest-hltv --laboratory`: acesso exploratório ao provider;
- `python -m src.ingest_hltv`: rematerialização do Sports DB;
- scripts em `scripts/`: replay, calibração, simulação e avaliação.

Beyond Market shadow (reaberto 2026-08-14, `SHADOW_ONLY_NO_CAPITAL`, nunca
capital real):

- `scripts/collect_polymarket_upcoming.py` / `collect_polymarket_shadow.py`:
  coleta read-only de moneylines CS no Polymarket;
- `scripts/import_market_quotes.py`: importa o JSONL coletado para
  `data/market_shadow.db`;
- `scripts/settle_prospective_market.py`: liquidação EM PAPEL contra o
  resultado oficial do Sports DB (Brier/log-loss do modelo vs. a última
  cotação Polymarket pré-evento, não dinheiro — isso **não** é CLV, que
  exigiria uma closing line externa, independente e líquida; ver
  `clv_available: false` em `market_shadow_status.py`);
- `scripts/market_shadow_status.py`: progresso rumo à amostra mínima
  (50 liquidações / 30 dias);
- `scripts/validate_beyond_market.py`: comparação temporal mercado x modelo,
  sempre com `financial_capital_authorized: false`.

Agendamento no Windows: `scripts/windows/run_market_shadow_cycle.ps1`
encadeia ingest HLTV recente + coleta + import + settle + status (cada passo
tolerante a falha) e documenta o `Register-ScheduledTask` de exemplo no
próprio arquivo. É automação do operador, não parte do pacote instalável.

`CS_LABORATORY=1` pode substituir a flag em ambientes de laboratório
controlados. `cs-settle` é mantido apenas para compatibilidade: sempre informa
`CLOSED_BY_HUMAN_DECISION` e retorna código 2, sem executar settlement
financeiro — isso não muda com a reabertura shadow.

## Arquitetura

- `src/model.py`: Elo de série, combinatória BO1/BO3/BO5 e Platt;
- `src/model_maps.py`: extensão laboratorial de Elo por mapa;
- `src/services.py`: coleta, previsão, ingestão e fronteira de settlement;
- `src/scheduler.py`: integração com `predictor_ops`;
- `src/archival_collection.py`: arquivo append-only `COLLECTION_ONLY`;
- `scripts/`: replays e governança científica;
- `snapshots/`: previsões pré-evento, resultados e maturação encadeados por hash.

## Evidência histórica

Relatórios e tentativas anteriores foram preservados em
[`docs/evidence/historical/`](docs/evidence/historical/). Eles explicam a
evolução do projeto, mas seus números não substituem o replay canônico acima.
Os contratos modernos estão em [`docs/MODERNIZATION.md`](docs/MODERNIZATION.md)
e [`docs/VALIDATION.md`](docs/VALIDATION.md). A migração para core 2.2/ops 3.0
e sua prova de transparência estão em
[`docs/MIGRATION_OPS_V3.md`](docs/MIGRATION_OPS_V3.md).
