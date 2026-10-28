"""Sortie orders: the hub stamp, the opening sortie, Mode A quests, the escalation plan.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import ARCHETYPE_VERB, WORKSPACE_ROOT, canonical_map_id, load_json, save_json, utc_now
from .schema import CAMPAIGN_ID, zone_maps_from_workspace
from verdance.company.company import (
    company_deploy_aces,
    company_deploy_band,
    ensure_company,
    sortie_roster,
)
from verdance.company.quest_generator import generate_quests, write_quest_batch
from verdance.company.capture_node_claims import stamp_objective_capture
from verdance.world import escalation_ladder as ladder
from verdance.hub.contract import normalize_sortie, sortie_v2_to_v1_order
from verdance.company import quest_generator as qg

def available_allies(state: Dict[str, Any]) -> List[str]:
    """Who will stand with the clans, read from the graph + reputation. The
    ascendant mortal enemy sheds defectors; a courted merc line shows up."""
    graph = state.get("graph", {}) or {}
    rep = state.get("reputation", {}) or {}
    q0 = float(graph.get("q0_armada_cortex", 0.5) or 0.5)
    allies = ["ashwalkers"]
    if float(rep.get("nullmercs", 0) or 0) >= 40:
        allies.append("nullmercs")
    if q0 >= 0.6:
        allies.append("cortex_defectors")
    elif q0 <= 0.4:
        allies.append("armada_deserters")
    return allies


def load_sortie_order(workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """WO-003 / WO-042 / contract v2: accepted contract.

    Preference order:
      1) outbox/next_sortie_choice.json (in-engine debrief pick)
      2) outbox/next_sortie_order.json (legal VA-SORTIE/1 or tools)
      3) outbox/quest_batch.latest.json top candidate (Mode A graph walk)
    """
    if workspace is None:
        return None
    for name in ("next_sortie_choice.json", "next_sortie_order.json"):
        path = Path(workspace) / "outbox" / name
        if not path.exists():
            continue
        try:
            order = load_json(path)
        except Exception:
            continue
        if not isinstance(order, dict):
            continue
        # Provenance must survive contract v2 normalize — hub stamps and opening
        # flags are how materialize decides who wins the drop.
        provenance = {
            "source": order.get("source"),
            "derived": order.get("derived"),
            "openingMission": order.get("openingMission"),
            "openingDoctrine": order.get("openingDoctrine"),
            "openingForce": order.get("openingForce"),
            "fromDebrief": order.get("fromDebrief"),
            "debriefPick": order.get("debriefPick"),
            "hubChoiceId": order.get("hubChoiceId") or order.get("choiceId"),
        }
        # Normalize via contract v2 when available.
        try:

            order = sortie_v2_to_v1_order(normalize_sortie(order))
        except Exception:
            if order.get("targetZoneId") and not order.get("mapId") and order.get("map"):
                order["mapId"] = order["map"]
        for key, val in provenance.items():
            if val is not None and (order.get(key) is None or key in ("source", "derived", "openingMission")):
                order[key] = val
        if not order.get("mapId") or not order.get("targetZoneId"):
            continue
        if not order.get("patron"):
            order["patron"] = "nullmercs"
        if not order.get("objectiveArchetype") and order.get("kind"):
            order["objectiveArchetype"] = order["kind"]
        order.setdefault("sessionMode", "same_map")
        order.setdefault("occupationModel", "living_shell")
        return order
    return None


def apply_sealed_company_to_packet(
    packet: Dict[str, Any],
    state: Dict[str, Any],
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Keep the hub dropping list as the only spawn list.

    A non-empty ``crewBand`` is the packs on this drop. An empty list on a hub
    stamp (``source=hub_deploy_plan``) means core only. Opening orders and
    stamps that never named a list still receive the full living company.
    """
    if not isinstance(packet, dict) or not isinstance(state, dict):
        return packet
    try:
        ensure_company(state, workspace)
    except Exception:
        pass
    company = state.get("company") or {}
    if not company.get("sealed"):
        return packet
    explicit = packet.get("crewBand")
    source = str(packet.get("source") or "")
    sheet = isinstance(explicit, list) and (
        len(explicit) > 0 or source == "hub_deploy_plan"
    )
    if sheet:
        # sortie_roster: core always, requested packs only, unknown ids dropped.
        band, aces = sortie_roster(state, [str(x) for x in explicit if x])
        packet["crewBand"] = list(band)
        packet["deployAces"] = list(aces)
    else:
        band = company_deploy_band(state)
        aces = company_deploy_aces(state)
        if band:
            packet["crewBand"] = list(band)
        if aces:
            packet["deployAces"] = list(aces)
    return packet


# Night one's raid: the Armada works next door to the start road's pad, not the far corner.
OPENING_TARGET = "GF_NW_BASTION"


def opening_sortie_order(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return the authored alpha opening for a genuinely fresh campaign.

    The C&C board can leave a stamped contract in the outbox between sessions.
    That is useful after mission one, but it must not be allowed to replace the
    story's deliberate opening raid. An explicit non-Jungle session home or a
    non-empty history means the player has already chosen a different flow.

    The company starts on the start road, holding both of its doors, so the opening lands
    on Greenest Fields' end of it (`GF_NW_MUSTER`) and raids the Armada works next door in the
    Northwest Bastion (the living shell's west/central grassland pockets; Cauter's wreck lies
    there), then lifts from the same pad or the ground it took. The southeast plateau, the
    door to Koom Valley, is the far corner: the campaign works across the field toward it
    instead of crossing the whole map on night one (Luke, 2026-10-25).
    """
    if int(state.get("missionNumber", 1) or 1) != 1:
        return None
    if state.get("history"):
        return None
    home = canonical_map_id(state.get("sessionHomeMap") or state.get("homeMapId") or "")
    if home and home != "the_rock_jungle":
        return None
    # Mission one locks map/objective. Sealed company band still drops via
    # apply_sealed_company_to_packet so hub muster matches BAR.
    deploy_aces = ["pavise", "ketha"]
    rim_pad = "GF_NW_MUSTER"  # the start road's door on Greenest Fields
    order = {
        "schemaVersion": "verdance-sortie-order/1.0",
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "mapId": "greenest_fields",
        "targetZoneId": OPENING_TARGET,
        "deploymentZoneId": rim_pad,
        "extractionZoneId": rim_pad,
        "fromZoneIds": [rim_pad],
        "captureZoneIds": [OPENING_TARGET],
        "secondaryCaptureZoneIds": [],
        "hubChoiceId": "c_raid_tnb_greenest_fields",
        "deployAces": deploy_aces,
        "crewBand": [],
        "patron": "nullmercs",
        "against": "armada",
        "objectiveArchetype": "eco_raid",
        "difficulty": 1,
        "targetDuration": "8min",
        "contractXp": 180,
        "pathSignal": state.get("pathSignal", "B"),
        "sessionMode": "reload_travel",
        "occupationModel": "living_shell",
        "source": "opening_mission",
        "openingMission": True,
        "openingDoctrine": "decoy_raid",
        "openingForce": {
            "mercenaryPackage": "punch_of_thugs",
            "mercenaryLabel": "Mercenary Punch of Thugs",
            "thugs": 6,
            "karkinos": 2,
            "rezBots": 6,
        },
        "label": "Raid Greenest Fields for Tenebrium",
        "hubBlurb": (
            "Cross the start road to Greenest Fields: land on its north-west muster, break the "
            "Armada decoy farms on the southeast plateau for Tenebrium, and lift from the same pad. "
            "Hold the plateau too and the road to Koom Valley opens."
        ),
        "notes": (
            "Opening Tnb raid from the start road's door, Greenest Fields' north-west muster. "
            "Hit Armada decoy commanders with Thugs and Legion Karkinos. "
            "Home is the Rock Jungle — this sortie funds that base."
        ),
    }
    apply_sealed_company_to_packet(order, state, workspace)
    return order


def opening_hub_choice(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Project the canonical opening order as the hub's single deploy choice."""
    order = opening_sortie_order(state, workspace)
    if not order:
        return None
    effect = copy.deepcopy(order)
    effect["contractKind"] = effect.get("objectiveArchetype") or "eco_raid"
    effect["preferredDeployZoneId"] = order["deploymentZoneId"]
    effect["preferredCaptureZoneId"] = order["targetZoneId"]
    effect["preferredExtractionZoneId"] = order["extractionZoneId"]
    effect["padLocked"] = True   # the start road's door: the hub does not snap it toward the target
    return {
        "id": order["hubChoiceId"],
        "label": order.get("label") or "Raid Greenest Fields for Tenebrium",
        "blurb": order.get("hubBlurb") or order.get("notes") or "Hit the marked objective, then extract.",
        "kind": "deploy",
        "recommended": True,
        "effect": effect,
        "journey": "tnb_raid",
    }


def _session_home_map(state: Dict[str, Any], workspace: Optional[Path] = None) -> Optional[str]:
    """Mode A: prefer campaign session home, then open contract / last history."""
    # Campaign truth first — set by process_result after each sortie (Mode A lock).
    home = state.get("sessionHomeMap") or state.get("homeMapId")
    if home:
        mid = canonical_map_id(home)
        if mid:
            return mid
    if workspace is not None:
        for name in ("next_sortie_choice.json", "next_sortie_order.json", "next_mission_intent.json"):
            p = Path(workspace) / "outbox" / name
            if not p.exists():
                continue
            try:
                data = load_json(p)
            except Exception:
                continue
            mid = canonical_map_id(data.get("mapId") or data.get("map"))
            if mid:
                return mid
    hist = state.get("history") or []
    if hist and isinstance(hist[-1], dict):
        mid = canonical_map_id(hist[-1].get("mapId"))
        if mid:
            return mid
    return None


def _is_hub_stamped_sortie(order: Dict[str, Any]) -> bool:
    """True when the order was written by stamp_deploy_plan / hub C&C board.

    Authored opening_mission also carries hubChoiceId — that must NOT count as
    a player theater seal, or the opening would lock out real hub stamps.
    """
    if not isinstance(order, dict):
        return False
    source = str(order.get("source") or "")
    if source in ("opening_mission", "opening", "authored_opening"):
        return False
    if order.get("openingMission"):
        return False
    derived = order.get("derived") if isinstance(order.get("derived"), dict) else {}
    derived_src = str(derived.get("source") or "")
    if source in ("hub_deploy_plan", "hub_stamp", "stamp_deploy_plan_v1"):
        return True
    if derived_src in ("hub_deploy_plan", "hub_stamp"):
        return True
    # Explicit hub board fields without a debrief/player/opening source → hub.
    if order.get("hubChoiceId") and source not in (
        "debrief",
        "va_next_sortie_choice",
        "player_pick",
        "mode_a_quest",
        "quest_generator",
        "opening_mission",
        "opening",
        "authored_opening",
        "",
    ):
        return True
    return False


def _is_player_debrief_sortie(order: Dict[str, Any]) -> bool:
    if not isinstance(order, dict):
        return False
    source = str(order.get("source") or "")
    if source in ("debrief", "va_next_sortie_choice", "player_pick", "in_engine_debrief"):
        return True
    if order.get("fromDebrief") or order.get("debriefPick"):
        return True
    return False


def consume_played_hub_sorties(
    workspace: Optional[Path],
    result: Dict[str, Any],
    map_id: Optional[str],
) -> Dict[str, Any]:
    """After a sortie resolves, drop spent hub stamps so Mode A can walk the next node.

    Keeps in-engine debrief picks (1/2/3). Archives hub-stamped orders that
    match the map just played so materialize_next_intent does not re-issue the
    same C&C board forever.
    """
    report: Dict[str, Any] = {"cleared": [], "kept": [], "archived": []}
    if workspace is None:
        return report
    outbox = Path(workspace) / "outbox"
    played_map = canonical_map_id(map_id or result.get("mapId") or result.get("deploymentMapId"))
    played_target = result.get("targetZoneId") or (
        (result.get("objectiveTarget") or {}).get("targetZoneId") if isinstance(result.get("objectiveTarget"), dict) else None
    )
    for name in ("next_sortie_choice.json", "next_sortie_order.json"):
        path = outbox / name
        if not path.is_file():
            continue
        try:
            order = load_json(path)
        except Exception:
            continue
        if not isinstance(order, dict):
            continue
        if _is_player_debrief_sortie(order):
            report["kept"].append({"file": name, "reason": "debrief_pick"})
            continue
        order_map = canonical_map_id(order.get("mapId") or order.get("map"))
        order_target = order.get("targetZoneId")
        same_map = bool(played_map and order_map and order_map == played_map)
        same_target = bool(played_target and order_target and order_target == played_target)
        # Consume hub stamps on the map just played; also any explicit hubChoice board.
        # Drop 4 bug fix: ALSO consume Mode A auto-picks on the played map.
        # materialize_next_intent persists its graph-walk pick to
        # next_sortie_order.json; leaving it there made every later mission
        # reload the SAME contract (same kind, same zone — even after that
        # zone flipped to the player), overriding the quest board forever.
        hub_stamped = _is_hub_stamped_sortie(order)
        if hub_stamped and (same_map or same_target or order.get("hubChoiceId")):
            try:
                archive = outbox / f"{path.stem}.last.json"
                save_json(archive, {**order, "consumedAt": utc_now(), "consumedReason": "played_hub_sortie"})
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
                report["cleared"].append(name)
                report["archived"].append(str(archive.name))
            except Exception as e:  # noqa: BLE001
                report.setdefault("errors", []).append(f"{name}: {e}")
        elif (not hub_stamped) and (same_map or same_target):
            try:
                archive = outbox / f"{path.stem}.last.json"
                save_json(archive, {**order, "consumedAt": utc_now(), "consumedReason": "played_mode_a_sortie"})
                path.unlink(missing_ok=True)  # type: ignore[call-arg]
                report["cleared"].append(name)
                report["archived"].append(str(archive.name))
            except Exception as e:  # noqa: BLE001
                report.setdefault("errors", []).append(f"{name}: {e}")
        else:
            report["kept"].append({
                "file": name,
                "reason": "not_hub_or_other_map",
                "mapId": order_map,
                "hub": hub_stamped,
            })
    return report


def generate_mode_a_sortie(state: Dict[str, Any], workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Build a same-map legal sortie from world_zone_graph quest walk."""
    if workspace is None:
        return None
    home = _session_home_map(state, workspace)
    cands = generate_quests(
        Path(workspace),
        state,
        map_id=home,
        patron="nullmercs",
        limit=6,
    )
    try:
        write_quest_batch(Path(workspace), cands)
    except Exception:
        pass
    if not cands:
        return None
    pick = dict(cands[0])
    pick["valid"] = True
    pick["sessionMode"] = "same_map"
    pick["occupationModel"] = "living_shell"
    pick["source"] = "mode_a_quest"
    pick.pop("score", None)
    pick.pop("graphEdgeKind", None)
    # Keep human label for hub open-node paint when quest_batch is read
    if not pick.get("label"):
        pick.pop("label", None)
    return pick


def objective_from_sortie(order: Dict[str, Any], state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Build objectiveTarget from a validated sortie order (contract)."""
    zone_id = order["targetZoneId"]
    map_id = order["mapId"]
    archetype = order.get("objectiveArchetype") or "gate_control"
    against = order.get("against") or "neutral"
    # Plain words, as the hub writes them: "Raid Southeast Plateau".
    zone_label = ((state.get("zoneMemory") or {}).get(map_id, {}) or {}).get(zone_id, {}).get("label")
    if not zone_label and workspace is not None:
        authored = zone_maps_from_workspace(Path(workspace)).get(canonical_map_id(map_id)) or {}
        zone_label = next((z.get("label") for z in authored.get("zones") or [] if z.get("zoneId") == zone_id), None)
    label = str(order.get("label") or f"{ARCHETYPE_VERB.get(archetype, 'Strike')} {zone_label or zone_id}")
    obj = {
        "id": zone_id,
        "kind": archetype,
        "label": label,
        "targetZoneId": zone_id,
        "enemyFaction": against,
        "patron": order.get("patron"),
        "fromZoneIds": list(order.get("fromZoneIds") or []),
        "contractXp": order.get("contractXp"),
        "difficulty": order.get("difficulty"),
        "namedDefender": order.get("namedDefender"),
    }
    # Hub capture contracts: clear living-shell pocket + hold under regrow.
    try:

        obj = stamp_objective_capture(obj, order)
    except Exception:
        if archetype in ("seize_lane", "gate_control", "hold_plateau"):
            obj["captureMode"] = "clear_hold_shell"
            obj["description"] = f"Clear pocket + hold under regrow to claim {zone_id}"
    return obj


def build_escalation_plan(state: Dict[str, Any], map_id: str, objective: Dict[str, Any],
                          finale_plan: Optional[Dict[str, Any]],
                          workspace: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Drop 4: the authored escalation for this mission — scale window,
    objective strength (surgical/raze/purge), waves override, and secondary
    objectives resolved to real zones off the quest board (always distinct
    from the primary target). Compiler and gadget both honor this stamp."""
    mission_num = int(state.get("missionNumber", 1) or 1)
    plan = ladder.plan_for_mission(mission_num, bool(finale_plan), workspace)
    specs = list(plan.get("secondaries") or [])
    resolved: List[Dict[str, Any]] = []
    if specs and not finale_plan:
        primary = str(objective.get("targetZoneId") or "")
        taken = {primary}
        try:
            ws = Path(workspace) if workspace else WORKSPACE_ROOT
            cands = qg.generate_quests(ws, state, map_id=map_id, limit=8)
        except Exception:
            cands = []
        for spec in specs:
            zone = None
            label = ""
            for cand in cands:
                zid = str(cand.get("targetZoneId") or "")
                if zid and zid not in taken:
                    zone, label = zid, str(cand.get("label") or zid)
                    break
            if not zone:
                # Not enough distinct zones on this board — drop the spec
                # rather than doubling up on the primary.
                continue
            taken.add(zone)
            resolved.append({
                "id": "sec_" + zone.lower(),
                "zoneId": zone,
                "label": label,
                "required": bool(spec.get("required")),
            })
    return {
        "missionNumber": mission_num,
        "scaleWindow": list(plan.get("scaleWindow") or []),
        "objectiveStrength": str(plan.get("objectiveStrength") or "surgical"),
        "wavesMode": plan.get("wavesMode"),
        "secondaries": resolved,
    }


__all__ = [
    "_is_hub_stamped_sortie",
    "_is_player_debrief_sortie",
    "_session_home_map",
    "apply_sealed_company_to_packet",
    "available_allies",
    "build_escalation_plan",
    "consume_played_hub_sorties",
    "generate_mode_a_sortie",
    "load_sortie_order",
    "objective_from_sortie",
    "opening_hub_choice",
    "opening_sortie_order",
]
