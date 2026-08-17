import pytest

from src import db
from src.market_db import (CANONICALIZATION_VERSION, ContractError, EventMapping,
                           MarketDB, MarketQuote, SportsSeries,
                           beyond_market_validate, canonical_event_id)

START = "2026-07-20T12:00:00+00:00"


def _mapping(status="EXACT", fmt="bo3", team_a="team-a", team_b="team-b"):
    event_id = canonical_event_id(team_a_id=team_a, team_b_id=team_b, match_start_at=START,
                                  series_format=fmt, competition_id="cct-1")
    return EventMapping(event_id, CANONICALIZATION_VERSION, "source-1", "polymarket", START,
                        team_a, team_b, fmt, "cct-1", "series", status,
                        .9 if status != "EXACT" else 1, "2026-07-19T00:00:00+00:00", "rules/1")


def _quote(**changes):
    row = dict(provider="polymarket", source_market_id="m1", captured_at="2026-07-20T10:00:00+00:00",
               bookmaker="polymarket", market_type="moneyline", market_scope="series",
               selection="team-a", decimal_odds=2.0, implied_probability_raw=.5,
               implied_probability_normalized=.5, is_closing=True, closing_definition_version="last-pre-event/1",
               ingestion_batch_id="batch-1", provenance_hash="a" * 64)
    row.update(changes)
    return MarketQuote(**row)


def test_canonical_event_is_deterministic_and_versioned():
    one = canonical_event_id(team_a_id="a", team_b_id="b", match_start_at=START, series_format="bo3", competition_id="x")
    two = canonical_event_id(team_a_id="b", team_b_id="a", match_start_at=START, series_format="bo3", competition_id="x")
    changed = canonical_event_id(team_a_id="a", team_b_id="b", match_start_at=START, series_format="bo3", competition_id="x", canonicalization_version="cs-event/2")
    assert one == two and one != changed


def test_mapping_rejects_invalid_scope_format_and_ambiguous_identity():
    with pytest.raises(ContractError): _mapping(team_a="academy", team_b="academy").validate()
    with pytest.raises(ContractError): _mapping(status="AMBIGUOUS").__class__(**{**_mapping(status="AMBIGUOUS").__dict__, "mapping_confidence": 1}).validate()
    with pytest.raises(ContractError): canonical_event_id(team_a_id="a", team_b_id="b", match_start_at=START, series_format="bo1", competition_id="x", market_scope="map")


def test_market_quote_requires_timestamp_bookmaker_and_valid_margin():
    with pytest.raises(ContractError, match="depois do evento"):
        _quote(captured_at="2026-07-20T12:00:00+00:00").validate(match_start_at=START)
    with pytest.raises(ContractError): _quote(bookmaker="").validate(match_start_at=START)
    with pytest.raises(ContractError): _quote(implied_probability_normalized=float("nan")).validate(match_start_at=START)
    with pytest.raises(ContractError): _quote(max_spread=-.01).validate(match_start_at=START)
    with pytest.raises(ContractError): _quote(liquidity=-1).validate(match_start_at=START)


def test_market_db_rejects_unmapped_and_ambiguous_event(tmp_path):
    store = MarketDB(tmp_path / "market.db"); conn = store.connect()
    event = _mapping(); event.validate()
    with pytest.raises(ContractError): store.insert_quote(conn, canonical_event_id=event.canonical_event_id, quote=_quote(), match_start_at=START)
    store.map_event(conn, _mapping(status="AMBIGUOUS"))
    with pytest.raises(ContractError): store.insert_quote(conn, canonical_event_id=event.canonical_event_id, quote=_quote(), match_start_at=START)
    store.map_event(conn, event); store.insert_quote(conn, canonical_event_id=event.canonical_event_id, quote=_quote(), match_start_at=START)
    assert conn.execute("SELECT count(*) FROM market_quotes").fetchone()[0] == 1


def test_market_db_persists_spread_and_liquidity(tmp_path):
    store = MarketDB(tmp_path / "quotes.db"); conn = store.connect(); event = _mapping()
    store.map_event(conn, event)
    store.insert_quote(conn, canonical_event_id=event.canonical_event_id,
                       quote=_quote(max_spread=.03, liquidity=1250), match_start_at=START)
    assert conn.execute("SELECT max_spread,liquidity FROM market_quotes").fetchone() == (.03, 1250.0)


def test_sports_contract_rejects_future_roster_result_and_bad_hash():
    base = dict(source_event_id="1", source="hltv", match_start_at=START, team_a_id="a", team_b_id="b",
                series_format="bo3", competition_id="c", roster_snapshot_id="r", result_available_at="2026-07-20T13:00:00+00:00",
                ingestion_batch_id="b", provenance_hash="f" * 64)
    SportsSeries(**base).validate()
    with pytest.raises(ContractError): SportsSeries(**{**base, "result_available_at": "2026-07-20T11:00:00+00:00"}).validate()
    with pytest.raises(ContractError): SportsSeries(**{**base, "provenance_hash": "bad"}).validate()


def test_sports_db_metadata_isolated_from_match_result_table():
    conn = db.connect(":memory:")
    db.upsert_matches(conn, [{"match_id": 7, "date": "2026-07-20", "ts": 1,
                              "team_a": "A", "team_b": "B", "score_a": 2,
                              "score_b": 0, "format": "bo3", "event": "Cup"}])
    db.upsert_sports_series_metadata(conn, {"source": "hltv", "source_event_id": "7", "match_id": 7,
        "match_start_at": START, "team_a_id": "a", "team_b_id": "b", "series_format": "bo3",
        "competition_id": "cup", "roster_snapshot_id": None, "result_available_at": "2026-07-20T13:00:00+00:00",
        "ingestion_batch_id": "batch", "provenance_hash": "f" * 64})
    assert conn.execute("SELECT source_event_id FROM sports_series_metadata").fetchone() == ("7",)


def test_two_same_day_events_need_competition_or_start_to_be_distinct():
    first = canonical_event_id(team_a_id="a", team_b_id="b", match_start_at=START, series_format="bo3", competition_id="one")
    second = canonical_event_id(team_a_id="a", team_b_id="b", match_start_at="2026-07-20T16:00:00+00:00", series_format="bo3", competition_id="two")
    assert first != second


def test_beyond_market_has_strict_train_test_cut_and_no_financial_go():
    rows = []
    for i in range(40):
        day = 1 if i < 20 else 2
        rows.append({"captured_at": f"2026-07-{day:02d}T10:00:00+00:00", "match_start_at": f"2026-07-{day:02d}T12:00:00+00:00",
                     "outcome": i % 2, "market_probability": .55 if i % 2 else .45,
                     "model_probability": .60 if i % 2 else .40})
    out = beyond_market_validate(rows, train_end_at="2026-07-02T00:00:00+00:00", minimum_test_rows=20)
    assert out["train_n"] == 20 and out["test_n"] == 20
    assert out["counts_toward_financial_gate"] is False
    assert out["economic_gate"].startswith("NO-GO")


def test_beyond_market_rejects_leakage_and_empty_dataset():
    assert beyond_market_validate([], train_end_at=START)["verdict"] == "INCONCLUSIVE"
    with pytest.raises(ContractError):
        beyond_market_validate([{"captured_at": START, "match_start_at": START, "outcome": 1,
                                  "market_probability": .5, "model_probability": .5}], train_end_at="2026-07-19T00:00:00+00:00")
