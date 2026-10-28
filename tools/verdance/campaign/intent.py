"""Intent dressing: landable zones and pads, enemy scale, economy, difficulty presentation and story events.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, clamp, load_json, utc_now
from .schema import CAMPAIGN_ID, EVENTS_SCHEMA
from .acts import act_for_mission
from .progression import ensure_progression
from .measure import expected_presence_band
from .voice import load_ketha_voice, pick_line, result_streak
from .objectives import zone_center_norm
from verdance.world import roads as _roads, escalation_ladder as _ladder

# A landing zone this wet at rest is a beach, not a beachhead.
DRY_ENOUGH_TO_LAND = 0.35


def load_zone_map(map_id: str, workspace: Optional[Path] = None) -> Dict[str, Any]:
    roots: List[Path] = []
    if workspace is not None:
        roots.append(Path(workspace) / "data" / "zone_maps" / "authored")
    roots.append(WORKSPACE_ROOT / "data" / "zone_maps" / "authored")
    for root in roots:
        path = root / f"{map_id}.authored.zone_map.json"
        if path.exists():
            try:
                data = load_json(path)
                if isinstance(data, dict) and data.get("zones"):
                    return data
            except Exception:
                continue
    return {}


def zone_is_landable(zone: Dict[str, Any], level: float) -> bool:
    """Dry enough to put an army on, at THIS mission's waterline.

    campEligible is a static property -- can this ground ever hold a camp. It
    cannot know that the campaign has since flooded the basin, so the dynamic
    check belongs here."""
    if not zone:
        return False
    if not zone.get("campEligible", True):
        return False
    hydro = zone.get("hydrology") or {}
    if float(hydro.get("restingSubmerged", 0.0) or 0.0) >= DRY_ENOUGH_TO_LAND:
        return False
    floods_at = float(hydro.get("floodsAt", 2.0) or 2.0)
    return floods_at > float(level)


# A zone rect wider than this is a region, not a pad. Its centre often sits
# in the river even when the anchor is on a shelf (Rock Jungle gates).
PAD_SPAN_MAX = 0.50
# Farther than the nearest dry pad by this much is a cross-map haul.
NEAR_PAD_SLACK = 0.12
# Absolute cap: a corner muster on the other shore is not a walk.
NEAR_PAD_CAP = 0.40


def _pad_span_ok(zone: Dict[str, Any], limit: float = PAD_SPAN_MAX) -> bool:
    bounds = zone.get("bounds") or {}
    try:
        sx = abs(float(bounds.get("xMax", 1.0)) - float(bounds.get("xMin", 0.0)))
        sz = abs(float(bounds.get("zMax", 1.0)) - float(bounds.get("zMin", 0.0)))
    except (TypeError, ValueError):
        return False
    return 0.02 <= sx <= limit and 0.02 <= sz <= limit


def _anchor_dist(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ax, az = zone_center_norm(a)
    bx, bz = zone_center_norm(b)
    return ((ax - bx) ** 2 + (az - bz) ** 2) ** 0.5


def ground_pads_by_distance(
    map_id: str,
    target_zone_id: str,
    workspace: Optional[Path] = None,
    level: float = 0.0,
    zones: Optional[Dict[str, Any]] = None,
) -> List[Tuple[float, str]]:
    """Dry, pad-sized zones nearest the objective anchor. Ground exfil only.

    Skips flooded basins and map-wide rects. The nearest hit is the shore a
    kbot can walk to; a far dry corner across the river is left off the front.
    """
    if zones is None:
        zones = {
            str(z.get("zoneId")): z
            for z in (load_zone_map(map_id, workspace).get("zones") or [])
            if z.get("zoneId")
        }
    target = zones.get(str(target_zone_id)) or {}
    if not target:
        return []
    ranked: List[Tuple[float, str]] = []
    for zid, zone in zones.items():
        if zid == str(target_zone_id):
            continue
        if not zone_is_landable(zone, level):
            continue
        if not _pad_span_ok(zone):
            continue
        ranked.append((_anchor_dist(target, zone), zid))
    ranked.sort()
    return ranked


def ground_pad_is_near(
    zone_id: str,
    map_id: str,
    target_zone_id: str,
    workspace: Optional[Path] = None,
    level: float = 0.0,
    zones: Optional[Dict[str, Any]] = None,
    ranked: Optional[List[Tuple[float, str]]] = None,
) -> bool:
    """True when this pad is dry, pad-sized, and on the objective's shore."""
    if zones is None:
        zones = {
            str(z.get("zoneId")): z
            for z in (load_zone_map(map_id, workspace).get("zones") or [])
            if z.get("zoneId")
        }
    zone = zones.get(str(zone_id)) or {}
    target = zones.get(str(target_zone_id)) or {}
    if not zone or not target:
        return False
    if str(zone_id) == str(target_zone_id):
        return False
    if not zone_is_landable(zone, level) or not _pad_span_ok(zone):
        return False
    if ranked is None:
        ranked = ground_pads_by_distance(
            map_id, target_zone_id, workspace, level, zones
        )
    if not ranked:
        return False
    dist = _anchor_dist(target, zone)
    best = ranked[0][0]
    return dist <= best + NEAR_PAD_SLACK and dist <= max(NEAR_PAD_CAP, best + 0.02)


def separate_intent_zones(intent: Dict[str, Any],
                          workspace: Optional[Path] = None,
                          state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Infil and exfil are dry pads the company can walk to from the objective.

    With the campaign state in hand, a pad is only ever somewhere the company may land: a door it
    holds or ground it holds (landing_zones). A pad that is not, or that the water has taken,
    moves to the nearest such pad, never onto open ground.

    The objective may sit in a flooded basin. A dry corner on the far shore is
    not an exit: at Rock Jungle's river level that crossing needs air
    transport, and far is a bad walk even when the graph draws an edge.
    Landing and leaving on the same near pad is intentional.
    """
    target = intent.get("targetZoneId")
    if not isinstance(target, str) or not target:
        return intent
    map_id = str(intent.get("mapId") or "")
    zones = {
        str(z.get("zoneId")): z
        for z in (load_zone_map(map_id, workspace).get("zones") or [])
        if z.get("zoneId")
    }
    if not zones or target not in zones:
        return intent
    level = float(((intent.get("hydrology") or {}).get("level")) or 0.0)
    ranked = ground_pads_by_distance(map_id, target, workspace, level, zones)

    def _near(zid: Optional[str]) -> bool:
        return bool(zid) and ground_pad_is_near(
            str(zid), map_id, target, workspace, level, zones, ranked
        )

    def _write(key: str, zid: str) -> None:
        intent[key] = zid
        if key == "extractionZoneId":
            objective = intent.get("objectiveTarget")
            if isinstance(objective, dict):
                objective["extractionZoneId"] = zid

    nearest = ranked[0][1] if ranked else None
    # A door is the way off this map: the nearest dry shore of an inland hero must not
    # move a pad that stands on one. Other pads still snap.
    def _mouth(zid: Any) -> bool:
        return _roads.is_door(zid, workspace)

    deploy = intent.get("deploymentZoneId")
    stamped = str(intent.get("source") or "") in ("hub_deploy_plan", "hub_stamp", "stamp_deploy_plan_v1")

    def _landable(zid: Any) -> bool:
        try:
            return zone_is_landable(zones.get(str(zid)) or {}, level)
        except Exception:
            return True

    if state is not None:
        from verdance.world import landing_zones as _lz

        def _ours(zid: Any) -> bool:
            return _lz.is_legal_landing(state, map_id, str(zid), (zones.get(str(zid)) or {}).get("bounds") or {})

        if isinstance(deploy, str) and deploy and not (_ours(deploy) and _landable(deploy)):
            tz = zones.get(target) or {}
            pads = sorted((_anchor_dist(tz, z), zid) for zid, z in zones.items()
                          if zid != target and _ours(zid) and _landable(zid))
            if pads:
                intent["padSnapped"] = {"from": deploy, "to": pads[0][1],
                                        "reason": "flooded" if not _landable(deploy) else "not_ours"}
                _write("deploymentZoneId", pads[0][1])
    elif isinstance(deploy, str) and deploy and not _mouth(deploy) and not _near(deploy):
        # No ledger (tools, old tests): the pad the player stamped is theirs and moves only when
        # flooded; an engine-chosen pad snaps to the nearest dry shore.
        if nearest and (not stamped or not _landable(deploy)):
            intent["padSnapped"] = {"from": deploy, "to": nearest, "reason": "flooded" if not _landable(deploy) else "far_from_objective"}
            _write("deploymentZoneId", nearest)
    deploy = intent.get("deploymentZoneId")
    extract = intent.get("extractionZoneId")
    if not intent.get("finale") and isinstance(deploy, str) and deploy:
        # One pad: the company lifts where it landed. Only a finale names a different door.
        if extract != deploy:
            _write("extractionZoneId", deploy)
        return intent
    if not _mouth(extract) and not _near(extract if isinstance(extract, str) else None):
        if _mouth(deploy) or _near(deploy if isinstance(deploy, str) else None):
            _write("extractionZoneId", str(deploy))
        elif nearest:
            _write("extractionZoneId", nearest)
    return intent


def expected_map_enemy_scale(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    zones = state.get("zoneMemory", {}).get(map_id, {})
    bands = [expected_presence_band(map_id, z) for z in zones.values()]
    if not bands:
        return {"low": 3000, "center": 6000, "high": 10000, "basis": "default_no_zone_memory"}
    return {
        "low": int(sum(b["low"] for b in bands)),
        "center": int(sum(b["center"] for b in bands)),
        "high": int(sum(b["high"] for b in bands)),
        "basis": "zone_memory_abstract_state",
    }


def _economy_for_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    """Difficulty clarity pass: dial is the loud knob; graph is a soft nudge.

    Scarcity no longer starves early sorties into a corner (floor raised).
    Contested pressure multiplies less aggressively so the mission card label
    stays trustworthy.
    """
    prog = ensure_progression(state)
    dial = float(prog.get("difficultyDial", 1.0) or 1.0)
    graph = state.get("graph", {}) or {}
    q6 = float(graph.get("q6_contested", 0.5) or 0.5)
    q7 = float(graph.get("q7_resource_scarcity", 0.0) or 0.0)
    # Milder contested coeff (was *0.25); dial multiplies on top.
    coeff = (1.0 + q6 * 0.14) * dial
    # Resource floor 0.90 (was 0.80) so scarcity never obscures "what do I do".
    resource = clamp(1.12 - q7 * 0.22, 0.90, 1.15)
    return {
        "difficultyCoefficient": round(coeff, 3),
        "resourceModifier": round(resource, 3),
        "difficultyDial": round(dial, 3),
        "graphContested": round(q6, 3),
        "graphScarcity": round(q7, 3),
    }


def _difficulty_presentation(state: Dict[str, Any], map_id: str) -> Dict[str, Any]:
    """Plain-English difficulty readout for mission card + HUD (no fog)."""
    eco = _economy_for_intent(state)
    scale_center = float(expected_map_enemy_scale(state, map_id).get("center") or 6000.0)
    mission_n = int(state.get("missionNumber", 1) or 1)
    ramp = min(1.0, 0.7 + 0.15 * (mission_n - 1))
    # Preview the compiler's enemyScale formula (clarity mirror).
    raw = max(0.7, min(2.2, scale_center / 6000.0)) * float(eco["difficultyCoefficient"]) * ramp
    preview = round(raw, 3)
    # Drop 4: the compiler clamps the field into the ladder's scale window, so
    # clamp the card preview the same way — the card must not promise "heavy"
    # on a mission the window pins to "light".
    try:
        is_finale = act_for_mission(mission_n) >= 3
        window = _ladder.plan_for_mission(mission_n, is_finale).get("scaleWindow")
        preview = _ladder.clamp_scale(preview, window, float(eco["difficultyDial"] or 1.0))
    except Exception:
        pass
    if preview >= 1.6:
        band = "heavy"
    elif preview >= 1.2:
        band = "reinforced"
    elif preview <= 0.85:
        band = "light"
    else:
        band = "standard"
    prog = ensure_progression(state)
    return {
        "band": band,
        "enemyScalePreview": preview,
        "difficultyDial": eco["difficultyDial"],
        "onboardingRamp": round(ramp, 3),
        "missionNumber": mission_n,
        "label": f"Expected opposition: {band} (scale {preview:.2f})",
        "dialLine": f"Difficulty dial {eco['difficultyDial']:.2f} | ramp M{mission_n}",
        "mode": prog.get("mode"),
    }


def intent_story_tags(map_id: str, family: str, pressure: Dict[str, Any]) -> List[str]:
    tags = [family, map_id]
    if family == "wild":
        tags.append("extract-before-overrun")
    if pressure.get("maxFortification", 0) > 0.55:
        tags.append("fortress-pressure")
    if pressure.get("maxHazard", 0) > 0.5:
        tags.append("hazard-rising")
    return tags


def story_reason_for_intent(map_id: str, family: str, pressure: Dict[str, Any]) -> str:
    if map_id == "ancient_bastion":
        return "Bastion defenses have continued developing offscreen; strike one key wing and extract before counterpressure peaks."
    if family == "wild":
        return "Wild pressure resets live units between sorties, but surviving hives have escalated the zone hazard."
    if family == "economy":
        return "Economy state is the current campaign bottleneck; disrupt or secure converter momentum."
    return "Current graph pressure favors a short objective sortie over full map conquest."


def generate_story_events(state: Dict[str, Any], result: Dict[str, Any], bead: Optional[Dict[str, Any]],
                          processed: bool, workspace: Optional[Path] = None) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    if not processed:
        events.append({
            "kind": "warning",
            "tags": ["duplicate-result"],
            "text": "Duplicate result skipped; campaign state was not mutated.",
        })
    else:
        voice = load_ketha_voice(workspace)
        tags = bead.get("storyTags", []) if bead else []
        status = str(result.get("status", "unknown"))
        seed = (state.get("campaignId", CAMPAIGN_ID), result.get("missionId", "va_unknown"), status)

        # Primary debrief line: most specific matching pool wins.
        pool_key = "debrief.victory"
        if status in ("defeat", "failed", "failure"):
            pool_key = "debrief.defeat_commander" if result.get("terminalReason") == "commander_lost" else "debrief.defeat"
        elif status in ("partial", "extracted"):
            pool_key = "debrief.partial"
        elif result.get("destroyedObjectiveIds"):
            pool_key = "debrief.objective_destroyed"
        elif any(str(t).startswith("extract-clean") for t in tags):
            pool_key = "debrief.victory_clean"
        text = pick_line(voice, pool_key, *seed) or "The map gave us a measurement. Now it starts lying again."
        events.append({
            "kind": "dialogue",
            "speaker": voice.get("speaker", "ketha"),
            "tone": "field",
            "text": text,
            "tags": tags,
        })

        # Pillar D: Ketha names the ground the campaign lost to front decay while
        # the player was elsewhere ({zone} interpolated from the latest flip).
        if "territory-lost" in tags:
            lost = [e for e in state.get("frontEvents", []) if e.get("type") == "zone_lost"]
            if lost:
                zone_label = lost[-1].get("label") or lost[-1].get("zoneId") or "a foothold"
                line = pick_line(voice, "debrief.territory_lost", *seed)
                if line:
                    events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                                   "tone": "grim", "text": line.replace("{zone}", str(zone_label)),
                                   "tags": ["territory-lost", str(lost[-1].get("zoneId", ""))]})

        # Streak commentary: the line notices runs of results.
        streak_kind, streak_len = result_streak(state)
        if streak_len >= 3 and streak_kind == "win":
            streak_text = pick_line(voice, "debrief.streak.wins", *seed)
            if streak_text:
                events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                               "tone": "reflective", "text": streak_text, "tags": ["streak", "wins-" + str(streak_len)]})
        elif streak_len >= 2 and streak_kind == "loss":
            streak_text = pick_line(voice, "debrief.streak.losses", *seed)
            if streak_text:
                events.append({"kind": "dialogue", "speaker": voice.get("speaker", "ketha"),
                               "tone": "reflective", "text": streak_text, "tags": ["streak", "losses-" + str(streak_len)]})

        events.append({
            "kind": "mission_hook",
            "tags": ["next-intent"],
            "text": "Next mission intent materialized from measured and offscreen campaign state.",
        })
    return {
        "schemaVersion": EVENTS_SCHEMA,
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "generatedAt": utc_now(),
        "events": events,
    }


__all__ = [
    "DRY_ENOUGH_TO_LAND",
    "NEAR_PAD_CAP",
    "NEAR_PAD_SLACK",
    "PAD_SPAN_MAX",
    "_anchor_dist",
    "_difficulty_presentation",
    "_economy_for_intent",
    "_pad_span_ok",
    "expected_map_enemy_scale",
    "generate_story_events",
    "ground_pad_is_near",
    "ground_pads_by_distance",
    "intent_story_tags",
    "load_zone_map",
    "separate_intent_zones",
    "story_reason_for_intent",
    "zone_is_landable",
]
