'''
╔══════════════════════════════════════════════════════════════════╗
║         DOCUMENTATION ENGINE — Master Architect Protocol         ║
║         Generates triple-tier documentation for the project      ║
╚══════════════════════════════════════════════════════════════════╝
'''

import os
import json
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─── DOC 1: RETAIL USER MANUAL ────────────────────────────────────

def generate_doc1_user_manual() -> str:
    '''Explains how to use the Risk Engine dashboard.'''
    
    content = """
# 📜 Bayesian Risk Engine: User Manual

**Version 1.0** | **Last Updated:** {date}

---

## 1. Introduction

The Bayesian Risk Engine is a tool for thinking about risk in a structured, probabilistic way. It helps you move from vague feelings of uncertainty to quantified risk estimates by combining real-world data with your own contextual knowledge.

This dashboard allows you to:
-   Select a base risk from a pre-loaded **Data Lake** of statistics.
-   Apply **Context Multipliers** based on your specific situation.
-   Run a **Bayesian inference model** (PyMC) to calculate the final probability.
-   Visualize the result on an intuitive **Risk Dial**.

## 2. How to Run a Simulation

Follow these steps to assess a scenario:

1.  **Select a Base Event**: Choose a starting risk from the dropdown menu (e.g., "STARTUP_FAILURE"). The dashboard will show its historical base rate and data source.

2.  **Set Exposure**: Define the number of "units" for the risk. This could be years, trips, trades, or attempts. For `STARTUP_FAILURE`, an exposure of `1` represents one startup venture.

3.  **Add Context Multipliers**: This is the most important step. Add factors that make your situation different from the average. 
    -   **Name**: A label for the factor (e.g., "Experienced Founder").
    -   **Value (x)**: The multiplier effect. If you believe an experienced founder is half as likely to fail, you might use a value of `0.5`.
    -   **Uncertainty (σ)**: How confident you are in that multiplier. A low value (`0.1`) means you're very sure; a high value (`1.0`) means it's a wild guess.

4.  **Run Simulation**: Click the "RUN SIMULATION" button. The backend will run 10,000 simulation steps and return the result.

## 3. Interpreting the Results

Once the simulation is complete, the results panel will update:

-   **Posterior Odds**: The main result, presented as "1 in X". This is the model's best guess of the final risk.
-   **Risk Dial**: A visual gauge from "Safe" (1 in a billion) to "Certain" (100%). The needle shows where your result falls on a logarithmic scale.
-   **Risk Level**: A classification from NEGLIGIBLE to CRITICAL.
-   **Micromorts**: The risk expressed as a "1 in a million" chance of failure/death.
-   **Inference Trace**: A step-by-step log of how the model arrived at its conclusion, showing how the base rate was adjusted by your multipliers.

## 4. Example Scenario: Trading Risk

Let's assess the risk of a 5+ losing streak.

1.  **Base Event**: `TRADE_LOSS_STREAK` (Base rate: 15%)
2.  **Exposure**: `1` (representing one trading month)
3.  **Multipliers**:
    -   `Volatile_Market`: `2.0x` (doubles the risk)
    -   `No_Stop_Loss`: `3.0x` (triples the risk)
4.  **Result**: The engine might calculate the final odds as "1 in 2", a much higher risk than the initial 15% base rate.

---
*This document was generated automatically by the Master Architect Protocol.*

"""
    return content.replace("{date}", datetime.utcnow().strftime("%Y-%m-%d"))


# ─── DOC 2: REPLICATION DNA ───────────────────────────────────────

def generate_doc2_replication_dna() -> str:
    '''Provides a step-by-step guide for another AI to rebuild the project.'''
    
    content = """
# 🧬 Replication DNA: Bayesian Risk Engine v1.0

**Objective**: Enable a perfect, automated reconstruction of the `risk_engine` project.

**Generated:** {date}

---

## 1. System Overview

The project is a self-contained web application with a Python backend and a vanilla HTML/JS/React frontend.

-   **Backend**: `server.py` (FastAPI, PyMC)
-   **Frontend**: `dashboard.html` (React from CDN)
-   **Documentation**: Master Architect Protocol system (`docs/`, `scripts/`, `bot/`, `knowledge_base/`)

## 2. Environment & Dependencies

1.  **OS**: Ubuntu 22.04 (or any modern Linux)
2.  **Python**: 3.11+
3.  **System Dependencies**: `rclone` for Google Drive sync.
4.  **Python Packages**: Install via pip:

    ```bash
    pip install fastapi uvicorn pymc numpy pydantic pytensor python-telegram-bot==20.7 requests aiohttp
    ```

## 3. File Manifest

Recreate the following directory structure and file contents:

```
/home/ubuntu/risk_engine/
├── server.py
├── dashboard.html
├── docs/
│   ├── doc_engine.py
│   └── (generated docs will appear here)
├── scripts/
│   ├── generate_docs.py
│   └── drive_sync.py
├── bot/
│   ├── telegram_bot.py
│   └── scheduler.py
└── knowledge_base/
    ├── kb.py
    └── kb_store.json
```

*The content of each file is provided in the session context that triggered this build.*

## 4. Reconstruction Sequence

1.  **Create Directories**: `mkdir -p /home/ubuntu/risk_engine/{{docs,scripts,bot,knowledge_base}}`

2.  **Install Dependencies**: Run the `pip install` command from section 2.

3.  **Write Files**: Populate each file (`server.py`, `dashboard.html`, etc.) with its corresponding source code.

4.  **Seed Knowledge Base**: Execute the KB script to create the initial log.
    ```bash
    python3 /home/ubuntu/risk_engine/knowledge_base/kb.py
    ```

5.  **Set Environment Variables** (Optional - for full functionality):
    -   `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from @BotFather.
    -   `TELEGRAM_CHAT_ID`: Your personal chat ID from @userinfobot.

6.  **Run the Application**:
    -   **Backend**: `python3 /home/ubuntu/risk_engine/server.py`
    -   **Frontend**: Open `dashboard.html` in a web browser.
    -   **Bot** (Optional): `python3 /home/ubuntu/risk_engine/bot/telegram_bot.py`

## 5. Validation

1.  The backend server should be running on `http://0.0.0.0:8000`.
2.  Accessing `http://localhost:8000/health` should return a `200 OK` with status "healthy".
3.  Opening `dashboard.html` should successfully fetch events from the `/datalake` endpoint and render the UI.
4.  Running a simulation should produce a valid result without errors.

---
*This document was generated automatically by the Master Architect Protocol.*
"""
    return content.replace("{date}", datetime.utcnow().strftime("%Y-%m-%d"))


# ─── DOC 3: COGNITIVE ARCHITECTURE ────────────────────────────────

def generate_doc3_cognitive_architecture() -> str:
    '''Explains the "why" behind the system's design.'''
    
    content = """
# 🧠 Cognitive Architecture: Bayesian Risk Engine v1.0

**Audience**: Product Managers, Systems Thinkers, AI Developers

**Generated:** {date}

---

## 1. Core Philosophy: From Intuition to Inference

The primary goal of this tool is to **externalize and structure risk assessment**. Human intuition is poor at compounding probabilities, especially for rare events. This engine acts as a cognitive prosthetic, forcing a disciplined, bottom-up approach to risk analysis.

**Key Principle**: *All risk is a combination of a base rate and context.* The system is designed to separate these two concerns explicitly.

## 2. System Design & Rationale

| Component              | Technology      | Rationale                                                                                                                            |
| ---------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Backend API**        | FastAPI         | High performance, async support, and automatic data validation via Pydantic. Ideal for a responsive, single-purpose API.             |
| **Inference Core**     | PyMC            | A mature, powerful probabilistic programming library. It provides the flexibility to build complex models if needed in V2.           |
| **Inference Method**   | ADVI            | **Speed over precision**. For a real-time dashboard, sub-second response is critical. ADVI is much faster than MCMC sampling.         |
| **Frontend**           | React (CDN)     | Avoids a complex build setup (npm, webpack). The entire UI is a single, self-contained HTML file, maximizing portability.        |
| **Data Lake**          | Hardcoded JSON  | For V1, this is sufficient. It decouples the data from the logic. In V2, this would be a query to a DuckDB or Postgres database. |
| **Documentation**      | Master Architect| Enforces a build-and-document loop, ensuring the project is self-explanatory and reproducible from day one.                      |

## 3. The Bayesian Model Explained

The model is a **Hierarchical Poisson Model**.

1.  **Prior (Base Rate)**: We model the base rate itself as a `LogNormal` distribution. This is crucial. We don't treat the statistic (e.g., "1 in a million") as a fixed number, but as a distribution representing our uncertainty about that number.

2.  **Multipliers**: Each multiplier is also a `LogNormal` distribution. This models the uncertainty of expert opinion ("I think this doubles the risk, but I'm not sure").

3.  **Combination**: We combine the base rate and multipliers by adding them in **log space**. This is equivalent to multiplying them in normal space (`log(A*B) = log(A) + log(B)`), which is the correct way to handle multiplicative risk factors.

4.  **Exposure**: The final probability is calculated using the Poisson-derived formula `P(event > 0) = 1 - exp(-lambda * exposure)`, where `lambda` is the effective rate and `exposure` is the number of trials.

This architecture provides a robust and extensible framework for reasoning about risk under uncertainty.

## 4. V2.0 Improvement Matrix

| Feature                      | Description                                                                                             | Priority |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- | -------- |
| **Batch Processing UI**      | Allow users to run multiple scenarios from the dashboard and compare results side-by-side.              | High     |
| **MCMC Sampling Option**     | Add a toggle to use more accurate (but slower) NUTS sampling instead of ADVI for deep analysis.         | Medium   |
| **Database Integration**     | Connect the Data Lake to a real database (e.g., DuckDB) to allow for dynamic updates.                     | Medium   |
| **Correlation Modeling**     | Allow users to define correlations between multipliers (e.g., a bad economy affects multiple factors).    | Low      |
| **User Accounts & History**  | Save user scenarios and results to a persistent database.                                               | High     |

---
*This document was generated automatically by the Master Architect Protocol.*
"""
    return content.replace("{date}", datetime.utcnow().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    print(generate_doc1_user_manual())
    print('---')
    print(generate_doc2_replication_dna())
    print('---')
    print(generate_doc3_cognitive_architecture())
