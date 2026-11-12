#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Engine v4.0 (Ensemble)

Stacks v1 (deterministic), v2 (Monte Carlo), v3 (factorized shrinkage)
into a meta-ensemble that:
  1. Runs all three engines in parallel on the same tick
  2. Computes agreement/disagreement metrics
  3. Uses inverse-variance weighting to combine them
  4. Applies a confidence discount when engines disagree
  5. Outputs a single composite + breakdown per engine

The ensemble exploits the different failure modes:
  - v1 fails on regime transitions (static weights)
  - v2 fails on stable regimes (MC noise adds no signal)
  - v3 fails on sparse data (shrinkage collapses everything to 0.5)

By combining them, the ensemble is robust across all market states.

References:
  Bates/Granger (1969) — combination of forecasts
  Timmermann (2006) — forecast combinations
"""
from __future__ import annotations

import math
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    MarketContext, Regime, GexRegime,
    logit, inv_logit, kelly_fraction, ev_gate, CONFIDENCE_ROUTING,
)
from bayesian_engine_v2_montecarlo import BayesianEngineV2
from bayesian_engine_v3_factorized import BayesianEngineV3


class BayesianEngineV4Ensemble:
    def __init__(self, mc_simulations: int = 300):
        self.v2_engine = BayesianEngineV2(n_simulations=mc_simulations)
        self.v3_engine = BayesianEngineV3()
        self._history: list[dict] = []
        self._engine_weights = {"v1": 0.35, "v2": 0.35, "v3": 0.30}
        self._tick_count = 0

    def update(self, ctx: MarketContext) -> dict:
        ts = ctx.timestamp or time.time()
        self._tick_count += 1

        # Run all engines
        v2_out = self.v2_engine.update(ctx)
        v3_out = self.v3_engine.update(ctx)

        v1_post = v2_out["base_posterior"]
        v2_post = v2_out["composite_posterior"]
        v3_post = v3_out["composite_posterior"]

        # Agreement metrics
        posts = [v1_post, v2_post, v3_post]
        mean_post = sum(posts) / 3
        variance = sum((p - mean_post) ** 2 for p in posts) / 3
        std_dev = math.sqrt(variance)
        agreement = 1.0 - min(std_dev / 0.25, 1.0)

        # Inverse-variance weighting (adaptive)
        # If an engine is far from consensus, reduce its weight
        distances = [abs(p - mean_post) for p in posts]
        inv_distances = [1.0 / max(d, 0.01) for d in distances]
        total_inv = sum(inv_distances)
        adaptive_weights = [w / total_inv for w in inv_distances]

        # Blend static and adaptive weights
        w1 = 0.5 * self._engine_weights["v1"] + 0.5 * adaptive_weights[0]
        w2 = 0.5 * self._engine_weights["v2"] + 0.5 * adaptive_weights[1]
        w3 = 0.5 * self._engine_weights["v3"] + 0.5 * adaptive_weights[2]
        w_total = w1 + w2 + w3
        w1, w2, w3 = w1 / w_total, w2 / w_total, w3 / w_total

        # Ensemble composite
        composite = w1 * v1_post + w2 * v2_post + w3 * v3_post

        # Confidence discount when engines disagree
        if agreement < 0.7:
            discount = 0.5 + 0.5 * agreement
            composite = 0.5 + (composite - 0.5) * discount

        composite = min(max(composite, 0.01), 0.99)

        # Vetoes from any engine
        veto_active = v2_out["veto_active"]
        veto_reasons = v2_out["veto_reasons"]
        if veto_active:
            composite = min(composite, 0.35)

        # Directional consensus
        bullish_count = sum(1 for p in posts if p > 0.55)
        bearish_count = sum(1 for p in posts if p < 0.45)
        neutral_count = 3 - bullish_count - bearish_count
        if bullish_count == 3:
            consensus = "STRONG_BULL"
        elif bearish_count == 3:
            consensus = "STRONG_BEAR"
        elif bullish_count >= 2:
            consensus = "LEAN_BULL"
        elif bearish_count >= 2:
            consensus = "LEAN_BEAR"
        else:
            consensus = "MIXED"

        # Confidence routing
        confidence_tier = "paper"
        for threshold, tier in CONFIDENCE_ROUTING:
            uncertainty = abs(composite - 0.5) * 2
            if 1 - uncertainty < threshold:
                confidence_tier = tier
                break

        # If engines strongly disagree, force paper
        if agreement < 0.5:
            confidence_tier = "paper"

        # Kelly / EV
        avg_win = 0.03 * ctx.premium if ctx.premium > 0 else 1.0
        avg_loss = 0.015 * ctx.premium if ctx.premium > 0 else 1.0
        cost = 0.10 * 2
        ev = ev_gate(composite, avg_win, avg_loss, cost)
        kf = kelly_fraction(composite, avg_win / max(avg_loss, 0.01))

        result = {
            "version": "v4_ensemble",
            "composite_posterior": round(composite, 6),
            "engine_posteriors": {
                "v1_deterministic": round(v1_post, 6),
                "v2_montecarlo": round(v2_post, 6),
                "v3_factorized": round(v3_post, 6),
            },
            "engine_weights": {
                "v1": round(w1, 4),
                "v2": round(w2, 4),
                "v3": round(w3, 4),
            },
            "agreement": round(agreement, 4),
            "consensus": consensus,
            "regime": ctx.regime.value,
            "gex_regime": ctx.gex_regime.value,
            "confidence_tier": confidence_tier,
            "kelly_fraction": round(kf, 4),
            "ev": round(ev, 4),
            "mc_regime_forecast": v2_out.get("regime_forecast", {}),
            "factor_effects": v3_out.get("factor_effects", {}),
            "live_nodes": v2_out["live_nodes"],
            "total_nodes": v2_out["total_nodes"],
            "tick_count": self._tick_count,
            "veto_active": veto_active,
            "veto_reasons": veto_reasons,
        }

        self._history.append({
            "ts": ts,
            "composite": composite,
            "v1": v1_post, "v2": v2_post, "v3": v3_post,
            "agreement": agreement,
        })
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        return result

    def recent_history(self, n: int = 10) -> list[dict]:
        return self._history[-n:]


# ---------------------------------------------------------------------------
# Multi-tick comparison
# ---------------------------------------------------------------------------

def run_comparison(n_ticks: int = 15):
    engine = BayesianEngineV4Ensemble(mc_simulations=200)

    base_ctx = dict(
        price=480.50, vwap=480.00, ema9=480.20, ema20=479.80,
        ema144=478.00, rsi_14=55.0, atr_14=2.5, bb_upper=483.0,
        bb_lower=477.0, volume_ratio=1.3, cvd_slope=0.8, vpin=0.65,
        obi=0.15, spread_bps=5.0, option_delta=0.45, option_gamma=0.08,
        option_theta=-0.35, option_iv=22.0, premium=1.85,
        premium_velocity=0.12, premium_acceleration=0.03,
        premium_in_band=True, gex=5e8, put_call_ratio=0.9,
        zero_dte_volume_ratio=1.2,
        regime=Regime.TREND_UP, gex_regime=GexRegime.LONG_GAMMA,
        vix=18.0, es_price=5350.0, nq_price=18800.0, es_nq_basis=2.5,
        futures_spot_corr=0.995, minutes_since_open=60,
        ib_high=481.0, ib_low=479.0, prev_day_poc=479.50,
        opening_gap_pct=0.3, dte=0, bid_depth_l1=500.0, ask_depth_l1=450.0,
    )

    print("BAYESIAN ENGINE V4 — ENSEMBLE COMPARISON")
    print("=" * 90)
    print(f"{'Tick':>4}  {'Ensemble':>9}  {'v1 Det':>8}  {'v2 MC':>8}"
          f"  {'v3 Fac':>8}  {'Agree':>6}  {'Consensus':>12}  {'Tier':>7}")
    print("-" * 90)

    regimes = [Regime.TREND_UP] * 5 + [Regime.CHOP] * 5 + [Regime.EXPANSION] * 5

    for i in range(n_ticks):
        ts = time.time() + i * 15
        ctx_dict = {**base_ctx, "timestamp": ts}
        ctx_dict["price"] += (i % 5) * 0.15 - 0.3
        ctx_dict["cvd_slope"] = 0.8 - (i % 7) * 0.2
        ctx_dict["minutes_since_open"] = 60 + i * 2
        ctx_dict["regime"] = regimes[i % len(regimes)]

        if regimes[i % len(regimes)] == Regime.CHOP:
            ctx_dict["obi"] = 0.02
            ctx_dict["volume_ratio"] = 0.8
        elif regimes[i % len(regimes)] == Regime.EXPANSION:
            ctx_dict["obi"] = 0.25
            ctx_dict["volume_ratio"] = 2.0
            ctx_dict["vpin"] = 0.85

        ctx = MarketContext(**ctx_dict)
        out = engine.update(ctx)

        ep = out["engine_posteriors"]
        print(f"{i+1:4d}  {out['composite_posterior']:9.6f}"
              f"  {ep['v1_deterministic']:8.6f}"
              f"  {ep['v2_montecarlo']:8.6f}"
              f"  {ep['v3_factorized']:8.6f}"
              f"  {out['agreement']:6.3f}"
              f"  {out['consensus']:>12}"
              f"  {out['confidence_tier']:>7}")

    print(f"\nFinal weights: {out['engine_weights']}")
    print(f"MC regime forecast: {out['mc_regime_forecast']}")
    print(f"Factor effects: {out['factor_effects']}")


if __name__ == "__main__":
    run_comparison(15)
