# PAST_ATTEMPT_LEDGER

| ID | Tentativa | Objetivo | Dados | Resultado | Evidência | Estado | Pode ser reutilizada? |
|---|---|---|---|---|---|---|---|
| CS-01 | HLTV `/results` via `curl_cffi` | histórico de séries | HLTV HTML | 17k+ séries, H1 prequential comprovada contra semente | `evidence/historical/RELATORIO_FASE1.md`, `cs.db` | concluída | sim, Sports DB |
| CS-02 | Parser de mapas HLTV | granularidade de mapas | páginas de partida HLTV | mapas de parte das séries; não é dataset de odds | `ingest_hltv_maps.py` | parcial | sim, somente esportivo |
| CS-03 | Identidade/aliases | evitar colisões de equipes | `teams_cs.json`, ratings | colisões reais de caixa corrigidas; ambiguidade rejeitada | `test_identity_hostile.py` | concluída | sim |
| CS-04 | Snapshots PRE_EVENT/MATURED | prova forward local | snapshots CS | vínculo SHA-256 e 4 pares válidos | `cs_snapshots.py` | concluída | sim, lifecycle local |
| CS-05 | Platt H2 prequential | calibrar Elo | stream HLTV | H2 materializado sem olhar o futuro | `backtest_calibracao.py`, trials | concluída | sim |
| CS-06 | Polymarket shadow | observar moneylines atuais | Gamma/CLOB público | quotes PRE_EVENT read-only; coleta pausada por decisão do operador | `polymarket_provider.py` | aguardando amostra | sim, prospectivo |
| CS-07 | Polymarket retrospectivo | comparar modelo e mercado | eventos fechados + histórico CLOB | 661 pares conservadores; mercado teve Brier menor, sem edge demonstrado | `backtest_market_historical.py` | resultado negativo/inconclusivo | sim, como baseline, não como gate forward |
| CS-08 | Kaggle/PandaScore histórico | fonte adicional de jogos | `historical_shadow.py`/PandaScore | não contém odds timestampadas; promoção financeira proibida | `ingest_pandascore_history.py` | rejeitada para Market DB | apenas pesquisa esportiva |
| CS-09 | Migração prospectiva Sports/Market | fechar quote→resultado→settlement | `cs.db` + shadow Polymarket | 17.324 séries classificadas PARTIAL; quotes legados sem event_id/competição rejeitados; novos quotes carregam ambos os campos | `migrate_prospective_market.py`, relatório runtime | em coleta | sim, somente coorte com mapping aceito |
| CS-10 | Reabertura shadow-only (2026-08-14) | completar a amostra mínima (50 liquidações/30 dias) que CS-06/07 não atingiram, sem tocar capital | Polymarket Gamma/CLOB + resultado oficial HLTV via `data/cs.db` | código restaurado de `docs/evidence/market_shadow/` para `data/market_shadow.db` (banco distinto de `data/market.db`); portão `assert_market_shadow_collection_open` separado do portão de capital `assert_beyond_market_open`, que permanece intocado; ainda sem amostra nova coletada nesta rodada | `docs/records/beyond_market_shadow_reopening.json`, `tests/test_market_shadow_governance.py` | reaberto, aguardando coleta | sim — é o mecanismo vigente para tentar fechar a amostra; CS-07 já mostrou mercado com Brier melhor que o modelo numa amostra retrospectiva de 661 pares, então a expectativa de edge prospectivo deve ser tratada com ceticismo |

Tentativas negativas não devem ser repetidas sem nova hipótese, nova fonte ou
alteração versionada do contrato.
