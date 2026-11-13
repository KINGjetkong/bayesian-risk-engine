"""
Bayesian Prior Factory — probability matrix for 0DTE options
Harvests, verifies, and weights statistical "if-then" rules from:
  - Published research (external)
  - Edgeful API (session statistics)
  - Databento (CME futures microstructure)
  - FlashAlpha (Greeks, GEX, flow)
  - Unusual Whales (dark pool, flow, seasonality)
  - Proprietary discoveries (manual trading forensics)
  - Google Sheets integration (live tracking)

Every evaluation is logged with millisecond timestamps.
State-outcome relationships accumulate for ML refinement.
"""
import json
import time
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("prior_factory")


class EvidenceTier(Enum):
    LOCKED = "LOCKED"
    PROVISIONAL = "PROVISIONAL"
    RESEARCH = "RESEARCH"
    EXTERNAL = "EXTERNAL"
    REFUTED = "REFUTED"


class PriorCategory(Enum):
    SEASONALITY = "seasonality"
    TIME_OF_DAY = "time_of_day"
    GAP = "gap"
    ORB = "opening_range_breakout"
    INITIAL_BALANCE = "initial_balance"
    REGIME = "regime"
    MICROSTRUCTURE = "microstructure"
    FLOW = "flow"
    GREEKS = "greeks"
    CROSS_ASSET = "cross_asset"
    VOLATILITY = "volatility"
    EVENT_DAY = "event_day"
    STREAK = "streak"
    PREVIOUS_DAY = "previous_day"
    PROPRIETARY = "proprietary"
    FRACTAL = "fractal"
    CANDLE_PATTERN = "candle_pattern"
    FUTURES_LEAD = "futures_lead"
    PREDICTION_MARKET = "prediction_market"


class InputType(Enum):
    BINARY = "binary"
    SPECTRUM = "spectrum"
    FLUID = "fluid"


@dataclass
class BayesianPrior:
    """A single 'if-then' probability rule."""
    id: str
    name: str
    category: PriorCategory
    tier: EvidenceTier

    condition: str
    outcome: str
    probability: float
    sample_size: int
    time_period: str

    source: str
    source_url: Optional[str] = None
    verified_internally: bool = False
    verification_pf: Optional[float] = None
    verification_n: Optional[int] = None

    input_type: InputType = InputType.BINARY
    weight: float = 1.0
    regime_locked: bool = False
    regime_conditions: Optional[str] = None

    tickers: list = field(default_factory=lambda: ["QQQ", "SPY"])
    timeframe: Optional[str] = None
    knowable_before_open: bool = False

    notes: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_logit_effect(self) -> float:
        """Convert probability to logit-space effect for Bayesian composition."""
        import math
        p = max(0.001, min(0.999, self.probability))
        return math.log(p / (1 - p))

    def weighted_logit(self) -> float:
        """Logit effect scaled by evidence weight."""
        tier_multipliers = {
            EvidenceTier.LOCKED: 1.0,
            EvidenceTier.PROVISIONAL: 0.7,
            EvidenceTier.RESEARCH: 0.4,
            EvidenceTier.EXTERNAL: 0.3,
            EvidenceTier.REFUTED: 0.0,
        }
        return self.to_logit_effect() * self.weight * tier_multipliers[self.tier]


@dataclass
class StateSnapshot:
    """Millisecond-resolution state capture for logging."""
    timestamp_ms: int
    prior_evaluations: dict
    composite_score: float
    posterior_probability: float
    route: str
    regime_state: dict
    active_priors: list
    null_priors: list

    def to_sheets_row(self) -> list:
        """Format for Google Sheets append."""
        ts = datetime.fromtimestamp(
            self.timestamp_ms / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return [
            ts,
            self.composite_score,
            self.posterior_probability,
            self.route,
            json.dumps(self.regime_state),
            len(self.active_priors),
            len(self.null_priors),
            json.dumps(self.prior_evaluations),
        ]


class PriorRegistry:
    """Central registry of all Bayesian priors."""

    def __init__(self):
        self.priors: dict[str, BayesianPrior] = {}
        self._evaluation_log: list[StateSnapshot] = []
        self._log_path = Path("RUNS/PRIOR_EVALUATIONS.jsonl")

    def register(self, prior: BayesianPrior) -> None:
        if prior.id in self.priors:
            logger.warning("Prior %s already registered, updating", prior.id)
        self.priors[prior.id] = prior
        logger.info(
            "Registered prior: %s [%s] p=%.3f n=%d",
            prior.name, prior.tier.value, prior.probability, prior.sample_size,
        )

    def evaluate_all(self, market_state: dict) -> StateSnapshot:
        """Evaluate every prior against current market state.

        Returns a StateSnapshot with millisecond timestamp for logging.
        Each prior is evaluated as active (condition met), null (not met),
        or N/A (data unavailable). Null results are datapoints too.
        """
        import math

        ts_ms = int(time.time() * 1000)
        evaluations = {}
        active = []
        null_priors = []
        logit_sum = 0.0

        for pid, prior in self.priors.items():
            if prior.tier == EvidenceTier.REFUTED:
                continue

            result = self._evaluate_prior(prior, market_state)
            evaluations[pid] = result

            if result["status"] == "active":
                active.append(pid)
                logit_sum += prior.weighted_logit()
            elif result["status"] == "null":
                null_priors.append(pid)

        posterior = 1.0 / (1.0 + math.exp(-2.2 * logit_sum))
        if posterior >= 0.75:
            route = "RUNNER"
        elif posterior >= 0.45:
            route = "HYBRID"
        else:
            route = "SWEEP"

        snapshot = StateSnapshot(
            timestamp_ms=ts_ms,
            prior_evaluations=evaluations,
            composite_score=logit_sum,
            posterior_probability=posterior,
            route=route,
            regime_state=self._extract_regime(market_state),
            active_priors=active,
            null_priors=null_priors,
        )

        self._evaluation_log.append(snapshot)
        self._write_log(snapshot)
        return snapshot

    def _evaluate_prior(
        self, prior: BayesianPrior, state: dict
    ) -> dict:
        """Evaluate a single prior against market state.

        Returns {"status": "active"|"null"|"unavailable", "value": ...}
        """
        evaluator = PRIOR_EVALUATORS.get(prior.category)
        if evaluator is None:
            return {"status": "unavailable", "value": None}
        try:
            return evaluator(prior, state)
        except (KeyError, TypeError, ValueError):
            return {"status": "unavailable", "value": None}

    def _extract_regime(self, state: dict) -> dict:
        return {
            "macro_bias": state.get("macro_bias", "unknown"),
            "day_bias": state.get("day_bias", "unknown"),
            "vix": state.get("vix", 0),
            "adx_15m": state.get("adx_15m", 0),
            "gex_regime": state.get("gex_regime", "unknown"),
            "tod_bucket": state.get("tod_bucket", "unknown"),
        }

    def _write_log(self, snapshot: StateSnapshot) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(asdict(snapshot)) + "\n")

    def get_active_count(self) -> int:
        return sum(
            1 for p in self.priors.values()
            if p.tier != EvidenceTier.REFUTED
        )

    def summary(self) -> dict:
        by_tier = {}
        by_cat = {}
        for p in self.priors.values():
            by_tier[p.tier.value] = by_tier.get(p.tier.value, 0) + 1
            by_cat[p.category.value] = by_cat.get(p.category.value, 0) + 1
        return {
            "total": len(self.priors),
            "active": self.get_active_count(),
            "by_tier": by_tier,
            "by_category": by_cat,
        }


# ---------------------------------------------------------------------------
# Prior evaluators: one function per category
# ---------------------------------------------------------------------------
def _eval_seasonality(prior: BayesianPrior, state: dict) -> dict:
    month = state.get("month")
    if month is None:
        return {"status": "unavailable", "value": None}
    cond = prior.condition
    if f"month={month}" in cond or f"month {month}" in cond.lower():
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_time_of_day(prior: BayesianPrior, state: dict) -> dict:
    tod = state.get("time_et")
    if tod is None:
        return {"status": "unavailable", "value": None}
    cond = prior.condition.lower()
    if "before 11:20" in cond and tod < "11:20":
        return {"status": "active", "value": prior.probability}
    if "after 11:20" in cond and tod >= "11:20":
        return {"status": "active", "value": prior.probability}
    if "first hour" in cond and tod < "10:30":
        return {"status": "active", "value": prior.probability}
    if "lunch" in cond and "11:30" <= tod < "13:30":
        return {"status": "active", "value": prior.probability}
    if "power hour" in cond and tod >= "15:00":
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_gap(prior: BayesianPrior, state: dict) -> dict:
    gap_pct = state.get("gap_pct")
    if gap_pct is None:
        return {"status": "unavailable", "value": None}
    cond = prior.condition.lower()
    if "gap up" in cond and gap_pct > 0:
        return {"status": "active", "value": prior.probability}
    if "gap down" in cond and gap_pct < 0:
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_regime(prior: BayesianPrior, state: dict) -> dict:
    adx = state.get("adx_15m", 0)
    cond = prior.condition.lower()
    if "trending" in cond and adx > 25:
        return {"status": "active", "value": prior.probability}
    if "choppy" in cond and adx <= 25:
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_volatility(prior: BayesianPrior, state: dict) -> dict:
    vix = state.get("vix", 0)
    cond = prior.condition.lower()
    if "vix > 25" in cond and vix > 25:
        return {"status": "active", "value": prior.probability}
    if "vix < 15" in cond and vix < 15:
        return {"status": "active", "value": prior.probability}
    if "vix 15-25" in cond and 15 <= vix <= 25:
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_event_day(prior: BayesianPrior, state: dict) -> dict:
    event = state.get("event_type", "NORMAL")
    cond = prior.condition.upper()
    if event.upper() in cond:
        return {"status": "active", "value": prior.probability}
    return {"status": "null", "value": 0}


def _eval_generic(prior: BayesianPrior, state: dict) -> dict:
    return {"status": "null", "value": 0}


PRIOR_EVALUATORS = {
    PriorCategory.SEASONALITY: _eval_seasonality,
    PriorCategory.TIME_OF_DAY: _eval_time_of_day,
    PriorCategory.GAP: _eval_gap,
    PriorCategory.REGIME: _eval_regime,
    PriorCategory.VOLATILITY: _eval_volatility,
    PriorCategory.EVENT_DAY: _eval_event_day,
    PriorCategory.ORB: _eval_generic,
    PriorCategory.INITIAL_BALANCE: _eval_generic,
    PriorCategory.MICROSTRUCTURE: _eval_generic,
    PriorCategory.FLOW: _eval_generic,
    PriorCategory.GREEKS: _eval_generic,
    PriorCategory.CROSS_ASSET: _eval_generic,
    PriorCategory.STREAK: _eval_generic,
    PriorCategory.PREVIOUS_DAY: _eval_generic,
    PriorCategory.PROPRIETARY: _eval_generic,
    PriorCategory.FRACTAL: _eval_generic,
    PriorCategory.CANDLE_PATTERN: _eval_generic,
    PriorCategory.FUTURES_LEAD: _eval_generic,
    PriorCategory.PREDICTION_MARKET: _eval_generic,
}


# ---------------------------------------------------------------------------
# Google Sheets integration for live tracking
# ---------------------------------------------------------------------------
class SheetsLogger:
    """Push state snapshots to Google Sheets for live tracking.

    Requires gspread + service account credentials.
    Columns: timestamp_ms | composite_score | posterior | route |
             regime_state | active_count | null_count | evaluations
    """

    def __init__(self, spreadsheet_id: str, worksheet_name: str = "PriorLog"):
        self.spreadsheet_id = spreadsheet_id
        self.worksheet_name = worksheet_name
        self._sheet = None

    def connect(self):
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            creds = Credentials.from_service_account_file(
                "credentials.json",
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            gc = gspread.authorize(creds)
            self._sheet = gc.open_by_key(self.spreadsheet_id).worksheet(
                self.worksheet_name
            )
            logger.info("Connected to Google Sheet: %s", self.spreadsheet_id)
        except Exception as e:
            logger.warning("Sheets connection failed: %s", e)

    def log_snapshot(self, snapshot: StateSnapshot) -> None:
        if self._sheet is None:
            return
        try:
            self._sheet.append_row(
                snapshot.to_sheets_row(),
                value_input_option="RAW",
            )
        except Exception as e:
            logger.warning("Sheets append failed: %s", e)

    def log_outcome(
        self,
        snapshot_ts_ms: int,
        pnl: float,
        hold_seconds: float,
        exit_reason: str,
    ) -> None:
        """Log the outcome of a trade for state-outcome correlation."""
        if self._sheet is None:
            return
        try:
            ts = datetime.fromtimestamp(
                snapshot_ts_ms / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self._sheet.append_row(
                [ts, "OUTCOME", pnl, hold_seconds, exit_reason],
                value_input_option="RAW",
            )
        except Exception as e:
            logger.warning("Sheets outcome log failed: %s", e)


# ---------------------------------------------------------------------------
# ML refinement: accumulate state-outcome pairs, retrain weights
# ---------------------------------------------------------------------------
class WeightRefiner:
    """Accumulate (state, outcome) pairs and periodically retrain prior weights.

    Uses gradient-boosted trees (LightGBM) to learn which priors predict
    profitable outcomes under which regime states.
    """

    def __init__(self, min_samples: int = 200):
        self.min_samples = min_samples
        self._pairs: list[dict] = []
        self._model = None
        self._data_path = Path("RUNS/STATE_OUTCOME_PAIRS.jsonl")

    def record_pair(
        self,
        snapshot: StateSnapshot,
        pnl: float,
        hold_seconds: float,
    ) -> None:
        pair = {
            "ts_ms": snapshot.timestamp_ms,
            "composite_score": snapshot.composite_score,
            "posterior": snapshot.posterior_probability,
            "route": snapshot.route,
            "active_count": len(snapshot.active_priors),
            "null_count": len(snapshot.null_priors),
            "regime": snapshot.regime_state,
            "pnl": pnl,
            "hold_seconds": hold_seconds,
            "profitable": pnl > 0,
        }
        for pid in snapshot.active_priors:
            pair[f"prior_{pid}"] = 1
        self._pairs.append(pair)
        self._data_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._data_path, "a") as f:
            f.write(json.dumps(pair) + "\n")

    def retrain(self, registry: PriorRegistry) -> dict:
        """Retrain prior weights from accumulated state-outcome data.

        Returns {"status": "retrained"|"insufficient_data", ...}
        """
        if len(self._pairs) < self.min_samples:
            return {
                "status": "insufficient_data",
                "current": len(self._pairs),
                "needed": self.min_samples,
            }

        try:
            import lightgbm as lgb
            import numpy as np

            feature_cols = [
                c for c in self._pairs[0].keys()
                if c.startswith("prior_") or c in (
                    "composite_score", "active_count", "null_count"
                )
            ]
            X = np.array([
                [p.get(c, 0) for c in feature_cols] for p in self._pairs
            ])
            y = np.array([p["profitable"] for p in self._pairs]).astype(int)

            dtrain = lgb.Dataset(X, label=y, feature_name=feature_cols)
            params = {
                "objective": "binary",
                "metric": "auc",
                "num_leaves": 31,
                "learning_rate": 0.05,
                "verbose": -1,
            }
            self._model = lgb.train(params, dtrain, num_boost_round=100)

            importances = dict(
                zip(feature_cols, self._model.feature_importance().tolist())
            )
            for pid, prior in registry.priors.items():
                key = f"prior_{pid}"
                if key in importances:
                    raw = importances[key]
                    prior.weight = max(0.1, min(3.0, raw / 50.0))

            return {
                "status": "retrained",
                "samples": len(self._pairs),
                "feature_importances": importances,
            }
        except ImportError:
            return {"status": "lightgbm_not_installed"}


# ---------------------------------------------------------------------------
# Seed priors: Unusual Whales seasonality (20yr verified)
# ---------------------------------------------------------------------------
def seed_seasonality_priors(registry: PriorRegistry) -> int:
    """Seed monthly seasonality priors from Unusual Whales 20-year data."""
    data = {
        "QQQ": {
            1: (0.65, 0.0089), 2: (0.45, 0.0042), 3: (0.65, 0.0129),
            4: (0.75, 0.0304), 5: (0.70, 0.0251), 6: (0.55, 0.0053),
            7: (0.85, 0.0340), 8: (0.65, 0.0102), 9: (0.50, -0.0049),
            10: (0.55, 0.0109), 11: (0.68, 0.0180), 12: (0.58, 0.0029),
        },
        "SPY": {
            1: (0.55, 0.0025), 2: (0.50, 0.0017), 3: (0.60, 0.0053),
            4: (0.80, 0.0245), 5: (0.80, 0.0118), 6: (0.50, -0.0022),
            7: (0.80, 0.0254), 8: (0.65, 0.0036), 9: (0.50, -0.0097),
            10: (0.55, 0.0092), 11: (0.79, 0.0236), 12: (0.63, 0.0017),
        },
    }
    count = 0
    month_names = [
        "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    for ticker, months in data.items():
        for month, (pct_positive, avg_return) in months.items():
            pid = f"SEASON_{ticker}_M{month:02d}"
            registry.register(BayesianPrior(
                id=pid,
                name=f"{ticker} {month_names[month]} seasonality",
                category=PriorCategory.SEASONALITY,
                tier=EvidenceTier.EXTERNAL,
                condition=f"month={month}",
                outcome=f"{ticker} monthly positive close",
                probability=pct_positive,
                sample_size=20,
                time_period="2006-2026 (20 years)",
                source="Unusual Whales market seasonality API",
                verified_internally=False,
                tickers=[ticker],
                knowable_before_open=True,
                notes=f"avg return {avg_return:+.2%}",
            ))
            count += 1
    return count


def seed_time_of_day_priors(registry: PriorRegistry) -> int:
    """Seed time-of-day priors from State Registry LOCKED forensics."""
    priors = [
        BayesianPrior(
            id="TOD_PRE1120_BULLISH",
            name="Pre-11:20 ET entry window",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.LOCKED,
            condition="before 11:20 ET",
            outcome="Profitable trade (WR 66.9%, PF 2.35)",
            probability=0.669,
            sample_size=183,
            time_period="Live Alpaca forensics, 30 days",
            source="State Registry Section 9, owner LIVE forensics",
            verified_internally=True,
            verification_pf=2.35,
            notes="+$48,490. 77% of $ from event days.",
        ),
        BayesianPrior(
            id="TOD_POST1120_BEARISH",
            name="Post-11:20 ET entry window",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.LOCKED,
            condition="after 11:20 ET",
            outcome="Unprofitable trade (WR 41%, PF 0.46)",
            probability=0.41,
            sample_size=183,
            time_period="Live Alpaca forensics, 30 days",
            source="State Registry Section 9, owner LIVE forensics",
            verified_internally=True,
            verification_pf=0.46,
            notes="-$99,425. This is the ONLY LOCKED TOD evidence.",
        ),
        BayesianPrior(
            id="TOD_RICHEST_MFE",
            name="09:41-09:55 ET richest MFE zone",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.PROVISIONAL,
            condition="first hour 09:41-09:55 ET",
            outcome="Median MFE $3.00 (richest zone)",
            probability=0.70,
            sample_size=100,
            time_period="Owner live MFE data",
            source="State Registry Section 9",
            notes="70% of 6%+ moves concentrated here",
        ),
        BayesianPrior(
            id="TOD_LUNCH_CHOP",
            name="11:30-13:30 Mid-Day Chop Trap",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.RESEARCH,
            condition="lunch 11:30-13:30 ET",
            outcome="-79% candle size, theta 2.3x",
            probability=0.35,
            sample_size=1260,
            time_period="Multiple engines",
            source="State Registry Section 9",
            notes="Largest observed phase bucket (1,260 of 2,802 obs)",
        ),
        BayesianPrior(
            id="TOD_STRONG_TAIL",
            name="Post-13:30 Strong All Day Tail",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.PROVISIONAL,
            condition="after 13:30 ET",
            outcome="QQQ PF 1.58, SPY PF 1.44, +55% median tail",
            probability=0.55,
            sample_size=500,
            time_period="Master Reconciliation Ledger",
            source="State Registry Section 9",
            notes="Second-best real PF in the whole ledger",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def seed_regime_priors(registry: PriorRegistry) -> int:
    """Seed regime-based priors from State Registry."""
    priors = [
        BayesianPrior(
            id="GEX_POS_BAD",
            name="Positive GEX + breakout = losses",
            category=PriorCategory.GREEKS,
            tier=EvidenceTier.PROVISIONAL,
            condition="positive GEX regime with breakout attempt",
            outcome="Win rate adjustment -56%",
            probability=0.30,
            sample_size=200,
            time_period="Bayesian cheat sheet + ALMOS + confluence",
            source="State Registry Section 8",
            notes="THREE independent sources agree. Gamma sessions = primary loss source.",
        ),
        BayesianPrior(
            id="GEX_NEG_GOOD",
            name="Negative GEX + momentum = wins",
            category=PriorCategory.GREEKS,
            tier=EvidenceTier.PROVISIONAL,
            condition="negative GEX regime with momentum",
            outcome="Win rate adjustment +23%",
            probability=0.65,
            sample_size=200,
            time_period="Bayesian cheat sheet",
            source="State Registry Section 8",
        ),
        BayesianPrior(
            id="FLOW_VETO",
            name="Flow veto (contra >= 2, confirm = 0)",
            category=PriorCategory.FLOW,
            tier=EvidenceTier.PROVISIONAL,
            condition="contra flow >= 2 AND confirm flow == 0",
            outcome="Veto trade. PF lifts from 2.05 to 3.06 when applied.",
            probability=0.15,
            sample_size=500,
            time_period="Video-analysis validated",
            source="State Registry Section 8, FLOW_VETO",
            notes="The ONLY empirically validated hard gate in the corpus.",
        ),
        BayesianPrior(
            id="HOLD_30_60S",
            name="30-60s hold time sweet spot",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.LOCKED,
            condition="hold time between 30 and 60 seconds",
            outcome="PF 2.415 (highest in corpus)",
            probability=0.58,
            sample_size=1000,
            time_period="State Registry HOLD_TIME_PF",
            source="State Registry Section 6",
            notes="<30s PF 0.240 (catastrophic). 1-3m PF 1.206 (decaying).",
        ),
    ]
    for p in priors:
        registry.register(p)
    return len(priors)


def create_factory() -> tuple[PriorRegistry, SheetsLogger, WeightRefiner]:
    """Create and seed a full prior factory."""
    registry = PriorRegistry()
    sheets = SheetsLogger(spreadsheet_id="")
    refiner = WeightRefiner(min_samples=200)

    n_season = seed_seasonality_priors(registry)
    n_tod = seed_time_of_day_priors(registry)
    n_regime = seed_regime_priors(registry)

    logger.info(
        "Prior factory initialized: %d seasonality, %d TOD, %d regime = %d total",
        n_season, n_tod, n_regime, registry.get_active_count(),
    )
    return registry, sheets, refiner


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    registry, sheets, refiner = create_factory()
    summary = registry.summary()
    print(json.dumps(summary, indent=2))
    print(f"\nTotal active priors: {summary['active']}")
    print(f"By tier: {summary['by_tier']}")
    print(f"By category: {summary['by_category']}")
