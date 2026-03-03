"""
dashboard/app.py
─────────────────
FastAPI + uvicorn dashboard.
Started as a background process when the bot launches.
Shows all registered projects, their status, and live log tails.

Start manually: uvicorn dashboard.app:app --host 0.0.0.0 --port 7000
"""

import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from state.projects import all_projects
from tools.filesystem import find_log, tail_file

app = FastAPI(title="Ollama Bot Dashboard", docs_url=None, redoc_url=None)


# ─── API endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/projects")
async def api_projects():
    """Return all project metadata as JSON."""
    return JSONResponse(content=all_projects())


@app.get("/api/projects/{name}/logs")
async def api_logs(name: str, lines: int = 50):
    """Return last N log lines for a project."""
    proj = all_projects().get(name)
    if not proj:
        return JSONResponse(status_code=404, content={"error": "Project not found"})
    log_path = find_log(proj["path"])
    if not log_path:
        return JSONResponse(content={"log": "", "path": None})
    return JSONResponse(content={"log": tail_file(log_path, lines), "path": log_path})


# ─── HTML dashboard ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Render the main dashboard page."""
    tmpl_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(tmpl_path) as f:
        return f.read()
