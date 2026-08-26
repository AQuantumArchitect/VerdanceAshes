#!/usr/bin/env python3
"""Local hub host — thin shim over verdance_kernel (Phase 0/1 compat).

Prefer the product entry:
  app\\bin\\PLAY.bat
  python -m verdance_kernel launch

Usage:
  python tools/hub_host_v1.py
  python tools/hub_host_v1.py --port 8770 --no-browser
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verdance war-map hub host (kernel shim)")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-bridge", action="store_true")
    args = ap.parse_args(argv)

    from verdance_kernel.server import serve

    return serve(
        args.workspace,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        enable_bridge=not args.no_bridge,
    )


if __name__ == "__main__":
    raise SystemExit(main())
