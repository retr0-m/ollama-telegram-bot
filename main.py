import re
import os
import requests
from datetime import datetime

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from telegram.constants import ChatAction

from config import *
from utils import (
    run_command, extract_tags, clean_reply,
    load_learned_rules, save_learned_rule,
)
from commands import (
    handle_help, handle_reset, handle_list,
    handle_stop, handle_logs, handle_status, handle_remember,
    is_allowed,
)


# ─── Shared state ─────────────────────────────────────────────────────────────
# commands.py reads these via lazy `from main import ...` inside each function
# to avoid circular imports at module load time.
chat_histories       = {}   # { chat_id: [{"role": ..., "content": ...}] }
pending_confirmation = {}   # { chat_id: project_name }
running_projects     = {}   # { project_name: { pid, port, started, path } }

MAX_HISTORY = 20


# ─── History helpers ──────────────────────────────────────────────────────────
def get_history(chat_id):
    return chat_histories.setdefault(chat_id, [])

def append_history(chat_id, role, content):
    h = get_history(chat_id)
    h.append({"role": role, "content": content})
    if len(h) > MAX_HISTORY:
        chat_histories[chat_id] = h[-MAX_HISTORY:]


# ─── System prompt ────────────────────────────────────────────────────────────
def build_system_prompt():
    learned = load_learned_rules()
    learned_section = f"\nLEARNED FROM PAST ERRORS (ALWAYS FOLLOW THESE):\n{learned}" if learned else ""
    return f"""You are an autonomous coding agent running on Ubuntu Server 24.04.
Your job is to take an idea and fully implement it: plan, write, debug, test and deploy.
Dont give me instructions, just do the work and show me the progress with CMD commands.

RULES:
- Always wrap shell commands in <CMD> tags: <CMD>command here</CMD>
- Always wrap project name in <PROJECT> tags: <PROJECT>myprojectname</PROJECT>
- Always wrap deployment URL in <URL> tags if applicable: <URL>http://{SERVER_IP}:PORT</URL>
- Always wrap the process PID in <PID> tags after starting a process: <PID>1234</PID>
- ALWAYS create the project directory first: <CMD>mkdir -p {PROJECTS_DIR}/PROJECTNAME</CMD>
- ALWAYS use python3 never python
- ALWAYS create a virtualenv for every python project:
    <CMD>python3 -m venv {PROJECTS_DIR}/PROJECTNAME/venv</CMD>
    <CMD>{PROJECTS_DIR}/PROJECTNAME/venv/bin/pip install PACKAGE</CMD>
    <CMD>{PROJECTS_DIR}/PROJECTNAME/venv/bin/python app.py &</CMD>
- When writing files use heredoc syntax:
    <CMD>cat > {PROJECTS_DIR}/PROJECTNAME/filename.py << 'EOF'
code here
EOF</CMD>
- After writing code always run it and check for errors
- If there is an error fix it and try again up to {MAX_FIX_ATTEMPTS} times
- When done and working say <READY_TO_DEPLOY> and wait for confirmation
- When told CONFIRMED push to GitHub and say <DEPLOYED>
- Be concise in explanations, focus on doing
- Server IP is {SERVER_IP}
- Projects directory is {PROJECTS_DIR}
- You're running on Ubuntu 24.04 LTS on an 8 GB DDR3 Mac Mini.
- DONT GIVE ME INSTRUCTIONS, JUST DO THE JOB WITH CMD COMMANDS AND SHOW ME THE PROGRESS.
{learned_section}
"""


# ─── Ollama ───────────────────────────────────────────────────────────────────
async def ask_ollama(messages):
    print(f"📤 Asking Ollama ({len(messages)} messages in history)...")
    response = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5-coder:7b",
        "messages": [{"role": "system", "content": build_system_prompt()}] + messages,
        "stream": False,
    })
    reply = response.json()["message"]["content"]
    print(f"📥 Ollama replied ({len(reply)} chars): {reply[:100]}...")
    return reply


async def maybe_learn_from_error(error_output):
    print("🧠 Analysing error for reusable rule...")
    response = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5-coder:7b",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You analyse errors and extract reusable rules to avoid them in future "
                    "ONLY IF THERE'S A HIGH CHANCE THIS ERROR WILL HAPPEN AGAIN ONCE FIXED. "
                    "Reply with ONLY a single short rule starting with ALWAYS or NEVER, "
                    "or reply SKIP if it's not a reusable systemic rule. No explanation."
                ),
            },
            {
                "role": "user",
                "content": f"This error occurred:\n{error_output}\nWhat rule should I add to avoid this forever?",
            },
        ],
        "stream": False,
    })
    rule = response.json()["message"]["content"].strip()
    if not rule.startswith("SKIP") and (rule.startswith("ALWAYS") or rule.startswith("NEVER")):
        save_learned_rule(rule)
        return rule
    return None


# ─── GitHub deploy ────────────────────────────────────────────────────────────
async def deploy_to_github(update, project_name):
    project_path = f"{PROJECTS_DIR}/{project_name}"
    print(f"🚀 Deploying {project_name} to GitHub...")
    for cmd in [
        f"cd {project_path} && git init",
        f"cd {project_path} && git add .",
        f'cd {project_path} && git commit -m "Initial commit - deployed by telegram bot"',
        f"cd {project_path} && gh repo create {project_name} --public --source=. --remote=origin --push 2>&1",
    ]:
        output, _ = run_command(cmd)
        print(f"📟 {output[:100]}")
    await update.message.reply_text(
        f"✅ Pushed to GitHub!\n🔗 https://github.com/{GITHUB_USERNAME}/{project_name}"
    )


# ─── Main message handler ─────────────────────────────────────────────────────
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        await update.message.reply_text("⛔ You are not authorised to use this bot.")
        return

    user_input = update.message.text
    user       = update.message.from_user.username or update.message.from_user.first_name
    chat_id    = update.message.chat_id
    print(f"\n📩 From @{user}: {user_input}")

    # ── Deployment confirmation shortcuts ──────────────────────────────────────
    if user_input.strip().upper() in {"YES", "CONFIRM", "OK", "DEPLOY", "PUSH"}:
        if chat_id in pending_confirmation:
            project = pending_confirmation.pop(chat_id)
            await update.message.reply_text(f"🚀 Deploying {project} to GitHub...")
            await deploy_to_github(update, project)
            return

    if user_input.strip().upper() in {"NO", "CANCEL", "SKIP"}:
        if chat_id in pending_confirmation:
            pending_confirmation.pop(chat_id)
            await update.message.reply_text("❌ Deployment cancelled. Project is still running locally.")
            return

    # ── Typing indicator + add to history ─────────────────────────────────────
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    append_history(chat_id, "user", user_input)
    await update.message.reply_text("🤔 Working on it...")

    # ── First Ollama call ──────────────────────────────────────────────────────
    reply = await ask_ollama(get_history(chat_id))
    append_history(chat_id, "assistant", reply)

    # ── Execution + auto-fix loop ──────────────────────────────────────────────
    attempt = 0
    while attempt < MAX_FIX_ATTEMPTS:
        cmds = extract_tags(reply, "CMD")
        if not cmds:
            break

        all_outputs = []
        has_error   = False

        for cmd in cmds:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            output, returncode = run_command(cmd.strip())
            all_outputs.append(f"$ {cmd.strip()}\n{output}")
            if returncode != 0 and output != "TIMEOUT":
                has_error = True

        # Register project metadata from tags
        pids_tagged     = extract_tags(reply, "PID")
        projects_tagged = extract_tags(reply, "PROJECT")
        urls_tagged     = extract_tags(reply, "URL")
        if projects_tagged:
            pname = projects_tagged[0].strip()
            port  = ""
            if urls_tagged:
                m = re.search(r':(\d{2,5})', urls_tagged[0])
                port = m.group(1) if m else ""
            running_projects[pname] = {
                "pid":     pids_tagged[0].strip() if pids_tagged else None,
                "port":    port,
                "started": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "path":    f"{PROJECTS_DIR}/{pname}",
            }

        # Send progress to Telegram
        progress = f"⚙️ *Attempt {attempt + 1}/{MAX_FIX_ATTEMPTS}:*\n" + "\n\n".join(all_outputs)
        for i in range(0, len(progress), 4096):
            await update.message.reply_text(progress[i:i + 4096])

        if has_error:
            attempt += 1
            new_rule = await maybe_learn_from_error("\n".join(all_outputs))
            if new_rule:
                await update.message.reply_text(f"🧠 *Learned:* {new_rule}", parse_mode="Markdown")
            append_history(chat_id, "user",
                f"There were errors:\n{chr(10).join(all_outputs)}\nPlease fix and try again.")
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            reply = await ask_ollama(get_history(chat_id))
            append_history(chat_id, "assistant", reply)
        else:
            break

    if attempt >= MAX_FIX_ATTEMPTS:
        await update.message.reply_text(
            f"😓 Reached max {MAX_FIX_ATTEMPTS} fix attempts. Want me to try a different approach?"
        )
        return

    # ── Clean final reply ──────────────────────────────────────────────────────
    final_text = clean_reply(reply)
    if final_text:
        for i in range(0, len(final_text), 4096):
            await update.message.reply_text(final_text[i:i + 4096])

    # ── URL ────────────────────────────────────────────────────────────────────
    urls = extract_tags(reply, "URL")
    if urls:
        await update.message.reply_text(f"🌐 Live at: {urls[0]}")

    # ── GitHub deploy prompt ───────────────────────────────────────────────────
    if "<READY_TO_DEPLOY>" in reply:
        projects     = extract_tags(reply, "PROJECT")
        project_name = projects[0].strip() if projects else "myproject"
        pending_confirmation[chat_id] = project_name
        await update.message.reply_text(
            f"🚀 *{project_name}* is working!\n\nPush to GitHub?\nReply *YES* to deploy or *NO* to skip.",
            parse_mode="Markdown",
        )


# ─── Startup ──────────────────────────────────────────────────────────────────
os.makedirs(PROJECTS_DIR, exist_ok=True)
print("🚀 Autonomous agent bot starting...")
print(f"📁 Projects dir: {PROJECTS_DIR}")

learned = load_learned_rules()
print(f"📚 Loaded learned rules:\n{learned}" if learned else "📚 No learned rules yet")
print(f"🔒 Whitelist: {ALLOWED_USER_IDS}" if ALLOWED_USER_IDS else "⚠️  No whitelist — open to everyone")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("help",     handle_help))
app.add_handler(CommandHandler("reset",    handle_reset))
app.add_handler(CommandHandler("list",     handle_list))
app.add_handler(CommandHandler("stop",     handle_stop))
app.add_handler(CommandHandler("logs",     handle_logs))
app.add_handler(CommandHandler("status",   handle_status))
app.add_handler(CommandHandler("remember", handle_remember))
app.add_handler(MessageHandler(filters.TEXT, handle))
print("✅ Ready! Waiting for your ideas...\n")
app.run_polling()