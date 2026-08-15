import json
from datetime import UTC, datetime

from scripts.market_shadow_status import main, status
from src.prospective_market import ProspectiveStore


def test_status_with_no_files_at_all_reports_zero_and_blocked(tmp_path):
    result = status(tmp_path / "market_shadow.jsonl", market_db=tmp_path / "market_shadow.db")
    assert result["raw_quotes"] == 0
    assert result["decision_ready"] is False
    assert result["verdict"] == "BLOCKED_BY_MARKET_DATA"


def test_status_falls_back_to_jsonl_when_market_db_does_not_exist_yet(tmp_path):
    quotes = tmp_path / "market_shadow.jsonl"
    quotes.write_text(
        json.dumps(
            {
                "quote_id": "q1",
                "market_id": "m1",
                "model_probability_a": 0.6,
                "model_probability_b": 0.4,
                "ratings_sha256": "a" * 64,
                "observed_at": "2026-08-01T10:00:00+00:00",
                "scheduled_at": "2026-08-02T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    result = status(quotes, market_db=tmp_path / "market_shadow.db")
    assert result["raw_quotes"] == 1
    assert result["eligible_quotes"] == 1
    assert result["eligible_matches"] == 1


def test_status_counts_legacy_ineligible_quotes_missing_required_fields(tmp_path):
    quotes = tmp_path / "market_shadow.jsonl"
    quotes.write_text(json.dumps({"quote_id": "q1"}) + "\n", encoding="utf-8")
    result = status(quotes, market_db=tmp_path / "market_shadow.db")
    assert result["raw_quotes"] == 1
    assert result["eligible_quotes"] == 0
    assert result["legacy_ineligible"] == 1


def test_status_delegates_to_prospective_store_when_market_db_exists(tmp_path):
    market_db = tmp_path / "market_shadow.db"
    store = ProspectiveStore(market_db)
    conn = store.connect()
    store.import_quotes(
        conn,
        [
            {
                "quote_id": "q1",
                "market_id": "m1",
                "team_a": "A",
                "team_b": "B",
                "format": "bo3",
                "scheduled_at": "2030-01-02T12:00:00+00:00",
                "observed_at": "2030-01-01T12:00:00+00:00",
                "model_probability_a": 0.6,
                "model_probability_b": 0.4,
                "ratings_sha256": "a" * 64,
                "probability_a": 0.55,
                "probability_b": 0.45,
                "decimal_a": 1.8,
                "decimal_b": 2.2,
                "source": "polymarket-clob",
                "source_kind": "prediction_market",
                "source_event_id": "e1",
                "competition_name": "Cup",
            }
        ],
        batch_id="b",
    )
    conn.close()

    result = status(
        tmp_path / "unused.jsonl", market_db=market_db, now=datetime(2030, 1, 1, tzinfo=UTC)
    )
    assert result["accepted_mappings"] == 1
    assert result["clv_available"] is False


def test_main_exits_zero_and_prints_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        [
            "market_shadow_status.py",
            "--quotes",
            str(tmp_path / "market_shadow.jsonl"),
            "--market-db",
            str(tmp_path / "market_shadow.db"),
        ],
    )
    exit_code = main()
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["raw_quotes"] == 0
