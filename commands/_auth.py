"""
commands/_auth.py
──────────────────
Shared auth check. Import `is_allowed` in every command handler.
"""

from telegram import Update
from config import ALLOWED_USER_IDS


def is_allowed(update: Update) -> bool:
    """True if ALLOWED_USER_IDS is empty (open) or the user is whitelisted."""
    if not ALLOWED_USER_IDS:
        return True
    return update.message.from_user.id in ALLOWED_USER_IDS
