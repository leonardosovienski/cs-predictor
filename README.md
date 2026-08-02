# cs-predictor

## Runtime moderno

O projeto é um pacote Python 3.13 instalado com `uv`; Python 3.14 permanece
experimental. `predictor-core 2.1.0` e `predictor-ops 2.0.1` são consumidos
como wheels em `wheelhouse/`, sem vendor, `PYTHONPATH`, `sys.path` ou checkout
irmão.

```bash
uv sync --frozen --extra dev
uv run pytest
uv run cs-predictor health
uv run cs-collect --input data/fixtures/upstream_events.example.json
uv run cs-scheduler --validate
uv run cs-scheduler
uv build
```

O contrato arquivístico formal está em
`schemas/upstream-event-v1.schema.json`; detalhes de transportes, isolamento
Sports DB/Market DB, scheduler portátil, migração e incompatibilidade dos
contratos comuns estão em `docs/MODERNIZATION.md`.

> **Estado operacional canonico (2026-07-29): COLLECTION_ONLY.** Beyond
> Market esta permanentemente fechado; `cs-market-shadow`, coleta de odds,
> importacao, settlement e avaliacao de mercado nao sao operacoes permitidas.
> O unico job permitido e `cs-archival-collection`.

> **Estado cientifico:** os numeros historicos H1 abaixo nao sao canonicos
> enquanto o replay prequential nao for reexecutado com a atualizacao Elo por
> vencedor de serie corrigida. Nao use os artefatos anteriores para decisao.

> **Status: Fase 1 CONCLUÍDA (2026-07-11).** HLTV destravado (curl_cffi
> impersonate); 17.100 séries coletadas e backtest prequential rodado:
> **H1 (Elo vencedor da série) COMPROVADA** — Brier 0,4573 vs semente
> 0,4956, acerto 62,6%, DM p<1e-4 — com **sobreconfiança nas pontas**
> documentada (zebra vence mais que o /400 diz). Elo vivido de 1.227 times
> em `data/ratings.json`. **Sem odds, sem apostas** (Fase 1b exigiria fonte
> de odds). Relatório: `docs/RELATORIO_FASE1.md`. Não é ferramenta de
> investimento.

Laboratório de previsão de **partidas de Counter-Strike 2** (vencedor da
série, handicap e total de mapas), sexto consumidor do ecossistema
`predictor_core`. 100% local (Python 3.13 + arquivos), sem cloud.

## Por que Elo (e não Poisson)

CS2 é jogo de rounds (first to 13 no MR12, com overtime), mas modelar round a
round exige dado que o esqueleto não tem. O Elo captura força relativa a
partir do histórico:

```
P(A vence um MAPA) = 1 / (1 + 10^((elo_B − elo_A)/400))
```

O rating é interpretado **por mapa**; vencedor da série (BO1/BO3/BO5), total
esperado de mapas e handicap (±1.5) saem da combinatória exata da série com
mapas i.i.d. — simplificação declarada da Fase 0. Extensões da Fase 1+:
pontos fortes por mapa, fator CT/TR, forma recente, economia de rounds.

Elo inicial semeado do **ranking HLTV Top 30 de 2026-07-06** (linear:
#1=1600 → #30=1300, regra do prompt de criação). K-factor por formato:
BO1=32, BO3=40, BO5=48. `update_ratings` persiste a evolução em
`data/ratings.json` (soma zero conservada).

## Uso

```bash
.venv\Scripts\python.exe -m src.predict Vitality MOUZ --format bo3
.venv\Scripts\python.exe -m src.predict Falcons Spirit --handicap -1.5 --json
.venv\Scripts\python.exe -m src.predict FURIA paiN --format bo5

# Testes e CI
.venv\Scripts\python.exe -m pytest tests/ -v
.venv\Scripts\python.exe scripts/ci_check.py
```

Toda previsão é carimbada com `PredictionPoint` do core (matures_at = início
+ duração típica do formato: 1h30/3h/5h), registrada em
`data/predictions.jsonl` (append-only, override por env) e emitida na
telemetria (domínio `cs`).

## Estrutura

```
config.yaml                 # game, formato default, K base, banca
src/
  config.py                 # scientific config and team identity
  settings.py               # typed operational settings
  plugin.py                 # canonical predictor.plugins entry point
  services.py               # prediction/ingestion/settlement/archival services
  model.py                  # EloModel (predict_match/predict_handicap/update_ratings)
  predict.py                # CLI de serving + PredictionPoint + telemetria
  data/hltv_provider.py     # stub HLTV (403 a cliente simples; Fase 1 decide a via)
data/teams_cs.json          # HLTV Top 30 (2026-07-06) com Elo semente
scripts/ci_check.py         # 3 barreiras: pytest, .ps1 ASCII, parse+smoke
tests/                      # suíte completa (modelo, serving, backup, core, identidade hostil)
wheelhouse/                 # immutable predictor-core/predictor-ops wheels
```

### Backup e restauração

```powershell
python -m src.backup_restore create --output backups/cs-AAAAMMDD
python -m src.backup_restore verify --backup backups/cs-AAAAMMDD
python -m src.backup_restore restore --backup backups/cs-AAAAMMDD --destination C:\restore\cs
```

O backup usa a API consistente do SQLite, inclui ratings, calibracao, ratings
por mapa, snapshots, configuracao, metadados do core e artefatos Market
preservados. Ele grava hashes SHA-256 e a restauracao verifica novamente os
bytes copiados, mantendo o manifesto no destino. A restauracao exige uma raiz
nova e nunca sobrescreve producao.

### Mercado shadow read-only

> **Encerrado por decisao humana em 2026-07-23.** A coorte prospectiva Beyond
> Market esta `CLOSED_BY_HUMAN_DECISION`, antes de atingir 50 liquidacoes e 30
> dias. Nao foi aprovada nem refutada. Coleta, status operacional, liquidacao e
> avaliacao falham fechados; a operacao com dinheiro real permanece `NO_GO`.
> Evidencia: `docs/records/beyond_market_closure.json`.

O job legado `cs-market-shadow` foi removido do Scheduler. A unica automacao de
coleta permitida e `cs-archival-collection`, instalada pelo mecanismo
canonico `powershell -File ..\tools\install_collection_only_tasks.ps1`; ela
usa `operational_runner`, runtime externo e nunca consulta mercados/apostas.

```powershell
# Unica automacao permitida:
sudo systemctl enable --now cs-archival-collection.timer
```

Esses comandos sao historicos e nao devem ser executados. O instalador
O instalador histórico, preservado sob `docs/evidence/market_shadow`, falha para impedir que
`cs-market-shadow` seja recriado; use somente `cs-archival-collection`.

O coletor aceita apenas um ID Gamma explícito, exige moneyline com identidade
exata e instante PRE_EVENT, consulta somente Gamma/CLOB públicos e grava em
`data/market_shadow.jsonl`. Não existe caminho de ordem ou trading no projeto.

Nao instale nem execute qualquer coletor de mercado. O instalador legado
O instalador legado aborta deliberadamente; os entrypoints de
Polymarket permanecem apenas como evidencia historica bloqueada.

O backtest auxiliar abaixo usa mercados encerrados e o histórico oficial de
preços do CLOB. Ele aceita somente casamento exato e único com o HLTV, reconstrói
o Elo/Platt prequential e recua o corte pela duração máxima da série para impedir
preço in-play. Por governança, nunca incrementa o gate prospectivo:

```powershell
python scripts/backtest_market_historical.py --target 1000
```

### Contrato Sports DB x Market DB

Partidas e preços são bases distintas. `data/cs.db` mede o modelo esportivo;
`data/market.db` só aceita moneyline de série com timestamp, bookmaker,
proveniência e mapeamento canônico aprovado. O relatório Beyond Market compara
mercado, modelo e combinação fora da amostra. Nenhum resultado libera capital:
o máximo é `GATE_PASSED_FOR_PROSPECTIVE_SHADOW`. Contratos e limites estão em
[`docs/SPORTS_MARKET_CONTRACTS.md`](docs/SPORTS_MARKET_CONTRACTS.md); o histórico
de tentativas está em [`docs/PAST_ATTEMPT_LEDGER.md`](docs/PAST_ATTEMPT_LEDGER.md).

Para materializar a coorte prospectiva com backup e relatório:

```powershell
python scripts/migrate_prospective_market.py --backup-dir backups/sports-market-AAAAMMDD
# removido do runtime; evidência em docs/evidence/market_shadow/
```

`EVENT_TIME_PASSED` não significa resultado maturado: sem mapping aceito,
resultado oficial validado e closing pré-evento, a série fica fora do Beyond Market.

## Roadmap

| Fase | Escopo | Status |
|---|---|---|
| 0 | Esqueleto: estrutura, vendor, Elo base, serving, CI | ✅ |
| 1 | Dados históricos Tier 1 (HLTV) + backtest walk-forward | ✅ H1 comprovada |
| 2 | Governança: harness + TrialRegistry + calibração Platt H2 | ✅ H2 comprovada (Platt calibrado, `data/calibration_platt.json`) |
| 3 | Operação: odds, bet_log, settle | ⏳ (só após GO financeiro — não construído) |
