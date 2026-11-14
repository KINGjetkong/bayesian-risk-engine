#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Engine v2.0 (Monte Carlo)

Differences from v1:
  v1 uses EMA-smoothed logit-space collapse with fixed domain weights.
  v2 uses Monte Carlo forward simulation with regime-transition probabilities
  to predict the NEXT regime state and weight nodes accordingly.

Architecture:
  1. Same 200+ ProbNodes as v1 (imported)
  2. Regime Transition Matrix — Markov chain over 6 regime states
  3. Monte Carlo Regime Predictor — N=500 simulations of 15-min forward path
  4. Attractor-Repeller Field — probability nodes create attractors (high-p
     events that pull price toward them) and repellers (high-p vetoes that
     push price away), collapsing into a field potential
  5. Stochastic collapse — instead of deterministic logit-mean, sample from
     the posterior distribution of each node and collapse via attractor field

The key insight: probabilities are NOT independent.  They form a directed
graph where some outcomes ATTRACT others (momentum → breakout → trend) and
some REPEL (veto → stop → reversal).  The Monte Carlo simulation traverses
this graph stochastically.

References:
  Hamilton (1989) — regime switching models
  Ang/Bekaert (2002) — regime-dependent asset allocation
  Barber/Lyon (1997) — detecting long-run abnormal stock returns
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    BayesianProbabilityEngine,
    MarketContext,
    EngineOutput,
    Regime,
    GexRegime,
    Domain,
    ProbNode,
    logit,
    inv_logit,
    reliability,
    kelly_fraction,
    ev_gate,
    break_even_move,
    CONFIDENCE_ROUTING,
)


# ---------------------------------------------------------------------------
# Regime Transition Matrix (Markov chain)
# ---------------------------------------------------------------------------

# Rows = current regime, Cols = next regime
# Estimated from intraday QQQ 15-min bars (stylized, from research)
REGIME_TRANSITIONS = {
    Regime.CHOP: {
        Regime.CHOP: 0.55, Regime.TREND_UP: 0.12, Regime.TREND_DOWN: 0.10,
        Regime.EXPANSION: 0.10, Regime.COMPRESSION: 0.12, Regime.UNKNOWN: 0.01,
    },
    Regime.TREND_UP: {
        Regime.CHOP: 0.18, Regime.TREND_UP: 0.50, Regime.TREND_DOWN: 0.05,
        Regime.EXPANSION: 0.18, Regime.COMPRESSION: 0.08, Regime.UNKNOWN: 0.01,
    },
    Regime.TREND_DOWN: {
        Regime.CHOP: 0.18, Regime.TREND_UP: 0.05, Regime.TREND_DOWN: 0.50,
        Regime.EXPANSION: 0.18, Regime.COMPRESSION: 0.08, Regime.UNKNOWN: 0.01,
    },
    Regime.EXPANSION: {
        Regime.CHOP: 0.15, Regime.TREND_UP: 0.22, Regime.TREND_DOWN: 0.22,
        Regime.EXPANSION: 0.30, Regime.COMPRESSION: 0.10, Regime.UNKNOWN: 0.01,
    },
    Regime.COMPRESSION: {
        Regime.CHOP: 0.20, Regime.TREND_UP: 0.15, Regime.TREND_DOWN: 0.15,
        Regime.EXPANSION: 0.30, Regime.COMPRESSION: 0.19, Regime.UNKNOWN: 0.01,
    },
    Regime.UNKNOWN: {
        Regime.CHOP: 0.30, Regime.TREND_UP: 0.15, Regime.TREND_DOWN: 0.15,
        Regime.EXPANSION: 0.15, Regime.COMPRESSION: 0.15, Regime.UNKNOWN: 0.10,
    },
}

REGIMES_LIST = list(Regime)


def sample_next_regime(current: Regime) -> Regime:
    probs = REGIME_TRANSITIONS[current]
    r = random.random()
    cumulative = 0.0
    for regime in REGIMES_LIST:
        cumulative += probs.get(regime, 0.0)
        if r <= cumulative:
            return regime
    return Regime.UNKNOWN


# ---------------------------------------------------------------------------
# Attractor-Repeller Field
# ---------------------------------------------------------------------------

@dataclass
class AttractorNode:
    node_id: str
    direction: float  # +1 bullish attractor, -1 bearish repeller
    strength: float  # [0,1] from posterior
    weight: float  # effective_weight from ProbNode


def compute_field_potential(attractors: list[AttractorNode]) -> float:
    if not attractors:
        return 0.0

    total_force = 0.0
    total_weight = 0.0

    for a in attractors:
        force = a.direction * a.strength * a.weight
        total_force += force
        total_weight += a.weight

    if total_weight == 0:
        return 0.0

    return total_force / total_weight


def classify_node_direction(node: ProbNode) -> float:
    role_directions = {
        "entry": 1.0,
        "exit": -0.5,
        "veto": -1.0,
        "sizing": 0.0,
        "context": 0.3,
        "regime": 0.5,
        "timing": 0.2,
        "routing": 0.0,
    }
    base_dir = role_directions.get(node.strategy_role, 0.0)

    if node.prior_update < 0:
        base_dir *= -1

    return base_dir


# ---------------------------------------------------------------------------
# Monte Carlo Engine
# ---------------------------------------------------------------------------

class MonteCarloRegimePredictor:
    def __init__(self, n_simulations: int = 500, horizon_steps: int = 1):
        self.n_simulations = n_simulations
        self.horizon_steps = horizon_steps

    def predict(self, current_regime: Regime) -> dict[Regime, float]:
        counts: dict[Regime, int] = {r: 0 for r in Regime}

        for _ in range(self.n_simulations):
            regime = current_regime
            for _ in range(self.horizon_steps):
                regime = sample_next_regime(regime)
            counts[regime] += 1

        total = sum(counts.values())
        return {r: c / total for r, c in counts.items()}


# ---------------------------------------------------------------------------
# V2 Engine
# ---------------------------------------------------------------------------

class BayesianEngineV2:
    def __init__(self, n_simulations: int = 500):
        self.base_engine = BayesianProbabilityEngine()
        self.mc_predictor = MonteCarloRegimePredictor(
            n_simulations=n_simulations, horizon_steps=1
        )
        self._regime_forecast: dict[Regime, float] = {}
        self._attractor_field: float = 0.0

    def update(self, ctx: MarketContext) -> dict:
        ts = ctx.timestamp or time.time()

        # Step 1: Run base engine update (populates all 200 nodes)
        base_output = self.base_engine.update(ctx)

        # Step 2: Monte Carlo regime prediction (15-min forward)
        self._regime_forecast = self.mc_predictor.predict(ctx.regime)

        # Step 3: Build attractor-repeller field from live nodes
        attractors = []
        for node in self.base_engine.nodes.values():
            if node._is_live:
                direction = classify_node_direction(node)
                if direction != 0:
                    attractors.append(AttractorNode(
                        node_id=node.id,
                        direction=direction,
                        strength=node._current_posterior,
                        weight=node.effective_weight,
                    ))

        self._attractor_field = compute_field_potential(attractors)

        # Step 4: Stochastic collapse — weight domain posteriors by
        # predicted regime probabilities
        regime_weighted_posterior = 0.0
        total_regime_weight = 0.0

        for regime, prob in self._regime_forecast.items():
            if prob < 0.01:
                continue
            regime_mult = self._regime_multiplier_for(regime)
            regime_posterior = base_output.composite_posterior * regime_mult
            regime_weighted_posterior += prob * regime_posterior
            total_regime_weight += prob

        if total_regime_weight > 0:
            mc_posterior = regime_weighted_posterior / total_regime_weight
        else:
            mc_posterior = base_output.composite_posterior

        # Step 5: Blend base posterior with MC posterior and attractor field
        # V9_HYBRID_BLEND: domain 0.40, rules 0.35, bayesian 0.25
        field_signal = inv_logit(self._attractor_field * 2)
        composite = (
            0.40 * base_output.composite_posterior +
            0.35 * mc_posterior +
            0.25 * field_signal
        )
        composite = min(max(composite, 0.01), 0.99)

        # Step 6: Apply vetoes
        if base_output.veto_active:
            composite = min(composite, 0.35)

        # Confidence routing
        confidence_tier = "paper"
        for threshold, tier in CONFIDENCE_ROUTING:
            uncertainty = abs(composite - 0.5) * 2
            if 1 - uncertainty < threshold:
                confidence_tier = tier
                break

        # Kelly / EV
        avg_win = 0.03 * ctx.premium if ctx.premium > 0 else 1.0
        avg_loss = 0.015 * ctx.premium if ctx.premium > 0 else 1.0
        cost = 0.10 * 2
        ev = ev_gate(composite, avg_win, avg_loss, cost)
        kf = kelly_fraction(composite, avg_win / max(avg_loss, 0.01))

        return {
            "version": "v2_montecarlo",
            "composite_posterior": round(composite, 6),
            "base_posterior": round(base_output.composite_posterior, 6),
            "mc_posterior": round(mc_posterior, 6),
            "attractor_field": round(self._attractor_field, 6),
            "field_signal": round(field_signal, 6),
            "regime_forecast": {
                r.value: round(p, 4)
                for r, p in sorted(
                    self._regime_forecast.items(),
                    key=lambda x: -x[1]
                )[:3]
            },
            "regime": ctx.regime.value,
            "confidence_tier": confidence_tier,
            "kelly_fraction": round(kf, 4),
            "ev": round(ev, 4),
            "live_nodes": base_output.live_node_count,
            "dark_nodes": base_output.dark_node_count,
            "total_nodes": base_output.total_node_count,
            "top_attractors": self._top_attractors(attractors, 5),
            "top_repellers": self._top_repellers(attractors, 5),
            "veto_active": base_output.veto_active,
            "veto_reasons": base_output.veto_reasons,
        }

    def _regime_multiplier_for(self, regime: Regime) -> float:
        mults = {
            Regime.CHOP: 0.85,
            Regime.TREND_UP: 1.15,
            Regime.TREND_DOWN: 0.85,
            Regime.EXPANSION: 1.10,
            Regime.COMPRESSION: 0.90,
            Regime.UNKNOWN: 1.00,
        }
        return mults.get(regime, 1.0)

    def _top_attractors(self, attractors: list[AttractorNode],
                        n: int) -> list[dict]:
        bullish = [a for a in attractors if a.direction > 0]
        bullish.sort(key=lambda a: a.strength * a.weight, reverse=True)
        return [
            {"id": a.node_id, "strength": round(a.strength, 4),
             "weight": round(a.weight, 4)}
            for a in bullish[:n]
        ]

    def _top_repellers(self, attractors: list[AttractorNode],
                       n: int) -> list[dict]:
        bearish = [a for a in attractors if a.direction < 0]
        bearish.sort(key=lambda a: abs(a.strength * a.weight), reverse=True)
        return [
            {"id": a.node_id, "strength": round(a.strength, 4),
             "weight": round(a.weight, 4)}
            for a in bearish[:n]
        ]


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    engine = BayesianEngineV2(n_simulations=500)

    ctx = MarketContext(
        timestamp=time.time(),
        price=480.50,
        vwap=480.00,
        ema9=480.20,
        ema20=479.80,
        ema144=478.00,
        rsi_14=55.0,
        atr_14=2.5,
        bb_upper=483.0,
        bb_lower=477.0,
        volume_ratio=1.3,
        cvd_slope=0.8,
        vpin=0.65,
        obi=0.15,
        spread_bps=5.0,
        option_delta=0.45,
        option_gamma=0.08,
        option_theta=-0.35,
        option_iv=22.0,
        premium=1.85,
        premium_velocity=0.12,
        premium_acceleration=0.03,
        premium_in_band=True,
        gex=5e8,
        put_call_ratio=0.9,
        zero_dte_volume_ratio=1.2,
        regime=Regime.TREND_UP,
        gex_regime=GexRegime.LONG_GAMMA,
        vix=18.0,
        es_price=5350.0,
        nq_price=18800.0,
        es_nq_basis=2.5,
        futures_spot_corr=0.995,
        minutes_since_open=60,
        is_first_15=False,
        is_lunch=False,
        is_power_hour=False,
        ib_high=481.0,
        ib_low=479.0,
        prev_day_poc=479.50,
        opening_gap_pct=0.3,
        dte=0,
        bid_depth_l1=500.0,
        ask_depth_l1=450.0,
    )

    output = engine.update(ctx)
    print(json.dumps(output, indent=2))
    print(f"\n{'='*60}")
    print(f"V2 MONTE CARLO ENGINE")
    print(f"Composite: {output['composite_posterior']:.4f}")
    print(f"Base v1:   {output['base_posterior']:.4f}")
    print(f"MC pred:   {output['mc_posterior']:.4f}")
    print(f"Field:     {output['attractor_field']:.4f}")
    print(f"Regime forecast: {output['regime_forecast']}")
    print(f"Tier: {output['confidence_tier']}")
    print(f"Nodes: {output['live_nodes']}/{output['total_nodes']} live")
