
# 🧠 Cognitive Architecture: Bayesian Risk Engine v1.0

**Audience**: Product Managers, Systems Thinkers, AI Developers

**Generated:** 2026-02-27

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
