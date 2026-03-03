"""
state/memory.py
───────────────
Two rule stores:
  • rules.txt     — user-supplied via /remember
  • learned.txt   — auto-extracted from errors by Ollama
Both are loaded and injected into every system prompt.
"""

import os
from config import RULES_FILE, LEARNED_FILE


def _read(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return ""


def _append(path: str, line: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(f"- {line}\n")


# ─── User rules (/remember) ──────────────────────────────────────────────────

def save_rule(rule: str):
    _append(RULES_FILE, rule)


def load_rules() -> str:
    return _read(RULES_FILE)


# ─── Auto-learned rules ───────────────────────────────────────────────────────

def save_learned(rule: str):
    _append(LEARNED_FILE, rule)


def load_learned() -> str:
    return _read(LEARNED_FILE)


# ─── Combined (used by prompt builder) ───────────────────────────────────────

def all_rules() -> str:
    """Return all rules from both files, deduplicated, ready to inject."""
    parts = []
    user    = load_rules()
    learned = load_learned()
    if user:
        parts.append(f"USER RULES:\n{user}")
    if learned:
        parts.append(f"LEARNED FROM PAST ERRORS:\n{learned}")
    return "\n\n".join(parts)
