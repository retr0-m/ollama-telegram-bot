import os

# ─── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN            = os.getenv("TELEGRAM_TOKEN", "your token goes here")
ALLOWED_USER_IDS  = []

# ─── Ollama ───────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL   = "http://localhost:11434"
OLLAMA_MODEL      = "qwen2.5-coder:7b"
MAX_FIX_ATTEMPTS  = 8
MAX_HISTORY_MSGS  = 20

# ─── Server ──────────────────────────────────────────────────────────────────
SERVER_IP         = os.getenv("SERVER_IP", "192.168.180.61")
GITHUB_USERNAME   = os.getenv("GITHUB_USERNAME", "retr0-m")

# ─── Filesystem ──────────────────────────────────────────────────────────────
BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR      = os.getenv("PROJECTS_DIR", "/home/retr0srv/ollama/projects")
DATA_DIR          = os.path.join(BASE_DIR, "data")

PROJECTS_FILE     = os.path.join(DATA_DIR, "projects.json")
RULES_FILE        = os.path.join(DATA_DIR, "rules.txt")
LEARNED_FILE      = os.path.join(DATA_DIR, "learned.txt")

# ─── Dashboard ───────────────────────────────────────────────────────────────
DASHBOARD_HOST    = "0.0.0.0"
DASHBOARD_PORT    = 7000