"""
Priors extracted from the V19_Conservative 0DTE Scalping Strategy document.

Source: Google Drive "Backtesting 0DTE Scalping Strategy" doc
Strategy: V19_Conservative: PF 2.85, WR 68.5%, Max DD -4.2%, avg trade 12 min
CAUTION: Document uses $0.65/contract commission — Josh's real fee is $0.10/side.
PF numbers need recalculation with correct fees per MADX backtest laws.

All priors marked EXTERNAL tier since they come from an outside document
and have not been verified on our own data yet.
"""
from bayesian_prior_factory import (
    BayesianPrior, PriorCategory, EvidenceTier, InputType,
    PriorRegistry,
)


def seed_v19_strategy_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="V19_RSI_KILL_ZONE_40_60",
            name="RSI 40-60 kill zone filter",
            category=PriorCategory.REGIME,
            tier=EvidenceTier.EXTERNAL,
            condition="RSI(14) between 40-60 on entry timeframe",
            outcome="~40% of false signals removed; remaining trades PF 2.85",
            probability=0.685,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.SPECTRUM,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="RSI 40-60 is the 'kill zone' where signals are ambiguous. "
                  "EXTERNAL — uses $0.65 commission, needs recalc at $0.10/side.",
        ),
        BayesianPrior(
            id="V19_10MIN_TIME_STOP",
            name="10-minute time stop if no 1x ATR profit",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.EXTERNAL,
            condition="Position open > 10 minutes without reaching 1.0x ATR profit",
            outcome="Exit — trade thesis invalidated",
            probability=0.50,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="If the move hasn't happened in 10 min, it's not coming. "
                  "EXTERNAL — needs verification on our data.",
        ),
        BayesianPrior(
            id="V19_THETA_CLIFF_1530",
            name="Theta cliff at 15:30 ET for 0DTE",
            category=PriorCategory.GREEKS,
            tier=EvidenceTier.EXTERNAL,
            condition="Time >= 15:30 ET on 0DTE option",
            outcome="Theta decay accelerates ~100x vs 45-day option; "
                    "premium erosion overwhelms directional edge",
            probability=0.40,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY", "QQQ"],
            timeframe="0DTE",
            notes="After 15:30 ET, theta acceleration makes 0DTE "
                  "directional trades unprofitable even with correct direction. "
                  "Power hour size reduces 50%, stops at 15:30.",
        ),
        BayesianPrior(
            id="V19_MORNING_DRIVE_0945_1100",
            name="Morning drive 09:45-11:00 highest ATR/volume",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.EXTERNAL,
            condition="Time between 09:45-11:00 ET",
            outcome="Highest ATR and volume of the session — best scalp window",
            probability=0.65,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY", "QQQ"],
            timeframe="0DTE",
            notes="Aligns with our own morning lock findings. "
                  "F01 uses <11:30 ET, V19 uses 09:45-11:00 ET.",
        ),
        BayesianPrior(
            id="V19_LUNCH_DORMANT_1130_1330",
            name="Lunch doldrums 11:30-13:30 dormant state",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.EXTERNAL,
            condition="Time between 11:30-13:30 ET",
            outcome="Volume drops 40-60%; ATR collapses; strategy enters dormant",
            probability=0.35,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY", "QQQ"],
            timeframe="0DTE",
            notes="Confirms F01 midday chop veto (11:30-13:50). "
                  "EXTERNAL — V19 data, not verified internally.",
        ),
        BayesianPrior(
            id="V19_ATR_MINIMUM_GATE",
            name="ATR minimum threshold for trade entry",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.EXTERNAL,
            condition="Current ATR above minimum threshold for instrument",
            outcome="Sufficient volatility for scalp profit target",
            probability=0.60,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.SPECTRUM,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="Below threshold -> dormant state (no entries). "
                  "Prevents trading in dead-vol environments.",
        ),
        BayesianPrior(
            id="V19_CIRCUIT_BREAKER_3PCT",
            name="Circuit breaker: -3% daily or 3 consecutive losses",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.EXTERNAL,
            condition="Daily loss >= -3% OR 3 consecutive losses",
            outcome="Halt all trading for the day",
            probability=0.50,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            notes="Risk management circuit breaker. "
                  "Similar to F01 capital governor (-2.5% -> 0.5x, -5% -> halt). "
                  "EXTERNAL — not yet wired into our system.",
        ),
        BayesianPrior(
            id="V19_MEAN_REVERSION_BOLLINGER",
            name="Pure mean reversion (Bollinger) PF 2.10 WR 72%",
            category=PriorCategory.REGIME,
            tier=EvidenceTier.EXTERNAL,
            condition="Bollinger band mean reversion setup",
            outcome="PF 2.10, WR 72.0% in V19 backtest",
            probability=0.72,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="Highest WR of the V19 strategy variants. "
                  "EXTERNAL — uses $0.65 commission.",
        ),
        BayesianPrior(
            id="V19_MOMENTUM_BREAKOUT_ATR",
            name="Momentum breakout (ATR) PF 1.85 WR 45%",
            category=PriorCategory.REGIME,
            tier=EvidenceTier.EXTERNAL,
            condition="ATR-based momentum breakout setup",
            outcome="PF 1.85, WR 45.0% in V19 backtest",
            probability=0.45,
            sample_size=0,
            time_period="V19 backtest period",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.BINARY,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="Lower WR but higher avg win. "
                  "EXTERNAL — uses $0.65 commission.",
        ),
        BayesianPrior(
            id="V19_0DTE_GAMMA_SWING",
            name="0DTE gamma: $0.50 move swings delta 0.50->0.90",
            category=PriorCategory.GREEKS,
            tier=EvidenceTier.EXTERNAL,
            condition="0DTE ATM option with $0.50 underlying move",
            outcome="Delta swings from ~0.50 to ~0.90 (non-linear amplification)",
            probability=0.70,
            sample_size=0,
            time_period="V19 backtest analysis",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.SPECTRUM,
            tickers=["SPY"],
            timeframe="0DTE",
            notes="Gamma amplification makes 0DTE non-linear. "
                  "Small underlying moves -> large premium changes. "
                  "This is the mechanism behind 0DTE scalping edges.",
        ),
        BayesianPrior(
            id="V19_SPREAD_FRICTION_1C",
            name="$0.01 bid-ask = 20% of $0.10 scalp target",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.EXTERNAL,
            condition="Bid-ask spread = $0.01 on option with $0.10 profit target",
            outcome="Spread friction consumes 20% of expected profit",
            probability=0.50,
            sample_size=0,
            time_period="V19 backtest analysis",
            source="V19_Conservative 0DTE backtest doc",
            input_type=InputType.SPECTRUM,
            tickers=["SPY", "QQQ"],
            timeframe="0DTE",
            notes="At wider spreads ($0.03+), friction becomes prohibitive. "
                  "Confirms F01 1-cent spread gate importance.",
        ),
    ]

    count = 0
    for p in priors:
        registry.register(p)
        count += 1
    return count


if __name__ == "__main__":
    registry = PriorRegistry()
    n = seed_v19_strategy_priors(registry)
    print(f"V19 strategy priors seeded: {n}")
    for p in registry.priors.values():
        print(f"  [{p.tier.value:12s}] {p.id}: {p.name}")
