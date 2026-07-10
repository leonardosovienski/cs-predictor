"""Fonte de dados HLTV — STUB da Fase 0.

O HLTV bloqueia fetch direto (403 Cloudflare — confirmado na criação deste
projeto em 2026-07-10; o ranking veio de um espelho). A Fase 1 decide a via:
curl_cffi com impersonate (padrão sofascore da plataforma), API de terceiros
ou export manual. Interface com a mesma disciplina do core
(DataUnavailableError; delay de cortesia via HLTV_SCRAPER_DELAY).
"""
import os

from predictor_core.data.contracts import DataUnavailableError


class HltvProvider:
    """Interface da fonte HLTV. Fase 0: tudo levanta DataUnavailableError —
    nenhum teste ou serving pode depender de rede sem perceber."""

    BASE_URL = "https://www.hltv.org"

    def __init__(self, delay: float | None = None):
        self.delay = float(delay if delay is not None
                           else os.environ.get("HLTV_SCRAPER_DELAY", 2))

    def health_check(self) -> bool:
        """Fase 0: sem rede — sempre False (honesto: não há fonte ligada)."""
        return False

    def fetch_ranking(self) -> list[dict]:
        """Fase 1: Top 30 atual (nome, região, posição)."""
        raise DataUnavailableError(
            "HltvProvider é stub na Fase 0 — HLTV responde 403 a cliente "
            "HTTP simples; implementar via curl_cffi/impersonate na Fase 1")

    def fetch_results(self, days: int = 30) -> list[dict]:
        """Fase 1: resultados de partidas Tier 1/2 (para update_ratings e
        backtest walk-forward)."""
        raise DataUnavailableError("HltvProvider é stub na Fase 0")
