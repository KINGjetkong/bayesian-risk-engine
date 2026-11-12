#!/usr/bin/env python3 -I
"""MadTrades V6 — Engine Benchmarking Suite

Runs all 6 Bayesian engine variants through identical market scenarios
and outputs a structured comparison report. Reusable script for rapid
iteration: change the scenario config, re-run, compare.

Usage:
  python3 -I bench_engines.py                    # default 30-tick mixed scenario
  python3 -I bench_engines.py --ticks 50         # custom tick count
  python3 -I bench_engines.py --regime trend_up   # single regime
  python3 -I bench_engines.py --json              # JSON output for pipeline
  python3 -I bench_engines.py --csv               # CSV output for spreadsheet
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    BayesianProbabilityEngine, MarketContext, Regime, GexRegime,
)
from bayesian_engine_v2_montecarlo import BayesianEngineV2
from bayesian_engine_v3_factorized import BayesianEngineV3
from bayesian_engine_v4_ensemble import BayesianEngineV4Ensemble
from bayesian_engine_v5_entropy import BayesianEngineV5Entropy
from bayesian_engine_v6_meta import BayesianEngineV6Meta

REGIME_MAP = {
    "trend_up": Regime.TREND_UP,
    "trend_down": Regime.TREND_DOWN,
    "chop": Regime.CHOP,
    "expansion": Regime.EXPANSION,
    "compression": Regime.COMPRESSION,
}

REGIME_CYCLE = [
    Regime.TREND_UP, Regime.TREND_UP, Regime.TREND_UP,
    Regime.CHOP, Regime.CHOP, Regime.CHOP,
    Regime.EXPANSION, Regime.EXPANSION,
    Regime.COMPRESSION, Regime.COMPRESSION,
    Regime.TREND_DOWN, Regime.TREND_DOWN,
]


def make_context(tick: int, n_ticks: int, regime_override: Regime | None = None) -> MarketContext:
    regime = regime_override or REGIME_CYCLE[tick % len(REGIME_CYCLE)]
    phase = tick / max(n_ticks - 1, 1)

    price = 480.50 + math.sin(phase * math.pi * 2) * 3.0
    cvd = 0.8 - (tick % 9) * 0.15
    vol_ratio = 1.0 + 0.5 * math.sin(phase * math.pi * 4)

    if regime == Regime.CHOP:
        obi, vpin, vol_ratio = 0.02, 0.45, 0.7
    elif regime == Regime.EXPANSION:
        obi, vpin, vol_ratio = 0.28, 0.88, 2.2
    elif regime == Regime.COMPRESSION:
        obi, vpin, vol_ratio = 0.05, 0.55, 0.5
    elif regime == Regime.TREND_DOWN:
        obi, vpin, cvd = -0.15, 0.72, -0.6
    else:
        obi, vpin = 0.15, 0.65

    return MarketContext(
        price=price, vwap=price - 0.5, ema9=price + 0.2, ema20=price - 0.3,
        ema144=price - 2.0, rsi_14=55 + 10 * math.sin(phase * math.pi),
        atr_14=2.5, bb_upper=price + 3.0, bb_lower=price - 3.0,
        volume_ratio=vol_ratio, cvd_slope=cvd, vpin=vpin, obi=obi,
        spread_bps=5.0, option_delta=0.45, option_gamma=0.08,
        option_theta=-0.35, option_iv=22.0, premium=1.85,
        premium_velocity=0.12, premium_acceleration=0.03,
        premium_in_band=True, gex=5e8, put_call_ratio=0.9,
        zero_dte_volume_ratio=1.2,
        regime=regime, gex_regime=GexRegime.LONG_GAMMA,
        vix=18.0, es_price=5350.0, nq_price=18800.0, es_nq_basis=2.5,
        futures_spot_corr=0.995, minutes_since_open=60 + tick * 2,
        ib_high=price + 1.0, ib_low=price - 1.0, prev_day_poc=price - 1.0,
        opening_gap_pct=0.3, dte=0,
        bid_depth_l1=500.0, ask_depth_l1=450.0,
        timestamp=time.time() + tick * 15,
    )


def run_benchmark(n_ticks: int = 30, regime_override: str | None = None,
                  output_format: str = "table") -> list[dict]:
    regime = REGIME_MAP.get(regime_override) if regime_override else None

    v1 = BayesianProbabilityEngine()
    v2 = BayesianEngineV2(n_simulations=200)
    v3 = BayesianEngineV3()
    v4 = BayesianEngineV4Ensemble(mc_simulations=200)
    v5 = BayesianEngineV5Entropy(mdl_prune=True, renyi_floor=3.0)
    v6 = BayesianEngineV6Meta(mc_simulations=150)

    results = []

    for i in range(n_ticks):
        ctx = make_context(i, n_ticks, regime)

        t0 = time.perf_counter()
        o1 = v1.update(ctx)
        t1 = time.perf_counter()
        o2 = v2.update(ctx)
        t2 = time.perf_counter()
        o3 = v3.update(ctx)
        t3 = time.perf_counter()
        o4 = v4.update(ctx)
        t4 = time.perf_counter()
        o5 = v5.update(ctx)
        t5 = time.perf_counter()
        o6 = v6.update(ctx)
        t6 = time.perf_counter()

        row = {
            "tick": i + 1,
            "regime": ctx.regime.value,
            "v1": round(o1.composite_posterior, 6),
            "v2": round(o2["composite_posterior"], 6),
            "v3": round(o3["composite_posterior"], 6),
            "v4": round(o4["composite_posterior"], 6),
            "v5": round(o5["composite_posterior"], 6),
            "v6": round(o6["composite_posterior"], 6),
            "agreement_v4": round(o4["agreement"], 4),
            "agreement_v6": round(o6["agreement"], 4),
            "consensus_v6": o6["consensus"],
            "v5_active": o5["active_nodes"],
            "tier_v6": o6["confidence_tier"],
            "ms_v1": round((t1 - t0) * 1000, 1),
            "ms_v2": round((t2 - t1) * 1000, 1),
            "ms_v3": round((t3 - t2) * 1000, 1),
            "ms_v4": round((t4 - t3) * 1000, 1),
            "ms_v5": round((t5 - t4) * 1000, 1),
            "ms_v6": round((t6 - t5) * 1000, 1),
        }
        results.append(row)

    if output_format == "table":
        print_table(results)
    elif output_format == "json":
        print(json.dumps(results, indent=2))
    elif output_format == "csv":
        print_csv(results)

    print_summary(results)
    return results


def print_table(results: list[dict]):
    print("\n" + "=" * 130)
    print("BAYESIAN ENGINE BENCHMARK — ALL 6 VARIANTS")
    print("=" * 130)
    print(f"{'Tick':>4}  {'Regime':>12}  {'V1':>8}  {'V2':>8}  {'V3':>8}"
          f"  {'V4':>8}  {'V5':>8}  {'V6':>8}  {'Agr6':>5}"
          f"  {'Consensus':>12}  {'Tier':>7}  {'V5act':>5}")
    print("-" * 130)
    for r in results:
        print(f"{r['tick']:4d}  {r['regime']:>12}"
              f"  {r['v1']:8.6f}  {r['v2']:8.6f}  {r['v3']:8.6f}"
              f"  {r['v4']:8.6f}  {r['v5']:8.6f}  {r['v6']:8.6f}"
              f"  {r['agreement_v6']:5.3f}"
              f"  {r['consensus_v6']:>12}  {r['tier_v6']:>7}"
              f"  {r['v5_active']:5d}")


def print_csv(results: list[dict]):
    if not results:
        return
    keys = list(results[0].keys())
    print(",".join(keys))
    for r in results:
        print(",".join(str(r[k]) for k in keys))


def print_summary(results: list[dict]):
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    for eng in ["v1", "v2", "v3", "v4", "v5", "v6"]:
        vals = [r[eng] for r in results]
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / len(vals))
        mn, mx = min(vals), max(vals)
        print(f"  {eng.upper():>4}  mean={mean:.4f}  std={std:.4f}  "
              f"range=[{mn:.4f}, {mx:.4f}]")

    print(f"\n  V4 Agreement  mean={sum(r['agreement_v4'] for r in results)/len(results):.3f}")
    print(f"  V6 Agreement  mean={sum(r['agreement_v6'] for r in results)/len(results):.3f}")

    latencies = {}
    for eng in ["v1", "v2", "v3", "v4", "v5", "v6"]:
        key = f"ms_{eng}"
        vals = [r[key] for r in results]
        latencies[eng] = sum(vals) / len(vals)
    print(f"\n  Latency (ms/tick avg):")
    for eng, ms in latencies.items():
        print(f"    {eng.upper()}: {ms:.1f}ms")
    total = sum(latencies.values())
    print(f"    TOTAL: {total:.1f}ms")

    by_regime = {}
    for r in results:
        reg = r["regime"]
        if reg not in by_regime:
            by_regime[reg] = []
        by_regime[reg].append(r["v6"])
    print(f"\n  V6 Composite by Regime:")
    for reg, vals in sorted(by_regime.items()):
        mean = sum(vals) / len(vals)
        print(f"    {reg:>15}: {mean:.4f} (n={len(vals)})")


def main():
    parser = argparse.ArgumentParser(description="Benchmark all 6 Bayesian engines")
    parser.add_argument("--ticks", type=int, default=30, help="Number of ticks")
    parser.add_argument("--regime", choices=list(REGIME_MAP.keys()), help="Override regime")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--csv", action="store_true", help="CSV output")
    args = parser.parse_args()

    fmt = "json" if args.json else "csv" if args.csv else "table"
    run_benchmark(args.ticks, args.regime, fmt)


if __name__ == "__main__":
    main()
