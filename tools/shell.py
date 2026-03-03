"""
tools/shell.py
──────────────
Low-level shell helpers.
All command execution flows through here so we have a single
place to add timeouts, logging and output sanitising.
"""

import subprocess
from typing import Tuple


def run_command(cmd: str, timeout: int = 60) -> Tuple[str, int]:
    """
    Run a shell command, return (output, returncode).
    stdout + stderr are merged so errors are always captured.
    """
    print(f"⚙️  CMD: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=timeout,
        )
        output = (result.stdout + result.stderr).strip()
        print(f"    → rc={result.returncode}  {output[:120]}")
        return output, result.returncode
    except subprocess.TimeoutExpired:
        print(f"    → TIMEOUT after {timeout}s")
        return "TIMEOUT", 1


def run_in_project(project_path: str, cmd: str, timeout: int = 60) -> Tuple[str, int]:
    """Run a command inside a project directory."""
    return run_command(f"cd {project_path} && {cmd}", timeout=timeout)


def venv_python(project_path: str) -> str:
    """Return the path to the project's venv Python binary."""
    return f"{project_path}/venv/bin/python"


def venv_pip(project_path: str) -> str:
    """Return the path to the project's venv pip binary."""
    return f"{project_path}/venv/bin/pip"
