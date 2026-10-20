#!/usr/bin/env python3
"""Mint / refresh playtest-infra packets in yurt work river."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

PKT_DIR = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\work_packets")
WS = Path(r"C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def write(pkt: dict) -> None:
    PKT_DIR.mkdir(parents=True, exist_ok=True)
    path = PKT_DIR / f"{pkt['packet_id']}.json"
    path.write_text(json.dumps(pkt, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> int:
    t = now()
    # Closed / shipped by this seat
    for pid, title, do_now, status in [
        (
            "pkt-bar-kernel-campaign-sim",
            "Kernel multi-sortie campaign sim (no BAR)",
            "Shipped: tools/kernel_campaign_sim_v1.py + tests. Re-run multi-seed for fun retune.",
            "cleared",
        ),
        (
            "pkt-bar-strategic-seat-attachments",
            "Strategic seat + attachment ledger",
            "Shipped: attachments_v1 + strategic_seat + process_result hook. Optional Ant brain later.",
            "cleared",
        ),
        (
            "pkt-bar-density-world-tick-power",
            "World tick + power-response curve",
            "Shipped: world_tick_v1.py. Retune tables after human afternoon scorecards (S6).",
            "cleared",
        ),
        (
            "pkt-bar-afternoon-playtest-pack",
            "Afternoon human playtest pack",
            "Shipped: snapshot, restore script, scorecard md. Operator runs P0-P5.",
            "cleared",
        ),
    ]:
        write(
            {
                "packet_id": pid,
                "tree": "bar-verdance",
                "node_id": "bar-playtest-infra",
                "caste": "wargen-grok",
                "title": title,
                "status": status,
                "do_now": do_now,
                "updated_at": t,
                "context_paths": [
                    str(WS / "outbound" / "47_PLAYTEST_INFRA.md"),
                    str(WS / "docs" / "AFTERNOON_PLAYTEST_SCORECARD.md"),
                ],
            }
        )

    # Open for post-play retune
    write(
        {
            "packet_id": "pkt-bar-playtest-s6-retune",
            "tree": "bar-verdance",
            "node_id": "bar-playtest-infra",
            "caste": "wargen-grok",
            "title": "S6: retune power-response + attachments from human scorecards",
            "status": "open",
            "do_now": (
                "After Luke fills docs/AFTERNOON_PLAYTEST_SCORECARD.md: retune world_tick "
                "power table, attachment memory lines, multi-seed fun floor. No hub UI."
            ),
            "updated_at": t,
            "context_paths": [
                str(WS / "outbound" / "47_PLAYTEST_INFRA.md"),
                str(WS / "docs" / "AFTERNOON_PLAYTEST_SCORECARD.md"),
                str(WS / "tools" / "world_tick_v1.py"),
            ],
        }
    )

    vitals = WS / "outbox" / "playtest_infra_vitals.latest.json"
    vitals.write_text(
        json.dumps(
            {
                "at": t,
                "kernel_sim_meanFun": 0.796,
                "strategic_seat_meanFun": 0.703,
                "diverse": True,
                "outbound": "47_PLAYTEST_INFRA.md",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {vitals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
