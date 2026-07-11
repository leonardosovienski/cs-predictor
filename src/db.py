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
"""

UPSERT = ("INSERT OR REPLACE INTO matches "
          "(match_id, date, ts, team_a, team_b, score_a, score_b, format, event) "
          "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")


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
