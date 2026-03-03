"""
state/projects.py
─────────────────
Single source of truth for all project metadata.
Persists to data/projects.json so state survives bot restarts.

Schema of projects.json:
{
  "current": "myapp",          ← name of the active project (or null)
  "projects": {
    "myapp": {
      "name":    "myapp",
      "path":    "/home/.../projects/myapp",
      "pid":     "12345",       ← null if not running
      "port":    "8000",        ← null if unknown
      "status":  "running",     ← "running" | "stopped" | "error" | "ready"
      "started": "2025-01-01 12:00",
      "git_url": "https://github.com/user/myapp"  ← null if not pushed
    }
  }
}
"""

import json
import os
from datetime import datetime
from typing import Optional

from config import PROJECTS_DIR, PROJECTS_FILE


def _load() -> dict:
    if os.path.exists(PROJECTS_FILE):
        with open(PROJECTS_FILE) as f:
            return json.load(f)
    return {"current": None, "projects": {}}


def _save(data: dict):
    os.makedirs(os.path.dirname(PROJECTS_FILE), exist_ok=True)
    with open(PROJECTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ─── Read ─────────────────────────────────────────────────────────────────────

def all_projects() -> dict:
    """Return the full {name: info} dict."""
    return _load()["projects"]


def get_project(name: str) -> Optional[dict]:
    """Return project info dict or None."""
    return _load()["projects"].get(name)


def current_project() -> Optional[dict]:
    """Return the currently active project info, or None."""
    data = _load()
    name = data["current"]
    if name:
        return data["projects"].get(name)
    return None


def current_name() -> Optional[str]:
    return _load()["current"]


# ─── Write ────────────────────────────────────────────────────────────────────

def create_project(name: str) -> dict:
    """
    Register a new project and make it the current one.
    Creates the project directory on disk.
    Returns the new project info dict.
    """
    data = _load()
    path = os.path.join(PROJECTS_DIR, name)
    os.makedirs(path, exist_ok=True)

    project = {
        "name":    name,
        "path":    path,
        "pid":     None,
        "port":    None,
        "status":  "created",
        "started": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "git_url": None,
    }
    data["projects"][name] = project
    data["current"] = name
    _save(data)
    return project


def switch_project(name: str) -> bool:
    """Set the current project. Returns False if project doesn't exist."""
    data = _load()
    if name not in data["projects"]:
        return False
    data["current"] = name
    _save(data)
    return True


def delete_project(name: str) -> bool:
    """Remove a project from the registry (does NOT delete files). Returns False if not found."""
    data = _load()
    if name not in data["projects"]:
        return False
    data["projects"].pop(name)
    if data["current"] == name:
        # Fall back to most recently added remaining project, or None
        remaining = list(data["projects"].keys())
        data["current"] = remaining[-1] if remaining else None
    _save(data)
    return True


def update_project(name: str, **kwargs):
    """
    Patch any fields on an existing project.
    Usage: update_project("myapp", pid="1234", port="8000", status="running")
    """
    data = _load()
    if name in data["projects"]:
        data["projects"][name].update(kwargs)
        _save(data)
