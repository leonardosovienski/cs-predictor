import sqlite3
from datetime import UTC, datetime

import pytest

from src.market_db import ContractError
from src.prospective_market import ProspectiveStore, migrate_sports_db
from src.shadow_economics import StrategySpec, shadow_decision


def _quote(**updates):
    row = {"quote_id": "q1", "market_id": "m1", "team_a": "A", "team_b": "B", "format": "bo3",
           "scheduled_at": "2030-01-02T12:00:00+00:00", "observed_at": "2030-01-01T12:00:00+00:00",
           "model_probability_a": .6, "model_probability_b": .4, "ratings_sha256": "a" * 64,
           "probability_a": .55, "probability_b": .45, "decimal_a": 1.8, "decimal_b": 2.2,
           "source": "polymarket-clob", "source_kind": "prediction_market", "source_event_id": "e1",
           "competition_name": "Cup"}
    row.update(updates); return row


def test_quote_without_source_event_is_explicitly_rejected(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    out = store.import_quotes(conn, [_quote(source_event_id=None, competition_name=None)], batch_id="b")
    assert out["rejected"] == 1
    assert store.status(conn, now=datetime(2030, 1, 3, tzinfo=UTC))["matured_matches"] == 0


def test_settlement_is_idempotent_and_requires_validated_result(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect(); store.import_quotes(conn, [_quote()], batch_id="b")
    key = "polymarket-clob:m1"
    assert store.settle(conn, event_key=key) == "RESULT_PENDING"
    store.record_result(conn, event_key=key, winner="A", score={"team_a": 2, "team_b": 0}, result_source="fixture", result_available_at="2030-01-02T13:00:00+00:00")
    assert store.settle(conn, event_key=key) == "MATURED"
    assert store.settle(conn, event_key=key) == "MATURED"
    assert conn.execute("SELECT count(*) FROM prospective_settlements").fetchone()[0] == 1


def test_event_time_passed_is_not_matured_and_corrected_result_replays_settlement(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect(); store.import_quotes(conn, [_quote()], batch_id="b")
    key = "polymarket-clob:m1"
    state = store.status(conn, now=datetime(2030, 1, 3, tzinfo=UTC))
    assert state["states"]["EVENT_TIME_PASSED"] == 1 and state["matured_matches"] == 0
    store.record_result(conn, event_key=key, winner="A", score={"team_a": 2, "team_b": 0}, result_source="fixture", result_available_at="2030-01-02T13:00:00+00:00")
    store.settle(conn, event_key=key)
    store.record_result(conn, event_key=key, winner="B", score={"team_a": 1, "team_b": 2}, result_source="corrected-fixture", result_available_at="2030-01-02T14:00:00+00:00")
    store.settle(conn, event_key=key)
    assert conn.execute("SELECT outcome_a FROM prospective_settlements WHERE event_key=?", (key,)).fetchone() == (0,)


def test_quote_after_event_is_invalid(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    out = store.import_quotes(conn, [_quote(observed_at="2030-01-02T12:00:00+00:00")], batch_id="b")
    assert out["invalid"] == 1


def test_sports_migration_is_idempotent_and_marks_missing_temporal_data_partial():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE matches(match_id INTEGER PRIMARY KEY,date TEXT,ts INTEGER,team_a TEXT,team_b TEXT,score_a INTEGER,score_b INTEGER,format TEXT,event TEXT)")
    conn.execute("INSERT INTO matches VALUES(1,'2030-01-01',1893456000,'A','B',2,0,'bo3','Cup')")
    first = migrate_sports_db(conn, migration_id="m1"); second = migrate_sports_db(conn, migration_id="m1")
    assert first["partial"] == 1 and second["status"] == "ALREADY_APPLIED"
    assert conn.execute("SELECT migration_status FROM sports_series_contract").fetchone() == ("PARTIAL",)


def test_liquidity_is_persisted_from_the_quote_row(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    store.import_quotes(conn, [_quote(liquidity=1234.5)], batch_id="b")
    assert conn.execute("SELECT liquidity FROM prospective_quotes WHERE quote_id='q1'").fetchone() == (1234.5,)


def test_liquidity_is_null_when_absent_from_the_quote_row(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    store.import_quotes(conn, [_quote()], batch_id="b")
    assert conn.execute("SELECT liquidity FROM prospective_quotes WHERE quote_id='q1'").fetchone() == (None,)


def test_existing_shadow_db_without_liquidity_column_is_migrated_in_place(tmp_path):
    """Bancos shadow criados antes desta coluna existir precisam continuar
    funcionando sem perder as cotações já coletadas pelo operador."""
    path = tmp_path / "market.db"
    legacy = sqlite3.connect(path)
    legacy.execute("""CREATE TABLE prospective_quotes (
        quote_id TEXT PRIMARY KEY, event_key TEXT, provider TEXT, source_market_id TEXT,
        captured_at TEXT, bookmaker TEXT, market_type TEXT, market_scope TEXT,
        selection_a_odds REAL, selection_b_odds REAL, probability_a REAL, probability_b REAL,
        max_spread REAL, model_probability_a REAL, model_probability_b REAL, ratings_sha256 TEXT,
        ingestion_batch_id TEXT, provenance_hash TEXT, data_quality_status TEXT)""")
    legacy.execute("INSERT INTO prospective_quotes VALUES('old','k','p','m','2030-01-01T00:00:00+00:00',"
                   "'b','moneyline','series',1.8,2.2,.55,.45,.02,.6,.4,'a','batch','h'*8,'ELIGIBLE')")
    legacy.commit(); legacy.close()

    store = ProspectiveStore(path); conn = store.connect()
    assert conn.execute("SELECT quote_id, liquidity FROM prospective_quotes WHERE quote_id='old'").fetchone() == ("old", None)
    store.import_quotes(conn, [_quote(liquidity=500.0)], batch_id="b2")
    assert conn.execute("SELECT liquidity FROM prospective_quotes WHERE quote_id='q1'").fetchone() == (500.0,)


def test_status_is_explicit_that_clv_is_not_available(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    status = store.status(conn, now=datetime(2030, 1, 1, tzinfo=UTC))
    assert status["clv_available"] is False
    assert "não é closing line externa" in status["market_reference_definition"]


def test_pre_post_veto_contract_requires_real_timestamps_and_external_closing(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    order_books = {"A": {"token_id": "token-a", "published_at": "2030-01-01T10:02:00+00:00",
                           "book_hash": "hash-a", "tick_size": .01, "min_order_size": 5,
                           "executable_depth_available": True,
                           "bids": [{"price": .54, "size": 1000}],
                           "asks": [{"price": .55, "size": 1000}]}}
    store.import_quotes(conn, [
        _quote(quote_id="pre", observed_at="2030-01-01T09:00:00+00:00"),
        _quote(quote_id="post", observed_at="2030-01-01T10:02:00+00:00",
               order_books=order_books),
    ], batch_id="b")
    key = "polymarket-clob:m1"
    roster_a = store.record_roster_snapshot(
        conn, event_key=key, team_id="team-a", known_at="2030-01-01T08:00:00+00:00",
        players=["a1", "a2", "a3", "a4", "a5"], stand_in_player_ids=[],
        igl_player_id="a1", coach_id="coach-a", source="grid")
    roster_b = store.record_roster_snapshot(
        conn, event_key=key, team_id="team-b", known_at="2030-01-01T08:00:00+00:00",
        players=["b1", "b2", "b3", "b4", "b5"], stand_in_player_ids=["b5"],
        igl_player_id="b1", coach_id=None, source="grid")
    store.record_forecast(
        conn, event_key=key, stage="PRE_VETO", generated_at="2030-01-01T09:00:00+00:00",
        probability_a=.58, model_name="elo", model_version="1", ratings_sha256="a" * 64,
        roster_snapshot_a_id=roster_a, roster_snapshot_b_id=roster_b)
    store.record_veto_action(conn, event_key=key, sequence_no=1, action_type="BAN",
                             actor_team_id="team-a", map_name="Mirage",
                             decided_at="2030-01-01T10:00:00+00:00", source="grid")
    store.record_veto_action(conn, event_key=key, sequence_no=2, action_type="PICK",
                             actor_team_id="team-b", map_name="Nuke",
                             decided_at="2030-01-01T10:01:00+00:00", source="grid")
    store.classify_quote_stage(conn, quote_id="pre", stage="PRE_VETO")
    store.classify_quote_stage(conn, quote_id="post", stage="POST_VETO", veto_sequence_cutoff=2)
    post_forecast = store.record_forecast(
        conn, event_key=key, stage="POST_VETO", generated_at="2030-01-01T10:02:00+00:00",
        probability_a=.63, model_name="elo-map", model_version="1", ratings_sha256="a" * 64,
        roster_snapshot_a_id=roster_a, roster_snapshot_b_id=roster_b, veto_sequence_cutoff=2)
    store.record_external_closing(
        conn, event_key=key, provider="independent-book", source_market_id="book-1",
        captured_at="2030-01-02T11:55:00+00:00", definition_version="liquid-close/1",
        probability_a=.60, decimal_odds_a=1.65, decimal_odds_b=2.35,
        max_spread=.02, liquidity=5000)
    assert conn.execute("SELECT count(*) FROM prospective_order_book_levels").fetchone() == (2,)
    spec = {**StrategySpec(stake=50, min_depth_multiple=1).__dict__, "capital_allowed": False}
    store.register_strategy(conn, spec)
    economic = shadow_decision(
        model_probability=.63, bids=order_books["A"]["bids"], asks=order_books["A"]["asks"],
        strategy=StrategySpec(stake=50, min_depth_multiple=1))
    decision_id = store.record_shadow_decision(
        conn, event_key=key, quote_id="post", forecast_id=post_forecast, selection="A",
        decision=economic, decided_at="2030-01-01T10:03:00+00:00")
    assert decision_id.startswith("decision_")
    assert conn.execute("SELECT decision,capital_allowed FROM prospective_shadow_decisions").fetchone() == ("BET", 0)
    store.record_result(conn, event_key=key, winner="A", score={"team_a": 2, "team_b": 0},
                        result_source="official", result_available_at="2030-01-02T13:00:00+00:00")
    evaluation = store.evaluate_pre_post_veto(
        conn, strategy_version="VETO-01/1", closing_provider="independent-book",
        closing_definition_version="liquid-close/1")
    assert evaluation["post_veto"]["brier"] < evaluation["pre_veto"]["brier"]
    assert evaluation["economic"]["settled_bets"] == 1
    assert evaluation["economic"]["mean_log_clv"] > 0
    assert evaluation["capital_allowed"] is False
    status = store.status(conn, now=datetime(2030, 1, 2, 11, 56, tzinfo=UTC))
    assert status["pre_post_veto_hypothesis_ready_matches"] == 1


def test_post_veto_rejects_proxy_or_missing_real_sequence(tmp_path):
    store = ProspectiveStore(tmp_path / "market.db"); conn = store.connect()
    store.import_quotes(conn, [_quote()], batch_id="b")
    key = "polymarket-clob:m1"
    with pytest.raises(ContractError, match="veto real"):
        store.record_forecast(conn, event_key=key, stage="POST_VETO",
                              generated_at="2030-01-01T10:00:00+00:00", probability_a=.6,
                              model_name="HistoricalVetoProxy", model_version="1",
                              ratings_sha256="a" * 64, veto_sequence_cutoff=1)
    with pytest.raises(ContractError, match="independente"):
        store.record_external_closing(
            conn, event_key=key, provider="polymarket-clob", source_market_id="m1",
            captured_at="2030-01-02T11:55:00+00:00", definition_version="self/1",
            probability_a=.55, decimal_odds_a=1.8, decimal_odds_b=2.2,
            max_spread=.02, liquidity=1000)
