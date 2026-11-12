#!/usr/bin/env python3 -I
"""MadTrades V6 — Bayesian Engine API (Version 5)

FastAPI server that exposes all 4 engine versions as API endpoints
with a real-time comparison dashboard.

Endpoints:
  GET  /                     → Engine status + docs
  GET  /health               → Health check
  POST /v1/assess            → V1 deterministic engine
  POST /v2/assess            → V2 Monte Carlo engine
  POST /v3/assess            → V3 factorized shrinkage engine
  POST /v4/assess            → V4 ensemble (all engines)
  POST /compare              → Side-by-side comparison
  GET  /nodes                → List all 200 probability nodes
  GET  /nodes/{domain}       → Nodes by domain
  GET  /node/{node_id}       → Single node detail
  GET  /domains              → Domain summary
  GET  /dashboard            → Comparison dashboard HTML
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from bayesian_engine_v1 import (
    BayesianProbabilityEngine,
    MarketContext,
    Regime,
    GexRegime,
    Domain,
)
from bayesian_engine_v2_montecarlo import BayesianEngineV2
from bayesian_engine_v3_factorized import BayesianEngineV3
from bayesian_engine_v4_ensemble import BayesianEngineV4Ensemble


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class MarketInput(BaseModel):
    timestamp: Optional[float] = None
    price: float = 0.0
    vwap: float = 0.0
    ema9: float = 0.0
    ema20: float = 0.0
    ema144: float = 0.0
    rsi_14: float = 50.0
    atr_14: float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    volume_ratio: float = 1.0
    cvd_slope: float = 0.0
    vpin: float = 0.0
    obi: float = 0.0
    spread_bps: float = 0.0
    option_delta: float = 0.0
    option_gamma: float = 0.0
    option_theta: float = 0.0
    option_iv: float = 0.0
    premium: float = 0.0
    premium_velocity: float = 0.0
    premium_acceleration: float = 0.0
    premium_in_band: bool = False
    gex: float = 0.0
    dex: float = 0.0
    put_call_ratio: float = 1.0
    zero_dte_volume_ratio: float = 0.0
    regime: str = "unknown"
    gex_regime: str = "unknown"
    fractal_state: str = "unknown"
    vix: float = 15.0
    es_price: float = 0.0
    nq_price: float = 0.0
    es_nq_basis: float = 0.0
    futures_spot_corr: float = 0.99
    dxy_5m_corr: float = 0.0
    hyg_below_vwap: bool = False
    xlp_xlu_outperform: bool = False
    vix_call_spike: bool = False
    mag7_all_declining: bool = False
    rsp_diverging: bool = False
    minutes_since_open: int = 0
    is_power_hour: bool = False
    is_lunch: bool = False
    is_first_15: bool = False
    is_last_15: bool = False
    is_event_day: bool = False
    ib_high: float = 0.0
    ib_low: float = 0.0
    prev_day_poc: float = 0.0
    opening_gap_pct: float = 0.0
    dte: int = 0
    bid_depth_l1: float = 0.0
    ask_depth_l1: float = 0.0
    day_high: float = 0.0
    day_low: float = 0.0
    velocity_5s: float = 0.0
    velocity_30s: float = 0.0
    block_trade_detected: bool = False
    order_cancel_ratio: float = 0.0

    def to_market_context(self) -> MarketContext:
        regime_map = {r.value: r for r in Regime}
        gex_map = {g.value: g for g in GexRegime}
        return MarketContext(
            timestamp=self.timestamp or time.time(),
            price=self.price,
            vwap=self.vwap,
            ema9=self.ema9,
            ema20=self.ema20,
            ema144=self.ema144,
            rsi_14=self.rsi_14,
            atr_14=self.atr_14,
            bb_upper=self.bb_upper,
            bb_lower=self.bb_lower,
            volume_ratio=self.volume_ratio,
            cvd_slope=self.cvd_slope,
            vpin=self.vpin,
            obi=self.obi,
            spread_bps=self.spread_bps,
            option_delta=self.option_delta,
            option_gamma=self.option_gamma,
            option_theta=self.option_theta,
            option_iv=self.option_iv,
            premium=self.premium,
            premium_velocity=self.premium_velocity,
            premium_acceleration=self.premium_acceleration,
            premium_in_band=self.premium_in_band,
            gex=self.gex,
            dex=self.dex,
            put_call_ratio=self.put_call_ratio,
            zero_dte_volume_ratio=self.zero_dte_volume_ratio,
            regime=regime_map.get(self.regime, Regime.UNKNOWN),
            gex_regime=gex_map.get(self.gex_regime, GexRegime.UNKNOWN),
            fractal_state=self.fractal_state,
            vix=self.vix,
            es_price=self.es_price,
            nq_price=self.nq_price,
            es_nq_basis=self.es_nq_basis,
            futures_spot_corr=self.futures_spot_corr,
            dxy_5m_corr=self.dxy_5m_corr,
            hyg_below_vwap=self.hyg_below_vwap,
            xlp_xlu_outperform=self.xlp_xlu_outperform,
            vix_call_spike=self.vix_call_spike,
            mag7_all_declining=self.mag7_all_declining,
            rsp_diverging=self.rsp_diverging,
            minutes_since_open=self.minutes_since_open,
            is_power_hour=self.is_power_hour,
            is_lunch=self.is_lunch,
            is_first_15=self.is_first_15,
            is_last_15=self.is_last_15,
            is_event_day=self.is_event_day,
            ib_high=self.ib_high,
            ib_low=self.ib_low,
            prev_day_poc=self.prev_day_poc,
            opening_gap_pct=self.opening_gap_pct,
            dte=self.dte,
            bid_depth_l1=self.bid_depth_l1,
            ask_depth_l1=self.ask_depth_l1,
            day_high=self.day_high,
            day_low=self.day_low,
            velocity_5s=self.velocity_5s,
            velocity_30s=self.velocity_30s,
            block_trade_detected=self.block_trade_detected,
            order_cancel_ratio=self.order_cancel_ratio,
        )


# ---------------------------------------------------------------------------
# App + singleton engines
# ---------------------------------------------------------------------------

app = FastAPI(
    title="MadTrades V6 Bayesian Probability Engine",
    version="5.0",
    description="200-node continuous rolling Bayesian probability engine "
                "with 4 collapse strategies",
)

v1_engine = BayesianProbabilityEngine()
v2_engine = BayesianEngineV2(n_simulations=300)
v3_engine = BayesianEngineV3()
v4_engine = BayesianEngineV4Ensemble(mc_simulations=200)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "name": "MadTrades V6 Bayesian Probability Engine",
        "version": "5.0",
        "total_nodes": len(v1_engine.nodes),
        "domains": len(v1_engine.workers),
        "engines": {
            "v1": "Deterministic logit-space collapse",
            "v2": "Monte Carlo regime prediction + attractor field",
            "v3": "Factorized partial-pooling shrinkage",
            "v4": "Ensemble (stacks v1-v3 with adaptive weighting)",
        },
        "endpoints": [
            "POST /v1/assess", "POST /v2/assess",
            "POST /v3/assess", "POST /v4/assess",
            "POST /compare", "GET /nodes", "GET /domains",
            "GET /dashboard",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "nodes": len(v1_engine.nodes), "engines": 4}


@app.post("/v1/assess")
def assess_v1(data: MarketInput):
    ctx = data.to_market_context()
    output = v1_engine.update(ctx)
    return {
        "version": "v1_deterministic",
        "composite_posterior": round(output.composite_posterior, 6),
        "domain_posteriors": {
            k: round(v, 4) for k, v in output.domain_posteriors.items()
        },
        "confidence_tier": output.confidence_tier,
        "kelly_fraction": round(output.kelly_fraction, 4),
        "ev": round(output.ev, 4),
        "sizing_multiplier": round(output.sizing_multiplier, 4),
        "live_nodes": output.live_node_count,
        "total_nodes": output.total_node_count,
        "top_factors": output.top_factors[:5],
        "veto_active": output.veto_active,
        "veto_reasons": output.veto_reasons,
    }


@app.post("/v2/assess")
def assess_v2(data: MarketInput):
    ctx = data.to_market_context()
    return v2_engine.update(ctx)


@app.post("/v3/assess")
def assess_v3(data: MarketInput):
    ctx = data.to_market_context()
    return v3_engine.update(ctx)


@app.post("/v4/assess")
def assess_v4(data: MarketInput):
    ctx = data.to_market_context()
    return v4_engine.update(ctx)


@app.post("/compare")
def compare(data: MarketInput):
    ctx = data.to_market_context()

    v1_out = v1_engine.update(ctx)
    v2_out = v2_engine.update(ctx)
    v3_out = v3_engine.update(ctx)
    v4_out = v4_engine.update(ctx)

    return {
        "timestamp": time.time(),
        "engines": {
            "v1_deterministic": {
                "composite": round(v1_out.composite_posterior, 6),
                "confidence": v1_out.confidence_tier,
                "live_nodes": v1_out.live_node_count,
            },
            "v2_montecarlo": {
                "composite": v2_out["composite_posterior"],
                "confidence": v2_out["confidence_tier"],
                "regime_forecast": v2_out.get("regime_forecast", {}),
            },
            "v3_factorized": {
                "composite": v3_out["composite_posterior"],
                "confidence": v3_out["confidence_tier"],
                "factor_effects": v3_out.get("factor_effects", {}),
            },
            "v4_ensemble": {
                "composite": v4_out["composite_posterior"],
                "confidence": v4_out["confidence_tier"],
                "agreement": v4_out.get("agreement", 0),
                "consensus": v4_out.get("consensus", ""),
                "weights": v4_out.get("engine_weights", {}),
            },
        },
        "total_nodes": len(v1_engine.nodes),
        "veto_active": v1_out.veto_active,
        "veto_reasons": v1_out.veto_reasons,
    }


@app.get("/nodes")
def list_nodes(domain: Optional[str] = None):
    nodes = []
    for node in v1_engine.nodes.values():
        if domain and node.domain.value != domain:
            continue
        nodes.append({
            "id": node.id,
            "domain": node.domain.value,
            "description": node.description,
            "base_rate": node.base_rate,
            "prior_update": node.prior_update,
            "priority": node.priority,
            "source": node.source,
            "verdict": node.verdict,
            "role": node.strategy_role,
            "is_live": node._is_live,
            "posterior": round(node._current_posterior, 4),
            "observations": node._observation_count,
        })
    return {"count": len(nodes), "nodes": nodes}


@app.get("/node/{node_id}")
def get_node(node_id: str):
    node = v1_engine.nodes.get(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    return {
        "id": node.id,
        "domain": node.domain.value,
        "description": node.description,
        "base_rate": node.base_rate,
        "prior_update": node.prior_update,
        "priority": node.priority,
        "source": node.source,
        "verdict": node.verdict,
        "role": node.strategy_role,
        "regime_mults": {k.value: v for k, v in node.regime_mults.items()},
        "gex_mults": {k.value: v for k, v in node.gex_mults.items()},
        "half_life_sec": node.half_life_sec,
        "is_live": node._is_live,
        "posterior": round(node._current_posterior, 6),
        "logit_effect": round(node.logit_effect, 6),
        "effective_weight": round(node.effective_weight, 6),
        "observations": node._observation_count,
    }


@app.get("/domains")
def domains():
    return v1_engine.status()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML


# ---------------------------------------------------------------------------
# Dashboard HTML
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Bayesian Engine Dashboard</title>
<style>
:root {
  --bg: #0a0e17; --surface: #111827; --border: #1f2937;
  --text: #e5e7eb; --muted: #9ca3af; --accent: #3b82f6;
  --green: #10b981; --red: #ef4444; --yellow: #f59e0b; --purple: #8b5cf6;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); padding: 16px; }
h1 { font-size: 1.5rem; margin-bottom: 8px; }
.subtitle { color: var(--muted); font-size: 0.875rem; margin-bottom: 24px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 16px; margin-bottom: 24px; }
.card { background: var(--surface); border: 1px solid var(--border);
        border-radius: 12px; padding: 20px; }
.card h2 { font-size: 1rem; color: var(--muted); margin-bottom: 12px; }
.big-num { font-size: 2.5rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.tier { display: inline-block; padding: 4px 12px; border-radius: 999px;
        font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
.tier-full { background: rgba(16,185,129,.2); color: var(--green); }
.tier-half { background: rgba(59,130,246,.2); color: var(--accent); }
.tier-quarter { background: rgba(245,158,11,.2); color: var(--yellow); }
.tier-paper { background: rgba(239,68,68,.2); color: var(--red); }
.bar { height: 8px; background: var(--border); border-radius: 4px;
       overflow: hidden; margin-top: 8px; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.meta { display: flex; justify-content: space-between; margin-top: 8px;
        font-size: 0.75rem; color: var(--muted); }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; }
td { font-variant-numeric: tabular-nums; }
.btn { background: var(--accent); color: white; border: none; padding: 10px 20px;
       border-radius: 8px; cursor: pointer; font-size: 0.875rem; }
.btn:hover { opacity: 0.9; }
#status { color: var(--muted); font-size: 0.75rem; margin-top: 8px; }
textarea { width: 100%; min-height: 200px; background: var(--surface);
           color: var(--text); border: 1px solid var(--border); border-radius: 8px;
           padding: 12px; font-family: monospace; font-size: 0.8rem; resize: vertical; }
</style>
</head>
<body>
<h1>MadTrades V6 Bayesian Engine</h1>
<p class="subtitle">200-node continuous rolling probability engine &mdash; 4 versions</p>

<div class="grid" id="engine-cards"></div>

<div class="card" style="margin-bottom:24px">
  <h2>Live Assessment</h2>
  <textarea id="ctx-input">{
  "price": 480.50, "vwap": 480.00, "ema9": 480.20, "ema20": 479.80,
  "ema144": 478.00, "atr_14": 2.5, "bb_upper": 483.0, "bb_lower": 477.0,
  "volume_ratio": 1.3, "cvd_slope": 0.8, "vpin": 0.65, "obi": 0.15,
  "spread_bps": 5.0, "option_delta": 0.45, "option_gamma": 0.08,
  "option_theta": -0.35, "option_iv": 22.0, "premium": 1.85,
  "premium_velocity": 0.12, "premium_in_band": true, "gex": 500000000,
  "regime": "trend_up", "gex_regime": "long_gamma", "vix": 18.0,
  "es_price": 5350.0, "nq_price": 18800.0, "es_nq_basis": 2.5,
  "minutes_since_open": 60, "ib_high": 481.0, "ib_low": 479.0,
  "prev_day_poc": 479.50, "opening_gap_pct": 0.3, "dte": 0,
  "bid_depth_l1": 500, "ask_depth_l1": 450
}</textarea>
  <br><br>
  <button class="btn" onclick="runCompare()">Run All Engines</button>
  <div id="status"></div>
</div>

<div class="card" id="nodes-section" style="display:none">
  <h2>Node Status</h2>
  <div style="overflow-x:auto">
    <table id="nodes-table">
      <thead>
        <tr><th>ID</th><th>Domain</th><th>Description</th><th>Posterior</th>
            <th>Weight</th><th>Role</th><th>Live</th></tr>
      </thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<script>
function tierClass(t) {
  return 'tier tier-' + (t || 'paper');
}
function posteriorColor(p) {
  if (p > 0.6) return 'var(--green)';
  if (p > 0.45) return 'var(--yellow)';
  return 'var(--red)';
}
function renderEngineCard(name, data) {
  const p = data.composite || 0.5;
  const tier = data.confidence || 'paper';
  return `<div class="card">
    <h2>${name}</h2>
    <div class="big-num" style="color:${posteriorColor(p)}">${p.toFixed(4)}</div>
    <span class="${tierClass(tier)}">${tier}</span>
    <div class="bar"><div class="bar-fill" style="width:${p*100}%;background:${posteriorColor(p)}"></div></div>
    <div class="meta">
      ${data.live_nodes != null ? '<span>Live: '+data.live_nodes+'</span>' : ''}
      ${data.agreement != null ? '<span>Agreement: '+(data.agreement*100).toFixed(1)+'%</span>' : ''}
      ${data.consensus ? '<span>'+data.consensus+'</span>' : ''}
    </div>
  </div>`;
}

async function runCompare() {
  const status = document.getElementById('status');
  status.textContent = 'Running all 4 engines...';
  try {
    const body = document.getElementById('ctx-input').value;
    const resp = await fetch('/compare', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: body
    });
    const data = await resp.json();
    const container = document.getElementById('engine-cards');
    container.innerHTML = '';
    const engines = data.engines;
    for (const [name, info] of Object.entries(engines)) {
      container.innerHTML += renderEngineCard(name, info);
    }
    if (data.veto_active) {
      container.innerHTML += `<div class="card" style="border-color:var(--red)">
        <h2 style="color:var(--red)">VETO ACTIVE</h2>
        <p>${(data.veto_reasons || []).join('<br>')}</p>
      </div>`;
    }
    status.textContent = 'Done. Total nodes: ' + data.total_nodes;
    loadNodes();
  } catch(e) {
    status.textContent = 'Error: ' + e.message;
  }
}

async function loadNodes() {
  try {
    const resp = await fetch('/nodes');
    const data = await resp.json();
    const tbody = document.querySelector('#nodes-table tbody');
    tbody.innerHTML = '';
    const liveNodes = data.nodes.filter(n => n.is_live)
      .sort((a,b) => Math.abs(b.posterior - 0.5) - Math.abs(a.posterior - 0.5));
    for (const n of liveNodes.slice(0, 20)) {
      tbody.innerHTML += `<tr>
        <td><code>${n.id}</code></td>
        <td>${n.domain}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${n.description}</td>
        <td style="color:${posteriorColor(n.posterior)}">${n.posterior.toFixed(4)}</td>
        <td>${(n.observations)}</td>
        <td>${n.role}</td>
        <td>${n.is_live ? '●' : '○'}</td>
      </tr>`;
    }
    document.getElementById('nodes-section').style.display = 'block';
  } catch(e) { /* ignore */ }
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
