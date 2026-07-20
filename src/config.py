"""Configuração do cs-predictor — carrega config.yaml e resolve paths.

Mesmo padrão do nba-predictor: YAML na raiz é a única fonte de parâmetros;
vendor/ entra no sys.path aqui — todo entrypoint importa src.config primeiro
e ganha `import predictor_core` de graça.
"""
import json
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
_VENDOR = ROOT / "vendor"
if str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def load_teams() -> list[dict]:
    """HLTV Top 30 de data/teams_cs.json (nome, região, rank, Elo semente)."""
    cfg = load_config()
    path = ROOT / cfg.get("teams_file", "data/teams_cs.json")
    return json.loads(path.read_text(encoding="utf-8"))["teams"]


def clear_caches() -> None:
    load_config.cache_clear()
    load_teams.cache_clear()


def identity_key(value: str) -> str:
    """Chave de comparação; preserva o nome original como identidade."""
    return unicodedata.normalize("NFC", value.strip()).casefold()


def resolve_team(name: str, *, allow_substring: bool = True) -> dict:
    """Resolve identidade sem escolher silenciosamente entre candidatos."""
    teams = load_teams()
    stripped = name.strip()
    if not stripped:
        raise ValueError("time desconhecido: nome vazio")

    # A grafia exata é identidade suficiente mesmo quando duas organizações
    # diferem apenas por caixa. Comparações flexíveis exigem unicidade.
    exact = [t for t in teams if t["name"] == stripped]
    if len(exact) == 1:
        return exact[0]

    key = identity_key(stripped)
    name_matches = [t for t in teams if identity_key(t["name"]) == key]
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        candidates = [t["name"] for t in name_matches]
        raise ValueError(
            f"nome ambíguo: {name!r} corresponde a entidades distintas "
            f"{candidates} — use a grafia exata")

    # aliases explícitos (campo opcional "aliases" em teams_cs.json) têm
    # precedência sobre o casamento por substring, que é ambíguo por natureza
    alias_matches = [t for t in teams
                     if any(identity_key(alias) == key
                            for alias in t.get("aliases", []))]
    if len(alias_matches) == 1:
        return alias_matches[0]
    if len(alias_matches) > 1:
        candidates = [t["name"] for t in alias_matches]
        raise ValueError(
            f"alias ambíguo: {name!r} corresponde a entidades distintas "
            f"{candidates}")

    if not allow_substring:
        raise ValueError(f"time desconhecido: {name!r}; use nome exato ou alias")
    hits = [t for t in teams if key in identity_key(t["name"])]
    if len(hits) == 1:
        return hits[0]
    sugestao = [t["name"] for t in hits]
    raise ValueError(f"time desconhecido: {name!r}"
                     + (f" — você quis dizer {sugestao}?" if sugestao else ""))
