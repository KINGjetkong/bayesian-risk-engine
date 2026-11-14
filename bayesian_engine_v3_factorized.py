#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Engine v3.0 (Factorized Shrinkage)

Differences from v1 and v2:
  v1: EMA + logit-space collapse (deterministic)
  v2: Monte Carlo regime prediction + attractor field (stochastic)
  v3: Factorized partial-pooling Bayesian shrinkage with per-condition
      posterior effects in logit-space — directly mirrors the architecture
      of factorized_bayesian_router.py but applied to ALL 200 nodes.

Architecture:
  Each probability node's effect is decomposed into INDEPENDENT FACTORS:
    1. Regime factor effect (what regime adds/subtracts in logit-space)
    2. GEX factor effect (long vs short gamma)
    3. Time-of-day factor effect
    4. Volatility factor effect (VIX bucket)
    5. Node-specific residual effect

  Each factor is learned with SHRINKAGE toward a global mean:
    effect_i = reliability_i × raw_effect_i + (1 - reliability_i) × global_mean

  The factors are ADDITIVE in logit-space (multiplicative in odds-space).
  This prevents correlated signals from over-counting: if 10 order-flow
  nodes all fire because of the same CVD divergence, their effects are
  shrunk toward the domain's pooled mean rather than each adding independently.

  Key mathematical properties:
    - Partial pooling prevents overfitting to rare conditions
    - Logit-space additivity preserves probabilistic coherence
    - Reliability weighting = n/(n+k) naturally handles sparse data
    - Domain-level shrinkage groups correlated features

References:
  Gelman/Hill (2006) — multilevel models
  Efron/Morris (1975) — Stein's paradox and shrinkage
  James/Stein (1961) — admissible estimators
"""
from __future__ import annotations

import math
import time
import sys
import os
from dataclasses import dataclass, field
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    BayesianProbabilityEngine,
    MarketContext,
    Regime,
    GexRegime,
    Domain,
    ProbNode,
    logit,
    inv_logit,
    reliability,
    kelly_fraction,
    ev_gate,
    CONFIDENCE_ROUTING,
)


# ---------------------------------------------------------------------------
# Factor Tables
# ---------------------------------------------------------------------------

class FactorBucket:
    REGIME = "regime"
    GEX = "gex"
    TOD = "tod"
    VIX = "vix"


def tod_bucket(minutes_since_open: int) -> str:
    if minutes_since_open < 30:
        return "open_30"
    elif minutes_since_open < 90:
        return "morning"
    elif minutes_since_open < 210:
        return "midday"
    elif minutes_since_open < 330:
        return "afternoon"
    else:
        return "power_hour"


def vix_bucket(vix: float) -> str:
    if vix < 15:
        return "low"
    elif vix < 20:
        return "normal"
    elif vix < 25:
        return "elevated"
    elif vix < 30:
        return "high"
    else:
        return "extreme"


# ---------------------------------------------------------------------------
# Shrinkage Estimator
# ---------------------------------------------------------------------------

@dataclass
class FactorEffect:
    raw_sum: float = 0.0
    count: int = 0
    min_support: int = 8

    @property
    def raw_mean(self) -> float:
        if self.count == 0:
            return 0.0
        return self.raw_sum / self.count

    @property
    def reliability(self) -> float:
        return self.count / (self.count + self.min_support)

    def shrunk_effect(self, global_mean: float) -> float:
        r = self.reliability
        return r * self.raw_mean + (1 - r) * global_mean

    def observe(self, logit_effect: float) -> None:
        self.raw_sum += logit_effect
        self.count += 1


class FactorTable:
    def __init__(self, min_support: int = 8):
        self.min_support = min_support
        self._effects: dict[str, dict[str, FactorEffect]] = defaultdict(
            lambda: defaultdict(lambda: FactorEffect(min_support=self.min_support))
        )
        self._global_effects: dict[str, FactorEffect] = defaultdict(
            lambda: FactorEffect(min_support=self.min_support)
        )

    def observe(self, factor_type: str, bucket: str,
                logit_effect: float) -> None:
        self._effects[factor_type][bucket].observe(logit_effect)
        self._global_effects[factor_type].observe(logit_effect)

    def get_shrunk_effect(self, factor_type: str, bucket: str) -> float:
        global_mean = self._global_effects[factor_type].raw_mean
        return self._effects[factor_type][bucket].shrunk_effect(global_mean)

    def get_reliability(self, factor_type: str, bucket: str) -> float:
        return self._effects[factor_type][bucket].reliability

    def summary(self) -> dict:
        result = {}
        for ftype, buckets in self._effects.items():
            result[ftype] = {}
            for bucket, effect in buckets.items():
                result[ftype][bucket] = {
                    "raw_mean": round(effect.raw_mean, 4),
                    "count": effect.count,
                    "reliability": round(effect.reliability, 4),
                    "shrunk": round(
                        effect.shrunk_effect(
                            self._global_effects[ftype].raw_mean
                        ), 4
                    ),
                }
        return result


# ---------------------------------------------------------------------------
# Domain Shrinkage Pool
# ---------------------------------------------------------------------------

class DomainPool:
    def __init__(self, min_support: int = 12):
        self.min_support = min_support
        self._domain_sums: dict[str, float] = defaultdict(float)
        self._domain_counts: dict[str, int] = defaultdict(int)
        self._global_sum: float = 0.0
        self._global_count: int = 0

    def observe(self, domain: str, logit_effect: float) -> None:
        self._domain_sums[domain] += logit_effect
        self._domain_counts[domain] += 1
        self._global_sum += logit_effect
        self._global_count += 1

    def shrunk_domain_effect(self, domain: str) -> float:
        n = self._domain_counts[domain]
        r = n / (n + self.min_support)
        domain_mean = (self._domain_sums[domain] / n) if n > 0 else 0.0
        global_mean = (self._global_sum / self._global_count
                       if self._global_count > 0 else 0.0)
        return r * domain_mean + (1 - r) * global_mean


# ---------------------------------------------------------------------------
# V3 Engine
# ---------------------------------------------------------------------------

class BayesianEngineV3:
    def __init__(self):
        self.base_engine = BayesianProbabilityEngine()
        self.factor_table = FactorTable(min_support=8)
        self.domain_pool = DomainPool(min_support=12)
        self._tick_count = 0

    def update(self, ctx: MarketContext) -> dict:
        ts = ctx.timestamp or time.time()

        # Step 1: Run base engine to populate all node posteriors
        base_output = self.base_engine.update(ctx)
        self._tick_count += 1

        # Step 2: Extract current factor buckets
        regime_key = ctx.regime.value
        gex_key = ctx.gex_regime.value
        tod_key = tod_bucket(ctx.minutes_since_open)
        vix_key = vix_bucket(ctx.vix)

        # Step 3: For each live node, decompose into factor effects
        # and observe them in the factor table
        domain_effects: dict[str, list[float]] = defaultdict(list)

        for node in self.base_engine.nodes.values():
            if not node._is_live:
                continue

            effect = node.logit_effect
            weight = node.effective_weight

            if weight <= 0:
                continue

            # Observe effect in factor tables
            self.factor_table.observe(FactorBucket.REGIME, regime_key, effect)
            self.factor_table.observe(FactorBucket.GEX, gex_key, effect)
            self.factor_table.observe(FactorBucket.TOD, tod_key, effect)
            self.factor_table.observe(FactorBucket.VIX, vix_key, effect)

            # Observe in domain pool
            self.domain_pool.observe(node.domain.value, effect)

            domain_effects[node.domain.value].append(effect * weight)

        # Step 4: Compute shrunk factor effects
        regime_effect = self.factor_table.get_shrunk_effect(
            FactorBucket.REGIME, regime_key
        )
        gex_effect = self.factor_table.get_shrunk_effect(
            FactorBucket.GEX, gex_key
        )
        tod_effect = self.factor_table.get_shrunk_effect(
            FactorBucket.TOD, tod_key
        )
        vix_effect = self.factor_table.get_shrunk_effect(
            FactorBucket.VIX, vix_key
        )

        # Step 5: Compute shrunk domain effects
        shrunk_domain_posteriors = {}
        for domain_name, effects in domain_effects.items():
            domain_shrunk = self.domain_pool.shrunk_domain_effect(domain_name)
            shrunk_domain_posteriors[domain_name] = inv_logit(
                logit(0.5) + domain_shrunk
            )

        # Step 6: Factorized collapse
        # Sum all shrunk factor effects in logit-space
        total_logit_effect = (
            regime_effect +
            gex_effect +
            tod_effect * 0.5 +  # lower weight for time-of-day
            vix_effect * 0.3    # lower weight for VIX
        )

        factorized_posterior = inv_logit(logit(0.5) + total_logit_effect)

        # Step 7: Blend with base engine (60% factorized, 40% base)
        composite = 0.60 * factorized_posterior + 0.40 * base_output.composite_posterior
        composite = min(max(composite, 0.01), 0.99)

        # Apply vetoes
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

        # Factor reliabilities
        factor_reliabilities = {
            "regime": round(
                self.factor_table.get_reliability(
                    FactorBucket.REGIME, regime_key), 4
            ),
            "gex": round(
                self.factor_table.get_reliability(
                    FactorBucket.GEX, gex_key), 4
            ),
            "tod": round(
                self.factor_table.get_reliability(
                    FactorBucket.TOD, tod_key), 4
            ),
            "vix": round(
                self.factor_table.get_reliability(
                    FactorBucket.VIX, vix_key), 4
            ),
        }

        return {
            "version": "v3_factorized_shrinkage",
            "composite_posterior": round(composite, 6),
            "factorized_posterior": round(factorized_posterior, 6),
            "base_posterior": round(base_output.composite_posterior, 6),
            "factor_effects": {
                "regime": round(regime_effect, 4),
                "gex": round(gex_effect, 4),
                "tod": round(tod_effect, 4),
                "vix": round(vix_effect, 4),
                "total_logit": round(total_logit_effect, 4),
            },
            "factor_reliabilities": factor_reliabilities,
            "shrunk_domain_posteriors": {
                k: round(v, 4) for k, v in shrunk_domain_posteriors.items()
            },
            "regime": ctx.regime.value,
            "gex_regime": ctx.gex_regime.value,
            "tod_bucket": tod_key,
            "vix_bucket": vix_key,
            "confidence_tier": confidence_tier,
            "kelly_fraction": round(kf, 4),
            "ev": round(ev, 4),
            "tick_count": self._tick_count,
            "live_nodes": base_output.live_node_count,
            "total_nodes": base_output.total_node_count,
            "veto_active": base_output.veto_active,
            "veto_reasons": base_output.veto_reasons,
        }


# ---------------------------------------------------------------------------
# Multi-tick simulation (demonstrates convergence over rolling updates)
# ---------------------------------------------------------------------------

def simulate_rolling_ticks(n_ticks: int = 20):
    engine = BayesianEngineV3()

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

    print(f"{'Tick':>4}  {'Composite':>10}  {'Factorized':>11}  {'Base':>8}"
          f"  {'Live':>5}  {'Regime R':>9}  {'GEX R':>7}  {'Tier':>7}")
    print("-" * 78)

    for i in range(n_ticks):
        ts = time.time() + i * 15  # 15-sec intervals
        # Slightly vary inputs to simulate live data
        ctx_dict = {**base_ctx, "timestamp": ts}
        ctx_dict["price"] += (i % 5) * 0.1 - 0.25
        ctx_dict["cvd_slope"] += (i % 3) * 0.2 - 0.2
        ctx_dict["minutes_since_open"] = 60 + i

        ctx = MarketContext(**ctx_dict)
        out = engine.update(ctx)

        print(f"{i+1:4d}  {out['composite_posterior']:10.6f}"
              f"  {out['factorized_posterior']:11.6f}"
              f"  {out['base_posterior']:8.6f}"
              f"  {out['live_nodes']:5d}"
              f"  {out['factor_reliabilities']['regime']:9.4f}"
              f"  {out['factor_reliabilities']['gex']:7.4f}"
              f"  {out['confidence_tier']:>7}")

    print(f"\nFinal factor effects: {out['factor_effects']}")
    print(f"Shrunk domain posteriors: {out['shrunk_domain_posteriors']}")


if __name__ == "__main__":
    simulate_rolling_ticks(20)
