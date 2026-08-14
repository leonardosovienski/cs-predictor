import json

from scripts.import_market_quotes import main
from src.beyond_market_closure import BeyondMarketClosedError
from src.prospective_market import ProspectiveStore


def _quote_line(**updates):
    row = {
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
    row.update(updates)
    return json.dumps(row)


def test_main_reports_no_quotes_when_jsonl_missing(tmp_path, capsys):
    exit_code = main(
        [
            "--quotes",
            str(tmp_path / "missing.jsonl"),
            "--market-db",
            str(tmp_path / "market_shadow.db"),
        ]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "NO_QUOTES"


def test_main_dry_run_reports_line_count_without_writing(tmp_path, capsys):
    quotes = tmp_path / "market_shadow.jsonl"
    quotes.write_text(_quote_line() + "\n", encoding="utf-8")
    exit_code = main(
        ["--quotes", str(quotes), "--market-db", str(tmp_path / "market_shadow.db"), "--dry-run"]
    )
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"status": "DRY_RUN", "linhas_no_jsonl": 1}
    assert not (tmp_path / "market_shadow.db").exists()


def test_main_imports_quotes_and_reports_ok(tmp_path, capsys):
    quotes = tmp_path / "market_shadow.jsonl"
    quotes.write_text(_quote_line() + "\n", encoding="utf-8")
    market_db = tmp_path / "market_shadow.db"
    exit_code = main(["--quotes", str(quotes), "--market-db", str(market_db)])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "OK"
    assert out["import"]["imported"] == 1
    assert out["accepted"] == 1
    assert market_db.exists()


def test_main_reports_shadow_closed_when_gate_rejects(tmp_path, capsys, monkeypatch):
    quotes = tmp_path / "market_shadow.jsonl"
    quotes.write_text(_quote_line() + "\n", encoding="utf-8")

    def _closed(self):
        raise BeyondMarketClosedError("fixture: shadow fechado")

    monkeypatch.setattr(ProspectiveStore, "connect", _closed)
    exit_code = main(["--quotes", str(quotes), "--market-db", str(tmp_path / "market_shadow.db")])
    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "SHADOW_COLLECTION_CLOSED"
