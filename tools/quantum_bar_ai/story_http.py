"""Tiny HTTP server for the proxy-player story (yurt-style hearth view).

Serves app/story/latest/ (or --dir). Default http://127.0.0.1:8765/
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .suite import _workspace_root


def _default_story_dir(ws: Path) -> Path:
    return ws / "app" / "story" / "latest"


class StoryHandler(SimpleHTTPRequestHandler):
    story_dir: Path = Path(".")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.story_dir), **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # quieter
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        # Cinematic friend demo lives under app/showoff — serve it from /show
        if parsed.path in ("/show", "/show/", "/show.html", "/demo", "/demo/"):
            ws = _workspace_root()
            show = ws / "app" / "showoff" / "index.html"
            alt = self.story_dir / "show.html"
            target = show if show.is_file() else alt
            if target.is_file():
                raw = target.read_bytes()
                # rewrite art paths when serving from showoff root via redirect-ish
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        if parsed.path.startswith("/showoff/"):
            ws = _workspace_root()
            rel = parsed.path[len("/showoff/") :]
            f = (ws / "app" / "showoff" / rel).resolve()
            root = (ws / "app" / "showoff").resolve()
            if str(f).startswith(str(root)) and f.is_file():
                raw = f.read_bytes()
                ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404, "not found")
            return
        if parsed.path in ("/", "/index.html"):
            # Prefer cinematic if present
            ws = _workspace_root()
            show = ws / "app" / "showoff" / "index.html"
            if show.is_file() and "gallery" not in (parsed.query or ""):
                self.path = "/show.html"
                # fall through after rewrite
            index = self.story_dir / "index.html"
            if self.path == "/show.html" and show.is_file():
                raw = show.read_bytes()
                # fix relative art/ links to /showoff/art/
                text = raw.decode("utf-8", errors="replace")
                text = text.replace("art/", "/showoff/art/")
                raw = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if index.is_file():
                self.path = "/index.html"
            elif (self.story_dir / "STORY.md").is_file():
                self._serve_text(
                    (self.story_dir / "STORY.md").read_text(encoding="utf-8"),
                    "text/markdown; charset=utf-8",
                )
                return
        if parsed.path == "/api/story":
            js = self.story_dir / "story.json"
            if js.is_file():
                raw = js.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404, "story.json missing — run fair arc first")
            return
        if parsed.path == "/api/health":
            payload = {
                "ok": True,
                "story_dir": str(self.story_dir),
                "has_story": (self.story_dir / "story.json").is_file(),
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return
        return super().do_GET()

    def _serve_text(self, text: str, ctype: str) -> None:
        raw = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def guess_type(self, path: str) -> str:  # type: ignore[override]
        ctype, _ = mimetypes.guess_type(path)
        return ctype or "application/octet-stream"


def serve(story_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> None:
    story_dir = Path(story_dir)
    story_dir.mkdir(parents=True, exist_ok=True)
    StoryHandler.story_dir = story_dir
    httpd = ThreadingHTTPServer((host, port), StoryHandler)
    print(f"Verdance proxy story hearth → http://{host}:{port}/")
    print(f"  dir: {story_dir}")
    print(f"  api: http://{host}:{port}/api/story")
    if not (story_dir / "story.json").is_file():
        print("  (no story yet — run app\\bin\\RUN_FAIR_ARC_ANT.bat first)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main() -> int:
    p = argparse.ArgumentParser(description="Serve proxy player story over HTTP")
    p.add_argument("--dir", type=str, default="", help="story directory")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    ws = _workspace_root()
    d = Path(args.dir) if args.dir else _default_story_dir(ws)
    serve(d, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
