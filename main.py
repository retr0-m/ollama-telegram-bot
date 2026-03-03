"""
main.py
────────
Entry point. Wires up all Telegram handlers and starts the bot.
The dashboard is launched as a background thread before polling begins.

Run with:  python main.py
"""

import os
import threading
import uvicorn

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from config import (
    TELEGRAM_TOKEN, ALLOWED_USER_IDS, PROJECTS_DIR,
    DATA_DIR, DASHBOARD_HOST, DASHBOARD_PORT,
)
from commands import (
    is_allowed,
    handle_new, handle_switch, handle_delete, handle_list, handle_current,
    handle_status, handle_logs, handle_stop, handle_reset,
    handle_remember, handle_help,
)
from agent.executor import (
    run_agent,
    has_pending_deploy, pop_pending_deploy,
)
from tools.git import push_to_github
from state.projects import get_project
from state.memory import all_rules


# ─── Dashboard (background thread) ────────────────────────────────────────────

def _start_dashboard():
    """Launch the uvicorn dashboard in a daemon thread."""
    from dashboard.app import app as fastapi_app
    uvicorn.run(
        fastapi_app,
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        log_level="warning",
    )


# ─── Main message handler ─────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles all plain-text messages.
    Routes YES/NO deployment confirmations before passing to the agent.
    """
    if not is_allowed(update):
        await update.message.reply_text("⛔ You are not authorised to use this bot.")
        return

    chat_id    = update.message.chat_id
    user_input = update.message.text.strip()
    user       = update.message.from_user.username or update.message.from_user.first_name
    print(f"\n📩 @{user}: {user_input}")

    # ── GitHub deploy confirmation shortcuts ──────────────────────────────────
    if user_input.upper() in {"YES", "CONFIRM", "OK", "DEPLOY", "PUSH"}:
        if has_pending_deploy(chat_id):
            project_name = pop_pending_deploy(chat_id)
            proj         = get_project(project_name)
            if proj:
                await update.message.reply_text(f"🚀 Pushing *{project_name}* to GitHub...", parse_mode="Markdown")
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                url, ok = push_to_github(proj["path"], project_name)
                if ok:
                    await update.message.reply_text(f"✅ Done! 🔗 {url}")
                else:
                    await update.message.reply_text(f"⚠️ GitHub push failed:\n{url}")
                return

    if user_input.upper() in {"NO", "CANCEL", "SKIP"}:
        if has_pending_deploy(chat_id):
            pop_pending_deploy(chat_id)
            await update.message.reply_text("❌ Deployment skipped. Project is still running locally.")
            return

    # ── Forward to agent ──────────────────────────────────────────────────────
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await run_agent(user_input, update, context)


# ─── Bootstrap ────────────────────────────────────────────────────────────────

def main():
    # Ensure data and project dirs exist
    os.makedirs(PROJECTS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    rules = all_rules()
    print("🚀 Starting Ollama Coding Agent Bot")
    print(f"   Projects dir : {PROJECTS_DIR}")
    print(f"   Dashboard    : http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print(f"   Whitelist    : {ALLOWED_USER_IDS or 'open to everyone'}")
    print(f"   Rules loaded : {len(rules.splitlines())} line(s)" if rules else "   Rules loaded : none")

    # Start dashboard in background
    t = threading.Thread(target=_start_dashboard, daemon=True)
    t.start()
    print(f"   Dashboard thread started ✓\n")

    # Build and start Telegram bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Project management
    app.add_handler(CommandHandler("new",     handle_new))
    app.add_handler(CommandHandler("switch",  handle_switch))
    app.add_handler(CommandHandler("delete",  handle_delete))
    app.add_handler(CommandHandler("list",    handle_list))
    app.add_handler(CommandHandler("current", handle_current))

    # System
    app.add_handler(CommandHandler("status",  handle_status))
    app.add_handler(CommandHandler("logs",    handle_logs))
    app.add_handler(CommandHandler("stop",    handle_stop))
    app.add_handler(CommandHandler("reset",   handle_reset))

    # Memory + help
    app.add_handler(CommandHandler("remember", handle_remember))
    app.add_handler(CommandHandler("help",     handle_help))

    # All plain text → agent
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot ready. Waiting for messages...\n")
    app.run_polling()


if __name__ == "__main__":
    main()
