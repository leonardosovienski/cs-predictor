"""Trava auditável para uma coorte prospectiva Beyond Market encerrada."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLOSURE_RECORD = ROOT / "docs" / "records" / "beyond_market_closure.json"


class BeyondMarketClosedError(RuntimeError):
    """A coorte foi encerrada por decisão humana e não pode ser mutada."""


def closure_record(path: Path | None = None) -> dict | None:
    """Devolve somente um registro de encerramento humano válido.

    Arquivo ilegível ou com outro status não reabre a coorte: falha fechada.
    """
    record_path = Path(path or DEFAULT_CLOSURE_RECORD)
    if not record_path.exists():
        raise BeyondMarketClosedError(
            "registro de decisao humana ausente; a coorte nao pode ser reaberta por remocao de arquivo"
        )
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BeyondMarketClosedError(f"registro de encerramento ilegível: {record_path}") from exc
    status = record.get("scientific_status")
    if status != "CLOSED_BY_HUMAN_DECISION":
        raise BeyondMarketClosedError(f"registro de encerramento inválido: {record_path}")
    return record


def assert_beyond_market_open(path: Path | None = None) -> None:
    record = closure_record(path)
    if record:
        raise BeyondMarketClosedError(
            "Beyond Market CLOSED_BY_HUMAN_DECISION; COLLECTION_ONLY e obrigatorio"
        )


def is_production_market_db(path: Path) -> bool:
    return Path(path).resolve() == (ROOT / "data" / "market.db").resolve()


def assert_beyond_market_open_for_root(project_root: Path) -> None:
    """Protege os entrypoints reais sem bloquear fixtures em diretórios temporários."""
    if Path(project_root).resolve() == ROOT.resolve():
        assert_beyond_market_open()


def market_shadow_status() -> dict[str, str | bool]:
    """Immutable governance status; accepts no configuration or environment override."""
    record = closure_record()
    return {
        "scientific_status": record["scientific_status"],
        "operational_status": record["operational_status"],
        "collection_only": True,
        "trading": False,
        "capital_real": False,
    }


def reject_market_shadow_operation(*_args, **_kwargs) -> None:
    raise BeyondMarketClosedError(
        "market shadow is CLOSED_BY_HUMAN_DECISION and has no operational runtime"
    )
