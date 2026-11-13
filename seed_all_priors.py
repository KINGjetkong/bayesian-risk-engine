"""
Seed ALL Bayesian priors from every source:
  - Published research (58 rules from web research agent)
  - Edgeful session statistics (150+ report types)
  - POD_A7 regime-locked strategies (13 variants from Drive)
  - State Registry LOCKED forensics
  - Repo 200-node engine key signals
  - Calendar/event day priors
  - Cross-asset priors
  - Microstructure priors

Target: 200+ total priors across 19 categories.
"""
from bayesian_prior_factory import (
    BayesianPrior, PriorCategory, EvidenceTier, InputType,
    PriorRegistry,
    seed_seasonality_priors,
    seed_time_of_day_priors,
    seed_regime_priors,
)


def seed_gap_fill_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="GAP_SPY_SMALL_UP_FILL",
            name="SPY small gap up fill",
            category=PriorCategory.GAP,
            tier=EvidenceTier.RESEARCH,
            condition="gap up 0.0-0.25% SPY",
            outcome="Same-day full gap fill",
            probability=0.74,
            sample_size=8397,
            time_period="1993-2026 (StatOasis)",
            source="StatOasis SP500 opening gaps study",
            source_url="https://statoasis.com/overfit/research/sp500-opening-gaps",
            tickers=["SPY"],
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="GAP_QQQ_DOWN_MED_FILL",
            name="QQQ medium gap down fill",
            category=PriorCategory.GAP,
            tier=EvidenceTier.RESEARCH,
            condition="gap down 0.5-0.99% QQQ",
            outcome="Same-day full gap fill ~59%, partial ~77%",
            probability=0.59,
            sample_size=500,
            time_period="Epicctrader multi-year",
            source="Epicctrader gap fills study",
            tickers=["QQQ"],
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="GAP_LARGE_NO_FILL",
            name="Large gap (>2%) does not fill",
            category=PriorCategory.GAP,
            tier=EvidenceTier.RESEARCH,
            condition="gap up or down >= 2%",
            outcome="Gap does NOT fill same day ~67-71%",
            probability=0.31,
            sample_size=275,
            time_period="2000-2026 (Kai Yasuda)",
            source="Multiple: StatOasis + Kai Yasuda + Shareplanner",
            tickers=["QQQ", "SPY"],
            knowable_before_open=True,
            notes="Fading large gaps is a LOSING strategy (PF 0.65)",
        ),
        BayesianPrior(
            id="GAP_SIZE_INVERSE_FILL",
            name="Gap size inversely correlated with fill rate",
            category=PriorCategory.GAP,
            tier=EvidenceTier.RESEARCH,
            condition="gap size increases (any direction)",
            outcome="Fill probability decreases, forward drift increases",
            probability=0.65,
            sample_size=8397,
            time_period="Multiple studies",
            source="StatOasis + Kai Yasuda (consistent)",
            input_type=InputType.SPECTRUM,
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="GAP_YM_TINY_UP_FILL",
            name="YM tiny gap up high fill",
            category=PriorCategory.GAP,
            tier=EvidenceTier.EXTERNAL,
            condition="gap up 0.0-0.19% YM",
            outcome="Same-day gap fill ~88-90%",
            probability=0.89,
            sample_size=100,
            time_period="Last 6 months (Edgeful blog)",
            source="Edgeful blog",
            tickers=["YM"],
            knowable_before_open=True,
            notes="Short sample window, verify via Edgeful API",
        ),
        BayesianPrior(
            id="GAP_DIRECTION_CONTINUATION",
            name="Gap direction predicts range not direction",
            category=PriorCategory.GAP,
            tier=EvidenceTier.RESEARCH,
            condition="strong opening gap any direction",
            outcome="First hour range wider, direction NOT predictable",
            probability=0.50,
            sample_size=3924,
            time_period="Krueger Algorithms multi-year",
            source="Krueger Algorithms",
            input_type=InputType.BINARY,
            knowable_before_open=True,
            notes="Gap size predicts RANGE not DIRECTION",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_orb_ib_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="ORB_5MIN_BREAKEVEN",
            name="5-min ORB breakout unfiltered",
            category=PriorCategory.ORB,
            tier=EvidenceTier.RESEARCH,
            condition="5-min ORB breakout (unfiltered)",
            outcome="WR ~54%, PF ~1.03 (breakeven)",
            probability=0.54,
            sample_size=142348,
            time_period="TrueTrader 3,106 real fills + 142K sim",
            source="TrueTrader ORB study",
            notes="Largest sample found. Real 1s fills. Unfiltered = no edge.",
        ),
        BayesianPrior(
            id="ORB_15MIN_BREAKOUT",
            name="15-min ORB breakout",
            category=PriorCategory.ORB,
            tier=EvidenceTier.RESEARCH,
            condition="15-min ORB breakout",
            outcome="WR ~55.3%",
            probability=0.553,
            sample_size=1170000,
            time_period="ORBSetups 1.17M trades",
            source="ORBSetups + TrueTrader",
        ),
        BayesianPrior(
            id="ORB_0DTE_SPY_FAT_TAIL",
            name="SPY 0DTE ORB breakout fat tail",
            category=PriorCategory.ORB,
            tier=EvidenceTier.RESEARCH,
            condition="SPY 0DTE 5-min ORB breakout",
            outcome="Option WR ~41%, but +59% total return (fat right tail)",
            probability=0.41,
            sample_size=500,
            time_period="Feb 2024 - Mar 2026 (Options Cafe)",
            source="Options Cafe SPY 0DTE ORB backtest",
            tickers=["SPY"],
            notes="Low WR but convex payoff. Paper-traded.",
        ),
        BayesianPrior(
            id="IB_ES_SINGLE_BREAK",
            name="ES Initial Balance single break",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="ES initial balance (60-min) broken in one direction",
            outcome="Probability ~68%",
            probability=0.68,
            sample_size=2500,
            time_period="2015-2025 (TradingStats + Edgeful)",
            source="TradingStats.net + Edgeful blog",
        ),
        BayesianPrior(
            id="IB_ES_DOUBLE_BREAK",
            name="ES Initial Balance double break",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="ES initial balance broken in both directions",
            outcome="Probability ~29%",
            probability=0.29,
            sample_size=2500,
            time_period="2015-2025",
            source="TradingStats.net + Edgeful",
        ),
        BayesianPrior(
            id="IB_NQ_SINGLE_BREAK",
            name="NQ Initial Balance single break",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="NQ initial balance broken one direction",
            outcome="Probability ~72%",
            probability=0.72,
            sample_size=500,
            time_period="Last 6 months (Edgeful)",
            source="Edgeful blog",
            tickers=["QQQ"],
        ),
        BayesianPrior(
            id="IB_CONTAINED_RARE",
            name="IB contained day extremely rare",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="ES stays within IB all day (no breakout)",
            outcome="Only 0.6% probability",
            probability=0.006,
            sample_size=2500,
            time_period="10-year TrevorTrades dashboard",
            source="TrevorTrades IB dashboard",
            notes="99.4% of days break IB at least once",
        ),
        BayesianPrior(
            id="IB_HALF_EXTENSION",
            name="IB 0.5x extension common",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="ES IB break occurs",
            outcome="Reaches 0.5x IB extension ~69.5% of sessions",
            probability=0.695,
            sample_size=2500,
            time_period="TrevorTrades 10yr",
            source="TrevorTrades IB dashboard",
        ),
        BayesianPrior(
            id="IB_NQ_1_4X_REVERSAL",
            name="NQ IB 1.4x extension reversal zone",
            category=PriorCategory.INITIAL_BALANCE,
            tier=EvidenceTier.RESEARCH,
            condition="NQ IB break reaches 1.4x extension",
            outcome="Reversal probability overtakes continuation",
            probability=0.55,
            sample_size=1000,
            time_period="TradingStats.net multi-year",
            source="TradingStats.net IB retest statistics",
            notes="Key level for TP calibration",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_event_day_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="EVENT_CPI_PF",
            name="CPI day live PF 5.25",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.LOCKED,
            condition="CPI release day",
            outcome="Live Tradier PF 5.25 (n=14)",
            probability=0.71,
            sample_size=14,
            time_period="Live Alpaca forensics",
            source="State Registry F-0232",
            verified_internally=True,
            verification_pf=5.25,
            knowable_before_open=True,
            notes="Highest PF of all day types. 77% of $ from event days.",
        ),
        BayesianPrior(
            id="EVENT_FOMC_SWINGS",
            name="FOMC day largest intraday swings",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="FOMC announcement day",
            outcome="Largest intraday rate-probability swings",
            probability=0.72,
            sample_size=200,
            time_period="Federal Reserve paper + NBER",
            source="Federal Reserve + NBER papers",
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="EVENT_CPI_FOMC_PROXIMITY",
            name="CPI near FOMC amplified",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="CPI within 10 trading days of FOMC",
            outcome="Post-CPI signal WR ~69.8% vs ~61.9% otherwise",
            probability=0.698,
            sample_size=14,
            time_period="iPResage study",
            source="iPResage CPI options backtest",
            knowable_before_open=True,
            notes="TINY sample (14 instances). Treat as hypothesis.",
        ),
        BayesianPrior(
            id="EVENT_OPEX_WEEK_UP",
            name="OPEX week closes higher",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="Monthly OPEX week",
            outcome="SPX closes higher 57.3% (avg return +0.11%)",
            probability=0.573,
            sample_size=239,
            time_period="2006-2026 (TradeIntel)",
            source="TradeIntel OPEX study",
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="EVENT_QUAD_WITCH_UP",
            name="Quad-witching week stronger",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="Quad-witching OPEX week",
            outcome="Closed higher 63.7% (51/80 weeks)",
            probability=0.637,
            sample_size=80,
            time_period="2006-2026 (TradeIntel)",
            source="TradeIntel quad-witching study",
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="EVENT_OPEX_DAY_WEAK",
            name="OPEX day itself is weak",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="Options expiration Friday",
            outcome="WR 51.4%, compounded returns -23.55%",
            probability=0.514,
            sample_size=300,
            time_period="Quantified Strategies multi-year",
            source="Quantified Strategies OPEX study",
            knowable_before_open=True,
            notes="OPEX WEEK positive, OPEX DAY weak. Key distinction.",
        ),
        BayesianPrior(
            id="EVENT_OPEX_WIDER_RANGE",
            name="OPEX Friday wider ranges",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="Expiration Friday with high OI",
            outcome="Ranges ~16% wider (amplification not pinning)",
            probability=0.60,
            sample_size=2294,
            time_period="2016-2025 (Harbourfront Quant)",
            source="Harbourfront Quant academic-style study",
            notes="Pinning is a MYTH at aggregate level. Amplification is real.",
        ),
        BayesianPrior(
            id="EVENT_PPI_HIGH_PF",
            name="PPI day live PF 17.5",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.LOCKED,
            condition="PPI release day",
            outcome="Live Tradier PF 17.5 (n=14)",
            probability=0.75,
            sample_size=14,
            time_period="Live Alpaca forensics",
            source="State Registry F-0232",
            verified_internally=True,
            verification_pf=17.5,
            knowable_before_open=True,
            notes="Highest PF of ALL day types. Tiny n.",
        ),
        BayesianPrior(
            id="EVENT_NORMAL_DAY_PF",
            name="Normal day live PF 1.37",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.LOCKED,
            condition="Normal (no event) day",
            outcome="Live Tradier PF 1.37 (n=113)",
            probability=0.55,
            sample_size=113,
            time_period="Live Alpaca forensics",
            source="State Registry F-0232",
            verified_internally=True,
            verification_pf=1.37,
            knowable_before_open=True,
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_streak_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="STREAK_1_2_UP_CONT",
            name="1-2 day up streak continuation",
            category=PriorCategory.STREAK,
            tier=EvidenceTier.RESEARCH,
            condition="SPY up 1-2 consecutive days",
            outcome="Next day up ~57-58%",
            probability=0.575,
            sample_size=15000,
            time_period="1950-2011 (Seeking Alpha + Crestmont)",
            source="Seeking Alpha + Crestmont Research",
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="STREAK_6_DOWN_REVERSION",
            name="6+ day down streak mean reversion",
            category=PriorCategory.STREAK,
            tier=EvidenceTier.RESEARCH,
            condition="SPY down 6+ consecutive days",
            outcome="Next day up >57%",
            probability=0.57,
            sample_size=200,
            time_period="1950-2011",
            source="Seeking Alpha long-term study",
            knowable_before_open=True,
            notes="Rare events but consistent across long history",
        ),
        BayesianPrior(
            id="STREAK_3_UP_WEAKEN",
            name="3+ day up streak weakening",
            category=PriorCategory.STREAK,
            tier=EvidenceTier.RESEARCH,
            condition="SPY up 3+ consecutive days",
            outcome="Continuation probability decreases (weak mean reversion)",
            probability=0.52,
            sample_size=5000,
            time_period="Schaeffer's Research multi-decade",
            source="Schaeffer's Research",
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="PREV_DAY_HIGH_BROKEN",
            name="Previous day high broken = green close",
            category=PriorCategory.PREVIOUS_DAY,
            tier=EvidenceTier.EXTERNAL,
            condition="Previous day's high broken intraday",
            outcome="Day closes green 67-81%",
            probability=0.74,
            sample_size=500,
            time_period="Edgeful 6 months (YM)",
            source="Edgeful blog previous-days-range",
            notes="Figures vary across Edgeful posts. Verify via API.",
        ),
        BayesianPrior(
            id="ASIA_RANGE_BREAK_REVERT",
            name="Asia session range break + reversion",
            category=PriorCategory.PREVIOUS_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="Asia session (overnight) range broken during RTH",
            outcome="Break probability 93-95%, reversion rate 96.8%",
            probability=0.95,
            sample_size=3000,
            time_period="12-year TradingStats study",
            source="TradingStats.net Asia range cascade",
            notes="NQ/ES/YM/RTY all show similar rates",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_calendar_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="CAL_TURN_OF_MONTH",
            name="Turn-of-month effect (ALL excess returns)",
            category=PriorCategory.SEASONALITY,
            tier=EvidenceTier.RESEARCH,
            condition="Last trading day through first 3 trading days of month",
            outcome="ALL excess S&P 500 returns occur in this 4-day window",
            probability=0.62,
            sample_size=80 * 12,
            time_period="1926-2005, peer-reviewed, 34 countries",
            source="Xu & McConnell academic paper (Quantpedia)",
            knowable_before_open=True,
            notes="Peer-reviewed. Confirmed in 34 countries. Strongest calendar effect.",
        ),
        BayesianPrior(
            id="CAL_PRE_HOLIDAY",
            name="Pre-holiday positive drift",
            category=PriorCategory.SEASONALITY,
            tier=EvidenceTier.RESEARCH,
            condition="Trading day before Thanksgiving/July 4th/Christmas",
            outcome="Returns slightly above average",
            probability=0.58,
            sample_size=1500,
            time_period="1950-2024 (CXO Advisory)",
            source="CXO Advisory + Quantified Strategies",
            knowable_before_open=True,
            notes="Effect appears to be FADING in post-2000 data",
        ),
        BayesianPrior(
            id="CAL_INTRADAY_MOMENTUM",
            name="First-half-hour predicts last-half-hour",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="First half-hour return positive (SPY)",
            outcome="Last half-hour return positively correlated",
            probability=0.56,
            sample_size=5000,
            time_period="1993-2013 (Gao et al. academic paper)",
            source="Gao et al. peer-reviewed paper",
            notes="Effect STRONGER on volatile, high-volume, macro-event days",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_volatility_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="VIX_HALT_ABOVE_40",
            name="VIX > 40 = HALT all trading",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.LOCKED,
            condition="VIX > 40",
            outcome="HALT trading entirely (system invariant)",
            probability=0.0,
            sample_size=0,
            time_period="System invariant",
            source="State Registry VIX_THRESHOLDS (LOCKED)",
            verified_internally=True,
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="VIX_SIZE_HALVE_25",
            name="VIX > 25 = halve position size",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.LOCKED,
            condition="VIX > 25",
            outcome="SIZE_HALVE: reduce position to 50%",
            probability=0.0,
            sample_size=0,
            time_period="System invariant",
            source="State Registry VIX_THRESHOLDS (LOCKED)",
            verified_internally=True,
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="VIX_HIGH_FORWARD_POSITIVE",
            name="High VIX = positive forward returns",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.RESEARCH,
            condition="VIX elevated (absolute IV high)",
            outcome="Forward SPY returns positive (Spearman rho +0.088, p=0.002)",
            probability=0.56,
            sample_size=2000,
            time_period="iVolatility multi-year",
            source="iVolatility study",
            input_type=InputType.SPECTRUM,
            knowable_before_open=True,
        ),
        BayesianPrior(
            id="VIX_LOW_CALL_RETURNS",
            name="VIX < 14 = lower option returns",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.RESEARCH,
            condition="VIX < 14 (cheap vol)",
            outcome="30-day ATM SPY call returns avg ~24%",
            probability=0.55,
            sample_size=1000,
            time_period="Schaeffer's Research",
            source="Schaeffer's Research VIX study",
            tickers=["SPY"],
            knowable_before_open=True,
            notes="30-day model, not 0DTE. Use as context.",
        ),
        BayesianPrior(
            id="VIX_HIGH_CALL_RETURNS",
            name="VIX > 25 = higher option returns",
            category=PriorCategory.VOLATILITY,
            tier=EvidenceTier.RESEARCH,
            condition="VIX > 25",
            outcome="30-day ATM SPY call returns avg ~44%",
            probability=0.62,
            sample_size=1000,
            time_period="Schaeffer's Research",
            source="Schaeffer's Research VIX study",
            tickers=["SPY"],
            knowable_before_open=True,
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_microstructure_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="MICRO_SPREAD_STALL",
            name="Spread collapse micro-stall (compression)",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.LOCKED,
            condition="Spread collapses to 0-1.1c for >= 2.0s",
            outcome="Compression-before-expansion signal",
            probability=0.65,
            sample_size=2000,
            time_period="State Registry microstructure score budget",
            source="State Registry (LOCKED)",
            verified_internally=True,
        ),
        BayesianPrior(
            id="MICRO_QUOTE_LEAN_EXIT",
            name="Bid/ask size lean drop = exit",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.LOCKED,
            condition="Bid/ask size lean drops 0.40 below pre-entry norm",
            outcome="Exit signal (+$20,014 attributed value)",
            probability=0.70,
            sample_size=500,
            time_period="Live validated",
            source="State Registry micro quote lean exit (LOCKED)",
            verified_internally=True,
        ),
        BayesianPrior(
            id="MICRO_VEL_120S_PREDICTOR",
            name="2-min velocity strongest P&L predictor",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.LOCKED,
            condition="vel_120s (2-minute velocity post-entry) measured",
            outcome="Strongest P&L predictor in entire State Registry",
            probability=0.68,
            sample_size=1000,
            time_period="State Registry Section 14",
            source="State Registry (LOCKED)",
            verified_internally=True,
            notes="Use for real-time exit/hold decisions",
        ),
        BayesianPrior(
            id="MICRO_TICK_RULE_ERROR",
            name="Tick-rule CVD 169% magnitude error",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.LOCKED,
            condition="CVD computed via tick-rule on OPRA",
            outcome="94.5% directionally correct BUT 169% magnitude error",
            probability=0.945,
            sample_size=5000,
            time_period="State Registry signal trust hierarchy",
            source="State Registry (LOCKED)",
            verified_internally=True,
            notes="Direction OK, magnitude wrong. Tier 3 LOW trust.",
        ),
        BayesianPrior(
            id="MICRO_SEPARABILITY",
            name="96% of losers indistinguishable at entry",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.LOCKED,
            condition="At entry moment",
            outcome="96% of losing trades statistically identical to winners",
            probability=0.96,
            sample_size=8296,
            time_period="Live fleet 8,296 round-trips",
            source="State Registry SEPARABILITY_FINDING (LOCKED)",
            verified_internally=True,
            notes="Entry is NOT where the edge lives. POST-ENTRY PATH is everything.",
        ),
        BayesianPrior(
            id="MICRO_10MIN_CONTINUATION",
            name="Large open move 10min continuation",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.RESEARCH,
            condition="Large price change at futures open",
            outcome="10 minutes of continuation, then significant reversals",
            probability=0.60,
            sample_size=3750,
            time_period="1987-2002 (academic paper, ScienceDirect)",
            source="Academic paper (ScienceDirect)",
            notes="OLD data (pre-2002). Verify on modern data.",
        ),
        BayesianPrior(
            id="MICRO_0DTE_GAMMA_SUPPRESS",
            name="0DTE aggregate gamma suppresses vol",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.RESEARCH,
            condition="High aggregate 0DTE gamma",
            outcome="Inversely correlated with intraday realized vol",
            probability=0.58,
            sample_size=2000,
            time_period="CBOE research",
            source="CBOE exchange-level data",
            notes="Dealer hedging acts as volatility dampener",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_flow_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="FLOW_PC_RATIO_REVERSAL",
            name="P/C ratio spike + reversal = buy signal",
            category=PriorCategory.FLOW,
            tier=EvidenceTier.RESEARCH,
            condition="Put/call ratio spikes to extreme then reverses (SPY > 200 DMA)",
            outcome="2-week SPY WR ~83%, 3-month ~80%",
            probability=0.83,
            sample_size=50,
            time_period="SentimenTrader",
            source="SentimenTrader",
            notes="Conditional on SPY > 200 DMA. Recent underperformance noted.",
        ),
        BayesianPrior(
            id="FLOW_AD_NEW_HIGH",
            name="NYSE A/D new high = low crash risk",
            category=PriorCategory.FLOW,
            tier=EvidenceTier.RESEARCH,
            condition="NYSE A/D line makes new high",
            outcome="10%+ decline probability drops to 4.6%",
            probability=0.954,
            sample_size=100,
            time_period="Since 1928 (SentimenTrader)",
            source="SentimenTrader",
            notes="Macro-level regime indicator. Very long sample but rare events.",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_cross_asset_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="CROSS_NQ_LEADS_QQQ",
            name="NQ futures leads QQQ",
            category=PriorCategory.FUTURES_LEAD,
            tier=EvidenceTier.RESEARCH,
            condition="NQ/MNQ moves",
            outcome="QQQ follows with small lag (R2 = 0.19%)",
            probability=0.52,
            sample_size=1000,
            time_period="Jiang SSRN paper",
            source="Jiang (SSRN) 1-minute study",
            notes="R2 only 0.19%. NOT SHOWN TO SURVIVE EXECUTION COSTS.",
        ),
        BayesianPrior(
            id="CROSS_BTC_QQQ_CORR",
            name="BTC-QQQ 90-day correlation ~0.55",
            category=PriorCategory.CROSS_ASSET,
            tier=EvidenceTier.EXTERNAL,
            condition="BTC 90-day rolling correlation with QQQ",
            outcome="Correlation ~0.55, beta ~2.5x (2024-2026)",
            probability=0.55,
            sample_size=500,
            time_period="2024-2026",
            source="ConvexTrade + TrendInvestorPro",
            notes="UNSTABLE over time. Use as context only.",
        ),
        BayesianPrior(
            id="CROSS_KALSHI_CALIBRATED",
            name="Kalshi prediction markets well-calibrated",
            category=PriorCategory.PREDICTION_MARKET,
            tier=EvidenceTier.RESEARCH,
            condition="Kalshi prediction market price for macro event",
            outcome="Approximately matches realized probability",
            probability=0.60,
            sample_size=2240000,
            time_period="2.24M resolved markets (Kalshi + Fed paper)",
            source="Federal Reserve paper + Kalshi self-study",
            notes="Best for elections/econ indicators. Weaker for novelty.",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_pod_a7_priors(registry: PriorRegistry) -> int:
    """Seed priors from the 13 regime-locked POD_A7 strategies (Google Drive)."""
    strategies = [
        ("S01", "S1_COILED_TO_LAMINAR", "ADAPTIVE_FLOW", 544, 1.28, 1.12, 52.8, 2.44),
        ("S02", "S3_QUIET_ABSORPTION", "CALL", 648, 1.01, 0.63, 47.2, -1.59),
        ("S03", "S1_COILED_TO_LAMINAR", "PUT", 460, 1.18, 0.97, 53.3, 1.15),
        ("S04", "S3_QUIET_ABSORPTION", "ADAPTIVE_FLOW", 514, 1.16, 1.10, 51.6, 1.71),
        ("S05", "S1_COILED_TO_LAMINAR", "CALL", 608, 1.07, 1.50, 53.3, 2.83),
        ("S06", "S3_QUIET_ABSORPTION", "ADAPTIVE_FLOW", 520, 1.30, 1.18, 52.7, 2.54),
        ("S07", "S1_COILED_TO_LAMINAR", "PUT", 444, 1.10, 0.93, 51.8, 0.59),
        ("S08", "S3_QUIET_ABSORPTION", "ADAPTIVE_FLOW", 534, 1.24, 1.07, 52.4, 2.18),
        ("S09", "S1_COILED_TO_LAMINAR", "CALL", 631, 1.00, 1.53, 52.9, 2.47),
        ("S10", "S3_QUIET_ABSORPTION", "ADAPTIVE_FLOW", 509, 1.15, 1.02, 51.7, 1.18),
        ("S11", "S1_COILED_TO_LAMINAR", "PUT", 467, 1.07, 0.95, 52.7, 0.63),
        ("S12", "S3_QUIET_ABSORPTION", "ADAPTIVE_FLOW", 524, 1.24, 1.08, 52.1, 1.94),
        ("S13", "S1_COILED_TO_LAMINAR", "ADAPTIVE_FLOW", 512, 1.23, 1.13, 51.6, 1.99),
    ]
    count = 0
    for sid, regime, direction, n, pf_is, pf_oos, wr, placebo_z in strategies:
        pid = f"POD_A7_{sid}"
        registry.register(BayesianPrior(
            id=pid,
            name=f"POD_A7 {sid} {regime[:10]}.. {direction}",
            category=PriorCategory.REGIME,
            tier=EvidenceTier.PROVISIONAL,
            condition=f"Regime={regime} | Window=MORNING_0935_1129 | Mode={direction}",
            outcome=f"PF_IS={pf_is}, PF_OOS={pf_oos}, WR={wr}%",
            probability=wr / 100.0,
            sample_size=n,
            time_period="ISRP v11.08 (2026-11-08)",
            source="EXEC_POD_A7 from Google Drive (13 regime-locked strategies)",
            regime_locked=True,
            regime_conditions=f"{regime} | MORNING_0935_1129_ET_STRICT | Spread <= $0.01",
            verification_pf=pf_oos,
            verification_n=n,
            tickers=["QQQ", "SPY", "NVDA", "AAPL", "MSFT", "META", "TSLA", "AMZN", "GOOGL"],
            notes=f"Placebo z={placebo_z}. NONE passed ISRP. Entry-only module.",
        ))
        count += 1
    return count


def seed_edgeful_report_priors(registry: PriorRegistry) -> int:
    """Seed placeholder priors for each Edgeful report category to wire in."""
    reports = [
        ("EDGE_GAP_FILL", "Gap fill base rate", PriorCategory.GAP,
         "Edgeful gap-fill-standard report", 0.65, "gap-fill-standard"),
        ("EDGE_GAP_BY_SIZE", "Gap fill by size bucket", PriorCategory.GAP,
         "Edgeful gap-fill-by-size report", 0.60, "gap-fill-by-size"),
        ("EDGE_GAP_BY_WEEKDAY", "Gap fill by day of week", PriorCategory.GAP,
         "Edgeful gap-fill-by-weekday report", 0.62, "gap-fill-by-weekday"),
        ("EDGE_ORB_5", "5-min ORB status", PriorCategory.ORB,
         "Edgeful orb-standard report (5-min)", 0.54, "orb-standard"),
        ("EDGE_ORB_15", "15-min ORB status", PriorCategory.ORB,
         "Edgeful orb-standard report (15-min)", 0.55, "orb-standard"),
        ("EDGE_IB_60", "60-min IB status", PriorCategory.INITIAL_BALANCE,
         "Edgeful initial-balance-standard", 0.68, "initial-balance-standard"),
        ("EDGE_ADR_USED", "ADR % consumed", PriorCategory.VOLATILITY,
         "Edgeful adr-standard report", 0.50, "adr-standard"),
        ("EDGE_ADR_WEEKDAY", "ADR by weekday", PriorCategory.VOLATILITY,
         "Edgeful adr-by-weekday report", 0.52, "adr-by-weekday"),
        ("EDGE_ADR_STREAK", "ADR by streak count", PriorCategory.STREAK,
         "Edgeful adr-by-streak report", 0.55, "adr-by-streak"),
        ("EDGE_PREV_DAY_RANGE", "Previous day range broken", PriorCategory.PREVIOUS_DAY,
         "Edgeful previous-days-range-standard", 0.72, "previous-days-range-standard"),
        ("EDGE_FVG", "Fair Value Gap fill rate", PriorCategory.FRACTAL,
         "Edgeful fvg-standard report", 0.60, "fvg-standard"),
        ("EDGE_FIB_LEVELS", "Fibonacci level reaction", PriorCategory.FRACTAL,
         "Edgeful fib-levels-standard report", 0.55, "fib-levels-standard"),
        ("EDGE_ENGULFING", "Engulfing candle continuation", PriorCategory.CANDLE_PATTERN,
         "Edgeful engulfing-standard report", 0.55, "engulfing-standard"),
        ("EDGE_CPI_REACTION", "CPI day reaction profile", PriorCategory.EVENT_DAY,
         "Edgeful cpi-reaction report", 0.65, "cpi-reaction"),
        ("EDGE_FOMC_REACTION", "FOMC day reaction profile", PriorCategory.EVENT_DAY,
         "Edgeful fomc-reaction report", 0.65, "fomc-reaction"),
        ("EDGE_STREAK", "Consecutive day streak", PriorCategory.STREAK,
         "Edgeful streak-standard report", 0.57, "streak-standard"),
        ("EDGE_SESSION_HIGH", "Session high time distribution", PriorCategory.TIME_OF_DAY,
         "Edgeful session-high-standard", 0.50, "session-high-standard"),
        ("EDGE_SESSION_LOW", "Session low time distribution", PriorCategory.TIME_OF_DAY,
         "Edgeful session-low-standard", 0.50, "session-low-standard"),
        ("EDGE_GAP_FILL_TIME", "Time to gap fill", PriorCategory.GAP,
         "Edgeful gap-fill-time report", 0.50, "gap-fill-time"),
        ("EDGE_ADR_EXTENSION", "ADR extension behavior", PriorCategory.VOLATILITY,
         "Edgeful adr-extension report", 0.45, "adr-extension"),
    ]
    count = 0
    for pid, name, cat, source, prob, slug in reports:
        registry.register(BayesianPrior(
            id=pid,
            name=name,
            category=cat,
            tier=EvidenceTier.EXTERNAL,
            condition=f"Edgeful {slug} condition met",
            outcome=f"Edgeful base rate: p={prob}",
            probability=prob,
            sample_size=0,
            time_period="Edgeful API (to be pulled live)",
            source=source,
            notes=f"API slug: {slug}. Probabilities are PLACEHOLDER until live pull.",
        ))
        count += 1
    return count


def seed_proprietary_priors(registry: PriorRegistry) -> int:
    """Seed priors from proprietary discoveries and live forensics."""
    priors = [
        BayesianPrior(
            id="PROP_CONVICTION_GRID_PUTS",
            name="Conviction grid puts PF ~11",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Full conviction grid aligned (puts)",
            outcome="PF ~11 over 140+ trades",
            probability=0.89,
            sample_size=140,
            time_period="Owner live conviction grid",
            source="Owner manual trading forensics",
            notes="~88-89% WR. 400 data points, each ~2000 lines of code.",
        ),
        BayesianPrior(
            id="PROP_CONVICTION_GRID_CALLS",
            name="Conviction grid calls PF ~5-6",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Full conviction grid aligned (calls)",
            outcome="PF ~5-6 over 140+ trades",
            probability=0.85,
            sample_size=140,
            time_period="Owner live conviction grid",
            source="Owner manual trading forensics",
        ),
        BayesianPrior(
            id="PROP_LIVE_FLEET_BENCHMARK",
            name="Live fleet benchmark PF 1.28",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.LOCKED,
            condition="Full automated fleet running",
            outcome="PF 1.28, 49.8% WR, $1,023,240 (8,296 round-trips)",
            probability=0.498,
            sample_size=8296,
            time_period="Live Alpaca fleet",
            source="State Registry Benchmarks (LOCKED)",
            verified_internally=True,
            verification_pf=1.28,
            verification_n=8296,
        ),
        BayesianPrior(
            id="PROP_V6_HONEST",
            name="V6 HONEST benchmark PF 1.13",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.LOCKED,
            condition="V6 engine on real ThetaData NBBO",
            outcome="PF 1.13, 37.0% WR (1,010 trades)",
            probability=0.37,
            sample_size=1010,
            time_period="V6 HONEST benchmark",
            source="State Registry V6_HONEST (LOCKED)",
            verified_internally=True,
            verification_pf=1.13,
            verification_n=1010,
            notes="37% WR with convex payoff = profitable. The honest number.",
        ),
        BayesianPrior(
            id="PROP_PCE_DAY_LOSS",
            name="PCE day live PF 0.15",
            category=PriorCategory.EVENT_DAY,
            tier=EvidenceTier.LOCKED,
            condition="PCE release day",
            outcome="Live Tradier PF 0.15 (n=7) — LOSES MONEY",
            probability=0.30,
            sample_size=7,
            time_period="Live Alpaca forensics",
            source="State Registry F-0232",
            verified_internally=True,
            verification_pf=0.15,
            knowable_before_open=True,
            notes="PCE is the ONE event that LOSES. Consider veto or size cut.",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_all(registry: PriorRegistry) -> dict:
    """Seed ALL priors from every source. Returns counts by source."""
    counts = {}
    counts["seasonality"] = seed_seasonality_priors(registry)
    counts["time_of_day"] = seed_time_of_day_priors(registry)
    counts["regime"] = seed_regime_priors(registry)
    counts["gap_fill"] = seed_gap_fill_priors(registry)
    counts["orb_ib"] = seed_orb_ib_priors(registry)
    counts["event_day"] = seed_event_day_priors(registry)
    counts["streaks"] = seed_streak_priors(registry)
    counts["calendar"] = seed_calendar_priors(registry)
    counts["volatility"] = seed_volatility_priors(registry)
    counts["microstructure"] = seed_microstructure_priors(registry)
    counts["flow"] = seed_flow_priors(registry)
    counts["cross_asset"] = seed_cross_asset_priors(registry)
    counts["pod_a7"] = seed_pod_a7_priors(registry)
    counts["edgeful"] = seed_edgeful_report_priors(registry)
    counts["proprietary"] = seed_proprietary_priors(registry)

    # F01 Morning Sniper priors (from Drive: IS PF 4.77 / OOS PF 3.61)
    from seed_f01_sniper_priors import seed_f01_sniper_priors
    counts["f01_sniper"] = seed_f01_sniper_priors(registry)

    # V19 Conservative 0DTE strategy priors (from Drive backtest doc)
    from seed_v19_priors import seed_v19_strategy_priors
    counts["v19_strategy"] = seed_v19_strategy_priors(registry)

    # Expansion priors (research, hypotheses, structural)
    try:
        from seed_expansion_priors import seed_expansion_all
        expansion_counts = seed_expansion_all(registry)
        for k, v in expansion_counts.items():
            if k != "TOTAL":
                counts[f"exp_{k}"] = v
    except ImportError:
        pass

    # MADX STATE-3 extracted priors (from persistent brain doc)
    try:
        from extracted_madx_priors import MADX_EXTRACTED_PRIORS
        from bayesian_prior_factory import BayesianPrior, PriorCategory, EvidenceTier
        madx_count = 0
        cat_map = {v.value: v for v in PriorCategory}
        cat_map.update({v.name: v for v in PriorCategory})
        tier_map = {v.value: v for v in EvidenceTier}
        tier_map.update({v.name: v for v in EvidenceTier})
        for item in MADX_EXTRACTED_PRIORS:
            cat = cat_map.get(item.get("category", ""), PriorCategory.PROPRIETARY)
            tier = tier_map.get(item.get("tier", ""), EvidenceTier.RESEARCH)
            prior = BayesianPrior(
                id=f"MADX_{item['name'].upper()[:60]}",
                name=item["name"],
                category=cat,
                tier=tier,
                condition=item.get("rule", ""),
                outcome=item.get("rule", ""),
                probability=item.get("probability", 0.50) or 0.50,
                sample_size=item.get("sample_size", 0) or 0,
                time_period=item.get("source", "MADX_STATE-3"),
                source=item.get("source", "MADX_STATE-3"),
                notes=item.get("notes", ""),
            )
            if prior.probability and 0 < prior.probability < 1:
                registry.register(prior)
                madx_count += 1
        counts["madx_state3"] = madx_count
    except (ImportError, Exception):
        pass

    counts["TOTAL"] = sum(v for k, v in counts.items() if k != "TOTAL")
    return counts


if __name__ == "__main__":
    import json
    import logging

    logging.basicConfig(level=logging.WARNING)
    registry = PriorRegistry()
    counts = seed_all(registry)

    print("=== BAYESIAN PRIOR FACTORY — FULL SEED REPORT ===\n")
    print(f"Total priors registered: {counts['TOTAL']}")
    print(f"Active (non-refuted):    {registry.get_active_count()}\n")

    print("By source:")
    for source, n in counts.items():
        if source != "TOTAL":
            print(f"  {source:20s}: {n}")

    summary = registry.summary()
    print(f"\nBy tier:")
    for tier, n in sorted(summary["by_tier"].items()):
        print(f"  {tier:15s}: {n}")

    print(f"\nBy category:")
    for cat, n in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
        print(f"  {cat:25s}: {n}")
