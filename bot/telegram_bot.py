"""
╔══════════════════════════════════════════════════════════════════╗
║         TELEGRAM BOT — Master Architect Protocol                 ║
║         Push notifications, status updates, KB search           ║
║         Uses python-telegram-bot v20 async API                   ║
╚══════════════════════════════════════════════════════════════════╝

SETUP:
1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
2. Get your chat_id by messaging @userinfobot
3. Set env vars: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
4. Run: python3 bot/telegram_bot.py

COMMANDS:
  /status   — Show project status and KB summary
  /search   — Search knowledge base: /search ADVI
  /health   — Check API health
  /help     — Show all commands
"""

import os
import sys
import asyncio
import logging
import json
import requests
from datetime import datetime

# Add parent dir to path for kb import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ─── CONFIG ───────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
API_BASE  = os.environ.get("RISK_ENGINE_API", "http://localhost:8000")

# ─── SIMPLE HTTP SENDER (no telegram lib required for basic push) ──

def send_message_http(text: str, token: str = None, chat_id: str = None) -> bool:
    """Send a Telegram message via raw HTTP (no library needed)."""
    token   = token   or BOT_TOKEN
    chat_id = chat_id or CHAT_ID
    if not token or not chat_id:
        logger.warning("Telegram credentials not set. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False


def send_push_notification(message: str, category: str = "update"):
    """
    Master Architect Protocol: send a push notification.
    Called after major build milestones.
    """
    icons = {
        "milestone": "🏆",
        "build_log":  "🔨",
        "decision":   "🧠",
        "doc_update": "📄",
        "deploy":     "🚀",
        "error":      "🚨",
        "update":     "📡",
    }
    icon = icons.get(category, "📡")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    text = (
        f"{icon} *RISK ENGINE — {category.upper()}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{message}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 `{timestamp}`"
    )
    return send_message_http(text)


def send_daily_recap(kb_summary: dict, drive_links: list = None):
    """Send the 8PM daily recap with build summary and Drive links."""
    cats = kb_summary.get("categories", {})
    cat_lines = "\n".join([f"  • {k}: {v}" for k, v in cats.items()])
    
    links_section = ""
    if drive_links:
        links_section = "\n\n📁 *Google Drive Docs:*\n" + "\n".join([f"  [{l['name']}]({l['url']})" for l in drive_links])
    
    text = (
        f"🌅 *DAILY RECAP — Bayesian Risk Engine*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 *KB Summary:*\n{cat_lines}\n"
        f"📝 Total Entries: {kb_summary.get('total_entries', 0)}\n"
        f"🔄 Last Updated: `{kb_summary.get('last_updated', 'N/A')}`\n"
        f"💬 Latest: _{kb_summary.get('latest_entry', 'N/A')}_"
        f"{links_section}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`"
    )
    return send_message_http(text)


# ─── FULL BOT (requires python-telegram-bot) ──────────────────────

def run_full_bot():
    """
    Run the full interactive Telegram bot with command handlers.
    Requires: pip install python-telegram-bot==20.7
    """
    try:
        from telegram import Update
        from telegram.ext import Application, CommandHandler, ContextTypes
    except ImportError:
        print("python-telegram-bot not installed. Run: pip install python-telegram-bot==20.7")
        return

    if not BOT_TOKEN:
        print("Set TELEGRAM_BOT_TOKEN environment variable.")
        return

    async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 *Bayesian Risk Engine Bot*\n\n"
            "Commands:\n"
            "/status — Project KB summary\n"
            "/health — API health check\n"
            "/search <query> — Search KB\n"
            "/help — This message",
            parse_mode="Markdown"
        )

    async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        try:
            from knowledge_base.kb import get_summary
            summary = get_summary("risk_engine")
            cats = "\n".join([f"  • {k}: {v}" for k, v in summary.get("categories", {}).items()])
            await update.message.reply_text(
                f"📊 *Risk Engine KB Status*\n\n{cats}\n\nTotal: {summary['total_entries']} entries",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def health_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        try:
            r = requests.get(f"{API_BASE}/health", timeout=5)
            data = r.json()
            await update.message.reply_text(
                f"✅ *API Health*\n\nStatus: {data['status']}\nVersion: {data['version']}\nData Lake: {data['data_lake_size']} events",
                parse_mode="Markdown"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ API Offline: {e}")

    async def search_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = " ".join(ctx.args) if ctx.args else ""
        if not query:
            await update.message.reply_text("Usage: /search <query>")
            return
        try:
            from knowledge_base.kb import search
            results = search(query, "risk_engine")[:5]
            if not results:
                await update.message.reply_text(f"No results for: {query}")
                return
            lines = "\n".join([f"• [{r['category']}] {r['content'][:80]}" for r in results])
            await update.message.reply_text(f"🔍 *Search: {query}*\n\n{lines}", parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("help",   start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("health", health_cmd))
    app.add_handler(CommandHandler("search", search_cmd))

    print(f"Bot starting... (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Test push notification
    if BOT_TOKEN and CHAT_ID:
        print("Sending test notification...")
        ok = send_push_notification(
            "Bayesian Risk Engine bot initialized and ready. All systems nominal.",
            "milestone"
        )
        print(f"Sent: {ok}")
        run_full_bot()
    else:
        print("No Telegram credentials found.")
        print("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable notifications.")
        print("Bot module loaded successfully (credentials not required for import).")
