"""HTTP face for the campaign kernel (Phase 1 shell transport).

Serves the hub (app/showoff) and the /api/* endpoints the HTML map calls.
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

            if path == "/api/narrative":
                code, body, ct = _json_bytes(kernel.narrative_surface())
                return self._send(code, body, ct)

            if path == "/api/camp":
                code, body, ct = _json_bytes(kernel.camp_surface())
                return self._send(code, body, ct)

            # THE LAW: the player side shows the company's belief only. Truth, another faction's
            # mind and belief-vs-truth are dev faces: 403 unless devMode / VA_DEV=1.
            if path == "/api/intel":
                q = parse_qs(parsed.query or "")
                persp = (q.get("perspective") or ["company"])[0]
                result = kernel.intel_surface(persp)
                code, body, ct = _json_bytes(result, 403 if result.get("error") == "dev only" else 200)
                return self._send(code, body, ct)

            if path == "/api/truth":
                result = kernel.truth_surface()
                code, body, ct = _json_bytes(result, 403 if result.get("error") == "dev only" else 200)
                return self._send(code, body, ct)

            if path == "/api/divergence":
                result = kernel.divergence_surface()
                code, body, ct = _json_bytes(result, 403 if result.get("error") == "dev only" else 200)
                return self._send(code, body, ct)

            if path == "/api/exposure":
                code, body, ct = _json_bytes(kernel.exposure_surface())
                return self._send(code, body, ct)

            if path == "/api/health":
                code, body, ct = _json_bytes(kernel.health())
                return self._send(code, body, ct)

            if path == "/api/chronicle":
                code, body, ct = _json_bytes(kernel.chronicle_surface())
                return self._send(code, body, ct)

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

            # /api/continuity-audit, /api/phases, /api/steam, /api/surface were removed in pass 8B:
            # nothing in app/ or tools/ called them (campaign_zip went with them in pass 10).

            if path == "/api/saves":
                if hasattr(kernel, "list_saves"):
                    code, body, ct = _json_bytes(kernel.list_saves())
                else:
                    code, body, ct = _json_bytes({"ok": False, "error": "saves not available"}, 404)
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

            if path == "/api/camp-act":
                try:
                    result = kernel.camp_act(_read_json_body(self))
                except (ValueError, TypeError, AttributeError):
                    result = {"ok": False, "error": "Invalid camp action request."}
                code, body, ct = _json_bytes(result, 200 if result.get("ok") else 409)
                return self._send(code, body, ct)

            if path == "/api/narrative-choice":
                try:
                    result = kernel.narrative_choice(_read_json_body(self))
                except (ValueError, TypeError, AttributeError):
                    result = {"ok": False, "error": "Invalid narrative choice request."}
                code, body, ct = _json_bytes(result, 200 if result.get("ok") else 409)
                return self._send(code, body, ct)

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
                if result.get("accepted"):
                    code = 202
                else:
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

            if path == "/api/camp-talk":
                try:
                    body_in = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                if hasattr(kernel, "camp_talk"):
                    result = kernel.camp_talk(
                        talk_id=str(body_in.get("talkId") or body_in.get("id") or ""),
                        hero_a=str(body_in.get("a") or body_in.get("heroA") or ""),
                        hero_b=str(body_in.get("b") or body_in.get("heroB") or ""),
                    )
                else:
                    result = {"ok": False, "error": "camp_talk not available"}
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/seal-company":
                try:
                    body_in = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                band = body_in.get("band") or body_in.get("crewBand") or body_in.get("picks") or []
                if not isinstance(band, list):
                    band = []
                if hasattr(kernel, "seal_company"):
                    result = kernel.seal_company(band=[str(x) for x in band])
                else:
                    result = {"ok": False, "error": "seal_company not available"}
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/feedback-bundle":
                try:
                    body_in = _read_json_body(self)
                except Exception:  # noqa: BLE001
                    body_in = {}
                result = kernel.feedback_bundle(body_in if isinstance(body_in, dict) else {})
                code, body, ct = _json_bytes(result, 200 if result.get("ok") else 500)
                return self._send(code, body, ct)

            if path == "/api/reset-campaign":
                try:
                    body_in = _read_json_body(self)
                except Exception:
                    body_in = {}
                confirm = str(
                    body_in.get("confirm")
                    or (qs.get("confirm") or [""])[0]
                    or ""
                )
                if hasattr(kernel, "reset_campaign"):
                    result = kernel.reset_campaign(confirm=confirm)
                else:
                    result = {"ok": False, "error": "reset not available"}
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/save-campaign":
                try:
                    body_in = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                if hasattr(kernel, "save_campaign"):
                    result = kernel.save_campaign(
                        slot=str(body_in.get("slot") or body_in.get("name") or ""),
                        label=str(body_in.get("label") or ""),
                        note=str(body_in.get("note") or ""),
                    )
                else:
                    result = {"ok": False, "error": "save not available"}
                code = 200 if result.get("ok") else 400
                code, body, ct = _json_bytes(result, code)
                return self._send(code, body, ct)

            if path == "/api/load-campaign":
                try:
                    body_in = _read_json_body(self)
                except Exception as e:  # noqa: BLE001
                    code, body, ct = _json_bytes({"ok": False, "error": f"bad json: {e}"}, 400)
                    return self._send(code, body, ct)
                confirm = str(
                    body_in.get("confirm")
                    or (qs.get("confirm") or [""])[0]
                    or ""
                )
                if hasattr(kernel, "load_campaign"):
                    result = kernel.load_campaign(
                        slot=str(body_in.get("slot") or body_in.get("name") or ""),
                        confirm=confirm,
                    )
                else:
                    result = {"ok": False, "error": "load not available"}
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
