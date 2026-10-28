"""Phase 1 — single product entry.

Starts the kernel HTTP server and opens an embedded shell when possible
(pywebview), else the system browser — still one process tree / one command.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from verdance_kernel.api import CampaignKernel
from verdance_kernel.bar_bridge import BarBridge
from verdance_kernel.paths import showoff_dir
from verdance_kernel.server import make_handler


def reclaim_kernel_port(host: str = "127.0.0.1", port: int = 8770) -> list[int]:
    """Stop stale verdance_kernel listeners on *port* so PLAY owns the hub.

    After a reboot / RESET / abandoned PLAY window, an old kernel often keeps
    :8770. A second PLAY then either fails to bind or (on Windows with reuse)
    shares the port — and the browser keeps showing yesterday's campaign.
    """
    killed: list[int] = []
    self_pid = os.getpid()
    try:
        import subprocess

        # Prefer PowerShell on Windows — reliable Listen PID + command line.
        if os.name == "nt":
            ps = (
                f"$conns = Get-NetTCPConnection -LocalPort {int(port)} "
                f"-State Listen -ErrorAction SilentlyContinue; "
                f"foreach ($c in @($conns)) {{ "
                f"  $p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" "
                f"-ErrorAction SilentlyContinue; "
                f"  if ($p -and $p.CommandLine -match 'verdance_kernel') {{ "
                f"    Write-Output $c.OwningProcess "
                f"  }} "
                f"}}"
            )
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    ps,
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            pids: list[int] = []
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.append(int(line))
        else:
            pids = []
            try:
                import socket

                # Best-effort: if bind fails, we still raise below.
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind((host, port))
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        print(f"[launcher] port reclaim probe failed ({e})", file=sys.stderr)
        return killed

    for pid in sorted(set(pids)):
        if pid <= 0 or pid == self_pid:
            continue
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                os.kill(pid, 15)
            killed.append(pid)
            print(f"[launcher] stopped stale kernel PID {pid} on :{port}")
        except Exception as e:  # noqa: BLE001
            print(f"[launcher] could not stop PID {pid}: {e}", file=sys.stderr)

    if killed:
        # Brief pause so the OS releases the listen socket.
        time.sleep(0.4)
    return killed


def _try_webview(url: str, title: str = "Verdance's Ashes") -> bool:
    try:
        import webview  # type: ignore
    except ImportError:
        return False
    try:
        webview.create_window(
            title,
            url,
            width=1280,
            height=800,
            background_color="#040907",
        )
        webview.start()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[launcher] webview failed ({e}); falling back to browser", file=sys.stderr)
        return False


def _bar_mod_banner(workspace: Path) -> None:
    """Print which tree BAR will load for VerdanceAshes.sdd (deployed vs workspace)."""
    try:
        from verdance_kernel.sortie import find_bar_data_root

        # The configured root (verdance_config.json) is the truth; detection only when unset.
        root = find_bar_data_root(workspace)
        if not root:
            print("BAR data root: not found. Run SETUP.bat (it asks for the path when it cannot detect BAR).", file=sys.stderr)
            return
        print(f"BAR data root: {root}")
        mod_dest = Path(root) / "games" / "VerdanceAshes.sdd"
        deployed = Path.home() / "Documents" / "My Games" / "VerdanceAshes" / "mod" / "VerdanceAshes.sdd"
        workspace_mod = workspace / "mod" / "VerdanceAshes.sdd"
        if not mod_dest.exists():
            print(f"BAR mod: not installed yet at {mod_dest} (SETUP.bat installs it; every Drop re-copies it)", file=sys.stderr)
            return
        # Junction/symlink: resolve(); plain dir resolves to itself.
        target = mod_dest.resolve()
        deployed_r = deployed.resolve() if deployed.exists() else None
        workspace_r = workspace_mod.resolve() if workspace_mod.exists() else None
        mode = "CUSTOM"
        if deployed_r and target == deployed_r:
            mode = "DEPLOYED"
        elif workspace_r and target == workspace_r:
            mode = "WORKSPACE"
        print(f"BAR mod mode: {mode}")
        print(f"BAR mod loads: {target}")
        # Pass five: every Drop re-copies the workspace mod into data\games (CUSTOM = that copy).
        # Whatever is there now is replaced on the next Drop; the workspace is the truth.
        if mode == "DEPLOYED":
            print("NOTE: data\\games currently points at the My Games install; the next Drop replaces it with a copy of the workspace mod.")
        else:
            print("Drop Lua: copied from the workspace on every Drop.")
    except Exception as e:  # noqa: BLE001
        print(f"BAR mod banner skipped ({e})", file=sys.stderr)


def launch(
    workspace: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    no_ui: bool = False,
    prefer_browser: bool = False,
    enable_bridge: bool = True,
    rebuild: bool = True,
) -> int:
    kernel = CampaignKernel(workspace)
    showoff = showoff_dir(kernel.ws)
    if not (showoff / "index.html").is_file():
        print(f"ERROR: missing {showoff / 'index.html'}", file=sys.stderr)
        return 2

    _bar_mod_banner(Path(kernel.ws))

    # A fresh clone / unzip has no campaign yet; the rebuild below would fail with a
    # message about war_map.json. Say the one true thing instead.
    state_file = Path(kernel.ws) / "state" / "campaign_state.json"
    if rebuild and not state_file.is_file() and not (Path(kernel.ws) / "outbox" / "war_map.json").is_file():
        print(
            f"ERROR: no campaign yet ({state_file} missing).\n"
            f"  Run SETUP.bat once: it finds BAR, installs the mutator and writes mission 1.\n"
            f"  Then run PLAY.bat again.",
            file=sys.stderr,
        )
        return 5

    # PLAY is the product entry point, so refresh the hub every time. Leaving
    # hub_state.json untouched made a fresh launch show yesterday's first
    # recommendation even though the campaign state and compiler had moved on.
    # No stale-surface fallback: a broken rebuild must fail loud, not revive
    # yesterday's Sortie N paint over a wiped campaign_state.
    if rebuild:
        print("Refreshing campaign hub…")
    try:
        if rebuild:
            kernel.rebuild_hub()
    except Exception as e:  # noqa: BLE001
        print(
            f"ERROR: hub refresh failed ({e}).\n"
            f"  Refusing to open the last readable surface — that hid real bugs\n"
            f"  and could paint an old sortie over a RESET campaign.\n"
            f"  Fix the rebuild, then run PLAY.bat again.",
            file=sys.stderr,
        )
        return 4

    if enable_bridge:
        BarBridge(kernel).start()

    reclaim_kernel_port(host, port)

    handler = make_handler(kernel, showoff)
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as e:
        print(
            f"ERROR: cannot bind {host}:{port} ({e}).\n"
            f"  Another process still owns the hub port. Close the other PLAY window,\n"
            f"  or run RESET.bat then PLAY.bat again.",
            file=sys.stderr,
        )
        return 3
    url = f"http://{host}:{port}/"

    def _serve() -> None:
        try:
            server.serve_forever()
        except Exception:  # noqa: BLE001
            pass

    thread = threading.Thread(target=_serve, name="va-kernel-http", daemon=True)
    thread.start()

    # Wait until port answers
    ready = False
    for _ in range(40):
        try:
            import urllib.request

            with urllib.request.urlopen(url + "api/status", timeout=0.4) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:  # noqa: BLE001
            time.sleep(0.1)
    if not ready:
        print(f"WARNING: kernel may not be ready at {url}", file=sys.stderr)

    print("")
    print("  ============================================================")
    print("   VERDANCE'S ASHES")
    print("   The green is dying. Ashwalkers hold the line.")
    print("  ============================================================")
    print(f"   Kernel:  {url}")
    print(f"   Bridge:  {'on (auto bring-home)' if enable_bridge else 'off'}")
    print("   Stop:    close this window / Ctrl+C")
    print("  ============================================================")
    print("")

    if no_ui:
        try:
            while thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    else:
        used_webview = False
        if not prefer_browser:
            used_webview = _try_webview(url)
        if not used_webview:
            webbrowser.open(url)
            print(f"Opened browser → {url}")
            print("(Optional: pip install pywebview for an embedded window)")
            try:
                while thread.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass

    print("\nShutting down kernel…")
    if kernel._bridge is not None:
        try:
            kernel._bridge.stop()
        except Exception:  # noqa: BLE001
            pass
    server.shutdown()
    server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verdance's Ashes — product launcher")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--no-ui", action="store_true", help="Kernel only, no browser/webview")
    ap.add_argument("--browser", action="store_true", help="Force system browser (skip webview)")
    ap.add_argument("--no-bridge", action="store_true", help="Disable BAR auto-apply bridge")
    ap.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Skip hub rebuild on start (does not re-apply the last result)",
    )
    args = ap.parse_args(argv)
    return launch(
        args.workspace,
        host=args.host,
        port=args.port,
        no_ui=args.no_ui,
        prefer_browser=args.browser,
        enable_bridge=not args.no_bridge,
        rebuild=not args.no_rebuild,
    )


if __name__ == "__main__":
    raise SystemExit(main())
