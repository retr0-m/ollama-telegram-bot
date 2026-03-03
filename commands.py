import os
import time
from datetime import datetime

import psutil
from telegram import Update
from telegram.ext import ContextTypes

from config import PROJECTS_DIR, ALLOWED_USER_IDS
from utils import run_command, save_reminder


# ─── Auth helper ─────────────────────────────────────────────────────────────
def is_allowed(update: Update) -> bool:
    """Return True if ALLOWED_USER_IDS is empty (open) or the user is in the list."""
    if not ALLOWED_USER_IDS:
        return True
    return update.message.from_user.id in ALLOWED_USER_IDS


# ─── /help ───────────────────────────────────────────────────────────────────
HELP_TEXT = """
🤖 *Autonomous Coding Agent — Command Reference*

Send any plain message and the bot will plan, code, run and deploy it on your server using Ollama (qwen2.5-coder).

━━━━━━━━━━━━━━━━━
*💬 Conversation*
━━━━━━━━━━━━━━━━━
Just type your idea, e.g.:
  `Build a Flask REST API with a /ping route`
  `Create a Node.js scraper for Hacker News`

The bot will:
1. Write the code
2. Run it via shell commands
3. Auto-fix errors (up to MAX attempts)
4. Ask you to confirm GitHub push when ready

*YES / CONFIRM / DEPLOY* — push the current project to GitHub
*NO / CANCEL / SKIP* — keep it local, skip GitHub

━━━━━━━━━━━━━━━━━
*📂 Project Management*
━━━━━━━━━━━━━━━━━
/list — show all running projects with PID, port and start time
/stop `<name>` — kill a running project by name
/logs `<name>` — tail the last 50 lines of a project log
/reset — clear conversation history for this chat

━━━━━━━━━━━━━━━━━
*🖥️ Server*
━━━━━━━━━━━━━━━━━
/status — CPU, RAM and disk usage of the Mac Mini

━━━━━━━━━━━━━━━━━
*🧠 Memory*
━━━━━━━━━━━━━━━━━
/remember `<rule>` — teach the bot a permanent rule, e.g.:
  `/remember ALWAYS use port 8080 for Flask apps`

Rules are injected into every future system prompt.

━━━━━━━━━━━━━━━━━
*⚙️ Tips*
━━━━━━━━━━━━━━━━━
• Be specific — more detail = better output
• Use /reset if the bot gets confused mid-task
• Check /status before heavy tasks to verify free RAM
• Projects are saved in your configured PROJECTS\\_DIR
• Logs are expected at PROJECTS\\_DIR/<name>/app.log
""".strip()

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


# ─── /reset ──────────────────────────────────────────────────────────────────
async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from bot import chat_histories, pending_confirmation
    chat_id = update.message.chat_id
    chat_histories[chat_id] = []
    pending_confirmation.pop(chat_id, None)
    await update.message.reply_text("🔄 Conversation history cleared. Fresh start!")


# ─── /list ───────────────────────────────────────────────────────────────────
def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False

async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from bot import running_projects
    if not running_projects:
        await update.message.reply_text("📭 No projects tracked yet.\nSend a build request to get started!")
        return

    lines = ["📋 *Running Projects:*\n"]
    for name, info in running_projects.items():
        pid   = info.get("pid", "?")
        port  = info.get("port", "—")
        start = info.get("started", "?")
        alive = "✅ alive" if _pid_alive(pid) else "💀 dead"
        lines.append(
            f"*{name}*\n"
            f"  PID: `{pid}` {alive}\n"
            f"  Port: `{port}`\n"
            f"  Started: {start}"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


# ─── /stop ───────────────────────────────────────────────────────────────────
async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from bot import running_projects
    if not context.args:
        await update.message.reply_text("❓ Usage: /stop <project_name>")
        return

    name = context.args[0]
    if name not in running_projects:
        await update.message.reply_text(f"❓ Project `{name}` not found.", parse_mode="Markdown")
        return

    pid = running_projects[name].get("pid")
    if pid and _pid_alive(pid):
        output, code = run_command(f"kill {pid}")
        if code == 0:
            await update.message.reply_text(f"🛑 Stopped *{name}* (PID {pid})", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"⚠️ Could not kill PID {pid}:\n{output}")
    else:
        await update.message.reply_text(
            f"⚠️ Process for *{name}* is already dead or PID unknown.", parse_mode="Markdown"
        )
    running_projects.pop(name, None)


# ─── /logs ───────────────────────────────────────────────────────────────────
async def handle_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("❓ Usage: /logs <project_name>")
        return

    name     = context.args[0]
    log_path = f"{PROJECTS_DIR}/{name}/app.log"

    if not os.path.exists(log_path):
        output, _ = run_command(f"find {PROJECTS_DIR}/{name} -name '*.log' 2>/dev/null | head -3")
        if output:
            log_path = output.splitlines()[0]
        else:
            await update.message.reply_text(
                f"📭 No log file found for `{name}`.\nExpected: `{log_path}`",
                parse_mode="Markdown"
            )
            return

    output, _ = run_command(f"tail -50 {log_path}")
    msg = f"📄 *Logs — {name}*\n```\n{(output or '(empty)')[-3500:]}\n```"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ─── /status ─────────────────────────────────────────────────────────────────
async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    from bot import running_projects

    cpu      = psutil.cpu_percent(interval=1)
    mem      = psutil.virtual_memory()
    disk     = psutil.disk_usage('/')
    uptime_s = time.time() - psutil.boot_time()
    uptime   = (
        datetime.utcfromtimestamp(uptime_s).strftime('%H:%M:%S')
        if uptime_s < 86400
        else f"{int(uptime_s // 3600)}h {int((uptime_s % 3600) // 60)}m"
    )

    def bar(pct, width=10):
        filled = int(pct / 100 * width)
        return "█" * filled + "░" * (width - filled)

    msg = (
        f"🖥️ *Mac Mini — Server Status*\n\n"
        f"`CPU  ` {bar(cpu)} {cpu:.1f}%\n"
        f"`RAM  ` {bar(mem.percent)} {mem.percent:.1f}%  "
        f"({mem.used/1e9:.1f} / {mem.total/1e9:.1f} GB)\n"
        f"`Disk ` {bar(disk.percent)} {disk.percent:.1f}%  "
        f"({disk.used/1e9:.1f} / {disk.total/1e9:.1f} GB)\n"
        f"`Up   ` {uptime}\n\n"
        f"Projects tracked: {len(running_projects)}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# ─── /remember ───────────────────────────────────────────────────────────────
async def handle_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    text = update.message.text.replace("/remember", "").strip()
    if not text:
        await update.message.reply_text("❓ Usage: /remember ALWAYS use port 8080 for Flask apps")
        return
    save_reminder(text)
    await update.message.reply_text(f"🧠 Got it! I'll remember:\n- {text}")