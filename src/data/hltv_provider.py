"""Fonte de dados HLTV — IMPLEMENTAÇÃO REAL (Fase 1, 2026-07-11).

O 403 da Fase 0 caiu com curl_cffi + impersonate Chrome (mesma técnica do
Sofascore na plataforma; sondagem 2026-07-11: /results e /ranking respondem
200 com conteúdo real). Parser de /results?offset=N por regex sobre os blocos
`result-con` — cada bloco carrega timestamp unix (ms), os dois times, o
placar da série, o evento e o formato (map-text: 'bo3'/'bo5'; nome de mapa
= bo1).

Cortesia: HLTV_SCRAPER_DELAY (default 2s) entre páginas — é scraping de
página HTML, não API; seja educado ou o 403 volta.
"""
import atexit
from html import unescape
import os
import re
import ssl
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests as creq

from ..model import infer_format

BASE = "https://www.hltv.org"

_BLOCK = re.compile(
    r'data-zonedgrouping-entry-unix="(\d+)"(.*?)'
    r'(?=data-zonedgrouping-entry-unix="|<div class="standard-headline|$)',
    re.S)
_TEAM = re.compile(r'<div class="team[^"]*">([^<]+)</div>')
_SCORE = re.compile(r'result-score">(.*?)</td>', re.S)
_EVENT = re.compile(r'<span class="event-name">([^<]+)</span>')
_MAP = re.compile(r'<div class="map-text">([^<]+)</div>')
_HREF = re.compile(r'<a href="(/matches/(\d+)/[^"]*)"')
_TAGS = re.compile(r"<[^>]+>")

_MAPHOLDER = re.compile(
    r'<div class="mapholder">(.*?)(?=<div class="mapholder">|$)', re.S)
_PLAYED = re.compile(r'<div class="(played|optional)">', re.S)
_MAPNAME = re.compile(r'<div class="mapname">([^<]+)</div>')
_TEAMNAME = re.compile(r'<div class="results-teamname text-ellipsis">'
                       r'([^<]+)</div>\s*'
                       r'<div class="results-team-score">([^<]+)</div>')


def _windows_ca_bundle():
    if sys.platform != "win32":
        return None
    pems = []
    for store in ("ROOT", "CA"):
        try:
            for cert, _enc, _trust in ssl.enum_certificates(store):
                pems.append(ssl.DER_cert_to_PEM_cert(cert))
        except Exception:
            pass
    if not pems:
        return None
    tmp = tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False)
    tmp.write("\n".join(pems))
    tmp.close()
    atexit.register(lambda: Path(tmp.name).unlink(missing_ok=True))
    return tmp.name


def parse_results_page(html: str) -> list[dict]:
    """Blocos result-con → dicts. Função pura (testável sem rede)."""
    out = []
    for ts_ms, block in _BLOCK.findall(html):
        teams = _TEAM.findall(block)
        score_m = _SCORE.search(block)
        href_m = _HREF.search(block)
        if len(teams) < 2 or not score_m or not href_m:
            continue
        raw = _TAGS.sub(" ", score_m.group(1))
        nums = re.findall(r"\d+", raw)
        if len(nums) < 2:
            continue
        map_m = _MAP.search(block)
        mtext = (map_m.group(1).strip().lower() if map_m else "")
        score_a, score_b = int(nums[0]), int(nums[1])
        # HLTV also lists drawn BO2/map results (for example 12-12).  They
        # have no series winner and therefore cannot enter this binary model.
        if score_a == score_b:
            continue
        advertised = mtext if mtext in ("bo1", "bo3", "bo5") else "bo1"
        fmt = infer_format(score_a, score_b, advertised)
        ev = _EVENT.search(block)
        ts = int(ts_ms) // 1000
        out.append({
            "match_id": int(href_m.group(2)),
            "url": href_m.group(1),
            "date": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d"),
            "ts": ts,
            "team_a": unescape(teams[0].strip()),
            "team_b": unescape(teams[1].strip()),
            "score_a": score_a,
            "score_b": score_b,
            "format": fmt,
            "event": unescape(ev.group(1).strip()) if ev else None,
        })
    return out


def parse_match_page(html: str) -> list[dict]:
    """Página /matches/<id>/... → mapas JOGADOS em ordem (mapname, times,
    placar em rounds). Blocos "optional" (não jogados, sobra do veto) são
    descartados. Função pura (testável sem rede)."""
    out = []
    for block in _MAPHOLDER.findall(html):
        played_m = _PLAYED.search(block)
        if not played_m or played_m.group(1) != "played":
            continue
        map_m = _MAPNAME.search(block)
        teams = _TEAMNAME.findall(block)
        if not map_m or len(teams) < 2:
            continue
        (name_a, score_a), (name_b, score_b) = teams[0], teams[1]
        if not score_a.strip().isdigit() or not score_b.strip().isdigit():
            continue                            # placar "-" = mapa não jogado
        out.append({
            "map_name": unescape(map_m.group(1).strip()),
            "team_a": unescape(name_a.strip()),
            "team_b": unescape(name_b.strip()),
            "score_a": int(score_a),
            "score_b": int(score_b),
        })
    return out


class HltvProvider:
    """Cliente real do HLTV (curl_cffi impersonate + CA bundle do Windows)."""

    def __init__(self, delay: float | None = None,
                 impersonate: str = "chrome146"):
        self.delay = float(delay if delay is not None
                           else os.environ.get("HLTV_SCRAPER_DELAY", 2))
        self.session = creq.Session(impersonate=impersonate)
        self.session.headers.update({
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.hltv.org/"})
        if os.environ.get("HLTV_INSECURE") == "1":
            self.verify = False
        else:
            self.verify = _windows_ca_bundle() or True

    def health_check(self) -> bool:
        try:
            r = self.session.get(f"{BASE}/results?offset=0", timeout=30,
                                 verify=self.verify)
            return r.status_code == 200 and "result-con" in r.text
        except Exception:
            return False

    def fetch_results_page(self, offset: int) -> list[dict]:
        """Uma página de /results (100 resultados), já parseada."""
        r = self.session.get(f"{BASE}/results?offset={offset}", timeout=30,
                             verify=self.verify)
        time.sleep(self.delay)
        r.raise_for_status()
        return parse_results_page(r.text)

    def fetch_match_maps(self, match_id: int, url: str | None = None) -> list[dict]:
        """Mapas jogados de UMA partida (página de detalhe). `url` é o path
        relativo já capturado em /results (evita reconstruir slug)."""
        path = url if url else f"/matches/{match_id}/x"
        r = self.session.get(f"{BASE}{path}", timeout=30, verify=self.verify)
        time.sleep(self.delay)
        r.raise_for_status()
        return parse_match_page(r.text)

    def fetch_results(self, until_date: str, max_pages: int = 600):
        """Gera resultados paginando até que a página só contenha jogos
        ANTERIORES a until_date (ISO). Yield página a página (o chamador
        persiste incrementalmente — queda no meio não perde o que veio)."""
        offset = 0
        for _ in range(max_pages):
            rows = self.fetch_results_page(offset)
            if not rows:
                return
            yield rows
            if min(r["date"] for r in rows) < until_date:
                return
            offset += 100
