# HANDOFF.md — cs-predictor

> **Atualização 2026-08-01:** este handoff histórico foi superado pela
> modernização descrita em `docs/MODERNIZATION.md`. Vendor, imports de workspace,
> Task Scheduler e runtime de market shadow não fazem mais parte do pacote.
> `CLOSED_BY_HUMAN_DECISION` e a evidência histórica foram preservados.

> ## ENCERRAMENTO PROSPECTIVO BEYOND MARKET (2026-07-23)
>
> Decisao humana: `CLOSED_BY_HUMAN_DECISION`; status operacional: `NO_GO`.
> A coorte foi encerrada antes da amostra minima; nao foi aprovada nem
> refutada. O job `cs-market-shadow` foi removido do Scheduler. O registro versionado
> com hashes e contadores finais esta em `docs/records/beyond_market_closure.json`.
> Coleta, atualizacao, status, settlement e avaliacao sao bloqueados; reabertura
> exige nova decisao humana auditavel.

> ## READINESS FINAL — COLLECTION_ONLY (2026-07-25)
>
> **`PRODUCTION_READY_WITH_EXTERNAL_BLOCKER`**. O codigo, vendor, scheduler,
> provenance e runtime externo foram validados. `cs-archival-collection` usa
> o `operational_runner` canonico, com lock, timeout, heartbeat e event log em
> `%LOCALAPPDATA%\predictor-tools\runtime\cs-predictor\cs-archival-collection`.
> A dependencia restante e o exportador esportivo oficial que materializa
> `data/collection_only/upstream_events.json`: arquivo ausente ou corrompido
> emite `SOURCE_UNAVAILABLE`; JSON valido vazio emite `NO_UPSTREAM_EVENTS`.
> Nenhuma ausencia e tratada como coleta saudavel. Beyond Market permanece
> `CLOSED_BY_HUMAN_DECISION`, `cs-market-shadow` permanece removido e nenhuma
> hipotese, trial ou gate foi reaberto.

> ## SPORTS DB / MARKET DB (2026-07-21)
>
> A separação foi formalizada sem alterar o lifecycle criptográfico local:
> `cs.db` permanece Sports DB, `market.db` guarda apenas cotações com contrato
> econômico, e o mapping canônico versionado rejeita ambiguidade, mapa/série e
> formatos incompatíveis. O Beyond Market usa corte temporal train/test e o
> resultado máximo é `GATE_PASSED_FOR_PROSPECTIVE_SHADOW`; `real=True` continua
> bloqueado incondicionalmente. A retrospectiva conservadora de 661 pares não
> provou edge contra o mercado. Ver `docs/SPORTS_MARKET_CONTRACTS.md` e
> `docs/PAST_ATTEMPT_LEDGER.md`.

> ## CADEIA PROSPECTIVA (2026-07-22)
>
> Migração executada com backup: 17.324 séries materializadas como `PARTIAL`
> pois HLTV histórico não informa roster nem disponibilidade de resultado com
> precisão suficiente. O status não usa mais horário passado como maturidade.
> A coorte atual tem mappings aceitos somente quando a quote possui event ID e
> competição; linhas legadas são rejeitadas para settlement, preservadas no
> ledger. Capital real continua impossibilitado.

> ## ESTADO REVALIDADO (2026-07-20)
>
> Suíte completa: **110 verdes**; CI local: **3/3**. Vendor do
> `predictor_core` sincronizado em `feeac2a` com a versão
> `1.3.2-ga-20260720`. O HEAD local `28a7d33` está um commit à frente de
> `origin/main` (`feeac2a`); nenhum push foi feito nesta rodada.

> ## 🔒 AUDITORIA DE IDENTIDADE (2026-07-19)
>
> **Bug real corrigido**: `ratings.json` contém 3 pares de organizações
> DISTINTAS cujos nomes diferem só pela caixa (`LEO`/`Leo` — 4 vs 185
> partidas na base —, `CHAOS`/`Chaos`, `WINNERS`/`Winners`).
> `EloModel._elo` resolvia case-insensitive devolvendo o PRIMEIRO hit do
> dict: `_elo("Leo")` retornava silenciosamente a entidade `LEO`. Agora:
> caixa exata resolve; casamento case-insensitive só quando único;
> ambíguo rejeita com a lista das entidades. `cs_snapshots._resolve`
> (que já rejeitava o ambíguo) ganhou a mesma preferência por caixa
> exata (`RATINGS_EXACT`). O pipeline que materializa os ratings não estava
> exposto: o replay (`backtest_walkforward.py`) usa nomes exatos do banco,
> sem passar por `_elo`; o bug estava no lookup de serving/snapshot.
> A continuação de 2026-07-20 aplicou o mesmo contrato ao Top 30: Unicode
> NFC + `casefold`, caixa exata primeiro e rejeição de colisões de nomes ou
> aliases. Testes hostis em `tests/test_identity_hostile.py` e
> `tests/test_config.py`; suíte ampliada e verde,
> CI 3/3. Verificado também nesta rodada: 0 `match_id` duplicado em
> 17.138 séries à época (os 7 "duplicados exatos" por data/evento/placar são
> rematches reais com match_id HLTV distintos); 4 snapshots reais de
> 2026 verificam. Em 2026-07-20, os três resultados pendentes foram conferidos
> no HLTV e maturados: estado atual = 4 `VALID_FORWARD`, 0 pendentes.
> A ingestão incremental foi atualizada para 17.320 séries e os três jogos
> receberam mapas detalhados. Backup/restore de `cs.db`, ratings e snapshots
> foi implementado com manifesto SHA-256 e `integrity_check`; restore real
> verificado em raiz temporária com 17.320 séries.
> A Fase 1b deixou de estar bloqueada por descoberta de fonte: integração
> Polymarket Gamma/CLOB read-only adicionada com identidade exata, formato BO,
> enforcement PRE_EVENT e dedupe concorrente. Continua sem GO financeiro até
> existir amostra prospectiva madura; passagem do tempo não é bug de código.
> Primeira coleta real: 15 cotações PRE_EVENT em 20/07. Trials H3
> (calibração assimétrica) e H4 (decay por inatividade) pré-registrados como
> forward-only a partir de 21/07, mínimo 1.000 previsões e 90 dias; não foram
> executados e não alteram o serving.

> ## ADENDO ECOSSISTEMA (2026-07-18)
>
> Vendor de `predictor_core` íntegro contra seu `CORE_MANIFEST.json`,
> sincronizado em `7627c03`. Suíte: 100% verde. Bug real corrigido numa rodada anterior:
> alias "NAVI" ausente para Natus Vincere (`a478829`). Auditoria hostil
> adicional 2026-07-18 (`resolve_team` contra 13 apelidos/abreviações reais
> e colisões de substring adversariais): nenhum bug novo, zero
> falso-positivo. Lifecycle `PRE_EVENT`/`MATURED` deste projeto tem vínculo
> criptográfico (hash) entre snapshots — mais rigoroso que F1/LoL, por isso
> não foi promovido a contrato comum do core (`PENDENCIAS_ABERTAS.md`
> INC-1). Sem incidente de segurança próprio. Documento canônico do
> ecossistema: `../ECOSYSTEM_HANDOFF.md`.
>
> ## 🔧 REVISÃO GERAL (2026-07-17)
>
> Correções da revisão de código (suíte 83 verdes, CI 3 barreiras OK):
> - **Semente do Elo por mapa corrigida**: time desconhecido herdava o rating
>   do PRIMEIRO time de ratings.json; agora usa a semente neutra
>   (`backtest.default_seed_elo`, 1400).
> - **Guard de empate/BO2**: `infer_format` rejeita placar sem vencedor
>   (1-1/12-12) — `update_ratings` não pune mais o time A como derrotado em
>   dado sujo. Base auditada: 1 empate 12-12 em 17.138 séries; backtest e
>   fluxo semanal já pulavam empates, ratings.json de produção NÃO foi
>   afetado.
> - **score_probs agora consistente com o Platt**: distribuição reescalada
>   (forma condicional ao vencedor preservada) para que handicap e mapas
>   esperados contem a mesma história que a probabilidade servida; crua
>   preservada em `score_probs_raw`. Helpers únicos em model.py
>   (`series_win_prob`, `expected_maps`, `cover_probability`,
>   `calibrate_score_probs`) — duplicação removida de predict/model_maps/
>   model_maps_shrunk.
> - **Push em handicap inteiro** exposto (`p_push`; cobrir/não-cobrir/push
>   somam 1). **`--dry-run`** no CLI (consulta sem poluir o ledger).
>   **Aliases explícitos** opcionais em teams_cs.json (`"aliases": [...]`),
>   precedência sobre substring. Guard `_event_has_result` com janela ±1 dia
>   (série que vira meia-noite UTC).
>
> Pendências deliberadas (exigem trial no registro, NÃO rodadas): calibração
> assimétrica nas pontas (isotônica/bins — Platt simétrico não corrige a
> cauda 0,07→0,19) e decay de Elo por inatividade no modelo de série
> (roster changes) — candidatas a tentativa N+2.

> ## 🟢 FASE 1 CONCLUÍDA — H1 COMPROVADA (2026-07-11)
>
> **O 403 do HLTV caiu**: curl_cffi + impersonate Chrome responde 200 com
> conteúdo real (mesma técnica do Sofascore). `hltv_provider.py` virou
> implementação real (parser de /results por regex, delay 2s); **17.100
> séries** coletadas (2024-12→2026-07, todas as tiers, 1.008+ times).
>
> Backtest prequential (Elo por mapa, P(série) pela combinatória do formato,
> K 32/40/48, burn-in 90d, n medido 10.671) com governança completa.
> **H1-CS COMPROVADA**: Brier 0,4573 vs semente 0,4956 (≈coin-flip fora do
> Top 30 — a prova é de APRENDIZADO), acerto 62,6%, DM p<1e-4.
>
> **Achado central: sobreconfiança nas pontas** (prev 0,93 → real 0,88;
> prev 0,07 → real 0,19) — zebra de CS vence mais que a logística /400 diz
> (variância de veto/mapa + roster changes). Recalibrar escala/K = tentativa
> N+1 no registro; NÃO foi rodada. Serving materializado: `ratings.json`
> (Elo vivido de 1.227 times). Relatório: `docs/RELATORIO_FASE1.md`.
> Fase 1b (odds ao vivo em sombra) depende de fonte de odds corrente.

> ## 🔫 CRIAÇÃO (2026-07-10)
>
> **Projeto criado. Modelo Elo base implementado. Backtest e operação real
> pendentes.**
>
> Sexto consumidor do predictor_core (v1.1.0, vendor via `sync_core --write`).
> Python 3.13 em `.venv` (pandas, numpy, scipy, pydantic, httpx, pytest).
>
> Decisões da Fase 0:
> - **Elo por MAPA + combinatória de série**: P(mapa) pela logística clássica;
>   BO1/BO3/BO5, total de mapas e handicap ±1.5 saem da distribuição exata do
>   placar com mapas i.i.d. (simplificação declarada — mapas específicos,
>   CT/TR e forma recente são Fase 1+). K por formato: 32/40/48; formato
>   inferido do placar no `update_ratings`; Elo soma-zero, persistido em
>   `data/ratings.json` (gitignored — evolução é dado de runtime).
> - **Semente do Elo = ranking HLTV real de 2026-07-06** (Falcons #1 …
>   Lynn Vision #30), linear 1600→1300 conforme a regra do prompt. Fonte:
>   espelho pley.gg — **hltv.org responde 403** a cliente HTTP simples
>   (Cloudflare), decisão da via de coleta fica para a Fase 1 (curl_cffi/
>   impersonate como no sofascore, API de terceiros ou export manual).
>   Time #17 "magic" com region=unknown (pós-cutoff de conhecimento).
> - **Governança desde o dia zero**: PredictionPoint (matures_at = início +
>   1h30/3h/5h por formato), telemetria domínio `cs`, log append-only com
>   override por env (CI não polui produção — lição da Copa).
> - CI 3 barreiras + testes de integridade do vendor/higiene de repo copiados
>   do brasileirao-predictor; `.gitattributes` eol=lf (clone com autocrlf
>   quebraria os hashes do CORE_MANIFEST).
> - Suíte: **24 verdes**.
>
> Próximo passo (Fase 1, prompt separado): dados históricos de partidas
> Tier 1 (HLTV), recalibração dos ratings com resultados reais, backtest
> walk-forward e o fluxo de governança da plataforma (harness → TrialRegistry
> → GO/NO-GO) antes de qualquer aposta.

## O que é o projeto

Laboratório de previsão de partidas de CS2 (vencedor, handicap, total de
mapas) — Fase 0. Roda 100% local. Idioma do projeto: português. NÃO é
ferramenta de investimento; nenhum edge foi demonstrado.

Máquina do Leo: Windows, `C:\Claude-projetos\Claude\cs-predictor`,
venv `.venv` (Python 3.13.14), atrás de proxy corporativo Volvo.
