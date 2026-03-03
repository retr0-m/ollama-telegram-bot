"""
commands/help_cmd.py
─────────────────────
/help — full command reference.
"""

from telegram import Update
from telegram.ext import ContextTypes

from commands._auth import is_allowed


HELP_TEXT = """
🤖 *Autonomous Coding Agent*

Just type your idea and I'll plan, code, run and deploy it.
Example: `Build a FastAPI app with a /ping route`

━━━━━━━━━━━━━━━━━━━━
*📂 Project Management*
━━━━━━━━━━━━━━━━━━━━
/new `<name>`    — create a project and set it as active
/switch `<name>` — switch to a different project
/delete `<name>` — remove a project from the registry
/list            — show all projects with status
/current         — show the active project

━━━━━━━━━━━━━━━━━━━━
*🖥️ System*
━━━━━━━━━━━━━━━━━━━━
/status          — CPU, RAM and disk of the server
/logs `[name]`   — last 50 lines of a project log (defaults to current)
/stop `[name]`   — kill a running project (defaults to current)
/reset           — clear this chat's conversation history

━━━━━━━━━━━━━━━━━━━━
*🧠 Memory*
━━━━━━━━━━━━━━━━━━━━
/remember `<rule>` — teach me a permanent rule, e.g.:
  `/remember ALWAYS use port 8080 for Flask apps`

Rules are injected into every future prompt.

━━━━━━━━━━━━━━━━━━━━
*🚀 Deployment*
━━━━━━━━━━━━━━━━━━━━
When the bot says the project is ready, reply:
  *YES / CONFIRM / DEPLOY* — push to GitHub
  *NO / CANCEL / SKIP*     — keep local only

━━━━━━━━━━━━━━━━━━━━
*💡 Tips*
━━━━━━━━━━━━━━━━━━━━
• Always /new a project before describing a task
• Use /switch to work on multiple projects in parallel
• /reset if the bot gets confused mid-task
• Check /status before heavy jobs (RAM check)
• All projects are isolated — separate dir, venv & logs
""".strip()


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")
