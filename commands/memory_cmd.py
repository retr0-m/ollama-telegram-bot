"""
commands/memory_cmd.py
───────────────────────
/remember <rule>
Saves a permanent rule that is injected into every future system prompt.
"""

from telegram import Update
from telegram.ext import ContextTypes

from commands._auth import is_allowed
from state.memory import save_rule, load_rules


async def handle_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /remember ALWAYS use port 8080 for Flask apps
    Adds the rule to rules.txt so it persists across restarts.
    """
    if not is_allowed(update):
        return

    text = update.message.text.replace("/remember", "").strip()
    if not text:
        await update.message.reply_text(
            "❓ Usage: /remember <rule>\n\n"
            "Example: /remember ALWAYS use port 8080 for Flask apps"
        )
        return

    save_rule(text)

    all_rules = load_rules()
    count     = len([l for l in all_rules.splitlines() if l.strip()])
    await update.message.reply_text(
        f"🧠 Got it! I'll always remember:\n`{text}`\n\n"
        f"_{count} rule(s) active_",
        parse_mode="Markdown",
    )
