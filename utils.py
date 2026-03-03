import re
import subprocess
import os

from config import LEARNED_RULES_FILE_PATH, REMEMBER_FILE_PATH

LEARNED_RULES_FILE = os.path.expanduser(LEARNED_RULES_FILE_PATH)


# ─── Shell ───────────────────────────────────────────────────────────────────
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


# ─── Tag helpers ─────────────────────────────────────────────────────────────
def extract_tags(text, tag):
    return re.findall(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL)

def clean_reply(text):
    for tag in ("CMD", "PROJECT", "URL", "PID"):
        text = re.sub(rf'<{tag}>.*?</{tag}>', '', text, flags=re.DOTALL)
    text = re.sub(r'<READY_TO_DEPLOY>', '', text)
    text = re.sub(r'<DEPLOYED>', '', text)
    return text.strip()


# ─── Learned rules ───────────────────────────────────────────────────────────
def load_learned_rules():
    if os.path.exists(LEARNED_RULES_FILE):
        with open(LEARNED_RULES_FILE, "r") as f:
            return f.read().strip()
    return ""

def save_reminder(rule):
    """Persist a user-supplied /remember rule."""
    with open(LEARNED_RULES_FILE, "a") as f:
        f.write(f"- {rule}\n")
    print(f"🧠 Saved reminder: {rule}")

def save_learned_rule(rule):
    """Persist a rule auto-extracted from an error."""
    with open(REMEMBER_FILE_PATH, "a") as f:
        f.write(f"- {rule}\n")
    print(f"🧠 Learned new rule: {rule}")