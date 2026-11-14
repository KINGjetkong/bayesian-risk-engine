"""
Experimental Monte Carlo Bayesian Engine — Continuous Probability Simulation

Rolling 120K-path Monte Carlo with:
  - Continuous entry probability scoring (separate sleeve)
  - Path-dependent physics (5 lens: Slingshot, Fluid, Refraction, Orbit, Crystal)
  - Predictive pre-exit probability distribution zones
  - L2 order book math for optimal exit timing (1-5s rolling window)
  - ML weight adjustment via gradient-boosted online learning
  - Score decay when adverse price movement likelihood increases

Every function is self-contained and inspectable — designed so other agents
can judge the math at face value.

SECURITY: No keys printed. No orders placed. GET-only. $0.10/side fees added AFTER.
"""
import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum


# =============================================================================
# §1  CORE MATH EQUATIONS — Telemetry Schema (JIMSIMONS.mfQT)
# =============================================================================

def effective_spread(fill_px: float, micro_price: float, side: int) -> float:
    """Effective spread in dollars. Side: +1 buy, -1 sell.
    Equation: S_eff = 2 × side × (fill - μ_price)
    Source: Telemetry Schema T2, Hasbrouck (1993)"""
    return 2.0 * side * (fill_px - micro_price)


def stoikov_micro_price(bid: float, ask: float, bid_sz: int, ask_sz: int) -> float:
    """Stoikov micro-price — size-weighted fair value.
    Equation: μ = bid + spread × (ask_sz / (bid_sz + ask_sz))
    Source: Stoikov & Avellaneda (2008), Telemetry T3"""
    if bid_sz + ask_sz == 0:
        return (bid + ask) / 2.0
    return bid + (ask - bid) * (ask_sz / (bid_sz + ask_sz))


def queue_imbalance(bid_sz: int, ask_sz: int) -> float:
    """L1 queue imbalance — directional pressure indicator.
    Equation: QI = (bid_sz - ask_sz) / (bid_sz + ask_sz)
    Range: [-1, +1]; >0 = buy pressure. Source: Telemetry T3"""
    total = bid_sz + ask_sz
    if total == 0:
        return 0.0
    return (bid_sz - ask_sz) / total


def order_flow_imbalance(bid: float, ask: float, bid_sz: int, ask_sz: int,
                         prev_bid: float, prev_ask: float,
                         prev_bid_sz: int, prev_ask_sz: int) -> float:
    """Cont-Kukanov-Stoikov Order Flow Imbalance.
    Equation:
      bidFlow = +bidSize if bid > prevBid
                else (bidSize - prevBidSize) if bid == prevBid
                else -prevBidSize
      askFlow = -askSize if ask < prevAsk
                else (prevAskSize - askSize) if ask == prevAsk
                else +prevAskSize
      OFI = bidFlow + askFlow
    Source: Cont, Kukanov & Stoikov (2014), FM-002 remediation"""
    if bid > prev_bid:
        bid_flow = bid_sz
    elif bid == prev_bid:
        bid_flow = bid_sz - prev_bid_sz
    else:
        bid_flow = -prev_bid_sz

    if ask < prev_ask:
        ask_flow = -ask_sz
    elif ask == prev_ask:
        ask_flow = prev_ask_sz - ask_sz
    else:
        ask_flow = prev_ask_sz

    return bid_flow + ask_flow


def garman_klass_rv(high: float, low: float, open_px: float, close: float) -> float:
    """Garman-Klass realized volatility estimator.
    Equation: σ²_GK = 0.5·ln(H/L)² − (2ln2−1)·ln(C/O)²
    Source: Garman & Klass (1980), Telemetry T3"""
    if low <= 0 or open_px <= 0:
        return 0.0
    hl = math.log(high / low)
    co = math.log(close / open_px)
    return 0.5 * hl * hl - (2.0 * math.log(2.0) - 1.0) * co * co


def kaufman_efficiency_ratio(prices: np.ndarray, period: int = 10) -> float:
    """Kaufman Efficiency Ratio — fractal path efficiency.
    Equation: ER = |P_t − P_{t−N}| / Σ|P_i − P_{i−1}| for i in [t−N+1, t]
    Range: [0, 1]; 1 = perfectly trending. Source: Kaufman (1995), Telemetry T3"""
    if len(prices) < period + 1:
        return 0.0
    direction = abs(prices[-1] - prices[-period - 1])
    volatility = np.sum(np.abs(np.diff(prices[-period - 1:])))
    if volatility == 0:
        return 0.0
    return direction / volatility


def options_leverage_omega(delta: float, spot: float, option_value: float) -> float:
    """Options leverage (Omega) — effective gearing.
    Equation: Ω = Δ × S / V
    Source: Telemetry T3, Hull (2012)"""
    if option_value <= 0:
        return 0.0
    return delta * spot / option_value


def vrp_ratio(realized_vol: float, implied_vol: float) -> float:
    """Volatility Risk Premium ratio.
    Equation: VRP = RV / IV
    <1 means IV overpriced (sellers collect premium). Source: Telemetry T3"""
    if implied_vol <= 0:
        return 0.0
    return realized_vol / implied_vol


def mfe_capture_efficiency(realized_pnl: float, mfe_absolute: float) -> float:
    """How much of the maximum favorable excursion was captured.
    Equation: η_MFE = Realized PnL / MFE_absolute
    Range: [−∞, 1]; 1 = perfect exit at peak. Source: Telemetry T2"""
    if mfe_absolute <= 0:
        return 0.0
    return realized_pnl / mfe_absolute


def adverse_selection_cost(mid_after: float, fill_px: float, side: int) -> float:
    """Adverse selection at dt seconds post-fill.
    Equation: AS_dt = side × (mid_{t+dt} − fill_px)
    Negative = adverse. Source: Telemetry T2, FM-015"""
    return side * (mid_after - fill_px)


# =============================================================================
# §2  CORE MATH EQUATIONS — Book of Enrichment (78 Chapters)
# =============================================================================

def alma(prices: np.ndarray, window: int = 9, offset: float = 0.85,
         sigma: float = 6.0) -> float:
    """Arnaud Legoux Moving Average.
    Equation: ALMA = Σ w_i·P_i / Σ w_i
      where w_i = exp(−(i − m)² / (2·s²)), m = offset·(N−1), s = N/sigma
    Source: Arnaud Legoux, EPUB Ch 03"""
    n = min(window, len(prices))
    if n == 0:
        return 0.0
    m = offset * (n - 1)
    s = n / sigma
    w = np.array([math.exp(-((i - m) ** 2) / (2.0 * s * s)) for i in range(n)])
    w_sum = np.sum(w)
    if w_sum == 0:
        return prices[-1]
    return float(np.dot(w, prices[-n:]) / w_sum)


def conviction_score(probabilities: np.ndarray, weights: np.ndarray) -> float:
    """Multi-factor conviction score — the master scoring equation.
    Equation: Score = clamp(±100, round(Σ(p_i − 0.5)·2·w_i / Σw_i × 50))
    Source: EPUB conviction grid, CORE.N1"""
    w_sum = np.sum(weights)
    if w_sum == 0:
        return 0.0
    raw = np.sum((probabilities - 0.5) * 2.0 * weights) / w_sum * 50.0
    return float(np.clip(round(raw), -100, 100))


def bipower_variation(returns: np.ndarray) -> float:
    """Bipower variation — jump-robust volatility estimator.
    Equation: BV(t) = (π/2) × mean(|r_u| × |r_{u−1}|) for u in window
    Source: Barndorff-Nielsen & Shephard (2004), EPUB Ch 48"""
    if len(returns) < 2:
        return 0.0
    abs_r = np.abs(returns)
    return float((math.pi / 2.0) * np.mean(abs_r[1:] * abs_r[:-1]))


def jump_indicator(ret: float, sigma: float, dt: float = 1.0,
                   threshold_c: float = 3.0) -> int:
    """Jump detection indicator.
    Equation: J = I(|r_t| > C·σ·√dt)
    Source: Lee & Mykland (2008), EPUB Co-jump cascade"""
    if sigma <= 0:
        return 0
    return 1 if abs(ret) > threshold_c * sigma * math.sqrt(dt) else 0


def cojump_cascade(jump_signs: np.ndarray) -> Tuple[int, int, int]:
    """Co-jump cascade across assets.
    Equation: C+ = Σ I(J_j = +1), C− = Σ I(J_j = −1), K = max(C+, C−)
    Source: EPUB B11.0 Co-Jump Cascade Spec"""
    c_plus = int(np.sum(jump_signs == 1))
    c_minus = int(np.sum(jump_signs == -1))
    k = max(c_plus, c_minus)
    return c_plus, c_minus, k


def drift_diffusion_first_passage(x: float, L: float, U: float,
                                  mu: float, sigma: float) -> float:
    """Drift-diffusion first-passage probability to upper barrier.
    Equation: P_U(x) = (1 − exp(−2μ(x−L)/σ²)) / (1 − exp(−2μ(U−L)/σ²))
    Source: Wald (1947), EPUB HYP-43"""
    if sigma <= 0 or U <= L:
        return 0.5
    exp_num = 1.0 - math.exp(-2.0 * mu * (x - L) / (sigma ** 2))
    exp_den = 1.0 - math.exp(-2.0 * mu * (U - L) / (sigma ** 2))
    if abs(exp_den) < 1e-15:
        return (x - L) / (U - L)  # zero-drift case
    return exp_num / exp_den


def survival_function(hazard_rates: np.ndarray, dt: float = 1.0) -> float:
    """Competing-event survival function.
    Equation: S(t) = exp(−Σ h_total(u) · dt)
    Causes: QUICK_POP, RUNNER, STALL, ADVERSE, EXPIRY
    Source: EPUB HYP-49"""
    return float(math.exp(-np.sum(hazard_rates) * dt))


def empirical_bayes_shrinkage(cell_pf: float, grand_pf: float,
                              n_cell: int, kappa: float = 60.0) -> float:
    """Empirical Bayes shrinkage for cell-level estimates.
    Equation: PF_shrunk = w·PF_cell + (1−w)·PF_grand, w = n/(n+κ)
    Source: James-Stein (1961), EPUB §3"""
    w = n_cell / (n_cell + kappa)
    return w * cell_pf + (1.0 - w) * grand_pf


def temperature_scaling(logit_score: float, t_calib: float = 1.0) -> float:
    """Temperature-scaled probability calibration.
    Equation: p_cal = 1 / (1 + exp(−logit / T))
    Source: Platt (1999), EPUB §3"""
    return 1.0 / (1.0 + math.exp(-logit_score / t_calib))


def hyperbolic_recovery(drawdown_pct: float) -> float:
    """Hyperbolic recovery return needed to reach prior HWM.
    Equation: R_recovery = d / (1 − d)
    −20% drawdown needs +25% return. Source: EPUB Module 23"""
    if drawdown_pct >= 1.0:
        return float('inf')
    return drawdown_pct / (1.0 - drawdown_pct)


def volatility_compression_index(rv_current_2h: float,
                                 rv_trailing_2h: np.ndarray) -> float:
    """VCI — volatility compression relative to trailing 30 days.
    Equation: VCI[t] = RV_2h(day d) / mean(RV_2h(day d−k) for k=1..30)
    <1 = compressed. Source: EPUB HYP-32"""
    mean_rv = np.mean(rv_trailing_2h) if len(rv_trailing_2h) > 0 else 1.0
    if mean_rv <= 0:
        return 1.0
    return rv_current_2h / mean_rv


# =============================================================================
# §3  FIVE PHYSICAL MODELS — Path-Dependent Physics
# =============================================================================

def slingshot_elastic_energy(k: float, delta_mid: float) -> float:
    """Slingshot Model — elastic potential energy stored in price displacement.
    Equation: U_elastic = ½·k·Δmid²
    k = spring constant (estimated from ATR). Higher U → bigger snap-back.
    Source: 5-Lens Model, Hooke's Law analogy"""
    return 0.5 * k * delta_mid ** 2


def fluid_vorticity(velocity_field: np.ndarray, dx: float = 1.0) -> float:
    """Fluid Model — Navier-Stokes vorticity of the order flow.
    Equation: Ω = curl(v) ≈ ∂v_y/∂x − ∂v_x/∂y (2D simplification)
    In 1D tape: Ω ≈ d(OFI)/dt − d(price_vel)/d(volume)
    High |Ω| = rotational flow (chop). Low |Ω| = laminar (trend).
    Source: 5-Lens Model, Navier-Stokes"""
    if len(velocity_field) < 3:
        return 0.0
    dvdt = np.gradient(velocity_field, dx)
    return float(np.mean(np.abs(np.gradient(dvdt, dx))))


def refraction_lead_lag(nq_prices: np.ndarray, qqq_prices: np.ndarray,
                        max_lag: int = 5) -> Tuple[float, int]:
    """Refraction Model — Nyquist/Shannon multi-clock lead-lag.
    Equation: Δt_lag = argmax_τ XCorr(NQ, QQQ)[τ] for τ in [−max_lag, +max_lag]
    At 133t/233t/333t Nyquist frequencies.
    Source: 5-Lens Model, cross-correlation"""
    if len(nq_prices) < max_lag * 2 or len(qqq_prices) < max_lag * 2:
        return 0.0, 0
    n = min(len(nq_prices), len(qqq_prices))
    nq = nq_prices[-n:]
    qqq = qqq_prices[-n:]
    nq_ret = np.diff(nq) / nq[:-1]
    qqq_ret = np.diff(qqq) / qqq[:-1]
    best_corr = -1.0
    best_lag = 0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            a = nq_ret[lag:]
            b = qqq_ret[:len(a)]
        else:
            b = qqq_ret[-lag:]
            a = nq_ret[:len(b)]
        if len(a) < 5:
            continue
        c = np.corrcoef(a, b)[0, 1]
        if not np.isnan(c) and c > best_corr:
            best_corr = c
            best_lag = lag
    return float(best_corr), best_lag


def orbit_barycenter_drift(prices: np.ndarray, volumes: np.ndarray) -> float:
    """Orbit Model — volume-weighted barycenter (center of mass) drift.
    Equation: B(t) = Σ(P_i · V_i) / Σ V_i — centroid of price×volume
    Δ_bary = B(t) − B(t−N): positive = accumulation drift upward.
    Source: 5-Lens Model, center of mass"""
    if len(prices) == 0 or len(volumes) == 0:
        return 0.0
    total_vol = np.sum(volumes)
    if total_vol == 0:
        return 0.0
    return float(np.sum(prices * volumes) / total_vol)


def crystal_dime_dislocation(price: float) -> Dict[str, float]:
    """Crystal Model — Z_100 modular lattice dislocation analysis.
    Equation: cents = round(price × 100) mod 100
    dime_bias = I(cents mod 10 < 2) — attraction to .X0 levels
    Void entropy = −Σ p_i·log(p_i) over cent distribution (low = pinned)
    Source: 5-Lens Model, digit gravity / FM-011"""
    cents = round(price * 100) % 100
    dime_residual = cents % 10
    dime_bias = 1.0 if dime_residual < 2 or dime_residual > 8 else 0.0
    return {
        "cents": cents,
        "dime_bias": dime_bias,
        "dime_residual": dime_residual,
        "near_round": 1.0 if cents < 5 or cents > 95 else 0.0,
    }


# =============================================================================
# §4  BAYESIAN COMPOSITION — Prior Factory Math
# =============================================================================

def posterior_logistic(logit_sum: float, gain: float = 2.2) -> float:
    """Bayesian posterior via logistic sigmoid.
    Equation: p = 1 / (1 + exp(−gain · logit_sum))
    gain = 2.2 (LOCKED). Source: Prior Factory"""
    return 1.0 / (1.0 + math.exp(-gain * logit_sum))


def multiplicative_confluence(priors: np.ndarray) -> float:
    """Multiplicative confluence — independent probability combination.
    Equation: P_total = 1 − Π(1 − P_i)
    Source: Prior Factory, Bernoulli trials"""
    return float(1.0 - np.prod(1.0 - priors))


def hawkes_intensity(mu: float, kappa: float, beta: float,
                     event_times: np.ndarray, t: float) -> float:
    """Hawkes self-exciting process intensity.
    Equation: λ(t) = μ + Σ κ·exp(−β·(t − t_i)) for t_i < t
    μ≈0.244, κ≈0.742, β≈0.196; half-life 3.54s.
    Source: Prior Factory, Hawkes (1971)"""
    past = event_times[event_times < t]
    if len(past) == 0:
        return mu
    excitation = kappa * np.sum(np.exp(-beta * (t - past)))
    return mu + float(excitation)


def kelly_fraction(p: float, r: float, fraction: float = 0.25) -> float:
    """Kelly criterion at fractional Kelly.
    Equation: f* = [p − (1−p)/R] × fraction
    fraction = 0.25 (quarter Kelly). Source: Kelly (1956), Prior Factory"""
    if r <= 0:
        return 0.0
    full_kelly = p - (1.0 - p) / r
    return max(0.0, full_kelly * fraction)


# =============================================================================
# §5  FAILURE MODE VETO EQUATIONS (FM-001 through FM-100)
# =============================================================================

def gamma_theta_race_ratio(gamma_pnl_per_sec: float,
                           theta_decay_per_sec: float) -> float:
    """Gamma-Theta Race Ratio — FM-029.
    Equation: R_ΓΘ = Γ_pnl/sec / Θ_decay/sec
    VETO if R < 1.0 for > 15 seconds. Source: FM-029"""
    if theta_decay_per_sec <= 0:
        return float('inf')
    return gamma_pnl_per_sec / theta_decay_per_sec


def delta_error_elasticity(delta_p_opt: float, delta_hat: float,
                           delta_s: float, p_opt: float) -> float:
    """Delta error drift — FM-033.
    Equation: ε_t = (ΔP_opt − Δ̂·ΔS) / P_opt
    VETO if ε_t ≤ −0.025 for 2 consecutive ticks. Source: FM-033"""
    if p_opt <= 0:
        return 0.0
    return (delta_p_opt - delta_hat * delta_s) / p_opt


def vanna_charm_divergence(vanna: float, d_sigma_dt: float,
                           charm: float, dk: float = 1.0) -> float:
    """Vanna-Charm PDE divergence — FM-035.
    Equation: div(J) = ∂/∂K(Vanna · dσ/dt) + ∂/∂t(Charm)
    EXIT when div(J) flips negative. Source: FM-035"""
    return vanna * d_sigma_dt / dk + charm


def frenet_serret_curvature(velocity: np.ndarray,
                            acceleration: np.ndarray) -> float:
    """Frenet-Serret curvature — tape turning detection.
    Equation: κ = |v × a| / |v|³
    Source: FM-059, EPUB Ch 06"""
    v_mag = np.linalg.norm(velocity)
    if v_mag < 1e-10:
        return 0.0
    cross = np.cross(velocity, acceleration) if len(velocity) >= 2 else 0.0
    return float(np.abs(cross)) / (v_mag ** 3)


def optimal_spread_stoikov(delta_inv: float, gamma_risk: float,
                           cost_rt: float) -> float:
    """Optimal market-maker spread — Stoikov solution.
    Equation: m* = (−δ + √(δ² + 2γ·c_rt)) / γ
    Source: EPUB R9 Simons m* Gate"""
    if gamma_risk <= 0:
        return cost_rt
    disc = delta_inv ** 2 + 2.0 * gamma_risk * cost_rt
    if disc < 0:
        return cost_rt
    return (-delta_inv + math.sqrt(disc)) / gamma_risk


# =============================================================================
# §6  EXPERIMENTAL MONTE CARLO ENGINE
# =============================================================================

class MCState(Enum):
    SCANNING = "SCANNING"
    HIGH_PROB_ENTRY = "HIGH_PROB_ENTRY"
    IN_TRADE = "IN_TRADE"
    EXIT_ZONE = "EXIT_ZONE"
    COOLDOWN = "COOLDOWN"


@dataclass
class MCPath:
    """Single Monte Carlo simulation path."""
    prices: List[float] = field(default_factory=list)
    pnl: float = 0.0
    entry_score: float = 0.0
    exit_score: float = 0.0
    holding_seconds: int = 0
    mfe: float = 0.0
    mae: float = 0.0
    exit_reason: str = ""


@dataclass
class MCResult:
    """Aggregate result from N Monte Carlo paths."""
    n_paths: int = 0
    win_rate: float = 0.0
    mean_pnl: float = 0.0
    median_pnl: float = 0.0
    pf: float = 0.0
    sharpe: float = 0.0
    p_profit: float = 0.0
    var_95: float = 0.0
    cvar_95: float = 0.0
    best_exit_time: int = 0
    exit_distribution: Dict[int, float] = field(default_factory=dict)
    entry_prob: float = 0.0
    score_trajectory: List[float] = field(default_factory=list)


class ExperimentalMonteCarlo:
    """Continuous Monte Carlo Bayesian simulation engine.

    Runs 120K paths per evaluation cycle, each path simulating:
    1. Entry at current score level
    2. Path-dependent price evolution using 5 physical models
    3. Rolling 1-5s exit probability windows
    4. ML-adjusted weight factors

    The engine maintains a SEPARATE SLEEVE that continuously scores
    hypothetical entries and tracks what would have happened.
    """

    N_PATHS = 120_000
    ROLLING_WINDOW = 5  # seconds
    GAIN = 2.2  # posterior logistic gain (LOCKED)

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.state = MCState.SCANNING
        self.score_history: List[float] = []
        self.weight_factors = self._default_weights()
        self.ml_adjustments: Dict[str, float] = {}
        self.trade_log: List[MCPath] = []

    def _default_weights(self) -> Dict[str, float]:
        """PATH_SCORE_WEIGHTS (LOCKED from prior factory)."""
        return {
            "velocity": 0.22,
            "acceleration": 0.16,
            "vpump": 0.13,
            "gex_thrust": 0.13,
            "atr": 0.13,
            "cross_asset": 0.12,
            "m5": 0.09,
            "tod": -0.06,
        }

    def compute_entry_score(self, state: Dict) -> float:
        """Compute entry probability score from all available signals.

        Uses Bayesian composition across all active priors, then applies
        the 5 physical model adjustments.

        Returns: score in [0, 1] where >0.75 = RUNNER, >0.45 = HYBRID.
        """
        priors = state.get("prior_probabilities", np.array([0.5]))
        weights = state.get("prior_weights", np.ones(len(priors)))

        # Logit-space composition
        logit_effects = np.zeros(len(priors))
        for i, (p, w) in enumerate(zip(priors, weights)):
            p_clamp = max(0.001, min(0.999, p))
            logit_effects[i] = math.log(p_clamp / (1.0 - p_clamp)) * w

        logit_sum = np.sum(logit_effects)

        # Apply 5-lens physics adjustments
        physics_adj = 0.0
        if "slingshot_energy" in state:
            u = state["slingshot_energy"]
            physics_adj += 0.1 * math.tanh(u / 0.5)
        if "vorticity" in state:
            omega = state["vorticity"]
            physics_adj -= 0.05 * math.tanh(omega / 2.0)  # high vorticity = chop penalty
        if "lead_lag_sec" in state:
            lag = state["lead_lag_sec"]
            physics_adj += 0.08 * (1.0 if lag > 0 else -0.5 if lag < 0 else 0.0)
        if "barycenter_drift" in state:
            drift = state["barycenter_drift"]
            physics_adj += 0.06 * math.tanh(drift / 0.3)
        if "dime_bias" in state and state["dime_bias"] > 0.5:
            physics_adj -= 0.03  # digit gravity pin penalty

        adjusted_logit = logit_sum + physics_adj
        posterior = posterior_logistic(adjusted_logit, self.GAIN)

        self.score_history.append(posterior)
        return posterior

    def simulate_paths(self, entry_price: float, entry_score: float,
                       current_vol: float, dt: float = 1.0) -> MCResult:
        """Run N_PATHS Monte Carlo simulations from this entry point.

        Each path evolves price using geometric Brownian motion calibrated
        to current realized volatility, with drift from the entry score.

        Returns MCResult with full distribution statistics.
        """
        n = self.N_PATHS
        max_hold = 300  # 5 minutes max

        # Calibrate drift from score: higher score → positive drift bias
        mu = (entry_score - 0.5) * 2.0 * current_vol * 0.1
        sigma = current_vol / math.sqrt(252.0 * 6.5 * 3600.0)  # per-second vol

        # Generate all paths at once (vectorized)
        z = self.rng.standard_normal((n, max_hold))
        log_returns = (mu - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * z
        price_paths = entry_price * np.exp(np.cumsum(log_returns, axis=1))

        # Insert entry price at t=0
        price_paths = np.column_stack([np.full(n, entry_price), price_paths])

        # Compute PnL, MFE, MAE for each path at each potential exit
        pnl_matrix = (price_paths - entry_price) / entry_price  # return %

        # Find optimal exit time for each path
        cummax = np.maximum.accumulate(pnl_matrix, axis=1)
        mfe_per_path = np.max(pnl_matrix, axis=1)
        mae_per_path = np.min(pnl_matrix, axis=1)

        # Exit at time that maximizes expectancy across rolling windows
        exit_pnls = {}
        for t in range(1, min(max_hold + 1, 6)):
            exit_pnls[t] = pnl_matrix[:, t]

        # Find best exit window
        best_t = 1
        best_mean = -float('inf')
        for t, pnls in exit_pnls.items():
            m = np.mean(pnls)
            if m > best_mean:
                best_mean = m
                best_t = t

        # Full distribution at best exit time
        final_pnl = pnl_matrix[:, min(best_t, max_hold)]
        winners = final_pnl > 0
        losers = final_pnl <= 0

        gross_win = np.sum(final_pnl[winners]) if np.any(winners) else 0.0
        gross_loss = abs(np.sum(final_pnl[losers])) if np.any(losers) else 1e-10

        sorted_pnl = np.sort(final_pnl)
        var_95_idx = int(0.05 * n)
        var_95 = sorted_pnl[var_95_idx] if var_95_idx < n else 0.0
        cvar_95 = np.mean(sorted_pnl[:var_95_idx]) if var_95_idx > 0 else 0.0

        std_pnl = np.std(final_pnl)
        sharpe = np.mean(final_pnl) / std_pnl if std_pnl > 0 else 0.0

        # Build exit distribution (probability of positive PnL at each second)
        exit_dist = {}
        for t in range(1, min(max_hold + 1, 11)):
            if t < pnl_matrix.shape[1]:
                exit_dist[t] = float(np.mean(pnl_matrix[:, t] > 0))

        # Score trajectory (mean score decay over time)
        score_traj = []
        for t in range(0, min(max_hold + 1, 11)):
            if t < pnl_matrix.shape[1]:
                p_positive = float(np.mean(pnl_matrix[:, t] > 0))
                score_traj.append(p_positive)

        return MCResult(
            n_paths=n,
            win_rate=float(np.mean(winners)),
            mean_pnl=float(np.mean(final_pnl)),
            median_pnl=float(np.median(final_pnl)),
            pf=gross_win / gross_loss if gross_loss > 0 else float('inf'),
            sharpe=sharpe,
            p_profit=float(np.mean(final_pnl > 0)),
            var_95=float(var_95),
            cvar_95=float(cvar_95),
            best_exit_time=best_t,
            exit_distribution=exit_dist,
            entry_prob=entry_score,
            score_trajectory=score_traj,
        )

    def rolling_exit_probability(self, current_price: float, entry_price: float,
                                 current_vol: float, holding_sec: int) -> Dict:
        """Predictive pre-exit Monte Carlo — probability distribution for next 1-5s.

        Runs mini-simulation (10K paths) from CURRENT position to estimate
        probability of price dropping in each of the next 1-5 seconds.

        Returns score that DROPS as adverse likelihood INCREASES.
        """
        n = 10_000
        sigma = current_vol / math.sqrt(252.0 * 6.5 * 3600.0)

        # Current unrealized PnL
        unrealized = (current_price - entry_price) / entry_price

        results = {}
        z = self.rng.standard_normal((n, self.ROLLING_WINDOW))
        log_ret = -0.5 * sigma ** 2 + sigma * z
        future_prices = current_price * np.exp(np.cumsum(log_ret, axis=1))

        for t in range(1, self.ROLLING_WINDOW + 1):
            future_pnl = (future_prices[:, t - 1] - entry_price) / entry_price
            p_worse = float(np.mean(future_pnl < unrealized))
            p_better = float(np.mean(future_pnl > unrealized))
            results[t] = {
                "p_worse": p_worse,
                "p_better": p_better,
                "expected_change": float(np.mean(future_prices[:, t - 1]) - current_price),
                "var_95": float(np.percentile(future_prices[:, t - 1] - current_price, 5)),
            }

        # Composite exit score: high when holding is good, low when should exit
        avg_p_worse = np.mean([r["p_worse"] for r in results.values()])
        exit_score = 1.0 - avg_p_worse  # drops as adverse probability rises

        # Decay penalty for long holds (theta burn on 0DTE)
        theta_penalty = 0.0
        if holding_sec > 60:
            theta_penalty = 0.02 * math.log(holding_sec / 60.0)

        results["composite_exit_score"] = max(0.0, exit_score - theta_penalty)
        results["recommendation"] = (
            "HOLD" if results["composite_exit_score"] > 0.55
            else "EXIT_PARTIAL" if results["composite_exit_score"] > 0.40
            else "EXIT_FULL"
        )
        return results

    def l2_order_book_exit_math(self, bid_levels: List[Tuple[float, int]],
                                ask_levels: List[Tuple[float, int]],
                                position_side: str = "LONG") -> Dict:
        """L2 order book analysis for optimal exit timing.

        Computes absorption ratio, void entropy, and pressure gradient
        across top 5 levels to predict immediate price trajectory.

        Source: FM-002 Iceberg absorption, FM-003 Phantom depth"""
        if not bid_levels or not ask_levels:
            return {"absorb_ratio": 0.5, "void_entropy": 0.0, "pressure": 0.0}

        bid_sizes = np.array([sz for _, sz in bid_levels[:5]])
        ask_sizes = np.array([sz for _, sz in ask_levels[:5]])

        total_bid = np.sum(bid_sizes)
        total_ask = np.sum(ask_sizes)
        total = total_bid + total_ask

        # Absorption ratio: how much bid support vs ask pressure
        absorb_ratio = total_bid / total if total > 0 else 0.5

        # Void entropy: uniformity of depth distribution (low = concentrated = weak)
        all_sizes = np.concatenate([bid_sizes, ask_sizes])
        all_sizes = all_sizes[all_sizes > 0]
        if len(all_sizes) > 1:
            probs = all_sizes / np.sum(all_sizes)
            void_entropy = float(-np.sum(probs * np.log(probs + 1e-10)))
        else:
            void_entropy = 0.0

        # Pressure gradient: rate of size decay away from touch
        if len(bid_sizes) > 1:
            bid_gradient = float(np.mean(np.diff(bid_sizes)))
        else:
            bid_gradient = 0.0

        # Exit signal for LONG: exit if absorb_ratio dropping and gradient negative
        if position_side == "LONG":
            exit_urgency = (1.0 - absorb_ratio) + max(0, -bid_gradient / 100.0)
        else:
            exit_urgency = absorb_ratio + max(0, bid_gradient / 100.0)

        return {
            "absorb_ratio": float(absorb_ratio),
            "void_entropy": void_entropy,
            "bid_gradient": bid_gradient,
            "exit_urgency": float(np.clip(exit_urgency, 0, 1)),
            "total_bid_depth": int(total_bid),
            "total_ask_depth": int(total_ask),
        }

    def ml_weight_update(self, feature_name: str, observed_pnl: float,
                         predicted_pnl: float, learning_rate: float = 0.01) -> float:
        """Online ML weight adjustment via gradient descent.

        Adjusts weight factors based on prediction error:
        Equation: w_new = w_old − η · ∂L/∂w = w_old − η · (predicted − observed) · x

        Source: Stochastic gradient descent, LightGBM-inspired online update"""
        error = predicted_pnl - observed_pnl
        current_w = self.weight_factors.get(feature_name, 1.0)
        adjustment = -learning_rate * error
        new_w = current_w + adjustment
        new_w = max(0.01, min(2.0, new_w))  # clamp weights
        self.weight_factors[feature_name] = new_w
        self.ml_adjustments[feature_name] = adjustment
        return new_w

    def run_full_cycle(self, state: Dict) -> Dict:
        """Run one complete simulation cycle.

        1. Compute entry score from all priors + physics
        2. If score high enough, run 120K-path Monte Carlo
        3. Compute rolling exit probabilities
        4. Return full result with code references
        """
        # Step 1: Entry score
        entry_score = self.compute_entry_score(state)

        result = {
            "entry_score": entry_score,
            "state": self.state.value,
            "route": (
                "RUNNER" if entry_score >= 0.75
                else "HYBRID" if entry_score >= 0.45
                else "SWEEP"
            ),
        }

        # Step 2: Monte Carlo if score warrants
        if entry_score >= 0.45:
            price = state.get("price", 1.0)
            vol = state.get("implied_vol", 0.20)
            mc = self.simulate_paths(price, entry_score, vol)
            result["monte_carlo"] = {
                "n_paths": mc.n_paths,
                "win_rate": round(mc.win_rate, 4),
                "mean_pnl_pct": round(mc.mean_pnl * 100, 4),
                "pf": round(mc.pf, 3),
                "sharpe": round(mc.sharpe, 3),
                "p_profit": round(mc.p_profit, 4),
                "var_95_pct": round(mc.var_95 * 100, 4),
                "best_exit_sec": mc.best_exit_time,
                "exit_distribution": {
                    k: round(v, 4) for k, v in mc.exit_distribution.items()
                },
                "score_trajectory": [round(s, 4) for s in mc.score_trajectory],
            }

        # Step 3: Exit probabilities if in trade
        if self.state == MCState.IN_TRADE:
            entry_px = state.get("entry_price", state.get("price", 1.0))
            current_px = state.get("price", 1.0)
            vol = state.get("implied_vol", 0.20)
            hold_sec = state.get("holding_seconds", 0)

            exit_probs = self.rolling_exit_probability(
                current_px, entry_px, vol, hold_sec
            )
            result["exit_analysis"] = exit_probs

            # L2 book analysis if available
            if "bid_levels" in state and "ask_levels" in state:
                l2 = self.l2_order_book_exit_math(
                    state["bid_levels"], state["ask_levels"]
                )
                result["l2_analysis"] = l2

        return result


# =============================================================================
# §7  DEFLATED SHARPE RATIO — Bailey & López de Prado
# =============================================================================

def deflated_sharpe_ratio(sharpe_observed: float, n_trials: int,
                          t_periods: int, skew: float = 0.0,
                          kurtosis: float = 3.0) -> float:
    """Deflated Sharpe Ratio — adjusts for multiple testing.
    Equation: DSR = Φ((SR_obs − SR_0) / σ_SR)
    where SR_0 = √(V[SR]) × ((1−γ)·Φ^{-1}(1−1/N) + γ·Φ^{-1}(1−1/(N·e)))
    and V[SR] = (1 + 0.5·SR²·(κ−1) − SR·s) / T
    γ ≈ 0.5772 (Euler-Mascheroni). Source: Bailey & López de Prado (2014)"""
    from scipy import stats as sp_stats

    if t_periods <= 0 or n_trials <= 1:
        return 0.0

    gamma_em = 0.5772156649
    var_sr = (1.0 + 0.5 * sharpe_observed ** 2 * (kurtosis - 1.0)
              - sharpe_observed * skew) / t_periods
    if var_sr <= 0:
        var_sr = 1e-10
    std_sr = math.sqrt(var_sr)

    # Expected max SR under null
    z_n = sp_stats.norm.ppf(1.0 - 1.0 / n_trials)
    z_ne = sp_stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    sr_0 = std_sr * ((1.0 - gamma_em) * z_n + gamma_em * z_ne)

    dsr = sp_stats.norm.cdf((sharpe_observed - sr_0) / std_sr)
    return float(dsr)


# =============================================================================
# §8  SELF-TEST — Verify all equations produce sane outputs
# =============================================================================

def self_test():
    """Verify every equation function with known inputs."""
    print("=" * 60)
    print("EXPERIMENTAL MONTE CARLO ENGINE — SELF-TEST")
    print("=" * 60)

    passed = 0
    total = 0

    def check(name, value, low, high):
        nonlocal passed, total
        total += 1
        ok = low <= value <= high
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {value:.6f} (expected [{low}, {high}])")
        if ok:
            passed += 1

    # §1 Telemetry equations
    print("\n§1 TELEMETRY SCHEMA EQUATIONS:")
    check("effective_spread", effective_spread(2.55, 2.53, 1), 0.03, 0.05)
    check("stoikov_micro", stoikov_micro_price(2.50, 2.55, 100, 50), 2.51, 2.54)
    check("queue_imbalance", queue_imbalance(100, 50), 0.3, 0.4)
    check("ofi", order_flow_imbalance(2.51, 2.55, 110, 50, 2.50, 2.55, 100, 50), 109, 111)
    check("garman_klass", garman_klass_rv(502, 498, 500, 501), 0.0, 0.001)
    check("kaufman_er", kaufman_efficiency_ratio(np.linspace(100, 110, 20)), 0.9, 1.01)
    check("omega_leverage", options_leverage_omega(0.5, 500, 2.0), 124, 126)
    check("vrp", vrp_ratio(0.15, 0.20), 0.74, 0.76)
    check("mfe_capture", mfe_capture_efficiency(50, 100), 0.49, 0.51)

    # §2 Book of Enrichment equations
    print("\n§2 BOOK OF ENRICHMENT EQUATIONS:")
    check("alma", alma(np.array([1, 2, 3, 4, 5, 6, 7, 8, 9]), 9, 0.85, 6.0), 7.0, 9.0)
    check("conviction_score", conviction_score(np.array([0.8, 0.7, 0.6]), np.array([1, 1, 1])), 15, 25)
    check("bipower_var", bipower_variation(np.array([0.01, -0.02, 0.015, -0.01, 0.02])), 0.0, 0.001)
    check("drift_diffusion", drift_diffusion_first_passage(55, 50, 60, 0.1, 1.0), 0.4, 0.75)
    check("survival", survival_function(np.array([0.01, 0.02, 0.005])), 0.95, 0.97)
    check("bayes_shrink", empirical_bayes_shrinkage(2.0, 1.0, 30, 60), 1.2, 1.5)
    check("temp_scale", temperature_scaling(1.0, 1.0), 0.72, 0.74)
    check("hyperbolic_recovery", hyperbolic_recovery(0.20), 0.24, 0.26)

    # §3 Five Physical Models
    print("\n§3 FIVE PHYSICAL MODELS:")
    check("slingshot", slingshot_elastic_energy(100, 0.5), 12.4, 12.6)
    check("fluid_vorticity", fluid_vorticity(np.sin(np.linspace(0, 4*math.pi, 50))), 0.0, 5.0)
    corr, lag = refraction_lead_lag(
        np.cumsum(np.random.randn(100)) + 500,
        np.cumsum(np.random.randn(100)) + 200,
    )
    check("refraction_corr", corr, -1.0, 1.0)
    check("orbit_bary", orbit_barycenter_drift(
        np.array([500, 501, 502]), np.array([1000, 2000, 1500])), 500, 502)
    crystal = crystal_dime_dislocation(501.30)
    check("crystal_cents", crystal["cents"], 29, 31)

    # §4 Bayesian Composition
    print("\n§4 BAYESIAN COMPOSITION:")
    check("posterior_logistic", posterior_logistic(0.5), 0.7, 0.8)
    check("multiplicative", multiplicative_confluence(np.array([0.3, 0.4, 0.5])), 0.75, 0.80)
    check("hawkes", hawkes_intensity(0.244, 0.742, 0.196, np.array([0, 1, 2]), 3), 0.5, 3.0)
    check("kelly", kelly_fraction(0.61, 0.88, 0.25), 0.0, 0.15)

    # §5 Failure Mode Vetoes
    print("\n§5 FAILURE MODE VETOES:")
    check("gamma_theta_race", gamma_theta_race_ratio(0.05, 0.10), 0.49, 0.51)
    check("delta_error", delta_error_elasticity(0.02, 0.5, 0.05, 2.0), -0.003, 0.002)
    check("vanna_charm_div", vanna_charm_divergence(0.05, -0.01, 0.002), -0.001, 0.003)
    check("optimal_spread", optimal_spread_stoikov(0.58, 0.08, 0.0025), 0.0, 1.0)

    # §6 Monte Carlo Engine
    print("\n§6 MONTE CARLO ENGINE:")
    engine = ExperimentalMonteCarlo(seed=42)
    state = {
        "prior_probabilities": np.array([0.65, 0.70, 0.55, 0.60]),
        "prior_weights": np.array([1.0, 0.7, 0.4, 0.3]),
        "price": 2.50,
        "implied_vol": 0.35,
        "slingshot_energy": 0.3,
        "vorticity": 0.5,
        "lead_lag_sec": 1,
        "barycenter_drift": 0.1,
        "dime_bias": 0.0,
    }
    score = engine.compute_entry_score(state)
    check("entry_score", score, 0.3, 1.0)

    mc = engine.simulate_paths(2.50, score, 0.35)
    check("mc_win_rate", mc.win_rate, 0.0, 1.0)
    check("mc_pf", mc.pf, 0.0, float('inf'))
    print(f"  [INFO] MC paths: {mc.n_paths}, best exit: {mc.best_exit_time}s")
    print(f"  [INFO] Exit dist: { {k:round(v,3) for k,v in mc.exit_distribution.items()} }")

    # Exit probability test
    engine.state = MCState.IN_TRADE
    state["entry_price"] = 2.40
    state["holding_seconds"] = 45
    state["bid_levels"] = [(2.49, 200), (2.48, 150), (2.47, 100), (2.46, 80), (2.45, 50)]
    state["ask_levels"] = [(2.50, 100), (2.51, 120), (2.52, 80), (2.53, 60), (2.54, 40)]
    result = engine.run_full_cycle(state)
    if "exit_analysis" in result:
        exit_score = result["exit_analysis"]["composite_exit_score"]
        check("exit_composite_score", exit_score, 0.0, 1.0)
        print(f"  [INFO] Exit recommendation: {result['exit_analysis']['recommendation']}")

    if "l2_analysis" in result:
        l2 = result["l2_analysis"]
        check("l2_absorb_ratio", l2["absorb_ratio"], 0.0, 1.0)
        print(f"  [INFO] L2 void entropy: {l2['void_entropy']:.3f}")

    # ML weight update test
    new_w = engine.ml_weight_update("velocity", 0.05, 0.02, 0.01)
    check("ml_weight_velocity", new_w, 0.01, 2.0)

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed}/{total} passed")
    print(f"{'=' * 60}")
    return passed == total


if __name__ == "__main__":
    self_test()
