"""
tools/git.py
────────────
GitHub operations for the deploy step.
"""

from config import GITHUB_USERNAME
from .shell import run_in_project


def push_to_github(project_path: str, project_name: str) -> tuple[str, bool]:
    """
    Init repo, commit everything and push to a new public GitHub repo.
    Returns (message, success).
    Requires `gh` CLI to be authenticated on the server.
    """
    steps = [
        "git init",
        "git add .",
        'git commit -m "Initial commit — deployed via telegram bot"',
        f"gh repo create {project_name} --public --source=. --remote=origin --push 2>&1",
    ]
    output_lines = []
    for cmd in steps:
        out, rc = run_in_project(project_path, cmd)
        output_lines.append(f"$ {cmd}\n{out}")
        if rc != 0:
            return "\n".join(output_lines), False

    url = f"https://github.com/{GITHUB_USERNAME}/{project_name}"
    return url, True
