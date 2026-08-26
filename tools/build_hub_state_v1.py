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
            "deployable": (rh.get("status") or ch.get("status") or "active") == "active",
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


def build_regions(war: dict) -> list[dict]:
    regions = []
    for r in war.get("regions") or []:
        regions.append(
            {
                "mapId": r.get("mapId"),
                "displayName": r.get("displayName") or r.get("mapId"),
                "descriptor": r.get("descriptor") or "",
                "family": r.get("family") or "tempo",
                "control": r.get("control") or "contested",
                "dominantEnemy": r.get("dominantEnemy") or "armada",
                "threatBand": r.get("threatBand") or "light",
                "controlCounts": r.get("controlCounts") or {},
                "selectable": True,
            }
        )
    return regions


HOME_MAP_ID = "the_rock_jungle"


def pick_focus_region(regions: list[dict], state: dict | None = None) -> str:
    """Mode A: stay on session home map when set; default Ashwalker home = Rock Jungle."""
    st = state or {}
    session_mode = st.get("sessionMode") or "same_map"
    home = st.get("sessionHomeMap") or st.get("homeMapId") or HOME_MAP_ID
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
    for i, q in enumerate(cands[:limit]):
        if not isinstance(q, dict):
            continue
        map_id = q.get("mapId") or focus
        # Mode A: only same-map continues when session is locked
        if (state.get("sessionMode") or "same_map") == "same_map" and map_id != focus:
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
                    "preferredDeployZoneId": (q.get("fromZoneIds") or [None])[0]
                    if isinstance(q.get("fromZoneIds"), list)
                    else q.get("deploymentZoneId"),
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
    for zid, z in zm.items():
        if not isinstance(z, dict):
            continue
        abstract = z.get("abstract") or {}
        control = str(
            z.get("controllingFaction") or abstract.get("control") or "unknown"
        ).lower()
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
                "confidence": z.get("confidence") or "estimated",
                "openTarget": zid in open_ids,
                "claimed": claimed,
                "preferred": zid in open_ids or bool(abstract.get("preferredObjective")),
                "hazard": float(
                    z.get("hazardPressure") or abstract.get("hazardPressure") or 0
                ),
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

    # Prefer a raid theater (economy / crater) when sitting on home wilds.
    raid_map = "greenest_fields"
    for r in regions:
        if r["mapId"] != home and r.get("family") in ("economy", "tempo"):
            raid_map = r["mapId"]
            break
    crater = next((r["mapId"] for r in regions if r["mapId"] == "eye_of_horus"), None)

    deploy_aces = [a["id"] for a in aces if a.get("deployable")][:2]

    # Prefer same-map continues (quest candidates) as the primary battle picks.
    mode_a = _quest_continue_choices(state, focus, deploy_aces, limit=3)
    if mode_a:
        choices = []
        for ch in mode_a:
            effect = dict(ch.get("effect") or {})
            choices.append({**ch, "effect": effect})
    else:
        if focus == HOME_MAP_ID:
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
                        "preferredCaptureZoneId": "RJ_CENTRAL_LAGOON_MAZE",
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

    # Home camp build (hub spend — not a BAR freebuild).
    if not home_cleared:
        choices.append(
            {
                "id": "c_home_build",
                "label": f"Raise the jungle camp (L{camp_level} → L{camp_level + 1})",
                "blurb": (
                    f"Spend {1} Tnb + {25} scrap on the shelf. "
                    "Without Tenebrium you cannot scale build power at home."
                ),
                "kind": "home_build",
                "effect": {
                    "mapId": HOME_MAP_ID,
                    "tenebriumCost": 1,
                    "creditCost": 25,
                    "campLevel": camp_level,
                },
            }
        )

    # Raid abroad for Tnb when home is focus.
    if focus == HOME_MAP_ID or home == HOME_MAP_ID:
        raid_name = next(
            (r["displayName"] for r in regions if r["mapId"] == raid_map), raid_map
        )
        choices.append(
            {
                "id": f"c_raid_tnb_{raid_map}",
                "label": f"Raid {raid_name} for Tenebrium",
                "blurb": "Home stays hungry without Tnb. Hit their works, print, return.",
                "kind": "deploy",
                "effect": {
                    "mapId": raid_map,
                    "contractKind": "eco_raid",
                    "deployAces": deploy_aces,
                    "sessionMode": "map_travel",
                    "against": "armada",
                },
            }
        )
        if crater:
            choices.append(
                {
                    "id": "c_raid_crater",
                    "label": "Strike the Horus crater",
                    "blurb": "Cortex still smiles at customers — until you glass their gear.",
                    "kind": "deploy",
                    "effect": {
                        "mapId": "eye_of_horus",
                        "contractKind": "destroy_key_structure",
                        "deployAces": deploy_aces,
                        "sessionMode": "map_travel",
                        "against": "cortex",
                    },
                }
            )

    choices.extend(
        [
            {
                "id": "c_shop",
                "label": "See the broker",
                "blurb": "Merc loans, scrap, and the odd printer upgrade.",
                "kind": "shop",
                "effect": {"panel": "shop"},
            },
            {
                "id": "c_talk_ketha",
                "label": "Talk with Ketha",
                "blurb": "A quiet minute by the fire. Bonds hold better than armor.",
                "kind": "talk",
                "effect": {
                    "social": "vane_ketha_hearth",
                    "bondDelta": {"vane": {"ketha": 2}, "ketha": {"vane": 2}},
                },
            },
            {
                "id": "c_rest",
                "label": "Rest the company",
                "blurb": "Bandage the wounded. Let the stress bleed off.",
                "kind": "rest",
                "effect": {"healWounds": 1, "stressDelta": -5},
            },
        ]
    )

    if null_rep >= BAY_THRESHOLD:
        choices.append(
            {
                "id": "c_bay_locked",
                "label": "Null Mercs garage",
                "blurb": "Still welding. Come back when the contract deepens.",
                "kind": "bay",
                "effect": {"note": "The bay is locked for now — not open in this build."},
            }
        )

    home_name = next(
        (r["displayName"] for r in regions if r["mapId"] == home), "Rock Jungle"
    )
    if home_cleared:
        ketha_line = (
            f"The Rock Jungle is ours. The shelves hold. "
            f"Raid if you must — but home no longer begs."
        )
    elif mission_n <= 1:
        ketha_line = (
            f"Home is the limestone maze — {home_name}. "
            f"We cannot clear the wilds without Tenebrium. "
            f"Mark a wound on the map, or raid their fields to print."
        )
    elif focus == HOME_MAP_ID:
        ketha_line = (
            f"Still under the spires. Camp L{camp_level}. Tnb {tnb}. "
            f"{'Scale enough — take the maze.' if home_ready else 'Raid. Print. Build the camp. Then we clear.'}"
        )
    else:
        ketha_line = (
            f"Mission {mission_n} off home ground. {focus_name} bleeds metal. "
            f"Bring Tnb back to the jungle."
        )
    if null_rep >= BAY_THRESHOLD and mission_n > 1:
        ketha_line += " They still say your name in the bay."

    return {
        "id": f"hub_open_m{mission_n}",
        "kind": "choice",
        "speaker": "ketha",
        "text": ketha_line,
        "regionHint": focus,
        "sessionHomeMap": home or focus,
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
    if listing.get("starterOwned") and listing_id in owned:
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
    ccost = int(listing.get("creditCost") or 0)
    if int(commerce.get("tenebrium") or 0) < tcost:
        return False, f"need {tcost} Tenebrium (have {commerce.get('tenebrium', 0)})"
    if int(commerce.get("credits") or 0) < ccost:
        return False, f"need {ccost} scrap credits (have {commerce.get('credits', 0)})"
    return True, "ok"


def build_commerce_surface(state: dict, mission_n: int) -> dict:
    """Project catalog + campaign bag into hub_state.commerce for the shop UI."""
    catalog = load_catalog()
    bag = dict(state.get("commerce") or {})
    credits_meta = catalog.get("credits") or {}
    resource = catalog.get("resource") or {}
    starting = resource.get("startingBalance") or {}
    tenebrium = int(bag.get("tenebrium") if "tenebrium" in bag else 0)
    credits = int(
        bag.get("credits")
        if "credits" in bag
        else (credits_meta.get("startingBalance") or 40)
    )
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
                "loanCount": int(listing.get("count") or 0),
                "kind": listing.get("kind") or "loan_package",
                "source": "starter",
            }

    commerce_view = {
        "tenebrium": tenebrium,
        "credits": credits,
        "owned": owned,
        "upgrades": upgrades,
        "ledger": list(bag.get("ledger") or [])[-12:],
    }

    shop: list[dict] = []
    for lid, listing in (catalog.get("listings") or {}).items():
        if not isinstance(listing, dict):
            continue
        ok, reason = listing_available_ui(lid, listing, state, commerce_view, mission_n)
        tcost = int(listing.get("tenebriumCost") or 0)
        if listing.get("builds") and tcost < 1:
            tcost = 1
        shop.append(
            {
                "id": lid,
                "label": listing.get("label") or lid,
                "blurb": listing.get("blurb") or "",
                "kind": listing.get("kind"),
                "unitDef": listing.get("unitDef") or listing.get("factoryDef") or listing.get("product"),
                "count": listing.get("count") or listing.get("seedCount"),
                "tenebriumCost": tcost,
                "creditCost": int(listing.get("creditCost") or 0),
                "builds": bool(listing.get("builds")),
                "loan": bool(listing.get("loan")),
                "starterOwned": bool(listing.get("starterOwned")),
                "available": ok,
                "blockedReason": None if ok else reason,
                "owned": lid in owned or lid in upgrades,
                "repMin": listing.get("repMin") or {},
                "arcMin": int(listing.get("arcMin") or 1),
                "tags": list(listing.get("tags") or []),
                "requires": listing.get("requires"),
            }
        )

    deploy_kit: list[dict] = []
    listings = catalog.get("listings") or {}
    for lid, rec in owned.items():
        if not isinstance(rec, dict):
            continue
        listing = listings.get(lid) or {}
        kind = str(rec.get("kind") or listing.get("kind") or "purchase_package")
        unit_def = rec.get("unitDef") or listing.get("unitDef")
        count = int(rec.get("loanCount") or rec.get("count") or listing.get("count") or 0)
        if unit_def and count > 0:
            deploy_kit.append(
                {
                    "listingId": lid,
                    "kind": kind,
                    "unitDef": unit_def,
                    "count": count,
                    "loan": bool(rec.get("loan") or listing.get("loan")),
                    "label": listing.get("label") or lid,
                }
            )
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
        "credits": {
            "id": credits_meta.get("id") or "scrap_credits",
            "label": credits_meta.get("label") or "Scrap Credits",
        },
        "tenebrium": tenebrium,
        "scrapCredits": credits,
        "owned": owned,
        "upgrades": upgrades,
        "shop": shop,
        "deployKit": deploy_kit,
        "ledger": commerce_view["ledger"],
        "notes": (
            "Tenebrium is black-hole metal (scarce since the Generic Disaster). "
            "Anything that builds costs ≥1. Ashwalkers/Null Mercs start at 0."
        ),
        "catalogSchema": catalog.get("schemaVersion"),
        "armadaCrisis": (resource.get("armadaCrisis") or {}).get("active", True),
        "startingBalanceHint": starting,
    }


def build_faction_banks(state: dict, commerce: dict) -> dict:
    """Kernel paint: faction Tenebrium banks (Armada crisis → 0)."""
    banks = dict(state.get("factionBanks") or {})
    tnb = int(commerce.get("tenebrium") or 0)
    banks.setdefault("armada", 0)
    banks.setdefault("cortex", int((commerce.get("startingBalanceHint") or {}).get("cortex") or 2))
    banks.setdefault("nullmercs", tnb)
    banks.setdefault("ashwalkers", tnb)
    # Live bag always wins for player-side factions
    banks["nullmercs"] = tnb
    banks["ashwalkers"] = tnb
    if commerce.get("armadaCrisis", True):
        banks["armada"] = 0
    return {
        "armada": int(banks.get("armada") or 0),
        "cortex": int(banks.get("cortex") or 0),
        "nullmercs": int(banks.get("nullmercs") or 0),
        "ashwalkers": int(banks.get("ashwalkers") or 0),
    }


def build_hub(state: dict, war: dict) -> dict:
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
    companion = state.get("companion") or {}
    mission_n = int(state.get("missionNumber") or war.get("missionNumber") or 1)
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

    return {
        "schemaVersion": "verdance-hub-state/1.0",
        "campaignId": state.get("campaignId") or war.get("campaignId") or "verdance_ashes",
        "missionNumber": mission_n,
        "arc": arc,
        "pathSignal": state.get("pathSignal") or "B",
        "seed": state.get("seed") or 28,
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tagline": "Home is the Rock Jungle. Raid for Tenebrium. Clear the wilds when you can scale.",
        "sessionMode": session_mode,
        "sessionHomeMap": session_home,
        "theater": theater,
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
        "regions": regions,
        "node": node,
        "lastResult": _load_last_hub_result(),
        "history": [],
        "flags": {
            "mode": "hub",
            # True until HTML is opened via hub_host (runtime clears this).
            "deployStub": True,
            "hubHostHint": "app/bin/HUB_HOST.bat → http://127.0.0.1:8770/",
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
        },
    }


def _load_last_hub_result():
    p = ROOT / "outbox" / "hub_result.latest.json"
    if not p.is_file():
        return None
    try:
        data = load_json(p)
        return data.get("lastResult") or data
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
    hub = build_hub(state, war)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(hub, indent=2) + "\n", encoding="utf-8")
    OUT_EMBED.write_text(
        "window.HUB_STATE = " + json.dumps(hub, indent=None) + ";\n",
        encoding="utf-8",
    )
    shop_n = len((hub.get("commerce") or {}).get("shop") or [])
    avail = sum(1 for s in ((hub.get("commerce") or {}).get("shop") or []) if s.get("available"))
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_EMBED}")
    print(
        f"aces={len(hub['aces'])} regions={len(hub['regions'])} "
        f"choices={len(hub['node']['choices'])} shop={shop_n} available={avail} "
        f"tnb={hub.get('tenebrium')} mode={hub.get('sessionMode')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
