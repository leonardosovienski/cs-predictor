# HANDOFF.md — cs-predictor

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
