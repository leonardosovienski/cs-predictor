"""Migração e lifecycle auditável da coorte prospectiva de mercado CS.

O módulo deliberadamente não adivinha match IDs, rosters ou resultados. Linhas
sem os dados necessários ficam REJECTED/PARTIAL e nunca entram no settlement.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .beyond_market_closure import (
    assert_beyond_market_open,
    assert_market_shadow_collection_open,
    is_production_market_db,
    is_shadow_market_db,
)
from .market_db import ContractError, canonical_event_id
from .shadow_economics import probability_metrics

ACCEPTED_MAPPING = {"EXACT", "RULE_BASED", "MANUAL_CONFIRMED"}
EVENT_STATES = {"PRE_EVENT", "EVENT_TIME_PASSED", "RESULT_PENDING", "RESULT_VALIDATED",
                "CLOSING_PENDING", "SETTLEMENT_READY", "MATURED", "VOID", "REJECTED"}
VETO_ACTIONS = {"BAN", "PICK", "DECIDER", "START_SIDE"}
FORECAST_STAGES = {"PRE_VETO", "POST_VETO"}


def _iso(ts: int | None, date: str) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat(timespec="seconds")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def _team_id(name: str) -> str:
    # Exato em Unicode: nunca colapsa LEO/Leo só para ganhar cobertura.
    return "team_" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:20]


SPORTS_MIGRATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sports_series_contract (
  match_id INTEGER PRIMARY KEY, source TEXT NOT NULL, source_event_id TEXT NOT NULL,
  match_start_at TEXT, team_a_id TEXT NOT NULL, team_b_id TEXT NOT NULL,
  series_format TEXT, competition_id TEXT, competition_name TEXT,
  market_scope TEXT NOT NULL, roster_snapshot_id TEXT, result_json TEXT,
  result_available_at TEXT, ingestion_batch_id TEXT NOT NULL, provenance_hash TEXT NOT NULL,
  migration_status TEXT NOT NULL, migration_reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sports_migrations (
  migration_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source_count INTEGER NOT NULL,
  migrated_count INTEGER NOT NULL, partial_count INTEGER NOT NULL, rejected_count INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL
);
"""


def migrate_sports_db(conn: sqlite3.Connection, *, migration_id: str) -> dict[str, int | str]:
    """Materializa uma visão contratual sem alterar o resultado esportivo base.

    É idempotente por `match_id`; timestamp de disponibilidade do resultado e
    roster inexistentes são preservados como nulos e classificados PARTIAL.
    """
    conn.executescript(SPORTS_MIGRATION_SCHEMA)
    already = conn.execute("SELECT 1 FROM sports_migrations WHERE migration_id=?", (migration_id,)).fetchone()
    if already:
        return {"migration_id": migration_id, "status": "ALREADY_APPLIED"}
    rows = conn.execute("SELECT match_id,date,ts,team_a,team_b,score_a,score_b,format,event FROM matches ORDER BY match_id").fetchall()
    counts = {"MIGRATED": 0, "PARTIAL": 0, "REJECTED": 0}
    digest_rows = []
    for mid, date, ts, a, b, sa, sb, fmt, event in rows:
        start = _iso(ts, date)
        reason = "result_available_at/roster_snapshot_id indisponíveis na fonte histórica"
        status = "PARTIAL"
        if not start or fmt not in {"bo1", "bo3", "bo5"} or a == b:
            status, reason = "REJECTED", "timestamp/formato/identidade insuficiente"
        competition_name = event or ""
        record = {"match_id": mid, "date": date, "ts": ts, "team_a": a, "team_b": b,
                  "score_a": sa, "score_b": sb, "format": fmt, "event": event}
        provenance = _hash(record)
        competition_id = "competition_" + _hash({"source": "hltv", "name": competition_name})[:20] if competition_name else None
        conn.execute("""INSERT OR REPLACE INTO sports_series_contract VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (mid, "hltv", str(mid), start, _team_id(a), _team_id(b), fmt, competition_id,
                      competition_name or None, "series", None,
                      json.dumps({"score_a": sa, "score_b": sb}), None, migration_id,
                      provenance, status, reason))
        counts[status] += 1; digest_rows.append(record)
    source_hash = _hash(digest_rows)
    conn.execute("INSERT INTO sports_migrations VALUES(?,?,?,?,?,?,?)",
                 (migration_id, datetime.now(UTC).isoformat(timespec="seconds"), len(rows),
                  counts["MIGRATED"], counts["PARTIAL"], counts["REJECTED"], source_hash))
    conn.commit()
    return {"migration_id": migration_id, "status": "APPLIED", "source_count": len(rows),
            "migrated": counts["MIGRATED"], "partial": counts["PARTIAL"], "rejected": counts["REJECTED"],
            "source_sha256": source_hash}


PROSPECTIVE_SCHEMA = """
CREATE TABLE IF NOT EXISTS prospective_events (
  event_key TEXT PRIMARY KEY, provider TEXT NOT NULL, source_event_id TEXT,
  source_market_id TEXT NOT NULL, canonical_event_id TEXT, match_start_at TEXT NOT NULL,
  team_a TEXT NOT NULL, team_b TEXT NOT NULL, team_a_id TEXT, team_b_id TEXT,
  series_format TEXT NOT NULL, competition_id TEXT, competition_name TEXT,
  mapping_status TEXT NOT NULL, mapping_confidence REAL NOT NULL, mapping_rule_version TEXT NOT NULL,
  mapping_reason TEXT NOT NULL, reviewed_at TEXT NOT NULL, event_state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_quotes (
  quote_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, provider TEXT NOT NULL,
  source_market_id TEXT NOT NULL, captured_at TEXT NOT NULL, bookmaker TEXT,
  market_type TEXT NOT NULL, market_scope TEXT NOT NULL, selection_a_odds REAL,
  selection_b_odds REAL, probability_a REAL, probability_b REAL, max_spread REAL,
  model_probability_a REAL NOT NULL, model_probability_b REAL NOT NULL, ratings_sha256 TEXT NOT NULL,
  ingestion_batch_id TEXT NOT NULL, provenance_hash TEXT NOT NULL, data_quality_status TEXT NOT NULL,
  liquidity REAL
);
CREATE TABLE IF NOT EXISTS prospective_results (
  event_key TEXT PRIMARY KEY, winner TEXT NOT NULL, result_json TEXT NOT NULL,
  result_source TEXT NOT NULL, result_available_at TEXT NOT NULL, provenance_hash TEXT NOT NULL,
  validation_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_closings (
  event_key TEXT PRIMARY KEY, quote_id TEXT NOT NULL, captured_at TEXT NOT NULL,
  closing_definition_version TEXT NOT NULL, provenance_hash TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_settlements (
  event_key TEXT PRIMARY KEY, outcome_a INTEGER NOT NULL, model_probability_a REAL NOT NULL,
  market_probability_a REAL NOT NULL, closing_quote_id TEXT NOT NULL, settled_at TEXT NOT NULL,
  provenance_hash TEXT NOT NULL, settlement_status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_roster_snapshots (
  roster_snapshot_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, team_id TEXT NOT NULL,
  known_at TEXT NOT NULL, players_json TEXT NOT NULL, stand_in_player_ids_json TEXT NOT NULL,
  igl_player_id TEXT, coach_id TEXT, source TEXT NOT NULL, provenance_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_veto_actions (
  event_key TEXT NOT NULL, sequence_no INTEGER NOT NULL, action_type TEXT NOT NULL,
  actor_team_id TEXT, map_name TEXT NOT NULL, starting_side TEXT, decided_at TEXT NOT NULL,
  source TEXT NOT NULL, provenance_hash TEXT NOT NULL,
  PRIMARY KEY(event_key, sequence_no)
);
CREATE TABLE IF NOT EXISTS prospective_forecasts (
  forecast_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, stage TEXT NOT NULL,
  generated_at TEXT NOT NULL, probability_a REAL NOT NULL, probability_b REAL NOT NULL,
  model_name TEXT NOT NULL, model_version TEXT NOT NULL, ratings_sha256 TEXT NOT NULL,
  roster_snapshot_a_id TEXT, roster_snapshot_b_id TEXT, veto_sequence_cutoff INTEGER,
  provenance_hash TEXT NOT NULL, UNIQUE(event_key, stage)
);
CREATE TABLE IF NOT EXISTS prospective_quote_stages (
  quote_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, stage TEXT NOT NULL,
  veto_sequence_cutoff INTEGER, classified_at TEXT NOT NULL, provenance_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_order_books (
  quote_id TEXT NOT NULL, selection TEXT NOT NULL, token_id TEXT NOT NULL,
  published_at TEXT NOT NULL, book_hash TEXT NOT NULL, tick_size REAL,
  min_order_size REAL, executable_depth_available INTEGER NOT NULL,
  PRIMARY KEY(quote_id, selection)
);
CREATE TABLE IF NOT EXISTS prospective_order_book_levels (
  quote_id TEXT NOT NULL, selection TEXT NOT NULL, side TEXT NOT NULL,
  level_no INTEGER NOT NULL, price REAL NOT NULL, size REAL,
  PRIMARY KEY(quote_id, selection, side, level_no)
);
CREATE TABLE IF NOT EXISTS prospective_strategy_specs (
  strategy_version TEXT PRIMARY KEY, registered_at TEXT NOT NULL,
  spec_json TEXT NOT NULL, provenance_hash TEXT NOT NULL, capital_allowed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_shadow_decisions (
  decision_id TEXT PRIMARY KEY, event_key TEXT NOT NULL, quote_id TEXT NOT NULL,
  forecast_id TEXT NOT NULL, strategy_version TEXT NOT NULL, selection TEXT NOT NULL,
  decision TEXT NOT NULL, reason TEXT NOT NULL, requested_stake REAL NOT NULL,
  filled_stake REAL NOT NULL, average_price REAL, effective_decimal_odds REAL,
  net_edge REAL, decided_at TEXT NOT NULL, payload_json TEXT NOT NULL,
  provenance_hash TEXT NOT NULL, capital_allowed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS prospective_external_closings (
  event_key TEXT NOT NULL, provider TEXT NOT NULL, source_market_id TEXT NOT NULL,
  captured_at TEXT NOT NULL, definition_version TEXT NOT NULL, probability_a REAL NOT NULL,
  decimal_odds_a REAL NOT NULL, decimal_odds_b REAL NOT NULL, max_spread REAL,
  liquidity REAL, provenance_hash TEXT NOT NULL, status TEXT NOT NULL,
  PRIMARY KEY(event_key, provider, definition_version)
);
"""


def _migrate_add_liquidity_column(conn: sqlite3.Connection) -> None:
    """Bancos shadow criados antes desta coluna existir não têm `liquidity`;
    ALTER TABLE idempotente evita perder cotações já coletadas no disco do
    operador (nunca recriamos o banco por baixo dele)."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(prospective_quotes)")}
    if "liquidity" not in columns:
        conn.execute("ALTER TABLE prospective_quotes ADD COLUMN liquidity REAL")
        conn.commit()


class ProspectiveStore:
    def __init__(self, path: str | Path): self.path = Path(path)
    def connect(self) -> sqlite3.Connection:
        self._assert_open()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=5000")
        c.executescript(PROSPECTIVE_SCHEMA)
        _migrate_add_liquidity_column(c)
        return c

    def _assert_open(self) -> None:
        if is_production_market_db(self.path):
            assert_beyond_market_open()
        if is_shadow_market_db(self.path):
            assert_market_shadow_collection_open()

    @staticmethod
    def _event_key(row: dict) -> str:
        return f"{row.get('source','polymarket-clob')}:{row.get('market_id') or row['quote_id']}"

    def import_quotes(self, conn: sqlite3.Connection, rows: list[dict], *, batch_id: str) -> dict[str, int]:
        self._assert_open()
        counts = {"imported": 0, "exact": 0, "rejected": 0, "invalid": 0}
        for row in rows:
            try:
                required = ("quote_id", "market_id", "team_a", "team_b", "format", "scheduled_at", "observed_at",
                            "model_probability_a", "model_probability_b", "ratings_sha256")
                if any(key not in row for key in required): raise ContractError("quote sem previsão congelada ou campos obrigatórios")
                if row["format"] not in {"bo1", "bo3", "bo5"}: raise ContractError("formato inválido")
                start = datetime.fromisoformat(row["scheduled_at"].replace("Z", "+00:00"))
                observed = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
                if observed >= start: raise ContractError("quote posterior ao evento")
                event_key = self._event_key(row); provider = row.get("source", "polymarket-clob")
                source_event_id = row.get("source_event_id")
                competition = row.get("competition_name") or None
                if source_event_id and competition:
                    a_id, b_id = _team_id(row["team_a"]), _team_id(row["team_b"])
                    comp_id = "competition_" + _hash({"source": provider, "name": competition})[:20]
                    canonical = canonical_event_id(team_a_id=a_id, team_b_id=b_id, match_start_at=row["scheduled_at"],
                                                   series_format=row["format"], competition_id=comp_id)
                    mapping_status, confidence, reason = "RULE_BASED", .8, "fonte fornece event_id, competição, times, formato e horário"
                    counts["exact"] += 1
                else:
                    a_id = b_id = comp_id = canonical = None
                    mapping_status, confidence, reason = "REJECTED", 0.0, "quote legado sem source_event_id/competição; promoção proibida"
                    counts["rejected"] += 1
                now = datetime.now(UTC).isoformat(timespec="seconds")
                state = "PRE_EVENT" if start > datetime.now(start.tzinfo) else "EVENT_TIME_PASSED"
                # Uma cotação nova pode enriquecer um mercado que entrou antes
                # da evolução do schema. Não preservamos REJECTED legado quando
                # a mesma fonte passa a fornecer event_id e competição.
                conn.execute("""INSERT OR REPLACE INTO prospective_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (event_key, provider, source_event_id, str(row["market_id"]), canonical, row["scheduled_at"],
                              row["team_a"], row["team_b"], a_id, b_id, row["format"], comp_id, competition,
                              mapping_status, confidence, "mapping/1", reason, now, state))
                quality = "ELIGIBLE" if mapping_status in ACCEPTED_MAPPING else "REJECTED_MAPPING"
                conn.execute("""INSERT OR IGNORE INTO prospective_quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (row["quote_id"], event_key, provider, str(row["market_id"]), row["observed_at"],
                              provider if row.get("source_kind") == "prediction_market" else None, "moneyline", "series",
                              row.get("decimal_a"), row.get("decimal_b"), row.get("probability_a"), row.get("probability_b"),
                              row.get("max_spread"), row["model_probability_a"], row["model_probability_b"],
                              row["ratings_sha256"], batch_id, _hash(row), quality, row.get("liquidity")))
                for selection, book in (row.get("order_books") or {}).items():
                    conn.execute("""INSERT OR IGNORE INTO prospective_order_books
                                 VALUES(?,?,?,?,?,?,?,?)""",
                                 (row["quote_id"], selection, book["token_id"],
                                  book["published_at"], book.get("book_hash", ""),
                                  book.get("tick_size"), book.get("min_order_size"),
                                  int(book.get("executable_depth_available", False))))
                    for side in ("bids", "asks"):
                        for level_no, level in enumerate(book.get(side) or [], 1):
                            conn.execute("""INSERT OR IGNORE INTO prospective_order_book_levels
                                         VALUES(?,?,?,?,?,?)""",
                                         (row["quote_id"], selection, side.upper(), level_no,
                                          level["price"], level.get("size")))
                counts["imported"] += 1
            except (ContractError, ValueError, TypeError): counts["invalid"] += 1
        conn.commit(); return counts

    def record_roster_snapshot(self, conn: sqlite3.Connection, *, event_key: str, team_id: str,
                               known_at: str, players: list[str], stand_in_player_ids: list[str],
                               igl_player_id: str | None, coach_id: str | None,
                               source: str) -> str:
        """Persist a point-in-time roster without pretending a reserved ID is populated."""
        self._assert_open()
        event = conn.execute("SELECT match_start_at FROM prospective_events WHERE event_key=?",
                             (event_key,)).fetchone()
        if not event:
            raise ContractError("evento prospectivo desconhecido")
        known = datetime.fromisoformat(known_at.replace("Z", "+00:00"))
        start = datetime.fromisoformat(event[0].replace("Z", "+00:00"))
        if known >= start or not players or len(players) != len(set(players)):
            raise ContractError("roster exige jogadores únicos conhecidos antes do evento")
        if any(player not in players for player in stand_in_player_ids):
            raise ContractError("stand-in não pertence ao roster")
        payload = {"event_key": event_key, "team_id": team_id, "known_at": known_at,
                   "players": players, "stand_ins": stand_in_player_ids, "igl": igl_player_id,
                   "coach": coach_id, "source": source}
        roster_id = "roster_" + _hash(payload)[:24]
        conn.execute("""INSERT OR IGNORE INTO prospective_roster_snapshots
                     VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (roster_id, event_key, team_id, known_at, json.dumps(players, sort_keys=True),
                      json.dumps(stand_in_player_ids, sort_keys=True), igl_player_id, coach_id,
                      source, _hash(payload)))
        conn.commit()
        return roster_id

    def record_veto_action(self, conn: sqlite3.Connection, *, event_key: str, sequence_no: int,
                           action_type: str, map_name: str, decided_at: str, source: str,
                           actor_team_id: str | None = None,
                           starting_side: str | None = None) -> None:
        """Record a real, timestamped veto action; historical map frequency is not accepted."""
        self._assert_open()
        event = conn.execute("SELECT match_start_at FROM prospective_events WHERE event_key=?",
                             (event_key,)).fetchone()
        action = action_type.upper()
        if not event:
            raise ContractError("evento prospectivo desconhecido")
        if sequence_no < 1 or action not in VETO_ACTIONS or not map_name.strip() or not source.strip():
            raise ContractError("ação de veto inválida")
        decided = datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
        start = datetime.fromisoformat(event[0].replace("Z", "+00:00"))
        if decided >= start:
            raise ContractError("veto deve ser conhecido antes do evento")
        previous = conn.execute("SELECT max(sequence_no),max(decided_at) FROM prospective_veto_actions "
                                "WHERE event_key=?", (event_key,)).fetchone()
        if previous[0] is not None and (sequence_no != previous[0] + 1 or decided_at < previous[1]):
            raise ContractError("sequência/timestamp de veto não monotônico")
        payload = {"event_key": event_key, "sequence": sequence_no, "action": action,
                   "actor": actor_team_id, "map": map_name, "side": starting_side,
                   "decided_at": decided_at, "source": source}
        conn.execute("INSERT INTO prospective_veto_actions VALUES(?,?,?,?,?,?,?,?,?)",
                     (event_key, sequence_no, action, actor_team_id, map_name, starting_side,
                      decided_at, source, _hash(payload)))
        conn.commit()

    def record_forecast(self, conn: sqlite3.Connection, *, event_key: str, stage: str,
                        generated_at: str, probability_a: float, model_name: str,
                        model_version: str, ratings_sha256: str,
                        roster_snapshot_a_id: str | None = None,
                        roster_snapshot_b_id: str | None = None,
                        veto_sequence_cutoff: int | None = None) -> str:
        """Freeze comparable pre/post-veto probabilities with strict temporal semantics."""
        self._assert_open()
        normalized_stage = stage.upper()
        event = conn.execute("SELECT match_start_at FROM prospective_events WHERE event_key=?",
                             (event_key,)).fetchone()
        if not event or normalized_stage not in FORECAST_STAGES or not 0 < probability_a < 1:
            raise ContractError("previsão prospectiva inválida")
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        start = datetime.fromisoformat(event[0].replace("Z", "+00:00"))
        if generated >= start or len(ratings_sha256) != 64:
            raise ContractError("tempo/rating da previsão inválido")
        last_veto = conn.execute("SELECT max(sequence_no),max(decided_at) FROM prospective_veto_actions "
                                 "WHERE event_key=?", (event_key,)).fetchone()
        if normalized_stage == "PRE_VETO" and last_veto[0] is not None:
            first_veto = conn.execute("SELECT min(decided_at) FROM prospective_veto_actions "
                                      "WHERE event_key=?", (event_key,)).fetchone()[0]
            if generated_at >= first_veto:
                raise ContractError("previsão PRE_VETO posterior ao início do veto")
        if normalized_stage == "POST_VETO":
            if last_veto[0] is None or veto_sequence_cutoff != last_veto[0] or generated_at < last_veto[1]:
                raise ContractError("previsão POST_VETO exige veto real completo até o cutoff")
        payload = {"event_key": event_key, "stage": normalized_stage, "generated_at": generated_at,
                   "probability_a": probability_a, "model": model_name, "version": model_version,
                   "ratings": ratings_sha256, "rosters": [roster_snapshot_a_id, roster_snapshot_b_id],
                   "veto_sequence_cutoff": veto_sequence_cutoff}
        forecast_id = "forecast_" + _hash(payload)[:24]
        conn.execute("""INSERT INTO prospective_forecasts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (forecast_id, event_key, normalized_stage, generated_at, probability_a,
                      1 - probability_a, model_name, model_version, ratings_sha256,
                      roster_snapshot_a_id, roster_snapshot_b_id, veto_sequence_cutoff, _hash(payload)))
        conn.commit()
        return forecast_id

    def classify_quote_stage(self, conn: sqlite3.Connection, *, quote_id: str, stage: str,
                             veto_sequence_cutoff: int | None = None) -> None:
        """Classify a persisted executable quote against observed veto timestamps."""
        self._assert_open()
        normalized_stage = stage.upper()
        quote = conn.execute("SELECT event_key,captured_at FROM prospective_quotes WHERE quote_id=?",
                             (quote_id,)).fetchone()
        if not quote or normalized_stage not in FORECAST_STAGES:
            raise ContractError("quote/estágio inválido")
        event_key, captured_at = quote
        boundary = conn.execute("SELECT min(decided_at),max(decided_at),max(sequence_no) "
                                "FROM prospective_veto_actions WHERE event_key=?", (event_key,)).fetchone()
        if boundary[2] is None:
            raise ContractError("classificação exige veto real timestampado")
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        first = datetime.fromisoformat(boundary[0].replace("Z", "+00:00"))
        last = datetime.fromisoformat(boundary[1].replace("Z", "+00:00"))
        if normalized_stage == "PRE_VETO" and captured >= first:
            raise ContractError("quote PRE_VETO não antecede o veto")
        if normalized_stage == "POST_VETO" and (
                captured < last or veto_sequence_cutoff != boundary[2]):
            raise ContractError("quote POST_VETO exige veto completo até o cutoff")
        payload = {"quote_id": quote_id, "event_key": event_key, "stage": normalized_stage,
                   "veto_sequence_cutoff": veto_sequence_cutoff}
        conn.execute("INSERT OR REPLACE INTO prospective_quote_stages VALUES(?,?,?,?,?,?)",
                     (quote_id, event_key, normalized_stage, veto_sequence_cutoff,
                      datetime.now(UTC).isoformat(timespec="seconds"), _hash(payload)))
        conn.commit()

    def register_strategy(self, conn: sqlite3.Connection, spec: dict[str, Any]) -> str:
        """Freeze a no-capital strategy before any prospective decision."""
        self._assert_open()
        version = str(spec.get("version") or "").strip()
        required = ("stake", "min_edge", "max_spread", "min_depth_multiple", "fee_rate")
        if not version or any(key not in spec for key in required):
            raise ContractError("estratégia incompleta")
        if spec.get("capital_allowed") is not False:
            raise ContractError("estratégia prospectiva deve ser shadow-only")
        payload = {key: spec[key] for key in sorted(spec)}
        conn.execute("INSERT OR IGNORE INTO prospective_strategy_specs VALUES(?,?,?,?,0)",
                     (version, datetime.now(UTC).isoformat(timespec="seconds"),
                      json.dumps(payload, sort_keys=True), _hash(payload)))
        conn.commit()
        return version

    def record_shadow_decision(self, conn: sqlite3.Connection, *, event_key: str,
                               quote_id: str, forecast_id: str, selection: str,
                               decision: dict[str, Any], decided_at: str) -> str:
        """Append an auditable BET/NO_BET/NO_FILL decision; real capital is impossible."""
        self._assert_open()
        allowed = {"BET", "NO_BET", "NO_FILL"}
        strategy = decision.get("strategy") or {}
        version = str(strategy.get("version") or "")
        if decision.get("decision") not in allowed or strategy.get("capital_allowed", False):
            raise ContractError("decisão shadow inválida")
        registered = conn.execute("SELECT 1 FROM prospective_strategy_specs WHERE strategy_version=? "
                                  "AND capital_allowed=0", (version,)).fetchone()
        quote = conn.execute("""SELECT 1 FROM prospective_quote_stages
                              WHERE quote_id=? AND event_key=? AND stage='POST_VETO'""",
                             (quote_id, event_key)).fetchone()
        forecast = conn.execute("""SELECT 1 FROM prospective_forecasts
                                 WHERE forecast_id=? AND event_key=? AND stage='POST_VETO'""",
                                (forecast_id, event_key)).fetchone()
        if not registered or not quote or not forecast:
            raise ContractError("decisão exige estratégia, quote e previsão POST_VETO")
        event = conn.execute("SELECT match_start_at FROM prospective_events WHERE event_key=?",
                             (event_key,)).fetchone()
        moment = datetime.fromisoformat(decided_at.replace("Z", "+00:00"))
        if not event or moment >= datetime.fromisoformat(event[0].replace("Z", "+00:00")):
            raise ContractError("decisão posterior ao evento")
        payload = {**decision, "event_key": event_key, "quote_id": quote_id,
                   "forecast_id": forecast_id, "selection": selection,
                   "decided_at": decided_at, "capital_allowed": False}
        decision_id = "decision_" + _hash(payload)[:24]
        conn.execute("""INSERT OR IGNORE INTO prospective_shadow_decisions
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                     (decision_id, event_key, quote_id, forecast_id, version, selection,
                      decision["decision"], decision["reason"], decision["requested_stake"],
                      decision.get("filled_stake", 0), decision.get("average_price"),
                      decision.get("effective_decimal_odds"), decision.get("net_edge"),
                      decided_at, json.dumps(payload, sort_keys=True), _hash(payload)))
        conn.commit()
        return decision_id

    def record_external_closing(self, conn: sqlite3.Connection, *, event_key: str, provider: str,
                                source_market_id: str, captured_at: str, definition_version: str,
                                probability_a: float, decimal_odds_a: float, decimal_odds_b: float,
                                max_spread: float | None, liquidity: float | None) -> None:
        """Record an independent closing reference; Polymarket self-closing is rejected."""
        self._assert_open()
        event = conn.execute("SELECT provider,match_start_at FROM prospective_events WHERE event_key=?",
                             (event_key,)).fetchone()
        if not event:
            raise ContractError("evento prospectivo desconhecido")
        if provider == event[0] or provider.lower().startswith("polymarket"):
            raise ContractError("closing externo deve usar fonte independente")
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        start = datetime.fromisoformat(event[1].replace("Z", "+00:00"))
        if captured >= start or not 0 < probability_a < 1 or decimal_odds_a <= 1 or decimal_odds_b <= 1:
            raise ContractError("closing externo inválido")
        if max_spread is not None and not 0 <= max_spread <= 1:
            raise ContractError("spread externo inválido")
        if liquidity is not None and liquidity < 0:
            raise ContractError("liquidez externa inválida")
        payload = {"event_key": event_key, "provider": provider, "market": source_market_id,
                   "captured_at": captured_at, "definition": definition_version,
                   "probability_a": probability_a, "odds": [decimal_odds_a, decimal_odds_b],
                   "max_spread": max_spread, "liquidity": liquidity}
        conn.execute("INSERT OR REPLACE INTO prospective_external_closings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (event_key, provider, source_market_id, captured_at, definition_version,
                      probability_a, decimal_odds_a, decimal_odds_b, max_spread, liquidity,
                      _hash(payload), "VALID"))
        conn.commit()

    def evaluate_pre_post_veto(self, conn: sqlite3.Connection, *, strategy_version: str,
                               closing_provider: str,
                               closing_definition_version: str) -> dict[str, Any]:
        """Evaluate only matured, prospectively frozen rows against an external close."""
        self._assert_open()
        rows = conn.execute("""SELECT e.event_key,e.team_a,r.winner,
            pre.probability_a,post.probability_a,c.probability_a
          FROM prospective_events e
          JOIN prospective_results r ON r.event_key=e.event_key AND r.validation_status='RESULT_VALIDATED'
          JOIN prospective_forecasts pre ON pre.event_key=e.event_key AND pre.stage='PRE_VETO'
          JOIN prospective_forecasts post ON post.event_key=e.event_key AND post.stage='POST_VETO'
          JOIN prospective_external_closings c ON c.event_key=e.event_key
             AND c.provider=? AND c.definition_version=? AND c.status='VALID'
          ORDER BY e.event_key""", (closing_provider, closing_definition_version)).fetchall()
        scored = [{"event_key": key, "outcome": int(winner == team_a),
                   "pre_probability": pre, "post_probability": post,
                   "closing_probability": closing}
                  for key, team_a, winner, pre, post, closing in rows]
        decisions = conn.execute("""SELECT d.selection,d.filled_stake,d.effective_decimal_odds,
            d.payload_json,e.team_a,r.winner,c.decimal_odds_a,c.decimal_odds_b
          FROM prospective_shadow_decisions d
          JOIN prospective_events e ON e.event_key=d.event_key
          JOIN prospective_results r ON r.event_key=d.event_key AND r.validation_status='RESULT_VALIDATED'
          JOIN prospective_external_closings c ON c.event_key=d.event_key
             AND c.provider=? AND c.definition_version=? AND c.status='VALID'
          WHERE d.strategy_version=? AND d.decision='BET' AND d.capital_allowed=0
          ORDER BY d.decision_id""",
                                 (closing_provider, closing_definition_version,
                                  strategy_version)).fetchall()
        total_staked = pnl = clv_sum = 0.0
        for selection, stake, entry_odds, payload_json, team_a, winner, close_a, close_b in decisions:
            payload = json.loads(payload_json)
            fee = float(payload["strategy"]["fee_rate"])
            won = selection == winner
            pnl += stake * (entry_odds - 1) * (1 - fee) if won else -stake
            total_staked += stake
            closing_odds = close_a if selection == team_a else close_b
            clv_sum += math.log(entry_odds / closing_odds)
        pre_metrics = probability_metrics(scored, "pre_probability")
        post_metrics = probability_metrics(scored, "post_probability")
        return {
            "strategy_version": strategy_version,
            "closing_provider": closing_provider,
            "closing_definition_version": closing_definition_version,
            "pre_veto": pre_metrics, "post_veto": post_metrics,
            "brier_improvement": (None if not scored else
                                  pre_metrics["brier"] - post_metrics["brier"]),
            "log_loss_improvement": (None if not scored else
                                     pre_metrics["log_loss"] - post_metrics["log_loss"]),
            "economic": {"settled_bets": len(decisions), "total_staked": total_staked,
                         "pnl": pnl, "roi_on_staked": (pnl / total_staked
                                                        if total_staked else None),
                         "mean_log_clv": (clv_sum / len(decisions) if decisions else None),
                         "clv_available": bool(decisions)},
            "capital_allowed": False,
        }

    def record_result(self, conn: sqlite3.Connection, *, event_key: str, winner: str, score: dict,
                      result_source: str, result_available_at: str) -> None:
        self._assert_open()
        event = conn.execute("SELECT team_a,team_b,match_start_at,mapping_status FROM prospective_events WHERE event_key=?", (event_key,)).fetchone()
        if not event: raise ContractError("evento prospectivo desconhecido")
        a, b, start, mapping = event
        if mapping not in ACCEPTED_MAPPING: raise ContractError("resultado sem mapping aceito")
        if winner not in {a, b} or not isinstance(score, dict): raise ContractError("resultado/ganhador inválido")
        if datetime.fromisoformat(result_available_at.replace("Z", "+00:00")) < datetime.fromisoformat(start.replace("Z", "+00:00")): raise ContractError("resultado disponível antes do evento")
        payload = {"winner": winner, "score": score, "source": result_source, "available": result_available_at}
        conn.execute("INSERT OR REPLACE INTO prospective_results VALUES(?,?,?,?,?,?,?)", (event_key, winner, json.dumps(score, sort_keys=True), result_source, result_available_at, _hash(payload), "RESULT_VALIDATED"))
        conn.execute("UPDATE prospective_events SET event_state='RESULT_VALIDATED' WHERE event_key=?", (event_key,)); conn.commit()

    def settle(self, conn: sqlite3.Connection, *, event_key: str) -> str:
        self._assert_open()
        event = conn.execute("SELECT team_a,match_start_at,mapping_status FROM prospective_events WHERE event_key=?", (event_key,)).fetchone()
        if not event: raise ContractError("evento prospectivo desconhecido")
        a, start, mapping = event
        if mapping not in ACCEPTED_MAPPING: return "REJECTED"
        result = conn.execute("SELECT winner,validation_status FROM prospective_results WHERE event_key=?", (event_key,)).fetchone()
        if not result or result[1] != "RESULT_VALIDATED":
            conn.execute("UPDATE prospective_events SET event_state='RESULT_PENDING' WHERE event_key=?", (event_key,)); conn.commit(); return "RESULT_PENDING"
        closing = conn.execute("SELECT quote_id,captured_at,probability_a FROM prospective_quotes WHERE event_key=? AND captured_at<? AND data_quality_status='ELIGIBLE' ORDER BY captured_at DESC LIMIT 1", (event_key, start)).fetchone()
        if not closing:
            conn.execute("UPDATE prospective_events SET event_state='CLOSING_PENDING' WHERE event_key=?", (event_key,)); conn.commit(); return "CLOSING_PENDING"
        quote_id, captured, market_p = closing
        model = conn.execute("SELECT model_probability_a FROM prospective_quotes WHERE event_key=? ORDER BY captured_at ASC LIMIT 1", (event_key,)).fetchone()
        if model is None: return "MODEL_FROZEN_VALUE_MISSING"
        outcome_a = int(result[0] == a)
        closing_payload = {"event_key": event_key, "quote_id": quote_id, "captured_at": captured,
                           "definition": "last-valid-pre-event/1"}
        conn.execute("INSERT OR REPLACE INTO prospective_closings VALUES(?,?,?,?,?,?)",
                     (event_key, quote_id, captured, "last-valid-pre-event/1", _hash(closing_payload), "VALID"))
        settlement_payload = {"event_key": event_key, "outcome_a": outcome_a, "model": model[0],
                              "market": market_p, "closing_quote_id": quote_id}
        conn.execute("INSERT OR REPLACE INTO prospective_settlements VALUES(?,?,?,?,?,?,?,?)",
                     (event_key, outcome_a, model[0], market_p, quote_id,
                      datetime.now(UTC).isoformat(timespec="seconds"), _hash(settlement_payload), "MATURED"))
        conn.execute("UPDATE prospective_events SET event_state='MATURED' WHERE event_key=?", (event_key,))
        conn.commit(); return "MATURED"

    def status(self, conn: sqlite3.Connection, *, now: datetime | None = None) -> dict[str, Any]:
        self._assert_open()
        now = now or datetime.now(UTC)
        rows = conn.execute("SELECT event_state,mapping_status,match_start_at FROM prospective_events").fetchall()
        counts = {state: 0 for state in EVENT_STATES}
        for state, mapping, start in rows:
            if mapping not in ACCEPTED_MAPPING: counts["REJECTED"] += 1
            elif datetime.fromisoformat(start.replace("Z", "+00:00")) < now and state == "PRE_EVENT": counts["EVENT_TIME_PASSED"] += 1
            else: counts[state] = counts.get(state, 0) + 1
        matured = conn.execute("SELECT count(*) FROM prospective_settlements WHERE settlement_status='MATURED'").fetchone()[0]
        first = conn.execute("""SELECT min(q.captured_at) FROM prospective_quotes q
                                JOIN prospective_events e ON e.event_key=q.event_key
                                WHERE e.mapping_status IN ('EXACT','RULE_BASED','MANUAL_CONFIRMED')""").fetchone()[0]
        days = 0 if not first else max(0, (now - datetime.fromisoformat(first.replace("Z", "+00:00"))).days)
        ambiguous = conn.execute("SELECT count(*) FROM prospective_events WHERE mapping_status='AMBIGUOUS'").fetchone()[0]
        hypothesis_ready = conn.execute("""SELECT count(*) FROM prospective_events e
            WHERE EXISTS (SELECT 1 FROM prospective_forecasts f WHERE f.event_key=e.event_key AND f.stage='PRE_VETO')
              AND EXISTS (SELECT 1 FROM prospective_forecasts f WHERE f.event_key=e.event_key AND f.stage='POST_VETO'
                          AND f.roster_snapshot_a_id IS NOT NULL AND f.roster_snapshot_b_id IS NOT NULL)
              AND EXISTS (SELECT 1 FROM prospective_veto_actions v WHERE v.event_key=e.event_key)
              AND EXISTS (SELECT 1 FROM prospective_quote_stages q WHERE q.event_key=e.event_key AND q.stage='PRE_VETO')
              AND EXISTS (SELECT 1 FROM prospective_quote_stages q WHERE q.event_key=e.event_key AND q.stage='POST_VETO')
              AND EXISTS (SELECT 1 FROM prospective_external_closings c WHERE c.event_key=e.event_key AND c.status='VALID')""").fetchone()[0]
        return {"states": counts, "matured_matches": matured, "required_matured_matches": 50,
                "calendar_days": days, "required_calendar_days": 30,
                "accepted_mappings": sum(1 for _state, mapping, _start in rows if mapping in ACCEPTED_MAPPING),
                "rejected_legacy_mappings": counts["REJECTED"], "ambiguous_mappings": ambiguous,
                "decision_ready": matured >= 50 and days >= 30 and ambiguous == 0,
                "pre_post_veto_hypothesis_ready_matches": hypothesis_ready,
                "verdict": "PENDING_SETTLEMENT" if matured < 50 else "READY_FOR_BLINDED_EVALUATION",
                # Honestidade metodológica: o settlement usa a última cotação Polymarket
                # antes do início (`closing_definition_version="last-valid-pre-event/1"`),
                # não uma closing line externa/independente e líquida. Brier/log-loss
                # contra essa referência são válidos; CLV verdadeiro não é.
                "clv_available": False,
                "market_reference_definition": "last-valid-pre-event/1 (última cotação "
                "Polymarket antes do início; não é closing line externa/independente)"}
