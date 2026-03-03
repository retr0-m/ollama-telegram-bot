
import requests
import subprocess
import re
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes, CommandHandler
from config import *


history = []
pending_confirmation = {}

LEARNED_RULES_FILE = os.path.expanduser(LEARNED_RULES_FILE_PATH)

def load_learned_rules():
    if os.path.exists(LEARNED_RULES_FILE):
        with open(LEARNED_RULES_FILE, "r") as f:
            return f.read().strip()
    return ""

def save_reminder(rule):
    with open(LEARNED_RULES_FILE, "a") as f:
        f.write(f"- {rule}\n")
    print(f"🧠 Learned new rule: {rule}")

def save_learned_rule(rule):
    with open(REMEMBER_FILE_PATH, "a") as f:
        f.write(f"- {rule}\n")
    print(f"🧠 Learned new rule: {rule}")

def build_system_prompt():
    learned = load_learned_rules()
    learned_section = f"\nLEARNED FROM PAST ERRORS (ALWAYS FOLLOW THESE):\n{learned}" if learned else ""
    return f"""You are an autonomous coding agent running on Ubuntu Server 22.04.
Your job is to take an idea and fully implement it: plan, write, debug, test and deploy.
Dont give me instructions, just do the work and show me the progress with CMD commands.

RULES:
- Always wrap shell commands in <CMD> tags: <CMD>command here</CMD>
- Always wrap project name in <PROJECT> tags: <PROJECT>myprojectname</PROJECT> 
- Always wrap deployment URL in <URL> tags if applicable: <URL>http://{SERVER_IP}:PORT</URL>
- ALWAYS create the project directory first: <CMD>mkdir -p {PROJECTS_DIR}/PROJECTNAME</CMD> - replace PROJECTNAME with the actual name, if none was given simple a good name for it.
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
- You're running on a Ubuntu server 22.04 LTS on a 8gb DDR3 mac mini.
- DONT GIVE ME INSTRUCTIONS, JUST DO THE JOB WITH CMD COMMANDS AND SHOW ME THE PROGRESS.

{learned_section}
"""


def run_command(cmd, timeout=60):
    print(f"⚙️  Running: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout
        )
        output = (result.stdout + result.stderr).strip()
        print(f"📟 Output: {output[:200]}")
        return output, result.returncode
    except subprocess.TimeoutExpired:
        print("⏱️  Command timed out")
        return "TIMEOUT", 1


def extract_tags(text, tag):
    return re.findall(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)


def clean_reply(text):
    text = re.sub(r'<CMD>.*?</CMD>', '', text, flags=re.DOTALL)
    text = re.sub(r'<PROJECT>.*?</PROJECT>', '', text, flags=re.DOTALL)
    text = re.sub(r'<URL>.*?</URL>', '', text, flags=re.DOTALL)
    text = re.sub(r'<READY_TO_DEPLOY>', '', text)
    text = re.sub(r'<DEPLOYED>', '', text)
    return text.strip()


async def ask_ollama(messages):
    print(f"📤 Asking Ollama (history: {len(messages)} messages)...")
    response = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5-coder:7b",
        "messages": [{"role": "system", "content": build_system_prompt()}] + messages,
        "stream": False
    })
    reply = response.json()["message"]["content"]
    print(f"📥 Ollama replied ({len(reply)} chars): {reply[:100]}...")
    return reply


async def maybe_learn_from_error(error_output):
    print("🧠 Analyzing error for reusable rule...")
    response = requests.post("http://localhost:11434/api/chat", json={
        "model": "qwen2.5-coder:7b",
        "messages": [
            {
                "role": "system",
                "content": "You analyze errors and extract reusable rules to avoid them in future ONLY IF THERE'S A HIGH CHANCE THIS ERROR WILL HAPPEN AGAIN ONCE FIXED. Reply with ONLY a single short rule starting with ALWAYS or NEVER, or reply SKIP if it's not a reusable systemic rule. No explanation, just the rule or SKIP."
            },
            {
                "role": "user",
                "content": f"This error occurred:\n{error_output}\nWhat rule should I add to avoid this forever?"
            }
        ],
        "stream": False
    })
    rule = response.json()["message"]["content"].strip()
    if not rule.startswith("SKIP") and (rule.startswith("ALWAYS") or rule.startswith("NEVER")):
        save_learned_rule(rule)
        return rule
    return None


async def deploy_to_github(update, project_name):
    project_path = f"{PROJECTS_DIR}/{project_name}"
    print(f"🚀 Deploying {project_name} to GitHub...")

    commands = [
        f"cd {project_path} && git init",
        f"cd {project_path} && git add .",
        f'cd {project_path} && git commit -m "Initial commit - deployed by telegram bot"',
        f"cd {project_path} && gh repo create {project_name} --public --source=. --remote=origin --push 2>&1"
    ]

    outputs = []
    for cmd in commands:
        output, code = run_command(cmd)
        outputs.append(f"$ {cmd}\n{output}")
        print(f"📟 {output[:100]}")

    repo_url = f"https://github.com/{GITHUB_USERNAME}/{project_name}"
    await update.message.reply_text(
        f"✅ Pushed to GitHub!\n🔗 {repo_url}"
    )

async def handle_remember(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.replace("/remember", "").strip()
    if not text:
        await update.message.reply_text("❓ Usage: /remember ALWAYS use port 8080 for flask apps")
        return
    save_reminder(text)
    await update.message.reply_text(f"🧠 Got it! I'll remember:\n- {text}")


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    user = update.message.from_user.username or update.message.from_user.first_name
    chat_id = update.message.chat_id

    print(f"\n📩 From @{user}: {user_input}")

    # Handle deployment confirmation
    if user_input.strip().upper() in ["YES", "CONFIRM", "OK", "DEPLOY", "PUSH"]:
        if chat_id in pending_confirmation:
            project = pending_confirmation.pop(chat_id)
            await update.message.reply_text(f"🚀 Deploying {project} to GitHub...")
            await deploy_to_github(update, project)
            return

    if user_input.strip().upper() in ["NO", "CANCEL", "SKIP"]:
        if chat_id in pending_confirmation:
            pending_confirmation.pop(chat_id)
            await update.message.reply_text("❌ Deployment cancelled. Project is still running locally.")
            return

    history.append({"role": "user", "content": user_input})
    await update.message.reply_text("🤔 Working on it...")

    # Get initial response
    reply = await ask_ollama(history)
    history.append({"role": "assistant", "content": reply})

    # Execution and auto-fix loop
    attempt = 0
    while attempt < MAX_FIX_ATTEMPTS:
        cmds = extract_tags(reply, "CMD")
        if not cmds:
            print("ℹ️  No commands found in reply")
            break

        all_outputs = []
        has_error = False

        for cmd in cmds:
            cmd = cmd.strip()
            output, returncode = run_command(cmd)
            all_outputs.append(f"$ {cmd}\n{output}")
            if returncode != 0 and output != "TIMEOUT":
                has_error = True

        # Send progress to Telegram
        progress = f"⚙️ *Attempt {attempt + 1}/{MAX_FIX_ATTEMPTS}:*\n" + "\n\n".join(all_outputs)
        if len(progress) > 4096:
            progress = progress[:4096]
        await update.message.reply_text(progress)

        if has_error:
            attempt += 1
            print(f"🐛 Error detected, fix attempt {attempt}/{MAX_FIX_ATTEMPTS}")

            # Try to learn from this error
            new_rule = await maybe_learn_from_error("\n".join(all_outputs))
            if new_rule:
                await update.message.reply_text(f"🧠 *Learned:* {new_rule}", parse_mode="Markdown")

            error_context = f"There were errors:\n{chr(10).join(all_outputs)}\nPlease fix and try again."
            history.append({"role": "user", "content": error_context})
            reply = await ask_ollama(history)
            history.append({"role": "assistant", "content": reply})
        else:
            break

    if attempt >= MAX_FIX_ATTEMPTS:
        await update.message.reply_text(
            f"😓 Reached max {MAX_FIX_ATTEMPTS} fix attempts. Want me to try a different approach?"
        )
        return

    # Send clean final reply
    final_text = clean_reply(reply)
    if final_text:
        if len(final_text) > 4096:
            for i in range(0, len(final_text), 4096):
                await update.message.reply_text(final_text[i:i+4096])
        else:
            await update.message.reply_text(final_text)

    # Send URL if found
    urls = extract_tags(reply, "URL")
    if urls:
        await update.message.reply_text(f"🌐 Live at: {urls[0]}")

    # Ask for GitHub deployment confirmation
    if "<READY_TO_DEPLOY>" in reply:
        projects = extract_tags(reply, "PROJECT")
        project_name = projects[0].strip() if projects else "myproject"
        pending_confirmation[chat_id] = project_name
        await update.message.reply_text(
            f"🚀 *{project_name}* is working!\n\nPush to GitHub?\nReply *YES* to deploy or *NO* to skip.",
            parse_mode="Markdown"
        )


# Startup
os.makedirs(PROJECTS_DIR, exist_ok=True)
print("🚀 Autonomous agent bot starting...")
print(f"📁 Projects dir: {PROJECTS_DIR}")
print(f"🧠 Learned rules file: {LEARNED_RULES_FILE}")
learned = load_learned_rules()
if learned:
    print(f"📚 Loaded learned rules:\n{learned}")
else:
    print("📚 No learned rules yet")

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT, handle))
app.add_handler(CommandHandler("remember", handle_remember))
print("✅ Ready! Waiting for your ideas...\n")
app.run_polling()
