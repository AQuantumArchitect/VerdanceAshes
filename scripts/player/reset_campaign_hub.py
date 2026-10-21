#!/usr/bin/env python3
"""Finish a campaign reset: rebuild hub + ensure commerce wallets + clean opener intent.

Buy-everything: no free Punch grant. Called from reset_campaign.ps1 after wipe/migrate.
Avoids PowerShell here-strings (LF-only .ps1 files break @"..."@ in Windows PowerShell 5.1).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _invalidate_stale_seed(ws: Path) -> None:
    """Drop ghost va_current so BAR cannot load a pre-company empty wreck bake.

    Company seal + Drop rebuild the living seed. Leaving a pre-seal bake around
    is what made rescue wrecks feel ~50% haunted (hub newer than BAR seed).
    """
    outbox = ws / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    status = {
        "schemaVersion": "verdance-seed-status/1.0",
        "stale": True,
        "reason": "await_company_seal",
        "at": _utc(),
        "note": (
            "Reset cleared the playable seed. Form the company on the hub, then Drop — "
            "that bake stamps deployAces + fieldRecruits (wrecks)."
        ),
    }
    (outbox / "seed_status.json").write_text(
        json.dumps(status, indent=2) + "\n", encoding="utf-8"
    )
    for rel in (
        outbox / "va_current.lua",
        ws
        / "mod"
        / "VerdanceAshes.sdd"
        / "singleplayer"
        / "verdance_ashes"
        / "generated"
        / "va_current.lua",
    ):
        try:
            if rel.is_file():
                rel.unlink()
        except OSError:
            pass


def seed_opener_intent(ws: Path, state: dict | None = None) -> Path:
    """Write the canonical opening intent (hub NE desert → SE decoy plateau).

    Must match ``opening_sortie_order`` / hub theater — not a second NW-bastion
    recipe. Does **not** bake va_current: field wrecks need a sealed company.
    """
    outbox = ws / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / "next_mission_intent.json"

    order = None
    try:
        tools = ws / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from verdance.campaign import load_json, opening_sortie_order

        st = state if isinstance(state, dict) else {}
        if not st:
            sp = ws / "state" / "campaign_state.json"
            if sp.is_file():
                st = load_json(sp)
        order = opening_sortie_order(st, ws)
    except Exception:  # noqa: BLE001
        order = None

    if isinstance(order, dict) and order.get("mapId"):
        rim = str(order.get("deploymentZoneId") or "GF_NE_PLATEAU")
        target = str(order.get("targetZoneId") or "GF_SE_PLATEAU")
        intent = {
            "schemaVersion": "verdance-mission-intent/1.0",
            "campaignId": order.get("campaignId") or "verdance_ashes",
            "missionId": "va_001",
            "missionNumber": 1,
            "act": 1,
            "mapId": str(order.get("mapId") or "greenest_fields"),
            "deploymentZoneId": rim,
            "extractionZoneId": str(order.get("extractionZoneId") or rim),
            "targetZoneId": target,
            "objective": str(order.get("objectiveArchetype") or "eco_raid"),
            "objectiveTarget": {
                "id": target,
                "kind": str(order.get("objectiveArchetype") or "eco_raid"),
                "label": f"{order.get('objectiveArchetype') or 'eco_raid'}: {target}",
                "targetZoneId": target,
                "mapId": str(order.get("mapId") or "greenest_fields"),
                "enemyFaction": str(order.get("against") or "armada"),
                "patron": str(order.get("patron") or "nullmercs"),
            },
            "captureZoneIds": list(order.get("captureZoneIds") or [target]),
            "secondaryCaptureZoneIds": list(order.get("secondaryCaptureZoneIds") or []),
            "fromZoneIds": list(order.get("fromZoneIds") or [rim]),
            "deployAces": list(order.get("deployAces") or ["vane", "ketha"]),
            "crewBand": list(order.get("crewBand") or []),
            "openingMission": True,
            "openingDoctrine": order.get("openingDoctrine") or "decoy_raid",
            "patron": str(order.get("patron") or "nullmercs"),
            "against": str(order.get("against") or "armada"),
            "sessionMode": order.get("sessionMode") or "reload_travel",
            "occupationModel": order.get("occupationModel") or "living_shell",
            "seededAt": _utc(),
            "seedReason": "campaign_reset_opener_canonical",
            "seedStaleUntilCompanySeal": True,
            "notes": (
                "Canonical opener (matches hub): quiet north desert rim → southeast "
                "decoy plateau. Center fusion vaults stay optional bonuses. "
                "Playable seed (wrecks + crew) bakes after company seal / Drop."
            ),
        }
    else:
        # Hard fallback — same zones as opening_sortie_order docs.
        rim = "GF_NE_PLATEAU"
        target = "GF_SE_PLATEAU"
        intent = {
            "schemaVersion": "verdance-mission-intent/1.0",
            "campaignId": "verdance_ashes",
            "missionId": "va_001",
            "missionNumber": 1,
            "act": 1,
            "mapId": "greenest_fields",
            "deploymentZoneId": rim,
            "extractionZoneId": rim,
            "targetZoneId": target,
            "objective": "eco_raid",
            "objectiveTarget": {
                "id": target,
                "kind": "eco_raid",
                "label": "eco_raid: Southeast Plateau",
                "targetZoneId": target,
                "mapId": "greenest_fields",
                "enemyFaction": "armada",
                "patron": "nullmercs",
            },
            "captureZoneIds": [target],
            "secondaryCaptureZoneIds": [],
            "fromZoneIds": [rim],
            "deployAces": ["vane", "ketha"],
            "crewBand": [],
            "openingMission": True,
            "patron": "nullmercs",
            "seededAt": _utc(),
            "seedReason": "campaign_reset_opener_fallback",
            "seedStaleUntilCompanySeal": True,
            "notes": (
                "Fallback canonical opener. Seed stays stale until company seal + Drop."
            ),
        }

    path.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")
    # Keep sortie order in lockstep so stamp/materialize cannot revive NW-ghost.
    order_path = outbox / "next_sortie_order.json"
    order_path.write_text(
        json.dumps(
            {
                "schemaVersion": "verdance-sortie-order/1.0",
                "campaignId": intent.get("campaignId"),
                "mapId": intent.get("mapId"),
                "targetZoneId": intent.get("targetZoneId"),
                "deploymentZoneId": intent.get("deploymentZoneId"),
                "extractionZoneId": intent.get("extractionZoneId"),
                "fromZoneIds": list(intent.get("fromZoneIds") or []),
                "captureZoneIds": list(intent.get("captureZoneIds") or []),
                "secondaryCaptureZoneIds": list(
                    intent.get("secondaryCaptureZoneIds") or []
                ),
                "deployAces": list(intent.get("deployAces") or []),
                "crewBand": list(intent.get("crewBand") or []),
                "patron": intent.get("patron"),
                "against": intent.get("against") or "armada",
                "objectiveArchetype": intent.get("objective"),
                "openingMission": True,
                "source": "campaign_reset_opener",
                "seedStaleUntilCompanySeal": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild hub after campaign reset")
    ap.add_argument("--workspace", required=True)
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    tools = ws / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))

    from verdance.company.company import ensure_company
    from verdance_kernel.api import CampaignKernel
    from verdance.campaign import build_war_map, ensure_commerce, ensure_roster, load_json, save_json

    sp = ws / "state" / "campaign_state.json"
    outbox = ws / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    showoff = ws / "app" / "showoff"
    # Scrub stale hub paint first — never leave Sortie N on disk while rebuild runs.
    for stale in (
        showoff / "hub_state.json",
        showoff / "hub_state.embed.js",
        outbox / "campaign_surface.latest.json",
        outbox / "hub_result.latest.json",
    ):
        try:
            if stale.is_file():
                stale.unlink()
                print("scrubbed", stale.name)
        except OSError as e:
            print(f"WARN could not scrub {stale.name}: {e}", file=sys.stderr)

    if sp.is_file():
        state = load_json(sp)
        # Seed the full authored catalog (names + gap-fill heroes) before hub paint.
        ensure_roster(state)
        ensure_company(state, ws)
        save_json(sp, state)
        # war_map is required by build_hub_state — regenerate, do not borrow ghosts.
        save_json(outbox / "war_map.json", build_war_map(state))
        print("wrote outbox/war_map.json")

    k = CampaignKernel(str(ws))
    try:
        r = k.rebuild_hub(skip_apply=True)
    except Exception as e:  # noqa: BLE001
        print(f"hub rebuild failed: {e}", file=sys.stderr)
        return 1
    if not r.get("ok"):
        print("hub", r)
        return 1
    print("hub ok (no result re-apply)")

    if sp.is_file():
        state = load_json(sp)
        # Fresh continuity: no leftover scars / HV ghosts on a reset state.
        state.setdefault("shellScars", {})
        state.setdefault("heldInstallations", {})
        state.setdefault("playerFootprints", {})
        state.setdefault("claimedNodes", {})
        c = ensure_commerce(state, ws)
        save_json(sp, state)
        owned = list((c.get("owned") or {}).keys())
        print(
            "commerce metalK=%s tnb=%s owned=%s"
            % (c.get("metalK"), c.get("tenebrium"), owned)
        )

    state = load_json(sp) if sp.is_file() else {}
    intent_path = seed_opener_intent(ws, state if isinstance(state, dict) else None)
    print("opener intent:", intent_path)

    # Never bake va_current before company seal — empty fieldRecruits haunted Drop.
    _invalidate_stale_seed(ws)
    print("seed: stale until company seal + Drop (no pre-seal bake)")

    # Second rebuild so shop/owned paint matches wallets (empty bag until purchase).
    try:
        r2 = k.rebuild_hub(skip_apply=True)
    except Exception as e:  # noqa: BLE001
        print(f"hub refresh failed: {e}", file=sys.stderr)
        return 1
    print("hub refresh:", "ok" if r2.get("ok") else r2)

    state = load_json(sp) if sp.is_file() else {}
    n = int(state.get("missionNumber") or 0)
    if n != 1:
        print("RESET FAILED: missionNumber is %s, expected 1" % n)
        return 1
    hub_path = showoff / "hub_state.json"
    if not hub_path.is_file():
        print("RESET FAILED: hub_state.json missing after rebuild", file=sys.stderr)
        return 1
    hub = load_json(hub_path)
    hn = int(hub.get("missionNumber") or 0)
    if hn != 1:
        print("RESET FAILED: hub_state missionNumber is %s, expected 1" % hn, file=sys.stderr)
        return 1
    print("missionNumber=1 hub_state=1")

    return 0 if r2.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
