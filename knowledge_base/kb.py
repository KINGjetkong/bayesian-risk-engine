"""
╔══════════════════════════════════════════════════════════════════╗
║         KNOWLEDGE BASE — Master Architect Protocol               ║
║         Logs all build decisions, events, and milestones         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict

KB_FILE = os.path.join(os.path.dirname(__file__), "kb_store.json")


def _load() -> List[Dict]:
    if not os.path.exists(KB_FILE):
        return []
    with open(KB_FILE, "r") as f:
        return json.load(f)


def _save(entries: List[Dict]):
    with open(KB_FILE, "w") as f:
        json.dump(entries, f, indent=2, default=str)


def add_entry(content: str, category: str = "general", project: str = "risk_engine", metadata: Optional[Dict] = None):
    """
    Add a new entry to the knowledge base.
    Categories: build_log, decision, milestone, error, doc_update, deploy
    """
    entries = _load()
    entry = {
        "id": len(entries) + 1,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "project": project,
        "category": category,
        "content": content,
        "metadata": metadata or {}
    }
    entries.append(entry)
    _save(entries)
    return entry


def get_entries(project: Optional[str] = None, category: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Retrieve entries, optionally filtered by project or category."""
    entries = _load()
    if project:
        entries = [e for e in entries if e.get("project") == project]
    if category:
        entries = [e for e in entries if e.get("category") == category]
    return entries[-limit:]


def get_summary(project: str = "risk_engine") -> Dict:
    """Return a summary of all activity for a project."""
    entries = get_entries(project=project)
    categories = {}
    for e in entries:
        cat = e.get("category", "general")
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "project": project,
        "total_entries": len(entries),
        "categories": categories,
        "last_updated": entries[-1]["timestamp"] if entries else None,
        "latest_entry": entries[-1]["content"] if entries else None
    }


def search(query: str, project: Optional[str] = None) -> List[Dict]:
    """Simple text search across knowledge base entries."""
    entries = get_entries(project=project, limit=500)
    query_lower = query.lower()
    return [e for e in entries if query_lower in e["content"].lower()]


# ─── SEED INITIAL BUILD LOG ───────────────────────────────────────
if __name__ == "__main__":
    add_entry("Project initialized: Bayesian Risk Engine v1.0", "milestone", "risk_engine")
    add_entry("Backend: FastAPI + PyMC ADVI inference engine built", "build_log", "risk_engine")
    add_entry("Frontend: React + Tailwind dashboard with risk dial built", "build_log", "risk_engine")
    add_entry("Data Lake: 10 preset events across 5 categories", "build_log", "risk_engine")
    add_entry("Architecture decision: ADVI over MCMC for sub-second inference on convex models", "decision", "risk_engine")
    add_entry("Architecture decision: LogNormal priors for positivity + multiplicative uncertainty", "decision", "risk_engine")
    print("KB seeded:", get_summary())
