"""Subprocess helpers shared by kernel ops."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from verdance.common import tools_env


def run_cmd(
    cmd: list[str],
    cwd: Path,
    *,
    timeout: int = 300,
    env: dict[str, str] | None = None,
    encoding: str | None = None,
) -> dict[str, Any]:
    # errors="replace": a child's stray byte must never fail the run that printed it
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding=encoding,
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout_tail": (r.stdout or "")[-2000:],
            "stderr_tail": (r.stderr or "")[-1200:],
            "cmd": cmd,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}", "cmd": cmd}


def run_ps1(script: Path, ws: Path, extra_args: list[str] | None = None, *, timeout: int = 240) -> dict[str, Any]:
    if not script.is_file():
        return {"ok": False, "reason": f"missing {script.name}"}
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Workspace",
        str(ws),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return run_cmd(cmd, ws, timeout=timeout)


def run_module(ws: Path, module: str, args: list[str] | None = None, *, workspace_flag: bool = True,
               timeout: int = 120) -> dict[str, Any]:
    """Run ``python -m <module>`` from the workspace with tools/ on the child's PYTHONPATH."""
    cmd = [sys.executable, "-m", module, *(args or [])]
    if workspace_flag and "--workspace" not in (args or []):
        cmd.extend(["--workspace", str(ws)])
    # A Python child prints UTF-8 whatever the console's code page (the PC's cp1252 could not print
    # the mission builder's "→" and the build failed, 2026-11-04).
    env = dict(tools_env(ws), PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return run_cmd(cmd, ws, timeout=timeout, env=env, encoding="utf-8")
