
# 🧬 Replication DNA: Bayesian Risk Engine v1.0

**Objective**: Enable a perfect, automated reconstruction of the `risk_engine` project.

**Generated:** 2026-02-27

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
