"""
agent/ollama.py
───────────────
Thin wrapper around the Ollama /api/chat endpoint.
All model calls go through here.
"""

import requests
from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from agent.prompt import build_system_prompt


def chat(messages: list[dict]) -> str:
    """
    Send a conversation to Ollama and return the assistant reply string.
    `messages` is a list of {"role": ..., "content": ...} dicts (no system msg).
    The system prompt is always injected fresh so it reflects the current project.
    """
    print(f"📤 Ollama ← {len(messages)} messages")
    payload = {
        "model":    OLLAMA_MODEL,
        "messages": [{"role": "system", "content": build_system_prompt()}] + messages,
        "stream":   False,
    }
    resp  = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120)
    reply = resp.json()["message"]["content"]
    print(f"📥 Ollama → {len(reply)} chars: {reply[:80]}...")
    return reply


def extract_rule_from_error(error_output: str) -> str | None:
    """
    Ask Ollama to distil an error into a reusable ALWAYS/NEVER rule.
    Returns the rule string or None if not applicable.
    """
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json={
        "model":  OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You analyse shell errors and extract one reusable rule to prevent recurrence. "
                    "Reply with ONLY a single line starting with ALWAYS or NEVER. "
                    "Reply SKIP if the error is one-off and not worth a permanent rule. No explanation."
                ),
            },
            {
                "role": "user",
                "content": f"Error output:\n{error_output}\n\nWhat rule prevents this permanently?",
            },
        ],
    }, timeout=60)
    rule = resp.json()["message"]["content"].strip()
    if rule.startswith(("ALWAYS", "NEVER")):
        return rule
    return None
