#!/usr/bin/env python3
"""Mint overnight remainder packets into yurt work river (no hang-prone shell quoting)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PKT_DIR = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\work_packets")
WS = Path(r"C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace")
CORAL = Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def write_packet(pkt: dict) -> Path:
    PKT_DIR.mkdir(parents=True, exist_ok=True)
    path = PKT_DIR / f"{pkt['packet_id']}.json"
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("status") in {"open", "walking", "claimed", "cleared"}:
                print(f"skip existing {pkt['packet_id']} status={old.get('status')}")
                return path
        except Exception:
            pass
    path.write_text(json.dumps(pkt, indent=2), encoding="utf-8")
    print(f"minted {pkt['packet_id']}")
    return path


def main() -> int:
    # Prefer work_packet.mint if importable
    sys.path.insert(0, str(CORAL))
    try:
        import work_packet as wp  # type: ignore

        use_api = True
    except Exception as e:
        print(f"work_packet import failed ({e}); writing JSON faces only")
        use_api = False

    specs = [
        {
            "packet_id": "pkt-bar-player-rig-hub-shop-deploy",
            "tree": "bar-verdance",
            "node_id": "bar-player-rig",
            "caste": "player-rig-ant",
            "title": "Player-rig: hub shop + Deploy + mission card paint (not kernel)",
            "do_now": (
                "Build showoff/hub_state shop surface from commerce catalog; "
                "Deploy calls compile+launch; no story-engine math. Kernel already emits "
                "sessionMode/occupationModel/factionBanks/tenebrium."
            ),
            "allow_paths": [
                "app/showoff/**",
                "docs/hub_state_v1.md",
                "tools/build_hub_state_v1.py",
                "export/**",
            ],
            "context_paths": [
                "data/commerce/commerce_catalog.json",
                "docs/SHIP_ARCHITECTURE.md",
            ],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\docs\hub_state_v1.md'); "
                r"assert p.is_file(); print('ok-hub-docs')\""
            ),
        },
        {
            "packet_id": "pkt-bar-mode-b-reload-travel",
            "tree": "bar-verdance",
            "node_id": "bar-mode-b",
            "caste": "worker-ant",
            "title": "Mode B Reload map travel (after capability matrix GO)",
            "do_now": (
                "Only after VA_CAPABILITY reload=true. Wire strategic_link edges from "
                "world_zone_graph into session host Reload path. Mode A is kernel default."
            ),
            "allow_paths": ["scripts/play_session_v1.ps1", "mod/**", "tools/**", "docs/**"],
            "context_paths": [
                "docs/CAMPAIGN_BAR_PROTOCOL.md",
                "data/zone_maps/world_zone_graph.v1.json",
            ],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\docs\CAMPAIGN_BAR_PROTOCOL.md'); "
                r"assert p.is_file(); print('ok')\""
            ),
        },
        {
            "packet_id": "pkt-bar-lua-tenebrium-file-split",
            "tree": "bar-verdance",
            "node_id": "bar-lua-split",
            "caste": "worker-ant",
            "title": "Extract tenebLoot handlers to include/va_tenebrium_handlers.lua",
            "do_now": (
                "Physical VFS.Include split of tenebLoot methods. README at "
                "luarules/gadgets/include/va_tenebrium_README.md. Smoke in BAR before ship."
            ),
            "allow_paths": ["mod/VerdanceAshes.sdd/luarules/gadgets/**"],
            "context_paths": [
                "mod/VerdanceAshes.sdd/luarules/gadgets/include/va_tenebrium_README.md"
            ],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\mod\VerdanceAshes.sdd\luarules\gadgets\include\va_tenebrium_README.md'); "
                r"assert p.is_file(); print('ok')\""
            ),
        },
        {
            "packet_id": "pkt-bar-cloud-shell-bake-real-dumps",
            "tree": "bar-verdance",
            "node_id": "bar-cloud-bake",
            "caste": "worker-ant",
            "title": "Cloud/headed BARb shell dumps (IconsAtlas unblock)",
            "do_now": (
                "Real shell templates replacing placeholders. Local headless hangs IconsAtlas "
                "f=30. Prefer AWS cloud bake or headed GPU path."
            ),
            "allow_paths": [
                "scripts/**",
                "data/base_templates/**",
            ],
            "context_paths": ["scripts/forge/cloud/README.md"],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\scripts\forge\cloud\README.md'); "
                r"assert p.is_file(); print('ok')\""
            ),
        },
        {
            "packet_id": "pkt-bar-capture-node-claims",
            "tree": "bar-verdance",
            "node_id": "bar-capture",
            "caste": "worker-ant",
            "title": "Capture = claim living shell node under regrow pressure",
            "do_now": (
                "After seven shells solid: hold cleared node = claim; hub contracts; no free Tnb mint."
            ),
            "allow_paths": ["tools/**", "mod/**", "data/**", "docs/**"],
            "context_paths": [
                "data/base_templates/README.md",
                "docs/GRAPH_COLLAPSE_SSOT.md",
            ],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\data\base_templates\README.md'); "
                r"assert p.is_file(); print('ok')\""
            ),
        },
        {
            "packet_id": "pkt-bar-seven-map-shell-recipes",
            "tree": "bar-verdance",
            "node_id": "bar-seven-shells",
            "caste": "worker-ant",
            "title": "Finish seven-map living shell recipes to character cards",
            "do_now": (
                "Horus core, Bastion citadel, Jungle scrap, Simmers multipaint — recipes + placeholders "
                "exist; real dumps when bake path works."
            ),
            "allow_paths": ["data/base_templates/**", "scripts/**"],
            "context_paths": ["data/base_templates/README.md"],
            "referee_cmd": (
                r'"C:\Python313\python.exe" -c "from pathlib import Path; '
                r"p=Path(r'C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\data\base_templates'); "
                r"assert p.is_dir(); print('ok', len(list(p.iterdir())))\""
            ),
        },
    ]

    for s in specs:
        if use_api:
            try:
                pkt = wp.mint(
                    packet_id=s["packet_id"],
                    tree=s["tree"],
                    node_id=s["node_id"],
                    caste=s["caste"],
                    title=s["title"],
                    do_now=s["do_now"],
                    allow_paths=s["allow_paths"],
                    context_paths=s.get("context_paths"),
                    referee_cmd=s["referee_cmd"],
                    cwd=str(WS),
                    minted_by="grok-overnight-kernel",
                    max_turns=16,
                )
                print(pkt.get("packet_id"), pkt.get("status"))
                continue
            except Exception as e:
                print(f"mint api fail {s['packet_id']}: {e}; writing face")
        face = {
            **s,
            "forbid_paths": [".env", "**/*secret*", "**/credentials*", "**/.ssh/**"],
            "max_turns": 16,
            "eta_claim_cap": 0.25,
            "cwd": str(WS),
            "minted_by": "grok-overnight-kernel",
            "minted_ts": now(),
            "status": "open",
            "mechanical_only": False,
            "spawn_swarm": False,
            "schema": "semantica-work-packet/0.1",
            "law": [
                "ants walk only — no strategy",
                "print code/artifacts; notes are not ship",
                "referee_cmd exit 0 clears packet",
                "never fake Luke dams",
            ],
            "tags": ["#river:bar-verdance", "#seat:wargen-grok", "#overnight:kernel-2026-07-28"],
        }
        write_packet(face)

    # refresh queue face lightly
    open_ids = []
    for f in PKT_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("status") == "open":
            open_ids.append(d.get("packet_id"))
    qpath = PKT_DIR.parent / "work_packet_queue.json"
    q = {
        "ts": now(),
        "schema": "work-packet-queue/0.1",
        "open": len(open_ids),
        "walking": 0,
        "open_ids": open_ids,
        "dir": str(PKT_DIR).replace("\\", "/"),
        "law": "fungus mints; ants walk; referee clears; no chat required",
        "note": "overnight kernel queued bar remainder",
    }
    qpath.write_text(json.dumps(q, indent=2), encoding="utf-8")
    print(f"queue open={len(open_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
