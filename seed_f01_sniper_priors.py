"""
Priors extracted from the F01_HGTFC_OPTIONZ_AA_MORNING_SNIPER sleeve.

Source: Google Drive file OH_YEAH__F01_HGTFC_OPTIONZ_AA_MORNING_SNIPER.py
Results: IS PF 4.77 / OOS PF 3.61 / W3 PF 2.48 (n=142, 1c book)
Fill protocol: Ask[t+1s] -> Bid[t], $0 fees first / $0.10 second
Two-window verified: W1 n=68, W2 n=74

These priors encode the verifiable, quantifiable conditions that make
F01 fire and the exit mechanics that harvest its edge.
"""
from bayesian_prior_factory import (
    BayesianPrior, PriorCategory, EvidenceTier, InputType,
    PriorRegistry,
)


def seed_f01_sniper_priors(registry: PriorRegistry) -> int:
    priors = [
        BayesianPrior(
            id="F01_MORNING_LOCK_PRE1130",
            name="F01 morning <11:30 ET sniper lock",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Entry before 11:30 ET with HGTFC + conviction grid alignment",
            outcome="IS PF 4.77 / OOS PF 3.61 on 1c book",
            probability=0.65,
            sample_size=142,
            time_period="Two-window verified (W1 68, W2 74)",
            source="F01_HGTFC_OPTIONZ_AA_MORNING_SNIPER gen1",
            verified_internally=True,
            verification_pf=3.61,
            verification_n=142,
            input_type=InputType.BINARY,
            regime_locked=True,
            regime_conditions="morning < 11:30 ET",
            tickers=["QQQ", "SPY"],
            timeframe="0DTE 2m-14m hold",
            notes="Two-window proven. W3 PF 2.48 = KEEP-PAPER-NOW. "
                  "Uses Ask[t+1s]->Bid[t] causal fills.",
        ),
        BayesianPrior(
            id="F01_MIDDAY_CHOP_VETO",
            name="Midday 11:30-13:50 ET chop veto",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Time between 11:30-13:50 ET for 0DTE directional snipers",
            outcome="Signal quality degrades — veto all entries",
            probability=0.35,
            sample_size=142,
            time_period="F01 development period",
            source="F01_HGTFC_OPTIONZ switchboard B3",
            verified_internally=True,
            input_type=InputType.BINARY,
            regime_locked=True,
            regime_conditions="11:30 <= tod_min <= 13:50 ET",
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Hardcoded veto in production sleeve. Cuts midday chop.",
        ),
        BayesianPrior(
            id="F01_1C_SPREAD_GATE",
            name="1-cent spread execution gate",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.PROVISIONAL,
            condition="Option bid-ask spread <= $0.01",
            outcome="Executions on 1c spreads show PF 4.77 IS / 3.61 OOS",
            probability=0.65,
            sample_size=142,
            time_period="F01 gen1 two-window",
            source="F01_HGTFC R-001 + 1-Cent-Spread Rule",
            verified_internally=True,
            verification_pf=3.61,
            verification_n=142,
            input_type=InputType.BINARY,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Spread > $0.01 = reject. Also Ask band $0.50-$2.00. "
                  "Verified on real NBBO quotes.",
        ),
        BayesianPrior(
            id="F01_CONVICTION_GRID_ALIGNMENT",
            name="Optionz engine + conviction grid alignment",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Optionz Engine ▲▲ WITH + Conviction Grid align",
            outcome="Entry signal fires with PF 4.77 IS",
            probability=0.65,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC_OPTIONZ signal gate",
            verified_internally=True,
            verification_pf=4.77,
            verification_n=68,
            input_type=InputType.BINARY,
            tickers=["QQQ", "SPY"],
            notes="Multi-clock order flow + conviction grid alignment. "
                  "AGAINST conviction grid = no fire.",
        ),
        BayesianPrior(
            id="F01_2MIN_GLOW_POSITIVE",
            name="2-minute glow > 0 entry confirmation",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.PROVISIONAL,
            condition="2-Min Glow > 0 at entry time",
            outcome="Confirms momentum direction for sniper entry",
            probability=0.60,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC_OPTIONZ 2-Min Glow requirement",
            verified_internally=True,
            input_type=InputType.BINARY,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE 2m-14m",
            notes="2-Min Glow = short-term momentum confirmation. "
                  "Glow <= 0 = no fire.",
        ),
        BayesianPrior(
            id="F01_ARMED_RATCHET_EXIT",
            name="Armed ratchet +12% arm / +8% floor harvester",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="MFE reaches +12% from entry",
            outcome="Never-red floor locks at max(+8%, 0.65*MFE)",
            probability=0.70,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC switchboard B5 Armed Pure-Pct Ratchet",
            verified_internally=True,
            input_type=InputType.SPECTRUM,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Zero fixed price stops (R-001 CON-08 banned). "
                  "Dynamic floor = max(floor_pct, 0.65 * mfe_pct). "
                  "Armed winner never turns red.",
        ),
        BayesianPrior(
            id="F01_PHYS_DERIV_5COND_STOP",
            name="5-condition physics-derivative stop",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.PROVISIONAL,
            condition="Un-armed trade: PnL <= -18% AND hold >= breathing_s AND "
                      "all 5 conditions met (swing broken, spot vel neg, "
                      "opt vel+acc neg, jerk/spread deteriorated)",
            outcome="Exit red trade on physics-based deterioration",
            probability=0.55,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC switchboard B6 (F-0131)",
            verified_internally=True,
            input_type=InputType.BINARY,
            regime_locked=True,
            regime_conditions="un-armed position, PnL <= -18%, past breathing window",
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Requires ALL 5: breathing time elapsed, swing threshold "
                  "broken, spot velocity negative, option 1st+2nd derivatives "
                  "negative, jerk or spread deteriorated. Fixed stops BANNED.",
        ),
        BayesianPrior(
            id="F01_EOD_FLATTEN_1550",
            name="15:50 ET hard EOD flatten",
            category=PriorCategory.TIME_OF_DAY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Time >= 15:50 ET with any open 0DTE position",
            outcome="Force flat — zero overnight 0DTE exposure",
            probability=0.50,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC EOD flatten rule",
            verified_internally=True,
            input_type=InputType.BINARY,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Entry cutoff 15:44 ET, EOD flatten 15:50 ET. "
                  "No overnight 0DTE exposure.",
        ),
        BayesianPrior(
            id="F01_CME_LEAD_Z_ENTRY",
            name="CME lead-lag z-score >= 1.5 entry signal",
            category=PriorCategory.FUTURES_LEAD,
            tier=EvidenceTier.PROVISIONAL,
            condition="CME NQ/ES lead z-score >= 1.5 at entry bar",
            outcome="Futures lead confirms directional move for option entry",
            probability=0.60,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC signal gate (cme_lead_z condition)",
            verified_internally=True,
            input_type=InputType.SPECTRUM,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE 1s bars",
            notes="One of multiple signal conditions (OR gate): "
                  "opt_vel_60s > 0 OR cme_lead_z >= 1.5 OR "
                  "hotspot_score >= 0.65 OR grassmann_geodesic_z >= 2.0",
        ),
        BayesianPrior(
            id="F01_SHADOW_TO_PAPER_GATE",
            name="n >= 30 two-window qualification for paper",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Cell has n >= 30 trades across two independent windows",
            outcome="Promoted from SHADOW (0 orders) to PAPER (1 lot)",
            probability=0.55,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC qualification lock",
            verified_internally=True,
            input_type=InputType.BINARY,
            notes="Sub-30 trade cells forced into SHADOW (logs only). "
                  "Two-window requirement prevents single-period overfitting. "
                  "Paper starts at qty=1.",
        ),
        BayesianPrior(
            id="F01_SAVITZKY_FLATNESS_GATE",
            name="Savitzky-Golay flatness filter",
            category=PriorCategory.MICROSTRUCTURE,
            tier=EvidenceTier.PROVISIONAL,
            condition="Savitzky-Golay smoothed price derivative indicates flatness OK",
            outcome="Filters out noisy/choppy price action before entry",
            probability=0.58,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC signal gate (savitzky_flatness_ok)",
            verified_internally=True,
            input_type=InputType.BINARY,
            tickers=["QQQ", "SPY"],
            notes="Must be True for entry. Rejects jagged intrabar noise.",
        ),
        BayesianPrior(
            id="F01_ASK_BAND_050_200",
            name="Option ask price band $0.50-$2.00",
            category=PriorCategory.GREEKS,
            tier=EvidenceTier.PROVISIONAL,
            condition="Option ask between $0.50 and $2.00",
            outcome="Liquid, tradeable delta range for 0DTE",
            probability=0.62,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC Law E1 Ask cap",
            verified_internally=True,
            input_type=InputType.SPECTRUM,
            tickers=["QQQ", "SPY"],
            timeframe="0DTE",
            notes="Below $0.50 = illiquid/wide. Above $2.00 = too deep ITM "
                  "or too expensive for 0DTE momentum. This band captures "
                  "the liquid delta range where dealer hedging amplifies moves.",
        ),
        BayesianPrior(
            id="F01_TWIN_LIFT_RANDOM",
            name="F01 +22.9 pts vs random twin (p=0.0004)",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="F01 entry timing vs matched-clock random twin entries",
            outcome="+22.9 pts lift, shuffle p = 0.0004",
            probability=0.65,
            sample_size=142,
            time_period="F01 gen1 Phase 2 test",
            source="F01_HGTFC Phase 2 twin test",
            verified_internally=True,
            verification_pf=3.61,
            verification_n=142,
            input_type=InputType.BINARY,
            notes="Entry edge confirmed vs random: not just regime selection. "
                  "p=0.0004 << 0.05 luck bar.",
        ),
        BayesianPrior(
            id="F01_CAPITAL_GOVERNOR",
            name="3-ledger capital governor drawdown gates",
            category=PriorCategory.PROPRIETARY,
            tier=EvidenceTier.PROVISIONAL,
            condition="Daily drawdown hits threshold",
            outcome="-2.5% -> 0.5x size, -5% -> 0.0x size (halt)",
            probability=0.50,
            sample_size=142,
            time_period="F01 gen1",
            source="F01_HGTFC switchboard B7",
            verified_internally=True,
            input_type=InputType.SPECTRUM,
            notes="Pod shadow gate: reduces exposure on drawdown. "
                  "3-ledger = sleeve + pod + account. "
                  "Circuit breaker prevents blowup days.",
        ),
    ]

    count = 0
    for p in priors:
        registry.register(p)
        count += 1
    return count


if __name__ == "__main__":
    registry = PriorRegistry()
    n = seed_f01_sniper_priors(registry)
    print(f"F01 Morning Sniper priors seeded: {n}")
    for p in registry.priors.values():
        print(f"  [{p.tier.value:12s}] {p.id}: {p.name}")
