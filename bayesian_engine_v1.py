#!/usr/bin/env python3 -I
"""MadTrades V6 — Continuous Rolling Bayesian Probability Engine v1.0

Architecture:
  8 parallel Bayesian domain workers collapse 250+ probability nodes into a
  single posterior estimate per tick.  Each node carries:
    - a LogNormal base-rate prior (from the Institutional Research Report)
    - a regime-dependent multiplier
    - a reliability weight (n / (n + min_support))
    - a 15-min rolling decay half-life

  Nodes are NOT binary gates.  Every node emits a continuous [0,1] posterior
  that is combined in logit-space (additive = multiplicative in odds) with
  mean-effect shrinkage to prevent correlated features from amplifying a
  single market move into false certainty.

  The engine runs three collapse layers:
    1. Domain posteriors (8 workers) — per-domain logit-mean
    2. Regime-weighted blend — V9_HYBRID_BLEND weights
    3. Monte Carlo forward projection — 15-min rolling regime forecast

  Graceful degradation: any data source can be absent.  The engine tracks
  which nodes are LIVE vs DARK and adjusts effective support accordingly.

References:
  Hasbrouck (1991) — information content of trades
  Easley/Lopez de Prado/O'Hara (2012) — VPIN / flow toxicity
  Cont/Kukanov/Stoikov (2014) — order book price impact
  Barbon/Buraschi (2020) — gamma fragility
  Bondarenko/Gonzalez-Perez (2024) — 0DTE volatility suppression
  Heston/Korajczyk/Sadka (2010) — intraday return patterns
  Black/Scholes (1973) — options pricing / expected move
  Ni/Pearson/Poteshman (2005) — OPEX pinning
  Kyle (1985) — lambda / price impact
  Brunnermeier/Pedersen (2009) — liquidity spirals
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------

def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def inv_logit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 30), -30)))


def ema_update(old: float, new: float, alpha: float) -> float:
    return alpha * new + (1 - alpha) * old


def half_life_alpha(half_life_seconds: float, dt_seconds: float) -> float:
    if half_life_seconds <= 0 or dt_seconds <= 0:
        return 1.0
    return 1.0 - math.exp(-0.693147 * dt_seconds / half_life_seconds)


def reliability(n: int, min_support: int = 12) -> float:
    return n / (n + min_support)


def kelly_fraction(p: float, win_loss_ratio: float) -> float:
    if win_loss_ratio <= 0:
        return 0.0
    f = p - (1 - p) / win_loss_ratio
    return max(0.0, min(f, 1.0))


def break_even_move(delta: float, gamma: float, cost_rt: float,
                    theta: float, hold_seconds: float) -> float:
    h = hold_seconds / 3600.0
    abs_theta_h = abs(theta) * h
    disc = delta * delta + 2 * gamma * (cost_rt + abs_theta_h)
    if disc < 0 or gamma == 0:
        return float('inf')
    return (-delta + math.sqrt(disc)) / gamma


def ev_gate(p_hat: float, avg_win: float, avg_loss: float,
            cost: float) -> float:
    return p_hat * avg_win - (1 - p_hat) * avg_loss - cost


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

class Regime(Enum):
    CHOP = "chop"
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    EXPANSION = "expansion"
    COMPRESSION = "compression"
    UNKNOWN = "unknown"


class GexRegime(Enum):
    LONG_GAMMA = "long_gamma"
    SHORT_GAMMA = "short_gamma"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class Domain(Enum):
    ORDER_FLOW = "order_flow"
    INTRADAY_STATS = "intraday_stats"
    MACRO_CROSS = "macro_cross"
    OPTIONS_MECHANICS = "options_mechanics"
    MICROSTRUCTURE = "microstructure"
    REGIME = "regime"
    TIMING = "timing"
    RISK = "risk"


V9_HYBRID_BLEND = {
    "domain_score": 0.40,
    "rules_adjustment": 0.35,
    "bayesian_posterior": 0.25,
}

REGIME_MULTIPLIERS = {
    Regime.CHOP: {"momentum": 0.4, "reversion": 1.6, "breakout": 0.3},
    Regime.TREND_UP: {"momentum": 1.5, "reversion": 0.5, "breakout": 1.2},
    Regime.TREND_DOWN: {"momentum": 1.5, "reversion": 0.5, "breakout": 1.2},
    Regime.EXPANSION: {"momentum": 1.3, "reversion": 0.6, "breakout": 1.5},
    Regime.COMPRESSION: {"momentum": 0.5, "reversion": 1.4, "breakout": 0.4},
    Regime.UNKNOWN: {"momentum": 1.0, "reversion": 1.0, "breakout": 1.0},
}

CONFIDENCE_ROUTING = [
    (0.12, "full"),
    (0.22, "half"),
    (0.35, "quarter"),
    (1.00, "paper"),
]

PATH_SCORE_WEIGHTS = {
    "velocity": 0.22, "acceleration": 0.16, "vpump": 0.13,
    "gex_thrust": 0.13, "atr": 0.13, "cross_asset": 0.12,
    "m5": 0.09, "tod": -0.06,
}


# ---------------------------------------------------------------------------
# Probability Node
# ---------------------------------------------------------------------------

@dataclass
class ProbNode:
    id: str
    domain: Domain
    description: str
    base_rate: float
    prior_update: float
    priority: int  # 1-5
    source: str
    verdict: str  # TRUE, PARTIALLY_TRUE, UNVERIFIED, FALSE
    strategy_role: str  # entry, exit, veto, sizing, context, routing

    regime_mults: dict[Regime, float] = field(default_factory=dict)
    gex_mults: dict[GexRegime, float] = field(default_factory=dict)
    required_fields: list[str] = field(default_factory=list)
    half_life_sec: float = 900.0  # 15-min default

    _current_posterior: float = 0.5
    _last_update_ts: float = 0.0
    _is_live: bool = False
    _observation_count: int = 0

    @property
    def effective_weight(self) -> float:
        rel = reliability(self._observation_count)
        p_weight = self.priority / 5.0
        v_weight = {"TRUE": 1.0, "PARTIALLY_TRUE": 0.75,
                     "UNVERIFIED": 0.5, "FALSE": 0.1}.get(self.verdict, 0.5)
        return rel * p_weight * v_weight

    def update(self, observed_p: float, regime: Regime,
               gex: GexRegime, ts: float) -> float:
        dt = ts - self._last_update_ts if self._last_update_ts > 0 else 1.0
        alpha = half_life_alpha(self.half_life_sec, dt)

        r_mult = self.regime_mults.get(regime, 1.0)
        g_mult = self.gex_mults.get(gex, 1.0)
        adjusted = observed_p * r_mult * g_mult
        adjusted = min(max(adjusted, 1e-6), 1 - 1e-6)

        self._current_posterior = ema_update(
            self._current_posterior, adjusted, alpha
        )
        self._last_update_ts = ts
        self._observation_count += 1
        self._is_live = True
        return self._current_posterior

    def decay(self, ts: float) -> float:
        if not self._is_live:
            return self._current_posterior
        dt = ts - self._last_update_ts
        alpha = half_life_alpha(self.half_life_sec, dt)
        self._current_posterior = ema_update(
            self._current_posterior, self.base_rate, alpha
        )
        return self._current_posterior

    @property
    def logit_effect(self) -> float:
        return logit(self._current_posterior) - logit(self.base_rate)


# ---------------------------------------------------------------------------
# Domain Worker
# ---------------------------------------------------------------------------

@dataclass
class DomainWorker:
    domain: Domain
    nodes: list[ProbNode] = field(default_factory=list)
    _posterior: float = 0.5

    def add(self, node: ProbNode) -> None:
        self.nodes.append(node)

    @property
    def live_nodes(self) -> list[ProbNode]:
        return [n for n in self.nodes if n._is_live]

    @property
    def dark_nodes(self) -> list[ProbNode]:
        return [n for n in self.nodes if not n._is_live]

    def collapse(self) -> float:
        live = self.live_nodes
        if not live:
            self._posterior = 0.5
            return 0.5

        baseline_logit = logit(0.5)
        weighted_effects = []
        total_weight = 0.0

        for node in live:
            w = node.effective_weight
            if w > 0:
                weighted_effects.append(w * node.logit_effect)
                total_weight += w

        if total_weight == 0:
            self._posterior = 0.5
            return 0.5

        mean_effect = sum(weighted_effects) / total_weight
        self._posterior = inv_logit(baseline_logit + mean_effect)
        return self._posterior

    @property
    def coverage(self) -> float:
        if not self.nodes:
            return 0.0
        return len(self.live_nodes) / len(self.nodes)

    @property
    def effective_support(self) -> float:
        live = self.live_nodes
        if not live:
            return 0.0
        return sum(n._observation_count for n in live) / len(live)


# ---------------------------------------------------------------------------
# Market Context (input to the engine)
# ---------------------------------------------------------------------------

@dataclass
class MarketContext:
    timestamp: float = 0.0

    # Price & TA
    price: float = 0.0
    vwap: float = 0.0
    ema9: float = 0.0
    ema20: float = 0.0
    ema144: float = 0.0
    rsi_14: float = 50.0
    rsi_28: float = 50.0
    atr_14: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    macd: float = 0.0
    macd_signal: float = 0.0

    # Volume & Flow
    volume_ratio: float = 1.0
    cvd_5: float = 0.0
    cvd_slope: float = 0.0
    vpin: float = 0.0
    dark_pool_ratio: float = 0.0
    block_trade_detected: bool = False

    # Order Book
    bid_depth_l1: float = 0.0
    ask_depth_l1: float = 0.0
    bid_depth_l10: float = 0.0
    ask_depth_l10: float = 0.0
    spread_bps: float = 0.0
    obi: float = 0.0  # (bid-ask)/(bid+ask)
    resting_order_size: float = 0.0
    order_cancel_ratio: float = 0.0

    # Options / Greeks
    option_delta: float = 0.0
    option_gamma: float = 0.0
    option_theta: float = 0.0
    option_iv: float = 0.0
    premium: float = 0.0
    premium_velocity: float = 0.0
    premium_acceleration: float = 0.0
    dte: int = 0

    # GEX / Greeks Exposure
    gex: float = 0.0
    dex: float = 0.0
    vex: float = 0.0
    max_pain: float = 0.0
    put_call_ratio: float = 1.0
    zero_dte_volume_ratio: float = 0.0

    # Regime
    regime: Regime = Regime.UNKNOWN
    gex_regime: GexRegime = GexRegime.UNKNOWN
    fractal_state: str = "unknown"
    vix: float = 15.0

    # Futures Lead-Lag
    es_price: float = 0.0
    nq_price: float = 0.0
    es_nq_basis: float = 0.0
    futures_spot_corr: float = 0.99

    # Cross-Asset
    dxy_5m_corr: float = 0.0
    hyg_below_vwap: bool = False
    xlp_xlu_outperform: bool = False
    vix_call_spike: bool = False
    mag7_all_declining: bool = False
    rsp_diverging: bool = False

    # Time of Day
    minutes_since_open: int = 0
    is_power_hour: bool = False
    is_lunch: bool = False
    is_first_15: bool = False
    is_last_15: bool = False
    is_event_day: bool = False
    event_type: str = ""

    # Premium Band
    premium_in_band: bool = False  # $1.00-$2.00

    # Session stats
    day_high: float = 0.0
    day_low: float = 0.0
    ib_high: float = 0.0  # initial balance (30-min)
    ib_low: float = 0.0
    prev_day_poc: float = 0.0
    overnight_high: float = 0.0
    overnight_low: float = 0.0
    opening_gap_pct: float = 0.0

    # Velocity / Acceleration
    velocity_5s: float = 0.0
    velocity_30s: float = 0.0
    velocity_120s: float = 0.0
    peak_velocity: float = 0.0


# ---------------------------------------------------------------------------
# Engine Output
# ---------------------------------------------------------------------------

@dataclass
class EngineOutput:
    timestamp: float
    composite_posterior: float  # main signal [0,1]
    domain_posteriors: dict[str, float]
    domain_coverage: dict[str, float]
    regime: Regime
    gex_regime: GexRegime
    confidence_tier: str  # full/half/quarter/paper
    kelly_fraction: float
    ev: float
    break_even_move: float
    sizing_multiplier: float
    live_node_count: int
    dark_node_count: int
    total_node_count: int
    top_factors: list[dict]
    veto_active: bool
    veto_reasons: list[str]


# ---------------------------------------------------------------------------
# The Engine
# ---------------------------------------------------------------------------

class BayesianProbabilityEngine:
    def __init__(self):
        self.workers: dict[Domain, DomainWorker] = {
            d: DomainWorker(domain=d) for d in Domain
        }
        self.nodes: dict[str, ProbNode] = {}
        self._build_nodes()
        self._last_regime = Regime.UNKNOWN
        self._regime_history: list[tuple[float, Regime]] = []
        self._composite_history: list[tuple[float, float]] = []

    def _register(self, node: ProbNode) -> None:
        self.nodes[node.id] = node
        self.workers[node.domain].add(node)

    def _build_nodes(self) -> None:
        self._build_order_flow_nodes()
        self._build_intraday_stats_nodes()
        self._build_macro_cross_nodes()
        self._build_options_mechanics_nodes()
        self._build_microstructure_nodes()
        self._build_regime_nodes()
        self._build_timing_nodes()
        self._build_risk_nodes()
        self._build_simons_six_nodes()
        self._build_volume_profile_nodes()
        self._build_volatility_surface_nodes()
        self._build_candle_geometry_nodes()
        self._build_cross_timeframe_nodes()
        self._build_premium_dynamics_nodes()

    # ── ORDER FLOW (Q1-Q50) ──────────────────────────────────────────────

    def _build_order_flow_nodes(self) -> None:
        nodes = [
            ProbNode("OF001", Domain.ORDER_FLOW,
                     "Deep LOB liquidity pool as S/R (low OCR, >5k contracts, >30min)",
                     0.55, 0.10, 4, "Hasbrouck(1991)", "PARTIALLY_TRUE", "context",
                     regime_mults={Regime.TREND_UP: 1.2, Regime.CHOP: 0.8}),
            ProbNode("OF002", Domain.ORDER_FLOW,
                     "Large resting orders >0.5% from spot as structural S/R",
                     0.58, 0.12, 4, "Glosten/Milgrom(1985)", "TRUE", "context",
                     regime_mults={Regime.TREND_UP: 1.1, Regime.EXPANSION: 1.3}),
            ProbNode("OF003", Domain.ORDER_FLOW,
                     "Fleeting order cancel probability (>10k within 3s of arrival)",
                     0.55, -0.08, 5, "Hasbrouck/Saar(2009)", "PARTIALLY_TRUE", "veto"),
            ProbNode("OF004", Domain.ORDER_FLOW,
                     "Pre-market large order bluff (>1k, within 30min of open)",
                     0.35, -0.12, 3, "Egginton(2016)", "PARTIALLY_TRUE", "veto"),
            ProbNode("OF005", Domain.ORDER_FLOW,
                     "Passive limit vs aggressive market — breakout probability",
                     0.58, 0.10, 5, "Cont/Kukanov/Stoikov(2014)", "TRUE", "entry",
                     regime_mults={Regime.EXPANSION: 1.4, Regime.CHOP: 0.6}),
            ProbNode("OF006", Domain.ORDER_FLOW,
                     "Passive sell > 2.5x aggressive buy → reversal +42%",
                     0.42, 0.15, 4, "Cont(2014)/Bouchaud(2009)", "PARTIALLY_TRUE", "entry",
                     regime_mults={Regime.TREND_UP: 1.3, Regime.CHOP: 0.7}),
            ProbNode("OF007", Domain.ORDER_FLOW,
                     "Institutional order persistence >45min, OCR<0.10",
                     0.70, 0.08, 3, "Hasbrouck/Saar(2009)", "UNVERIFIED", "context"),
            ProbNode("OF008", Domain.ORDER_FLOW,
                     "Static institutional orders 73% higher fill than shifting",
                     0.73, 0.10, 3, "Gould(2013)", "PARTIALLY_TRUE", "context"),
            ProbNode("OF009", Domain.ORDER_FLOW,
                     "Iceberg orders understate depth by 40-50% when VIX>25",
                     0.45, -0.10, 4, "Bessembinder(2009)", "PARTIALLY_TRUE", "sizing",
                     regime_mults={Regime.EXPANSION: 0.7}),
            ProbNode("OF010", Domain.ORDER_FLOW,
                     "Institutional icebergs scale down 40% display in short gamma",
                     0.40, 0.08, 3, "De Winne/D'Hondt(2007)", "PARTIALLY_TRUE", "context",
                     gex_mults={GexRegime.SHORT_GAMMA: 1.4}),
            ProbNode("OF011", Domain.ORDER_FLOW,
                     "CVD divergence = institutional absorption",
                     0.62, 0.18, 5, "Easley/LdP/O'Hara(2012)", "TRUE", "entry",
                     regime_mults={Regime.TREND_UP: 1.3, Regime.TREND_DOWN: 1.3}),
            ProbNode("OF012", Domain.ORDER_FLOW,
                     "Bullish price + declining CVD → absorption → reversal",
                     0.62, 0.18, 5, "Chordia(2002)", "TRUE", "entry",
                     regime_mults={Regime.TREND_UP: 1.5}),
            ProbNode("OF013", Domain.ORDER_FLOW,
                     "VWAP touch + CVD spike → 65% continuation",
                     0.65, 0.12, 4, "Madhavan(1997)", "PARTIALLY_TRUE", "entry"),
            ProbNode("OF014", Domain.ORDER_FLOW,
                     "Early AM VWAP retracement + CVD → 68% continuation",
                     0.68, 0.15, 5, "Gao(2018)/Berkman(1996)", "PARTIALLY_TRUE", "entry"),
            ProbNode("OF015", Domain.ORDER_FLOW,
                     "Intra-candle volume variance >3SD → dark pool routing",
                     0.55, 0.10, 4, "Easley(1996)", "TRUE", "context"),
            ProbNode("OF016", Domain.ORDER_FLOW,
                     "Volume variance >3SD + small body → dark pool accumulation",
                     0.55, 0.08, 3, "Zhu(2014)", "PARTIALLY_TRUE", "context"),
            ProbNode("OF017", Domain.ORDER_FLOW,
                     "Delta divergence at daily high/low → SPY reversal",
                     0.58, 0.15, 5, "Chordia(2002)/Cont(2014)", "TRUE", "entry"),
            ProbNode("OF018", Domain.ORDER_FLOW,
                     "SPY new high + 5min CVD failure → 58% mean reversion to VWAP",
                     0.58, 0.13, 5, "Chordia(2002)", "PARTIALLY_TRUE", "entry"),
            ProbNode("OF019", Domain.ORDER_FLOW,
                     "Footprint + Bookmap reduces false signals by 31.4%",
                     0.69, 0.10, 4, "Bouchaud(2009)/Cont(2011)", "PARTIALLY_TRUE", "context"),
            ProbNode("OF020", Domain.ORDER_FLOW,
                     "Footprint volume imbalance >65/35 at key level confirms breakout",
                     0.65, 0.10, 4, "Cont(2011)", "PARTIALLY_TRUE", "entry"),
            ProbNode("OF021", Domain.ORDER_FLOW,
                     "Liquidity depletion >65% in 30s → cascade imminent",
                     0.70, -0.20, 5, "Kyle(1985)/Brunnermeier(2009)", "TRUE", "veto"),
            ProbNode("OF022", Domain.ORDER_FLOW,
                     "70%+ depth drop in 3 ticks → stop-loss cascade",
                     0.70, 0.20, 5, "Brunnermeier(2009)", "TRUE", "entry",
                     regime_mults={Regime.TREND_DOWN: 1.5}),
            ProbNode("OF023", Domain.ORDER_FLOW,
                     "HFT exploits retail stop clusters at obvious levels",
                     0.65, -0.15, 5, "Brogaard(2014)/Egginton(2016)", "TRUE", "veto"),
            ProbNode("OF024", Domain.ORDER_FLOW,
                     "HFT micro-spoofing into retail stops (quote-to-trade >3x)",
                     0.60, 0.12, 4, "SEC Flash Crash Report(2010)", "TRUE", "entry"),
            ProbNode("OF025", Domain.ORDER_FLOW,
                     "Options MM GEX+ → compressed book, tight spreads, buy dips",
                     0.65, 0.15, 5, "Garleanu(2009)/Barbon(2020)", "TRUE", "context",
                     gex_mults={GexRegime.LONG_GAMMA: 1.5, GexRegime.SHORT_GAMMA: 0.5}),
            ProbNode("OF026", Domain.ORDER_FLOW,
                     "GEX- → wider spreads, thinner book, sell rips",
                     0.65, -0.10, 5, "Barbon/Buraschi(2020)", "TRUE", "context",
                     gex_mults={GexRegime.SHORT_GAMMA: 1.5, GexRegime.LONG_GAMMA: 0.5}),
            ProbNode("OF027", Domain.ORDER_FLOW,
                     "Microsecond T&S clustering → institutional split execution",
                     0.60, 0.08, 3, "Almgren/Chriss(2001)", "PARTIALLY_TRUE", "context"),
            ProbNode("OF028", Domain.ORDER_FLOW,
                     "T&S burst + CVD alignment → 60% continuation",
                     0.60, 0.08, 3, "Hasbrouck(1991)", "PARTIALLY_TRUE", "entry"),
            ProbNode("OF029", Domain.ORDER_FLOW,
                     "Thin book within 60s of CPI/FOMC → reduce size 50%",
                     0.50, -0.15, 5, "Fleming/Remolona(1999)", "TRUE", "sizing"),
            ProbNode("OF030", Domain.ORDER_FLOW,
                     "QQQ 45% greater liquidity extraction pre-CPI vs SPY",
                     0.45, -0.12, 4, "Chordia(2005)", "PARTIALLY_TRUE", "sizing"),
            ProbNode("OF031", Domain.ORDER_FLOW,
                     "Order book imbalance persists >60s → structural",
                     0.65, 0.12, 4, "Hasbrouck/Saar(2009)", "TRUE", "context"),
            ProbNode("OF032", Domain.ORDER_FLOW,
                     "Deep-chart anomaly 81% correlated with delayed dark pool print",
                     0.60, 0.08, 3, "Zhu(2014)", "UNVERIFIED", "context"),
            ProbNode("OF033", Domain.ORDER_FLOW,
                     "VPIN >0.90 in chop → 70% reversal probability",
                     0.70, 0.15, 5, "Easley/LdP/O'Hara(2012)", "PARTIALLY_TRUE", "entry",
                     regime_mults={Regime.CHOP: 1.4, Regime.TREND_UP: 0.7}),
            ProbNode("OF034", Domain.ORDER_FLOW,
                     "VPIN >0.90 in trend → 45% reversal (continuation more likely)",
                     0.45, 0.05, 5, "Easley/LdP/O'Hara(2012)", "TRUE", "context",
                     regime_mults={Regime.TREND_UP: 0.8, Regime.TREND_DOWN: 0.8}),
            ProbNode("OF035", Domain.ORDER_FLOW,
                     "Net positive institutional flow final 15min → 64% positive gap",
                     0.64, 0.12, 3, "Hendershott(2011)/Gao(2018)", "PARTIALLY_TRUE", "context"),
            ProbNode("OF036", Domain.ORDER_FLOW,
                     "E-mini book imbalance yields 18% higher alpha vs SPY/QQQ",
                     0.58, 0.18, 5, "Hasbrouck(1995)", "TRUE", "entry"),
            ProbNode("OF037", Domain.ORDER_FLOW,
                     "SPY/ES divergence >5bp persisting >15ms → genuine signal",
                     0.55, 0.10, 4, "Brogaard(2014)", "TRUE", "entry"),
            ProbNode("OF038", Domain.ORDER_FLOW,
                     "QQQ options block trade → NQ futures spike within 500ms",
                     0.60, 0.15, 4, "Garleanu(2009)", "TRUE", "entry"),
        ]
        for n in nodes:
            self._register(n)

    # ── INTRADAY STATISTICS (Q51-Q100) ────────────────────────────────────

    def _build_intraday_stats_nodes(self) -> None:
        nodes = [
            ProbNode("IS001", Domain.INTRADAY_STATS,
                     "62% of days are chop (IB not broken by 10am)",
                     0.62, 0.15, 5, "Crabel(1990)/Dalton(1990)", "TRUE", "regime"),
            ProbNode("IS002", Domain.INTRADAY_STATS,
                     "Breakout validation timer: 12-15min hold or failed",
                     0.55, 0.12, 4, "Heston(2010)", "PARTIALLY_TRUE", "entry"),
            ProbNode("IS003", Domain.INTRADAY_STATS,
                     "QQQ >2.5 SD breakout → tail event day (2.4/month)",
                     0.60, 0.20, 4, "Heston(2010)", "PARTIALLY_TRUE", "regime",
                     regime_mults={Regime.EXPANSION: 1.5}),
            ProbNode("IS004", Domain.INTRADAY_STATS,
                     "Hard reversal days triggered by mid-day macro (3.1/quarter)",
                     0.25, -0.10, 4, "Harris(1986)", "PARTIALLY_TRUE", "veto"),
            ProbNode("IS005", Domain.INTRADAY_STATS,
                     "QQQ ADR 34% larger on down days (leverage effect)",
                     0.60, 0.15, 5, "Schwert(1989)/Ang(2006)", "TRUE", "sizing",
                     regime_mults={Regime.TREND_DOWN: 1.34}),
            ProbNode("IS006", Domain.INTRADAY_STATS,
                     "Lunch hour candles 50-70% smaller (12:00-13:30 ET)",
                     0.55, 0.12, 5, "Wood(1985)/Harris(1986)", "PARTIALLY_TRUE", "timing"),
            ProbNode("IS007", Domain.INTRADAY_STATS,
                     "SPY prints max 4.2 directional 5min candles before retracement",
                     0.60, -0.15, 4, "Lo/MacKinlay(1988)", "PARTIALLY_TRUE", "exit"),
            ProbNode("IS008", Domain.INTRADAY_STATS,
                     "Daily high/low set in first 15min 37% of time",
                     0.37, 0.10, 4, "Harris(1986)/Gao(2018)", "TRUE", "context"),
            ProbNode("IS009", Domain.INTRADAY_STATS,
                     "Downward $1 SPY move 55% faster velocity than upward",
                     0.55, 0.15, 5, "Schwert(1989)/Ang(2006)", "TRUE", "sizing"),
            ProbNode("IS010", Domain.INTRADAY_STATS,
                     "Liquidity gaps >3SD occur 1.4x/day on QQQ, clustered 10am",
                     0.55, -0.15, 5, "Fleming(1999)/Chordia(2005)", "PARTIALLY_TRUE", "veto"),
            ProbNode("IS011", Domain.INTRADAY_STATS,
                     "15min ORB: 41% win rate, 59% false breakout reverts to VWAP",
                     0.41, -0.15, 5, "Crabel(1990)/Lo(2000)", "TRUE", "entry"),
            ProbNode("IS012", Domain.INTRADAY_STATS,
                     "QQQ Fibonacci retracement clusters at 38.2%",
                     0.55, 0.08, 3, "Lo(2000)/Osler(2000)", "PARTIALLY_TRUE", "entry"),
            ProbNode("IS013", Domain.INTRADAY_STATS,
                     "Max confidence setups 09:30-11:00; after 11am require 1.5x signal",
                     0.60, 0.12, 4, "Gao(2018)", "UNVERIFIED", "timing"),
            ProbNode("IS014", Domain.INTRADAY_STATS,
                     "NQ/ES divergence at inflection → 61.5% win convergence trade",
                     0.615, 0.12, 4, "Hasbrouck(1995)", "PARTIALLY_TRUE", "entry"),
            ProbNode("IS015", Domain.INTRADAY_STATS,
                     "Failed breakdown below prev-day low reclaims in 15min → 67% reversal",
                     0.67, 0.20, 5, "Jegadeesh/Titman(1993)/Lo(1990)", "TRUE", "entry"),
            ProbNode("IS016", Domain.INTRADAY_STATS,
                     "Opening 30min volume >1.5x 90d avg → bimodal distribution day",
                     0.60, 0.15, 4, "Wood(1985)/Admati(1988)", "PARTIALLY_TRUE", "regime"),
            ProbNode("IS017", Domain.INTRADAY_STATS,
                     "Previous day's POC as intraday S/R (54% significance)",
                     0.54, 0.08, 3, "Dalton(1990)", "TRUE", "context"),
            ProbNode("IS018", Domain.INTRADAY_STATS,
                     "IV expected move 1-SD range contains 68.2% of closes",
                     0.682, 0.15, 5, "Black/Scholes(1973)/Bondarenko(2014)", "TRUE", "sizing"),
            ProbNode("IS019", Domain.INTRADAY_STATS,
                     "QQQ median max intraday drawdown 1.62%, SPY 0.94%",
                     0.55, 0.10, 4, "Ang(2006)", "PARTIALLY_TRUE", "sizing"),
            ProbNode("IS020", Domain.INTRADAY_STATS,
                     "Inside days 2.2/month → volatility compression before breakout",
                     0.70, 0.15, 4, "Crabel(1990)/Bollerslev(1986)", "TRUE", "regime"),
            ProbNode("IS021", Domain.INTRADAY_STATS,
                     "OPEX pinning: hourly returns compress 22% around large OI strikes",
                     0.64, 0.18, 5, "Ni/Pearson/Poteshman(2005)", "TRUE", "context"),
            ProbNode("IS022", Domain.INTRADAY_STATS,
                     "Non-news momentum impulses on QQQ mean duration 18min",
                     0.55, 0.10, 4, "Heston(2010)", "PARTIALLY_TRUE", "exit"),
            ProbNode("IS023", Domain.INTRADAY_STATS,
                     "Round number stop-run: 45% velocity increase",
                     0.55, 0.12, 4, "Osler(2003)", "TRUE", "veto"),
            ProbNode("IS024", Domain.INTRADAY_STATS,
                     "Small gap <0.5% filled within 2 hours 71%",
                     0.71, 0.20, 5, "Bhattacharya(2012)/Lucca(2015)", "TRUE", "entry"),
            ProbNode("IS025", Domain.INTRADAY_STATS,
                     "Mid-day reversal from deep morning low ~11x/year",
                     0.15, 0.08, 3, "Harris(1986)", "PARTIALLY_TRUE", "context"),
        ]
        for n in nodes:
            self._register(n)

    # ── MACRO & CROSS-ASSET (Q101-Q150) ───────────────────────────────────

    def _build_macro_cross_nodes(self) -> None:
        nodes = [
            ProbNode("MC001", Domain.MACRO_CROSS,
                     "E-mini futures lead SPY by 4.2ms average",
                     0.60, 0.15, 5, "Hasbrouck(1995)/Brogaard(2014)", "TRUE", "entry"),
            ProbNode("MC002", Domain.MACRO_CROSS,
                     "Futures/spot correlation drops to 0.941 during lunch",
                     0.55, -0.10, 4, "Admati/Pfleiderer(1988)", "PARTIALLY_TRUE", "timing"),
            ProbNode("MC003", Domain.MACRO_CROSS,
                     "NQ premium widening >15min → 65% QQQ catch-up rally",
                     0.65, 0.15, 5, "Hasbrouck(1995)/Gao(2018)", "TRUE", "entry"),
            ProbNode("MC004", Domain.MACRO_CROSS,
                     "Overnight futures session H/L → 44% boundary for cash",
                     0.44, 0.08, 3, "Crabel(1990)", "PARTIALLY_TRUE", "context"),
            ProbNode("MC005", Domain.MACRO_CROSS,
                     "HFT selloff → ES/SPY tracking error expands to 14bp",
                     0.55, 0.10, 3, "Brogaard(2014)/SEC(2010)", "TRUE", "entry"),
            ProbNode("MC006", Domain.MACRO_CROSS,
                     "Mag7 all declining → 90%+ QQQ decline probability",
                     0.90, 0.20, 5, "Ang/Chen(2002)/MSCI(2023)", "TRUE", "veto"),
            ProbNode("MC007", Domain.MACRO_CROSS,
                     "SPY rises while RSP declines 30d → 74% >5% correction",
                     0.74, -0.15, 3, "Ang/Chen(2002)", "TRUE", "veto"),
            ProbNode("MC008", Domain.MACRO_CROSS,
                     "AAPL+MSFT both below VWAP → QQQ uptrend sustaining <15%",
                     0.15, -0.25, 5, "Hasbrouck(1995)", "TRUE", "veto"),
            ProbNode("MC009", Domain.MACRO_CROSS,
                     "Index IV < weighted avg single-stock IV → correlation compression",
                     0.55, 0.12, 3, "Driessen(2009)", "TRUE", "context"),
            ProbNode("MC010", Domain.MACRO_CROSS,
                     "AAPL structural breakdown → SPY follows in 90-180s",
                     0.60, 0.15, 4, "Hasbrouck(1995)/Brogaard(2014)", "TRUE", "entry"),
            ProbNode("MC011", Domain.MACRO_CROSS,
                     "0DTE volume >1.5x 20d avg + GEX+ → volatility suppression day",
                     0.55, -0.12, 5, "Bondarenko/Gonzalez-Perez(2024)", "TRUE", "regime",
                     gex_mults={GexRegime.LONG_GAMMA: 1.4}),
            ProbNode("MC012", Domain.MACRO_CROSS,
                     "QQQ options block → NQ futures corr 0.84 within 500ms",
                     0.60, 0.15, 4, "Garleanu(2009)", "TRUE", "entry"),
            ProbNode("MC013", Domain.MACRO_CROSS,
                     "Defensive sector ETF outperform → 68% SPY correction in 48h",
                     0.68, -0.10, 3, "Barberis(2005)/Chordia(2000)", "PARTIALLY_TRUE", "veto"),
            ProbNode("MC014", Domain.MACRO_CROSS,
                     "VIX call volume >3x avg → disable long QQQ, downside in 8min",
                     0.60, -0.20, 5, "Whaley(2009)/Ni(2008)", "TRUE", "veto"),
            ProbNode("MC015", Domain.MACRO_CROSS,
                     "SPY 30d > RSP 30d declines → 74% breadth correction",
                     0.74, -0.15, 3, "Lo/MacKinlay(1990)", "TRUE", "context"),
            ProbNode("MC016", Domain.MACRO_CROSS,
                     "VIX >30 → all sector correlations converge to >0.90",
                     0.55, -0.20, 5, "Longin/Solnik(2001)", "TRUE", "sizing"),
            ProbNode("MC017", Domain.MACRO_CROSS,
                     "DAX >1.5% European session → 79% SPY direction match",
                     0.79, 0.15, 3, "Eun/Shim(1989)", "PARTIALLY_TRUE", "context"),
            ProbNode("MC018", Domain.MACRO_CROSS,
                     "DXY/S&P 5min corr < -0.85 → strong risk-on, momentum +18.3%",
                     0.55, 0.15, 4, "Brunnermeier(2009)", "PARTIALLY_TRUE", "entry"),
            ProbNode("MC019", Domain.MACRO_CROSS,
                     "TQQQ tracking error expands 22bp/hour in volatile sessions",
                     0.55, -0.08, 3, "Cheng/Madhavan(2009)", "TRUE", "context"),
            ProbNode("MC020", Domain.MACRO_CROSS,
                     "HYG below VWAP + SPY above → risk-off warning, 12min lead",
                     0.55, -0.12, 4, "Chordia(2005)", "PARTIALLY_TRUE", "veto"),
            ProbNode("MC021", Domain.MACRO_CROSS,
                     "SPY/QQQ first-hour divergence → 82% convergence by close",
                     0.82, 0.15, 4, "Hasbrouck(1995)", "PARTIALLY_TRUE", "entry"),
        ]
        for n in nodes:
            self._register(n)

    # ── OPTIONS MECHANICS (Q121-Q180) ─────────────────────────────────────

    def _build_options_mechanics_nodes(self) -> None:
        nodes = [
            ProbNode("OM001", Domain.OPTIONS_MECHANICS,
                     "0DTE volume suppresses realized vol when GEX+ (14% compression)",
                     0.55, -0.12, 5, "Bondarenko(2024)", "TRUE", "regime",
                     gex_mults={GexRegime.LONG_GAMMA: 1.4}),
            ProbNode("OM002", Domain.OPTIONS_MECHANICS,
                     "Premium velocity_120s strongest P&L correlator (+0.2199)",
                     0.58, 0.15, 5, "MadTrades V6 internal", "TRUE", "entry"),
            ProbNode("OM003", Domain.OPTIONS_MECHANICS,
                     "Premium band $1.00-$2.00 strongest single filter (p=0.0001)",
                     0.65, 0.20, 5, "MadTrades V6 F-0338", "TRUE", "entry"),
            ProbNode("OM004", Domain.OPTIONS_MECHANICS,
                     "Break-even move gate: ΔV = Δ·ΔS + ½Γ·ΔS² + Θ·h",
                     0.50, 0.0, 5, "Black/Scholes(1973)", "TRUE", "veto"),
            ProbNode("OM005", Domain.OPTIONS_MECHANICS,
                     "EV gate: fire only if EV>0 AND bootstrap 10th pctile p > p*",
                     0.50, 0.0, 5, "Kelly(1956)", "TRUE", "veto"),
            ProbNode("OM006", Domain.OPTIONS_MECHANICS,
                     "Theta decay acceleration last 2 hours of 0DTE",
                     0.65, -0.15, 5, "Black/Scholes(1973)", "TRUE", "timing"),
            ProbNode("OM007", Domain.OPTIONS_MECHANICS,
                     "Delta sensitivity increases as 0DTE approaches expiry",
                     0.60, 0.12, 4, "Black/Scholes(1973)", "TRUE", "sizing"),
            ProbNode("OM008", Domain.OPTIONS_MECHANICS,
                     "IV crush post-CPI/FOMC → premium destruction within 5min",
                     0.70, -0.20, 5, "Bondarenko(2014)", "TRUE", "timing"),
            ProbNode("OM009", Domain.OPTIONS_MECHANICS,
                     "GEX regime is single highest-impact finding (Q161-164)",
                     0.60, 0.20, 5, "Barbon/Buraschi(2020)", "TRUE", "regime",
                     gex_mults={GexRegime.LONG_GAMMA: 1.5, GexRegime.SHORT_GAMMA: 0.6}),
            ProbNode("OM010", Domain.OPTIONS_MECHANICS,
                     "Max pain gravitational pull within 0.5% of strike, OPEX",
                     0.64, 0.18, 5, "Ni/Pearson/Poteshman(2005)", "TRUE", "context"),
            ProbNode("OM011", Domain.OPTIONS_MECHANICS,
                     "Put/call ratio extremes (>1.5 or <0.5) → reversal within 2h",
                     0.58, 0.12, 4, "CBOE studies", "PARTIALLY_TRUE", "entry"),
            ProbNode("OM012", Domain.OPTIONS_MECHANICS,
                     "Gamma exposure flip (GEX sign change) → regime transition",
                     0.65, 0.15, 5, "Barbon/Buraschi(2020)", "TRUE", "regime"),
            ProbNode("OM013", Domain.OPTIONS_MECHANICS,
                     "IV term structure inversion → near-term event expected",
                     0.60, 0.10, 4, "Bondarenko(2014)", "PARTIALLY_TRUE", "context"),
            ProbNode("OM014", Domain.OPTIONS_MECHANICS,
                     "Skew steepening → institutional put buying / downside hedging",
                     0.58, -0.10, 4, "Bates(2000)", "TRUE", "context"),
            ProbNode("OM015", Domain.OPTIONS_MECHANICS,
                     "Hold time <=30s PF 0.24 (worst); 30-60s PF 2.415 (best)",
                     0.55, 0.15, 5, "MadTrades V6 internal", "TRUE", "timing"),
        ]
        for n in nodes:
            self._register(n)

    # ── MICROSTRUCTURE (Q31-Q40) ──────────────────────────────────────────

    def _build_microstructure_nodes(self) -> None:
        nodes = [
            ProbNode("MS001", Domain.MICROSTRUCTURE,
                     "Feature-reframing (Kalman/autoencoder) improves mean-reversion 15-25%",
                     0.55, 0.10, 3, "Cont(2011)/Lo(1990)", "PARTIALLY_TRUE", "context"),
            ProbNode("MS002", Domain.MICROSTRUCTURE,
                     "Dynamic ATR-based lookback window optimizes liquidity tracking",
                     0.55, 0.08, 3, "Avellaneda/Lee(2010)", "TRUE", "context"),
            ProbNode("MS003", Domain.MICROSTRUCTURE,
                     "Synthetic OBI reverts <400ms; structural persists across 1min candles",
                     0.60, 0.12, 4, "Hasbrouck/Saar(2009)", "TRUE", "context"),
            ProbNode("MS004", Domain.MICROSTRUCTURE,
                     "Spread expansion >2x ATR in <5s → liquidity withdrawal",
                     0.55, -0.12, 4, "Kyle(1985)", "TRUE", "veto"),
            ProbNode("MS005", Domain.MICROSTRUCTURE,
                     "Tick imbalance bars capture directional information better than time bars",
                     0.58, 0.10, 4, "Lopez de Prado(2018)", "TRUE", "context"),
            ProbNode("MS006", Domain.MICROSTRUCTURE,
                     "Volume clock bars normalize for intraday volume seasonality",
                     0.55, 0.08, 3, "Lopez de Prado(2018)", "TRUE", "context"),
            ProbNode("MS007", Domain.MICROSTRUCTURE,
                     "Kyle's lambda (price impact) increases 3x in thin markets",
                     0.60, -0.15, 5, "Kyle(1985)", "TRUE", "sizing"),
            ProbNode("MS008", Domain.MICROSTRUCTURE,
                     "Quote staleness >60s in liquid names → data feed issue",
                     0.50, -0.20, 5, "Internal", "TRUE", "veto"),
        ]
        for n in nodes:
            self._register(n)

    # ── REGIME DETECTION ──────────────────────────────────────────────────

    def _build_regime_nodes(self) -> None:
        nodes = [
            ProbNode("RG001", Domain.REGIME,
                     "IB breakout by 10am → 62% directional day",
                     0.62, 0.15, 5, "Dalton(1990)", "TRUE", "regime"),
            ProbNode("RG002", Domain.REGIME,
                     "VIX >25 → short gamma dominates, wider spreads expected",
                     0.55, 0.12, 5, "Bessembinder(2009)", "PARTIALLY_TRUE", "regime",
                     gex_mults={GexRegime.SHORT_GAMMA: 1.3}),
            ProbNode("RG003", Domain.REGIME,
                     "Bollinger Band squeeze (<1% width) → expansion imminent",
                     0.65, 0.15, 4, "Bollerslev(1986)", "TRUE", "regime"),
            ProbNode("RG004", Domain.REGIME,
                     "ADR expansion >1.5x 20d avg → trending day classification",
                     0.60, 0.12, 4, "Crabel(1990)", "TRUE", "regime"),
            ProbNode("RG005", Domain.REGIME,
                     "3 consecutive inside candles on 15min → coiled spring setup",
                     0.60, 0.15, 4, "Bollerslev(1986)", "TRUE", "regime"),
            ProbNode("RG006", Domain.REGIME,
                     "Price within IB + declining ATR → mean-reversion regime",
                     0.62, 0.15, 5, "Dalton(1990)", "TRUE", "regime",
                     regime_mults={Regime.CHOP: 1.4}),
            ProbNode("RG007", Domain.REGIME,
                     "GEX flip from positive to negative → regime transition signal",
                     0.65, 0.18, 5, "Barbon/Buraschi(2020)", "TRUE", "regime"),
            ProbNode("RG008", Domain.REGIME,
                     "Fractal state alignment across 1m/5m/15m → high conviction",
                     0.65, 0.15, 4, "Mandelbrot/Hudson(2004)", "TRUE", "entry"),
        ]
        for n in nodes:
            self._register(n)

    # ── TIMING ────────────────────────────────────────────────────────────

    def _build_timing_nodes(self) -> None:
        nodes = [
            ProbNode("TM001", Domain.TIMING,
                     "Power hour (15:00-16:00) → elevated volume, directional moves",
                     0.58, 0.12, 4, "Harris(1986)", "TRUE", "timing"),
            ProbNode("TM002", Domain.TIMING,
                     "Lunch (12:00-13:30) → 50-70% reduced candle size, noise",
                     0.55, -0.12, 5, "Wood(1985)", "TRUE", "timing"),
            ProbNode("TM003", Domain.TIMING,
                     "First 90 minutes highest signal confidence window",
                     0.60, 0.12, 4, "Gao(2018)", "UNVERIFIED", "timing"),
            ProbNode("TM004", Domain.TIMING,
                     "Last 15 minutes: widening spreads, institutional positioning",
                     0.55, 0.10, 3, "Harris(1986)", "TRUE", "timing"),
            ProbNode("TM005", Domain.TIMING,
                     "CPI/FOMC: thin book 60s before, reduce size 50%",
                     0.50, -0.15, 5, "Fleming/Remolona(1999)", "TRUE", "veto"),
            ProbNode("TM006", Domain.TIMING,
                     "Pre-open 30min: high cancel rate, low signal quality",
                     0.35, -0.12, 3, "Egginton(2016)", "PARTIALLY_TRUE", "veto"),
            ProbNode("TM007", Domain.TIMING,
                     "Hold time 30-60s optimal PF window for 0DTE scalps",
                     0.55, 0.15, 5, "MadTrades V6 internal", "TRUE", "exit"),
            ProbNode("TM008", Domain.TIMING,
                     "Theta cliff: avoid new entries after 15:30 on 0DTE",
                     0.55, -0.15, 5, "Black/Scholes(1973)", "TRUE", "veto"),
            ProbNode("TM009", Domain.TIMING,
                     "10:00 AM reversal window: macro data release cluster",
                     0.55, 0.10, 4, "Fleming/Remolona(1999)", "TRUE", "timing"),
            ProbNode("TM010", Domain.TIMING,
                     "14:00 ET bond auction / Fed minutes → volatility spike",
                     0.55, -0.10, 3, "Fleming/Remolona(1999)", "PARTIALLY_TRUE", "veto"),
            ProbNode("TM011", Domain.TIMING,
                     "OPEX Friday 15:00-16:00 → max pain gravitational pull intensifies",
                     0.60, 0.15, 4, "Ni/Pearson/Poteshman(2005)", "TRUE", "context"),
        ]
        for n in nodes:
            self._register(n)

    # ── RISK MANAGEMENT ───────────────────────────────────────────────────

    def _build_risk_nodes(self) -> None:
        nodes = [
            ProbNode("RK001", Domain.RISK,
                     "Live performance degrades 18-42% vs backtest (Module 5)",
                     0.70, -0.18, 5, "Institutional Research Report", "TRUE", "sizing"),
            ProbNode("RK002", Domain.RISK,
                     "Correlation convergence at VIX>30 → diversification fails",
                     0.55, -0.20, 5, "Longin/Solnik(2001)", "TRUE", "sizing"),
            ProbNode("RK003", Domain.RISK,
                     "Consecutive losses >3 → reduce size 50% (behavioral tilt guard)",
                     0.50, -0.15, 4, "Internal risk management", "TRUE", "sizing"),
            ProbNode("RK004", Domain.RISK,
                     "Daily P&L drawdown >-2% → halt new entries",
                     0.50, -0.25, 5, "Internal risk management", "TRUE", "veto"),
            ProbNode("RK005", Domain.RISK,
                     "Account drawdown >-5% from peak → quarter sizing",
                     0.50, -0.20, 5, "Internal risk management", "TRUE", "sizing"),
            ProbNode("RK006", Domain.RISK,
                     "Spread >2x normal → slippage risk elevated",
                     0.55, -0.15, 4, "Kyle(1985)", "TRUE", "sizing"),
            ProbNode("RK007", Domain.RISK,
                     "Quote staleness >10s → possible data feed failure",
                     0.50, -0.15, 5, "Internal", "TRUE", "veto"),
            ProbNode("RK008", Domain.RISK,
                     "Position concentration >20% of daily volume → market impact risk",
                     0.55, -0.12, 4, "Almgren/Chriss(2001)", "TRUE", "sizing"),
        ]
        for n in nodes:
            self._register(n)

    # ── SIMONS SIX — sleeve-specific probability nodes ──────────────────

    def _build_simons_six_nodes(self) -> None:
        nodes = [
            # LAST CALL (LCL) — EOD momentum fade
            ProbNode("SSX001", Domain.OPTIONS_MECHANICS,
                     "LCL: 15:00-15:45 window + directional move >0.3% → fade setup",
                     0.58, 0.15, 5, "SIMONS_SIX/LCL", "TRUE", "entry",
                     regime_mults={Regime.TREND_UP: 1.3, Regime.TREND_DOWN: 1.3}),
            ProbNode("SSX002", Domain.OPTIONS_MECHANICS,
                     "LCL: Premium $1.00-$2.00 + delta 0.30-0.50 → optimal strike",
                     0.65, 0.18, 5, "SIMONS_SIX/LCL", "TRUE", "entry"),
            ProbNode("SSX003", Domain.OPTIONS_MECHANICS,
                     "LCL: Theta acceleration last 60min → premium decay >2x normal",
                     0.60, -0.12, 5, "SIMONS_SIX/LCL", "TRUE", "sizing"),
            # FENCE JUMPER (FNJ) — breakout reclaim
            ProbNode("SSX004", Domain.INTRADAY_STATS,
                     "FNJ: Failed breakout reclaim within 5 bars → 67% reversal",
                     0.67, 0.20, 5, "SIMONS_SIX/FNJ", "TRUE", "entry"),
            ProbNode("SSX005", Domain.INTRADAY_STATS,
                     "FNJ: Volume spike >1.5x on reclaim bar → confirmation",
                     0.60, 0.12, 4, "SIMONS_SIX/FNJ", "TRUE", "entry"),
            ProbNode("SSX006", Domain.INTRADAY_STATS,
                     "FNJ: Consecutive failed breakouts (2+) → stronger reversal",
                     0.72, 0.15, 4, "SIMONS_SIX/FNJ", "PARTIALLY_TRUE", "entry"),
            # DEALER'S CHOICE (DLC) — GEX-driven
            ProbNode("SSX007", Domain.OPTIONS_MECHANICS,
                     "DLC: GEX flip zone ±0.5% → directional catalyst",
                     0.62, 0.18, 5, "SIMONS_SIX/DLC", "TRUE", "entry",
                     gex_mults={GexRegime.SHORT_GAMMA: 1.4}),
            ProbNode("SSX008", Domain.OPTIONS_MECHANICS,
                     "DLC: Dealer hedging flow visible in 0DTE chain → 65% directional",
                     0.65, 0.15, 5, "SIMONS_SIX/DLC", "TRUE", "entry"),
            ProbNode("SSX009", Domain.OPTIONS_MECHANICS,
                     "DLC: DEX magnitude >95th percentile → explosive move imminent",
                     0.60, 0.20, 4, "SIMONS_SIX/DLC", "TRUE", "entry"),
            # TAPE WHISPER (TPW) — order flow scalp
            ProbNode("SSX010", Domain.ORDER_FLOW,
                     "TPW: Aggressive market order surge >3x passive limit → 60% follow",
                     0.60, 0.12, 4, "SIMONS_SIX/TPW", "TRUE", "entry"),
            ProbNode("SSX011", Domain.ORDER_FLOW,
                     "TPW: CVD + OBI alignment → 64% 30-sec momentum",
                     0.64, 0.15, 5, "SIMONS_SIX/TPW", "TRUE", "entry"),
            ProbNode("SSX012", Domain.ORDER_FLOW,
                     "TPW: Tape reading + footprint divergence → fakeout detection",
                     0.55, -0.12, 4, "SIMONS_SIX/TPW", "TRUE", "veto"),
            # GHOST STATE (GST) — regime transition
            ProbNode("SSX013", Domain.REGIME,
                     "GST: Hidden regime transition detected by state machine",
                     0.55, 0.15, 5, "SIMONS_SIX/GST", "TRUE", "regime"),
            ProbNode("SSX014", Domain.REGIME,
                     "GST: Fractal alignment 1m+5m+15m → high conviction state",
                     0.65, 0.18, 5, "SIMONS_SIX/GST", "TRUE", "entry"),
            ProbNode("SSX015", Domain.REGIME,
                     "GST: State persistence >5 candles → regime locked",
                     0.60, 0.12, 4, "SIMONS_SIX/GST", "TRUE", "context"),
            # 50-75 CLUB (FSC) — premium range scalp
            ProbNode("SSX016", Domain.OPTIONS_MECHANICS,
                     "FSC: Premium $0.50-$0.75 optimal for 30-60sec scalps",
                     0.58, 0.12, 4, "SIMONS_SIX/FSC", "TRUE", "entry"),
            ProbNode("SSX017", Domain.OPTIONS_MECHANICS,
                     "FSC: Target +30-50% premium gain in 30-60 seconds",
                     0.55, 0.15, 4, "SIMONS_SIX/FSC", "TRUE", "exit"),
            ProbNode("SSX018", Domain.OPTIONS_MECHANICS,
                     "FSC: Low premium = high gamma leverage, fast P&L swings",
                     0.55, 0.10, 4, "SIMONS_SIX/FSC", "TRUE", "sizing"),
        ]
        for n in nodes:
            self._register(n)

    # ── VOLUME PROFILE ────────────────────────────────────────────────────

    def _build_volume_profile_nodes(self) -> None:
        nodes = [
            ProbNode("VP001", Domain.INTRADAY_STATS,
                     "POC (Point of Control) acts as magnet — price within 0.3% = 62% reversion",
                     0.62, 0.15, 5, "Dalton(1990)/CBOT MarketProfile", "TRUE", "entry",
                     regime_mults={Regime.CHOP: 1.4}),
            ProbNode("VP002", Domain.INTRADAY_STATS,
                     "Value Area High/Low as S/R (70% rule: 80% of time price stays)",
                     0.58, 0.12, 4, "Dalton(1990)", "TRUE", "context"),
            ProbNode("VP003", Domain.INTRADAY_STATS,
                     "Low Volume Node (LVN) — price accelerates through, 55% velocity increase",
                     0.55, 0.12, 4, "Dalton(1990)", "TRUE", "entry"),
            ProbNode("VP004", Domain.INTRADAY_STATS,
                     "High Volume Node (HVN) — price consolidates, 65% pause probability",
                     0.65, -0.08, 3, "Dalton(1990)", "TRUE", "context"),
            ProbNode("VP005", Domain.INTRADAY_STATS,
                     "Single-print areas on TPO → likely revisit target",
                     0.55, 0.10, 3, "Dalton(1990)/Steidlmayer", "PARTIALLY_TRUE", "context"),
            ProbNode("VP006", Domain.INTRADAY_STATS,
                     "Developing POC migration direction → 60% continuation",
                     0.60, 0.12, 4, "Dalton(1990)", "TRUE", "entry"),
            ProbNode("VP007", Domain.INTRADAY_STATS,
                     "Volume gap between sessions → 70% fill within 2 hours",
                     0.70, 0.15, 4, "Dalton(1990)/Harris(1986)", "PARTIALLY_TRUE", "entry"),
            ProbNode("VP008", Domain.INTRADAY_STATS,
                     "VWAP deviation >1 ATR → mean-reversion 58% within 30min",
                     0.58, 0.12, 4, "Madhavan(1997)", "PARTIALLY_TRUE", "entry"),
            ProbNode("VP009", Domain.INTRADAY_STATS,
                     "Composite volume profile naked POC from prior day → magnet effect",
                     0.55, 0.10, 3, "Dalton(1990)", "TRUE", "context"),
            ProbNode("VP010", Domain.INTRADAY_STATS,
                     "Volume-weighted time analysis: >60% of volume in first 90min",
                     0.55, 0.08, 3, "Wood(1985)/Admati(1988)", "TRUE", "timing"),
        ]
        for n in nodes:
            self._register(n)

    # ── VOLATILITY SURFACE ────────────────────────────────────────────────

    def _build_volatility_surface_nodes(self) -> None:
        nodes = [
            ProbNode("VS001", Domain.OPTIONS_MECHANICS,
                     "IV rank >80 → premium selling edge, puts overpriced 8-12%",
                     0.58, 0.12, 4, "Bondarenko(2014)/Carr/Wu(2009)", "TRUE", "context"),
            ProbNode("VS002", Domain.OPTIONS_MECHANICS,
                     "IV rank <20 → long premium edge, gamma scalping viable",
                     0.55, 0.10, 3, "Bondarenko(2014)", "TRUE", "context"),
            ProbNode("VS003", Domain.OPTIONS_MECHANICS,
                     "Skew steepening (25D put vs call) → institutional hedging, -0.12",
                     0.55, -0.12, 4, "Bates(2000)/Carr/Wu(2009)", "TRUE", "context"),
            ProbNode("VS004", Domain.OPTIONS_MECHANICS,
                     "Term structure inversion (front>back IV) → near-term event priced",
                     0.60, 0.15, 4, "Bondarenko(2014)", "TRUE", "regime"),
            ProbNode("VS005", Domain.OPTIONS_MECHANICS,
                     "VRP positive (IV > RV) → short vol has edge, premium overpriced",
                     0.58, 0.08, 3, "Carr/Wu(2009)/Bollerslev(2009)", "TRUE", "context"),
            ProbNode("VS006", Domain.OPTIONS_MECHANICS,
                     "Realized vol >IV → vol regime shift, breakout more likely",
                     0.55, 0.12, 4, "Bollerslev(2009)", "TRUE", "regime"),
            ProbNode("VS007", Domain.OPTIONS_MECHANICS,
                     "0DTE IV crush: IV drops 15-25% in first 90min from open",
                     0.55, -0.08, 3, "Bondarenko(2024)", "TRUE", "timing"),
            ProbNode("VS008", Domain.OPTIONS_MECHANICS,
                     "Gamma/theta ratio optimization: max gamma per theta at 0.40-0.45 delta",
                     0.60, 0.12, 4, "Black/Scholes(1973)", "TRUE", "entry"),
            ProbNode("VS009", Domain.OPTIONS_MECHANICS,
                     "Vanna exposure: vol drop + price rise → dealer buying amplifies move",
                     0.55, 0.10, 3, "Barbon/Buraschi(2020)", "TRUE", "context"),
            ProbNode("VS010", Domain.OPTIONS_MECHANICS,
                     "Charm decay: delta shifts intraday on 0DTE by 0.02-0.05/hour",
                     0.55, -0.08, 3, "Black/Scholes(1973)", "TRUE", "context"),
        ]
        for n in nodes:
            self._register(n)

    # ── CANDLE GEOMETRY (geometric shape patterns with volume) ─────────

    def _build_candle_geometry_nodes(self) -> None:
        nodes = [
            ProbNode("CG001", Domain.INTRADAY_STATS,
                     "Doji at key level + volume >1.5x → 58% reversal",
                     0.58, 0.12, 4, "Nison(1991)/Lo(2000)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG002", Domain.INTRADAY_STATS,
                     "Engulfing pattern at S/R + volume confirmation → 55% continuation",
                     0.55, 0.10, 3, "Nison(1991)/Lo(2000)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG003", Domain.INTRADAY_STATS,
                     "3-bar narrowing range (inside-inside) → 70% breakout imminent",
                     0.70, 0.15, 4, "Crabel(1990)/Bollerslev(1986)", "TRUE", "regime"),
            ProbNode("CG004", Domain.INTRADAY_STATS,
                     "Pin bar / hammer with wick >2x body → 54% reversal signal",
                     0.54, 0.08, 3, "Nison(1991)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG005", Domain.INTRADAY_STATS,
                     "Momentum candle (body >80% of range) → 60% continuation next bar",
                     0.60, 0.12, 4, "Lo(2000)", "TRUE", "entry"),
            ProbNode("CG006", Domain.INTRADAY_STATS,
                     "Body-to-wick ratio >3:1 → strong conviction, 62% follow-through",
                     0.62, 0.12, 4, "Lo(2000)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG007", Domain.INTRADAY_STATS,
                     "Volume-weighted candle size: large candle + low volume = false move",
                     0.55, -0.10, 4, "Lo(2000)/Admati(1988)", "PARTIALLY_TRUE", "veto"),
            ProbNode("CG008", Domain.INTRADAY_STATS,
                     "Candle body shrinkage 3 consecutive → exhaustion, 58% reversal",
                     0.58, 0.10, 3, "Lo(2000)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG009", Domain.INTRADAY_STATS,
                     "Gap-and-go: open outside prior range + hold 5min → 55% continuation",
                     0.55, 0.10, 3, "Crabel(1990)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CG010", Domain.INTRADAY_STATS,
                     "Tick bar geometric symmetry → balanced market, mean-revert",
                     0.55, 0.08, 3, "Lopez de Prado(2018)", "PARTIALLY_TRUE", "context"),
        ]
        for n in nodes:
            self._register(n)

    # ── CROSS-TIMEFRAME ALIGNMENT ─────────────────────────────────────────

    def _build_cross_timeframe_nodes(self) -> None:
        nodes = [
            ProbNode("CT001", Domain.REGIME,
                     "1m+5m+15m all above respective EMAs → 72% bullish continuation",
                     0.72, 0.18, 5, "Mandelbrot/Hudson(2004)", "TRUE", "entry"),
            ProbNode("CT002", Domain.REGIME,
                     "1m above EMA but 15m below → conflicting, reduce to 50% sizing",
                     0.50, -0.10, 4, "Internal", "TRUE", "sizing"),
            ProbNode("CT003", Domain.REGIME,
                     "HTF (15m) trend + LTF (1m) pullback to EMA → 65% bounce",
                     0.65, 0.15, 5, "Internal", "TRUE", "entry"),
            ProbNode("CT004", Domain.REGIME,
                     "All timeframes in compression → 75% expansion within 30min",
                     0.75, 0.15, 4, "Bollerslev(1986)", "TRUE", "regime"),
            ProbNode("CT005", Domain.REGIME,
                     "Range bar alignment with time bars → 68% signal confirmation",
                     0.68, 0.12, 4, "Lopez de Prado(2018)", "TRUE", "entry"),
            ProbNode("CT006", Domain.REGIME,
                     "Tick bar momentum divergence from time bar → 55% early signal",
                     0.55, 0.10, 3, "Lopez de Prado(2018)", "PARTIALLY_TRUE", "entry"),
            ProbNode("CT007", Domain.REGIME,
                     "Daily pivot (PP) alignment with intraday VWAP → 62% S/R confluence",
                     0.62, 0.12, 4, "Dalton(1990)", "TRUE", "context"),
            ProbNode("CT008", Domain.REGIME,
                     "Weekly open + daily POC convergence → 70% key level",
                     0.70, 0.15, 4, "Dalton(1990)", "TRUE", "context"),
        ]
        for n in nodes:
            self._register(n)

    # ── PREMIUM DYNAMICS (multi-variant premium/velocity/acceleration) ──

    def _build_premium_dynamics_nodes(self) -> None:
        nodes = [
            ProbNode("PD001", Domain.OPTIONS_MECHANICS,
                     "Premium velocity >$0.10/s sustained 5s → 62% continuation 30s",
                     0.62, 0.15, 5, "MadTrades V6 internal", "TRUE", "entry"),
            ProbNode("PD002", Domain.OPTIONS_MECHANICS,
                     "Premium acceleration positive + velocity positive → rocket setup",
                     0.60, 0.18, 5, "MadTrades V6 internal", "TRUE", "entry"),
            ProbNode("PD003", Domain.OPTIONS_MECHANICS,
                     "Premium deceleration while price still moving → exit 65%",
                     0.65, -0.15, 5, "MadTrades V6 internal", "TRUE", "exit"),
            ProbNode("PD004", Domain.OPTIONS_MECHANICS,
                     "Premium spread >$0.10 on 0DTE → slippage risk, reduce size",
                     0.55, -0.12, 4, "Internal", "TRUE", "sizing"),
            ProbNode("PD005", Domain.OPTIONS_MECHANICS,
                     "Premium velocity divergence from underlying velocity → IV shift",
                     0.55, 0.10, 3, "Black/Scholes(1973)", "TRUE", "context"),
            ProbNode("PD006", Domain.OPTIONS_MECHANICS,
                     "Bid-ask tightening on 0DTE option → liquidity arriving, 58% move",
                     0.58, 0.10, 3, "Kyle(1985)", "TRUE", "context"),
            ProbNode("PD007", Domain.OPTIONS_MECHANICS,
                     "Premium per tick ratio vs delta → mispricing detection",
                     0.52, 0.08, 3, "Black/Scholes(1973)", "TRUE", "context"),
            ProbNode("PD008", Domain.OPTIONS_MECHANICS,
                     "Multi-strike grid: adjacent strikes confirm → 60% directional",
                     0.60, 0.12, 4, "Garleanu(2009)", "TRUE", "entry"),
            ProbNode("PD009", Domain.OPTIONS_MECHANICS,
                     "Premium band $1.50 sweet spot: max gamma/theta + manageable spread",
                     0.62, 0.15, 5, "MadTrades V6 F-0338", "TRUE", "entry"),
            ProbNode("PD010", Domain.OPTIONS_MECHANICS,
                     "Futures lead-lag premium: NQ move → QQQ option premium lags 4-12ms",
                     0.58, 0.15, 5, "Hasbrouck(1995)", "TRUE", "entry"),
        ]
        for n in nodes:
            self._register(n)

    # ── MAIN UPDATE LOOP ─────────────────────────────────────────────────

    def update(self, ctx: MarketContext) -> EngineOutput:
        ts = ctx.timestamp or time.time()

        self._update_order_flow(ctx, ts)
        self._update_intraday_stats(ctx, ts)
        self._update_macro_cross(ctx, ts)
        self._update_options_mechanics(ctx, ts)
        self._update_microstructure(ctx, ts)
        self._update_regime(ctx, ts)
        self._update_timing(ctx, ts)
        self._update_risk(ctx, ts)
        self._update_simons_six(ctx, ts)
        self._update_volume_profile(ctx, ts)
        self._update_volatility_surface(ctx, ts)
        self._update_candle_geometry(ctx, ts)
        self._update_cross_timeframe(ctx, ts)
        self._update_premium_dynamics(ctx, ts)

        for nid, node in self.nodes.items():
            if not node._is_live:
                node.decay(ts)

        domain_posteriors = {}
        domain_coverage = {}
        for d, w in self.workers.items():
            domain_posteriors[d.value] = w.collapse()
            domain_coverage[d.value] = w.coverage

        composite = self._composite_collapse(domain_posteriors)

        self._regime_history.append((ts, ctx.regime))
        self._composite_history.append((ts, composite))

        veto_active, veto_reasons = self._check_vetoes(ctx)
        if veto_active:
            composite = min(composite, 0.35)

        confidence_tier = "paper"
        for threshold, tier in CONFIDENCE_ROUTING:
            uncertainty = abs(composite - 0.5) * 2
            if 1 - uncertainty < threshold:
                confidence_tier = tier
                break

        avg_win = 0.03 * ctx.premium if ctx.premium > 0 else 1.0
        avg_loss = 0.015 * ctx.premium if ctx.premium > 0 else 1.0
        cost = 0.10 * 2
        ev = ev_gate(composite, avg_win, avg_loss, cost)
        kf = kelly_fraction(composite, avg_win / max(avg_loss, 0.01))
        bem = break_even_move(
            ctx.option_delta, ctx.option_gamma, cost,
            ctx.option_theta, 90.0
        ) if ctx.option_gamma != 0 else float('inf')

        sizing = self._compute_sizing(composite, ctx, confidence_tier)

        live_count = sum(1 for n in self.nodes.values() if n._is_live)
        dark_count = len(self.nodes) - live_count

        top_factors = self._top_factors(10)

        return EngineOutput(
            timestamp=ts,
            composite_posterior=composite,
            domain_posteriors=domain_posteriors,
            domain_coverage=domain_coverage,
            regime=ctx.regime,
            gex_regime=ctx.gex_regime,
            confidence_tier=confidence_tier,
            kelly_fraction=kf,
            ev=ev,
            break_even_move=bem,
            sizing_multiplier=sizing,
            live_node_count=live_count,
            dark_node_count=dark_count,
            total_node_count=len(self.nodes),
            top_factors=top_factors,
            veto_active=veto_active,
            veto_reasons=veto_reasons,
        )

    def _composite_collapse(self, domain_posts: dict[str, float]) -> float:
        baseline = logit(0.5)
        effects = []
        weights = []

        domain_importance = {
            "order_flow": 0.25, "intraday_stats": 0.15,
            "macro_cross": 0.12, "options_mechanics": 0.20,
            "microstructure": 0.08, "regime": 0.10,
            "timing": 0.05, "risk": 0.05,
        }

        for dname, post in domain_posts.items():
            w = domain_importance.get(dname, 0.1)
            cov = self.workers[Domain(dname)].coverage
            eff_w = w * cov
            if eff_w > 0:
                effects.append(eff_w * (logit(post) - baseline))
                weights.append(eff_w)

        if not weights:
            return 0.5

        total_w = sum(weights)
        mean_effect = sum(effects) / total_w
        return inv_logit(baseline + mean_effect)

    def _compute_sizing(self, composite: float, ctx: MarketContext,
                        tier: str) -> float:
        base = {"full": 1.0, "half": 0.5, "quarter": 0.25, "paper": 0.0}
        mult = base.get(tier, 0.0)

        if ctx.minutes_since_open >= 690:
            mult *= 0.5

        if ctx.vix > 30:
            mult *= 0.6

        if ctx.spread_bps > 20:
            mult *= 0.7

        if not ctx.premium_in_band and ctx.premium > 0:
            mult *= 0.5

        return min(max(mult, 0.0), 2.0)

    def _check_vetoes(self, ctx: MarketContext) -> tuple[bool, list[str]]:
        reasons = []

        if ctx.mag7_all_declining:
            reasons.append("VETO: Mag7 all declining — QQQ decline >90%")
        if ctx.vix_call_spike:
            reasons.append("VETO: VIX call volume >3x avg — downside in 8min")
        if ctx.hyg_below_vwap and ctx.price > ctx.vwap:
            reasons.append("VETO: HYG below VWAP, risk-off divergence")

        of021 = self.nodes.get("OF021")
        if of021 and of021._is_live and of021._current_posterior > 0.65:
            reasons.append("VETO: Liquidity depletion cascade risk >65%")

        rk004 = self.nodes.get("RK004")
        if rk004 and rk004._is_live and rk004._current_posterior > 0.6:
            reasons.append("VETO: Daily P&L drawdown limit")

        ms008 = self.nodes.get("MS008")
        if ms008 and ms008._is_live and ms008._current_posterior > 0.6:
            reasons.append("VETO: Quote staleness — data feed issue")

        return len(reasons) > 0, reasons

    def _top_factors(self, n: int) -> list[dict]:
        scored = []
        for node in self.nodes.values():
            if node._is_live:
                impact = abs(node.logit_effect) * node.effective_weight
                scored.append({
                    "id": node.id,
                    "domain": node.domain.value,
                    "description": node.description,
                    "posterior": round(node._current_posterior, 4),
                    "logit_effect": round(node.logit_effect, 4),
                    "weight": round(node.effective_weight, 4),
                    "impact": round(impact, 4),
                    "role": node.strategy_role,
                })
        scored.sort(key=lambda x: x["impact"], reverse=True)
        return scored[:n]

    # ── Node update dispatchers (map MarketContext fields → node updates) ─

    def _update_order_flow(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.obi != 0:
            obi_bull = (ctx.obi + 1) / 2
            for nid in ["OF005", "OF006"]:
                if nid in self.nodes:
                    self.nodes[nid].update(obi_bull, r, g, ts)

        if ctx.cvd_slope != 0:
            cvd_p = 0.5 + min(max(ctx.cvd_slope / 5.0, -0.3), 0.3)
            for nid in ["OF011", "OF012", "OF013", "OF014"]:
                if nid in self.nodes:
                    self.nodes[nid].update(cvd_p, r, g, ts)

        if ctx.vpin > 0:
            vpin_p = min(ctx.vpin, 0.99)
            for nid in ["OF033", "OF034"]:
                if nid in self.nodes:
                    self.nodes[nid].update(vpin_p, r, g, ts)

        if ctx.bid_depth_l1 > 0 and ctx.ask_depth_l1 > 0:
            depth_ratio = ctx.bid_depth_l1 / (ctx.bid_depth_l1 + ctx.ask_depth_l1)
            for nid in ["OF001", "OF002", "OF008", "OF031"]:
                if nid in self.nodes:
                    self.nodes[nid].update(depth_ratio, r, g, ts)

        if ctx.order_cancel_ratio > 0:
            cancel_p = min(ctx.order_cancel_ratio, 0.99)
            for nid in ["OF003", "OF004"]:
                if nid in self.nodes:
                    self.nodes[nid].update(cancel_p, r, g, ts)

        if ctx.gex != 0:
            gex_p = 0.5 + min(max(ctx.gex / 1e9, -0.3), 0.3)
            for nid in ["OF025", "OF026"]:
                if nid in self.nodes:
                    self.nodes[nid].update(gex_p, r, g, ts)

        if ctx.spread_bps > 0:
            spread_norm = min(ctx.spread_bps / 50.0, 0.99)
            for nid in ["OF029", "OF030"]:
                if nid in self.nodes:
                    self.nodes[nid].update(1.0 - spread_norm, r, g, ts)

        if ctx.block_trade_detected:
            for nid in ["OF038", "OF027", "OF028"]:
                if nid in self.nodes:
                    self.nodes[nid].update(0.70, r, g, ts)

        if ctx.es_nq_basis != 0:
            basis_p = 0.5 + min(max(ctx.es_nq_basis / 20.0, -0.3), 0.3)
            if "OF037" in self.nodes:
                self.nodes["OF037"].update(basis_p, r, g, ts)

    def _update_intraday_stats(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.ib_high > 0 and ctx.ib_low > 0:
            in_ib = ctx.ib_low <= ctx.price <= ctx.ib_high
            ib_p = 0.62 if in_ib else 0.38
            if "IS001" in self.nodes:
                self.nodes["IS001"].update(ib_p, r, g, ts)

        if ctx.atr_14 > 0:
            daily_range = ctx.day_high - ctx.day_low
            adr_ratio = daily_range / ctx.atr_14 if ctx.atr_14 > 0 else 1.0
            if adr_ratio > 2.5:
                if "IS003" in self.nodes:
                    self.nodes["IS003"].update(0.75, r, g, ts)
            if "IS005" in self.nodes:
                down_mult = 1.34 if ctx.price < ctx.vwap else 1.0
                self.nodes["IS005"].update(
                    min(0.5 + 0.1 * adr_ratio * down_mult, 0.95), r, g, ts
                )

        if ctx.opening_gap_pct != 0 and abs(ctx.opening_gap_pct) < 0.5:
            if "IS024" in self.nodes:
                self.nodes["IS024"].update(0.71, r, g, ts)

        if ctx.prev_day_poc > 0:
            poc_dist = abs(ctx.price - ctx.prev_day_poc) / max(ctx.atr_14, 0.01)
            poc_p = max(0.54 - poc_dist * 0.1, 0.3)
            if "IS017" in self.nodes:
                self.nodes["IS017"].update(poc_p, r, g, ts)

        if ctx.option_iv > 0:
            expected_move = ctx.price * ctx.option_iv / math.sqrt(252)
            dist_from_center = abs(ctx.price - ctx.vwap) / max(expected_move, 0.01)
            em_p = max(0.682 - dist_from_center * 0.2, 0.2)
            if "IS018" in self.nodes:
                self.nodes["IS018"].update(em_p, r, g, ts)

    def _update_macro_cross(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.es_price > 0 and ctx.nq_price > 0:
            if "MC001" in self.nodes:
                self.nodes["MC001"].update(0.60, r, g, ts)
            if ctx.futures_spot_corr < 0.95:
                if "MC002" in self.nodes:
                    self.nodes["MC002"].update(0.45, r, g, ts)
            nq_premium = ctx.nq_price - ctx.price * 100  # rough
            if nq_premium > 5 and "MC003" in self.nodes:
                self.nodes["MC003"].update(0.65, r, g, ts)

        if ctx.mag7_all_declining and "MC006" in self.nodes:
            self.nodes["MC006"].update(0.92, r, g, ts)

        if ctx.rsp_diverging and "MC007" in self.nodes:
            self.nodes["MC007"].update(0.74, r, g, ts)

        if ctx.hyg_below_vwap and "MC020" in self.nodes:
            self.nodes["MC020"].update(0.65, r, g, ts)

        if ctx.vix_call_spike and "MC014" in self.nodes:
            self.nodes["MC014"].update(0.75, r, g, ts)

        if ctx.xlp_xlu_outperform and "MC013" in self.nodes:
            self.nodes["MC013"].update(0.68, r, g, ts)

        if ctx.dxy_5m_corr < -0.85 and "MC018" in self.nodes:
            self.nodes["MC018"].update(0.65, r, g, ts)

        if ctx.vix > 30 and "MC016" in self.nodes:
            self.nodes["MC016"].update(0.75, r, g, ts)

    def _update_options_mechanics(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.premium_velocity != 0:
            vel_p = 0.5 + min(max(ctx.premium_velocity / 10.0, -0.3), 0.3)
            if "OM002" in self.nodes:
                self.nodes["OM002"].update(vel_p, r, g, ts)

        if ctx.premium_in_band and "OM003" in self.nodes:
            self.nodes["OM003"].update(0.72, r, g, ts)

        if ctx.zero_dte_volume_ratio > 1.5 and "OM001" in self.nodes:
            self.nodes["OM001"].update(0.65, r, g, ts)

        if ctx.gex != 0 and "OM009" in self.nodes:
            gex_p = 0.5 + min(max(ctx.gex / 1e9, -0.3), 0.3)
            self.nodes["OM009"].update(gex_p, r, g, ts)

        if ctx.dte == 0 and ctx.minutes_since_open > 330:
            if "OM006" in self.nodes:
                self.nodes["OM006"].update(0.75, r, g, ts)
            if "OM007" in self.nodes:
                self.nodes["OM007"].update(0.70, r, g, ts)

        if ctx.put_call_ratio > 0:
            pcr_extreme = abs(ctx.put_call_ratio - 1.0) / 0.5
            pcr_p = min(0.5 + pcr_extreme * 0.1, 0.75)
            if "OM011" in self.nodes:
                self.nodes["OM011"].update(pcr_p, r, g, ts)

        if ctx.option_iv > 0 and "OM013" in self.nodes:
            self.nodes["OM013"].update(
                min(0.5 + ctx.option_iv / 100.0, 0.85), r, g, ts
            )

    def _update_microstructure(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.spread_bps > 0:
            if ctx.spread_bps > ctx.atr_14 * 200 * 2 and "MS004" in self.nodes:
                self.nodes["MS004"].update(0.70, r, g, ts)
            if "MS007" in self.nodes:
                lambda_mult = min(ctx.spread_bps / 10.0, 3.0)
                self.nodes["MS007"].update(
                    min(0.5 + lambda_mult * 0.1, 0.85), r, g, ts
                )

        if ctx.obi != 0:
            obi_persist = min(abs(ctx.obi) / 0.3, 1.0)
            if "MS003" in self.nodes:
                self.nodes["MS003"].update(0.5 + obi_persist * 0.2, r, g, ts)

    def _update_regime(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.ib_high > 0 and ctx.ib_low > 0:
            broken = ctx.price > ctx.ib_high or ctx.price < ctx.ib_low
            if "RG001" in self.nodes:
                self.nodes["RG001"].update(0.62 if broken else 0.38, r, g, ts)

        if ctx.vix > 25 and "RG002" in self.nodes:
            self.nodes["RG002"].update(0.70, r, g, ts)

        if ctx.bb_upper > 0 and ctx.bb_lower > 0:
            bb_width = (ctx.bb_upper - ctx.bb_lower) / max(ctx.price, 1)
            if bb_width < 0.01 and "RG003" in self.nodes:
                self.nodes["RG003"].update(0.72, r, g, ts)

        if ctx.atr_14 > 0:
            if "RG004" in self.nodes:
                daily_range = ctx.day_high - ctx.day_low
                adr_ratio = daily_range / ctx.atr_14
                self.nodes["RG004"].update(
                    min(0.5 + adr_ratio * 0.05, 0.85), r, g, ts
                )

        if ctx.gex != 0:
            current_gex_sign = 1 if ctx.gex > 0 else -1
            if "RG007" in self.nodes:
                self.nodes["RG007"].update(0.65, r, g, ts)

    def _update_timing(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.is_power_hour and "TM001" in self.nodes:
            self.nodes["TM001"].update(0.65, r, g, ts)

        if ctx.is_lunch and "TM002" in self.nodes:
            self.nodes["TM002"].update(0.70, r, g, ts)

        if ctx.is_first_15 and "TM003" in self.nodes:
            self.nodes["TM003"].update(0.70, r, g, ts)

        if ctx.minutes_since_open < 90 and "TM003" in self.nodes:
            self.nodes["TM003"].update(0.65, r, g, ts)

        if ctx.is_event_day and "TM005" in self.nodes:
            self.nodes["TM005"].update(0.70, r, g, ts)

        if ctx.dte == 0 and ctx.minutes_since_open > 360:
            if "TM008" in self.nodes:
                self.nodes["TM008"].update(0.75, r, g, ts)

    def _update_risk(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.vix > 30 and "RK002" in self.nodes:
            self.nodes["RK002"].update(0.75, r, g, ts)

        if ctx.spread_bps > 20 and "RK006" in self.nodes:
            self.nodes["RK006"].update(0.70, r, g, ts)

    # ── New domain update dispatchers ────────────────────────────────────

    def _update_simons_six(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        # LCL — Last Call (power hour entries)
        if ctx.is_power_hour and ctx.minutes_since_open >= 330:
            if ctx.premium_in_band and "SSX001" in self.nodes:
                self.nodes["SSX001"].update(0.65, r, g, ts)
            if ctx.premium > 0 and 1.0 <= ctx.premium <= 2.0:
                if "SSX002" in self.nodes:
                    self.nodes["SSX002"].update(0.70, r, g, ts)
            if ctx.dte == 0 and "SSX003" in self.nodes:
                self.nodes["SSX003"].update(0.72, r, g, ts)

        # FNJ — Fence Jumper (failed breakout)
        if ctx.ib_high > 0 and ctx.ib_low > 0:
            near_ib = (abs(ctx.price - ctx.ib_high) < ctx.atr_14 * 0.3 or
                       abs(ctx.price - ctx.ib_low) < ctx.atr_14 * 0.3)
            if near_ib and ctx.volume_ratio > 1.5:
                for nid in ["SSX004", "SSX005"]:
                    if nid in self.nodes:
                        self.nodes[nid].update(0.65, r, g, ts)

        # DLC — Dealer's Choice (GEX-driven)
        if ctx.gex != 0:
            gex_flip_proximity = abs(ctx.gex) < 1e8
            if gex_flip_proximity and "SSX007" in self.nodes:
                self.nodes["SSX007"].update(0.68, r, g, ts)
            if ctx.dex != 0 and "SSX009" in self.nodes:
                dex_p = min(0.5 + abs(ctx.dex) / 1e9, 0.85)
                self.nodes["SSX009"].update(dex_p, r, g, ts)

        # TPW — Tape Whisper (order flow)
        if ctx.obi != 0 and ctx.cvd_slope != 0:
            alignment = (ctx.obi > 0 and ctx.cvd_slope > 0) or \
                        (ctx.obi < 0 and ctx.cvd_slope < 0)
            if alignment and "SSX011" in self.nodes:
                self.nodes["SSX011"].update(0.68, r, g, ts)

        # GST — Ghost State (regime transition)
        if ctx.fractal_state != "unknown" and "SSX013" in self.nodes:
            self.nodes["SSX013"].update(0.60, r, g, ts)

    def _update_volume_profile(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.prev_day_poc > 0 and ctx.atr_14 > 0:
            poc_dist = abs(ctx.price - ctx.prev_day_poc) / ctx.atr_14
            if poc_dist < 0.3 and "VP001" in self.nodes:
                self.nodes["VP001"].update(0.68, r, g, ts)

        if ctx.vwap > 0 and ctx.atr_14 > 0:
            vwap_dev = abs(ctx.price - ctx.vwap) / ctx.atr_14
            if vwap_dev > 1.0 and "VP008" in self.nodes:
                self.nodes["VP008"].update(0.62, r, g, ts)

        if ctx.minutes_since_open < 90 and "VP010" in self.nodes:
            self.nodes["VP010"].update(0.65, r, g, ts)

    def _update_volatility_surface(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.option_iv > 0:
            if ctx.option_iv > 40 and "VS001" in self.nodes:
                self.nodes["VS001"].update(0.65, r, g, ts)
            elif ctx.option_iv < 15 and "VS002" in self.nodes:
                self.nodes["VS002"].update(0.60, r, g, ts)

            if "VS004" in self.nodes:
                self.nodes["VS004"].update(
                    min(0.5 + ctx.option_iv / 80.0, 0.80), r, g, ts
                )

        if ctx.dte == 0 and ctx.minutes_since_open < 90 and "VS007" in self.nodes:
            self.nodes["VS007"].update(0.65, r, g, ts)

        if 0.40 <= abs(ctx.option_delta) <= 0.45 and "VS008" in self.nodes:
            self.nodes["VS008"].update(0.68, r, g, ts)

    def _update_candle_geometry(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.bb_upper > 0 and ctx.bb_lower > 0:
            bb_width = (ctx.bb_upper - ctx.bb_lower) / max(ctx.price, 1)
            if bb_width < 0.005 and "CG003" in self.nodes:
                self.nodes["CG003"].update(0.75, r, g, ts)

        if ctx.velocity_5s != 0 and ctx.volume_ratio > 0:
            if abs(ctx.velocity_5s) > ctx.atr_14 * 0.1 and ctx.volume_ratio > 1.5:
                if "CG005" in self.nodes:
                    self.nodes["CG005"].update(0.65, r, g, ts)
            if abs(ctx.velocity_5s) > ctx.atr_14 * 0.1 and ctx.volume_ratio < 0.5:
                if "CG007" in self.nodes:
                    self.nodes["CG007"].update(0.65, r, g, ts)

    def _update_cross_timeframe(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        above_emas = (ctx.price > ctx.ema9 and ctx.price > ctx.ema20
                      and ctx.price > ctx.ema144)
        if above_emas and "CT001" in self.nodes:
            self.nodes["CT001"].update(0.75, r, g, ts)

        mixed = (ctx.price > ctx.ema9 and ctx.price < ctx.ema144)
        if mixed and "CT002" in self.nodes:
            self.nodes["CT002"].update(0.45, r, g, ts)

        if ctx.price > ctx.ema144 and abs(ctx.price - ctx.ema9) < ctx.atr_14 * 0.2:
            if "CT003" in self.nodes:
                self.nodes["CT003"].update(0.68, r, g, ts)

        if ctx.bb_upper > 0 and ctx.bb_lower > 0:
            bb_width = (ctx.bb_upper - ctx.bb_lower) / max(ctx.price, 1)
            if bb_width < 0.005 and "CT004" in self.nodes:
                self.nodes["CT004"].update(0.78, r, g, ts)

        if ctx.prev_day_poc > 0 and ctx.vwap > 0:
            poc_vwap_gap = abs(ctx.prev_day_poc - ctx.vwap) / max(ctx.atr_14, 0.01)
            if poc_vwap_gap < 0.5 and "CT007" in self.nodes:
                self.nodes["CT007"].update(0.68, r, g, ts)

    def _update_premium_dynamics(self, ctx: MarketContext, ts: float) -> None:
        r, g = ctx.regime, ctx.gex_regime

        if ctx.premium_velocity != 0:
            if abs(ctx.premium_velocity) > 0.10 and "PD001" in self.nodes:
                vel_p = min(0.5 + abs(ctx.premium_velocity) / 0.5, 0.85)
                self.nodes["PD001"].update(vel_p, r, g, ts)

            if ctx.premium_acceleration > 0 and ctx.premium_velocity > 0:
                if "PD002" in self.nodes:
                    self.nodes["PD002"].update(0.70, r, g, ts)

            if ctx.premium_acceleration < 0 and abs(ctx.premium_velocity) > 0.05:
                if "PD003" in self.nodes:
                    self.nodes["PD003"].update(0.70, r, g, ts)

        if ctx.spread_bps > 10 and ctx.dte == 0 and "PD004" in self.nodes:
            self.nodes["PD004"].update(0.65, r, g, ts)

        if ctx.premium_in_band and "PD009" in self.nodes:
            self.nodes["PD009"].update(0.70, r, g, ts)

        if ctx.es_nq_basis != 0 and ctx.premium_velocity != 0:
            if "PD010" in self.nodes:
                self.nodes["PD010"].update(0.62, r, g, ts)

    # ── Diagnostic ────────────────────────────────────────────────────────

    def status(self) -> dict:
        live = sum(1 for n in self.nodes.values() if n._is_live)
        dark = len(self.nodes) - live
        return {
            "total_nodes": len(self.nodes),
            "live_nodes": live,
            "dark_nodes": dark,
            "domains": {
                d.value: {
                    "nodes": len(w.nodes),
                    "live": len(w.live_nodes),
                    "posterior": round(w._posterior, 4),
                    "coverage": round(w.coverage, 4),
                }
                for d, w in self.workers.items()
            },
        }


# ---------------------------------------------------------------------------
# Convenience: run the engine on a MarketContext dict
# ---------------------------------------------------------------------------

def run_engine(ctx_dict: dict) -> dict:
    engine = BayesianProbabilityEngine()
    ctx = MarketContext(**{
        k: v for k, v in ctx_dict.items()
        if hasattr(MarketContext, k)
    })
    output = engine.update(ctx)
    return {
        "composite_posterior": round(output.composite_posterior, 6),
        "domain_posteriors": {
            k: round(v, 4) for k, v in output.domain_posteriors.items()
        },
        "domain_coverage": {
            k: round(v, 4) for k, v in output.domain_coverage.items()
        },
        "regime": output.regime.value,
        "gex_regime": output.gex_regime.value,
        "confidence_tier": output.confidence_tier,
        "kelly_fraction": round(output.kelly_fraction, 4),
        "ev": round(output.ev, 4),
        "sizing_multiplier": round(output.sizing_multiplier, 4),
        "live_nodes": output.live_node_count,
        "dark_nodes": output.dark_node_count,
        "total_nodes": output.total_node_count,
        "top_factors": output.top_factors[:5],
        "veto_active": output.veto_active,
        "veto_reasons": output.veto_reasons,
    }


if __name__ == "__main__":
    import json

    engine = BayesianProbabilityEngine()
    print(json.dumps(engine.status(), indent=2))
    print(f"\nTotal probability nodes: {len(engine.nodes)}")
    print(f"Domains: {len(engine.workers)}")
    for d, w in engine.workers.items():
        print(f"  {d.value}: {len(w.nodes)} nodes")

    ctx = MarketContext(
        timestamp=time.time(),
        price=480.50,
        vwap=480.00,
        ema9=480.20,
        ema20=479.80,
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
    print(f"\n{'='*60}")
    print(f"COMPOSITE POSTERIOR: {output.composite_posterior:.4f}")
    print(f"REGIME: {output.regime.value}")
    print(f"GEX REGIME: {output.gex_regime.value}")
    print(f"CONFIDENCE TIER: {output.confidence_tier}")
    print(f"KELLY FRACTION: {output.kelly_fraction:.4f}")
    print(f"EV: {output.ev:.4f}")
    print(f"SIZING MULTIPLIER: {output.sizing_multiplier:.4f}")
    print(f"LIVE/DARK/TOTAL: {output.live_node_count}/{output.dark_node_count}/{output.total_node_count}")
    print(f"VETO: {output.veto_active} — {output.veto_reasons}")
    print(f"\nTOP FACTORS:")
    for f in output.top_factors[:5]:
        print(f"  {f['id']} [{f['domain']}] {f['description'][:60]}")
        print(f"    posterior={f['posterior']:.4f} effect={f['logit_effect']:.4f} impact={f['impact']:.4f}")
