"""Trava auditável do Beyond Market — testes de MECANISMO, não de estado ambiente.

Antes de 2026-07-25 estes testes liam o registro de produção e afirmavam que ele
bloqueava tudo. Isso acoplava a suíte ao estado científico corrente: reabrir a
coorte por decisão humana (o caminho que o próprio módulo sanciona em
`REOPENED_BY_HUMAN_DECISION`) derrubava os testes sem que nenhuma garantia
tivesse sido perdida.

Agora cada garantia é exercida com registro de fixture, e o registro de produção
é verificado só quanto ao que precisa valer SEMPRE: ser válido e nunca autorizar
capital real.
"""
import json
from pathlib import Path

import pytest

from src import beyond_market_closure as bmc
from src.beyond_market_closure import (
    BeyondMarketClosedError, assert_beyond_market_open, closure_record,
)
from src.prospective_market import ProspectiveStore
import src.prospective_market as prospective_market


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_RECORD = ROOT / "docs" / "records" / "beyond_market_closure.json"

_CLOSED = {
    "schema_version": "cs-beyond-market-closure/1.0",
    "scientific_status": "CLOSED_BY_HUMAN_DECISION",
    "operational_status": "NO_GO",
    "closed_at_utc": "2026-01-01T00:00:00Z",
    "human_decision": {"reason": "fixture"},
}
_REOPENED = {
    **_CLOSED,
    "scientific_status": "REOPENED_BY_HUMAN_DECISION",
    "reopened_at_utc": "2026-01-02T00:00:00Z",
    "reopening_decision": {"reason": "fixture"},
    "supersedes_commit": "0" * 40,
}


def _write(path: Path, record: dict) -> Path:
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_registro_encerrado_bloqueia(tmp_path):
    closed = _write(tmp_path / "closed.json", _CLOSED)
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open(closed)


def test_reabertura_exige_os_tres_campos_de_decisao(tmp_path):
    """Declarar REOPENED sem a decisão auditável não reabre nada."""
    for faltando in ("reopened_at_utc", "reopening_decision", "supersedes_commit"):
        incompleto = {k: v for k, v in _REOPENED.items() if k != faltando}
        path = _write(tmp_path / f"sem_{faltando}.json", incompleto)
        with pytest.raises(BeyondMarketClosedError):
            closure_record(path)


def test_reabertura_completa_continua_bloqueada(tmp_path):
    reopened = _write(tmp_path / "reopened.json", _REOPENED)
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open(reopened)


def test_status_desconhecido_falha_fechado(tmp_path):
    estranho = _write(tmp_path / "estranho.json", {**_CLOSED, "scientific_status": "ABERTO"})
    with pytest.raises(BeyondMarketClosedError):
        closure_record(estranho)


def test_registro_ilegivel_falha_fechado(tmp_path):
    corrompido = tmp_path / "corrompido.json"
    corrompido.write_text("{nao e json", encoding="utf-8")
    with pytest.raises(BeyondMarketClosedError):
        closure_record(corrompido)


def test_remover_o_registro_nao_reabre_a_coorte(tmp_path, monkeypatch):
    """A garantia central: apagar o arquivo falha FECHADO, nunca aberto."""
    monkeypatch.setattr(bmc, "DEFAULT_CLOSURE_RECORD", tmp_path / "inexistente.json")
    with pytest.raises(BeyondMarketClosedError):
        closure_record()
    with pytest.raises(BeyondMarketClosedError):
        assert_beyond_market_open()


def test_store_de_producao_respeita_o_registro_default(tmp_path, monkeypatch):
    monkeypatch.setattr(bmc, "DEFAULT_CLOSURE_RECORD",
                        _write(tmp_path / "closed.json", _CLOSED))
    monkeypatch.setattr(prospective_market, "is_production_market_db", lambda _p: True)
    store = ProspectiveStore(tmp_path / "market.db")
    with pytest.raises(BeyondMarketClosedError):
        store.connect()


def test_registro_de_producao_e_valido_e_nunca_libera_capital():
    """Invariante que vale em QUALQUER estado científico, aberto ou fechado."""
    record = json.loads(PRODUCTION_RECORD.read_text(encoding="utf-8"))
    assert record["scientific_status"] == "CLOSED_BY_HUMAN_DECISION"
    assert record["operational_status"] == "NO_GO"
    closure_record()  # registro de produção é aceito pelo contrato
