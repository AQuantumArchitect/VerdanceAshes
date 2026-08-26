"""Subprocess helpers shared by kernel ops."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any


def run_cmd(
    cmd: list[str],
    cwd: Path,
    *,
    timeout: int = 300,
) -> dict[str, Any]:
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
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


def run_py_tool(ws: Path, tool_name: str, args: list[str] | None = None, *, timeout: int = 120) -> dict[str, Any]:
    script = ws / "tools" / tool_name
    if not script.is_file():
        return {"ok": False, "reason": f"missing {tool_name}"}
    cmd = [sys.executable, str(script), *(args or [])]
    # Most tools take --workspace
    if "--workspace" not in (args or []):
        cmd.extend(["--workspace", str(ws)])
    return run_cmd(cmd, ws, timeout=timeout)
