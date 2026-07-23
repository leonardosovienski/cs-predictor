"""Migração e lifecycle auditável da coorte prospectiva de mercado CS.

O módulo deliberadamente não adivinha match IDs, rosters ou resultados. Linhas
sem os dados necessários ficam REJECTED/PARTIAL e nunca entram no settlement.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .market_db import ContractError, canonical_event_id
from .beyond_market_closure import assert_beyond_market_open, is_production_market_db
from .config import identity_key

ACCEPTED_MAPPING = {"EXACT", "RULE_BASED", "MANUAL_CONFIRMED"}
EVENT_STATES = {"PRE_EVENT", "EVENT_TIME_PASSED", "RESULT_PENDING", "RESULT_VALIDATED",
                "CLOSING_PENDING", "SETTLEMENT_READY", "MATURED", "VOID", "REJECTED"}


def _iso(ts: int | None, date: str) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


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
                 (migration_id, datetime.now(timezone.utc).isoformat(timespec="seconds"), len(rows),
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
  ingestion_batch_id TEXT NOT NULL, provenance_hash TEXT NOT NULL, data_quality_status TEXT NOT NULL
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
"""


class ProspectiveStore:
    def __init__(self, path: str | Path): self.path = Path(path)
    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path); c.execute("PRAGMA journal_mode=WAL"); c.execute("PRAGMA busy_timeout=5000")
        c.executescript(PROSPECTIVE_SCHEMA); return c

    def _assert_open(self) -> None:
        if is_production_market_db(self.path):
            assert_beyond_market_open()

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
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                state = "PRE_EVENT" if start > datetime.now(start.tzinfo) else "EVENT_TIME_PASSED"
                # Uma cotação nova pode enriquecer um mercado que entrou antes
                # da evolução do schema. Não preservamos REJECTED legado quando
                # a mesma fonte passa a fornecer event_id e competição.
                conn.execute("""INSERT OR REPLACE INTO prospective_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (event_key, provider, source_event_id, str(row["market_id"]), canonical, row["scheduled_at"],
                              row["team_a"], row["team_b"], a_id, b_id, row["format"], comp_id, competition,
                              mapping_status, confidence, "mapping/1", reason, now, state))
                quality = "ELIGIBLE" if mapping_status in ACCEPTED_MAPPING else "REJECTED_MAPPING"
                conn.execute("""INSERT OR IGNORE INTO prospective_quotes VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (row["quote_id"], event_key, provider, str(row["market_id"]), row["observed_at"],
                              provider if row.get("source_kind") == "prediction_market" else None, "moneyline", "series",
                              row.get("decimal_a"), row.get("decimal_b"), row.get("probability_a"), row.get("probability_b"),
                              row.get("max_spread"), row["model_probability_a"], row["model_probability_b"],
                              row["ratings_sha256"], batch_id, _hash(row), quality))
                counts["imported"] += 1
            except (ContractError, ValueError, TypeError): counts["invalid"] += 1
        conn.commit(); return counts

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
                      datetime.now(timezone.utc).isoformat(timespec="seconds"), _hash(settlement_payload), "MATURED"))
        conn.execute("UPDATE prospective_events SET event_state='MATURED' WHERE event_key=?", (event_key,))
        conn.commit(); return "MATURED"

    def status(self, conn: sqlite3.Connection, *, now: datetime | None = None) -> dict[str, Any]:
        self._assert_open()
        now = now or datetime.now(timezone.utc)
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
        return {"states": counts, "matured_matches": matured, "required_matured_matches": 50,
                "calendar_days": days, "required_calendar_days": 30,
                "accepted_mappings": sum(1 for _state, mapping, _start in rows if mapping in ACCEPTED_MAPPING),
                "rejected_legacy_mappings": counts["REJECTED"], "ambiguous_mappings": ambiguous,
                "decision_ready": matured >= 50 and days >= 30 and ambiguous == 0,
                "verdict": "PENDING_SETTLEMENT" if matured < 50 else "READY_FOR_BLINDED_EVALUATION"}
