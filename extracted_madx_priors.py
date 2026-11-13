"""
Extracted priors from MADX_STATE-3 persistent brain document (285KB).
Source: Google Drive file 'claude finding research backtest and algo development IMPORTANT MADX_STATE-3.md'
Extraction date: 2026-11-13

These are quantifiable if-then rules found across the document's 292K chars,
covering findings from ~F-0066 through ~F-0369, fleet operations, backtests,
and regime studies from Jul-Aug 2026.

IMPORTANT:
- V62 fleet numbers use real Alpaca paper fills on ThetaData NBBO
- QuantPad numbers are IN-SAMPLE ONLY unless marked OOS
- Any claim from Manus/Gemini/other-AI is tagged [OTHER-AI] and unverified
- PF numbers are $0-fee unless noted
- Josh's real fees are $0.10/contract/side, NEVER $0.65
"""

MADX_EXTRACTED_PRIORS = [
    # =====================================================================
    # TIME OF DAY
    # =====================================================================
    {
        "name": "pre_1120_et_morning_edge",
        "category": "TIME_OF_DAY",
        "rule": "IF entries taken before 11:20 ET THEN significantly higher PF",
        "probability": None,
        "pf": 2.35,
        "sample_size": 851,
        "source": "MADX_STATE-3 tick revalidation, 851 real Tradier fills",
        "tier": "LOCKED",
        "notes": "<=11:20 ET PF 2.35 vs after 11:20 ET PF 0.46. SPY NOSTOP PF 1.12->1.32 with pre-11:20 gate. Strongest validated signal across multiple independent datasets."
    },
    {
        "name": "midday_chop_deweight",
        "category": "TIME_OF_DAY",
        "rule": "IF time is 11:30-13:50 ET THEN reduce size to 0.5x or skip",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 Gamma doc consensus (3 docs)",
        "tier": "PROVISIONAL",
        "notes": "PPS size x1.0 morning / x0.75 midday / x0.5 afternoon. MATCHES live 7/15 bleed pattern."
    },
    {
        "name": "call_block_after_1330_et",
        "category": "TIME_OF_DAY",
        "rule": "IF time >= 13:30 ET THEN block CALL entries",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 V6.4 engine config CALL_BLOCK_1330",
        "tier": "PROVISIONAL",
        "notes": "Deployed in live V6.4 engine. Theta decay accelerates on calls in afternoon."
    },
    {
        "name": "morning_qty_boost",
        "category": "TIME_OF_DAY",
        "rule": "IF time < 11:30 ET THEN use 100 qty (2x base 50)",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 V6.4 config MORNING_QTY=100/BASE_QTY=50",
        "tier": "PROVISIONAL",
        "notes": "Morning window gets double sizing vs afternoon base."
    },
    {
        "name": "ten_oclock_put_hole",
        "category": "TIME_OF_DAY",
        "rule": "IF buying puts at 10:00 ET into a recovery day THEN expect large loss",
        "probability": None,
        "pf": None,
        "sample_size": 186,
        "source": "MADX_STATE-3 #85 enrich716 forensics",
        "tier": "RESEARCH",
        "notes": "10:00 ET bucket: -$40,466 loss on 7/16. Puts bought INTO bounces on recovery day. Every other bucket green except 13:00 (-$10K)."
    },
    {
        "name": "entry_cutoff_1544_et",
        "category": "TIME_OF_DAY",
        "rule": "IF time > 15:44 ET THEN block all new entries",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 V6.4 hard cutoff + F01 morning sniper",
        "tier": "LOCKED",
        "notes": "Hard entry cutoff 15:44 ET (3:44 PM). EOD flatten at 15:50 ET. Deployed in F01 and V6.4."
    },
    {
        "name": "f01_morning_sniper_lock",
        "category": "TIME_OF_DAY",
        "rule": "IF time < 11:30 ET AND optionz+conviction align AND 2min_glow > 0 AND spread <= 1c THEN fire sniper entry",
        "probability": None,
        "pf": 4.77,
        "sample_size": 142,
        "source": "MADX_STATE-3 F01_HGTFC_OPTIONZ_AA_MORNING_SNIPER",
        "tier": "PROVISIONAL",
        "notes": "IS PF 4.77 / OOS PF 3.61 / W3 PF 2.48. n=142 1c book (68 W1 / 74 W2). Two-window verified. PAPER 1-lot status."
    },
    # =====================================================================
    # REGIME / GEX
    # =====================================================================
    {
        "name": "gex_regime_gate_trail",
        "category": "REGIME",
        "rule": "IF GEX regime applied THEN WR improves 51.4% -> 63.9%, PF 2.13 -> 2.48",
        "probability": 0.639,
        "pf": 2.48,
        "sample_size": 0,
        "source": "MADX_STATE-3 Gamma doc consensus (4 docs), SPY 1m",
        "tier": "RESEARCH",
        "notes": "Neg-gamma = PUTs only. Trail x1.3 in neg-gamma / x0.7 in pos-gamma. Cross-doc consensus from 4 independent Gamma research docs."
    },
    {
        "name": "neg_gamma_puts_only",
        "category": "REGIME",
        "rule": "IF GEX regime is negative gamma THEN only take PUT entries, block CALLS",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 GEX regime gate, deployed as neg-gamma CALL ban",
        "tier": "PROVISIONAL",
        "notes": "Deployed in engine commit 55e924d. Block CALLs in neg gamma / PUTs in pos gamma."
    },
    {
        "name": "neg_gamma_sizeup",
        "category": "REGIME",
        "rule": "IF GEX regime is negative gamma AND PUT entry THEN size up 1.5x",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 FA neg-gamma sizeup test",
        "tier": "RESEARCH",
        "notes": "Tested as 'ultfa' variant. Added variance without payoff improvement (PF 0.96 vs PF 1.02 without). REJECTED in backtest but concept valid."
    },
    # =====================================================================
    # PUT vs CALL ASYMMETRY
    # =====================================================================
    {
        "name": "put_asymmetry_wr",
        "category": "PROPRIETARY",
        "rule": "IF direction is PUT THEN WR ~73.5% vs CALL ~62%",
        "probability": 0.735,
        "pf": 3.87,
        "sample_size": 186,
        "source": "MADX_STATE-3 #85 716 forensics + Gamma doc consensus",
        "tier": "PROVISIONAL",
        "notes": "PUT PF 3.87 vs CALL PF 1.07. Confirmed across 3 independent datasets. QuantPad: PUT +$1.32M vs CALL -$212K."
    },
    {
        "name": "put_only_oos_survivor",
        "category": "PROPRIETARY",
        "rule": "IF restrict to PUT-only entries THEN PF improves significantly",
        "probability": None,
        "pf": 1.27,
        "sample_size": 117,
        "source": "MADX_STATE-3 DIP_TURN AA19 P-only OOS",
        "tier": "RESEARCH",
        "notes": "AA19 (P-only) PF 1.27 OOS. Consistent with put asymmetry finding across all tests."
    },
    # =====================================================================
    # MICROSTRUCTURE
    # =====================================================================
    {
        "name": "spread_5pct_reject",
        "category": "MICROSTRUCTURE",
        "rule": "IF option spread > 5% of ask price THEN reject entry",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 Gamma doc feature importance delta -0.81",
        "tier": "PROVISIONAL",
        "notes": "Spread >5% reject has feature delta -0.81 (strongest negative). Premium >= $0.50 (delta +0.53) as hard gate."
    },
    {
        "name": "one_cent_spread_gate",
        "category": "MICROSTRUCTURE",
        "rule": "IF option spread > $0.01 THEN reject entry for 0DTE sniper",
        "probability": None,
        "pf": None,
        "sample_size": 142,
        "source": "MADX_STATE-3 F01 morning sniper 1c spread rule",
        "tier": "LOCKED",
        "notes": "F01 HGTFC IS PF 4.77 / OOS PF 3.61. 1-cent spread gate is core filter. Buy at Ask[t+1s], spread <= $0.01."
    },
    {
        "name": "premium_band_050_200",
        "category": "MICROSTRUCTURE",
        "rule": "IF option ask < $0.50 OR ask > $2.00 THEN reject entry",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 F01 morning sniper premium band",
        "tier": "PROVISIONAL",
        "notes": "Premium >= $0.50 (feature delta +0.53). Max ask $2.00 for 0DTE snipers. Law E1."
    },
    {
        "name": "losers_peak_earlier_than_winners",
        "category": "MICROSTRUCTURE",
        "rule": "IF option peaks within 15s of entry THEN likely loser (vs winner peak at 75s)",
        "probability": None,
        "pf": None,
        "sample_size": 186,
        "source": "MADX_STATE-3 #85 enrich716, peak timing discriminator",
        "tier": "PROVISIONAL",
        "notes": "THE discriminator: losers peak med 15s / winners 75s. At 120s losers negative, winners still positive. 2-min checkpoint is the tell."
    },
    # =====================================================================
    # SIZE / POSITION MANAGEMENT
    # =====================================================================
    {
        "name": "size_kills_large_positions",
        "category": "PROPRIETARY",
        "rule": "IF position size > ~66 contracts THEN WR drops significantly",
        "probability": None,
        "pf": None,
        "sample_size": 186,
        "source": "MADX_STATE-3 #85 716 forensics",
        "tier": "PROVISIONAL",
        "notes": "SIZE = killer factor: losers avg 131.4 contracts vs winners 66.4. qty<->win correlation -0.406."
    },
    # =====================================================================
    # STREAK / COOLDOWN
    # =====================================================================
    {
        "name": "two_min_cooldown_boost",
        "category": "STREAK",
        "rule": "IF 2-min cooldown between trades THEN PF improves significantly",
        "probability": None,
        "pf": 1.46,
        "sample_size": 107,
        "source": "MADX_STATE-3 Cooldown A/B test, VPS Alpaca PAPER",
        "tier": "PROVISIONAL",
        "notes": "n=107 real round-trips Jul 14-17. ALL PF 1.46 +$65,076 -> 2-min cooldown 95 trips +$104K. CONTRADICTION: state's final ruleset says 'no cooldowns.' Needs Josh decision."
    },
    {
        "name": "win_streak_continuation",
        "category": "STREAK",
        "rule": "IF 3 consecutive wins THEN next trade WR = 61%; IF 5+ consecutive wins THEN WR = 66%",
        "probability": 0.61,
        "pf": None,
        "sample_size": 5376,
        "source": "MADX_STATE-3 sigma-cooldown test on fleet data",
        "tier": "PROVISIONAL",
        "notes": "Josh's sigma-cooldown after big wins TESTED, REJECTED (loses $770k-$1.13M in every config). But the clustering stat is real: wins cluster. Fleet 5,376 trips."
    },
    {
        "name": "two_loss_direction_cooldown",
        "category": "STREAK",
        "rule": "IF 2 consecutive losses in same direction THEN block that direction for 15 min",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 PATCH-0720B CB_DIR_COOLDOWN",
        "tier": "PROVISIONAL",
        "notes": "Deployed live. Entry pacing only, not a full breaker. Confirmed working on 7/22 (-$10,900 day)."
    },
    # =====================================================================
    # CIRCUIT BREAKERS
    # =====================================================================
    {
        "name": "daily_loss_circuit_breaker",
        "category": "PROPRIETARY",
        "rule": "IF daily loss >= 8% of equity THEN halt all trading for rest of day",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 CB_DAILY_LOSS -8% breaker",
        "tier": "LOCKED",
        "notes": "Deployed live in V6.4. Tripped correctly multiple times (7/20, 7/22, 7/23). Gate-blocks all signals."
    },
    {
        "name": "giveback_pause_guard",
        "category": "PROPRIETARY",
        "rule": "IF day P&L drops to <= 50% of $10K+ intraday peak THEN pause entries 60 min",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 PATCH-0720B CB_GIVEBACK_PAUSE",
        "tier": "PROVISIONAL",
        "notes": "Arm at +$6K day gain; flatten+halt if giveback > min(35% of peak gain, $10K). 7/17: would have locked ~$10-15K vs $0."
    },
    {
        "name": "ratchet_tiered_sizing",
        "category": "PROPRIETARY",
        "rule": "IF day giveback to 85% of peak THEN qty x0.50 + score floor 68; IF to 65% THEN qty x0.25 + floor 75",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 RATCHET_ARM_USD=8000 tiered sizing",
        "tier": "PROVISIONAL",
        "notes": "T1 @ 85% peak -> half size. T2 @ 65% peak -> quarter size. T3 (arm $10K): flatten + block. Deployed live."
    },
    {
        "name": "four_loss_streak_pause",
        "category": "STREAK",
        "rule": "IF 4 consecutive losses THEN pause engine until reset",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 CB 4-loss streak breaker",
        "tier": "PROVISIONAL",
        "notes": "Deployed live. Confirmed working 7/22: paused engine 15:22->16:07 ET after 4 consecutive losses."
    },
    # =====================================================================
    # EXIT MECHANICS
    # =====================================================================
    {
        "name": "armed_ratchet_exit",
        "category": "PROPRIETARY",
        "rule": "IF MFE >= +12% THEN arm never-red floor at +8%",
        "probability": None,
        "pf": None,
        "sample_size": 142,
        "source": "MADX_STATE-3 F01 RATCHET_ARM_PCT=0.12 / RATCHET_FLOOR_PCT=0.08",
        "tier": "LOCKED",
        "notes": "Armed pure-pct ratchet + 5-condition PHYS_DERIV_STOP. No fixed -% price stops (R-001 LOCKED OFF FOREVER, CON-08)."
    },
    {
        "name": "breakfail_exit_40pct",
        "category": "PROPRIETARY",
        "rule": "IF peak retrace > 40% pre-TP1 THEN exit all",
        "probability": None,
        "pf": 1.35,
        "sample_size": 16,
        "source": "MADX_STATE-3 #66 716 tweak backtest BREAKFAIL-40",
        "tier": "RESEARCH",
        "notes": "BREAKFAIL-40 +$7,167 PF 1.35 (+$1,225 vs baseline PF 1.24). BF-25/30 REJECT (clips winners). Needs 28-day tape validation."
    },
    {
        "name": "two_point_five_pct_realizable",
        "category": "PROPRIETARY",
        "rule": "IF bid MFE >= +2.5% THEN sell-at-bid is realizable profit bar",
        "probability": None,
        "pf": None,
        "sample_size": 263,
        "source": "MADX_STATE-3 kill rule grid full week",
        "tier": "LOCKED",
        "notes": "2.5% realizable bar LOCKED (bid MFE >= +2.5%, sell-at-bid). Both rigs confirmed."
    },
    {
        "name": "exit_capture_65pct_of_peak",
        "category": "PROPRIETARY",
        "rule": "IF position has MFE > 5% THEN V64 exits capture avg 65% of peak",
        "probability": None,
        "pf": None,
        "sample_size": 18,
        "source": "MADX_STATE-3 V64 exit capture 7/20",
        "tier": "RESEARCH",
        "notes": "9/18 exited >= 85% of peak. Not a score-path/entry-quality problem."
    },
    {
        "name": "phys_deriv_stop_5cond",
        "category": "PROPRIETARY",
        "rule": "IF unarmed AND pnl <= -18% AND hold >= breathing_window AND 5 physics conditions met THEN exit",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 F-0131 PHYS_DERIV_STOP",
        "tier": "LOCKED",
        "notes": "5 conditions: (1) breathing window, (2) swing broken, (3) spot vel negative, (4) opt 1st+2nd deriv neg, (5) jerk<=0 or spread widened 2.2x. Zero fixed -% stops."
    },
    # =====================================================================
    # ENTRY GATES
    # =====================================================================
    {
        "name": "score_gate_60_minimum",
        "category": "PROPRIETARY",
        "rule": "IF entry score < 60 THEN reject entry",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 V6.4 engine gate >= 60",
        "tier": "PROVISIONAL",
        "notes": "Deployed in live V6.4. Score gate 60 is the minimum for entry. Higher gates (>=65, >=80) do NOT improve PF on degraded features."
    },
    {
        "name": "score_gate_inversion",
        "category": "PROPRIETARY",
        "rule": "IF score >= 80 THEN PF actually WORSE (0.46) vs baseline (0.78)",
        "probability": 0.40,
        "pf": 0.46,
        "sample_size": 1082,
        "source": "MADX_STATE-3 PPS v0.2 score study, 1082 scored trades",
        "tier": "LOCKED",
        "notes": "CRITICAL FINDING: No score gate improves PF. >=65 -> PF 0.73; >=80 -> PF 0.46. 35-50 band PF 1.05 INVERTS design. In degraded state (97% features dark), PPS CANNOT rank entries."
    },
    {
        "name": "entry_rate_filter",
        "category": "PROPRIETARY",
        "rule": "IF entry-rate filter ER >= 0.30 applied THEN PF improves 0.67 -> 0.69",
        "probability": None,
        "pf": 0.69,
        "sample_size": 500,
        "source": "MADX_STATE-3 ULT theta NBBO variants",
        "tier": "RESEARCH",
        "notes": "ER>=0.30 modest improvement. But ULT stack (ER+F3+blk+heat): 75 trades, 53.3% win, PF 1.02 from PF 0.67 base. DD cut 25x."
    },
    {
        "name": "f3_dirmatch_gate",
        "category": "PROPRIETARY",
        "rule": "IF F3 direction-match filter applied THEN PF improves 0.67 -> 0.81",
        "probability": None,
        "pf": 0.81,
        "sample_size": 500,
        "source": "MADX_STATE-3 ULT theta NBBO variants",
        "tier": "RESEARCH",
        "notes": "F3 dirmatch alone: PF 0.67->0.81. Part of ULT stack that reaches PF 1.02."
    },
    {
        "name": "midday_block_1000_1400",
        "category": "TIME_OF_DAY",
        "rule": "IF time is 10:00-14:00 ET AND midday block enabled THEN PF 0.67 -> 0.73",
        "probability": None,
        "pf": 0.73,
        "sample_size": 500,
        "source": "MADX_STATE-3 ULT theta NBBO variants blk 10:00-14:00",
        "tier": "RESEARCH",
        "notes": "Part of ULT stack. Blocking the middle of the day improves results modestly alone."
    },
    {
        "name": "ult_stack_combined_gates",
        "category": "PROPRIETARY",
        "rule": "IF ER>=0.30 AND F3_dirmatch AND midday_block AND heat_filter THEN PF 1.02 from 0.67 base",
        "probability": 0.533,
        "pf": 1.02,
        "sample_size": 75,
        "source": "MADX_STATE-3 ULT stack 20-day QQQ real NBBO",
        "tier": "RESEARCH",
        "notes": "75 trades, 53.3% win, PF 1.02, +$294, maxDD $4,181, 10/20 green days. DD cut 25x from base. Bleeder -> breakeven on REAL fills."
    },
    # =====================================================================
    # STRATEGY PERFORMANCE (V62 FLEET)
    # =====================================================================
    {
        "name": "v62_fleet_lifetime",
        "category": "PROPRIETARY",
        "rule": "IF running V62 fleet THEN lifetime PF and WR as measured",
        "probability": 0.38,
        "pf": None,
        "sample_size": 5376,
        "source": "MADX_STATE-3 fleet lifetime stats",
        "tier": "LOCKED",
        "notes": "Fleet lifetime P&L $1,065,823, 38.0% win, mean $198, sd $6,407/trade. 5,376 round-trips."
    },
    {
        "name": "v62_raw_base_losing",
        "category": "PROPRIETARY",
        "rule": "IF running V62 unfiltered 20-day QQQ THEN PF 0.67 (losing)",
        "probability": 0.414,
        "pf": 0.67,
        "sample_size": 500,
        "source": "MADX_STATE-3 ULT theta NBBO base",
        "tier": "LOCKED",
        "notes": "500 trades, 41.4% win, PF 0.67, -$104,727, maxDD $105K, 4 green days. This is the raw unfiltered baseline."
    },
    {
        "name": "v64_full_sim_losing",
        "category": "PROPRIETARY",
        "rule": "IF running V6.4 full simulation with circuit breakers THEN still losing",
        "probability": 0.418,
        "pf": None,
        "sample_size": 6020,
        "source": "MADX_STATE-3 V6.4 $110K+$250K dual bankroll sim",
        "tier": "LOCKED",
        "notes": "Both $110k and $250k accounts go to ~$4. WR 41.7-41.8% on 6,020 positions. Peak +94%/$213K before death. 479 days, 834,784-bar real SIP tape."
    },
    # =====================================================================
    # HTF ALIGNMENT
    # =====================================================================
    {
        "name": "swing_align_htf_gate",
        "category": "REGIME",
        "rule": "IF swing direction aligns with HTF trend THEN WR 50% and +$2,114/ct vs misaligned 37% and +$16/ct",
        "probability": 0.50,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 Gamma doc HTF alignment study",
        "tier": "RESEARCH",
        "notes": "Aligned 50%WR/+$2,114/ct vs 37%/+$16. ATR% top feature delta +0.61."
    },
    {
        "name": "atr_pct_top_entry_feature",
        "category": "VOLATILITY",
        "rule": "IF ATR% is high THEN entry quality improves (feature importance delta +0.61)",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 Gamma doc feature importance ranking",
        "tier": "RESEARCH",
        "notes": "ATR% top feature delta +0.61. Higher ATR = better entries. Strongest positive predictor."
    },
    # =====================================================================
    # SPECIFIC STRATEGY RESULTS
    # =====================================================================
    {
        "name": "orb_gex_regime_momentum",
        "category": "ORB",
        "rule": "IF ORB + GEX regime momentum strategy THEN PF 2.83 SPY / 2.31 QQQ",
        "probability": None,
        "pf": 2.83,
        "sample_size": 0,
        "source": "MADX_STATE-3 vault algo specs, 745 lines",
        "tier": "RESEARCH",
        "notes": "Feb 2024-Mar 2026, real FlashAlpha NBBO fills. HAS FA / missing UW connectors. SPY PF 2.83 / QQQ PF 2.31."
    },
    {
        "name": "harvest_ladder_master_qc",
        "category": "PROPRIETARY",
        "rule": "IF using harvest ladder exit THEN WR 66.7% PF 5.03",
        "probability": 0.667,
        "pf": 5.03,
        "sample_size": 51,
        "source": "MADX_STATE-3 MASTER_QC harvest ladder n=51",
        "tier": "RESEARCH",
        "notes": "n=51 is small. WR 66.7% PF 5.03. Harvest ladder = TP1(25%)/TP2(50%)/runner."
    },
    {
        "name": "dip_and_turn_entry",
        "category": "CANDLE_PATTERN",
        "rule": "IF GO bias flip + pullback within 0.10% of EMA9 THEN PF 1.52 IS / 1.14 OOS",
        "probability": 0.57,
        "pf": 1.52,
        "sample_size": 47,
        "source": "MADX_STATE-3 TRUMPGO sweep DIP|DD04",
        "tier": "RESEARCH",
        "notes": "IS: DIP|DD04 PF 1.52 +$9,300/47tr 57-60% win. OOS: DD04 FAILED (PF 0.84 curve-fit). TWO-WINDOW SURVIVOR: DIP|Z01B|EXHBOOST IS 1.31 / OOS 1.14 (117 tr, 54.7%)."
    },
    {
        "name": "exhboost_sizing",
        "category": "CANDLE_PATTERN",
        "rule": "IF exhaustion candle at entry THEN 1.5x size boost improves performance",
        "probability": None,
        "pf": None,
        "sample_size": 117,
        "source": "MADX_STATE-3 DIP_TURN EXHBOOST finding",
        "tier": "RESEARCH",
        "notes": "EXHBOOST beat FIX in EVERY config BOTH windows. Most robust finding in the DIP_TURN family."
    },
    # =====================================================================
    # STRONG_TREND REGIME
    # =====================================================================
    {
        "name": "strong_trend_up_calls_dead",
        "category": "REGIME",
        "rule": "IF regime is STRONG_TREND_UP AND buying calls THEN PF ~0.36",
        "probability": 0.33,
        "pf": 0.36,
        "sample_size": 3,
        "source": "MADX_STATE-3 brain exit-study + Josh's table",
        "tier": "RESEARCH",
        "notes": "ONLY entry-dead zone found: STRONG_TREND_UP median MFE +3.4%, 33% hit +10, n=3 tiny. Matches Josh's table (PF 0.36 buying calls into strength). Small n but convergent."
    },
    {
        "name": "mfe_available_exit_fixable",
        "category": "PROPRIETARY",
        "rule": "IF trade has large MFE but loses THEN exit-fixable not entry-dead",
        "probability": 0.84,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 brain exit study",
        "tier": "RESEARCH",
        "notes": "84% touch +8.88% and median MFE +60% -> EXIT-FIXABLE, not entry-dead. Blocking red buckets would throw away huge available MFE."
    },
    # =====================================================================
    # INFRASTRUCTURE / OPERATIONAL
    # =====================================================================
    {
        "name": "halt_flag_overstay",
        "category": "PROPRIETARY",
        "rule": "IF PATCH0717_HALT_FLAG fires THEN blocks all signals 5-6+ hours (intended vs stuck unresolved)",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 recurring issue Jul-Aug 2026",
        "tier": "RESEARCH",
        "notes": "UNRESOLVED through 8+ sessions. Blocks score-98 signals for 5+ hours on green days. Needs Josh eyeball on intended vs stuck behavior."
    },
    {
        "name": "broker_403_resync_loss",
        "category": "PROPRIETARY",
        "rule": "IF broker returns 403 on exit orders THEN expect ~$5,800 extra loss vs clean exit",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 #69 403-loop class",
        "tier": "RESEARCH",
        "notes": "403-blocked stop cost ~$5,800 extra vs clean -55% exit. TP ladder DID work on 693P/690P."
    },
    # =====================================================================
    # MOMENTUM / QUALITY SCORES
    # =====================================================================
    {
        "name": "momentum_tilt_q5_q1",
        "category": "REGIME",
        "rule": "IF momentum quintile Q5 THEN size 1.5x; IF Q1 THEN size 0.5x",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 MOMENTUM TILT test",
        "tier": "RESEARCH",
        "notes": "Survives walk-forward OOS. Holdout last 7 days: +$234,157 uplift. $5K FLAT LOSS CAP REJECTED (look-ahead)."
    },
    {
        "name": "tp1_rate_monotone_with_score",
        "category": "PROPRIETARY",
        "rule": "IF entry score increases THEN TP1 hit rate increases (62% lowest -> 90% highest)",
        "probability": None,
        "pf": None,
        "sample_size": 1082,
        "source": "MADX_STATE-3 PPS v0.2 score study",
        "tier": "RESEARCH",
        "notes": "TP1 rate monotone with score: 62% (lowest band) -> 90% (highest). Stop rate inverse: 28% -> 18%. BUT overall score gate does NOT improve PF."
    },
    # =====================================================================
    # FLEET ACCOUNT PERFORMANCE
    # =====================================================================
    {
        "name": "a6_a7_winner_population",
        "category": "PROPRIETARY",
        "rule": "IF account is A6 or A7 winner population THEN PF 4.98 / 7.07",
        "probability": None,
        "pf": 4.98,
        "sample_size": 894,
        "source": "MADX_STATE-3 vault-5 winner population proxy",
        "tier": "RESEARCH",
        "notes": "A6 PF 4.98, A7 PF 7.07 real Alpaca paper. 406/894 matched to feature_matrix. Control A1/A4/A5: 2,566 trades PF 0.84."
    },
    {
        "name": "top_10_trades_equal_all_pnl",
        "category": "PROPRIETARY",
        "rule": "IF examining winner population THEN top 10 trades account for ~100% of P&L",
        "probability": None,
        "pf": None,
        "sample_size": 406,
        "source": "MADX_STATE-3 A6/A7 winner analysis",
        "tier": "LOCKED",
        "notes": "Two monster runners (+22,589%, +9,210%) scored 47.6 — mid-pack. Top-10 trades ~= 100% of winner P&L. Runner capture is everything."
    },
    # =====================================================================
    # VALIDATION / SCORING FINDINGS
    # =====================================================================
    {
        "name": "pps_cannot_rank_degraded",
        "category": "PROPRIETARY",
        "rule": "IF feature coverage < 3% THEN PPS scoring provides no value",
        "probability": None,
        "pf": None,
        "sample_size": 3129,
        "source": "MADX_STATE-3 PPS v0.2 validation, 3129 trades",
        "tier": "LOCKED",
        "notes": "In degraded state (coverage 0.020-0.027, ~97% of 1,053 features dark), PPS v0.2 CANNOT rank or gate entries. AUC score<->realized +0.010 (p=0.85). Half-split flips sign."
    },
    {
        "name": "live_vs_backtest_exit_gap",
        "category": "PROPRIETARY",
        "rule": "IF comparing live vs replay signals THEN expect ~33.5% exit-model gap",
        "probability": None,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 SIM-A/SIM-B comparison",
        "tier": "RESEARCH",
        "notes": "SIM-A (harness signals) -$9.1K vs REAL +$43.6K. SIM-B (real signals locked) +$29.0K -> residual -33.5% exit-model gap."
    },
    # =====================================================================
    # HGTFC / ENGINE VARIANTS
    # =====================================================================
    {
        "name": "hgtfc_100_week_claim",
        "category": "PROPRIETARY",
        "rule": "IF HGTFC 718 algo with trade-print fills THEN claimed WR 80.4%",
        "probability": 0.804,
        "pf": None,
        "sample_size": 4723,
        "source": "MADX_STATE-3 HGTFCC_718_ALG0.py docstring",
        "tier": "EXTERNAL",
        "notes": "100-week ablation claim: 4,723 trades, FULL +$825,045, WR 80.4%, +$254/trade. 12/24 months negative. fills=trade prints NOT NBBO — claims NOT re-verified. PAPER-ONLY."
    },
    {
        "name": "hgtfc_tick3_proven_loser",
        "category": "PROPRIETARY",
        "rule": "IF running hgtfc_tick3 or tick4 THEN PF 0.75 LOSING",
        "probability": None,
        "pf": 0.75,
        "sample_size": 0,
        "source": "MADX_STATE-3 hgtfc_tick-3/4 backtest",
        "tier": "LOCKED",
        "notes": "hgtfc_tick3 PROVEN LOSER PF 0.75 -41.5%/92d. File itself not in repo."
    },
    {
        "name": "voldump_usi_claim",
        "category": "PROPRIETARY",
        "rule": "IF running VOLDUMP_USI algo THEN claimed 85.5% WR PF 7.56",
        "probability": 0.855,
        "pf": 7.56,
        "sample_size": 0,
        "source": "MADX_STATE-3 ALG0_HGTFC_VOLDUMP_USI_v1 claim",
        "tier": "EXTERNAL",
        "notes": "Claim 85.5% WR PF 7.56 vs 30.9%/0.99 baseline. UNVERIFIED by us."
    },
    # =====================================================================
    # JUNK (REFUTED)
    # =====================================================================
    {
        "name": "tqqq_sqqq_sleeves_dead",
        "category": "PROPRIETARY",
        "rule": "IF running TQQQ/SQQQ leveraged ETF sleeves THEN losing",
        "probability": None,
        "pf": 0.73,
        "sample_size": 0,
        "source": "MADX_STATE-3 JUNK refuted, real NBBO",
        "tier": "LOCKED",
        "notes": "TQQQ PF 0.73 / SQQQ PF 0.58 -$116K. 12-Parallel PF 0.90/0.71 (1 acct 100% DD). SPY params on QQQ 1m 15.4% WR -$12.8K. REFUTED."
    },
    {
        "name": "spy_params_on_qqq_dead",
        "category": "PROPRIETARY",
        "rule": "IF applying SPY-calibrated params to QQQ 1m THEN WR 15.4%",
        "probability": 0.154,
        "pf": None,
        "sample_size": 0,
        "source": "MADX_STATE-3 JUNK refuted",
        "tier": "LOCKED",
        "notes": "SPY params on QQQ 1m = 15.4% WR -$12.8K. Instrument-specific calibration mandatory."
    },
]

if __name__ == "__main__":
    print(f"MADX_STATE-3 extracted priors: {len(MADX_EXTRACTED_PRIORS)}")
    tiers = {}
    cats = {}
    for p in MADX_EXTRACTED_PRIORS:
        tiers[p['tier']] = tiers.get(p['tier'], 0) + 1
        cats[p['category']] = cats.get(p['category'], 0) + 1
    print(f"\nBy tier: {dict(sorted(tiers.items()))}")
    print(f"\nBy category: {dict(sorted(cats.items()))}")
    pf_priors = [p for p in MADX_EXTRACTED_PRIORS if p['pf'] is not None]
    print(f"\nWith PF values: {len(pf_priors)}")
    for p in sorted(pf_priors, key=lambda x: x['pf'], reverse=True)[:10]:
        print(f"  {p['name']}: PF {p['pf']} (n={p['sample_size']}, tier={p['tier']})")
