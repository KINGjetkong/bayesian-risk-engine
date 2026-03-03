# Bayesian Risk Engine v1.0

A real-time probabilistic risk assessment tool built with FastAPI + PyMC. Turns vague uncertainty into quantified probability using Bayesian inference.

## What It Does

- Select a base risk event from a 10-event **Data Lake** (startup failure, trading loss streaks, market crashes, etc.)
- Apply **Context Multipliers** to adjust for your specific situation
- Run a **PyMC ADVI inference model** (10,000 simulation steps) in real-time
- Get back: posterior odds, 95% CI, micromorts, risk level, and a full logic chain trace

## Live Demo

- **Dashboard:** `/dashboard`
- **API Docs:** `/docs`
- **Health:** `/health`

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + PyMC + Pydantic |
| Inference | Hierarchical Poisson Model, ADVI |
| Frontend | React (CDN) + Vanilla JS |
| Notifications | python-telegram-bot |
| Docs | Master Architect Protocol (triple-tier) |

## Quick Start

```bash
pip install -r requirements.txt
python server.py
# Open http://localhost:8000/dashboard
```

## API

```bash
POST /assess
{
  "event_type": "startup_failure",
  "exposure": 1.0,
  "multipliers": [
    {"name": "Experienced_Founder", "value": 0.5, "uncertainty": 0.2}
  ]
}
```

## Built By

JetSetFly / Josh King Madrid — Master Architect Protocol + MiniMax Terminal
