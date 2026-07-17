"""Fase 1 — parser de /results do HLTV e db do CS."""
import pytest

from src import db
from src.data.hltv_provider import parse_match_page, parse_results_page

# bloco mínimo com a estrutura real observada na sondagem 2026-07-12
# (página de detalhe de partida, /matches/<id>/...)
_MATCH_HTML = '''
<div class="mapholder">
  <div class="played">
    <div class="map-name-holder"><div class="mapname">Mirage</div></div>
  </div>
  <div class="results played">
    <div class="results-left won ">
      <div class="results-teamname-container text-ellipsis">
        <div class="results-teamname text-ellipsis">9z</div>
        <div class="results-team-score">13</div>
      </div>
    </div>
<span class="results-right lost pick">
      <div class="results-teamname-container text-ellipsis">
        <div class="results-teamname text-ellipsis">PARIVISION</div>
        <div class="results-team-score">9</div>
      </div>
    </span></div>
</div>
<div class="mapholder">
  <div class="optional">
    <div class="map-name-holder"><div class="mapname">Ancient</div></div>
  </div>
  <div class="results">
    <div class="results-left ">
      <div class="results-teamname-container text-ellipsis">
        <div class="results-teamname text-ellipsis">9z</div>
        <div class="results-team-score">-</div>
      </div>
    </div>
<span class="results-right">
      <div class="results-teamname-container text-ellipsis">
        <div class="results-teamname text-ellipsis">PARIVISION</div>
        <div class="results-team-score">-</div>
      </div>
    </span></div>
</div>
'''

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
<div class="result-con" data-zonedgrouping-entry-unix="1783730000000">
<a href="/matches/2372515/team-a-vs-team-b-cup">
<div class="team team-won">Team &amp; A</div>
<div class="team ">Team B</div>
<td class="result-score"><span class="score-won">2</span> - <span class="score-lost">1</span></td>
<span class="event-name">Cup &amp; Finals</span>
<div class="map-text">nuke</div>
</a></div>
</div>
'''


def test_parse_results_page():
    rows = parse_results_page(_HTML)
    assert len(rows) == 3
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
    assert rows[2]["format"] == "bo3"
    assert rows[2]["team_a"] == "Team & A"
    assert rows[2]["event"] == "Cup & Finals"


def test_parse_bloco_quebrado_nao_derruba():
    quebrado = _HTML.replace('<td class="result-score"><span class="score-won">2</span> - <span class="score-lost">0</span></td>', "")
    rows = parse_results_page(quebrado)
    assert len(rows) == 2                     # só o bloco quebrado fica fora


def test_db_upsert_idempotente():
    conn = db.connect(":memory:")
    r = {"match_id": 1, "date": "2026-07-11", "ts": 1783738869,
         "team_a": "FaZe", "team_b": "BetBoom", "score_a": 2, "score_b": 0,
         "format": "bo3", "event": "XSE"}
    db.upsert_matches(conn, [r])
    db.upsert_matches(conn, [dict(r, score_b=1)])
    assert conn.execute("SELECT score_b FROM matches").fetchall() == [(1,)]


def test_parse_match_page_so_mapas_jogados():
    maps = parse_match_page(_MATCH_HTML)
    assert len(maps) == 1                     # "optional" (nao jogado) fora
    m = maps[0]
    assert m["map_name"] == "Mirage"
    assert (m["team_a"], m["team_b"]) == ("9z", "PARIVISION")
    assert (m["score_a"], m["score_b"]) == (13, 9)


def test_db_upsert_match_maps_idempotente():
    conn = db.connect(":memory:")
    maps = [{"map_name": "Mirage", "team_a": "9z", "team_b": "PARIVISION",
             "score_a": 13, "score_b": 9}]
    db.upsert_match_maps(conn, 1, maps)
    db.upsert_match_maps(conn, 1, [dict(maps[0], score_b=7)])
    rows = conn.execute("SELECT score_b FROM match_maps WHERE match_id=1").fetchall()
    assert rows == [(7,)]


def test_match_ids_missing_maps(tmp_path):
    conn = db.connect(":memory:")
    db.upsert_matches(conn, [
        {"match_id": 1, "date": "2026-07-01", "ts": 1, "team_a": "A",
         "team_b": "B", "score_a": 2, "score_b": 0, "format": "bo3"},
        {"match_id": 2, "date": "2026-07-02", "ts": 1, "team_a": "A",
         "team_b": "C", "score_a": 2, "score_b": 1, "format": "bo3"},
    ])
    db.upsert_match_maps(conn, 1, [{"map_name": "Mirage", "team_a": "A",
                                     "team_b": "B", "score_a": 13, "score_b": 9}])
    assert db.match_ids_missing_maps(conn) == [2]


def test_db_read_only(tmp_path):
    import sqlite3
    p = tmp_path / "cs.db"
    db.connect(str(p)).close()
    ro = db.connect(str(p), read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM matches")
