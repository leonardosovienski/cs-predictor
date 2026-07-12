"""SQLite do domínio CS — partidas Tier 1/2 do HLTV (Fase 1).

Uma tabela `matches` no nível de SÉRIE (o resultado que o Elo consome):
match_id do HLTV é a chave (dedupe natural entre páginas re-visitadas).
read_only=True monta mode=ro + query_only (pesquisa não escreve — P12).
"""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id    INTEGER PRIMARY KEY,     -- id do HLTV
    date        TEXT NOT NULL,           -- YYYY-MM-DD (UTC)
    ts          INTEGER,                 -- epoch segundos (ordem intra-dia)
    team_a      TEXT NOT NULL,
    team_b      TEXT NOT NULL,
    score_a     INTEGER NOT NULL,        -- mapas vencidos
    score_b     INTEGER NOT NULL,
    format      TEXT,                    -- bo1 | bo3 | bo5
    event       TEXT
);
CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);

CREATE TABLE IF NOT EXISTS match_maps (
    match_id    INTEGER NOT NULL,        -- FK matches.match_id
    seq         INTEGER NOT NULL,        -- ordem do mapa dentro da série (1..5)
    map_name    TEXT NOT NULL,           -- Mirage, Inferno, Ancient, ...
    team_a      TEXT NOT NULL,           -- mesma convenção de matches.team_a/b
    team_b      TEXT NOT NULL,
    score_a     INTEGER NOT NULL,        -- rounds vencidos NESTE mapa
    score_b     INTEGER NOT NULL,
    PRIMARY KEY (match_id, seq)
);
"""

UPSERT = ("INSERT OR REPLACE INTO matches "
          "(match_id, date, ts, team_a, team_b, score_a, score_b, format, event) "
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")

UPSERT_MAP = ("INSERT OR REPLACE INTO match_maps "
              "(match_id, seq, map_name, team_a, team_b, score_a, score_b) "
              "VALUES (?, ?, ?, ?, ?, ?, ?)")


def connect(db_path: str, read_only: bool = False) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only=ON")
        return conn
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn


def upsert_matches(conn, rows: list[dict]) -> int:
    cur = conn.executemany(UPSERT, [
        (r["match_id"], r["date"], r.get("ts"), r["team_a"], r["team_b"],
         r["score_a"], r["score_b"], r.get("format"), r.get("event"))
        for r in rows])
    conn.commit()
    return cur.rowcount


def upsert_match_maps(conn, match_id: int, maps: list[dict]) -> int:
    cur = conn.executemany(UPSERT_MAP, [
        (match_id, i + 1, m["map_name"], m["team_a"], m["team_b"],
         m["score_a"], m["score_b"])
        for i, m in enumerate(maps)])
    conn.commit()
    return cur.rowcount


def match_ids_missing_maps(conn, teams: list[str] | None = None) -> list[int]:
    """match_id em ordem cronológica que ainda não têm mapa a mapa coletado.

    `teams`, se dado, restringe a partidas em que PELO MENOS um dos lados
    é um desses times (foco em campeonatos específicos, sem raspar o
    histórico inteiro)."""
    where = ("WHERE match_id NOT IN (SELECT DISTINCT match_id FROM match_maps)")
    params: list = []
    if teams:
        placeholders = ",".join("?" for _ in teams)
        where += (f" AND (team_a IN ({placeholders}) "
                  f"OR team_b IN ({placeholders}))")
        params = list(teams) + list(teams)
    rows = conn.execute(
        f"SELECT match_id FROM matches {where} "
        "ORDER BY date, ts, match_id", params).fetchall()
    return [r[0] for r in rows]
