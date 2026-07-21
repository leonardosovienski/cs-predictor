"""Mercado de previsão público para shadow CS; estritamente read-only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import math
import re
import subprocess
from typing import Any, Callable
from urllib.parse import urlencode, urlparse

import httpx

from ..config import identity_key
from predictor_core.data.contracts import DataUnavailableError

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"


def _array(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise DataUnavailableError(f"Polymarket {field} inválido") from exc
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise DataUnavailableError(f"Polymarket {field} inválido")
    return value


def _timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, timezone.utc)
    raw = str(value).strip()
    if raw.isdigit():
        return _timestamp(int(raw))
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataUnavailableError("timestamp inválido no order book") from exc
    if parsed.tzinfo is None:
        raise DataUnavailableError("timestamp sem timezone")
    return parsed.astimezone(timezone.utc)


class PolymarketProvider:
    def __init__(self, *, get_json: Callable[[str], Any] | None = None,
                 timeout: float = 20.0):
        self.get_json = get_json or self._http_get_json
        self.timeout = timeout

    def _http_get_json(self, url: str) -> Any:
        try:
            response = httpx.get(url, timeout=self.timeout,
                                 headers={"User-Agent": "cs-predictor-shadow/1.0"})
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            try:
                return self._curl_via_doh(url)
            except (OSError, ValueError, subprocess.SubprocessError) as fallback:
                raise DataUnavailableError(
                    f"Polymarket indisponível: {exc}; fallback DoH: {fallback}") from fallback

    def _curl_via_doh(self, url: str) -> Any:
        parsed = urlparse(url)
        allowed = {"gamma-api.polymarket.com", "clob.polymarket.com"}
        if parsed.scheme != "https" or parsed.hostname not in allowed:
            raise ValueError("host não permitido no fallback DoH")
        dns = httpx.get("https://1.1.1.1/dns-query",
                        params={"name": parsed.hostname, "type": "A"},
                        headers={"accept": "application/dns-json"}, timeout=self.timeout)
        dns.raise_for_status()
        addresses = []
        for row in dns.json().get("Answer") or []:
            if row.get("type") == 1:
                address = ipaddress.ip_address(row.get("data", ""))
                if not address.is_global:
                    raise ValueError("DoH retornou endereço não público")
                addresses.append(str(address))
        if not addresses:
            raise ValueError("DoH não retornou endereço A")
        result = subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--max-time",
             str(max(1, int(self.timeout))), "--resolve",
             f"{parsed.hostname}:443:{addresses[0]}", url],
            capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(result.stdout)

    def list_upcoming_matches(self, *, horizon_hours: int = 48,
                              now: datetime | None = None) -> list[dict[str, Any]]:
        observed = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        limit = observed + timedelta(hours=horizon_hours)
        query = urlencode({"q": "Counter-Strike", "events_status": "active",
                           "limit_per_type": 100, "keep_closed_markets": 0})
        payload = self.get_json(f"{GAMMA}/public-search?{query}")
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise DataUnavailableError("busca de eventos Polymarket inválida")
        found = []
        for event in payload["events"]:
            if event.get("closed") is True:
                continue
            try:
                scheduled = _timestamp(event.get("startTime") or event.get("endDate"))
            except DataUnavailableError:
                continue
            if not observed < scheduled <= limit:
                continue
            moneylines = [market for market in event.get("markets") or []
                          if market.get("sportsMarketType") == "moneyline"
                          and market.get("closed") is not True]
            if len(moneylines) != 1:
                continue
            outcomes = _array(moneylines[0].get("outcomes"), "outcomes")
            if len(outcomes) == 2:
                found.append({"event_id": str(event.get("id")),
                              "team_a": outcomes[0], "team_b": outcomes[1],
                              "scheduled_at": scheduled.isoformat(timespec="seconds")})
        unique = {row["event_id"]: row for row in found}
        return sorted(unique.values(), key=lambda row: (row["scheduled_at"], row["event_id"]))

    @staticmethod
    def _midpoint(book: dict[str, Any]) -> tuple[float, float]:
        try:
            bids = [float(row["price"]) for row in book["bids"]]
            asks = [float(row["price"]) for row in book["asks"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise DataUnavailableError("order book malformado") from exc
        if not bids or not asks:
            raise DataUnavailableError("order book sem ambos os lados")
        bid, ask = max(bids), min(asks)
        if not 0 < bid <= ask < 1:
            raise DataUnavailableError("order book com preços inválidos")
        return (bid + ask) / 2, ask - bid

    def fetch_match(self, team_a: str, team_b: str, *,
                    observed_at: datetime | None = None,
                    event_id: str | None = None) -> dict[str, Any]:
        if observed_at is not None and (
                observed_at.tzinfo is None or observed_at.utcoffset() is None):
            raise ValueError("observed_at deve conter timezone")
        observed = (observed_at.astimezone(timezone.utc)
                    if observed_at is not None else None)
        if event_id:
            event = self.get_json(f"{GAMMA}/events/{event_id}")
            events = [event] if isinstance(event, dict) else []
        else:
            query = urlencode({"q": f"Counter-Strike: {team_a} vs {team_b}",
                               "events_status": "active", "limit_per_type": 20,
                               "keep_closed_markets": 0})
            payload = self.get_json(f"{GAMMA}/public-search?{query}")
            events = payload.get("events", []) if isinstance(payload, dict) else []
        target = {identity_key(team_a), identity_key(team_b)}
        candidates = []
        for event in events:
            for market in event.get("markets") or []:
                if market.get("sportsMarketType") != "moneyline":
                    continue
                outcomes = _array(market.get("outcomes"), "outcomes")
                tokens = _array(market.get("clobTokenIds"), "clobTokenIds")
                if len(outcomes) == len(tokens) == 2 and {identity_key(x) for x in outcomes} == target:
                    candidates.append((event, market, outcomes, tokens))
        if len(candidates) != 1:
            raise DataUnavailableError(f"esperado 1 moneyline exato; encontrados {len(candidates)}")
        event, market, outcomes, tokens = candidates[0]
        fmt = re.search(r"\(BO([135])\)", market.get("question") or "", re.I)
        if not fmt:
            raise DataUnavailableError("moneyline sem formato BO1/BO3/BO5")
        scheduled = _timestamp(event.get("startTime") or event.get("endDate"))
        if observed is not None and observed >= scheduled:
            raise DataUnavailableError("coleta não é PRE_EVENT")
        books = [self.get_json(f"{CLOB}/book?{urlencode({'token_id': token})}")
                 for token in tokens]
        if observed is None:
            observed = datetime.now(timezone.utc)
        if observed >= scheduled:
            raise DataUnavailableError("coleta fora da janela PRE_EVENT")
        published = max(_timestamp(book.get("timestamp")) for book in books)
        if published > observed:
            raise DataUnavailableError("order book publicado depois da observação")
        values = [self._midpoint(book) for book in books]
        total = sum(mid for mid, _spread in values)
        probs = {name: mid / total for name, (mid, _spread) in zip(outcomes, values)}
        name_a = next(name for name in outcomes if identity_key(name) == identity_key(team_a))
        name_b = next(name for name in outcomes if identity_key(name) == identity_key(team_b))
        quote_id = hashlib.sha256(
            f"polymarket-clob|{market.get('id')}|{published.isoformat()}".encode()).hexdigest()
        return {
            "schema_version": "cs-market-quote/1.0", "quote_id": quote_id,
            "source": "polymarket-clob", "source_kind": "prediction_market",
            "market_id": str(market.get("id")), "team_a": team_a, "team_b": team_b,
            "format": f"bo{fmt.group(1)}", "scheduled_at": scheduled.isoformat(timespec="seconds"),
            "observed_at": observed.isoformat(timespec="seconds"),
            "published_at": published.isoformat(timespec="seconds"),
            "probability_a": round(probs[name_a], 8), "probability_b": round(probs[name_b], 8),
            "decimal_a": round(1 / probs[name_a], 6), "decimal_b": round(1 / probs[name_b], 6),
            "max_spread": round(max(spread for _mid, spread in values), 8),
            "liquidity": float(market.get("liquidity") or event.get("liquidity") or 0),
            "read_only": True,
        }
