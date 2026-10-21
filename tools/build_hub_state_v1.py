#!/usr/bin/env python3
"""Build hub_state.v1 for the HTML war-map CYOA (G1).

Reads campaign_state + war_map + commerce catalog, writes app/showoff/hub_state.json
and a JS embed snippet app/showoff/hub_state.embed.js for file:// open.

Shop surface is a read-only projection of the commerce catalog + campaign bag
(no story-engine mutation). Deploy wire lives in the HTML host (POST /api/deploy).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "state" / "campaign_state.json"
WAR_MAP_PATH = ROOT / "outbox" / "war_map.json"
CATALOG_PATH = ROOT / "data" / "commerce" / "commerce_catalog.json"
OUT_JSON = ROOT / "app" / "showoff" / "hub_state.json"
OUT_EMBED = ROOT / "app" / "showoff" / "hub_state.embed.js"

# Mission selection is owned by the story engine. This module only projects
# the canonical order into the C&C board; it must not invent a second route.
from verdance_story_engine_v1 import opening_hub_choice
try:
    import hub_belief_v1  # pass six: the board paints belief, never truth
except Exception:  # noqa: BLE001
    hub_belief_v1 = None

try:
    from commerce_delivery_v1 import delivery_eta
except ImportError:  # pragma: no cover
    from tools.commerce_delivery_v1 import delivery_eta  # type: ignore

BAY_THRESHOLD = 40


def arc_from_mission(mission_n: int) -> dict:
    """Campaign arcs: 1-5 First Scar, 6-10 Second, 11+ Third.
    C&C board: arc1 = 1 capture mark; arc2 = 2; arc3 = 3.
    """
    n = max(1, int(mission_n or 1))
    if n <= 5:
        return {"id": 1, "title": "First Scar", "maxCaptureMarks": 1, "maxMissionsInArc": 5}
    if n <= 10:
        return {"id": 2, "title": "Second Scar", "maxCaptureMarks": 2, "maxMissionsInArc": 5}
    return {"id": 3, "title": "Third Scar", "maxCaptureMarks": 3, "maxMissionsInArc": 5}


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def rank_from_level(level: int) -> str:
    return {1: "Runner", 2: "Scarred", 3: "Captain", 4: "Legend"}.get(level, f"Lv{level}")


def build_aces(state: dict) -> list[dict]:
    _away = hub_belief_v1.away_from_camp(state) if hub_belief_v1 else set()
    characters = state.get("characters") or {}
    roster = (state.get("roster") or {}).get("heroes") or []
    by_id = {h.get("heroId"): h for h in roster if h.get("heroId")}

    aces = []
    # Prefer player roster order; fall back to player-flagged characters
    order = [h.get("heroId") for h in roster if h.get("heroId")]
    if not order:
        order = [cid for cid, c in characters.items() if c.get("player")]

    for hid in order:
        ch = characters.get(hid) or {}
        rh = by_id.get(hid) or {}
        level = int(rh.get("level") or 1)
        ace = {
            "id": hid,
            "name": rh.get("name") or ch.get("name") or hid,
            "faction": ch.get("faction") or "ashwalkers",
            "unitDef": rh.get("unitDef") or ch.get("unitDef") or "legcen",
            "level": level,
            "rank": rh.get("rank") or rank_from_level(level),
            "campaignXp": float(rh.get("campaignXp") or ch.get("xp") or 0),
            "wounds": int(ch.get("wounds") or rh.get("timesWounded") or 0),
            "status": rh.get("status") or ch.get("status") or "active",
            "scars": list(ch.get("scars") or rh.get("scars") or []),
            "deployable": ((rh.get("status") or ch.get("status") or "active") == "active") and (hid not in _away),
            "where": ((state.get("camp") or {}).get("people") or {}).get(hid, {}).get("where") or "camp",
            "bonds": dict(ch.get("bonds") or {}),
            "loadout": ch.get("loadout") or {"modules": [], "bayTier": 0},
        }
        # Seed vane↔ketha bond if missing
        if hid == "vane" and "ketha" not in ace["bonds"]:
            ace["bonds"]["ketha"] = 10
        if hid == "ketha" and "vane" not in ace["bonds"]:
            ace["bonds"]["vane"] = 10
        aces.append(ace)

    return aces


def _support_web_surface(
    aces: list, company_surface: dict, state: dict | None = None
) -> dict:
    """FE support-web projection for hub (hearth + highlights)."""
    web_path = ROOT / "data" / "story" / "support_web.json"
    talks_path = ROOT / "data" / "story" / "camp_talks.json"
    out: dict = {
        "schemaVersion": "verdance-support-web-surface/1.0",
        "available": False,
        "edgeCount": 0,
        "talkCount": 0,
        "topPairs": [],
        "eligibleTalks": [],
        "note": "Parametric relationship web — hearth talks wire next.",
    }
    if not web_path.is_file():
        return out
    try:
        web = json.loads(web_path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return out

    ace_ids = {str(a.get("id")) for a in (aces or []) if a.get("id")}

    def _as_hid(raw) -> str | None:
        if isinstance(raw, dict):
            hid = raw.get("id") or raw.get("heroId")
            return str(hid) if hid else None
        if raw is None:
            return None
        s = str(raw).strip()
        return s or None

    # Company band + core are the camp circle; fall back to all aces.
    circle = set()
    if isinstance(company_surface, dict):
        for key in ("core", "band", "joinedLater"):
            for raw in company_surface.get(key) or []:
                hid = _as_hid(raw)
                if hid:
                    circle.add(hid)
    if not circle:
        circle = set(ace_ids)

    def _pair_row(e: dict) -> dict:
        return {
            "id": e.get("id"),
            "a": e.get("a"),
            "b": e.get("b"),
            "aName": e.get("aName"),
            "bName": e.get("bName"),
            "score": e.get("score"),
            "polarity": e.get("polarity"),
            "motif": (e.get("motifs") or [None])[0],
            "authored": bool(e.get("authored")),
        }

    all_edges = [e for e in (web.get("edges") or []) if isinstance(e, dict)]
    all_edges.sort(key=lambda e: -float(e.get("score") or 0))
    circle_edges = [
        e
        for e in all_edges
        if str(e.get("a")) in circle and str(e.get("b")) in circle
    ]
    authored = [e for e in all_edges if e.get("authored")]
    out["available"] = True
    out["edgeCount"] = len(all_edges)
    out["circleEdgeCount"] = len(circle_edges)
    out["circle"] = sorted(circle)
    # Camp-circle pairs first (hearth-eligible); fall back to authored highlights.
    out["topPairs"] = [_pair_row(e) for e in (circle_edges or authored)[:12]]
    out["highlights"] = [_pair_row(e) for e in authored[:12]]

    pair_points: dict = {}
    if isinstance(state, dict):
        att = state.get("attachments") or {}
        for pk, row in (att.get("pairBonds") or {}).items():
            if isinstance(row, dict):
                pair_points[str(pk)] = {
                    "points": float(row.get("points") or 0),
                    "rank": row.get("rank"),
                    "talksDone": list(row.get("talksDone") or []),
                }
    out["pairBonds"] = pair_points

    if talks_path.is_file():
        try:
            talks_doc = json.loads(talks_path.read_text(encoding="utf-8-sig"))
            talks = talks_doc.get("talks") or []
            out["talkCount"] = len(talks)
            out["authoredTalkCount"] = sum(
                1 for t in talks if isinstance(t, dict) and t.get("generated") is False
            )

            def _eligible_rank(t: dict) -> bool:
                """Next unread rank for this pair given bond points."""
                if not isinstance(t, dict):
                    return False
                pid = str(t.get("pairId") or "")
                rank = str(t.get("rank") or "C")
                pb = pair_points.get(pid) or {}
                done = set(pb.get("talksDone") or [])
                tid = str(t.get("id") or "")
                if tid in done:
                    return False
                pts = float(pb.get("points") or 0)
                bond_min = float((t.get("unlock") or {}).get("bondMin") or 0)
                if pts < bond_min:
                    return False
                # Prefer lowest unread rank
                return True

            eligible = []
            for t in talks:
                if not isinstance(t, dict):
                    continue
                if str(t.get("a")) not in circle or str(t.get("b")) not in circle:
                    continue
                if not _eligible_rank(t):
                    continue
                eligible.append(
                    {
                        "id": t.get("id"),
                        "pairId": t.get("pairId"),
                        "title": t.get("title"),
                        "polarity": t.get("polarity"),
                        "motif": t.get("motif"),
                        "rank": t.get("rank"),
                        "a": t.get("a"),
                        "b": t.get("b"),
                        "authored": t.get("generated") is False,
                        "beats": list(t.get("beats") or [])[:10],
                        "unlock": t.get("unlock") or {},
                    }
                )
            # Prefer authored, then C, then score-ish by rank letter
            rank_ord = {"C": 0, "B": 1, "A": 2}

            def _sort_key(x: dict):
                return (
                    0 if x.get("authored") else 1,
                    rank_ord.get(str(x.get("rank")), 9),
                    str(x.get("id") or ""),
                )

            eligible.sort(key=_sort_key)
            # One talk per pair (lowest rank first)
            seen_pairs = set()
            deduped = []
            for t in eligible:
                pid = t.get("pairId")
                if pid in seen_pairs:
                    continue
                seen_pairs.add(pid)
                deduped.append(t)
            out["eligibleTalks"] = deduped[:12]
        except Exception:  # noqa: BLE001
            pass
    return out


def build_regions(war: dict) -> list[dict]:
    """Theater chips: name and family only. war_map's control / dominantEnemy / threatBand /
    controlCounts are the engine's truth (summarize_front) and never reach the hub; the chip's
    known/stale/dark counts come from hub.belief at render time."""
    regions = []
    for r in war.get("regions") or []:
        regions.append(
            {
                "mapId": r.get("mapId"),
                "displayName": r.get("displayName") or r.get("mapId"),
                "descriptor": r.get("descriptor") or "",
                "family": r.get("family") or "tempo",
                "selectable": True,
            }
        )
    return regions


HOME_MAP_ID = "the_rock_jungle"
# Raid theaters must never steal sessionHomeMap from the Ashwalker camp.
RAID_THEATER_MAPS = {
    "greenest_fields",
    "eye_of_horus",
    "koom_valley",
    "tabula",
    "ancient_bastion",
    "all_that_simmers",
}


def repair_session_home(state: dict) -> str:
    """Keep sessionHomeMap on homeCamp; raid sorties used to overwrite it to Greenest."""
    camp = (state.get("homeCamp") or {}).get("mapId") or state.get("homeMapId") or HOME_MAP_ID
    camp = str(camp)
    home = str(state.get("sessionHomeMap") or camp)
    if home in RAID_THEATER_MAPS and camp == HOME_MAP_ID:
        state["sessionHomeMap"] = camp
        return camp
    state.setdefault("sessionHomeMap", camp)
    return str(state.get("sessionHomeMap") or camp)


def pick_focus_region(regions: list[dict], state: dict | None = None) -> str:
    """Mode A: stay on session home map when set; default Ashwalker home = Rock Jungle."""
    st = state or {}
    session_mode = st.get("sessionMode") or "same_map"
    home = repair_session_home(st)
    region_ids = {r.get("mapId") for r in regions}
    if session_mode == "same_map" and home and home in region_ids:
        return home
    # Last history bead map (post-advance Mode A footprint)
    hist = st.get("history") or []
    if hist and isinstance(hist[-1], dict):
        last_map = hist[-1].get("mapId")
        if last_map and last_map in region_ids:
            return last_map
    if HOME_MAP_ID in region_ids:
        return HOME_MAP_ID
    for r in regions:
        if r.get("family") in ("wild", "economy"):
            return r["mapId"]
    return regions[0]["mapId"] if regions else HOME_MAP_ID


def _near_ground_pad(map_id: str, target_zone: str) -> str | None:
    """Nearest dry pad-sized shore to the objective. None if the map has no pads."""
    try:
        from verdance_story_engine_v1 import ground_pads_by_distance

        ranked = ground_pads_by_distance(map_id, target_zone, ROOT, 0.0)
    except Exception:  # noqa: BLE001
        return None
    return ranked[0][1] if ranked else None


def _pad_is_near(zone_id: str, map_id: str, target_zone: str) -> bool:
    if not zone_id:
        return False
    try:
        from verdance_story_engine_v1 import ground_pad_is_near

        return bool(ground_pad_is_near(zone_id, map_id, target_zone, ROOT, 0.0))
    except Exception:  # noqa: BLE001
        return False


def _quest_continue_choices(
    state: dict, focus: str, deploy_aces: list, limit: int = 3
) -> list[dict]:
    """Surface Mode A / quest_batch candidates as hub deploy choices (same-map chain)."""
    out: list[dict] = []
    batch_path = ROOT / "outbox" / "quest_batch.latest.json"
    if not batch_path.is_file():
        return out
    try:
        batch = load_json(batch_path)
    except Exception:  # noqa: BLE001
        return out
    cands = batch.get("candidates") or batch.get("quests") or batch
    if isinstance(cands, dict):
        cands = cands.get("candidates") or []
    if not isinstance(cands, list):
        return out
    arch_verb = {
        "eco_raid": "Raid",
        "seize_lane": "Take",
        "strike_relay": "Cut",
        "destroy_key_structure": "Break",
        "hive_clear_or_bypass": "Clear",
        "gate_control": "Hold",
        "economy_disrupt": "Starve",
    }
    arch_blurb = {
        "eco_raid": "Hit the works. Leave before their guns arrive.",
        "seize_lane": "Stand on the scar and stay standing.",
        "strike_relay": "Drop the relay. Their dealers go quiet.",
        "destroy_key_structure": "Break one bone. Let gravity finish it.",
        "hive_clear_or_bypass": "Burn the nest or slip past it.",
        "gate_control": "Hold the gate until the map answers to us.",
        "economy_disrupt": "Make their economy a lie.",
    }
    spent = state.get("spentTheaters") if isinstance(state.get("spentTheaters"), dict) else {}
    for i, q in enumerate(cands[:limit]):
        if not isinstance(q, dict):
            continue
        map_id = q.get("mapId") or focus
        # Mode A: only same-map continues when session is locked
        if (state.get("sessionMode") or "same_map") == "same_map" and map_id != focus:
            continue
        # Blank / spent raid theaters must not reappear as Mode A continues.
        if map_id in spent and map_id in RAID_THEATER_MAPS:
            continue
        zone = q.get("targetZoneId") or q.get("zoneId")
        if not zone:
            continue
        zone_label = (
            q.get("label")
            or q.get("zoneLabel")
            or q.get("displayName")
            or str(zone).replace("_", " ").title()
        )
        # Strip internal "Continue —" prefixes; rebuild as mission cards.
        zl = str(zone_label)
        if zl.lower().startswith("continue"):
            zl = zl.split("—", 1)[-1].split("-", 1)[-1].strip() or zl
        arch = q.get("objectiveArchetype") or q.get("kind") or "seize_lane"
        verb = arch_verb.get(str(arch), "Strike")
        label = f"{verb} {zl}" if len(zl) < 40 else f"{verb} this pocket"
        blurb = arch_blurb.get(str(arch), "Drop in, cut the objective, come home.")
        from_ids = q.get("fromZoneIds") if isinstance(q.get("fromZoneIds"), list) else []
        from_pad = from_ids[0] if from_ids else q.get("deploymentZoneId")
        near_pad = _near_ground_pad(str(map_id), str(zone))
        deploy_pad = from_pad
        if near_pad and not _pad_is_near(str(from_pad or ""), str(map_id), str(zone)):
            deploy_pad = near_pad
        out.append(
            {
                "id": f"c_mode_a_{i}_{zone}",
                "label": label,
                "blurb": blurb,
                "kind": "deploy",
                "effect": {
                    "mapId": map_id,
                    "contractKind": arch,
                    "deployAces": deploy_aces,
                    "preferredCaptureZoneId": zone,
                    "preferredDeployZoneId": deploy_pad,
                    "preferredExtractionZoneId": near_pad or deploy_pad,
                    "sessionMode": "same_map",
                    "source": "quest_batch",
                },
            }
        )
    return out


def build_theater(state: dict, map_id: str, capture_contracts: list | None = None) -> dict:
    """Per-zone intel for the main-view theater board (geometry stays in ZONE_BOARDS)."""
    zm = (state.get("zoneMemory") or {}).get(map_id) or {}
    claims = state.get("nodeClaims") or state.get("claimedNodes") or {}
    open_ids: set[str] = set()
    open_targets: list[dict] = []
    for c in capture_contracts or []:
        if not isinstance(c, dict):
            continue
        if c.get("mapId") and c.get("mapId") != map_id:
            continue
        zid = c.get("targetZoneId") or c.get("zoneId")
        if not zid:
            continue
        open_ids.add(str(zid))
        open_targets.append(
            {
                "zoneId": zid,
                "label": c.get("label") or zid,
                "archetype": c.get("objectiveArchetype") or c.get("contractKind") or "seize_lane",
            }
        )
    zones_out: list[dict] = []
    # Pass six law: the board shows what the COMPANY believes. zoneMemory (truth) only names the
    # zones; colour, confidence, state and threat come from the belief frame.
    belief = {}
    if hub_belief_v1 is not None:
        try:
            belief = hub_belief_v1.belief_surface(ROOT, state, map_id).get("zones") or {}
        except Exception:  # noqa: BLE001
            belief = {}
    for zid, z in zm.items():
        if not isinstance(z, dict):
            continue
        abstract = z.get("abstract") or {}
        b = belief.get(str(zid)) or {"believed": "dark", "confidence": 0.0, "state": "dark", "faction": None}
        believed = b.get("believed") or "dark"
        # `control` keeps its old name for the renderer: a faction we believe holds it, "ashwalkers"
        # for ours, "empty"/"unknown" otherwise. Never the truth.
        if believed == "ours":
            control = "ashwalkers"
        elif believed == "held":
            control = str(b.get("faction") or "held").lower()
        elif believed == "empty":
            control = "empty"
        else:
            control = "unknown"
        claim_key = f"capture:{map_id}:{zid}"
        claimed = bool(
            claims.get(claim_key)
            or claims.get(zid)
            or (isinstance(claims.get(map_id), dict) and claims[map_id].get(zid))
        )
        zones_out.append(
            {
                "zoneId": zid,
                "label": z.get("label") or zid,
                "control": control,
                "believed": believed,
                "confidence": float(b.get("confidence") or 0.0),
                "state": b.get("state") or "dark",
                "ageMin": b.get("age_min"),
                "source": b.get("source"),
                "threat": b.get("threat"),
                "surprise": b.get("surprise"),
                "people": b.get("people") or [],
                "holding": int(b.get("holding") or 0),
                "openTarget": zid in open_ids,
                "claimed": claimed,
                "preferred": zid in open_ids or bool(abstract.get("preferredObjective")),
                "hazard": 0.0,
            }
        )
    # Prefer open targets even if zoneMemory empty for that id
    known = {z["zoneId"] for z in zones_out}
    for ot in open_targets:
        if ot["zoneId"] not in known:
            zones_out.append(
                {
                    "zoneId": ot["zoneId"],
                    "label": ot.get("label") or ot["zoneId"],
                    "control": "unknown",
                    "confidence": "contract",
                    "openTarget": True,
                    "claimed": False,
                    "preferred": True,
                    "hazard": 0.0,
                }
            )
    return {
        "mapId": map_id,
        "zones": zones_out,
        "openTargets": open_targets,
        "intelByZone": {z["zoneId"]: z for z in zones_out},
    }


def _wet_reach_choices(state: dict, deploy_aces: list) -> tuple[list[dict], str | None]:
    """The collapsed three. Each card says where you are and where you are heading."""
    try:
        from wet_reach_v1 import collapse_sorties
    except ImportError:
        return [], None
    try:
        collapsed = collapse_sorties(state, ROOT)
    except Exception as exc:  # noqa: BLE001
        print(f"VA_WET_REACH_HUB_FAIL {exc}")
        return [], None
    choices: list[dict] = []
    for card in collapsed.get("cards") or []:
        if not isinstance(card, dict):
            continue
        effect = dict(card.get("effect") or {})
        effect["deployAces"] = list(deploy_aces)
        choices.append({
            "id": card.get("id"),
            "label": card.get("label"),
            "blurb": card.get("blurb"),
            "kind": "deploy",
            "recommended": bool(card.get("recommended")),
            "effect": effect,
        })
    voice = str(collapsed.get("voice") or "") or None
    return choices, voice


def build_open_node(state: dict, regions: list[dict], aces: list[dict], rep: dict) -> dict:
    mission_n = int(state.get("missionNumber") or 1)
    focus = pick_focus_region(regions, state)
    focus_name = next((r["displayName"] for r in regions if r["mapId"] == focus), focus)
    null_rep = float(rep.get("nullmercs") or 0)
    session_mode = state.get("sessionMode") or "same_map"
    home = state.get("sessionHomeMap") or HOME_MAP_ID
    flags = state.get("flags") or {}
    camp = state.get("homeCamp") or {}
    camp_level = int(camp.get("level") or 0)
    tnb = int((state.get("commerce") or {}).get("tenebrium") or 0)
    home_ready = bool(flags.get("homeClearReady")) or tnb >= 3 or camp_level >= 1
    home_cleared = bool(flags.get("homeCleared"))
    fresh_opening = mission_n == 1 and not state.get("history") and not state.get("lastResult")

    # Prefer a raid theater (economy / crater) when sitting on home wilds.
    raid_map = "greenest_fields"
    for r in regions:
        if r["mapId"] != home and r.get("family") in ("economy", "tempo"):
            raid_map = r["mapId"]
            break
    crater = next((r["mapId"] for r in regions if r["mapId"] == "eye_of_horus"), None)

    deploy_aces = [a["id"] for a in aces if a.get("deployable")][:2]

    # The authored opening is a Greenest Fields raid. Rock Jungle is the locked
    # future home/camp objective, not the first recommended sortie. The story
    # engine owns the route and force; this builder only projects that choice.
    if fresh_opening:
        opening_choice = opening_hub_choice(state, ROOT)
        if not opening_choice:
            raise RuntimeError("fresh campaign has no canonical opening contract")
        choices = [opening_choice]
    else:
        spent_early = (
            state.get("spentTheaters")
            if isinstance(state.get("spentTheaters"), dict)
            else {}
        )
        focus_spent = focus in spent_early and focus in RAID_THEATER_MAPS
        # Prefer same-map continues (quest candidates) as the primary battle picks.
        # Skip when focus is a spent raid theater — outflow doors own that beat.
        mode_a = (
            []
            if focus_spent
            else _quest_continue_choices(state, focus, deploy_aces, limit=3)
        )
        if mode_a:
            choices = []
            for ch in mode_a:
                effect = dict(ch.get("effect") or {})
                choices.append({**ch, "effect": effect})
        elif focus_spent:
            # Empty primary; Journey A (home) + need_outflow (Eye / return) fill in.
            choices = []
        elif focus == HOME_MAP_ID:
            clear_blurb = (
                "The lagoon maze still breeds. You need Tenebrium scale — or a camp — to finish this."
                if not home_ready
                else "Enough metal in the blood. Take the wilds. This is the Ashwalker win."
            )
            choices = [
                {
                    "id": "c_home_clear",
                    "label": "Clear the Rock Jungle" if home_ready else "Probe the jungle wilds",
                    "blurb": clear_blurb if not home_cleared else "Home holds. Walk the shelves. Keep the wilds honest.",
                    "kind": "deploy",
                    "effect": {
                        "mapId": HOME_MAP_ID,
                        "contractKind": "hive_clear_or_bypass",
                        "preferredCaptureZoneId": "TRJ_C_SPILLWAY",
                        "deployAces": deploy_aces,
                        "sessionMode": "same_map",
                        "against": "wild",
                        "homeClearAttempt": home_ready and not home_cleared,
                    },
                },
            ]
        else:
            primary_label = (
                f"Press the line on {focus_name}"
                if session_mode == "same_map" and home
                else f"Raid {focus_name}"
            )
            choices = [
                {
                    "id": f"c_raid_{focus}",
                    "label": primary_label,
                    "blurb": "Your aces. Their ground. One pocket to claim.",
                    "kind": "deploy",
                    "effect": {
                        "mapId": focus,
                        "contractKind": "eco_raid" if focus == "greenest_fields" else "seize_lane",
                        "edgeId": None,
                        "deployAces": deploy_aces,
                        "sessionMode": session_mode,
                        "against": "cortex" if focus == "eye_of_horus" else "armada",
                    },
                },
            ]

    # Journey A — found / hold the Rock Jungle base (viable first pick, not "later").
    # Eco, raptor defence, constructors if Tnb wasn't spent on heroes.
    already_home_deploy = any(
        c.get("kind") == "deploy"
        and str((c.get("effect") or {}).get("mapId") or "") == HOME_MAP_ID
        for c in choices
    )
    if not home_cleared and not already_home_deploy:
        choices.append(
            {
                "id": "c_home_probe" if fresh_opening or not home_ready else "c_home_clear",
                "label": (
                    "Found the Rock Jungle camp"
                    if fresh_opening or camp_level <= 0
                    else ("Clear the Rock Jungle" if home_ready else "Hold the jungle shelf")
                ),
                "blurb": (
                    "Start the new Ashwalker base: plant eco, dig in against raptor pests, "
                    "and maybe mint a small exfil force. Spend leftover Tnb on constructors "
                    "at the broker if you did not seat expensive heroes."
                    if fresh_opening or camp_level <= 0
                    else (
                        "The lagoon maze still breeds. You need Tenebrium scale — or a camp — to finish this."
                        if not home_ready
                        else "Enough metal in the blood. Take the wilds. This is the Ashwalker win."
                    )
                ),
                "kind": "deploy",
                "effect": {
                    "mapId": HOME_MAP_ID,
                    # Founding / dig-in uses fortify (DV-only = secured).
                    # Full hive clear only when the camp exists and the player is ready.
                    "contractKind": (
                        "hive_clear_or_bypass"
                        if (camp_level >= 1 and home_ready and not home_cleared and not fresh_opening)
                        else "fortify_zone"
                    ),
                    "preferredCaptureZoneId": (
                        "TRJ_C_SPILLWAY"
                        if (camp_level >= 1 and home_ready and not home_cleared and not fresh_opening)
                        else "TRJ_NW_GATE"
                    ),
                    "preferredDeployZoneId": "TRJ_NW_OUTER_MUSTER",
                    "preferredExtractionZoneId": "TRJ_NW_OUTER_MUSTER",
                    "deployAces": deploy_aces,
                    "sessionMode": "same_map",
                    "against": "wild",
                    "homeClearAttempt": bool(
                        camp_level >= 1 and home_ready and not home_cleared and not fresh_opening
                    ),
                    "journey": "home_founding",
                },
            }
        )
    elif already_home_deploy:
        # Retitle the existing home deploy so founding fiction sticks.
        for c in choices:
            if c.get("kind") == "deploy" and str((c.get("effect") or {}).get("mapId") or "") == HOME_MAP_ID:
                if fresh_opening or camp_level <= 0:
                    c["label"] = "Found the Rock Jungle camp"
                    c["blurb"] = (
                        "Start the new Ashwalker base: plant eco, dig in against raptor pests, "
                        "and maybe mint a small exfil force. Spend leftover Tnb on constructors "
                        "at the broker if you did not seat expensive heroes."
                    )
                effect = dict(c.get("effect") or {})
                effect["journey"] = "home_founding"
                # Upgrade stale hive-march home probes into fortify dig-ins.
                if camp_level <= 0 or fresh_opening:
                    effect["contractKind"] = "fortify_zone"
                    effect.setdefault("preferredCaptureZoneId", "TRJ_NW_GATE")
                    effect.setdefault("preferredDeployZoneId", "TRJ_NW_OUTER_MUSTER")
                    effect.setdefault("preferredExtractionZoneId", "TRJ_NW_OUTER_MUSTER")
                    effect["homeClearAttempt"] = False
                c["effect"] = effect
                break

    # Home camp raise lives on the left-bar camp overlay (not main journeys).

    # Journey B — raid abroad for Tnb (skip if opening already seats that map).
    already_raid_maps = {
        str((c.get("effect") or {}).get("mapId") or "")
        for c in choices
        if c.get("kind") == "deploy"
    }
    spent = state.get("spentTheaters") if isinstance(state.get("spentTheaters"), dict) else {}
    last_sortie = str(state.get("lastSortieMapId") or "")
    # Outflow when sitting on / returning from a spent raid theater (esp. Greenest).
    # World spine: GF → Eye → Koom → Tabula → Bastion/Jungle. Hub PLAY has no
    # Mode B Reload host, so these doors are the real cross-map flow.
    need_outflow = (
        focus == "greenest_fields"
        or last_sortie == "greenest_fields"
        or "greenest_fields" in spent
        or focus == HOME_MAP_ID
        or home == HOME_MAP_ID
    )
    if need_outflow:
        raid_name = next(
            (r["displayName"] for r in regions if r["mapId"] == raid_map), raid_map
        )
        gf_spent = "greenest_fields" in spent or last_sortie == "greenest_fields"
        # Never re-offer a spent raid theater as the Tnb door.
        skip_raid = (
            raid_map in already_raid_maps
            or raid_map in spent
            or (gf_spent and raid_map == "greenest_fields")
        )
        if not skip_raid:
            choices.append(
                {
                    "id": f"c_raid_tnb_{raid_map}",
                    "label": f"Raid {raid_name} for Tenebrium",
                    "blurb": (
                        "Jump the Fields on the way: crack Armada decoy farms for Tnb, "
                        "optionally plant a presence, then haul loot home to fund the jungle camp."
                    ),
                    "kind": "deploy",
                    "effect": {
                        "mapId": raid_map,
                        "contractKind": "eco_raid",
                        "deployAces": deploy_aces,
                        "sessionMode": "map_travel",
                        "against": "armada",
                        "journey": "tnb_raid",
                    },
                }
            )
        if crater and crater not in already_raid_maps:
            choices.append(
                {
                    "id": "c_raid_crater",
                    "label": (
                        "Leave the Fields — strike the Horus crater"
                        if (focus == "greenest_fields" or gf_spent)
                        else "Strike the Horus crater"
                    ),
                    "blurb": (
                        "Greenest is spent. Take the corridor into the glassed Eye — "
                        "Cortex still smiles at customers until you glass their gear."
                        if (focus == "greenest_fields" or gf_spent)
                        else "Cortex still smiles at customers — until you glass their gear."
                    ),
                    "kind": "deploy",
                    "effect": {
                        "mapId": "eye_of_horus",
                        "contractKind": "destroy_key_structure",
                        "deployAces": deploy_aces,
                        "sessionMode": "map_travel",
                        "against": "cortex",
                        "journey": "spine_outflow",
                    },
                }
            )
        # Explicit home return when focus/last sortie is a raid theater.
        if focus != HOME_MAP_ID and HOME_MAP_ID not in already_raid_maps:
            choices.append(
                {
                    "id": "c_return_home_shelf",
                    "label": "Return to the Rock Jungle shelf",
                    "blurb": (
                        "Bank the Fields. Dig the Ashwalker camp back on limestone — "
                        "raptors, eco, and a pad you own."
                    ),
                    "kind": "deploy",
                    "effect": {
                        "mapId": HOME_MAP_ID,
                        "contractKind": "fortify_zone",
                        "preferredCaptureZoneId": "TRJ_NW_GATE",
                        "preferredDeployZoneId": "TRJ_NW_OUTER_MUSTER",
                        "preferredExtractionZoneId": "TRJ_NW_OUTER_MUSTER",
                        "deployAces": deploy_aces,
                        "sessionMode": "map_travel",
                        "against": "wild",
                        "journey": "home_founding",
                    },
                }
            )

    # After the opener, the doors are the collapse. The hardcoded Jungle
    # pockets, Greenest raid, and Horus strike are not the campaign.
    wet_voice = None
    if not fresh_opening:
        wet_choices, wet_voice = _wet_reach_choices(state, deploy_aces)
        if wet_choices:
            choices = wet_choices

    # Camp / broker / hearth / bay are left-bar or right-tab surfaces —
    # main journeys stay deploy-only (mission pick).

    home_name = next(
        (r["displayName"] for r in regions if r["mapId"] == home), "Rock Jungle"
    )
    true_home = (camp.get("mapId") or HOME_MAP_ID)
    true_home_name = next(
        (r["displayName"] for r in regions if r["mapId"] == true_home), "Rock Jungle"
    )
    chars = state.get("characters") or {}
    dead_names = [
        str((chars[k] or {}).get("name") or k)
        for k in chars
        if isinstance(chars.get(k), dict) and str(chars[k].get("status") or "") == "dead"
    ]
    dead_hint = ""
    if dead_names:
        shown = ", ".join(dead_names[:2])
        more = f" +{len(dead_names) - 2}" if len(dead_names) > 2 else ""
        dead_hint = f" We already lost {shown}{more}."

    if fresh_opening:
        ketha_line = (
            "Two roads from the ash: found our new base in the Rock Jungle "
            "(eco, raptor defence, leftover Tnb on constructors), "
            "or jump Greenest Fields first — raid decoy farms for Tenebrium, "
            "optionally plant a presence, then haul it home to build."
        )
    elif home_cleared:
        ketha_line = (
            f"The Rock Jungle is ours. The shelves hold. "
            f"Raid if you must — but home no longer begs."
        )
    elif mission_n <= 1:
        ketha_line = (
            f"We are founding {home_name}. "
            f"Raid Greenest Fields for Tenebrium when the camp needs metal in the blood, "
            f"or dig in at home against the wilds."
        )
    elif focus == true_home or focus == HOME_MAP_ID:
        ketha_line = (
            f"Still under the spires. Camp L{camp_level}. Tnb {tnb}. "
            f"{'Scale enough — take the maze.' if home_ready else 'Raid. Print. Build the camp. Then we clear.'}"
        )
    elif camp_level <= 0 and tnb < 6:
        # Hot raid fantasy: grab Tnb, extract, haul loot home, raise the shelf.
        ketha_line = (
            f"Mission {mission_n} on {focus_name} is hot — do not settle here."
            f"{dead_hint} "
            f"Crack decoy farms for Tenebrium, hit extract, haul the loot to "
            f"{true_home_name}. Camp is still L{camp_level}; we build with what we bring back."
        )
    else:
        ketha_line = (
            f"Mission {mission_n} off home ground. {focus_name} bleeds metal."
            f"{dead_hint} "
            f"Pocket the Tnb, extract clean, bring it back to {true_home_name}."
        )
    if null_rep >= BAY_THRESHOLD and mission_n > 1:
        ketha_line += " They still say your name in the bay."

    # World graph G pressure (Drop will collapse these axes on homecoming).
    try:
        from graph_collapse_v1 import pressure_brief  # type: ignore

        pressure = pressure_brief(state.get("graph") or {})
    except Exception:
        pressure = ""
    if wet_voice:
        ketha_line = wet_voice
    if pressure and mission_n > 1:
        ketha_line += f" World reads: {pressure}."

    # Theater should show the recommended sortie map, not only home ground.
    # Home stays on sessionHomeMap / badges; regionHint drives the briefing table.
    recommended_map = None
    for c in choices:
        if c.get("recommended") and c.get("kind") == "deploy":
            recommended_map = str((c.get("effect") or {}).get("mapId") or "") or None
            break
    if not recommended_map and fresh_opening:
        recommended_map = "greenest_fields"
    theater_hint = recommended_map or focus

    return {
        "id": f"hub_open_m{mission_n}",
        "kind": "choice",
        "speaker": "ketha",
        "text": ketha_line,
        "regionHint": theater_hint,
        "sortieMapId": recommended_map or theater_hint,
        "sessionHomeMap": home or focus,
        "graphPressure": pressure or None,
        "choices": choices,
    }


def project_campaign_rho(state: dict, mission_n: int) -> dict:
    """Bridge campaign graph qubits → CampaignRho-style axes for the density room.

    Signed poles match tools/quantum_bar_ai/campaign_manifold.CampaignRho.
    """
    g = state.get("graph") or {}
    q0 = float(g.get("q0_armada_cortex") or 0.5)
    q2 = float(g.get("q2_void_structure") or 0.15)
    q6 = float(g.get("q6_contested") or 0.5)
    q6i = float(g.get("q6_independent") or 0.24)
    q7 = float(g.get("q7_resource_scarcity") or 0.5)
    path_a = float(g.get("pathSignalA") or 0.33)
    path_b = float(g.get("pathSignalB") or 0.34)
    path_c = float(g.get("pathSignalC") or 0.33)
    # Signed [-1, +1] from classical [0,1] qubits where applicable
    arm_cor = max(-1.0, min(1.0, 2.0 * q0 - 1.0))
    void_struct = max(-1.0, min(1.0, 2.0 * q2 - 1.0))
    zone_control = max(-1.0, min(1.0, 2.0 * q6 - 1.0))
    tenebrium = max(-1.0, min(1.0, 2.0 * q7 - 1.0))  # high scarcity → +pole scarce
    # invert scarcity reading: high q7 = scarce = negative tenebrium wealth
    tenebrium = -abs(tenebrium) if q7 >= 0.5 else (1.0 - q7) * 0.4
    phi = max(0.0, min(1.0, (max(1, mission_n) - 1) / 14.0))
    # Classical diag stand-in (2 bins per axis, as CampaignRho.packed_diag)
    axes = {
        "arm_cor": round(arm_cor, 4),
        "schism": round(max(-1.0, min(1.0, 2.0 * q6i - 1.0)), 4),
        "void_struct": round(void_struct, 4),
        "zone_control": round(zone_control, 4),
        "tenebrium": round(tenebrium, 4),
        "phi": round(phi, 4),
        "path_a": round(path_a, 4),
        "path_b": round(path_b, 4),
        "path_c": round(path_c, 4),
    }
    packed: list[float] = []
    for key in ("arm_cor", "schism", "void_struct", "zone_control", "tenebrium"):
        v = max(-1.0, min(1.0, float(axes[key])))
        p1 = (v + 1.0) / 2.0
        packed.extend([round(1.0 - p1, 4), round(p1, 4)])
    purity = round(max(0.15, min(0.95, 1.0 - 0.35 * q6 - 0.15 * q2)), 4)
    entropy = round(max(0.05, min(1.2, 0.4 + 0.5 * q6 + 0.2 * q2)), 4)
    return {
        "schemaVersion": "verdance-campaign-rho/1.0",
        "source": "graph_qubits",
        "axes": axes,
        "packedDiag": packed,
        "purity": purity,
        "entropy": entropy,
        "width": round(max(0.15, min(0.95, 0.2 + 0.55 * q6)), 4),
        "sessionHomeMap": state.get("sessionHomeMap"),
        "missionNumber": mission_n,
    }


def commerce_arc_number(mission_n: int) -> int:
    n = max(1, int(mission_n or 1))
    if n <= 5:
        return 1
    if n <= 10:
        return 2
    return 3


def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        return {}
    return load_json(CATALOG_PATH)


def listing_available_ui(
    listing_id: str,
    listing: dict,
    state: dict,
    commerce: dict,
    mission_n: int,
) -> tuple[bool, str]:
    """Mirror story-engine shelf gates for hub paint (read-only)."""
    if not listing:
        return False, "unknown listing"
    owned = commerce.get("owned") or {}
    upgrades = commerce.get("upgrades") or {}
    kind = str(listing.get("kind") or "")
    if kind == "printer_upgrade" and listing_id in upgrades:
        return False, "upgrade already installed"
    if kind in ("unit_printer", "loan_package") and listing_id in owned:
        return False, "already owned"
    if listing.get("starterOwned") and listing.get("loan") and listing_id in owned:
        return False, "already owned (starter loan)"
    req = listing.get("requires")
    if req and req not in owned:
        return False, f"requires {req}"
    arc_min = int(listing.get("arcMin") or 1)
    if commerce_arc_number(mission_n) < arc_min:
        return False, f"arc {arc_min}+ only"
    rep = state.get("reputation") or {}
    for faction, need in (listing.get("repMin") or {}).items():
        have = float(rep.get(faction, 0) or 0)
        if have < float(need):
            return False, f"need {faction} rep ≥ {need} (have {have:.0f})"
    tcost = int(listing.get("tenebriumCost") or 0)
    if listing.get("builds") and tcost < 1:
        tcost = 1
    if listing.get("metalCostK") is not None:
        mcost = int(listing.get("metalCostK") or 0)
    else:
        mcost = int(listing.get("creditCost") or 0)
    if int(commerce.get("tenebrium") or 0) < tcost:
        return False, f"need {tcost} Tenebrium (have {commerce.get('tenebrium', 0)})"
    metal_have = int(commerce.get("metalK") if "metalK" in commerce else commerce.get("credits") or 0)
    if metal_have < mcost:
        return False, f"need {mcost}×1km$ metal (have {metal_have})"
    return True, "ok"


def build_commerce_surface(state: dict, mission_n: int) -> dict:
    """Project catalog + campaign bag into hub_state.commerce for the shop UI."""
    catalog = load_catalog()
    bag = dict(state.get("commerce") or {})
    metal_meta = catalog.get("metal") or catalog.get("credits") or {}
    resource = catalog.get("resource") or {}
    starting = resource.get("startingBalance") or {}
    tenebrium = int(bag.get("tenebrium") if "tenebrium" in bag else 0)
    if "metalK" in bag:
        metal_k = int(bag.get("metalK") or 0)
    elif "credits" in bag:
        metal_k = int(bag.get("credits") or 0) // 10
    else:
        metal_k = int(metal_meta.get("startingBalanceK") or 0)
    owned = dict(bag.get("owned") or {})
    upgrades = dict(bag.get("upgrades") or {})
    # Seed starter-owned listings into the surface if bag is empty of them
    for lid, listing in (catalog.get("listings") or {}).items():
        if not isinstance(listing, dict):
            continue
        if listing.get("starterOwned") and lid not in owned:
            owned[lid] = {
                "qty": 1,
                "loan": bool(listing.get("loan")),
                "unitDef": listing.get("unitDef"),
                "loanCount": int(listing.get("count") or 0) if listing.get("loan") else None,
                "kind": listing.get("kind") or "purchase_package",
                "source": "starter",
            }

    dest_map = str(
        state.get("plannedMapId")
        or state.get("sessionHomeMap")
        or "greenest_fields"
    )
    stamp = ROOT / "outbox" / "hub_deploy_stamp.latest.json"
    if stamp.exists():
        try:
            st = json.loads(stamp.read_text(encoding="utf-8-sig"))
            if isinstance(st, dict):
                dest_map = str(
                    st.get("mapId")
                    or st.get("deploymentMapId")
                    or (st.get("plan") or {}).get("mapId")
                    or dest_map
                )
        except Exception:
            pass

    commerce_view = {
        "tenebrium": tenebrium,
        "metalK": metal_k,
        "owned": owned,
        "upgrades": upgrades,
        "ledger": list(bag.get("ledger") or [])[-12:],
        "pendingDeliveries": list(bag.get("pendingDeliveries") or []),
    }

    shop: list[dict] = []
    for lid, listing in (catalog.get("listings") or {}).items():
        if not isinstance(listing, dict):
            continue
        ok, reason = listing_available_ui(lid, listing, state, commerce_view, mission_n)
        tcost = int(listing.get("tenebriumCost") or 0)
        if listing.get("builds") and tcost < 1:
            tcost = 1
        eta = delivery_eta(
            listing=listing,
            listing_id=lid,
            dest_map_id=dest_map,
            workspace=ROOT,
        )
        shop.append(
            {
                "id": lid,
                "label": listing.get("label") or lid,
                "blurb": listing.get("blurb") or "",
                "kind": listing.get("kind"),
                "unitDef": listing.get("unitDef") or listing.get("factoryDef") or listing.get("product"),
                "count": listing.get("count") or listing.get("seedCount"),
                "tenebriumCost": tcost,
                "metalCostK": int(
                    listing.get("metalCostK")
                    if listing.get("metalCostK") is not None
                    else listing.get("creditCost")
                    or 0
                ),
                "builds": bool(listing.get("builds")),
                "loan": bool(listing.get("loan")),
                "starterOwned": bool(listing.get("starterOwned")),
                "shelf": listing.get("shelf") or (
                    "armada" if "armada" in list(listing.get("tags") or []) else
                    "nullmercs" if ("nullmercs" in list(listing.get("tags") or []) or listing.get("kind") == "hero_contract") else
                    "cortex"
                ),
                "available": ok,
                "blockedReason": None if ok else reason,
                "owned": lid in owned or lid in upgrades,
                "ownedQty": int((owned.get(lid) or {}).get("qty") or (1 if lid in owned else 0)),
                "repMin": listing.get("repMin") or {},
                "arcMin": int(listing.get("arcMin") or 1),
                "tags": list(listing.get("tags") or []),
                "requires": listing.get("requires"),
                "delivery": {
                    "mode": eta.get("mode"),
                    "deferred": bool(eta.get("deferred")),
                    "sourceLabel": eta.get("sourceLabel"),
                    "etaSeconds": eta.get("etaSeconds"),
                    "etaText": eta.get("etaText"),
                    "summary": eta.get("summary"),
                    "routeLabels": eta.get("routeLabels"),
                },
            }
        )

    deploy_kit: list[dict] = []
    inbound: list[dict] = []
    listings = catalog.get("listings") or {}
    for lid, rec in owned.items():
        if not isinstance(rec, dict):
            continue
        listing = listings.get(lid) or {}
        kind = str(rec.get("kind") or listing.get("kind") or "purchase_package")
        unit_def = rec.get("unitDef") or listing.get("unitDef")
        qty = int(rec.get("qty") or 1)
        count = int(rec.get("loanCount") or rec.get("count") or listing.get("count") or 0)
        if kind == "purchase_package":
            count = int(listing.get("count") or count or 0) * max(1, qty)
        eta = delivery_eta(
            listing=listing,
            listing_id=lid,
            dest_map_id=dest_map,
            workspace=ROOT,
        )
        if unit_def and count > 0:
            row = {
                "listingId": lid,
                "kind": kind,
                "unitDef": unit_def,
                "count": count,
                "loan": bool(rec.get("loan") or listing.get("loan")),
                "label": listing.get("label") or lid,
                "delivery": {
                    "mode": eta.get("mode"),
                    "deferred": bool(eta.get("deferred")),
                    "etaText": eta.get("etaText"),
                    "summary": eta.get("summary"),
                    "sourceLabel": eta.get("sourceLabel"),
                },
            }
            if eta.get("deferred") and kind == "purchase_package":
                inbound.append(row)
            else:
                deploy_kit.append(row)
        if kind == "unit_printer" or listing.get("factoryDef"):
            deploy_kit.append(
                {
                    "listingId": lid,
                    "kind": "unit_printer",
                    "factoryDef": listing.get("factoryDef") or rec.get("factoryDef"),
                    "product": listing.get("product") or rec.get("product"),
                    "seedCount": int(listing.get("seedCount") or rec.get("seedCount") or 0),
                    "label": listing.get("label") or lid,
                }
            )
    for uid, urec in upgrades.items():
        listing = listings.get(uid) or {}
        deploy_kit.append(
            {
                "listingId": uid,
                "kind": "printer_upgrade",
                "nanoDef": (urec or {}).get("nanoDef") or listing.get("nanoDef"),
                "nanoCount": (urec or {}).get("nanoCount") or listing.get("nanoCount"),
                "label": listing.get("label") or uid,
            }
        )

    return {
        "schemaVersion": "verdance-hub-commerce/1.0",
        "resource": {
            "id": resource.get("id") or "tenebrium",
            "label": resource.get("label") or "Tenebrium",
            "shortLabel": resource.get("shortLabel") or "Tnb",
            "lore": resource.get("lore") or "",
            "storage": "infinite",
        },
        "metal": {
            "id": metal_meta.get("id") or "campaign_metal",
            "label": metal_meta.get("label") or "Metal",
            "shortLabel": metal_meta.get("shortLabel") or "1km$",
            "unitMetal": int(metal_meta.get("unitMetal") or 1000),
        },
        "tenebrium": tenebrium,
        "metalK": metal_k,
        "armyBudget": int(bag.get("armyBudget") or 0),
        "owned": owned,
        "upgrades": upgrades,
        "shop": shop,
        "deployKit": deploy_kit,
        "inbound": inbound,
        "pendingDeliveries": commerce_view["pendingDeliveries"],
        "destMapId": dest_map,
        "ledger": commerce_view["ledger"],
        "notes": (
            "Tenebrium is black-hole metal (scarce since the Generic Disaster). "
            "Campaign metal banks as floor(endMetal/1000) 1km$ units. "
            "Combat packs ship via Eye of Horus / All That Simmers / pawn launcher with field ETAs."
        ),
        "catalogSchema": catalog.get("schemaVersion"),
        "armadaCrisis": (resource.get("armadaCrisis") or {}).get("active", True),
        # authored lore, our side only — another faction's purse is its own business
        "startingBalanceHint": {k: v for k, v in dict(starting).items() if k in ("ashwalkers", "nullmercs")},
    }


def build_faction_banks(state: dict, commerce: dict) -> dict:
    """The company's own purse only. Another faction's Tenebrium bank is that faction's mind;
    the hub never carries it (pass 8B)."""
    tnb = int(commerce.get("tenebrium") or 0)
    return {"nullmercs": tnb, "ashwalkers": tnb}


def build_hub(state: dict, war: dict) -> dict:
    repair_session_home(state)
    rep = dict(state.get("reputation") or {})
    null_rep = float(rep.get("nullmercs") or 0)
    aces = build_aces(state)
    regions = build_regions(war)
    # Soft-evaluate home clear readiness before open-node choices.
    home_eval: dict = {}
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from verdance_story_engine_v1 import evaluate_home_clear  # type: ignore

        home_eval = evaluate_home_clear(state) or {}
    except Exception:  # noqa: BLE001
        home_eval = {}
    node = build_open_node(state, regions, aces, rep)
    # Soft unlock: chips / Theaters tab only light maps that appear in journeys
    # (plus home / recommended sortie). Scales as more deploy choices are emitted.
    open_maps: set[str] = set()
    for ch in node.get("choices") or []:
        if not isinstance(ch, dict) or ch.get("kind") != "deploy":
            continue
        mid = str((ch.get("effect") or {}).get("mapId") or "").strip()
        if mid:
            open_maps.add(mid)
    for key in ("sessionHomeMap",):
        v = state.get(key)
        if v:
            open_maps.add(str(v))
    for key in ("sortieMapId", "regionHint", "sessionHomeMap"):
        v = (node or {}).get(key)
        if v:
            open_maps.add(str(v))
    camp_map = ((state.get("homeCamp") or {}).get("mapId")) or HOME_MAP_ID
    open_maps.add(str(camp_map))
    if not open_maps:
        open_maps.update({"greenest_fields", HOME_MAP_ID})
    for r in regions:
        r["selectable"] = str(r.get("mapId") or "") in open_maps
    companion = state.get("companion") or {}
    mission_n = int(state.get("missionNumber") or war.get("missionNumber") or 1)
    fresh_opening = mission_n == 1 and not state.get("history") and not state.get("lastResult")
    arc = arc_from_mission(mission_n)
    graph = dict(state.get("graph") or {})
    # Ensure canonical qubits for the density-matrix room (framework defaults).
    graph.setdefault("q0_armada_cortex", 0.5)
    graph.setdefault("q2_void_structure", 0.15)
    graph.setdefault("q6_contested", 0.85)
    graph.setdefault("q6_independent", 0.24)
    graph.setdefault("q7_resource_scarcity", 0.98)
    graph.setdefault("pathSignalA", 0.0)
    graph.setdefault("pathSignalB", 0.1)
    graph.setdefault("pathSignalC", 0.0)
    try:
        from graph_collapse_v1 import pressure_brief  # type: ignore

        graph_pressure = pressure_brief(graph)
    except Exception:
        graph_pressure = (
            f"contested={float(graph.get('q6_contested') or 0):.2f} · "
            f"scarcity={float(graph.get('q7_resource_scarcity') or 0):.2f}"
        )
    spectral = state.get("lastSpectral") or {
        "dominantEigenvalue": round(1.0 + float(graph.get("q6_contested") or 0) * 0.3, 4),
        "energy": round(
            sum(float(graph.get(k) or 0) for k in (
                "q0_armada_cortex", "q2_void_structure", "q6_contested",
                "q6_independent", "q7_resource_scarcity",
            )),
            3,
        ),
        "participation": round(0.55 + float(graph.get("q6_independent") or 0) * 0.3, 4),
        "spread": round(float(graph.get("q6_contested") or 0.5) * 0.6, 4),
        "factionWeights": {
            "ashwalkers": 0.2,
            "armada": 0.35,
            "nullmercs": 0.2,
            "neutral": 0.25,
        },
    }

    commerce = build_commerce_surface(state, mission_n)
    faction_banks = build_faction_banks(state, commerce)
    session_mode = state.get("sessionMode") or "same_map"
    occupation_model = state.get("occupationModel") or "living_shell"
    session_home = state.get("sessionHomeMap") or pick_focus_region(regions, state)
    campaign_rho = project_campaign_rho(state, mission_n)

    company_surface: dict = {}
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from company_v1 import ensure_company, hub_company_surface  # type: ignore
        try:
            from verdance_story_engine_v1 import ensure_roster  # type: ignore

            ensure_roster(state)
        except Exception:  # noqa: BLE001
            pass

        ensure_company(state, ROOT)
        company_surface = hub_company_surface(state, ROOT)
    except Exception:  # noqa: BLE001
        company_surface = {
            "sealed": bool((state.get("company") or {}).get("sealed")),
            "preambleNeeded": not bool((state.get("company") or {}).get("sealed")),
            "core": [],
            "band": list((state.get("company") or {}).get("band") or []),
            "joinedLater": list((state.get("company") or {}).get("joinedLater") or []),
            "seatCap": 3,
            "pool": [],
            "wild": [],
        }

    # Hub capture: claimed nodes + open contracts (clear + hold under regrow).
    capture_contracts: list = []
    claim_surface: dict = {
        "occupationModel": occupation_model,
        "captureMode": "clear_hold_shell",
        "freeTnbMint": False,
        "nodes": [],
        "count": 0,
    }
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import capture_node_claims as cnc  # type: ignore

        capture_contracts = cnc.hub_capture_contracts(ROOT, state, limit=6)
        claim_surface = cnc.hub_claim_surface(state)
    except Exception:  # noqa: BLE001
        capture_contracts = []

    focus_map = (node.get("regionHint") if isinstance(node, dict) else None) or session_home
    theater = build_theater(state, focus_map, capture_contracts)
    home_camp = dict(state.get("homeCamp") or {"level": 0, "mapId": HOME_MAP_ID, "label": "Jungle shelf camp"})
    flags = dict(state.get("flags") or {})
    if home_eval:
        flags["homeClearReady"] = home_eval.get("homeClearReady")
        flags["homeCleared"] = home_eval.get("homeCleared")
    # Camp overlay surface (left bar) — raise is hub spend, not a main journey.
    camp_level = int(home_camp.get("level") or 0)
    home_cleared = bool(flags.get("homeCleared") or (home_eval or {}).get("homeCleared"))
    tnb_bag = int(commerce.get("tenebrium") or 0)
    metal_k_bag = int(commerce.get("metalK") or 0)
    can_raise = (not home_cleared) and tnb_bag >= 1 and metal_k_bag >= 1
    home_camp["canRaise"] = can_raise
    home_camp["raiseTnbCost"] = 1
    home_camp["raiseMetalCostK"] = 1
    home_camp["cleared"] = home_cleared
    home_camp["clearReady"] = bool(flags.get("homeClearReady") or (home_eval or {}).get("homeClearReady"))
    home_camp["level"] = camp_level
    try:
        from verdance_story_engine_v1 import commander_is_unlocked  # type: ignore

        walker_on = commander_is_unlocked(state)
    except Exception:  # noqa: BLE001
        commander = ((state.get("roster") or {}).get("commander") or {})
        walker_on = isinstance(commander, dict) and commander.get("unlocked") is True
    home_camp["commanderUnlocked"] = walker_on
    home_camp["commanderLine"] = (
        "The command walker walks with you."
        if walker_on
        else "The command walker is scrap. The company is the line until the story rebuilds it."
    )

    from narrative_v1 import project as narrative_project
    return {
        "schemaVersion": "verdance-hub-state/1.0",
        "narrative": narrative_project(state, node.get("choices") or [], ROOT),
        "campaignId": state.get("campaignId") or war.get("campaignId") or "verdance_ashes",
        "missionNumber": mission_n,
        "arc": arc,
        "pathSignal": state.get("pathSignal") or "B",
        "seed": state.get("seed") or 28,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tagline": (
            "Found the Rock Jungle camp — or raid Greenest Fields for Tenebrium to fund it."
            if fresh_opening
            else "Home is the Rock Jungle. Raid the Fields for Tenebrium. Clear the wilds when you can scale."
        ),
        "sessionMode": session_mode,
        "sessionHomeMap": session_home,
        "theater": theater,
        # pass six: the interstitial faces the board and debrief draw from
        "belief": (hub_belief_v1.belief_surface(ROOT, state, None) if hub_belief_v1 else {}),
        "camp": (hub_belief_v1.camp_surface(state) if hub_belief_v1 else {}),
        "exposure": (hub_belief_v1.exposure_surface(ROOT) if hub_belief_v1 else {}),
        "homeCamp": home_camp,
        "flags": flags,
        "homeEval": home_eval if isinstance(home_eval, dict) else {},
        "occupationModel": occupation_model,
        "captureMode": "clear_hold_shell",
        "freeTnbMint": False,
        "captureContracts": capture_contracts,
        "claimedNodes": claim_surface,
        "nodeClaims": state.get("nodeClaims") or state.get("claimedNodes") or {},
        "factionBanks": faction_banks,
        "tenebrium": commerce.get("tenebrium", 0),
        "graph": graph,
        "graphPressure": graph_pressure,
        "spectral": spectral,
        "campaignRho": campaign_rho,
        "reputation": rep,
        "companion": {
            "id": companion.get("id") or "ketha",
            "name": companion.get("name") or "Ketha",
            "morale": companion.get("morale"),
            "loyalty": companion.get("loyalty"),
            "stress": companion.get("stress"),
        },
        "bay": {
            "unlocked": null_rep >= BAY_THRESHOLD,
            "threshold": BAY_THRESHOLD,
            "label": "Null Mercs mod bay",
            "hint": (
                "Bay open — loadouts land in G8."
                if null_rep >= BAY_THRESHOLD
                else f"Bay locked — Null Mercs rep {null_rep:.0f}/{BAY_THRESHOLD}."
            ),
        },
        "commerce": commerce,
        "aces": aces,
        "supportWeb": _support_web_surface(aces, company_surface, state),
        "company": company_surface,
        "regions": regions,
        "node": node,
        "lastResult": _with_manifest(_load_last_hub_result(), state),
        "history": [],
        "flags": {
            "mode": "hub",
            # True until HTML is opened via hub_host (runtime clears this).
            "deployStub": True,
            "hubHostHint": "PLAY.bat",
            "source": "build_hub_state_v1",
            "shopSurface": True,
            "deployCompileLaunch": True,
            "resultPull": True,
            "densityMatrix": True,
            "campaignRho": True,
            "modeASameMap": session_mode == "same_map",
            "captureNodeClaims": True,
            "noFreeTnbMint": True,
            "livePurchase": True,
            "companyPreamble": True,
            "companySealed": bool(company_surface.get("sealed")),
            "homeClearReady": flags.get("homeClearReady"),
            "homeCleared": flags.get("homeCleared"),
        },
    }


def _with_manifest(payload, state):
    """The last bead's manifest rides on the debrief (pass five): going / staying / destination."""
    try:
        m = hub_belief_v1.last_manifest(state) if hub_belief_v1 else None
    except Exception:  # noqa: BLE001
        m = None
    if not m:
        return payload
    out = dict(payload or {})
    out["manifest"] = m
    return out


def _load_last_hub_result():
    p = ROOT / "outbox" / "hub_result.latest.json"
    if not p.is_file():
        return None
    try:
        data = load_json(p)
        payload = data.get("lastResult") or data
        # Sortie-2 ghost guard: after a wipe, campaign_state is mission 1 with
        # empty history, but a leftover hub_result.latest.json can still paint
        # "sortie 2" chrome. Ignore stale result paint in that case.
        state_path = ROOT / "state" / "campaign_state.json"
        if state_path.is_file():
            try:
                state = load_json(state_path)
                mission_n = int(state.get("missionNumber") or 1)
                hist = state.get("history") or []
                if mission_n <= 1 and not hist:
                    return None
                painted = int(
                    (payload or {}).get("missionNumber")
                    or data.get("missionNumber")
                    or 0
                )
                # Result from a later mission must not override an earlier state.
                if painted and painted > mission_n:
                    return None
            except Exception:  # noqa: BLE001
                pass
        return payload
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    if not STATE_PATH.is_file():
        print(f"missing {STATE_PATH}", file=sys.stderr)
        return 1
    if not WAR_MAP_PATH.is_file():
        print(f"missing {WAR_MAP_PATH}", file=sys.stderr)
        return 1

    state = load_json(STATE_PATH)
    war = load_json(WAR_MAP_PATH)
    # Persist company scaffolding / authored roster so Drop gate + ace list match hub.
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from company_v1 import ensure_company  # type: ignore
        from verdance_story_engine_v1 import ensure_roster  # type: ignore

        snap = json.dumps(
            {
                "company": state.get("company"),
                "fieldPool": state.get("fieldPool"),
                "unlockPool": state.get("unlockPool"),
                "roster": state.get("roster"),
                "characters": state.get("characters"),
            },
            sort_keys=True,
        )
        ensure_roster(state)
        ensure_company(state, ROOT)
        snap2 = json.dumps(
            {
                "company": state.get("company"),
                "fieldPool": state.get("fieldPool"),
                "unlockPool": state.get("unlockPool"),
                "roster": state.get("roster"),
                "characters": state.get("characters"),
            },
            sort_keys=True,
        )
        if snap != snap2:
            STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            print(f"updated roster/company fields on {STATE_PATH}")
    except Exception as e:  # noqa: BLE001
        print(f"company/roster ensure skipped: {e}", file=sys.stderr)

    hub = build_hub(state, war)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(hub, indent=2) + "\n", encoding="utf-8")
    OUT_EMBED.write_text(
        "window.HUB_STATE = " + json.dumps(hub, indent=None) + ";\n",
        encoding="utf-8",
    )
    shop_n = len((hub.get("commerce") or {}).get("shop") or [])
    avail = sum(1 for s in ((hub.get("commerce") or {}).get("shop") or []) if s.get("available"))
    company = hub.get("company") or {}
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_EMBED}")
    print(
        f"aces={len(hub['aces'])} regions={len(hub['regions'])} "
        f"choices={len(hub['node']['choices'])} shop={shop_n} available={avail} "
        f"tnb={hub.get('tenebrium')} mode={hub.get('sessionMode')} "
        f"companySealed={bool(company.get('sealed'))} pool={len(company.get('pool') or [])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
