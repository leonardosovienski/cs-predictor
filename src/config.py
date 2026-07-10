"""Configuração do cs-predictor — carrega config.yaml e resolve paths.

Mesmo padrão do nba-predictor: YAML na raiz é a única fonte de parâmetros;
vendor/ entra no sys.path aqui — todo entrypoint importa src.config primeiro
e ganha `import predictor_core` de graça.
"""
import json
import sys
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


def resolve_team(name: str) -> dict:
    """Nome exato ou substring única → registro do time. ValueError com
    sugestões quando ambíguo/desconhecido (contrato de erro da plataforma)."""
    teams = load_teams()
    low = name.strip().lower()
    for t in teams:
        if t["name"].lower() == low:
            return t
    hits = [t for t in teams if low in t["name"].lower()]
    if len(hits) == 1:
        return hits[0]
    sugestao = [t["name"] for t in hits]
    raise ValueError(f"time desconhecido: {name!r}"
                     + (f" — você quis dizer {sugestao}?" if sugestao else ""))
