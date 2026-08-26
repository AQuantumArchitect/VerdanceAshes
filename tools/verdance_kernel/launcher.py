"""Phase 1 — single product entry.

Starts the kernel HTTP server and opens an embedded shell when possible
(pywebview), else the system browser — still one process tree / one command.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from verdance_kernel.api import CampaignKernel
from verdance_kernel.bar_bridge import BarBridge
from verdance_kernel.paths import showoff_dir
from verdance_kernel.server import make_handler


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


def launch(
    workspace: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    no_ui: bool = False,
    prefer_browser: bool = False,
    enable_bridge: bool = True,
) -> int:
    kernel = CampaignKernel(workspace)
    showoff = showoff_dir(kernel.ws)
    if not (showoff / "index.html").is_file():
        print(f"ERROR: missing {showoff / 'index.html'}", file=sys.stderr)
        return 2

    if enable_bridge:
        BarBridge(kernel).start()

    if not (showoff / "hub_state.json").is_file():
        print("Rebuilding hub…")
        kernel.rebuild_hub()
    else:
        try:
            kernel.write_campaign_surface()
        except Exception:  # noqa: BLE001
            pass

    handler = make_handler(kernel, showoff)
    server = ThreadingHTTPServer((host, port), handler)
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
    args = ap.parse_args(argv)
    return launch(
        args.workspace,
        host=args.host,
        port=args.port,
        no_ui=args.no_ui,
        prefer_browser=args.browser,
        enable_bridge=not args.no_bridge,
    )


if __name__ == "__main__":
    raise SystemExit(main())
