"""
╔══════════════════════════════════════════════════════════════════╗
║         SCHEDULER — Master Architect Protocol                    ║
║         Daily recap at 8PM + milestone push notifications        ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
    python3 bot/scheduler.py &   # Run in background
    
The scheduler sends a daily recap at 20:00 server time with:
- KB summary (builds, decisions, milestones)
- Google Drive doc links
- Latest activity log
"""

import sys
import os
import time
import logging
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SCHEDULER] %(message)s')
logger = logging.getLogger(__name__)


def get_next_8pm() -> float:
    """Return seconds until next 8PM."""
    now = datetime.now()
    target = now.replace(hour=20, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daily_recap():
    """Execute the daily recap: pull KB summary + send via Telegram."""
    try:
        from knowledge_base.kb import get_summary
        from bot.telegram_bot import send_daily_recap

        summary = get_summary("risk_engine")
        
        # Try to get Google Drive links
        drive_links = []
        try:
            from scripts.drive_sync import get_latest_links
            drive_links = get_latest_links()
        except Exception:
            pass

        ok = send_daily_recap(summary, drive_links)
        logger.info(f"Daily recap sent: {ok}")
    except Exception as e:
        logger.error(f"Daily recap failed: {e}")


def run_scheduler():
    """Main scheduler loop. Sends daily recap at 8PM."""
    logger.info("Scheduler started. Daily recap at 20:00 server time.")
    
    while True:
        wait_secs = get_next_8pm()
        next_time = datetime.now() + timedelta(seconds=wait_secs)
        logger.info(f"Next recap at: {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_secs)
        run_daily_recap()


if __name__ == "__main__":
    run_scheduler()
