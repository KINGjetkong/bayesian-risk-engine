#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Engine v5.0 (Entropy-Weighted)

An information-theoretic collapse strategy that dynamically weights nodes
based on their predictive information content rather than fixed or
regime-dependent weights.

Key mathematical ideas:
  1. Shannon entropy of each node's posterior history → high entropy = noisy = downweight
  2. Kullback-Leibler divergence (prior→posterior) → "surprise" = information gain per tick
  3. Exponential moving average of KL-divergence → sustained information contributors upweighted
  4. Effective sample size via Rényi entropy → guards against dominated-by-one-node collapse
  5. Minimum Description Length (MDL) pruning → deactivates nodes whose contribution
     doesn't justify their complexity cost

The insight: in a 200-node field, most nodes are noise at any given moment.
V1-V4 use structural priors (regime, GEX, domain) to downweight.
V5 lets the DATA decide which nodes matter by measuring actual information flow.

References:
  Barron/Rissanen/Yu (1998) — MDL for model selection
  Kullback/Leibler (1951) — information divergence
  Rényi (1961) — generalized entropy
  Cover/Thomas (2006) — Elements of Information Theory
"""
from __future__ import annotations

import math
import time
import sys
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    BayesianProbabilityEngine,
    MarketContext, Regime, GexRegime, Domain,
    logit, inv_logit, kelly_fraction, ev_gate, CONFIDENCE_ROUTING,
)


def shannon_entropy(p: float) -> float:
    """H(p) = -p·log(p) - (1-p)·log(1-p) for a Bernoulli variable.
    Returns bits. Maximum at p=0.5 (1 bit), minimum at p=0/1 (0 bits)."""
    p = max(min(p, 0.9999), 0.0001)
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def kl_divergence(p: float, q: float) -> float:
    """KL(p || q) for Bernoulli. Measures information gained when
    updating from prior q to posterior p. Always >= 0 (Gibbs' inequality)."""
    p = max(min(p, 0.9999), 0.0001)
    q = max(min(q, 0.9999), 0.0001)
    return p * math.log(p / q) + (1 - p) * math.log((1 - p) / (1 - q))


def renyi_entropy(weights: list[float], alpha: float = 2.0) -> float:
    """Rényi entropy of order alpha on a weight distribution.
    At alpha=2 this is -log(sum(w_i^2)) which relates to the
    effective sample size: ESS = 1/sum(w_i^2) = 2^H_2.
    Higher Rényi entropy → more evenly distributed weights → healthier ensemble."""
    if not weights:
        return 0.0
    total = sum(weights)
    if total <= 0:
        return 0.0
    normed = [w / total for w in weights]
    sum_alpha = sum(w ** alpha for w in normed)
    if sum_alpha <= 0:
        return 0.0
    return (1.0 / (1.0 - alpha)) * math.log2(max(sum_alpha, 1e-15))


def mdl_cost(n_active: int, n_observations: int, residual_entropy: float) -> float:
    """Minimum Description Length cost: model complexity + data fit.
    MDL = (k/2)·log(n) + n·H_residual
    where k = number of active nodes, n = observations,
    H_residual = remaining uncertainty after using those nodes.
    Lower is better. Guides the pruning threshold."""
    if n_observations <= 0 or n_active <= 0:
        return float('inf')
    model_cost = (n_active / 2.0) * math.log2(max(n_observations, 1))
    data_cost = n_observations * residual_entropy
    return model_cost + data_cost


class NodeInfoState:
    """Tracks information-theoretic statistics for a single ProbNode."""
    __slots__ = ('node_id', 'kl_ema', 'entropy_history', 'info_weight',
                 'cumulative_kl', 'ticks_active', 'last_posterior',
                 'last_base_rate', 'mdl_active')

    def __init__(self, node_id: str, base_rate: float = 0.5):
        self.node_id = node_id
        self.kl_ema = 0.0
        self.entropy_history: list[float] = []
        self.info_weight = 1.0
        self.cumulative_kl = 0.0
        self.ticks_active = 0
        self.last_posterior = base_rate
        self.last_base_rate = base_rate
        self.mdl_active = True

    def update(self, posterior: float, base_rate: float, alpha: float = 0.1):
        """Update information statistics after a new observation."""
        self.ticks_active += 1
        self.last_posterior = posterior
        self.last_base_rate = base_rate

        h = shannon_entropy(posterior)
        self.entropy_history.append(h)
        if len(self.entropy_history) > 60:
            self.entropy_history = self.entropy_history[-60:]

        kl = kl_divergence(posterior, base_rate)
        self.kl_ema = alpha * kl + (1 - alpha) * self.kl_ema
        self.cumulative_kl += kl

        mean_entropy = sum(self.entropy_history) / len(self.entropy_history)
        entropy_discount = 1.0 - mean_entropy
        self.info_weight = self.kl_ema * max(entropy_discount, 0.05)


class BayesianEngineV5Entropy:
    """Information-theoretic engine that weights nodes by their measured
    information contribution rather than structural priors.

    Collapse strategy:
      1. Run V1 base engine to get all 200 node posteriors
      2. For each node, compute KL(posterior || base_rate) = information gained
      3. EMA-smooth the KL divergences → sustained contributors dominate
      4. Weight = KL_ema × (1 - mean_entropy) → high info + low noise
      5. MDL pruning: deactivate nodes whose marginal info doesn't justify cost
      6. Rényi entropy check: if effective sample size drops below floor,
         redistribute weight to prevent single-node domination
      7. Collapse: weighted logit-space combination of active nodes
    """

    def __init__(self, mdl_prune: bool = True, renyi_floor: float = 3.0):
        self.base_engine = BayesianProbabilityEngine()
        self.node_states: dict[str, NodeInfoState] = {}
        self.mdl_prune = mdl_prune
        self.renyi_floor = renyi_floor
        self._tick_count = 0
        self._history: list[dict] = []
        self._domain_info: dict[str, float] = defaultdict(float)
        self._last_engine_output = None

    def _ensure_node_states(self):
        """Initialize NodeInfoState for any nodes not yet tracked."""
        for domain, worker in self.base_engine.workers.items():
            for node in worker.nodes:
                if node.id not in self.node_states:
                    self.node_states[node.id] = NodeInfoState(
                        node.id, node.base_rate
                    )

    def _collect_node_posteriors(self) -> dict[str, tuple[float, float, str, float]]:
        """After base engine update, collect (posterior, base_rate, domain, weight)
        for every node."""
        result = {}
        for domain, worker in self.base_engine.workers.items():
            domain_name = domain.value if hasattr(domain, 'value') else str(domain)
            for node in worker.nodes:
                result[node.id] = (
                    node._current_posterior, node.base_rate, domain_name, node.effective_weight
                )
        return result

    def _mdl_pruning(self, node_data: dict[str, tuple]) -> set[str]:
        """MDL-based node selection: keep nodes whose KL information
        exceeds the per-node complexity penalty."""
        if not self.mdl_prune or self._tick_count < 15:
            return set(node_data.keys())

        scored = []
        for nid, (post, base, dom, w) in node_data.items():
            state = self.node_states.get(nid)
            if state and state.ticks_active > 0:
                scored.append((nid, state.kl_ema))

        scored.sort(key=lambda x: x[1], reverse=True)

        complexity_penalty = 0.5 * math.log2(max(self._tick_count, 1)) / max(self._tick_count, 1)

        active_set = set()
        for nid, kl in scored:
            if kl > complexity_penalty or len(active_set) < 20:
                active_set.add(nid)

        for nid in self.node_states:
            self.node_states[nid].mdl_active = nid in active_set

        return active_set

    def _renyi_rebalance(self, weights: dict[str, float]) -> dict[str, float]:
        """If the Rényi effective sample size is below the floor,
        redistribute weight toward equality to prevent domination."""
        if not weights:
            return weights

        vals = list(weights.values())
        h2 = renyi_entropy(vals, alpha=2.0)
        ess = 2.0 ** h2

        if ess >= self.renyi_floor:
            return weights

        n = len(weights)
        target_ess = min(self.renyi_floor, n)

        uniform = {k: 1.0 / n for k in weights}
        total = sum(weights.values()) or 1.0
        current = {k: v / total for k, v in weights.items()}

        blend = min(0.5, (target_ess - ess) / max(target_ess, 1.0))
        rebalanced = {}
        for k in weights:
            rebalanced[k] = (1 - blend) * current[k] + blend * uniform[k]

        rtotal = sum(rebalanced.values()) or 1.0
        return {k: v / rtotal * total for k, v in rebalanced.items()}

    def _entropy_collapse(self, node_data: dict, active_set: set,
                          info_weights: dict) -> float:
        """Collapse active nodes in logit-space using information weights."""
        if not active_set:
            return 0.5

        base_logit = 0.0
        total_w = 0.0

        for nid in active_set:
            if nid not in node_data:
                continue
            post, base, dom, struct_w = node_data[nid]
            iw = info_weights.get(nid, 0.0)
            if iw <= 0:
                continue

            logit_effect = logit(post) - logit(base)
            base_logit += logit_effect * iw
            total_w += iw

        if total_w > 0:
            base_logit /= total_w
            base_logit *= min(total_w, 3.0)

        return inv_logit(base_logit)

    def update(self, ctx: MarketContext) -> dict:
        ts = ctx.timestamp or time.time()
        self._tick_count += 1

        self._last_engine_output = self.base_engine.update(ctx)
        self._ensure_node_states()

        node_data = self._collect_node_posteriors()

        for nid, (post, base, dom, w) in node_data.items():
            state = self.node_states[nid]
            state.update(post, base, alpha=0.12)

        active_set = self._mdl_pruning(node_data)

        raw_weights = {}
        for nid in active_set:
            state = self.node_states.get(nid)
            if state:
                raw_weights[nid] = state.info_weight

        info_weights = self._renyi_rebalance(raw_weights)

        composite = self._entropy_collapse(node_data, active_set, info_weights)

        self._domain_info.clear()
        for nid in active_set:
            if nid in node_data:
                dom = node_data[nid][2]
                self._domain_info[dom] += info_weights.get(nid, 0.0)

        v1_posterior = self._last_engine_output.composite_posterior if self._last_engine_output else 0.5

        blend_alpha = 0.65
        blended = blend_alpha * composite + (1 - blend_alpha) * v1_posterior
        blended = max(0.01, min(0.99, blended))

        veto_active = self._last_engine_output.veto_active if self._last_engine_output else False
        veto_reasons = self._last_engine_output.veto_reasons if self._last_engine_output else []
        if veto_active:
            blended = min(blended, 0.35)

        all_weights = list(info_weights.values())
        h2 = renyi_entropy(all_weights, alpha=2.0) if all_weights else 0.0
        ess = 2.0 ** h2 if all_weights else 0.0

        total_kl = sum(s.kl_ema for s in self.node_states.values())
        mean_entropy_active = 0.0
        if active_set:
            entropies = []
            for nid in active_set:
                st = self.node_states.get(nid)
                if st and st.entropy_history:
                    entropies.append(st.entropy_history[-1])
            if entropies:
                mean_entropy_active = sum(entropies) / len(entropies)

        top_info_nodes = sorted(
            [(nid, info_weights.get(nid, 0)) for nid in active_set],
            key=lambda x: x[1], reverse=True
        )[:10]

        confidence_tier = "paper"
        for threshold, tier in CONFIDENCE_ROUTING:
            uncertainty = abs(blended - 0.5) * 2
            if 1 - uncertainty < threshold:
                confidence_tier = tier
                break

        if ess < 2.0:
            confidence_tier = "paper"

        avg_win = 0.03 * ctx.premium if ctx.premium > 0 else 1.0
        avg_loss = 0.015 * ctx.premium if ctx.premium > 0 else 1.0
        cost = 0.10 * 2
        ev = ev_gate(blended, avg_win, avg_loss, cost)
        kf = kelly_fraction(blended, avg_win / max(avg_loss, 0.01))

        result = {
            "version": "v5_entropy",
            "composite_posterior": round(blended, 6),
            "entropy_posterior": round(composite, 6),
            "base_posterior": round(v1_posterior, 6),
            "blend_alpha": blend_alpha,
            "active_nodes": len(active_set),
            "total_nodes": len(node_data),
            "pruned_nodes": len(node_data) - len(active_set),
            "effective_sample_size": round(ess, 2),
            "renyi_entropy_h2": round(h2, 4),
            "total_kl_divergence": round(total_kl, 6),
            "mean_entropy_active": round(mean_entropy_active, 4),
            "domain_information": {
                d: round(v, 4) for d, v in
                sorted(self._domain_info.items(), key=lambda x: x[1], reverse=True)
            },
            "top_info_nodes": [
                {"node": nid, "info_weight": round(w, 6)} for nid, w in top_info_nodes
            ],
            "regime": ctx.regime.value,
            "gex_regime": ctx.gex_regime.value,
            "confidence_tier": confidence_tier,
            "kelly_fraction": round(kf, 4),
            "ev": round(ev, 4),
            "veto_active": veto_active,
            "veto_reasons": veto_reasons,
            "tick_count": self._tick_count,
        }

        self._history.append({
            "ts": ts,
            "composite": blended,
            "entropy_raw": composite,
            "v1": v1_posterior,
            "active": len(active_set),
            "ess": ess,
        })
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        return result

    def recent_history(self, n: int = 10) -> list[dict]:
        return self._history[-n:]


def run_demo(n_ticks: int = 20):
    engine = BayesianEngineV5Entropy(mdl_prune=True, renyi_floor=3.0)

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

    print("BAYESIAN ENGINE V5 — ENTROPY-WEIGHTED INFORMATION-THEORETIC")
    print("=" * 100)
    print(f"{'Tick':>4}  {'Composite':>9}  {'Entropy':>8}  {'V1 Base':>8}"
          f"  {'Active':>6}  {'Pruned':>6}  {'ESS':>5}  {'TotalKL':>8}"
          f"  {'MeanH':>6}  {'Tier':>7}")
    print("-" * 100)

    regimes = ([Regime.TREND_UP] * 5 + [Regime.CHOP] * 5 +
               [Regime.EXPANSION] * 5 + [Regime.COMPRESSION] * 5)

    for i in range(n_ticks):
        ts = time.time() + i * 15
        ctx_dict = {**base_ctx, "timestamp": ts}
        ctx_dict["price"] += (i % 7) * 0.2 - 0.6
        ctx_dict["cvd_slope"] = 0.8 - (i % 9) * 0.15
        ctx_dict["minutes_since_open"] = 60 + i * 2
        ctx_dict["regime"] = regimes[i % len(regimes)]
        ctx_dict["volume_ratio"] = 1.0 + (i % 5) * 0.3

        if regimes[i % len(regimes)] == Regime.CHOP:
            ctx_dict["obi"] = 0.02
            ctx_dict["vpin"] = 0.45
        elif regimes[i % len(regimes)] == Regime.EXPANSION:
            ctx_dict["obi"] = 0.28
            ctx_dict["volume_ratio"] = 2.2
            ctx_dict["vpin"] = 0.88
        elif regimes[i % len(regimes)] == Regime.COMPRESSION:
            ctx_dict["obi"] = 0.05
            ctx_dict["volume_ratio"] = 0.6
            ctx_dict["premium_velocity"] = 0.02

        ctx = MarketContext(**ctx_dict)
        out = engine.update(ctx)

        print(f"{i+1:4d}  {out['composite_posterior']:9.6f}"
              f"  {out['entropy_posterior']:8.6f}"
              f"  {out['base_posterior']:8.6f}"
              f"  {out['active_nodes']:6d}"
              f"  {out['pruned_nodes']:6d}"
              f"  {out['effective_sample_size']:5.1f}"
              f"  {out['total_kl_divergence']:8.4f}"
              f"  {out['mean_entropy_active']:6.3f}"
              f"  {out['confidence_tier']:>7}")

    print(f"\n--- Domain Information Flow ---")
    for dom, info in out["domain_information"].items():
        bar = "█" * int(info * 200)
        print(f"  {dom:20s}  {info:.4f}  {bar}")

    print(f"\n--- Top 10 Information Nodes ---")
    for entry in out["top_info_nodes"]:
        print(f"  {entry['node']:20s}  info_weight={entry['info_weight']:.6f}")


if __name__ == "__main__":
    run_demo(20)
