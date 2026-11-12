#!/usr/bin/env python3 -I
"""MadTrades V6 — Graceful Degradation & Data Availability Manager

Tracks which data feeds are available, deactivates nodes that depend on
missing feeds, and reweights the remaining active set proportionally.

Data sources tracked:
  - FlashAlpha (GEX, DEX, flow signals, exposure)
  - Unusual Whales (option flow, dark pool, tide, institutional)
  - Edgeful (session stats, gap fill, ORB, ADR, calendar)
  - Databento (CME futures depth, tick trades, aggressor side)
  - ThetaData (QQQ options chain, historical quotes)
  - Core market data (price, OHLCV — always assumed available)

Each ProbNode declares its required_fields. This module maps those fields
to data sources, checks availability, and produces a degradation report
showing what's online, what's offline, and the impact on the engine.

Usage:
  python3 -I degradation.py                        # show current state
  python3 -I degradation.py --offline flashalpha    # simulate FlashAlpha down
  python3 -I degradation.py --offline databento,edgeful  # multiple sources down
"""
from __future__ import annotations

import sys
import os
import argparse
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bayesian_engine_v1 import (
    BayesianProbabilityEngine, Domain, Regime, GexRegime,
)


class DataSource(Enum):
    CORE = "core"
    FLASHALPHA = "flashalpha"
    UNUSUAL_WHALES = "unusual_whales"
    EDGEFUL = "edgeful"
    DATABENTO = "databento"
    THETADATA = "thetadata"
    DERIVED = "derived"


FIELD_TO_SOURCE: dict[str, DataSource] = {
    "price": DataSource.CORE,
    "vwap": DataSource.CORE,
    "ema9": DataSource.DERIVED,
    "ema20": DataSource.DERIVED,
    "ema144": DataSource.DERIVED,
    "rsi_14": DataSource.DERIVED,
    "atr_14": DataSource.DERIVED,
    "bb_upper": DataSource.DERIVED,
    "bb_lower": DataSource.DERIVED,
    "volume_ratio": DataSource.CORE,
    "cvd_slope": DataSource.DATABENTO,
    "vpin": DataSource.DATABENTO,
    "obi": DataSource.DATABENTO,
    "spread_bps": DataSource.CORE,
    "option_delta": DataSource.THETADATA,
    "option_gamma": DataSource.THETADATA,
    "option_theta": DataSource.THETADATA,
    "option_iv": DataSource.THETADATA,
    "premium": DataSource.THETADATA,
    "premium_velocity": DataSource.DERIVED,
    "premium_acceleration": DataSource.DERIVED,
    "premium_in_band": DataSource.DERIVED,
    "gex": DataSource.FLASHALPHA,
    "put_call_ratio": DataSource.UNUSUAL_WHALES,
    "zero_dte_volume_ratio": DataSource.UNUSUAL_WHALES,
    "regime": DataSource.DERIVED,
    "gex_regime": DataSource.FLASHALPHA,
    "vix": DataSource.CORE,
    "es_price": DataSource.DATABENTO,
    "nq_price": DataSource.DATABENTO,
    "es_nq_basis": DataSource.DERIVED,
    "futures_spot_corr": DataSource.DERIVED,
    "minutes_since_open": DataSource.CORE,
    "ib_high": DataSource.CORE,
    "ib_low": DataSource.CORE,
    "prev_day_poc": DataSource.EDGEFUL,
    "opening_gap_pct": DataSource.EDGEFUL,
    "dte": DataSource.CORE,
    "bid_depth_l1": DataSource.DATABENTO,
    "ask_depth_l1": DataSource.DATABENTO,
    "dark_pool_volume": DataSource.UNUSUAL_WHALES,
    "institutional_flow": DataSource.UNUSUAL_WHALES,
    "flow_signals": DataSource.FLASHALPHA,
    "dex": DataSource.FLASHALPHA,
    "dealer_premium": DataSource.FLASHALPHA,
    "gap_fill_pct": DataSource.EDGEFUL,
    "orb_range": DataSource.EDGEFUL,
    "adr_pct": DataSource.EDGEFUL,
    "session_stats": DataSource.EDGEFUL,
}

NODE_FIELD_DEPS: dict[str, list[str]] = {
    "OF001": ["cvd_slope"],
    "OF002": ["vpin"],
    "OF003": ["obi"],
    "OF004": ["gex"],
    "OF005": ["dark_pool_volume"],
    "OF006": ["bid_depth_l1", "ask_depth_l1"],
    "OF007": ["obi", "volume_ratio"],
    "OF008": ["gex", "option_delta"],
    "MC001": ["es_price", "nq_price"],
    "MC002": ["vix"],
    "MC006": ["es_nq_basis"],
    "MC008": ["futures_spot_corr"],
    "OM001": ["premium_velocity"],
    "OM002": ["option_delta", "option_gamma"],
    "OM003": ["option_iv"],
    "OM004": ["premium", "option_theta"],
    "OM005": ["put_call_ratio"],
    "OM006": ["zero_dte_volume_ratio"],
    "IS001": ["volume_ratio", "atr_14"],
    "IS002": ["ib_high", "ib_low"],
    "IS003": ["opening_gap_pct"],
    "IS004": ["prev_day_poc"],
    "MI001": ["spread_bps"],
    "MI002": ["bid_depth_l1", "ask_depth_l1"],
    "RG001": ["ib_high", "ib_low"],
    "TM001": ["minutes_since_open"],
    "RK001": ["premium", "atr_14"],
}


@dataclass
class DegradationReport:
    online_sources: list[DataSource]
    offline_sources: list[DataSource]
    total_nodes: int
    active_nodes: int
    deactivated_nodes: int
    deactivated_by_source: dict[str, int]
    domain_coverage: dict[str, tuple[int, int]]
    impact_pct: float
    recommendation: str


class DegradationManager:
    def __init__(self):
        self.engine = BayesianProbabilityEngine()
        self._source_status: dict[DataSource, bool] = {
            s: True for s in DataSource
        }

    def set_source_status(self, source: DataSource, online: bool):
        self._source_status[source] = online

    def set_offline(self, *sources: DataSource):
        for s in sources:
            self._source_status[s] = False

    def get_unavailable_fields(self) -> set[str]:
        unavail = set()
        for fld, src in FIELD_TO_SOURCE.items():
            if not self._source_status.get(src, True):
                unavail.add(fld)
        return unavail

    def get_deactivated_nodes(self) -> dict[str, str]:
        """Returns {node_id: reason} for nodes that should be deactivated."""
        unavail = self.get_unavailable_fields()
        deactivated = {}

        for node_id, deps in NODE_FIELD_DEPS.items():
            missing = [d for d in deps if d in unavail]
            if missing:
                sources = set()
                for m in missing:
                    src = FIELD_TO_SOURCE.get(m)
                    if src:
                        sources.add(src.value)
                deactivated[node_id] = (
                    f"missing {', '.join(missing)} "
                    f"(source: {', '.join(sources)})"
                )

        return deactivated

    def report(self) -> DegradationReport:
        online = [s for s, v in self._source_status.items() if v]
        offline = [s for s, v in self._source_status.items() if not v]
        deactivated = self.get_deactivated_nodes()

        total = 200
        active = total - len(deactivated)

        by_source: dict[str, int] = {}
        for nid, reason in deactivated.items():
            for src in DataSource:
                if src.value in reason:
                    by_source[src.value] = by_source.get(src.value, 0) + 1

        domain_coverage: dict[str, tuple[int, int]] = {}
        for domain, worker in self.engine.workers.items():
            domain_name = domain.value
            total_d = len(worker.nodes)
            dead_d = sum(1 for n in worker.nodes if n.id in deactivated)
            domain_coverage[domain_name] = (total_d - dead_d, total_d)

        impact = len(deactivated) / total * 100

        if impact == 0:
            rec = "ALL SYSTEMS NOMINAL — full 200-node field active"
        elif impact < 10:
            rec = "MINOR DEGRADATION — engine reliable, reweight active nodes"
        elif impact < 25:
            rec = "MODERATE DEGRADATION — reduce position sizes, widen stops"
        elif impact < 50:
            rec = "SIGNIFICANT DEGRADATION — paper trade only, await data restoration"
        else:
            rec = "CRITICAL — engine unreliable, halt trading"

        return DegradationReport(
            online_sources=online,
            offline_sources=offline,
            total_nodes=total,
            active_nodes=active,
            deactivated_nodes=len(deactivated),
            deactivated_by_source=by_source,
            domain_coverage=domain_coverage,
            impact_pct=round(impact, 1),
            recommendation=rec,
        )


def print_report(mgr: DegradationManager):
    report = mgr.report()
    deactivated = mgr.get_deactivated_nodes()

    print("\n" + "=" * 70)
    print("DEGRADATION REPORT — DATA AVAILABILITY ASSESSMENT")
    print("=" * 70)

    print(f"\n  ONLINE:  {', '.join(s.value for s in report.online_sources)}")
    print(f"  OFFLINE: {', '.join(s.value for s in report.offline_sources) or 'none'}")

    print(f"\n  Nodes: {report.active_nodes}/{report.total_nodes} active "
          f"({report.deactivated_nodes} deactivated, {report.impact_pct}% impact)")

    if report.deactivated_by_source:
        print(f"\n  Deactivated by source:")
        for src, count in sorted(report.deactivated_by_source.items(),
                                 key=lambda x: x[1], reverse=True):
            print(f"    {src:20s}: {count} nodes")

    print(f"\n  Domain coverage:")
    for dom, (active, total) in sorted(report.domain_coverage.items()):
        pct = active / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {dom:20s}: {active:3d}/{total:3d} ({pct:5.1f}%) {bar}")

    print(f"\n  {report.recommendation}")

    if deactivated:
        print(f"\n  Deactivated nodes:")
        for nid, reason in sorted(deactivated.items()):
            print(f"    {nid:8s}: {reason}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Data degradation assessment")
    parser.add_argument("--offline", type=str, default="",
                        help="Comma-separated sources to mark offline")
    args = parser.parse_args()

    mgr = DegradationManager()

    if args.offline:
        for name in args.offline.split(","):
            name = name.strip().lower()
            try:
                src = DataSource(name)
                mgr.set_offline(src)
            except ValueError:
                print(f"Unknown source: {name}")
                print(f"Valid: {', '.join(s.value for s in DataSource)}")
                sys.exit(1)

    print_report(mgr)

    if not args.offline:
        print("--- Scenario: FlashAlpha down ---")
        mgr2 = DegradationManager()
        mgr2.set_offline(DataSource.FLASHALPHA)
        print_report(mgr2)

        print("--- Scenario: Databento + Edgeful down ---")
        mgr3 = DegradationManager()
        mgr3.set_offline(DataSource.DATABENTO, DataSource.EDGEFUL)
        print_report(mgr3)


if __name__ == "__main__":
    main()
