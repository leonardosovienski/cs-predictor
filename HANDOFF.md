# HANDOFF.md — cs-predictor

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
