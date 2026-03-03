
# 📜 Bayesian Risk Engine: User Manual

**Version 1.0** | **Last Updated:** 2026-02-27

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

