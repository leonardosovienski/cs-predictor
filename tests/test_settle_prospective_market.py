"""Liquidação da coorte prospectiva a partir do resultado oficial.

O ponto delicado é a ORIENTAÇÃO: o Sports DB registra a partida na ordem do
HLTV, que frequentemente é o inverso da ordem do evento de mercado. Errar isso
troca o vencedor silenciosamente e corrompe todo o settlement — por isso o caso
invertido tem teste próprio.
"""

import sqlite3

from scripts.settle_prospective_market import official_result


def _sports(tmp_path):
    conn = sqlite3.connect(tmp_path / "cs.db")
    conn.execute(
        "CREATE TABLE matches (match_id INTEGER PRIMARY KEY, date TEXT, ts INTEGER,"
        " team_a TEXT, team_b TEXT, score_a INTEGER, score_b INTEGER,"
        " format TEXT, event TEXT)"
    )
    return conn


def _add(conn, match_id, date, a, b, sa, sb):
    conn.execute(
        "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?)",
        (match_id, date, 0, a, b, sa, sb, "bo3", "evento"),
    )
    conn.commit()


def test_orientacao_direta(tmp_path):
    conn = _sports(tmp_path)
    _add(conn, 1, "2026-07-23", "Gentle Mates", "paiN", 0, 2)
    r = official_result(conn, "Gentle Mates", "paiN", "2026-07-23T15:00:00+00:00")
    assert r["winner"] == "paiN"
    assert r["score"] == {"team_a": 0, "team_b": 2}


def test_orientacao_invertida_normaliza_placar_e_vencedor(tmp_path):
    """Sports DB tem 'OG 1x2 Spirit'; o mercado é 'Spirit x OG'."""
    conn = _sports(tmp_path)
    _add(conn, 2, "2026-07-23", "OG", "Spirit", 1, 2)
    r = official_result(conn, "Spirit", "OG", "2026-07-23T17:00:00+00:00")
    assert r["winner"] == "Spirit"
    assert r["score"] == {"team_a": 2, "team_b": 1}


def test_invertida_com_vitoria_do_time_b(tmp_path):
    """Sports DB tem '3DMAX 2x1 magic'; o mercado é 'magic x 3DMAX'."""
    conn = _sports(tmp_path)
    _add(conn, 3, "2026-07-24", "3DMAX", "magic", 2, 1)
    r = official_result(conn, "magic", "3DMAX", "2026-07-24T09:00:00+00:00")
    assert r["winner"] == "3DMAX"
    assert r["score"] == {"team_a": 1, "team_b": 2}


def test_partida_ausente_nao_inventa_resultado(tmp_path):
    conn = _sports(tmp_path)
    assert official_result(conn, "A", "B", "2026-07-23T15:00:00+00:00") is None


def test_empate_nao_liquida(tmp_path):
    """BO2 pode empatar: sem vencedor, não se liquida."""
    conn = _sports(tmp_path)
    _add(conn, 4, "2026-07-23", "A", "B", 1, 1)
    assert official_result(conn, "A", "B", "2026-07-23T15:00:00+00:00") is None


def test_ambiguidade_falha_fechado(tmp_path):
    """Duas partidas do mesmo confronto na janela: ausência, nunca escolha."""
    conn = _sports(tmp_path)
    _add(conn, 5, "2026-07-23", "A", "B", 2, 0)
    _add(conn, 6, "2026-07-24", "B", "A", 2, 1)
    assert official_result(conn, "A", "B", "2026-07-23T15:00:00+00:00") is None


def test_janela_de_um_dia_cobre_virada_de_data(tmp_path):
    conn = _sports(tmp_path)
    _add(conn, 7, "2026-07-24", "A", "B", 2, 0)
    r = official_result(conn, "A", "B", "2026-07-23T23:00:00+00:00")
    assert r is not None and r["winner"] == "A"


def test_fora_da_janela_nao_casa(tmp_path):
    conn = _sports(tmp_path)
    _add(conn, 8, "2026-07-28", "A", "B", 2, 0)
    assert official_result(conn, "A", "B", "2026-07-23T15:00:00+00:00") is None


def test_caixa_diferente_resolve_quando_unica(tmp_path):
    """Sports DB tem 'HEROIC'; o mercado registrou 'Heroic'. Casefold único resolve."""
    conn = _sports(tmp_path)
    _add(conn, 9, "2026-07-23", "HEROIC", "FOKUS", 2, 0)
    r = official_result(conn, "Heroic", "FOKUS", "2026-07-23T16:00:00+00:00")
    assert r["winner"] == "Heroic"  # devolve a identidade DO MERCADO
    assert r["score"] == {"team_a": 2, "team_b": 0}


def test_caixa_diferente_invertida_preserva_orientacao(tmp_path):
    """'Nuclear TigeRES x Echo' no Sports DB, 'ECHO' no mercado, ordem invertida."""
    conn = _sports(tmp_path)
    _add(conn, 10, "2026-07-22", "Nuclear TigeRES", "Echo", 0, 2)
    r = official_result(conn, "ECHO", "Nuclear TigeRES", "2026-07-22T16:00:00+00:00")
    assert r["winner"] == "ECHO"
    assert r["score"] == {"team_a": 2, "team_b": 0}


def test_colisao_de_caixa_real_falha_fechado(tmp_path):
    """LEO/Leo e CHAOS/Chaos sao organizacoes DISTINTAS no HLTV.

    Com duas partidas na janela que so diferem pela caixa, casefold e' ambiguo:
    nao se escolhe uma — regressao do bug de identidade corrigido em 2026-07-19."""
    conn = _sports(tmp_path)
    _add(conn, 11, "2026-07-23", "LEO", "MOUZ", 2, 0)
    _add(conn, 12, "2026-07-23", "Leo", "mouz", 0, 2)
    assert official_result(conn, "leo", "Mouz", "2026-07-23T15:00:00+00:00") is None


def test_caixa_exata_tem_precedencia_sobre_casefold(tmp_path):
    """Havendo caixa exata, ela resolve mesmo com outra variante na janela."""
    conn = _sports(tmp_path)
    _add(conn, 13, "2026-07-23", "LEO", "MOUZ", 2, 0)
    _add(conn, 14, "2026-07-23", "Leo", "MOUZ", 0, 2)
    r = official_result(conn, "Leo", "MOUZ", "2026-07-23T15:00:00+00:00")
    assert r["winner"] == "MOUZ" and r["score"] == {"team_a": 0, "team_b": 2}


def test_main_matures_a_pending_shadow_event_end_to_end(tmp_path):
    """Cobertura de main(): do banco esportivo + banco shadow até MATURED."""
    from scripts import settle_prospective_market as settle_mod
    from src.prospective_market import ProspectiveStore

    sports_db = tmp_path / "cs.db"
    conn = _sports(tmp_path)
    _add(conn, 1, "2026-07-23", "Vitality", "MOUZ", 2, 0)
    conn.close()

    market_db = tmp_path / "market_shadow.db"
    store = ProspectiveStore(market_db)
    mconn = store.connect()
    store.import_quotes(
        mconn,
        [
            {
                "quote_id": "q1",
                "market_id": "m1",
                "team_a": "Vitality",
                "team_b": "MOUZ",
                "format": "bo3",
                "scheduled_at": "2026-07-23T12:00:00+00:00",
                "observed_at": "2026-07-23T10:00:00+00:00",
                "model_probability_a": 0.6,
                "model_probability_b": 0.4,
                "ratings_sha256": "a" * 64,
                "probability_a": 0.55,
                "probability_b": 0.45,
                "decimal_a": 1.8,
                "decimal_b": 2.2,
                "source": "polymarket-clob",
                "source_kind": "prediction_market",
                "source_event_id": "e1",
                "competition_name": "Cup",
            }
        ],
        batch_id="b",
    )
    mconn.close()

    exit_code = settle_mod.main(["--sports-db", str(sports_db), "--market-db", str(market_db)])
    assert exit_code == 0

    verify = sqlite3.connect(market_db)
    assert verify.execute(
        "SELECT event_state FROM prospective_events WHERE event_key='polymarket-clob:m1'"
    ).fetchone() == ("MATURED",)
    assert verify.execute(
        "SELECT outcome_a FROM prospective_settlements WHERE event_key='polymarket-clob:m1'"
    ).fetchone() == (1,)


def test_main_dry_run_reports_without_writing(tmp_path):
    from scripts import settle_prospective_market as settle_mod
    from src.prospective_market import ProspectiveStore

    sports_db = tmp_path / "cs.db"
    conn = _sports(tmp_path)
    _add(conn, 1, "2026-07-23", "Vitality", "MOUZ", 2, 0)
    conn.close()

    market_db = tmp_path / "market_shadow.db"
    store = ProspectiveStore(market_db)
    mconn = store.connect()
    store.import_quotes(
        mconn,
        [
            {
                "quote_id": "q1",
                "market_id": "m1",
                "team_a": "Vitality",
                "team_b": "MOUZ",
                "format": "bo3",
                "scheduled_at": "2026-07-23T12:00:00+00:00",
                "observed_at": "2026-07-23T10:00:00+00:00",
                "model_probability_a": 0.6,
                "model_probability_b": 0.4,
                "ratings_sha256": "a" * 64,
                "probability_a": 0.55,
                "probability_b": 0.45,
                "decimal_a": 1.8,
                "decimal_b": 2.2,
                "source": "polymarket-clob",
                "source_kind": "prediction_market",
                "source_event_id": "e1",
                "competition_name": "Cup",
            }
        ],
        batch_id="b",
    )
    mconn.close()

    exit_code = settle_mod.main(
        ["--dry-run", "--sports-db", str(sports_db), "--market-db", str(market_db)]
    )
    assert exit_code == 0

    verify = sqlite3.connect(market_db)
    assert verify.execute("SELECT count(*) FROM prospective_settlements").fetchone()[0] == 0
    assert verify.execute("SELECT count(*) FROM prospective_results").fetchone()[0] == 0
