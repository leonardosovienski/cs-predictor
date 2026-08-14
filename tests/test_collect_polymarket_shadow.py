from concurrent.futures import ThreadPoolExecutor

from scripts import collect_polymarket_shadow as collector
from scripts import collect_polymarket_upcoming as upcoming
from scripts.collect_polymarket_shadow import append_once


def test_shadow_dedupes_under_concurrency(tmp_path):
    path = tmp_path / "shadow.jsonl"
    quote = {"quote_id": "q1", "read_only": True}

    def attempt():
        try:
            return append_once(path, quote)
        except RuntimeError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _value: attempt(), range(8)))
    assert outcomes.count(True) == 1
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_quote_freezes_model_probability_and_ratings_hash(tmp_path, monkeypatch):
    ratings = tmp_path / "data" / "ratings.json"
    ratings.parent.mkdir()
    ratings.write_text('{"A": 1500}', encoding="utf-8")
    monkeypatch.setattr(collector, "ROOT", tmp_path)
    monkeypatch.setattr(
        collector,
        "predict_match",
        lambda *_args, **_kwargs: {
            "prob_team_a": 0.6,
            "prob_team_b": 0.4,
            "model": "elo-platt-fase1",
        },
    )
    row = collector.enrich_with_frozen_model({"format": "bo3"}, "A", "B")
    assert row["model_probability_a"] == 0.6
    assert len(row["ratings_sha256"]) == 64


def test_main_cli_fetches_enriches_and_appends_a_single_quote(monkeypatch, tmp_path, capsys):
    ratings = tmp_path / "data" / "ratings.json"
    ratings.parent.mkdir()
    ratings.write_text('{"A": 1500}', encoding="utf-8")
    monkeypatch.setattr(collector, "ROOT", tmp_path)
    monkeypatch.setattr(
        collector,
        "predict_match",
        lambda *_args, **_kwargs: {
            "prob_team_a": 0.6,
            "prob_team_b": 0.4,
            "model": "elo-platt-fase1",
        },
    )
    monkeypatch.setattr(
        collector,
        "PolymarketProvider",
        lambda: type(
            "P",
            (),
            {
                "fetch_match": lambda _self, team_a, team_b, event_id: {
                    "quote_id": "q1",
                    "format": "bo3",
                    "scheduled_at": "2030-01-02T12:00:00+00:00",
                    "team_a": team_a,
                    "team_b": team_b,
                    "event_id": event_id,
                }
            },
        )(),
    )
    exit_code = collector.main(["A", "B", "--event-id", "e1"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert '"inserted": true' in out
    saved = (tmp_path / "data" / "market_shadow.jsonl").read_text(encoding="utf-8")
    assert "q1" in saved


def test_upcoming_collector_freezes_model_before_append(monkeypatch, tmp_path):
    monkeypatch.setattr(upcoming, "ROOT", tmp_path)
    monkeypatch.setattr(
        upcoming,
        "PolymarketProvider",
        lambda: type(
            "P",
            (),
            {
                "list_upcoming_matches": lambda _self, **_kwargs: [
                    {"team_a": "A", "team_b": "B", "event_id": "e"}
                ],
                "fetch_match": lambda _self, *_args, **_kwargs: {"quote_id": "q"},
            },
        )(),
    )
    seen = {}
    monkeypatch.setattr(
        upcoming,
        "enrich_with_frozen_model",
        lambda quote, *_: {**quote, "model_probability_a": 0.6},
    )
    monkeypatch.setattr(
        upcoming, "append_once", lambda _path, quote: seen.setdefault("quote", quote) and 1
    )
    assert upcoming.main() == 0
    assert seen["quote"]["model_probability_a"] == 0.6
