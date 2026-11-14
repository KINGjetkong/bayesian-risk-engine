#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Engine v6.0 (Meta-Ensemble)

Stacks ALL five engine variants into a single master signal:
  V1: Deterministic logit-space collapse (200 nodes, regime/GEX weights)
  V2: Monte Carlo regime prediction + attractor-repeller field
  V3: Factorized James-Stein shrinkage (regime × GEX × ToD × VIX)
  V4: Inverse-variance adaptive ensemble of V1-V3
  V5: Information-theoretic entropy-weighted MDL pruning

Meta-combination strategy:
  1. Run all five engines on the same tick
  2. Compute pairwise agreement matrix (5×5)
  3. Rank engines by recent accuracy if tracked, else use static priors
  4. Copula-inspired tail-agreement weighting: upweight engines that agree
     in the tails (high/low posterior) where it matters most for 0DTE
  5. Output: composite + per-engine breakdown + agreement heatmap
  6. Confidence routing uses the full 5-engine dispersion

This is the production signal generator. V1-V5 are research variants;
V6 is what the state machine consumes.
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
from bayesian_engine_v4_ensemble import BayesianEngineV4Ensemble
from bayesian_engine_v5_entropy import BayesianEngineV5Entropy


ENGINE_NAMES = ["v1_det", "v2_mc", "v3_fac", "v4_ens", "v5_ent"]

STATIC_WEIGHTS = {
    "v1_det": 0.20,
    "v2_mc":  0.20,
    "v3_fac": 0.15,
    "v4_ens": 0.25,
    "v5_ent": 0.20,
}


def tail_agreement_bonus(posteriors: list[float], threshold: float = 0.65) -> float:
    """When engines agree in the tail (all above threshold or all below
    1-threshold), return a bonus multiplier. This is where 0DTE money
    is made — strong consensus on direction matters more than consensus
    near 0.5."""
    if not posteriors:
        return 0.0
    above = sum(1 for p in posteriors if p > threshold)
    below = sum(1 for p in posteriors if p < (1 - threshold))
    n = len(posteriors)
    if above >= n - 1:
        return 0.15
    if below >= n - 1:
        return 0.15
    if above == n:
        return 0.25
    if below == n:
        return 0.25
    return 0.0


def pairwise_agreement_matrix(posteriors: dict[str, float]) -> dict[str, dict[str, float]]:
    """5×5 agreement matrix: 1 - |p_i - p_j| for each pair."""
    names = list(posteriors.keys())
    matrix = {}
    for i, ni in enumerate(names):
        matrix[ni] = {}
        for j, nj in enumerate(names):
            matrix[ni][nj] = round(1.0 - abs(posteriors[ni] - posteriors[nj]), 4)
    return matrix


class BayesianEngineV6Meta:
    """Production meta-ensemble that consumes all five engine variants."""

    def __init__(self, mc_simulations: int = 200):
        self.v2_engine = BayesianEngineV2(n_simulations=mc_simulations)
        self.v3_engine = BayesianEngineV3()
        self.v4_engine = BayesianEngineV4Ensemble(mc_simulations=mc_simulations)
        self.v5_engine = BayesianEngineV5Entropy(mdl_prune=True, renyi_floor=3.0)

        self._tick_count = 0
        self._history: list[dict] = []
        self._engine_errors: dict[str, list[float]] = {n: [] for n in ENGINE_NAMES}

    def _extract_posteriors(self, v2_out: dict, v3_out: dict,
                            v4_out: dict, v5_out: dict) -> dict[str, float]:
        return {
            "v1_det": v2_out["base_posterior"],
            "v2_mc":  v2_out["composite_posterior"],
            "v3_fac": v3_out["composite_posterior"],
            "v4_ens": v4_out["composite_posterior"],
            "v5_ent": v5_out["composite_posterior"],
        }

    def _adaptive_weights(self, posteriors: dict[str, float]) -> dict[str, float]:
        """Blend static priors with inverse-distance-from-median adaptive weights."""
        vals = list(posteriors.values())
        median_p = sorted(vals)[len(vals) // 2]

        inv_dist = {}
        for name, p in posteriors.items():
            dist = abs(p - median_p)
            inv_dist[name] = 1.0 / max(dist, 0.005)

        total_inv = sum(inv_dist.values())
        adaptive = {n: v / total_inv for n, v in inv_dist.items()}

        blended = {}
        for name in ENGINE_NAMES:
            blended[name] = 0.5 * STATIC_WEIGHTS[name] + 0.5 * adaptive[name]

        total = sum(blended.values())
        return {n: v / total for n, v in blended.items()}

    def _meta_collapse(self, posteriors: dict[str, float],
                       weights: dict[str, float]) -> float:
        """Weighted combination with tail-agreement bonus applied in logit space."""
        post_list = list(posteriors.values())
        tail_bonus = tail_agreement_bonus(post_list)

        logit_sum = 0.0
        for name in ENGINE_NAMES:
            p = posteriors[name]
            w = weights[name]
            logit_sum += logit(p) * w

        if tail_bonus > 0 and abs(logit_sum) > 0.3:
            logit_sum *= (1.0 + tail_bonus)

        return inv_logit(logit_sum)

    def update(self, ctx: MarketContext) -> dict:
        ts = ctx.timestamp or time.time()
        self._tick_count += 1

        v2_out = self.v2_engine.update(ctx)
        v3_out = self.v3_engine.update(ctx)
        v4_out = self.v4_engine.update(ctx)
        v5_out = self.v5_engine.update(ctx)

        posteriors = self._extract_posteriors(v2_out, v3_out, v4_out, v5_out)
        weights = self._adaptive_weights(posteriors)
        composite = self._meta_collapse(posteriors, weights)
        composite = max(0.01, min(0.99, composite))

        vals = list(posteriors.values())
        mean_p = sum(vals) / len(vals)
        variance = sum((p - mean_p) ** 2 for p in vals) / len(vals)
        std_dev = math.sqrt(variance)
        agreement = 1.0 - min(std_dev / 0.25, 1.0)

        if agreement < 0.6:
            discount = 0.4 + 0.6 * agreement
            composite = 0.5 + (composite - 0.5) * discount

        veto_active = v2_out.get("veto_active", False)
        veto_reasons = v2_out.get("veto_reasons", [])
        if veto_active:
            composite = min(composite, 0.35)

        composite = max(0.01, min(0.99, composite))

        agreement_matrix = pairwise_agreement_matrix(posteriors)

        bullish = sum(1 for p in vals if p > 0.55)
        bearish = sum(1 for p in vals if p < 0.45)
        if bullish == 5:
            consensus = "STRONG_BULL"
        elif bearish == 5:
            consensus = "STRONG_BEAR"
        elif bullish >= 4:
            consensus = "BULL"
        elif bearish >= 4:
            consensus = "BEAR"
        elif bullish >= 3:
            consensus = "LEAN_BULL"
        elif bearish >= 3:
            consensus = "LEAN_BEAR"
        else:
            consensus = "MIXED"

        confidence_tier = "paper"
        for threshold, tier in CONFIDENCE_ROUTING:
            uncertainty = abs(composite - 0.5) * 2
            if 1 - uncertainty < threshold:
                confidence_tier = tier
                break

        if agreement < 0.4:
            confidence_tier = "paper"

        avg_win = 0.03 * ctx.premium if ctx.premium > 0 else 1.0
        avg_loss = 0.015 * ctx.premium if ctx.premium > 0 else 1.0
        cost = 0.10 * 2
        ev = ev_gate(composite, avg_win, avg_loss, cost)
        kf = kelly_fraction(composite, avg_win / max(avg_loss, 0.01))

        tail_bonus = tail_agreement_bonus(vals)

        result = {
            "version": "v6_meta",
            "composite_posterior": round(composite, 6),
            "engine_posteriors": {n: round(p, 6) for n, p in posteriors.items()},
            "engine_weights": {n: round(w, 4) for n, w in weights.items()},
            "agreement": round(agreement, 4),
            "agreement_matrix": agreement_matrix,
            "std_dev": round(std_dev, 6),
            "consensus": consensus,
            "tail_agreement_bonus": round(tail_bonus, 4),
            "regime": ctx.regime.value,
            "gex_regime": ctx.gex_regime.value,
            "confidence_tier": confidence_tier,
            "kelly_fraction": round(kf, 4),
            "ev": round(ev, 4),
            "mc_regime_forecast": v2_out.get("regime_forecast", {}),
            "v5_active_nodes": v5_out.get("active_nodes", 0),
            "v5_domain_info": v5_out.get("domain_information", {}),
            "live_nodes": v2_out.get("live_nodes", 0),
            "total_nodes": v2_out.get("total_nodes", 200),
            "tick_count": self._tick_count,
            "veto_active": veto_active,
            "veto_reasons": veto_reasons,
        }

        self._history.append({
            "ts": ts,
            "composite": composite,
            **{n: posteriors[n] for n in ENGINE_NAMES},
            "agreement": agreement,
            "consensus": consensus,
        })
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        return result

    def recent_history(self, n: int = 10) -> list[dict]:
        return self._history[-n:]


def run_demo(n_ticks: int = 15):
    engine = BayesianEngineV6Meta(mc_simulations=150)

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

    print("BAYESIAN ENGINE V6 — META-ENSEMBLE (ALL 5 VARIANTS)")
    print("=" * 110)
    print(f"{'Tick':>4}  {'META':>9}  {'V1 Det':>8}  {'V2 MC':>8}"
          f"  {'V3 Fac':>8}  {'V4 Ens':>8}  {'V5 Ent':>8}"
          f"  {'Agree':>6}  {'Consensus':>12}  {'Tier':>7}")
    print("-" * 110)

    regimes = ([Regime.TREND_UP] * 5 + [Regime.CHOP] * 5 +
               [Regime.EXPANSION] * 5)

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
              f"  {ep['v1_det']:8.6f}"
              f"  {ep['v2_mc']:8.6f}"
              f"  {ep['v3_fac']:8.6f}"
              f"  {ep['v4_ens']:8.6f}"
              f"  {ep['v5_ent']:8.6f}"
              f"  {out['agreement']:6.3f}"
              f"  {out['consensus']:>12}"
              f"  {out['confidence_tier']:>7}")

    print(f"\nFinal weights: {out['engine_weights']}")
    print(f"Tail agreement bonus: {out['tail_agreement_bonus']}")
    print(f"V5 active info nodes: {out['v5_active_nodes']}")
    print(f"MC regime forecast: {out['mc_regime_forecast']}")


if __name__ == "__main__":
    run_demo(15)
