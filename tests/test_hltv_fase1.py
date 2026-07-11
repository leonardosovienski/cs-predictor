"""Fase 1 — parser de /results do HLTV e db do CS."""
import pytest

from src import db
from src.data.hltv_provider import parse_results_page

# bloco mínimo com a estrutura real observada na sondagem de 2026-07-11
_HTML = '''
<div class="results-all">
<span class="standard-headline">Results for July 11th 2026</span>
<div class="result-con" data-zonedgrouping-entry-unix="1783738869000">
<a href="/matches/2372513/faze-vs-betboom-xse-pro-league">
<div class="team team-won">FaZe</div>
<div class="team ">BetBoom</div>
<td class="result-score"><span class="score-won">2</span> - <span class="score-lost">0</span></td>
<span class="event-name">XSE Pro League Guangzhou 2026</span>
<div class="map-text">bo3</div>
</a></div>
<div class="result-con" data-zonedgrouping-entry-unix="1783733794000">
<a href="/matches/2372514/voca-vs-regain-circuit-x">
<div class="team ">Voca</div>
<div class="team team-won">regain</div>
<td class="result-score"><span class="score-lost">0</span> - <span class="score-won">1</span></td>
<span class="event-name">Circuit X BLAST Open</span>
<div class="map-text">inf</div>
</a></div>
</div>
'''


def test_parse_results_page():
    rows = parse_results_page(_HTML)
    assert len(rows) == 2
    r = rows[0]
    assert r["match_id"] == 2372513
    assert (r["team_a"], r["team_b"]) == ("FaZe", "BetBoom")
    assert (r["score_a"], r["score_b"]) == (2, 0)
    assert r["format"] == "bo3"
    assert r["event"] == "XSE Pro League Guangzhou 2026"
    assert r["date"] == "2026-07-11"          # do timestamp unix (ms)
    # map-text com nome de mapa = BO1
    assert rows[1]["format"] == "bo1"
    assert (rows[1]["score_a"], rows[1]["score_b"]) == (0, 1)


def test_parse_bloco_quebrado_nao_derruba():
    quebrado = _HTML.replace('<td class="result-score"><span class="score-won">2</span> - <span class="score-lost">0</span></td>', "")
    rows = parse_results_page(quebrado)
    assert len(rows) == 1                     # só o bloco íntegro sobra


def test_db_upsert_idempotente():
    conn = db.connect(":memory:")
    r = {"match_id": 1, "date": "2026-07-11", "ts": 1783738869,
         "team_a": "FaZe", "team_b": "BetBoom", "score_a": 2, "score_b": 0,
         "format": "bo3", "event": "XSE"}
    db.upsert_matches(conn, [r])
    db.upsert_matches(conn, [dict(r, score_b=1)])
    assert conn.execute("SELECT score_b FROM matches").fetchall() == [(1,)]


def test_db_read_only(tmp_path):
    import sqlite3
    p = tmp_path / "cs.db"
    db.connect(str(p)).close()
    ro = db.connect(str(p), read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM matches")
