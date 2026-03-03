"""
╔══════════════════════════════════════════════════════════════════╗
║         GOOGLE DRIVE SYNC — Master Architect Protocol            ║
║         Auto-uploads docs to timestamped Drive folders           ║
╚══════════════════════════════════════════════════════════════════╝

Uses rclone (pre-configured at /home/ubuntu/.gdrive-rclone.ini)
Uploads to: manus_google_drive:risk_engine/YYYY-MM-DDTHH-MM-SS/
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

RCLONE_CONFIG = "/home/ubuntu/.gdrive-rclone.ini"
REMOTE_NAME   = "manus_google_drive"
REMOTE_BASE   = "risk_engine"
LOCAL_DOCS    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")

_link_cache: List[Dict] = []


def get_timestamp_folder() -> str:
    """Return ISO 8601 timestamp folder name."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")


def upload_docs(local_dir: str = None, label: str = "docs") -> Optional[str]:
    """
    Upload a local directory to Google Drive under a timestamped folder.
    Returns the remote path on success, None on failure.
    """
    local_dir = local_dir or LOCAL_DOCS
    if not os.path.exists(local_dir):
        logger.warning(f"Local docs dir not found: {local_dir}")
        return None

    timestamp = get_timestamp_folder()
    remote_path = f"{REMOTE_NAME}:{REMOTE_BASE}/{timestamp}"

    cmd = [
        "rclone", "copy", local_dir, remote_path,
        "--config", RCLONE_CONFIG,
        "--progress"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            logger.info(f"Uploaded docs to: {remote_path}")
            return remote_path
        else:
            logger.error(f"rclone error: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("rclone upload timed out")
        return None
    except FileNotFoundError:
        logger.warning("rclone not found. Install rclone to enable Drive sync.")
        return None


def get_shareable_link(remote_path: str) -> Optional[str]:
    """Generate a shareable link for a remote path."""
    cmd = [
        "rclone", "link", remote_path,
        "--config", RCLONE_CONFIG
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception as e:
        logger.error(f"Link generation failed: {e}")
        return None


def sync_and_notify(doc_files: List[str] = None) -> List[Dict]:
    """
    Full sync: upload docs → get links → cache for Telegram recap.
    Returns list of {name, url} dicts.
    """
    global _link_cache

    remote_path = upload_docs()
    if not remote_path:
        return []

    links = []
    doc_names = doc_files or ["user_manual.md", "replication_dna.md", "cognitive_architecture.md"]
    
    for doc_name in doc_names:
        doc_remote = f"{remote_path}/{doc_name}"
        url = get_shareable_link(doc_remote)
        if url:
            links.append({"name": doc_name.replace("_", " ").replace(".md", "").title(), "url": url})

    _link_cache = links
    return links


def get_latest_links() -> List[Dict]:
    """Return cached Drive links from last sync."""
    return _link_cache


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Testing Drive sync...")
    links = sync_and_notify()
    print(f"Links generated: {links}")
