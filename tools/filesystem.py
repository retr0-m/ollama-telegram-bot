"""
tools/filesystem.py
───────────────────
Explicit filesystem operations available to the agent.

The agent uses <CMD> tags for shell commands, but these helpers
are called directly from Python (e.g. when the agent asks to
read a file before editing it, or we need to inspect a project).
"""

import os
import shutil
from typing import List, Optional


def read_file(path: str) -> Optional[str]:
    """Read and return file contents, or None if it doesn't exist."""
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def write_file(path: str, content: str):
    """Write content to a file, creating parent directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def append_file(path: str, content: str):
    """Append content to a file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(content)


def list_dir(path: str, recursive: bool = False) -> List[str]:
    """
    List files in a directory.
    Returns relative paths. Skips venv/, __pycache__/, .git/.
    """
    SKIP = {"venv", "__pycache__", ".git", "node_modules", ".mypy_cache"}
    results = []
    if not os.path.isdir(path):
        return results

    if recursive:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP]
            for f in files:
                abs_path = os.path.join(root, f)
                results.append(os.path.relpath(abs_path, path))
    else:
        for entry in os.scandir(path):
            if entry.name not in SKIP:
                results.append(entry.name + ("/" if entry.is_dir() else ""))

    return sorted(results)


def delete_path(path: str) -> bool:
    """Delete a file or directory tree. Returns True on success."""
    if not os.path.exists(path):
        return False
    if os.path.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)
    return True


def tail_file(path: str, lines: int = 50) -> str:
    """Return last N lines of a file, or an empty string."""
    if not os.path.exists(path):
        return ""
    with open(path) as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


def find_log(project_path: str) -> Optional[str]:
    """Find the most likely log file inside a project directory."""
    candidates = ["app.log", "uvicorn.log", "server.log", "run.log"]
    for name in candidates:
        p = os.path.join(project_path, name)
        if os.path.exists(p):
            return p
    # Fall back to first .log found
    for root, _, files in os.walk(project_path):
        for f in files:
            if f.endswith(".log"):
                return os.path.join(root, f)
    return None
