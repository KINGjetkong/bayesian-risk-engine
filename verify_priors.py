"""
Prior Verification Engine — cross-checks every prior against skill protocols.

Sources of truth:
  - edge-integrity: provenance tags, sanity triggers, fill-source class
  - book-of-gold-hgtfc: real-data backtest requirement, fill convention
  - madx-algo-backtests: DeepTest gauntlet, null testing, fee rules, fair comparison
  - mustache-similarity-test: curve-fit detection
  - madx-data-vault-export: data lineage verification
  - madx-trading-master: system-level cross-checks

Each prior is checked against ALL applicable rules. Failures are logged with
the specific rule violated and what's needed to fix it.
"""
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from bayesian_prior_factory import (
    BayesianPrior, PriorRegistry, EvidenceTier, PriorCategory, InputType,
)

logger = logging.getLogger("verify_priors")


class CheckStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


@dataclass
class VerificationCheck:
    """Single check result against a prior."""
    check_id: str
    check_name: str
    skill_source: str
    status: CheckStatus
    detail: str
    fix_needed: str = ""


@dataclass
class PriorVerification:
    """Full verification result for one prior."""
    prior_id: str
    prior_name: str
    tier: str
    checks: list = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    verdict: str = ""

    def add_check(self, check: VerificationCheck):
        self.checks.append(check)
        if check.status == CheckStatus.PASS:
            self.passed += 1
        elif check.status == CheckStatus.FAIL:
            self.failed += 1
        elif check.status == CheckStatus.WARN:
            self.warned += 1
        else:
            self.skipped += 1

    def compute_verdict(self):
        if self.failed > 0:
            self.verdict = "NEEDS_WORK"
        elif self.warned > 0:
            self.verdict = "REVIEW"
        else:
            self.verdict = "CLEAN"


# ---------------------------------------------------------------------------
# EDGE-INTEGRITY checks (provenance, sanity, fill-source)
# ---------------------------------------------------------------------------

def check_provenance_tag(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity §3: every stated statistic carries a provenance tag."""
    prov = getattr(prior, "provenance_tag", "") or ""
    source = prior.source or ""
    notes = prior.notes or ""
    combined = f"{prov} {source} {notes}"

    has_verified = bool(re.search(r"\[VERIFIED", combined))
    has_contested = bool(re.search(r"\[CONTESTED", combined))
    has_unsourced = bool(re.search(r"\[UNSOURCED", combined))
    has_any_tag = has_verified or has_contested or has_unsourced

    has_fid = bool(re.search(r"F-\d{3,4}", combined))
    has_doc_ref = bool(re.search(
        r"(Section \d|p\.\d|State Registry|backtest doc|MADX_STATE|F01_|V19_)",
        combined,
    ))

    if has_any_tag:
        return VerificationCheck(
            check_id="EI_PROVENANCE",
            check_name="Provenance tag present",
            skill_source="edge-integrity §3",
            status=CheckStatus.PASS,
            detail=f"Has provenance tag in source/notes",
        )

    if has_fid or has_doc_ref:
        return VerificationCheck(
            check_id="EI_PROVENANCE",
            check_name="Provenance tag present",
            skill_source="edge-integrity §3",
            status=CheckStatus.WARN,
            detail=f"Has doc reference but no formal provenance tag",
            fix_needed="Add [VERIFIED <doc>] or [UNSOURCED-YET] tag",
        )

    return VerificationCheck(
        check_id="EI_PROVENANCE",
        check_name="Provenance tag present",
        skill_source="edge-integrity §3",
        status=CheckStatus.FAIL,
        detail="No provenance tag, no doc reference, no F-id",
        fix_needed="Add [VERIFIED <doc> p.X] or [UNSOURCED-YET] tag. "
                   "Without n/window/file/F-id this prior may not set a weight.",
    )


def check_sample_size(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity swarm: WR with no n/window = [UNSOURCED-YET], may not set prior."""
    if prior.sample_size > 0:
        if prior.sample_size < 30:
            return VerificationCheck(
                check_id="EI_SAMPLE_N",
                check_name="Sample size sufficient",
                skill_source="edge-integrity swarm + madx-algo-backtests",
                status=CheckStatus.WARN,
                detail=f"n={prior.sample_size} < 30 (LOGGED per DeepTest rules)",
                fix_needed="Collect more observations or mark as LOGGED",
            )
        return VerificationCheck(
            check_id="EI_SAMPLE_N",
            check_name="Sample size sufficient",
            skill_source="edge-integrity swarm + madx-algo-backtests",
            status=CheckStatus.PASS,
            detail=f"n={prior.sample_size}",
        )

    return VerificationCheck(
        check_id="EI_SAMPLE_N",
        check_name="Sample size sufficient",
        skill_source="edge-integrity swarm + madx-algo-backtests",
        status=CheckStatus.FAIL,
        detail="sample_size=0 — no observations backing this prior",
        fix_needed="Provide sample size from source data, or pull from API",
    )


def check_sanity_triggers(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity swarm: auto sanity — PF > 3, WR > 85% flag."""
    issues = []

    if prior.probability > 0.85:
        issues.append(f"WR {prior.probability:.0%} > 85%")
    if prior.verification_pf and prior.verification_pf > 3.0:
        issues.append(f"PF {prior.verification_pf:.2f} > 3.0")

    if issues:
        return VerificationCheck(
            check_id="EI_SANITY",
            check_name="Sanity trigger check",
            skill_source="edge-integrity swarm auto-sanity",
            status=CheckStatus.WARN,
            detail=f"Sanity trigger: {'; '.join(issues)}",
            fix_needed="Verify not overfitted — run look-ahead + accounting audit",
        )

    return VerificationCheck(
        check_id="EI_SANITY",
        check_name="Sanity trigger check",
        skill_source="edge-integrity swarm auto-sanity",
        status=CheckStatus.PASS,
        detail="No sanity triggers fired",
    )


def check_evidence_dedup(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity swarm: a number copied across docs is ONE observation."""
    notes = prior.notes or ""
    source = prior.source or ""
    combined = f"{source} {notes}"

    multi_source_hints = [
        "confirms", "aligns with", "same as", "also found in",
        "matches", "consistent with",
    ]
    has_multi = any(h in combined.lower() for h in multi_source_hints)

    if has_multi:
        return VerificationCheck(
            check_id="EI_DEDUP",
            check_name="Evidence deduplication",
            skill_source="edge-integrity swarm evidence-by-origin",
            status=CheckStatus.WARN,
            detail="Notes reference multiple sources — may be ONE observation copied",
            fix_needed="Verify each source is independent. Hash (n, PF, $, window) "
                       "and collapse to first source if duplicated.",
        )

    return VerificationCheck(
        check_id="EI_DEDUP",
        check_name="Evidence deduplication",
        skill_source="edge-integrity swarm evidence-by-origin",
        status=CheckStatus.PASS,
        detail="No multi-source duplication flags",
    )


# ---------------------------------------------------------------------------
# BOOK-OF-GOLD-HGTFC checks
# ---------------------------------------------------------------------------

def check_real_data_backtest(prior: BayesianPrior) -> VerificationCheck:
    """book-of-gold rule 2: nothing is a rule until re-backtested on real data."""
    if prior.tier == EvidenceTier.LOCKED:
        if prior.verified_internally and prior.verification_pf is not None:
            return VerificationCheck(
                check_id="BOG_REALDATA",
                check_name="Real-data backtest (ThetaData 1s, $0.01 spread)",
                skill_source="book-of-gold-hgtfc rule 2",
                status=CheckStatus.PASS,
                detail=f"Verified internally, PF={prior.verification_pf:.2f}",
            )
        return VerificationCheck(
            check_id="BOG_REALDATA",
            check_name="Real-data backtest (ThetaData 1s, $0.01 spread)",
            skill_source="book-of-gold-hgtfc rule 2",
            status=CheckStatus.FAIL,
            detail="LOCKED tier but not verified on real data",
            fix_needed="Run DeepTest on ThetaData 1s with $0.01 spread, BID fills",
        )

    if prior.tier == EvidenceTier.PROVISIONAL:
        if prior.verified_internally:
            return VerificationCheck(
                check_id="BOG_REALDATA",
                check_name="Real-data backtest (ThetaData 1s, $0.01 spread)",
                skill_source="book-of-gold-hgtfc rule 2",
                status=CheckStatus.PASS,
                detail="Verified internally (PROVISIONAL — needs more data for LOCKED)",
            )
        return VerificationCheck(
            check_id="BOG_REALDATA",
            check_name="Real-data backtest (ThetaData 1s, $0.01 spread)",
            skill_source="book-of-gold-hgtfc rule 2",
            status=CheckStatus.WARN,
            detail="PROVISIONAL but not yet verified on own data",
            fix_needed="Run verification backtest on own ThetaData",
        )

    return VerificationCheck(
        check_id="BOG_REALDATA",
        check_name="Real-data backtest (ThetaData 1s, $0.01 spread)",
        skill_source="book-of-gold-hgtfc rule 2",
        status=CheckStatus.SKIP,
        detail=f"Tier {prior.tier.value} — real-data requirement applies at LOCKED/PROVISIONAL",
    )


def check_fill_convention(prior: BayesianPrior) -> VerificationCheck:
    """book-of-gold rule 3: fills at BID, hard-stop -13.5%, never green->red."""
    notes = prior.notes or ""
    source = prior.source or ""
    combined = f"{source} {notes}".lower()

    bad_fills = []
    if "$0.65" in combined:
        bad_fills.append("Uses $0.65 commission (Josh's real fee is $0.10/side)")
    if "mid" in combined and "fill" in combined:
        bad_fills.append("Mid fills detected — should be BID fills")
    if "limit" in combined and "fill" in combined:
        bad_fills.append("Limit fills detected — verify BID convention")

    if bad_fills:
        return VerificationCheck(
            check_id="BOG_FILLS",
            check_name="Fill convention (BID, no artificial fees)",
            skill_source="book-of-gold rule 3 + madx-algo-backtests fees",
            status=CheckStatus.FAIL,
            detail="; ".join(bad_fills),
            fix_needed="Recalculate with BID fills, $0.10/side (or no-fee first)",
        )

    return VerificationCheck(
        check_id="BOG_FILLS",
        check_name="Fill convention (BID, no artificial fees)",
        skill_source="book-of-gold rule 3 + madx-algo-backtests fees",
        status=CheckStatus.PASS,
        detail="No fill convention violations detected",
    )


# ---------------------------------------------------------------------------
# MADX-ALGO-BACKTESTS checks
# ---------------------------------------------------------------------------

def check_fee_compliance(prior: BayesianPrior) -> VerificationCheck:
    """madx-algo-backtests fees: no-fee first, $0.10/side labeled separately. Never $0.65."""
    notes = prior.notes or ""
    source = prior.source or ""
    combined = f"{source} {notes}"

    if "$0.65" in combined or "0.65" in combined:
        return VerificationCheck(
            check_id="MADX_FEES",
            check_name="Fee compliance ($0.10/side, no-fee first)",
            skill_source="madx-algo-backtests fees section",
            status=CheckStatus.FAIL,
            detail="References $0.65 commission — BANNED per Josh's rules",
            fix_needed="Rerun with no fees first, then $0.10/side labeled separately",
        )

    return VerificationCheck(
        check_id="MADX_FEES",
        check_name="Fee compliance ($0.10/side, no-fee first)",
        skill_source="madx-algo-backtests fees section",
        status=CheckStatus.PASS,
        detail="No banned fee references",
    )


def check_null_testing(prior: BayesianPrior) -> VerificationCheck:
    """madx-algo-backtests stats: null test with 1000 shuffles needed."""
    if prior.tier in (EvidenceTier.LOCKED, EvidenceTier.PROVISIONAL):
        notes = prior.notes or ""
        has_pvalue = bool(re.search(r"p[=<]\s*0\.\d", notes))
        has_null = "null" in notes.lower() or "shuffle" in notes.lower()

        if has_pvalue or has_null:
            return VerificationCheck(
                check_id="MADX_NULL",
                check_name="Null testing (1000 shuffles, luck bar)",
                skill_source="madx-algo-backtests stats section",
                status=CheckStatus.PASS,
                detail="P-value or null test referenced",
            )

        return VerificationCheck(
            check_id="MADX_NULL",
            check_name="Null testing (1000 shuffles, luck bar)",
            skill_source="madx-algo-backtests stats section",
            status=CheckStatus.WARN,
            detail=f"{prior.tier.value} tier but no null test / p-value documented",
            fix_needed="Run 1000-shuffle null test with luck bar 0.05 / cells",
        )

    return VerificationCheck(
        check_id="MADX_NULL",
        check_name="Null testing (1000 shuffles, luck bar)",
        skill_source="madx-algo-backtests stats section",
        status=CheckStatus.SKIP,
        detail=f"Tier {prior.tier.value} — null testing required at LOCKED/PROVISIONAL",
    )


def check_is_oos_split(prior: BayesianPrior) -> VerificationCheck:
    """madx-algo-backtests DeepTest: >=20 days, >=10 each half for gate."""
    if prior.tier == EvidenceTier.LOCKED:
        notes = prior.notes or ""
        has_oos = any(k in notes.lower() for k in ["oos", "out-of-sample", "out of sample", "is/oos"])
        has_split = any(k in notes.lower() for k in ["halves", "is pf", "oos pf"])

        if has_oos or has_split:
            return VerificationCheck(
                check_id="MADX_ISOOS",
                check_name="IS/OOS split validation",
                skill_source="madx-algo-backtests DeepTest gate",
                status=CheckStatus.PASS,
                detail="OOS reference found in notes",
            )

        return VerificationCheck(
            check_id="MADX_ISOOS",
            check_name="IS/OOS split validation",
            skill_source="madx-algo-backtests DeepTest gate",
            status=CheckStatus.WARN,
            detail="LOCKED but no IS/OOS split documented",
            fix_needed="Run DeepTest gate: >=20 days, >=10 each half, halves side by side",
        )

    return VerificationCheck(
        check_id="MADX_ISOOS",
        check_name="IS/OOS split validation",
        skill_source="madx-algo-backtests DeepTest gate",
        status=CheckStatus.SKIP,
        detail=f"Tier {prior.tier.value} — IS/OOS gate required at LOCKED",
    )


def check_fair_comparison(prior: BayesianPrior) -> VerificationCheck:
    """madx-algo-backtests fair comparison: day-type mix must be reported."""
    if prior.tier in (EvidenceTier.LOCKED, EvidenceTier.PROVISIONAL):
        notes = prior.notes or ""
        has_day_mix = any(k in notes.lower() for k in [
            "event day", "normal day", "cpi", "fomc", "nfp", "day type",
            "event-day share", "macro",
        ])

        if has_day_mix:
            return VerificationCheck(
                check_id="MADX_DAYMIX",
                check_name="Fair comparison (day-type mix reported)",
                skill_source="madx-algo-backtests fair comparison",
                status=CheckStatus.PASS,
                detail="Day-type context present in notes",
            )

        return VerificationCheck(
            check_id="MADX_DAYMIX",
            check_name="Fair comparison (day-type mix reported)",
            skill_source="madx-algo-backtests fair comparison",
            status=CheckStatus.WARN,
            detail="No day-type mix information — may be EVENT_CARRIED",
            fix_needed="Report n, WR, PF per day type (FOMC/CPI/NFP/NORMAL)",
        )

    return VerificationCheck(
        check_id="MADX_DAYMIX",
        check_name="Fair comparison (day-type mix reported)",
        skill_source="madx-algo-backtests fair comparison",
        status=CheckStatus.SKIP,
        detail=f"Tier {prior.tier.value}",
    )


def check_edgeful_base_rate(prior: BayesianPrior) -> VerificationCheck:
    """madx-algo-backtests Edgeful: these are BASE RATES, not trade edges."""
    source = prior.source or ""
    if "edgeful" not in source.lower():
        return VerificationCheck(
            check_id="MADX_EDGEFUL",
            check_name="Edgeful base-rate caveat",
            skill_source="madx-algo-backtests Edgeful section",
            status=CheckStatus.SKIP,
            detail="Not an Edgeful-sourced prior",
        )

    notes = prior.notes or ""
    if prior.sample_size == 0:
        return VerificationCheck(
            check_id="MADX_EDGEFUL",
            check_name="Edgeful base-rate caveat",
            skill_source="madx-algo-backtests Edgeful section",
            status=CheckStatus.FAIL,
            detail="Edgeful prior with sample_size=0 — placeholder, no API pull",
            fix_needed="Pull from Edgeful API: GET /report_calculation/<slug>/stock/QQQ",
        )

    has_base_rate_warning = "base rate" in notes.lower() or "not trade edge" in notes.lower()
    if not has_base_rate_warning:
        return VerificationCheck(
            check_id="MADX_EDGEFUL",
            check_name="Edgeful base-rate caveat",
            skill_source="madx-algo-backtests Edgeful section",
            status=CheckStatus.WARN,
            detail="Edgeful prior lacks base-rate caveat — these are session stats, not edges",
            fix_needed="Add note: Edgeful = day/session base rate on OHLC, not trade edge. "
                       "Compare against random entries on same days (protocol 15).",
        )

    return VerificationCheck(
        check_id="MADX_EDGEFUL",
        check_name="Edgeful base-rate caveat",
        skill_source="madx-algo-backtests Edgeful section",
        status=CheckStatus.PASS,
        detail="Edgeful base-rate caveat documented",
    )


def check_tier_consistency(prior: BayesianPrior) -> VerificationCheck:
    """Cross-check: tier must match evidence level.

    LOCKED requires: verified_internally=True, verification_pf set, sample_size>0
    PROVISIONAL requires: sample_size>0 or source document reference
    """
    if prior.tier == EvidenceTier.LOCKED:
        issues = []
        if not prior.verified_internally:
            issues.append("verified_internally=False")
        if prior.verification_pf is None:
            issues.append("no verification_pf")
        if prior.sample_size == 0:
            issues.append("sample_size=0")

        if issues:
            return VerificationCheck(
                check_id="TIER_CONSISTENCY",
                check_name="Tier-evidence consistency",
                skill_source="edge-integrity + book-of-gold combined",
                status=CheckStatus.FAIL,
                detail=f"LOCKED but: {', '.join(issues)}",
                fix_needed="Either downgrade tier or provide missing verification data",
            )

    elif prior.tier == EvidenceTier.PROVISIONAL:
        if prior.sample_size == 0 and not prior.source:
            return VerificationCheck(
                check_id="TIER_CONSISTENCY",
                check_name="Tier-evidence consistency",
                skill_source="edge-integrity + book-of-gold combined",
                status=CheckStatus.FAIL,
                detail="PROVISIONAL but no sample size and no source",
                fix_needed="Provide sample size or source document",
            )

    return VerificationCheck(
        check_id="TIER_CONSISTENCY",
        check_name="Tier-evidence consistency",
        skill_source="edge-integrity + book-of-gold combined",
        status=CheckStatus.PASS,
        detail=f"Tier {prior.tier.value} consistent with evidence fields",
    )


def check_causality(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity swarm: condition must be knowable BEFORE the outcome."""
    condition = prior.condition.lower()
    outcome = prior.outcome.lower()

    lookahead_words = [
        "closed", "end of day", "final", "session close",
        "full day", "by eod", "closing price",
    ]
    condition_lookahead = any(w in condition for w in lookahead_words)

    if condition_lookahead:
        return VerificationCheck(
            check_id="EI_CAUSALITY",
            check_name="Causality (condition knowable before outcome)",
            skill_source="edge-integrity swarm causality",
            status=CheckStatus.FAIL,
            detail=f"Condition contains post-hoc language: {condition[:80]}",
            fix_needed="Rewrite condition to use only pre-entry knowable facts. "
                       "Measure from when the thing is knowable (lesson 1, Nov 1-2).",
        )

    return VerificationCheck(
        check_id="EI_CAUSALITY",
        check_name="Causality (condition knowable before outcome)",
        skill_source="edge-integrity swarm causality",
        status=CheckStatus.PASS,
        detail="No obvious look-ahead in condition",
    )


# ---------------------------------------------------------------------------
# MUSTACHE SIMILARITY TEST placeholder (populated when skill loads)
# ---------------------------------------------------------------------------

def check_mustache_similarity(prior: BayesianPrior) -> VerificationCheck:
    """mustache-similarity-test: 4 cuts — in-cell split, impostor seconds,
    trigger shift, horizon split. Verdict: STATE-DRIVEN / TRIGGER-DRIVEN / JOINT.
    Real 1-s quotes, buy ask/sell bid t+1, $0 fees, day-clustered shuffles >=200.
    """
    overfit_hints = [
        prior.probability > 0.90 and prior.sample_size < 50,
        prior.verification_pf is not None and prior.verification_pf > 5.0
        and (prior.verification_n or 0) < 100,
    ]

    if any(overfit_hints):
        return VerificationCheck(
            check_id="MUSTACHE",
            check_name="Mustache 4-cut test readiness",
            skill_source="mustache-similarity-test",
            status=CheckStatus.WARN,
            detail="High performance on small sample — possible curve fit",
            fix_needed="Run 4-cut mustache: (1) in-cell split winners vs duds by filter "
                       "features, (2) impostor seconds where state matches but trigger "
                       "didn't fire, (3) trigger shift +/-300s, (4) horizon split "
                       "10s..30min. Verdict: STATE-DRIVEN / TRIGGER-DRIVEN / JOINT.",
        )

    return VerificationCheck(
        check_id="MUSTACHE",
        check_name="Mustache 4-cut test readiness",
        skill_source="mustache-similarity-test",
        status=CheckStatus.PASS,
        detail="No obvious curve-fit indicators (still needs formal 4-cut test)",
    )


def check_banned_features(prior: BayesianPrior) -> VerificationCheck:
    """edge-governance §08: banned features that must not be used as entry inputs."""
    condition = (prior.condition or "").lower()
    notes = (prior.notes or "").lower()
    combined = f"{condition} {notes}"

    banned = {
        "bid_move_2.5m": "bid_move_2.5m_pct",
        "mfe as live target": "MFE as live target",
        "entry_z": "entry_z",
        "relative volume": "relative volume (unbounded)",
        "hurst": "Hurst exponent",
        "rsi-separation": "RSI-separation",
        "consecutive-candle": "consecutive-candle count",
    }
    found = []
    for pattern, name in banned.items():
        if pattern in combined:
            found.append(name)

    if found:
        return VerificationCheck(
            check_id="GOV_BANNED",
            check_name="Banned features check",
            skill_source="madx-trading-master edge-governance §08",
            status=CheckStatus.FAIL,
            detail=f"Uses banned feature(s): {', '.join(found)}",
            fix_needed="Remove banned features from condition. "
                       "Gate = mechanical friction only, never alpha scoring.",
        )

    return VerificationCheck(
        check_id="GOV_BANNED",
        check_name="Banned features check",
        skill_source="madx-trading-master edge-governance §08",
        status=CheckStatus.PASS,
        detail="No banned features detected",
    )


def check_evidence_axes(prior: BayesianPrior) -> VerificationCheck:
    """edge-integrity swarm: three evidence axes required —
    causality (PREFIX_SAFE_TESTED), execution (ACTUAL_FILL), validation (REPLICATED).
    """
    if prior.tier in (EvidenceTier.RESEARCH, EvidenceTier.EXTERNAL):
        return VerificationCheck(
            check_id="EI_AXES",
            check_name="Three evidence axes declared",
            skill_source="edge-integrity swarm evidence axes",
            status=CheckStatus.SKIP,
            detail=f"Tier {prior.tier.value} — axes required at LOCKED/PROVISIONAL",
        )

    notes = (prior.notes or "").lower()
    source = (prior.source or "").lower()
    combined = f"{notes} {source}"

    axes_found = []
    causality_terms = ["prefix_safe", "lookahead", "causal", "knowable before"]
    execution_terms = ["actual_fill", "broker", "replay", "bid fill", "ask fill", "thetadata"]
    validation_terms = ["replicated", "lockbox", "oos", "out-of-sample", "deeptest"]

    if any(t in combined for t in causality_terms):
        axes_found.append("causality")
    if any(t in combined for t in execution_terms):
        axes_found.append("execution")
    if any(t in combined for t in validation_terms):
        axes_found.append("validation")

    if len(axes_found) == 3:
        return VerificationCheck(
            check_id="EI_AXES",
            check_name="Three evidence axes declared",
            skill_source="edge-integrity swarm evidence axes",
            status=CheckStatus.PASS,
            detail=f"All 3 axes present: {', '.join(axes_found)}",
        )

    missing = [a for a in ["causality", "execution", "validation"] if a not in axes_found]
    return VerificationCheck(
        check_id="EI_AXES",
        check_name="Three evidence axes declared",
        skill_source="edge-integrity swarm evidence axes",
        status=CheckStatus.WARN,
        detail=f"Missing axes: {', '.join(missing)} (has: {', '.join(axes_found) or 'none'})",
        fix_needed="Declare all 3: causality (PREFIX_SAFE_TESTED/LOOKAHEAD_IDENTIFIED), "
                   "execution (ACTUAL_FILL/QUOTE_MODEL/TRADE_PRINT_PROXY), "
                   "validation (DEVELOPMENT/REPLICATED/LOCKBOX).",
    )


def check_fill_model(prior: BayesianPrior) -> VerificationCheck:
    """madx-trading-master backtest-laws §09: fill at t+1s, buy ASK / sell BID.
    Never mid, never same-second.
    """
    notes = (prior.notes or "").lower()
    source = (prior.source or "").lower()
    combined = f"{notes} {source}"

    bad = []
    if "same-second" in combined or "same second" in combined:
        bad.append("Same-second fills detected")
    if "mid fill" in combined or "fill at mid" in combined:
        bad.append("Mid fills — should be buy ASK / sell BID")

    if bad:
        return VerificationCheck(
            check_id="LAW_FILLS",
            check_name="Fill model (buy ASK / sell BID at t+1s)",
            skill_source="madx-trading-master backtest-laws §09",
            status=CheckStatus.FAIL,
            detail="; ".join(bad),
            fix_needed="Rerun with fill model: decide at t, buy ASK / sell BID at t+1s",
        )

    return VerificationCheck(
        check_id="LAW_FILLS",
        check_name="Fill model (buy ASK / sell BID at t+1s)",
        skill_source="madx-trading-master backtest-laws §09",
        status=CheckStatus.PASS,
        detail="No fill model violations detected",
    )


# ---------------------------------------------------------------------------
# Run all checks on one prior
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    # edge-integrity
    check_provenance_tag,
    check_sample_size,
    check_sanity_triggers,
    check_evidence_dedup,
    check_causality,
    check_evidence_axes,
    # book-of-gold-hgtfc
    check_real_data_backtest,
    check_fill_convention,
    # madx-algo-backtests
    check_fee_compliance,
    check_null_testing,
    check_is_oos_split,
    check_fair_comparison,
    check_edgeful_base_rate,
    # madx-trading-master (edge-governance + backtest-laws)
    check_banned_features,
    check_fill_model,
    # mustache-similarity-test
    check_mustache_similarity,
    # cross-skill
    check_tier_consistency,
]


def verify_prior(prior: BayesianPrior) -> PriorVerification:
    """Run all verification checks on a single prior."""
    v = PriorVerification(
        prior_id=prior.id,
        prior_name=prior.name,
        tier=prior.tier.value,
    )
    for check_fn in ALL_CHECKS:
        result = check_fn(prior)
        v.add_check(result)
    v.compute_verdict()
    return v


def verify_all(registry: PriorRegistry) -> list[PriorVerification]:
    """Verify every non-refuted prior in the registry."""
    results = []
    for pid, prior in sorted(registry.priors.items()):
        if prior.tier == EvidenceTier.REFUTED:
            continue
        results.append(verify_prior(prior))
    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[PriorVerification]) -> dict:
    """Generate a summary report from verification results."""
    total = len(results)
    clean = sum(1 for r in results if r.verdict == "CLEAN")
    needs_work = sum(1 for r in results if r.verdict == "NEEDS_WORK")
    review = sum(1 for r in results if r.verdict == "REVIEW")

    by_tier = {}
    for r in results:
        tier = r.tier
        if tier not in by_tier:
            by_tier[tier] = {"total": 0, "clean": 0, "needs_work": 0, "review": 0}
        by_tier[tier]["total"] += 1
        by_tier[tier][r.verdict.lower()] = by_tier[tier].get(r.verdict.lower(), 0) + 1

    failed_checks = {}
    for r in results:
        for c in r.checks:
            if c.status == CheckStatus.FAIL:
                key = c.check_id
                if key not in failed_checks:
                    failed_checks[key] = {"name": c.check_name, "count": 0, "priors": []}
                failed_checks[key]["count"] += 1
                failed_checks[key]["priors"].append(r.prior_id)

    worst_priors = sorted(
        [r for r in results if r.verdict == "NEEDS_WORK"],
        key=lambda r: r.failed,
        reverse=True,
    )[:20]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_verified": total,
            "clean": clean,
            "needs_work": needs_work,
            "review": review,
            "clean_pct": f"{clean/total*100:.1f}%" if total else "0%",
        },
        "by_tier": by_tier,
        "most_common_failures": {
            k: {"name": v["name"], "count": v["count"]}
            for k, v in sorted(
                failed_checks.items(), key=lambda x: x[1]["count"], reverse=True,
            )
        },
        "worst_20": [
            {
                "id": r.prior_id,
                "name": r.prior_name,
                "tier": r.tier,
                "failed": r.failed,
                "warned": r.warned,
                "failures": [
                    {"check": c.check_id, "detail": c.detail, "fix": c.fix_needed}
                    for c in r.checks if c.status == CheckStatus.FAIL
                ],
            }
            for r in worst_priors
        ],
    }


def print_report(report: dict):
    """Print a human-readable verification report."""
    s = report["summary"]
    print("=" * 70)
    print("PRIOR VERIFICATION REPORT")
    print(f"  {report['timestamp']}")
    print("=" * 70)
    print(f"\n  Total verified: {s['total_verified']}")
    print(f"  CLEAN:      {s['clean']} ({s['clean_pct']})")
    print(f"  NEEDS_WORK: {s['needs_work']}")
    print(f"  REVIEW:     {s['review']}")

    print("\n--- By Tier ---")
    for tier, counts in sorted(report["by_tier"].items()):
        print(f"  {tier:12s}: {counts['total']:3d} total | "
              f"clean {counts.get('clean',0)} | needs_work {counts.get('needs_work',0)} | "
              f"review {counts.get('review',0)}")

    print("\n--- Most Common Failures ---")
    for check_id, info in report["most_common_failures"].items():
        print(f"  {check_id:20s}: {info['count']:3d} priors — {info['name']}")

    if report["worst_20"]:
        print("\n--- Worst 20 Priors (most failures) ---")
        for p in report["worst_20"]:
            print(f"\n  [{p['tier']:12s}] {p['id']}")
            print(f"    {p['name']}")
            print(f"    {p['failed']} FAIL, {p['warned']} WARN")
            for f in p["failures"]:
                print(f"    FAIL {f['check']}: {f['detail']}")
                if f["fix"]:
                    print(f"         FIX: {f['fix']}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    logging.basicConfig(level=logging.ERROR)

    from seed_all_priors import seed_all

    registry = PriorRegistry()
    seed_all(registry)

    results = verify_all(registry)
    report = generate_report(results)
    print_report(report)

    out_path = Path("RUNS/VERIFICATION_REPORT.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved to {out_path}")
