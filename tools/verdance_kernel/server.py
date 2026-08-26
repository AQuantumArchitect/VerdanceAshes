"""HTTP face for the campaign kernel (Phase 1 shell transport).

Same endpoints as hub_host_v1 so the HTML map keeps working.
"""
from __future__ import annotations

import json
import mimetypes
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from verdance_kernel.api import CampaignKernel
from verdance_kernel.bar_bridge import BarBridge
from verdance_kernel.paths import showoff_dir


def _json_bytes(obj: Any, code: int = 200) -> tuple[int, bytes, str]:
    body = json.dumps(obj, indent=2).encode("utf-8")
    return code, body, "application/json; charset=utf-8"


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    n = int(handler.headers.get("Content-Length") or 0)
    raw = handler.rfile.read(n) if n else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def make_handler(kernel: CampaignKernel, showoff: Path):
    class KernelHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            sys.stderr.write("[kernel] " + (fmt % args) + "\n")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send(204, b"", "text/plain")

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/api/status":
                code, body, ct = _json_bytes(kernel.status())
                return self._send(code, body, ct)

            if path == "/api/session":
                code, body, ct = _json_bytes(kernel.session_status())
                return self._send(code, body, ct)

            if path == "/api/hub-state":
                code, body, ct = _json_bytes(kernel.get_hub_surface())
                return self._send(code, body, ct)

            if path == "/api/result":
                code, body, ct = _json_bytes(kernel.get_result())
                return self._send(code, body, ct)

            if path == "/api/phases":
                from verdance_kernel.phases import phase_status

                code, body, ct = _json_bytes(phase_status())
                return self._send(code, body, ct)

            if path == "/api/steam":
                from verdance_kernel import steam as steam_mod

                code, body, ct = _json_bytes(steam_mod.status(kernel.ws))
                return self._send(code, body, ct)

            if path == "/api/surface":
                code, body, ct = _json_bytes(kernel.write_campaign_surface())
                return self._send(code, body, ct)

            rel = path.lstrip("/") or "index.html"
            if ".." in rel:
                return self._send(400, b"bad path", "text/plain")
            target = (showoff / rel).resolve()
            if not str(target).startswith(str(showoff.resolve())):
                return self._send(403, b"forbidden", "text/plain")
            if not target.is_file():
                return self._send(404, b"not found", "text/plain")
            data = target.read_bytes()
            ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
            if target.suffix == ".js":
                ctype = "application/javascript; charset=utf-8"
            elif target.suffix == ".html":
                ctype = "text/html; charset=utf-8"
            return self._send(200, data, ctype)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query or "")

            if path == "/api/rebuild-hub":
                code, body, ct = _json_bytes(kernel.rebuild_hub())
                return self._send(code, body, ct)

            if path == "/api/advance":
                try:
                    body_in = _read_json_body(self)
                except Exception:
                    body_in = {}
                extract = qs.get("extract", ["1"])[0] not in ("0", "false", "no")
                if isinstance(body_in.get("extract"), bool):
                    extract = body_in["extract"]
                skip = qs.get("skipAdvance", ["0"])[0] in ("1", "true", "yes")
                if hasattr(kernel, "bring_home"):
                    result = kernel.bring_home(
                        extract=extract, skip_advance=skip, mode="manual"
                    )
                else:
                    result = kernel.apply_result(extract=extract, skip_advance=skip)
                code = 200 if result.get("ok") else 502
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/abandon":
                try:
                    body_in = _read_json_body(self)
                except Exception:
                    body_in = {}
                reason = str(
                    body_in.get("reason")
                    or (qs.get("reason") or ["player_abandon"])[0]
                    or "player_abandon"
                )
                if hasattr(kernel, "abandon_sortie"):
                    result = kernel.abandon_sortie(reason=reason)
                else:
                    result = {"ok": False, "error": "abandon not available"}
                code = 200 if result.get("ok") else 502
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/deploy":
                try:
                    plan = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                launch = qs.get("launch", ["0"])[0] in ("1", "true", "yes")
                if isinstance(plan.get("launch"), bool):
                    launch = plan.pop("launch")
                result = kernel.commit_deploy(plan, launch=launch)
                code = 200 if result.get("ok") else 502
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/purchase":
                try:
                    body_in = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                lid = (
                    body_in.get("listingId")
                    or body_in.get("id")
                    or (qs.get("listingId") or [None])[0]
                )
                result = kernel.purchase(str(lid) if lid else "")
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/home-build":
                result = kernel.home_build()
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            code, body, ct = _json_bytes({"ok": False, "error": "unknown endpoint"}, 404)
            return self._send(code, body, ct)

    return KernelHandler


def serve(
    workspace: str | Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
    open_browser: bool = False,
    enable_bridge: bool = True,
) -> int:
    """Blocking HTTP server. Returns exit code."""
    import webbrowser

    kernel = CampaignKernel(workspace)
    showoff = showoff_dir(kernel.ws)
    if not (showoff / "index.html").is_file():
        print(f"ERROR: missing {showoff / 'index.html'}", file=sys.stderr)
        return 2

    if enable_bridge:
        bridge = BarBridge(kernel)
        bridge.start()
        print("  BAR bridge: auto-apply watching")

    # Ensure hub + surface exist
    if not (showoff / "hub_state.json").is_file():
        print("  rebuilding hub_state…")
        kernel.rebuild_hub()
    else:
        try:
            kernel.write_campaign_surface()
        except Exception:  # noqa: BLE001
            pass

    handler = make_handler(kernel, showoff)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"Verdance kernel on {url}")
    print(f"  workspace: {kernel.ws}")
    print(f"  schema:    {kernel.status().get('schemaVersion')}")
    print("  Ctrl+C to stop")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nKernel stopped.")
    finally:
        if enable_bridge and kernel._bridge is not None:
            try:
                kernel._bridge.stop()
            except Exception:  # noqa: BLE001
                pass
        server.server_close()
    return 0
