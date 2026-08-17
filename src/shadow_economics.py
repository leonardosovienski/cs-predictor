"""Deterministic, no-capital execution model for prospective shadow decisions."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


class ShadowEconomicsError(ValueError):
    pass


@dataclass(frozen=True)
class StrategySpec:
    version: str = "VETO-01/1"
    stake: float = 50.0
    min_edge: float = 0.04
    max_spread: float = 0.03
    min_depth_multiple: float = 5.0
    fee_rate: float = 0.0

    def validate(self) -> None:
        values = (self.stake, self.min_edge, self.max_spread,
                  self.min_depth_multiple, self.fee_rate)
        if any(not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in values):
            raise ShadowEconomicsError("estratégia contém valor não-finito")
        if (self.stake <= 0 or self.min_edge < 0 or not 0 <= self.max_spread < 1
                or self.min_depth_multiple < 1 or not 0 <= self.fee_rate < 1
                or not self.version.strip()):
            raise ShadowEconomicsError("estratégia shadow inválida")


def _levels(rows: list[dict[str, Any]], *, reverse: bool) -> list[tuple[float, float]]:
    parsed = []
    for row in rows:
        try:
            price, size = float(row["price"]), float(row["size"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ShadowEconomicsError("nível de book sem preço/tamanho") from exc
        if not math.isfinite(price) or not math.isfinite(size) or not 0 < price < 1 or size <= 0:
            raise ShadowEconomicsError("nível de book inválido")
        parsed.append((price, size))
    if not parsed:
        raise ShadowEconomicsError("lado vazio do order book")
    return sorted(parsed, key=lambda item: item[0], reverse=reverse)


def executable_buy(asks: list[dict[str, Any]], *, stake: float) -> dict[str, float | str]:
    """Walk asks using cash stake; never substitutes midpoint or last trade."""
    if not math.isfinite(stake) or stake <= 0:
        raise ShadowEconomicsError("stake inválida")
    parsed = _levels(asks, reverse=False)
    remaining, shares, spent = stake, 0.0, 0.0
    for price, size in parsed:
        level_cost = price * size
        cost = min(remaining, level_cost)
        shares += cost / price
        spent += cost
        remaining -= cost
        if remaining <= 1e-9:
            break
    if remaining > 1e-9:
        return {"status": "NO_FILL", "requested_stake": stake,
                "filled_stake": spent, "unfilled_stake": remaining}
    average_price = spent / shares
    return {"status": "FILLED", "requested_stake": stake, "filled_stake": spent,
            "unfilled_stake": 0.0, "shares": shares, "average_price": average_price,
            "decimal_odds": 1 / average_price,
            "slippage": average_price - parsed[0][0]}


def shadow_decision(*, model_probability: float, bids: list[dict[str, Any]],
                    asks: list[dict[str, Any]], strategy: StrategySpec) -> dict[str, Any]:
    strategy.validate()
    if not math.isfinite(model_probability) or not 0 < model_probability < 1:
        raise ShadowEconomicsError("probabilidade do modelo inválida")
    parsed_bids = _levels(bids, reverse=True)
    parsed_asks = _levels(asks, reverse=False)
    spread = parsed_asks[0][0] - parsed_bids[0][0]
    available_cash = sum(price * size for price, size in parsed_asks)
    fill = executable_buy(asks, stake=strategy.stake)
    base = {"strategy": asdict(strategy), "model_probability": model_probability,
            "best_bid": parsed_bids[0][0], "best_ask": parsed_asks[0][0],
            "spread": spread, "available_ask_cash": available_cash, **fill}
    if fill["status"] == "NO_FILL":
        return {**base, "decision": "NO_FILL", "reason": "stake não executável no book"}
    if spread > strategy.max_spread:
        return {**base, "decision": "NO_BET", "reason": "spread acima do limite"}
    if available_cash < strategy.stake * strategy.min_depth_multiple:
        return {**base, "decision": "NO_BET", "reason": "profundidade abaixo do múltiplo mínimo"}
    effective_odds = float(fill["decimal_odds"])
    edge = model_probability * (1 + (effective_odds - 1) * (1 - strategy.fee_rate)) - 1
    decision = "BET" if edge >= strategy.min_edge else "NO_BET"
    reason = "edge líquido suficiente" if decision == "BET" else "edge líquido insuficiente"
    return {**base, "decision": decision, "reason": reason, "net_edge": edge,
            "effective_decimal_odds": effective_odds}


def settle_shadow_decision(decision: dict[str, Any], *, won: bool) -> dict[str, Any]:
    if decision.get("decision") != "BET":
        return {**decision, "settlement": "NOT_APPLICABLE", "pnl": 0.0}
    stake = float(decision["filled_stake"])
    odds = float(decision["effective_decimal_odds"])
    fee = float(decision["strategy"]["fee_rate"])
    pnl = stake * (odds - 1) * (1 - fee) if won else -stake
    return {**decision, "settlement": "WON" if won else "LOST", "pnl": pnl}


def probability_metrics(rows: list[dict[str, Any]], probability_key: str) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "brier": None, "log_loss": None}
    brier = log_loss = 0.0
    for row in rows:
        probability, outcome = float(row[probability_key]), int(row["outcome"])
        if not 0 < probability < 1 or outcome not in (0, 1):
            raise ShadowEconomicsError("linha de avaliação inválida")
        clipped = min(max(probability, 1e-9), 1 - 1e-9)
        brier += (probability - outcome) ** 2
        log_loss -= outcome * math.log(clipped) + (1 - outcome) * math.log(1 - clipped)
    return {"n": len(rows), "brier": brier / len(rows), "log_loss": log_loss / len(rows)}
