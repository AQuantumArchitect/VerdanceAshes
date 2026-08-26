#!/usr/bin/env python3
"""Quick demo: blank-boot mood world + one mission + optional LLM tick."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow `python tools/quantum_bar_ai/demo.py` from workspace root.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from quantum_bar_ai.brain import load_brain_config
from quantum_bar_ai.seat import PlayerProxySeat, SeatConfig
from quantum_bar_ai.sim import EARLY_ARC
from quantum_bar_ai.world import PROXY_SPEC


def main() -> int:
    print("quantum-BAR-AI demo")
    print(f"  world: {PROXY_SPEC.name} nodes={len(PROXY_SPEC.nodes)} bindings={len(PROXY_SPEC.bindings)}")
    cfg = load_brain_config()
    print(f"  llm: enabled={cfg.enabled} model={cfg.model}")

    seat = PlayerProxySeat(
        config=SeatConfig(use_llm=cfg.enabled, llm_every_n=8, seed=11, verbose=True)
    )
    card = EARLY_ARC[0]
    result = seat.play_mission(card)
    print(json.dumps({
        "verdict": result.verdict,
        "ticks": result.ticks,
        "progress": result.progress,
        "sources": result.brain_source_counts,
        "summary": seat.summary(),
    }, indent=2))
    return 0 if result.verdict not in ("heroes_dead", "timeout_fail") else 1


if __name__ == "__main__":
    raise SystemExit(main())
