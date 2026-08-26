#!/usr/bin/env python3
"""verdance_cognifold_bridge — the BAR quantum brains' dual manifold as cognifold_trace_v1.

Until 2026-08-03 NEITHER manifold had a field rendering anywhere: the 6 proxy mood axes and
the 8 campaign design axes existed only as Python objects and JSON dumps. This bridge is the
translator, and ONLY that (same law as SpaceWheat's meerkat_cognifold_bridge.py, which it is
modeled on): it re-reads the artifact the brains already write — outbox/manifold_gym.latest.json,
whose `final_dual` carries BOTH manifolds (belief.expect = proxy mood, final_rho = campaign
axes) — and republishes the reshaped JSON locally for SpaceWheat's cognifold instrument
(Core/Visualization/CognifoldTraceView.gd, scripts/cognifold-bar.sh). It never writes to the
workspace and never touches the campaign state.

Honesty ledger:
  - expect/rho values are SIGNED expectations in [-1, 1] (world.py / campaign_manifold.py
    docstrings). A register's state point sits on the z-axis at that expectation — the data
    carries no transverse info, so none is drawn. purity = (1+z²)/2, the minimal-commitment
    state consistent with the expectation alone.
  - confidence = belief.coherence for proxy/mission registers (a real exported quantity);
    campaign registers carry NO per-axis confidence and none is fabricated.
  - edges/manifold are NOT populated — no coupling export exists to transcribe.
  - `stamp` + `source_age_s` ride along so a viewer can tell fresh from stale.

Pole glyphs are TRANSCRIBED from the axis docstrings (north = +1 pole, south = -1 pole):
world.py ("aggression -1 hold/defensive .. +1 push/charge", ...) and campaign_manifold.py
("Q0 Armada <-> Cortex (+1 = Armada weight)", ...). This doubles as the verdance worlds'
first real glyph vocabulary — the source the yurt vocabulary lint was waiting on.

Usage:
    python3 verdance_cognifold_bridge.py
    curl 127.0.0.1:8098/cognifold

Env:
    VERDANCE_WORKSPACE     default: this file's workspace root (two dirs up)
    VERDANCE_BRIDGE_PORT   default 8098
    VERDANCE_BRIDGE_POLL_S default 3.0
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_HERE = Path(__file__).resolve()
WORKSPACE = Path(os.environ.get("VERDANCE_WORKSPACE", _HERE.parents[2]))
FACE = WORKSPACE / "outbox" / "manifold_gym.latest.json"
BRIDGE_PORT = int(os.environ.get("VERDANCE_BRIDGE_PORT", "8098"))
POLL_S = float(os.environ.get("VERDANCE_BRIDGE_POLL_S", "3.0"))

# (role, north/+1 glyph, south/-1 glyph) — transcribed from world.py's axis docstring.
_PROXY_AXES = (
    ("aggression", "⚔️", "🛡️"),   # +1 push/charge      .. -1 hold/defensive
    ("caution",    "🐢", "🎲"),    # +1 careful           .. -1 reckless
    ("focus",      "🎯", "🌫️"),   # +1 objective-locked  .. -1 distracted
    ("pressure",   "⏰", "🧘"),    # +1 clock-panic       .. -1 calm/time
    ("cohesion",   "🤝", "🍂"),    # +1 group-kept        .. -1 scattered
    ("momentum",   "🚂", "🪨"),    # +1 steamrolling      .. -1 stalled
)
_MISSION_AXES = (
    ("objective", "🏁", "🕳️"),    # objective progress   .. objective lost
    ("threat",    "💀", "🕊️"),    # under threat .. safe (💀 not ☠️ — twemoji has no ☠️ SVG)
)
# Transcribed from campaign_manifold.py's CAMPAIGN_AXES comments (design-doc qubits Q0-Q7).
_CAMPAIGN_AXES = (
    ("arm_cor",      "🟦", "🟥"),  # Q0 Armada (+1)       .. Cortex
    ("schism",       "🪓", "🕊️"),  # Q1 internal schism   .. unified
    ("void_struct",  "🕳️", "🏗️"),  # Q2 Void (+1)        .. Structure
    ("bio_cold",     "🌱", "❄️"),  # Q3 Biogenesis        .. Cold
    ("ai_human",     "🤖", "👤"),  # Q4 AI synthesis      .. Human sovereignty
    ("phi",          "⌛", "🌄"),  # Q5 process-time: campaign late .. campaign start
    ("zone_control", "🚩", "⚔️"),  # Q6 held              .. contested
    ("tenebrium",    "💎", "🪫"),  # Q7 abundant (+1)     .. scarce
)
_NODE_ICONS = {"proxy": "🎖️", "mission": "🎯", "campaign": "🌋"}

_lock = threading.Lock()
_trace: dict | None = None
_last_error: str | None = None


def _register(node: str, role: str, north: str, south: str, v: float,
              confidence: float | None) -> dict:
    z = max(-1.0, min(1.0, float(v)))
    reg = {
        "node": node, "role": role, "node_icon": _NODE_ICONS[node],
        "north_emoji": north, "south_emoji": south,
        "value": (1.0 + z) / 2.0, "p0": (1.0 + z) / 2.0, "p1": (1.0 - z) / 2.0,
        "r_bloch": abs(z), "r_xy": 0.0, "phi": 0.0,
        "theta": 0.0 if z >= 0 else math.pi,
        "purity": (1.0 + z * z) / 2.0,
    }
    if confidence is not None:
        reg["confidence"] = float(confidence)
    return reg


def _build_trace() -> dict:
    """Re-read the gym face and reshape. Raises on any failure — the caller decides what
    'dark' means; nothing is guessed or filled in."""
    raw = json.loads(FACE.read_text(encoding="utf-8"))
    dual = raw["final_dual"]
    belief = dual["belief"]
    expect = belief["expect"]
    coherence = belief.get("coherence")
    rho = raw["final_rho"]

    registers = []
    for role, north, south in _PROXY_AXES:
        if role in expect:
            registers.append(_register("proxy", role, north, south, expect[role], coherence))
    for role, north, south in _MISSION_AXES:
        if role in expect:
            registers.append(_register("mission", role, north, south, expect[role], coherence))
    for role, north, south in _CAMPAIGN_AXES:
        if role in rho:
            registers.append(_register("campaign", role, north, south, rho[role], None))

    return {
        "world": "verdance-ashes",
        "registers": registers,
        "edges": [],
        "stamp": raw.get("stamp"),
        "source": str(FACE),
        "source_age_s": round(time.time() - FACE.stat().st_mtime, 1),
    }


def _poll_loop() -> None:
    global _trace, _last_error
    while True:
        try:
            trace = _build_trace()
            with _lock:
                _trace = trace
                _last_error = None
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            with _lock:
                _last_error = f"{type(exc).__name__}: {exc}"
            print(f"[verdance_cognifold_bridge] DARK: {_last_error}", flush=True)
        time.sleep(POLL_S)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/cognifold":
            self.send_response(404)
            self.end_headers()
            return
        with _lock:
            trace, err = _trace, _last_error
        if trace is None:
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": err or "no data yet"}).encode("utf-8"))
            return
        body = json.dumps(trace, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    threading.Thread(target=_poll_loop, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), _Handler)
    print(f"[verdance_cognifold_bridge] serving http://127.0.0.1:{BRIDGE_PORT}/cognifold "
          f"<- {FACE} (poll {POLL_S}s)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
