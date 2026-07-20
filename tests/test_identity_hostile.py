"""Testes hostis de identidade — entidades distintas que diferem só pela caixa.

O HLTV tem organizações realmente diferentes cujos nomes colidem em
case-insensitive (na base real: LEO/Leo, CHAOS/Chaos, WINNERS/Winners).
Resolver silenciosamente para a primeira entidade do dict seria falso
positivo; o contrato é: caixa exata resolve, caixa divergente ambígua rejeita.
"""
import json

import pytest

from src.model import EloModel


@pytest.fixture()
def model(tmp_path):
    ratings = {"LEO": 1327.4, "Leo": 1462.0, "Imperial Female": 1380.0,
               "9INE": 1410.0}
    path = tmp_path / "ratings.json"
    path.write_text(json.dumps(ratings), encoding="utf-8")
    return EloModel(ratings_file=path)


def test_case_sensitive_exact_wins_over_dict_order(model):
    assert model._elo("LEO") == ("LEO", 1327.4)
    assert model._elo("Leo") == ("Leo", 1462.0)
    assert model._elo(" Leo ") == ("Leo", 1462.0)


def test_case_insensitive_ambiguous_is_rejected(model):
    with pytest.raises(ValueError, match="ambíguo"):
        model._elo("leo")
    with pytest.raises(ValueError, match="ambíguo"):
        model._elo("LEo")


def test_case_insensitive_unique_still_resolves(model):
    assert model._elo("9ine") == ("9INE", 1410.0)


def test_unique_substring_still_resolves_and_unknown_rejects(model):
    assert model._elo("Imperial Fem")[0] == "Imperial Female"
    with pytest.raises(ValueError, match="desconhecido"):
        model._elo("time-que-nao-existe")


def test_predict_match_propagates_ambiguity(model):
    with pytest.raises(ValueError, match="ambíguo"):
        model.predict_match("leo", "9INE")


def test_snapshot_resolve_prefers_exact_case(tmp_path):
    from src.cs_snapshots import SnapshotError, _resolve
    ratings = {"LEO": 1327.4, "Leo": 1462.0}
    path = tmp_path / "ratings.json"
    path.write_text(json.dumps(ratings), encoding="utf-8")
    model = EloModel(ratings_file=path)
    assert _resolve(model, "Leo")["canonical"] == "Leo"
    assert _resolve(model, "LEO")["canonical"] == "LEO"
    assert _resolve(model, "Leo")["confidence"] == "RATINGS_EXACT"
    with pytest.raises(SnapshotError, match="ambíguo"):
        _resolve(model, "leo")


def test_snapshot_rejects_convenience_substring(model):
    from src.cs_snapshots import SnapshotError, _resolve
    with pytest.raises(SnapshotError, match="ambíguo ou ausente"):
        _resolve(model, "Vital")


@pytest.mark.parametrize("left,right", [
    ("LEO", "Leo"), ("CHAOS", "Chaos"), ("WINNERS", "Winners"),
])
def test_all_production_case_collisions_are_distinct(tmp_path, left, right):
    # Fixture versionada: a suíte não depende do ratings.json gitignored.
    path = tmp_path / "ratings.json"
    path.write_text(json.dumps({left: 1400, right: 1500}), encoding="utf-8")
    model = EloModel(ratings_file=path)
    assert model._elo(left)[0] == left
    assert model._elo(right)[0] == right
    with pytest.raises(ValueError, match="ambíguo"):
        model._elo(left.swapcase())
