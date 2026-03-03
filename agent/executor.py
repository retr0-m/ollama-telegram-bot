"""
agent/executor.py
─────────────────
The main agent loop:
  1. Send user message to Ollama
  2. Parse <CMD> tags from the reply
  3. Execute commands one by one
  4. On error → ask Ollama to fix → retry (up to MAX_FIX_ATTEMPTS)
  5. On <READY_TO_DEPLOY> → ask user to confirm GitHub push
  6. Register PID/port/status into project state after each run

This module is pure logic — it receives a Telegram `update` object
only to send progress messages back. All Ollama and shell calls go
through their respective modules.
"""

import re
from datetime import datetime
from typing import Optional

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ContextTypes

from config import MAX_FIX_ATTEMPTS
from agent.ollama import chat, extract_rule_from_error
from state.memory import save_learned
from state.projects import current_name, update_project
from tools.shell import run_command


# ─── Tag helpers ─────────────────────────────────────────────────────────────

def _tags(text: str, tag: str) -> list[str]:
    return re.findall(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)


def _strip_tags(text: str) -> str:
    """Remove all structural tags from the final reply before showing to user."""
    for tag in ("CMD", "PROJECT", "URL", "PID", "READY_TO_DEPLOY", "DEPLOYED"):
        text = re.sub(rf'<{tag}>.*?</{tag}>', '', text, flags=re.DOTALL)
        text = re.sub(rf'</?{tag}>', '', text)
    return text.strip()


# ─── Chat history helpers (per-chat, in-memory) ───────────────────────────────

_histories: dict[int, list[dict]] = {}   # chat_id → messages

def get_history(chat_id: int) -> list[dict]:
    return _histories.setdefault(chat_id, [])

def clear_history(chat_id: int):
    _histories[chat_id] = []

def _append(chat_id: int, role: str, content: str):
    from config import MAX_HISTORY_MSGS
    h = get_history(chat_id)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY_MSGS:
        _histories[chat_id] = h[-MAX_HISTORY_MSGS:]


# ─── Pending GitHub confirmations (per-chat) ─────────────────────────────────

_pending_deploy: dict[int, str] = {}   # chat_id → project_name

def set_pending_deploy(chat_id: int, project_name: str):
    _pending_deploy[chat_id] = project_name

def pop_pending_deploy(chat_id: int) -> Optional[str]:
    return _pending_deploy.pop(chat_id, None)

def has_pending_deploy(chat_id: int) -> bool:
    return chat_id in _pending_deploy


# ─── Main entry point ─────────────────────────────────────────────────────────

async def run_agent(
    user_input: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    """
    Full agent pipeline for one user message.
    Sends progress and final reply back through Telegram.
    """
    chat_id = update.message.chat_id
    _append(chat_id, "user", user_input)

    await update.message.reply_text("🤔 Thinking...")
    reply = chat(get_history(chat_id))
    _append(chat_id, "assistant", reply)

    # ── Execution + auto-fix loop ────────────────────────────────────────────
    for attempt in range(1, MAX_FIX_ATTEMPTS + 1):
        cmds = _tags(reply, "CMD")
        if not cmds:
            break   # No commands — pure text reply

        outputs   = []
        has_error = False

        for cmd in cmds:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            output, rc = run_command(cmd.strip())
            outputs.append(f"$ {cmd.strip()}\n{output}")
            if rc != 0 and output != "TIMEOUT":
                has_error = True

        # Update project state from tags
        _register_metadata(reply)

        # Send execution results
        progress = f"⚙️ *Attempt {attempt}/{MAX_FIX_ATTEMPTS}*\n" + "\n\n".join(outputs)
        await _send_chunked(update, progress)

        if not has_error:
            break

        # Auto-fix: learn from error, then ask Ollama to fix
        error_text = "\n".join(outputs)
        rule = extract_rule_from_error(error_text)
        if rule:
            save_learned(rule)
            await update.message.reply_text(f"🧠 *Learned:* {rule}", parse_mode="Markdown")

        _append(chat_id, "user",
            f"Errors occurred:\n{error_text}\nPlease fix and try again.")
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        reply = chat(get_history(chat_id))
        _append(chat_id, "assistant", reply)

    else:
        await update.message.reply_text(
            f"😓 Hit max {MAX_FIX_ATTEMPTS} fix attempts. Want me to try a completely different approach?"
        )
        return

    # ── Final reply ──────────────────────────────────────────────────────────
    clean = _strip_tags(reply)
    if clean:
        await _send_chunked(update, clean)

    # ── URL notification ─────────────────────────────────────────────────────
    urls = _tags(reply, "URL")
    if urls:
        await update.message.reply_text(f"🌐 Live at: {urls[0]}")

    # ── Deploy prompt ─────────────────────────────────────────────────────────
    if "<READY_TO_DEPLOY>" in reply:
        projects = _tags(reply, "PROJECT")
        name     = projects[0].strip() if projects else current_name() or "myproject"
        set_pending_deploy(chat_id, name)
        await update.message.reply_text(
            f"🚀 *{name}* is working!\n\nPush to GitHub?\nReply *YES* to deploy or *NO* to skip.",
            parse_mode="Markdown",
        )


# ─── Internals ────────────────────────────────────────────────────────────────

def _register_metadata(reply: str):
    """Parse PROJECT/PID/URL tags and persist them to project state."""
    projects = _tags(reply, "PROJECT")
    pids     = _tags(reply, "PID")
    urls     = _tags(reply, "URL")
    if not projects:
        return
    name = projects[0].strip()
    port = ""
    if urls:
        m = re.search(r':(\d{2,5})', urls[0])
        port = m.group(1) if m else ""
    update_project(name,
        pid     = pids[0].strip() if pids else None,
        port    = port or None,
        status  = "running",
        started = datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


async def _send_chunked(update: Update, text: str, chunk: int = 4096):
    for i in range(0, len(text), chunk):
        await update.message.reply_text(text[i:i + chunk])
