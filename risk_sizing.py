"""Research-driven 0DTE risk sizing utilities.

This module converts MadTrades-style signal confidence into executable risk
limits before an order reaches the execution layer. It intentionally has no
broker dependency so it can be used by FastAPI, a CLI, or a trading agent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Literal

Decision = Literal["ALLOW", "REDUCE", "BLOCK"]


@dataclass(frozen=True)
class RiskSizingInput:
    """Inputs required to size a short-duration options scalp."""

    account_equity: float
    signal_confidence: float
    entry_price: float
    stop_price: float
    atr: float | None = None
    current_drawdown_pct: float = 0.0
    daily_loss_pct: float = 0.0
    consecutive_losses: int = 0
    win_probability: float | None = None
    payoff_ratio: float | None = None
    liquidity_score: float = 1.0
    max_account_risk_pct: float = 0.01
    max_position_notional_pct: float = 0.25
    contract_multiplier: int = 100


@dataclass(frozen=True)
class RiskSizingResult:
    """Position size and gatekeeping decision."""

    decision: Decision
    contracts: int
    position_notional: float
    dollars_at_risk: float
    risk_per_contract: float
    effective_risk_pct: float
    confidence_multiplier: float
    drawdown_multiplier: float
    liquidity_multiplier: float
    kelly_fraction: float | None
    reasons: list[str] = field(default_factory=list)


def _bounded(value: float, low: float, high: float) -> float:
    if not isfinite(value):
        return low
    return max(low, min(high, value))


def confidence_to_multiplier(confidence: float) -> float:
    """Map a 0-100 or 0-1 confidence score into a conservative risk multiplier.

    The curve follows the research cluster emphasis on confidence-weighted
    position sizing: low-confidence signals are paper/watch only, 8/10 setups
    receive half risk, and 9-10/10 setups receive 75-100% of allowed risk.
    """

    c = confidence * 100 if confidence <= 1 else confidence
    c = _bounded(c, 0, 100)
    if c < 70:
        return 0.0
    if c < 80:
        return 0.25
    if c < 90:
        return 0.50
    if c < 95:
        return 0.75
    return 1.0


def drawdown_to_multiplier(current_drawdown_pct: float, daily_loss_pct: float, consecutive_losses: int) -> tuple[float, list[str]]:
    """Reduce risk as account/session damage increases."""

    reasons: list[str] = []
    dd = _bounded(current_drawdown_pct, 0, 1)
    daily = _bounded(daily_loss_pct, 0, 1)
    multiplier = 1.0

    if consecutive_losses >= 3:
        reasons.append("blocked: 3+ consecutive losses")
        return 0.0, reasons
    if daily >= 0.03:
        reasons.append("blocked: daily loss limit reached")
        return 0.0, reasons
    if dd >= 0.10:
        reasons.append("blocked: portfolio drawdown limit reached")
        return 0.0, reasons

    if consecutive_losses == 2:
        multiplier *= 0.35
        reasons.append("reduced: two consecutive losses")
    elif consecutive_losses == 1:
        multiplier *= 0.70
        reasons.append("reduced: one consecutive loss")

    if daily >= 0.02:
        multiplier *= 0.25
        reasons.append("reduced: daily loss above 2%")
    elif daily >= 0.01:
        multiplier *= 0.50
        reasons.append("reduced: daily loss above 1%")

    if dd >= 0.07:
        multiplier *= 0.35
        reasons.append("reduced: drawdown above 7%")
    elif dd >= 0.04:
        multiplier *= 0.60
        reasons.append("reduced: drawdown above 4%")

    return _bounded(multiplier, 0.0, 1.0), reasons


def fractional_kelly(win_probability: float | None, payoff_ratio: float | None, cap: float = 0.25) -> float | None:
    """Return a capped fractional Kelly fraction, or None when inputs are absent.

    Kelly is capped because 0DTE options have fat tails, spread slippage, and
    discontinuous losses. The returned value is a fraction of bankroll risk,
    not final notional allocation.
    """

    if win_probability is None or payoff_ratio is None:
        return None
    p = _bounded(win_probability, 0.0, 1.0)
    b = max(payoff_ratio, 1e-9)
    edge = p - ((1 - p) / b)
    return _bounded(edge * 0.25, 0.0, cap)


def calculate_position_size(payload: RiskSizingInput) -> RiskSizingResult:
    """Calculate risk-gated option contract size for a 0DTE scalp."""

    reasons: list[str] = []
    if payload.account_equity <= 0:
        raise ValueError("account_equity must be positive")
    if payload.entry_price <= 0 or payload.stop_price <= 0:
        raise ValueError("entry_price and stop_price must be positive")

    risk_per_share = abs(payload.entry_price - payload.stop_price)
    if payload.atr and payload.atr > 0:
        # Do not allow stop risk to understate a volatile tape.
        risk_per_share = max(risk_per_share, payload.atr * 0.30)
    risk_per_contract = risk_per_share * payload.contract_multiplier
    if risk_per_contract <= 0:
        raise ValueError("risk_per_contract must be positive")

    confidence_mult = confidence_to_multiplier(payload.signal_confidence)
    if confidence_mult == 0:
        reasons.append("blocked: signal confidence below 70")

    dd_mult, dd_reasons = drawdown_to_multiplier(
        payload.current_drawdown_pct,
        payload.daily_loss_pct,
        payload.consecutive_losses,
    )
    reasons.extend(dd_reasons)

    liq_mult = _bounded(payload.liquidity_score, 0.0, 1.0)
    if liq_mult < 0.50:
        reasons.append("reduced: liquidity score below 0.50")

    kelly = fractional_kelly(payload.win_probability, payload.payoff_ratio)
    base_risk_pct = _bounded(payload.max_account_risk_pct, 0.0, 0.05)
    if kelly is not None:
        base_risk_pct = min(base_risk_pct, max(kelly, 0.0025))
        reasons.append(f"kelly cap applied: {kelly:.4f}")

    effective_risk_pct = base_risk_pct * confidence_mult * dd_mult * liq_mult
    risk_budget = payload.account_equity * effective_risk_pct
    max_notional = payload.account_equity * _bounded(payload.max_position_notional_pct, 0.0, 1.0)

    raw_contracts = int(risk_budget // risk_per_contract)
    notional_per_contract = payload.entry_price * payload.contract_multiplier
    notional_cap_contracts = int(max_notional // notional_per_contract) if notional_per_contract > 0 else 0
    contracts = max(0, min(raw_contracts, notional_cap_contracts))

    dollars_at_risk = contracts * risk_per_contract
    position_notional = contracts * notional_per_contract

    if contracts == 0:
        decision: Decision = "BLOCK"
        if not reasons:
            reasons.append("blocked: risk budget too small for one contract")
    elif effective_risk_pct < base_risk_pct * 0.75:
        decision = "REDUCE"
    else:
        decision = "ALLOW"

    return RiskSizingResult(
        decision=decision,
        contracts=contracts,
        position_notional=round(position_notional, 2),
        dollars_at_risk=round(dollars_at_risk, 2),
        risk_per_contract=round(risk_per_contract, 2),
        effective_risk_pct=round(effective_risk_pct, 6),
        confidence_multiplier=confidence_mult,
        drawdown_multiplier=dd_mult,
        liquidity_multiplier=liq_mult,
        kelly_fraction=kelly,
        reasons=reasons,
    )


def result_to_dict(result: RiskSizingResult) -> dict[str, Any]:
    """Serialize dataclass output for FastAPI and agent tooling."""

    return {
        "decision": result.decision,
        "contracts": result.contracts,
        "position_notional": result.position_notional,
        "dollars_at_risk": result.dollars_at_risk,
        "risk_per_contract": result.risk_per_contract,
        "effective_risk_pct": result.effective_risk_pct,
        "confidence_multiplier": result.confidence_multiplier,
        "drawdown_multiplier": result.drawdown_multiplier,
        "liquidity_multiplier": result.liquidity_multiplier,
        "kelly_fraction": result.kelly_fraction,
        "reasons": result.reasons,
    }
