"""
commands/system_cmds.py
────────────────────────
/status  — server CPU/RAM/disk
/logs    — tail the log of a project (defaults to current project)
/stop    — kill a running project process
/reset   — clear chat history for this conversation
"""

import os
import time
from datetime import datetime

import psutil
from telegram import Update
from telegram.ext import ContextTypes

from agent.executor import clear_history
from commands._auth import is_allowed
from state.projects import all_projects, current_project, update_project
from tools.filesystem import find_log, tail_file
from tools.shell import run_command


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status — show server resource usage."""
    if not is_allowed(update):
        return

    cpu    = psutil.cpu_percent(interval=1)
    mem    = psutil.virtual_memory()
    disk   = psutil.disk_usage('/')
    up_sec = time.time() - psutil.boot_time()
    uptime = (
        datetime.utcfromtimestamp(up_sec).strftime('%H:%M:%S')
        if up_sec < 86400 else f"{int(up_sec // 3600)}h {int((up_sec % 3600) // 60)}m"
    )

    def bar(pct, w=10):
        n = int(pct / 100 * w)
        return "█" * n + "░" * (w - n)

    projects = all_projects()
    running  = sum(1 for p in projects.values() if _pid_alive(p.get("pid")))

    msg = (
        f"🖥️ *Server Status*\n\n"
        f"`CPU ` {bar(cpu)} {cpu:.1f}%\n"
        f"`RAM ` {bar(mem.percent)} {mem.percent:.1f}%  "
        f"({mem.used/1e9:.1f}/{mem.total/1e9:.1f} GB)\n"
        f"`Disk` {bar(disk.percent)} {disk.percent:.1f}%  "
        f"({disk.used/1e9:.1f}/{disk.total/1e9:.1f} GB)\n"
        f"`Up  ` {uptime}\n\n"
        f"Projects: {len(projects)} registered, {running} running"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /logs [project_name]
    Defaults to the current project if no name is given.
    """
    if not is_allowed(update):
        return

    if context.args:
        name = context.args[0]
        proj = all_projects().get(name)
    else:
        proj = current_project()
        name = proj["name"] if proj else None

    if not proj:
        await update.message.reply_text(
            "❓ No project specified and no active project.\n"
            "Usage: /logs <project_name>"
        )
        return

    log_path = find_log(proj["path"])
    if not log_path:
        await update.message.reply_text(
            f"📭 No log file found for `{name}`.",
            parse_mode="Markdown"
        )
        return

    content = tail_file(log_path, lines=50) or "(empty)"
    msg = f"📄 *{name}* — `{log_path}`\n```\n{content[-3500:]}\n```"
    await update.message.reply_text(msg, parse_mode="Markdown")


async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stop [project_name]
    Kills the process for a project. Defaults to current project.
    """
    if not is_allowed(update):
        return

    if context.args:
        name = context.args[0]
        proj = all_projects().get(name)
    else:
        proj = current_project()
        name = proj["name"] if proj else None

    if not proj:
        await update.message.reply_text("❓ Usage: /stop <project_name>")
        return

    pid = proj.get("pid")
    if pid and _pid_alive(pid):
        out, rc = run_command(f"kill {pid}")
        if rc == 0:
            update_project(name, pid=None, status="stopped")
            await update.message.reply_text(
                f"🛑 Stopped *{name}* (PID {pid})", parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(f"⚠️ Could not kill PID {pid}:\n{out}")
    else:
        await update.message.reply_text(
            f"⚠️ *{name}* is not running or PID is unknown.", parse_mode="Markdown"
        )


async def handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/reset — clear this chat's conversation history."""
    if not is_allowed(update):
        return
    clear_history(update.message.chat_id)
    await update.message.reply_text("🔄 Chat history cleared. Fresh start!")
