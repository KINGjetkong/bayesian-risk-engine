"""
╔══════════════════════════════════════════════════════════════════╗
║         BAYESIAN RISK ENGINE — FastAPI Backend v1.0              ║
║         Master Architect Protocol | MiniMax Terminal             ║
║         Stack: FastAPI + PyMC + ADVI Variational Inference       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import uvicorn
import pymc as pm
import numpy as np
import pytensor.tensor as pt
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import logging
import json
import os
from datetime import datetime
from tradeodds_client import TradeOddsClient

# ─── CONFIGURATION ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("RiskEngine")

app = FastAPI(
    title="Bayesian Risk Engine",
    version="1.0.0",
    description="Probabilistic modeling of rare events using PyMC Hierarchical Bayesian inference with ADVI."
)

# Allow CORS for local frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── LAYER 1: THE DATA LAKE ────────────────────────────────────────
# Hardcoded base rates. In production: queries DuckDB/Postgres.
DATA_LAKE = {
    "lightning_strike": {
        "base_rate": 1e-6,
        "uncertainty": 0.5,
        "source": "NOAA Climatology",
        "description": "Annual probability of being struck by lightning (US average)",
        "category": "natural"
    },
    "shark_attack": {
        "base_rate": 1e-7,
        "uncertainty": 1.0,
        "source": "Intl Shark Attack File",
        "description": "Annual probability of unprovoked shark attack",
        "category": "natural"
    },
    "car_crash_injury": {
        "base_rate": 0.007,
        "uncertainty": 0.2,
        "source": "NHTSA",
        "description": "Annual probability of car crash injury (US avg ~1 in 140)",
        "category": "transport"
    },
    "startup_failure": {
        "base_rate": 0.90,
        "uncertainty": 0.1,
        "source": "BLS / VC Stats",
        "description": "Probability of startup failure within 10 years",
        "category": "business"
    },
    "audit_risk": {
        "base_rate": 0.004,
        "uncertainty": 0.3,
        "source": "IRS Data Book",
        "description": "Annual IRS audit probability (~0.4% of returns)",
        "category": "financial"
    },
    "trade_loss_streak": {
        "base_rate": 0.15,
        "uncertainty": 0.25,
        "source": "Quantitative Finance Research",
        "description": "Probability of 5+ consecutive losing trades (avg 50% win rate)",
        "category": "trading"
    },
    "market_crash_20pct": {
        "base_rate": 0.12,
        "uncertainty": 0.35,
        "source": "S&P 500 Historical Data",
        "description": "Annual probability of a >20% market drawdown",
        "category": "trading"
    },
    "data_breach": {
        "base_rate": 0.28,
        "uncertainty": 0.2,
        "source": "IBM Cost of Data Breach Report 2023",
        "description": "Annual probability of a data breach for a mid-size company",
        "category": "business"
    },
    "plane_crash": {
        "base_rate": 2e-7,
        "uncertainty": 0.8,
        "source": "IATA Safety Report",
        "description": "Per-flight probability of fatal accident (commercial aviation)",
        "category": "transport"
    },
    "heart_attack_40s": {
        "base_rate": 0.005,
        "uncertainty": 0.3,
        "source": "AHA Heart Disease Statistics",
        "description": "Annual probability of heart attack for a 40-year-old male",
        "category": "health"
    }
}

# ─── LAYER 2: DATA MODELS ─────────────────────────────────────────

class Multiplier(BaseModel):
    name: str
    value: float = Field(..., description="Multiplier factor (e.g., 2.0 = double risk)")
    uncertainty: float = Field(0.2, description="Standard deviation in log-space (0.1=tight, 1.0=loose)")

class ScenarioRequest(BaseModel):
    event_type: str = Field(..., description="Key from DATA_LAKE or custom event name")
    custom_base_rate: Optional[float] = None
    exposure: float = Field(1.0, description="Exposure units (e.g., years, trips, attempts)")
    multipliers: List[Multiplier] = []
    scenario_name: Optional[str] = None

class RiskResponse(BaseModel):
    posterior_odds: str
    posterior_probability: float
    confidence_interval_95: List[float]
    micromorts: float
    risk_level: str
    logic_chain: List[str]
    status: str
    computed_at: str

class BatchRequest(BaseModel):
    scenarios: List[ScenarioRequest]

# ─── LAYER 3: BAYESIAN KERNEL (PyMC) ──────────────────────────────

def run_bayesian_inference(base_rate: float, base_sigma: float, exposure: float, multipliers: List[Multiplier]):
    """
    Constructs a Hierarchical Poisson Model on the fly.
    Uses ADVI (Variational Inference) for sub-second results.
    
    Architecture:
    - Base Rate Prior: LogNormal (ensures positivity, captures epistemic uncertainty)
    - Multipliers: Each modeled as LogNormal (expert elicitation is noisy)
    - Combination: Multiplicative in real space = additive in log space
    - Likelihood: Poisson process → P(event>0) = 1 - exp(-λ·t)
    """
    with pm.Model() as model:
        # 1. Base Rate Prior (LogNormal to ensure positivity)
        mu_log = np.log(base_rate)
        base_rate_dist = pm.LogNormal("base_rate", mu=mu_log, sigma=base_sigma)

        # 2. Apply Multipliers in log-space
        log_sum = pt.log(base_rate_dist)
        explanation_steps = [
            f"Prior: Base Rate ({base_rate:.2e}) | σ={base_sigma} | LogNormal distribution"
        ]

        for m in multipliers:
            m_dist = pm.LogNormal(f"mult_{m.name}", mu=np.log(m.value), sigma=m.uncertainty)
            log_sum += pt.log(m_dist)
            explanation_steps.append(
                f"Multiplier '{m.name}': {m.value}x (σ={m.uncertainty}) → log-additive"
            )

        # 3. Effective Rate
        lambda_effective = pm.Deterministic("lambda_effective", pt.exp(log_sum))

        # 4. Poisson Exposure Model
        p_event = pm.Deterministic("p_event", 1 - pt.exp(-lambda_effective * exposure))

        # 5. Inference
        # ADVI is faster than MCMC sampling for this convex problem
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            approx = pm.fit(n=10000, method='advi', progressbar=False)
            trace = approx.sample(1000)

    return trace, explanation_steps


def classify_risk_level(prob: float) -> str:
    """Map probability to human-readable risk tier."""
    if prob < 1e-6:
        return "NEGLIGIBLE"
    elif prob < 1e-4:
        return "VERY LOW"
    elif prob < 0.01:
        return "LOW"
    elif prob < 0.10:
        return "MODERATE"
    elif prob < 0.40:
        return "HIGH"
    elif prob < 0.70:
        return "VERY HIGH"
    else:
        return "CRITICAL"


# ─── LAYER 4: API ENDPOINTS ───────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Bayesian Risk Engine v1.0 | GET /datalake | POST /assess | POST /batch"}

@app.get("/datalake")
def get_datalake():
    """Return all available preset events with metadata."""
    return DATA_LAKE

@app.get("/datalake/{event_type}")
def get_event(event_type: str):
    """Return a single event from the data lake."""
    if event_type not in DATA_LAKE:
        raise HTTPException(status_code=404, detail=f"Event '{event_type}' not in Data Lake.")
    return DATA_LAKE[event_type]

@app.post("/assess", response_model=RiskResponse)
def assess_risk(scenario: ScenarioRequest):
    """
    Core inference endpoint. Runs PyMC ADVI on the scenario and returns
    posterior probability, 95% CI, micromorts, and a full logic chain.
    """
    # 1. Resolve Base Rate
    source = "Unknown"
    base_sigma = 0.5

    # Check for TradeOdds dynamic prior if it's a trading event
    if scenario.event_type in ["SPY_0DTE", "QQQ_0DTE", "trade_loss_streak", "market_crash_20pct"]:
        symbol = "SPY" if "SPY" in scenario.event_type else "QQQ"
        client = TradeOddsClient()
        dynamic_prior = client.get_market_prior(symbol)
        if dynamic_prior:
            base_rate = dynamic_prior
            base_sigma = 0.15 # Higher confidence in dynamic prior
            source = f"TradeOdds Pro (Dynamic {symbol} Prior)"
        else:
            # Fallback to Data Lake
            data = DATA_LAKE.get(scenario.event_type, DATA_LAKE.get("trade_loss_streak"))
            base_rate = data["base_rate"]
            base_sigma = data["uncertainty"]
            source = data["source"] + " (Fallback)"
    elif scenario.custom_base_rate:
        base_rate = scenario.custom_base_rate
        base_sigma = 0.5
        source = "User Input (Custom)"
    elif scenario.event_type in DATA_LAKE:
        data = DATA_LAKE[scenario.event_type]
        base_rate = data["base_rate"]
        base_sigma = data["uncertainty"]
        source = data["source"]
    else:
        raise HTTPException(
            status_code=404,
            detail=f"Event '{scenario.event_type}' not found. Provide custom_base_rate."
        )

    logger.info(
        f"[ASSESS] {scenario.event_type} | Base: {base_rate:.2e} | "
        f"Exposure: {scenario.exposure} | Multipliers: {len(scenario.multipliers)}"
    )

    # 2. Run Bayesian Inference
    try:
        trace, logic_chain = run_bayesian_inference(
            base_rate, base_sigma, scenario.exposure, scenario.multipliers
        )
    except Exception as e:
        logger.error(f"[INFERENCE FAILED] {e}")
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

    # 3. Extract Posterior Statistics
    posterior_samples = trace.posterior["p_event"].values.flatten()
    mean_prob = float(np.mean(posterior_samples))
    ci_low = float(np.percentile(posterior_samples, 2.5))
    ci_high = float(np.percentile(posterior_samples, 97.5))

    # 4. Format Output
    odds_denom = int(1 / mean_prob) if mean_prob > 1e-12 else 0
    odds_str = f"1 in {odds_denom:,}" if odds_denom > 0 else "Near Certainty"
    micromorts = mean_prob * 1_000_000
    risk_level = classify_risk_level(mean_prob)

    logic_chain.append(f"Source: {source}")
    logic_chain.append(f"Exposure: {scenario.exposure} unit(s)")
    logic_chain.append(f"Posterior Mean: {mean_prob:.4e}")
    logic_chain.append(f"Result: {odds_str} | Risk Level: {risk_level}")

    return {
        "posterior_odds": odds_str,
        "posterior_probability": mean_prob,
        "confidence_interval_95": [ci_low, ci_high],
        "micromorts": round(micromorts, 4),
        "risk_level": risk_level,
        "logic_chain": logic_chain,
        "status": "computed",
        "computed_at": datetime.utcnow().isoformat() + "Z"
    }

@app.post("/batch")
def batch_assess(batch: BatchRequest):
    """Run multiple scenarios in sequence and return all results."""
    results = []
    for scenario in batch.scenarios:
        try:
            result = assess_risk(scenario)
            results.append({"scenario": scenario.event_type, "result": result})
        except Exception as e:
            results.append({"scenario": scenario.event_type, "error": str(e)})
    return {"batch_results": results, "count": len(results)}

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "data_lake_size": len(DATA_LAKE),
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

# ─── SERVE STATIC FRONTEND ────────────────────────────────────────
# Serve dashboard.html from the same directory
@app.get("/dashboard")
def serve_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path)
    raise HTTPException(status_code=404, detail="Dashboard not found")


@app.get("/trading")
def serve_trading():
    trading_path = os.path.join(os.path.dirname(__file__), "trading.html")
    if os.path.exists(trading_path):
        return FileResponse(trading_path)
    raise HTTPException(status_code=404, detail="Trading app not found")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
