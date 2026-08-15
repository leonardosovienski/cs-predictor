"""Governança do Beyond Market: capital permanece fechado; shadow foi reaberto.

Até 2026-08-14 esta suíte também afirmava que NENHUMA superfície de mercado
existia no código ativo. Isso mudou por decisão humana explícita, registrada
em `docs/records/beyond_market_shadow_reopening.json`: a coleta e a
liquidação EM PAPEL foram reabertas para completar a amostra mínima definida
no próprio encerramento de 2026-07-23 (50 liquidações / 30 dias).

O que NUNCA mudou, e esta suíte continua a provar: capital real, `cs-settle`
financeiro e a produção `data/market.db` permanecem incondicionalmente
bloqueados, por um portão de código separado (`assert_beyond_market_open`)
que a reabertura shadow não toca.
"""

import hashlib
import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from src.betting import record_bet
from src.beyond_market_closure import (
    BeyondMarketClosedError,
    assert_beyond_market_open,
    assert_beyond_market_open_for_root,
    assert_market_shadow_collection_open,
    assert_market_shadow_collection_open_for_root,
    closure_record,
    is_production_market_db,
    is_shadow_market_db,
    market_shadow_status,
    reject_market_shadow_operation,
    shadow_reopening_record,
)
from src.cli import settle_main
from src.market_db import MarketDB
from src.plugin import CsPredictorPlugin
from src.prospective_market import ProspectiveStore
from src.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
CLOSURE_HASH = "8489268c9eedd5dc8783fda76174aa00304b4aa7bd1df312ded64da6554ae618"
EVIDENCE_HASHES = {
    "docs/evidence/market_shadow/src/prospective_market.py": "372881f33f4a475d85628e88b6e38d5e945fd470cad25a8dae58300703de3f72",
    "docs/evidence/market_shadow/scripts/install_market_shadow_task.ps1": "ab02d8b16f63eb03a3fad3020eba24b300569b4666374ccf875c7b3ccfc7adf4",
    "docs/evidence/market_shadow/tests/test_beyond_market_closure.py": "dadf0c7f378d2d1f2cdda485775161c59efc544bab3b386416eef983466a416c",
}

_REOPENED = {
    "schema_version": "cs-beyond-market-reopening/1.0",
    "scientific_status": "REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY",
    "operational_status": "SHADOW_ONLY_NO_CAPITAL",
    "reopened_at_utc": "2026-08-14T00:00:00Z",
    "reopening_decision": {"reason": "fixture"},
    "supersedes_commit": "0" * 40,
}


def _canonical_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _write(path: Path, record: dict) -> Path:
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_closure_is_immutable_and_fail_closed(tmp_path, monkeypatch):
    """O portão de CAPITAL nunca muda, com ou sem reabertura shadow."""
    assert market_shadow_status() == {
        "scientific_status": "CLOSED_BY_HUMAN_DECISION",
        "operational_status": "NO_GO",
        "collection_only": True,
        "trading": False,
        "capital_real": False,
    }
    for name in ("CS_MARKET_SHADOW", "CS_REOPEN_MARKET", "MARKET_SHADOW_ENABLED"):
        monkeypatch.setenv(name, "true")
    assert (
        Settings()
        .model_dump()
        .keys()
        .isdisjoint({"market_shadow", "reopen_market", "trading", "capital_real"})
    )
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open(tmp_path / "missing.json")
    with pytest.raises(BeyondMarketClosedError):
        reject_market_shadow_operation("direct-call", enabled=True)


def test_closure_and_historical_evidence_hashes_are_stable():
    closure = ROOT / "docs" / "records" / "beyond_market_closure.json"
    assert _canonical_sha256(closure) == CLOSURE_HASH
    assert closure_record()["human_decision"]["real_money"].endswith("bloqueada permanentemente.")
    for relative, expected in EVIDENCE_HASHES.items():
        assert _canonical_sha256(ROOT / relative) == expected


def test_capital_and_real_settlement_remain_permanently_blocked(tmp_path):
    """Independente de qualquer reabertura shadow, dinheiro real nunca sai daqui."""
    with pytest.raises(PermissionError):
        record_bet(
            selection="team_a",
            prob_model=0.6,
            decimal_odds=1.8,
            bankroll=1000,
            real=True,
            path=tmp_path / "bets.jsonl",
        )
    assert settle_main(["evt-1", "--result", "{}"]) == 2


def test_production_market_db_still_permanently_blocked(tmp_path, monkeypatch):
    """A reabertura shadow NUNCA libera a produção data/market.db."""
    monkeypatch.setattr(
        "src.market_db.is_production_market_db",
        lambda path: True,
    )
    with pytest.raises(BeyondMarketClosedError):
        MarketDB(tmp_path / "anything.db").connect()


def test_shadow_and_production_market_db_paths_are_distinct():
    assert is_production_market_db(ROOT / "data" / "market.db")
    assert not is_shadow_market_db(ROOT / "data" / "market.db")
    assert is_shadow_market_db(ROOT / "data" / "market_shadow.db")
    assert not is_production_market_db(ROOT / "data" / "market_shadow.db")


def test_shadow_reopening_requires_complete_decision(tmp_path):
    """Declarar REOPENED sem a decisão auditável completa não reabre nada."""
    for faltando in ("reopened_at_utc", "reopening_decision", "supersedes_commit"):
        incompleto = {k: v for k, v in _REOPENED.items() if k != faltando}
        path = _write(tmp_path / f"sem_{faltando}.json", incompleto)
        with pytest.raises(BeyondMarketClosedError):
            shadow_reopening_record(path)


def test_shadow_reopening_wrong_scope_fails_closed(tmp_path):
    errado = _write(tmp_path / "errado.json", {**_REOPENED, "operational_status": "GO_REAL_MONEY"})
    with pytest.raises(BeyondMarketClosedError):
        shadow_reopening_record(errado)


def test_shadow_collection_opens_only_with_valid_record(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.beyond_market_closure.DEFAULT_REOPENING_RECORD",
        _write(tmp_path / "reopened.json", _REOPENED),
    )
    assert_market_shadow_collection_open()  # não levanta


def test_removing_shadow_reopening_record_recloses_shadow(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "src.beyond_market_closure.DEFAULT_REOPENING_RECORD",
        tmp_path / "inexistente.json",
    )
    with pytest.raises(BeyondMarketClosedError):
        assert_market_shadow_collection_open()


def test_shadow_reopening_never_relaxes_the_capital_gate(tmp_path, monkeypatch):
    """Mesmo com reabertura shadow válida, assert_beyond_market_open() nunca abre."""
    monkeypatch.setattr(
        "src.beyond_market_closure.DEFAULT_REOPENING_RECORD",
        _write(tmp_path / "reopened.json", _REOPENED),
    )
    assert_market_shadow_collection_open()  # shadow: aberto
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open()  # capital: continua fechado


def test_market_surface_is_scoped_to_shadow_only():
    scripts = entry_points(group="console_scripts")
    assert not any("market" in item.name or "shadow" in item.name for item in scripts)
    plugin = CsPredictorPlugin()
    caps = plugin.capabilities()
    assert caps["trading"] is False
    assert caps["scientific_status"] == "CLOSED_BY_HUMAN_DECISION"
    assert caps["market_shadow_scientific_status"] == "REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY"
    assert not hasattr(plugin, "market_provider")
    assert (ROOT / "src" / "prospective_market.py").exists()
    assert (ROOT / "src" / "market_db.py").exists()
    # Migração one-shot já aplicada em 2026-07-22; não é reintroduzida.
    assert not (ROOT / "scripts" / "migrate_prospective_market.py").exists()
    # Task Scheduler legado (Windows) nunca volta; agendamento é só via predictor_ops.
    assert not (ROOT / "scripts" / "install_market_shadow_task.ps1").exists()
    jobs = json.loads((ROOT / "src" / "jobs.json").read_text(encoding="utf-8"))["jobs"]
    assert jobs[0]["id"] == "cs-archival-collection"
    shadow_jobs = [job for job in jobs if job["id"] != "cs-archival-collection"]
    assert shadow_jobs, "reabertura shadow deve declarar ao menos um job"
    for job in shadow_jobs:
        assert job["provenance"]["mode"] == "SHADOW_ONLY_NO_CAPITAL"
        assert job["scientific_state"] == "REOPENED_BY_HUMAN_DECISION_SHADOW_ONLY"
        assert (ROOT / job["command"][-1]).exists()


def test_no_script_defaults_to_the_production_market_db():
    for path in (ROOT / "scripts").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert '/ "market.db"' not in text
        assert 'MARKET_DB = ROOT / "data" / "market.db"' not in text


def test_prospective_store_on_shadow_db_requires_valid_reopening(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.prospective_market.is_shadow_market_db",
        lambda path: True,
    )
    monkeypatch.setattr(
        "src.beyond_market_closure.DEFAULT_REOPENING_RECORD",
        tmp_path / "inexistente.json",
    )
    with pytest.raises(BeyondMarketClosedError):
        ProspectiveStore(tmp_path / "shadow.db").connect()


# --- Ramos de falha fechada não exercidos até aqui: cada leitura de registro
# (encerramento ou reabertura) tem um caminho de arquivo ilegível, um de
# status incorreto e um de campo ausente. Todos devem falhar fechado.


def test_closure_record_unreadable_file_fails_closed(tmp_path):
    corrompido = tmp_path / "corrompido.json"
    corrompido.write_text("{nao e json", encoding="utf-8")
    with pytest.raises(BeyondMarketClosedError, match="ilegível"):
        closure_record(corrompido)


def test_closure_record_wrong_status_fails_closed(tmp_path):
    errado = tmp_path / "errado.json"
    errado.write_text(json.dumps({"scientific_status": "ABERTO"}), encoding="utf-8")
    with pytest.raises(BeyondMarketClosedError, match="inválido"):
        closure_record(errado)


def test_assert_beyond_market_open_for_root_blocks_the_real_checkout():
    """No checkout real (não um tmp_path de teste), o capital nunca abre."""
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open_for_root(ROOT)


def test_shadow_reopening_record_unreadable_file_fails_closed(tmp_path):
    corrompido = tmp_path / "corrompido.json"
    corrompido.write_text("{nao e json", encoding="utf-8")
    with pytest.raises(BeyondMarketClosedError, match="ilegível"):
        shadow_reopening_record(corrompido)


def test_shadow_reopening_record_wrong_status_fails_closed(tmp_path):
    errado = tmp_path / "errado.json"
    errado.write_text(json.dumps({"scientific_status": "ABERTO"}), encoding="utf-8")
    with pytest.raises(BeyondMarketClosedError, match="inválido"):
        shadow_reopening_record(errado)


def test_shadow_collection_blocked_when_closure_evidence_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.beyond_market_closure.DEFAULT_CLOSURE_RECORD",
        tmp_path / "inexistente.json",
    )
    with pytest.raises(BeyondMarketClosedError, match="evidência histórica"):
        assert_market_shadow_collection_open()


def test_shadow_collection_blocked_when_closure_evidence_unreadable(tmp_path, monkeypatch):
    corrompido = tmp_path / "corrompido.json"
    corrompido.write_text("{nao e json", encoding="utf-8")
    monkeypatch.setattr("src.beyond_market_closure.DEFAULT_CLOSURE_RECORD", corrompido)
    with pytest.raises(BeyondMarketClosedError, match="evidência histórica"):
        assert_market_shadow_collection_open()


def test_shadow_collection_blocked_when_closure_evidence_status_tampered(tmp_path, monkeypatch):
    """Se alguém editar o encerramento original pra mudar o status, o gate
    shadow bloqueia — não passa a confiar num registro adulterado."""
    adulterado = tmp_path / "adulterado.json"
    adulterado.write_text(
        json.dumps({"scientific_status": "REOPENED_BY_HUMAN_DECISION"}), encoding="utf-8"
    )
    monkeypatch.setattr("src.beyond_market_closure.DEFAULT_CLOSURE_RECORD", adulterado)
    with pytest.raises(BeyondMarketClosedError, match="alterada"):
        assert_market_shadow_collection_open()


def test_shadow_collection_open_for_root_succeeds_on_the_real_checkout():
    """Caminho feliz de produção: encerramento original íntegro + reabertura
    shadow válida presentes no checkout real abrem a coleta shadow."""
    assert_market_shadow_collection_open_for_root(ROOT)  # não levanta
