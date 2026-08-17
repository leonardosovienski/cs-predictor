"""Contratos locais para separar dados esportivos de preços de mercado.

Este módulo não envia ordens.  O Market DB guarda somente observações que
possuem origem, instante e escopo verificáveis; o resultado máximo de sua
avaliação é habilitar nova coleta *shadow* prospectiva.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .beyond_market_closure import (
    assert_beyond_market_open,
    assert_market_shadow_collection_open,
    is_production_market_db,
    is_shadow_market_db,
)

CANONICALIZATION_VERSION = "cs-event/1"
MAPPING_STATUSES = {"EXACT", "RULE_BASED", "MANUAL_CONFIRMED", "AMBIGUOUS", "REJECTED"}
SERIES_FORMATS = {"bo1", "bo3", "bo5"}


class ContractError(ValueError):
    pass


def _utc(value: str | datetime, field: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{field} inválido") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"{field} exige timezone")
    return parsed.astimezone(UTC)


def _finite(value: Any, field: str) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} inválido") from exc
    if not math.isfinite(value):
        raise ContractError(f"{field} não-finito")
    return value


def _hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def canonical_event_id(*, team_a_id: str, team_b_id: str, match_start_at: str | datetime,
                       series_format: str, competition_id: str, market_scope: str = "series",
                       canonicalization_version: str = CANONICALIZATION_VERSION) -> str:
    """ID determinístico, versionado e independente do provedor.

    O horário é arredondado ao minuto, mas competição, formato, escopo e os IDs
    de entidade são obrigatórios; portanto nunca é apenas data+nomenclatura.
    """
    if series_format.lower() not in SERIES_FORMATS or market_scope != "series":
        raise ContractError("formato ou escopo canônico inválido")
    if not all(isinstance(x, str) and x.strip() for x in (team_a_id, team_b_id, competition_id, canonicalization_version)):
        raise ContractError("identidade/competição/versão ausente")
    if team_a_id == team_b_id:
        raise ContractError("evento canônico com o mesmo time nos dois lados")
    start = _utc(match_start_at, "match_start_at").replace(second=0, microsecond=0).isoformat()
    payload = {"v": canonicalization_version, "teams": sorted((team_a_id, team_b_id)),
               "start": start, "format": series_format.lower(),
               "competition": competition_id.strip(), "scope": market_scope}
    return "cse_" + _hash(payload)[:32]


@dataclass(frozen=True)
class SportsSeries:
    source_event_id: str
    source: str
    match_start_at: str
    team_a_id: str
    team_b_id: str
    series_format: str
    competition_id: str
    roster_snapshot_id: str | None
    result_available_at: str
    ingestion_batch_id: str
    provenance_hash: str

    def validate(self) -> None:
        if not all(isinstance(getattr(self, key), str) and getattr(self, key).strip()
                   for key in ("source_event_id", "source", "team_a_id", "team_b_id",
                               "competition_id", "ingestion_batch_id", "provenance_hash")):
            raise ContractError("Sports DB exige identidade, fonte, lote e proveniência")
        if self.team_a_id == self.team_b_id or self.series_format.lower() not in SERIES_FORMATS:
            raise ContractError("série esportiva inválida")
        if _utc(self.result_available_at, "result_available_at") < _utc(self.match_start_at, "match_start_at"):
            raise ContractError("resultado disponível antes do evento")
        if len(self.provenance_hash) != 64:
            raise ContractError("provenance_hash inválido")


@dataclass(frozen=True)
class MarketQuote:
    provider: str
    source_market_id: str
    captured_at: str
    bookmaker: str
    market_type: str
    market_scope: str
    selection: str
    decimal_odds: float
    implied_probability_raw: float
    implied_probability_normalized: float
    is_closing: bool
    closing_definition_version: str
    ingestion_batch_id: str
    provenance_hash: str
    max_spread: float | None = None
    liquidity: float | None = None

    def validate(self, *, match_start_at: str | datetime | None = None) -> None:
        if not all(isinstance(getattr(self, key), str) and getattr(self, key).strip()
                   for key in ("provider", "source_market_id", "bookmaker", "market_type",
                               "market_scope", "selection", "closing_definition_version",
                               "ingestion_batch_id", "provenance_hash")):
            raise ContractError("Market DB exige provedor, bookmaker, lote e proveniência")
        if self.market_scope != "series" or self.market_type != "moneyline":
            raise ContractError("apenas moneyline de série é comparável")
        odds = _finite(self.decimal_odds, "decimal_odds")
        raw = _finite(self.implied_probability_raw, "implied_probability_raw")
        normalized = _finite(self.implied_probability_normalized, "implied_probability_normalized")
        if odds <= 1 or not 0 < raw < 1 or not 0 < normalized < 1:
            raise ContractError("odds/probabilidade de mercado inválida")
        if self.max_spread is not None and not 0 <= _finite(self.max_spread, "max_spread") <= 1:
            raise ContractError("max_spread inválido")
        if self.liquidity is not None and _finite(self.liquidity, "liquidity") < 0:
            raise ContractError("liquidity inválida")
        captured = _utc(self.captured_at, "captured_at")
        if match_start_at is not None and captured >= _utc(match_start_at, "match_start_at"):
            raise ContractError("closing/cotação depois do evento")
        if len(self.provenance_hash) != 64:
            raise ContractError("provenance_hash inválido")


@dataclass(frozen=True)
class EventMapping:
    canonical_event_id: str
    canonicalization_version: str
    source_event_id: str
    provider: str
    match_start_at: str
    team_a_id: str
    team_b_id: str
    series_format: str
    competition_id: str
    market_scope: str
    mapping_status: str
    mapping_confidence: float
    mapping_reviewed_at: str
    mapping_rule_version: str

    def validate(self) -> None:
        expected = canonical_event_id(team_a_id=self.team_a_id, team_b_id=self.team_b_id,
                                      match_start_at=self.match_start_at, series_format=self.series_format,
                                      competition_id=self.competition_id, market_scope=self.market_scope,
                                      canonicalization_version=self.canonicalization_version)
        if self.canonical_event_id != expected:
            raise ContractError("canonical_event_id não reproduzível")
        if self.mapping_status not in MAPPING_STATUSES:
            raise ContractError("mapping_status inválido")
        confidence = _finite(self.mapping_confidence, "mapping_confidence")
        if not 0 <= confidence <= 1:
            raise ContractError("mapping_confidence inválida")
        if self.mapping_status in {"AMBIGUOUS", "REJECTED"} and confidence >= 1:
            raise ContractError("mapeamento não-confirmado não pode ter confiança 1")
        _utc(self.mapping_reviewed_at, "mapping_reviewed_at")


MARKET_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_batches (
  ingestion_batch_id TEXT PRIMARY KEY, source TEXT NOT NULL, created_at TEXT NOT NULL,
  raw_sha256 TEXT NOT NULL, license_note TEXT NOT NULL, quality_class TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canonical_event_mappings (
  provider TEXT NOT NULL, source_event_id TEXT NOT NULL, canonical_event_id TEXT NOT NULL,
  canonicalization_version TEXT NOT NULL, match_start_at TEXT NOT NULL, team_a_id TEXT NOT NULL,
  team_b_id TEXT NOT NULL, series_format TEXT NOT NULL, competition_id TEXT NOT NULL,
  market_scope TEXT NOT NULL, mapping_status TEXT NOT NULL, mapping_confidence REAL NOT NULL,
  mapping_reviewed_at TEXT NOT NULL, mapping_rule_version TEXT NOT NULL,
  PRIMARY KEY(provider, source_event_id)
);
CREATE TABLE IF NOT EXISTS market_quotes (
  provider TEXT NOT NULL, source_market_id TEXT NOT NULL, canonical_event_id TEXT NOT NULL,
  captured_at TEXT NOT NULL, bookmaker TEXT NOT NULL, market_type TEXT NOT NULL,
  market_scope TEXT NOT NULL, selection TEXT NOT NULL, decimal_odds REAL NOT NULL,
  implied_probability_raw REAL NOT NULL, implied_probability_normalized REAL NOT NULL,
  is_closing INTEGER NOT NULL, closing_definition_version TEXT NOT NULL,
  ingestion_batch_id TEXT NOT NULL, provenance_hash TEXT NOT NULL,
  max_spread REAL, liquidity REAL,
  PRIMARY KEY(provider, source_market_id, selection, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_market_quotes_event ON market_quotes(canonical_event_id, captured_at);
-- Schema reservado para roster point-in-time; NENHUM ingestor popula esta
-- tabela hoje (2026-08-14). `roster_snapshot_id` em `SportsSeries` e nas
-- linhas prospectivas fica sempre NULL até que exista um pipeline real de
-- captura de roster com timestamp (não confundir "coluna existe" com
-- "roster está implementado").
CREATE TABLE IF NOT EXISTS roster_snapshots (
  roster_snapshot_id TEXT PRIMARY KEY, team_id TEXT NOT NULL, known_at TEXT NOT NULL,
  source TEXT NOT NULL, players_json TEXT NOT NULL, provenance_hash TEXT NOT NULL
);
"""


class MarketDB:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        # Dois portões independentes: o Market DB de produção permanece
        # incondicionalmente bloqueado (capital); o Market DB shadow exige a
        # decisão de reabertura shadow-only, e nunca autoriza capital.
        if is_production_market_db(self.path):
            assert_beyond_market_open()
        if is_shadow_market_db(self.path):
            assert_market_shadow_collection_open()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(MARKET_SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(market_quotes)")}
        if "max_spread" not in columns:
            conn.execute("ALTER TABLE market_quotes ADD COLUMN max_spread REAL")
        if "liquidity" not in columns:
            conn.execute("ALTER TABLE market_quotes ADD COLUMN liquidity REAL")
        conn.commit()
        return conn

    def insert_batch(self, conn: sqlite3.Connection, *, ingestion_batch_id: str, source: str,
                     raw_sha256: str, license_note: str, quality_class: str,
                     created_at: str | None = None) -> None:
        if not all(isinstance(v, str) and v.strip() for v in (ingestion_batch_id, source, raw_sha256, license_note, quality_class)) or len(raw_sha256) != 64:
            raise ContractError("lote de ingestão inválido")
        conn.execute("INSERT OR IGNORE INTO ingestion_batches VALUES(?,?,?,?,?,?)",
                     (ingestion_batch_id, source, created_at or datetime.now(UTC).isoformat(), raw_sha256, license_note, quality_class))
        conn.commit()

    def map_event(self, conn: sqlite3.Connection, mapping: EventMapping) -> None:
        mapping.validate()
        conn.execute("INSERT OR REPLACE INTO canonical_event_mappings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (mapping.provider, mapping.source_event_id, mapping.canonical_event_id,
                      mapping.canonicalization_version, mapping.match_start_at, mapping.team_a_id,
                      mapping.team_b_id, mapping.series_format, mapping.competition_id,
                      mapping.market_scope, mapping.mapping_status, mapping.mapping_confidence,
                      mapping.mapping_reviewed_at, mapping.mapping_rule_version))
        conn.commit()

    def insert_quote(self, conn: sqlite3.Connection, *, canonical_event_id: str,
                     quote: MarketQuote, match_start_at: str | datetime) -> None:
        quote.validate(match_start_at=match_start_at)
        mapping = conn.execute("SELECT mapping_status FROM canonical_event_mappings WHERE canonical_event_id=?",
                               (canonical_event_id,)).fetchone()
        if not mapping or mapping[0] not in {"EXACT", "RULE_BASED", "MANUAL_CONFIRMED"}:
            raise ContractError("cotação sem mapeamento canônico aceito")
        conn.execute("""INSERT OR IGNORE INTO market_quotes
                     (provider,source_market_id,canonical_event_id,captured_at,bookmaker,
                      market_type,market_scope,selection,decimal_odds,implied_probability_raw,
                      implied_probability_normalized,is_closing,closing_definition_version,
                      ingestion_batch_id,provenance_hash,max_spread,liquidity)
                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (quote.provider, quote.source_market_id, canonical_event_id, quote.captured_at,
                      quote.bookmaker, quote.market_type, quote.market_scope, quote.selection,
                      quote.decimal_odds, quote.implied_probability_raw,
                      quote.implied_probability_normalized, int(quote.is_closing),
                      quote.closing_definition_version, quote.ingestion_batch_id, quote.provenance_hash,
                      quote.max_spread, quote.liquidity))
        conn.commit()


def _logloss(probability: float, outcome: int) -> float:
    probability = min(max(probability, 1e-9), 1 - 1e-9)
    return -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))


def _metrics(rows: Iterable[dict[str, Any]], key: str) -> dict[str, float | None]:
    data = list(rows)
    if not data:
        return {"n": 0, "log_loss": None, "brier": None, "accuracy": None}
    probabilities = [_finite(row[key], key) for row in data]
    outcomes = [int(row["outcome"]) for row in data]
    if any(y not in (0, 1) for y in outcomes):
        raise ContractError("outcome binário inválido")
    return {"n": len(data), "log_loss": sum(_logloss(p, y) for p, y in zip(probabilities, outcomes)) / len(data),
            "brier": sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(data),
            "accuracy": sum((p >= .5) == bool(y) for p, y in zip(probabilities, outcomes)) / len(data)}


def beyond_market_validate(rows: list[dict[str, Any]], *, train_end_at: str | datetime,
                            minimum_test_rows: int = 30) -> dict[str, Any]:
    """Avalia mercado, modelo e combinação em uma janela posterior.

    O peso da combinação é escolhido exclusivamente no treino anterior, numa
    grade fixa; não há ajuste de hiperparâmetro na janela de teste.
    """
    cut = _utc(train_end_at, "train_end_at")
    parsed = []
    for row in rows:
        moment = _utc(row["captured_at"], "captured_at")
        if moment >= _utc(row["match_start_at"], "match_start_at"):
            raise ContractError("observação de mercado posterior ao evento")
        parsed.append({**row, "_at": moment})
    train, test = [r for r in parsed if r["_at"] < cut], [r for r in parsed if r["_at"] >= cut]
    if not train or len(test) < minimum_test_rows:
        return {"verdict": "INCONCLUSIVE", "reason": "janela train/test insuficiente",
                "train_n": len(train), "test_n": len(test), "counts_toward_financial_gate": False}
    weights = [i / 20 for i in range(21)]
    def loss(weight: float) -> float:
        return sum(_logloss(weight * _finite(r["model_probability"], "model_probability") +
                            (1 - weight) * _finite(r["market_probability"], "market_probability"), int(r["outcome"])) for r in train) / len(train)
    weight = min(weights, key=loss)
    projected = [{**r, "combined_probability": weight * _finite(r["model_probability"], "model_probability") +
                  (1 - weight) * _finite(r["market_probability"], "market_probability")} for r in test]
    market = _metrics(test, "market_probability")
    model = _metrics(test, "model_probability")
    combined = _metrics(projected, "combined_probability")
    delta = market["log_loss"] - combined["log_loss"]
    verdict = "GATE_PASSED_FOR_PROSPECTIVE_SHADOW" if delta is not None and delta > 0 else "NO_INFORMATION_EDGE"
    return {"verdict": verdict, "counts_toward_financial_gate": False,
            "train_n": len(train), "test_n": len(test), "blend_weight_model": weight,
            "market": market, "model": model, "market_plus_model": combined,
            "information_logloss_improvement": delta,
            "economic_gate": "NO-GO: sem CLV/ROI prospectivo maturado"}
