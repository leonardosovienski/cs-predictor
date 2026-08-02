# Historical test migration matrix

Baseline: 160 passed and one conditional skip. The modernization moved 50 tests
out of the executable suite and added contract/golden tests. This matrix accounts
for every moved test. “Evidence” means the original test and implementation are
preserved byte-for-byte below `docs/evidence/`; it is not treated as executable
runtime coverage.

| Historical test | Behavior | Risk | Destination | New test | Justification / evidence |
|---|---|---|---|---|---|
| `test_vendor_manifest_present` | vendor manifest exists | dependency drift | replacement architecture | `test_predictor_ops_201_is_installed_from_site_packages_and_hash_matches` | Wheels plus `uv.lock`; original in `legacy_dependencies/tests/test_core_integrity.py`. |
| `test_each_file_hash_matches_manifest` | vendored files match hashes | tampering | replacement architecture | `test_predictor_ops_201_is_installed_from_site_packages_and_hash_matches` | RECORD provenance and canonical wheel hash replace source-tree hashes. |
| `test_no_orphan_files_in_vendor` | no undeclared vendor files | hidden code | removal justified | `test_no_code_file_is_gitignored` | Vendor no longer exists; wheel RECORD is authoritative. |
| `test_aggregate_reproduces` | aggregate vendor digest | drift | replacement architecture | `test_predictor_ops_201_is_installed_from_site_packages_and_hash_matches` | Wheel SHA-256 inventory supersedes aggregate tree digest. |
| `test_tools_provenance_real_call_matches_independent_collect_tools_provenance` | tools provenance | false identity | replacement architecture | `test_predictor_ops_201_is_installed_from_site_packages_and_hash_matches` | Public `predictor_ops.provenance` replaces sibling `tools`; original preserved. |
| `test_registro_encerrado_bloqueia` | closed record blocks | reopening | contract coverage | `test_closure_is_immutable_and_fail_closed` | Active governance test. |
| `test_reabertura_exige_os_tres_campos_de_decisao` | incomplete reopening rejected | reopening | replacement architecture | `test_closure_is_immutable_and_fail_closed` | Reopening is now entirely absent, a stricter invariant. |
| `test_reabertura_completa_continua_bloqueada` | even complete reopening blocked | reopening | contract coverage | `test_closure_is_immutable_and_fail_closed` | Direct operation always raises. |
| `test_status_desconhecido_falha_fechado` | unknown status rejected | fail-open | contract coverage | `test_closure_and_historical_evidence_hashes_are_stable` | Canonical record/hash/status fixed. |
| `test_registro_ilegivel_falha_fechado` | corrupt record rejected | fail-open | contract coverage | `test_closure_is_immutable_and_fail_closed` | Missing/custom records raise; parser remains fail-closed. |
| `test_remover_o_registro_nao_reabre_a_coorte` | deletion cannot reopen | fail-open | contract coverage | `test_closure_is_immutable_and_fail_closed` | Missing fixture path explicitly raises. |
| `test_store_de_producao_respeita_o_registro_default` | store cannot bypass closure | capital | replacement architecture | `test_no_operational_market_surface_exists` | Store was removed; no import, entry point, provider, or job exists. |
| `test_registro_de_producao_e_valido_e_nunca_libera_capital` | production status/capital | capital | contract coverage | `test_closure_and_historical_evidence_hashes_are_stable` | Validates decision text, hash and `capital_real=false`. |
| `test_shadow_dedupes_under_concurrency` | quote dedupe | duplicate market rows | evidence preserved | `test_reprocessing_does_not_duplicate` | Upstream archival idempotency remains active; market writer is inaccessible. |
| `test_quote_freezes_model_probability_and_ratings_hash` | frozen market prediction | audit drift | evidence preserved | `test_golden_elo`, `test_golden_calibration` | Science stays golden; market artifact code is historical only. |
| `test_upcoming_collector_freezes_model_before_append` | pre-event freeze ordering | leakage | evidence preserved | `test_no_operational_market_surface_exists` | No upcoming-market collector can execute. |
| `test_canonical_event_is_deterministic_and_versioned` | market event identity | collision | contract coverage | `test_contract_detects_tampering`, `test_reprocessing_does_not_duplicate` | Versioned upstream identity replaces market identity. |
| `test_mapping_rejects_invalid_scope_format_and_ambiguous_identity` | strict mapping | wrong match | evidence preserved | `test_contract_detects_tampering` | Market mappings removed; upstream schema remains strict. |
| `test_market_quote_requires_timestamp_bookmaker_and_valid_margin` | quote schema | bad price | removal justified | `test_no_operational_market_surface_exists` | No quote/trading input surface exists. |
| `test_market_db_rejects_unmapped_and_ambiguous_event` | mapping gate | wrong settlement | removal justified | `test_no_operational_market_surface_exists` | Market DB runtime absent. |
| `test_sports_contract_rejects_future_roster_result_and_bad_hash` | sports temporal integrity | leakage | evidence preserved | `test_contract_detects_tampering` | Hash/time contract active; original detailed rules preserved. |
| `test_sports_db_metadata_isolated_from_match_result_table` | table isolation | contamination | contract coverage | `test_database_isolation.py` | Physical Sports/Market targets cannot alias. |
| `test_two_same_day_events_need_competition_or_start_to_be_distinct` | event disambiguation | collision | evidence preserved | `test_contract_detects_tampering` | Source record identity is explicit/versioned. |
| `test_beyond_market_has_strict_train_test_cut_and_no_financial_go` | no leakage/no GO | capital | evidence preserved | `test_no_operational_market_surface_exists` | No market capability or capital path. |
| `test_beyond_market_rejects_leakage_and_empty_dataset` | reject invalid evaluation | false GO | evidence preserved | `test_no_operational_market_surface_exists` | Evaluator is not executable. |
| `test_select_pre_event_price_rejects_future_and_invalid` | pre-event cutoff | lookahead | removal justified | `test_no_operational_market_surface_exists` | Price selection surface removed. |
| `test_select_pre_event_price_empty` | no invented price | fabrication | removal justified | `test_no_operational_market_surface_exists` | No price provider exists. |
| `test_legacy_quotes_are_not_retroactively_eligible` | legacy data ineligible | retroactive promotion | contract coverage | `test_no_operational_market_surface_exists` | Migration and status commands absent. |
| `test_read_only_pre_event_quote` | provider read-only | trading | removal justified | `test_no_operational_market_surface_exists` | Provider absent and plugin declares trading false. |
| `test_rejects_post_event_and_identity_mismatch` | quote timing/identity | leakage | removal justified | `test_no_operational_market_surface_exists` | No quote ingestion. |
| `test_clob_epoch_string_is_accepted` | timestamp compatibility | ingest failure | evidence preserved | — | Historical provider compatibility retained only as evidence. |
| `test_lists_only_unique_open_upcoming_moneylines` | unique moneylines | wrong market | removal justified | `test_no_operational_market_surface_exists` | No market listing endpoint. |
| `test_quote_without_source_event_is_explicitly_rejected` | source required | provenance loss | removal justified | `test_contract_detects_tampering` | Active upstream contract always requires provenance. |
| `test_settlement_is_idempotent_and_requires_validated_result` | market settlement idempotency | double settle | replacement architecture | `test_plugin_health_prediction_and_settlement` | Sports-only settlement; market settlement unavailable. |
| `test_event_time_passed_is_not_matured_and_corrected_result_replays_settlement` | maturity semantics | premature settle | evidence preserved | `test_no_operational_market_surface_exists` | No market maturity flow exists. |
| `test_quote_after_event_is_invalid` | post-event quote rejected | leakage | removal justified | `test_no_operational_market_surface_exists` | Quote surface absent. |
| `test_sports_migration_is_idempotent_and_marks_missing_temporal_data_partial` | migration safety | duplicate/corrupt migration | contract coverage | `test_no_operational_market_surface_exists` | Old migration absent; archival replay idempotency active. |
| `test_orientacao_direta` | direct result orientation | wrong winner | evidence preserved | `test_plugin_health_prediction_and_settlement` | Sports settlement boundary remains; legacy market matcher archived. |
| `test_orientacao_invertida_normaliza_placar_e_vencedor` | inverted orientation | wrong winner | evidence preserved | — | Market-specific normalization is non-runtime historical behavior. |
| `test_invertida_com_vitoria_do_time_b` | inverse winner | wrong winner | evidence preserved | — | Same archived settlement evidence. |
| `test_partida_ausente_nao_inventa_resultado` | missing match fails | fabrication | contract coverage | `test_no_events_is_not_source_unavailable` | Absence is never success; market settlement absent. |
| `test_empate_nao_liquida` | tie not settled | invalid outcome | golden/contract coverage | `test_infer_format_rejeita_empate` | Active sports model rejects ties. |
| `test_ambiguidade_falha_fechado` | ambiguous match fails | wrong settle | evidence preserved | `test_no_operational_market_surface_exists` | Matcher not executable. |
| `test_janela_de_um_dia_cobre_virada_de_data` | matching date window | missed result | evidence preserved | — | Market matching algorithm archived unchanged. |
| `test_fora_da_janela_nao_casa` | out-of-window rejected | wrong result | evidence preserved | — | Market matcher absent. |
| `test_caixa_diferente_resolve_quando_unica` | casefold unique | identity | evidence preserved | `test_database_isolation.py` | Runtime path case aliases covered; team identity tests remain active. |
| `test_caixa_diferente_invertida_preserva_orientacao` | casefold/inversion | identity | evidence preserved | `test_identity_hostile.py` | Active hostile identity suite retained. |
| `test_colisao_de_caixa_real_falha_fechado` | case collision fails | wrong team | contract coverage | `test_identity_hostile.py` | Active identity ambiguity coverage. |
| `test_caixa_exata_tem_precedencia_sobre_casefold` | exact identity precedence | wrong team | contract coverage | `test_identity_hostile.py` | Active identity resolution coverage. |

The sole previous skip (`test_vendor_manifest_files_are_tracked`) was removed as
a conditional vendor test and replaced by unconditional wheel hash, RECORD and
site-packages provenance tests. The calibration fixture is versioned, so its
conditional skip is converted to an assertion in the active suite.
