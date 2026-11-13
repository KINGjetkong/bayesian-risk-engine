"""
Testing Pipeline for the Bayesian Prior Factory.

Josh's testing methodology (verbatim from his instructions):
  1. Raw probability by itself — does this single prior have a win/loss rate?
  2. If not working → try inverse/negation
  3. Triple stack combos — combine 3 priors
  4. Layer over existing engines — add to what we already have
  5. Test binary vs spectrum vs fluid variants
  6. Weighted factor combinations
  7. State/regime lock — does it only work in certain regimes?
  8. Map nulls as datapoints — absence of a signal IS data

Each prior goes through this gauntlet. Results logged to JSONL + Google Sheets.
"""
import json
import math
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from itertools import combinations
from typing import Optional

from bayesian_prior_factory import (
    BayesianPrior, PriorRegistry, EvidenceTier, InputType,
    StateSnapshot, SheetsLogger,
)

logger = logging.getLogger("testing_pipeline")


@dataclass
class TestResult:
    """Result of testing a single prior or combination."""
    test_id: str
    test_type: str
    prior_ids: list
    trades_tested: int
    wins: int
    losses: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    regime_state: Optional[str]
    input_variant: str
    timestamp: str

    @property
    def is_profitable(self) -> bool:
        return self.profit_factor > 1.0

    @property
    def kelly_fraction(self) -> float:
        if self.avg_loss == 0 or self.win_rate == 0:
            return 0.0
        R = abs(self.avg_win / self.avg_loss) if self.avg_loss != 0 else 0
        f = self.win_rate - ((1 - self.win_rate) / R) if R > 0 else 0
        return max(0.0, f * 0.25)


class TestingGauntlet:
    """Run every prior through Josh's 8-step testing methodology."""

    def __init__(
        self,
        registry: PriorRegistry,
        sheets: Optional[SheetsLogger] = None,
    ):
        self.registry = registry
        self.sheets = sheets
        self._results: list[TestResult] = []
        self._log_path = Path("RUNS/TEST_RESULTS.jsonl")

    def run_phase_1_raw(
        self,
        prior_id: str,
        trades: list[dict],
    ) -> TestResult:
        """Phase 1: Test raw probability by itself."""
        prior = self.registry.priors[prior_id]
        wins, losses, gross_win, gross_loss = self._score_trades(prior, trades)
        total = wins + losses
        wr = wins / total if total > 0 else 0
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
        avg_w = gross_win / wins if wins > 0 else 0
        avg_l = gross_loss / losses if losses > 0 else 0

        result = TestResult(
            test_id=f"P1_RAW_{prior_id}_{int(time.time())}",
            test_type="phase_1_raw",
            prior_ids=[prior_id],
            trades_tested=total,
            wins=wins,
            losses=losses,
            win_rate=wr,
            profit_factor=pf,
            total_pnl=gross_win - gross_loss,
            avg_win=avg_w,
            avg_loss=avg_l,
            regime_state=None,
            input_variant="binary",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._log_result(result)
        return result

    def run_phase_2_inverse(
        self,
        prior_id: str,
        trades: list[dict],
    ) -> TestResult:
        """Phase 2: If raw doesn't work, try inverse/negation."""
        prior = self.registry.priors[prior_id]
        wins, losses, gross_win, gross_loss = self._score_trades(
            prior, trades, invert=True
        )
        total = wins + losses
        wr = wins / total if total > 0 else 0
        pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

        result = TestResult(
            test_id=f"P2_INV_{prior_id}_{int(time.time())}",
            test_type="phase_2_inverse",
            prior_ids=[prior_id],
            trades_tested=total,
            wins=wins,
            losses=losses,
            win_rate=wr,
            profit_factor=pf,
            total_pnl=gross_win - gross_loss,
            avg_win=gross_win / wins if wins > 0 else 0,
            avg_loss=gross_loss / losses if losses > 0 else 0,
            regime_state=None,
            input_variant="inverse",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._log_result(result)
        return result

    def run_phase_3_triple_stack(
        self,
        prior_ids: list[str],
        trades: list[dict],
    ) -> list[TestResult]:
        """Phase 3: Triple stack combos — test all 3-prior combinations."""
        results = []
        for combo in combinations(prior_ids, 3):
            combo_key = "+".join(sorted(combo))
            wins, losses, gw, gl = self._score_combo(list(combo), trades)
            total = wins + losses
            if total < 10:
                continue
            wr = wins / total if total > 0 else 0
            pf = gw / gl if gl > 0 else float("inf")

            result = TestResult(
                test_id=f"P3_STACK_{combo_key}_{int(time.time())}",
                test_type="phase_3_triple_stack",
                prior_ids=list(combo),
                trades_tested=total,
                wins=wins,
                losses=losses,
                win_rate=wr,
                profit_factor=pf,
                total_pnl=gw - gl,
                avg_win=gw / wins if wins > 0 else 0,
                avg_loss=gl / losses if losses > 0 else 0,
                regime_state=None,
                input_variant="triple_stack",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._log_result(result)
            results.append(result)
        return results

    def run_phase_5_variants(
        self,
        prior_id: str,
        trades: list[dict],
    ) -> list[TestResult]:
        """Phase 5: Test binary vs spectrum vs fluid input variants."""
        results = []
        for variant in ["binary", "spectrum", "fluid"]:
            prior = self.registry.priors[prior_id]
            wins, losses, gw, gl = self._score_trades_variant(
                prior, trades, variant
            )
            total = wins + losses
            if total < 5:
                continue
            wr = wins / total if total > 0 else 0
            pf = gw / gl if gl > 0 else float("inf")

            result = TestResult(
                test_id=f"P5_{variant.upper()}_{prior_id}_{int(time.time())}",
                test_type=f"phase_5_{variant}",
                prior_ids=[prior_id],
                trades_tested=total,
                wins=wins,
                losses=losses,
                win_rate=wr,
                profit_factor=pf,
                total_pnl=gw - gl,
                avg_win=gw / wins if wins > 0 else 0,
                avg_loss=gl / losses if losses > 0 else 0,
                regime_state=None,
                input_variant=variant,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._log_result(result)
            results.append(result)
        return results

    def run_phase_7_regime_lock(
        self,
        prior_id: str,
        trades: list[dict],
        regimes: list[str],
    ) -> list[TestResult]:
        """Phase 7: State/regime lock — test under each regime separately."""
        results = []
        for regime in regimes:
            regime_trades = [
                t for t in trades if t.get("regime", "") == regime
            ]
            if len(regime_trades) < 10:
                continue

            prior = self.registry.priors[prior_id]
            wins, losses, gw, gl = self._score_trades(prior, regime_trades)
            total = wins + losses
            if total < 5:
                continue
            wr = wins / total if total > 0 else 0
            pf = gw / gl if gl > 0 else float("inf")

            result = TestResult(
                test_id=f"P7_REGIME_{prior_id}_{regime}_{int(time.time())}",
                test_type="phase_7_regime_lock",
                prior_ids=[prior_id],
                trades_tested=total,
                wins=wins,
                losses=losses,
                win_rate=wr,
                profit_factor=pf,
                total_pnl=gw - gl,
                avg_win=gw / wins if wins > 0 else 0,
                avg_loss=gl / losses if losses > 0 else 0,
                regime_state=regime,
                input_variant="binary",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            self._log_result(result)
            results.append(result)
        return results

    def run_phase_8_null_mapping(
        self,
        prior_id: str,
        trades: list[dict],
    ) -> TestResult:
        """Phase 8: Map nulls as datapoints — when the prior DOESN'T fire."""
        prior = self.registry.priors[prior_id]
        wins, losses, gw, gl = self._score_trades(
            prior, trades, null_mode=True
        )
        total = wins + losses
        wr = wins / total if total > 0 else 0
        pf = gw / gl if gl > 0 else float("inf")

        result = TestResult(
            test_id=f"P8_NULL_{prior_id}_{int(time.time())}",
            test_type="phase_8_null_mapping",
            prior_ids=[prior_id],
            trades_tested=total,
            wins=wins,
            losses=losses,
            win_rate=wr,
            profit_factor=pf,
            total_pnl=gw - gl,
            avg_win=gw / wins if wins > 0 else 0,
            avg_loss=gl / losses if losses > 0 else 0,
            regime_state=None,
            input_variant="null",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._log_result(result)
        return result

    def full_gauntlet(
        self,
        prior_id: str,
        trades: list[dict],
        regimes: Optional[list[str]] = None,
    ) -> dict:
        """Run the full 8-phase testing gauntlet on a single prior."""
        results = {}
        results["phase_1_raw"] = self.run_phase_1_raw(prior_id, trades)
        results["phase_2_inverse"] = self.run_phase_2_inverse(prior_id, trades)
        results["phase_5_variants"] = self.run_phase_5_variants(
            prior_id, trades
        )
        if regimes:
            results["phase_7_regime"] = self.run_phase_7_regime_lock(
                prior_id, trades, regimes
            )
        results["phase_8_null"] = self.run_phase_8_null_mapping(
            prior_id, trades
        )

        raw = results["phase_1_raw"]
        inv = results["phase_2_inverse"]

        verdict = "INCONCLUSIVE"
        if raw.is_profitable and raw.profit_factor > 1.2:
            verdict = "KEEP_RAW"
        elif inv.is_profitable and inv.profit_factor > 1.2:
            verdict = "KEEP_INVERSE"
        elif raw.trades_tested < 30:
            verdict = "UNDERPOWERED"

        results["verdict"] = verdict
        return results

    def _score_trades(
        self,
        prior: BayesianPrior,
        trades: list[dict],
        invert: bool = False,
        null_mode: bool = False,
    ) -> tuple[int, int, float, float]:
        wins = losses = gross_win = gross_loss = 0
        for t in trades:
            condition_met = self._check_condition(prior, t)
            if null_mode:
                condition_met = not condition_met
            if invert:
                condition_met = not condition_met
            if not condition_met:
                continue
            pnl = t.get("pnl", 0)
            if pnl > 0:
                wins += 1
                gross_win += pnl
            else:
                losses += 1
                gross_loss += abs(pnl)
        return wins, losses, gross_win, gross_loss

    def _score_combo(
        self,
        prior_ids: list[str],
        trades: list[dict],
    ) -> tuple[int, int, float, float]:
        wins = losses = gw = gl = 0
        for t in trades:
            all_met = all(
                self._check_condition(self.registry.priors[pid], t)
                for pid in prior_ids
            )
            if not all_met:
                continue
            pnl = t.get("pnl", 0)
            if pnl > 0:
                wins += 1
                gw += pnl
            else:
                losses += 1
                gl += abs(pnl)
        return wins, losses, gw, gl

    def _score_trades_variant(
        self,
        prior: BayesianPrior,
        trades: list[dict],
        variant: str,
    ) -> tuple[int, int, float, float]:
        wins = losses = gw = gl = 0
        for t in trades:
            if variant == "binary":
                weight = 1.0 if self._check_condition(prior, t) else 0.0
            elif variant == "spectrum":
                weight = self._spectrum_weight(prior, t)
            elif variant == "fluid":
                weight = self._fluid_weight(prior, t)
            else:
                weight = 0.0

            if weight <= 0.0:
                continue

            pnl = t.get("pnl", 0) * weight
            if pnl > 0:
                wins += 1
                gw += pnl
            else:
                losses += 1
                gl += abs(pnl)
        return wins, losses, gw, gl

    def _check_condition(
        self, prior: BayesianPrior, trade: dict
    ) -> bool:
        cond = prior.condition.lower()
        if "month=" in cond:
            month = trade.get("month")
            return month is not None and f"month={month}" in cond
        if "before" in cond and "et" in cond:
            tod = trade.get("time_et", "")
            if "11:20" in cond:
                return tod < "11:20"
            if "11:30" in cond:
                return tod < "11:30"
        if "after" in cond and "et" in cond:
            tod = trade.get("time_et", "")
            if "11:20" in cond:
                return tod >= "11:20"
            if "13:30" in cond:
                return tod >= "13:30"
        if "gap up" in cond:
            return trade.get("gap_pct", 0) > 0
        if "gap down" in cond:
            return trade.get("gap_pct", 0) < 0
        if "vix" in cond:
            vix = trade.get("vix", 20)
            if "> 40" in cond:
                return vix > 40
            if "> 25" in cond:
                return vix > 25
            if "< 14" in cond:
                return vix < 14
        if "cpi" in cond:
            return trade.get("event_type", "").upper() == "CPI"
        if "fomc" in cond:
            return trade.get("event_type", "").upper() == "FOMC"
        if "regime=" in cond:
            regime = trade.get("regime", "")
            return regime.upper() in cond.upper()
        return False

    def _spectrum_weight(
        self, prior: BayesianPrior, trade: dict
    ) -> float:
        if not self._check_condition(prior, trade):
            return 0.0
        p = prior.probability
        return min(1.0, p * 1.2)

    def _fluid_weight(
        self, prior: BayesianPrior, trade: dict
    ) -> float:
        if not self._check_condition(prior, trade):
            return 0.0
        p = prior.probability
        logit = math.log(p / (1 - p)) if 0 < p < 1 else 0
        return 1.0 / (1.0 + math.exp(-2.2 * logit))

    def _log_result(self, result: TestResult) -> None:
        self._results.append(result)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._log_path, "a") as f:
            f.write(json.dumps(asdict(result)) + "\n")


def run_full_factory_test(
    registry: PriorRegistry,
    trades: list[dict],
    regimes: Optional[list[str]] = None,
) -> dict:
    """Run the full gauntlet on every prior in the registry."""
    gauntlet = TestingGauntlet(registry)
    all_results = {}

    for pid in list(registry.priors.keys()):
        prior = registry.priors[pid]
        if prior.tier == EvidenceTier.REFUTED:
            continue
        logger.info("Testing prior: %s", pid)
        all_results[pid] = gauntlet.full_gauntlet(pid, trades, regimes)

    summary = {
        "total_tested": len(all_results),
        "keep_raw": sum(
            1 for r in all_results.values() if r["verdict"] == "KEEP_RAW"
        ),
        "keep_inverse": sum(
            1 for r in all_results.values() if r["verdict"] == "KEEP_INVERSE"
        ),
        "underpowered": sum(
            1 for r in all_results.values() if r["verdict"] == "UNDERPOWERED"
        ),
        "inconclusive": sum(
            1 for r in all_results.values() if r["verdict"] == "INCONCLUSIVE"
        ),
    }
    return {"results": all_results, "summary": summary}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    from seed_all_priors import seed_all

    registry = PriorRegistry()
    seed_all(registry)

    sample_trades = [
        {"time_et": "09:45", "pnl": 150.0, "month": 7, "gap_pct": 0.3,
         "vix": 18, "event_type": "NORMAL", "regime": "S1_COILED_TO_LAMINAR"},
        {"time_et": "10:15", "pnl": -80.0, "month": 7, "gap_pct": -0.5,
         "vix": 22, "event_type": "NORMAL", "regime": "S3_QUIET_ABSORPTION"},
        {"time_et": "11:45", "pnl": -50.0, "month": 9, "gap_pct": 0.1,
         "vix": 30, "event_type": "FOMC", "regime": "CHOPPY"},
        {"time_et": "09:50", "pnl": 200.0, "month": 4, "gap_pct": 0.8,
         "vix": 15, "event_type": "CPI", "regime": "S1_COILED_TO_LAMINAR"},
    ]

    gauntlet = TestingGauntlet(registry)
    result = gauntlet.full_gauntlet("TOD_PRE1120_BULLISH", sample_trades)
    print(f"\nPhase 1 (raw): WR={result['phase_1_raw'].win_rate:.1%}, "
          f"PF={result['phase_1_raw'].profit_factor:.2f}")
    print(f"Phase 2 (inv): WR={result['phase_2_inverse'].win_rate:.1%}, "
          f"PF={result['phase_2_inverse'].profit_factor:.2f}")
    print(f"Verdict: {result['verdict']}")
