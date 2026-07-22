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

-- Camada Sports DB: metadados temporais/proveniência sem alterar a tabela que
-- alimenta o Elo. A separação impede que um preço de mercado vire dado esportivo.
CREATE TABLE IF NOT EXISTS sports_series_metadata (
    source TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    match_id INTEGER NOT NULL UNIQUE,
    match_start_at TEXT NOT NULL,
    team_a_id TEXT NOT NULL,
    team_b_id TEXT NOT NULL,
    series_format TEXT NOT NULL CHECK(series_format IN ('bo1','bo3','bo5')),
    competition_id TEXT NOT NULL,
    roster_snapshot_id TEXT,
    result_available_at TEXT NOT NULL,
    ingestion_batch_id TEXT NOT NULL,
    provenance_hash TEXT NOT NULL,
    PRIMARY KEY(source, source_event_id),
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);
CREATE INDEX IF NOT EXISTS idx_sports_metadata_start ON sports_series_metadata(match_start_at);

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


def upsert_sports_series_metadata(conn, row: dict) -> None:
    """Registra o contrato Sports DB; não aceita resultado disponível antes do jogo."""
    required = ("source", "source_event_id", "match_id", "match_start_at", "team_a_id",
                "team_b_id", "series_format", "competition_id", "result_available_at",
                "ingestion_batch_id", "provenance_hash")
    if any(not row.get(key) for key in required):
        raise ValueError("metadado Sports DB incompleto")
    if row["team_a_id"] == row["team_b_id"] or row["series_format"] not in {"bo1", "bo3", "bo5"}:
        raise ValueError("identidade/formato Sports DB inválido")
    if row["result_available_at"] < row["match_start_at"] or len(row["provenance_hash"]) != 64:
        raise ValueError("tempo/proveniência Sports DB inválido")
    conn.execute("""INSERT OR REPLACE INTO sports_series_metadata
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                 tuple(row.get(key) for key in required[:8]) + (row.get("roster_snapshot_id"),)
                 + tuple(row.get(key) for key in required[8:]))
    conn.commit()


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
