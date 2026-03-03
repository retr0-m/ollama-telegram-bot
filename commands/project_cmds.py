"""
commands/project_cmds.py
─────────────────────────
Telegram command handlers for project management.

/new    <name>   — create project + set as current
/switch <name>   — change active project
/delete <name>   — remove project from registry (keeps files)
/list            — show all registered projects
/current         — show which project is active right now
"""

from telegram import Update
from telegram.ext import ContextTypes

from state.projects import (
    create_project, switch_project, delete_project,
    all_projects, current_project, current_name,
)
from commands._auth import is_allowed


async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /new <project_name>
    Creates the project directory, registers it, sets it as current.
    """
    if not is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("❓ Usage: /new <project_name>")
        return

    name = context.args[0].lower().replace(" ", "_")

    # Don't overwrite existing
    if name in all_projects():
        await update.message.reply_text(
            f"⚠️ Project `{name}` already exists.\n"
            f"Use /switch {name} to activate it or /delete {name} to remove it.",
            parse_mode="Markdown",
        )
        return

    proj = create_project(name)
    await update.message.reply_text(
        f"✅ *{name}* created and set as active project.\n"
        f"📁 Path: `{proj['path']}`\n\n"
        f"Now just describe what you want to build!",
        parse_mode="Markdown",
    )


async def handle_switch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /switch <project_name>
    Changes the active project so all subsequent messages target it.
    """
    if not is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("❓ Usage: /switch <project_name>")
        return

    name = context.args[0]
    if not switch_project(name):
        available = ", ".join(f"`{n}`" for n in all_projects()) or "none yet"
        await update.message.reply_text(
            f"❓ Project `{name}` not found.\nAvailable: {available}",
            parse_mode="Markdown",
        )
        return

    proj = current_project()
    await update.message.reply_text(
        f"🔀 Switched to *{name}*\n"
        f"📁 `{proj['path']}`\n"
        f"Status: {proj.get('status', 'unknown')}",
        parse_mode="Markdown",
    )


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /delete <project_name>
    Removes the project from the registry.
    Files on disk are NOT deleted (safety measure).
    """
    if not is_allowed(update):
        return
    if not context.args:
        await update.message.reply_text("❓ Usage: /delete <project_name>")
        return

    name = context.args[0]
    if not delete_project(name):
        await update.message.reply_text(f"❓ Project `{name}` not found.", parse_mode="Markdown")
        return

    new_current = current_name()
    note = f"\n↩️ Switched back to *{new_current}*." if new_current else "\n⚠️ No active project now. Use /new to create one."
    await update.message.reply_text(
        f"🗑️ *{name}* removed from registry.\n"
        f"_(Files on disk are untouched)_{note}",
        parse_mode="Markdown",
    )


async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /list
    Shows all registered projects with status, PID and port.
    """
    if not is_allowed(update):
        return

    projects = all_projects()
    active   = current_name()

    if not projects:
        await update.message.reply_text(
            "📭 No projects yet.\nUse /new <name> to create your first one!"
        )
        return

    lines = ["📋 *Projects:*\n"]
    for name, info in projects.items():
        marker  = "▶️" if name == active else "  "
        pid_str = f"PID `{info['pid']}`" if info.get("pid") else "not running"
        port    = f"port `{info['port']}`" if info.get("port") else ""
        lines.append(
            f"{marker} *{name}*  [{info.get('status','?')}]\n"
            f"     {pid_str}  {port}\n"
            f"     📁 `{info['path']}`"
        )

    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown")


async def handle_current(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /current
    Shows the active project details.
    """
    if not is_allowed(update):
        return

    proj = current_project()
    if not proj:
        await update.message.reply_text(
            "⚠️ No active project.\nUse /new <name> to create one or /switch <name> to activate one."
        )
        return

    await update.message.reply_text(
        f"▶️ *Current project: {proj['name']}*\n\n"
        f"📁 Path:    `{proj['path']}`\n"
        f"🔄 Status:  {proj.get('status', 'unknown')}\n"
        f"🔌 Port:    {proj.get('port') or '—'}\n"
        f"🧵 PID:     {proj.get('pid') or '—'}\n"
        f"🕐 Since:   {proj.get('started', '—')}",
        parse_mode="Markdown",
    )
