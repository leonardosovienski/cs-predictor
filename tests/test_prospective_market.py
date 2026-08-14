import sqlite3
from datetime import UTC, datetime

from src.prospective_market import ProspectiveStore, migrate_sports_db


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
