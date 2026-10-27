#!/usr/bin/env python3
"""The story engine proper: ``process_result`` folds a sortie into the campaign, ``materialize_next_intent`` writes what the next Drop carries, and the CLI (``init-state`` / ``intent`` / ``advance``).

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import canonical_map_id, load_json, save_json, utc_now
from .schema import (
    CAMPAIGN_ID,
    INTENT_SCHEMA,
    STATE_SCHEMA,
    default_v1_state,
    ensure_zone_memory,
    map_family,
    migrate_state,
    mission_id,
    result_key,
    zone_infrastructure_for,
)
from .zones import canonical_zone_id, canonicalize_zone_ids
from .acts import act_for_mission, act_profile_for_state, finale_plan_for_state
from .progression import apply_reputation_companion, ensure_progression
from .hydrology import advance_planet_hydrology, map_waterline
from .measure import (
    apply_front_decay,
    apply_graph_deltas,
    apply_zone_dv,
    apply_player_regression,
    bp_access,
    get_elapsed_minutes,
    measure_graph_from_world,
    spectral_summary,
    tick_offscreen_zones,
    update_measured_zone_memory,
)
from .voice import (
    generate_beats,
    generate_briefing,
    generate_debrief_candidates,
    load_ketha_voice,
    pick_line,
    pick_title,
)
from .roster import (
    apply_act_rewards,
    apply_commander_story,
    apply_recruitment_beats,
    build_roster_intent,
    ensure_roster,
    merc_foothold_scale,
    update_roster,
)
from .commerce import (
    build_commerce_intent,
    ensure_commerce,
    ensure_faction_banks,
    settle_commerce_after_sortie,
)
from .home import evaluate_home_clear
from .living_shell import (
    apply_abstract_regrow,
    apply_player_footprint,
    apply_shell_scars,
    apply_surviving_installs,
)
from .objectives import (
    append_history_bead,
    build_war_map,
    choose_next_map_zone,
    objective_for_map,
    reset_live_raptors_but_escalate,
    update_destroyed_objectives,
    zone_pressure_summary,
)
from .sorties import (
    _is_hub_stamped_sortie,
    _is_player_debrief_sortie,
    _session_home_map,
    apply_sealed_company_to_packet,
    build_escalation_plan,
    consume_played_hub_sorties,
    generate_mode_a_sortie,
    load_sortie_order,
    objective_from_sortie,
    opening_sortie_order,
)
from .intent import (
    _difficulty_presentation,
    _economy_for_intent,
    expected_map_enemy_scale,
    generate_story_events,
    intent_story_tags,
    separate_intent_zones,
    story_reason_for_intent,
)
from verdance.readings.narrative import (
    operation_summary,
    project as narrative_project,
    world_snapshot,
    accept_result as accept_narrative_result,
)
from verdance.hub.contract import normalize_result, result_v2_to_v1_fields
from verdance.belief.match_credit import credit_from_result, presentable_debrief
from verdance.company.company import (
    ensure_company,
    apply_field_recruit_losses_from_result,
    apply_field_recruits_from_result,
)
from verdance.company.capture_node_claims import apply_node_claim, is_capture_result
from verdance.company import attachments as _att, synergy as _synergy
from verdance.world import (
    world_tick as _wt,
    offscreen_clash as _clash,
    roads as _roads,
    theaters as _theaters,
    visit_tiers as _vt,
    eye_story as _eye,
    landing_zones as _lz_seed,
)
from verdance.belief import manifest as _mf, homecoming as _bh, intel_lua as _il
from verdance.world.claim import claim_need
from verdance.world.graph_collapse import collapse_chips, collapse_payload, character_collapse_chips
from verdance.readings import (
    readings as _readings,
    occasions as _occasions,
    story_dance as _dance,
    chronicle as _chron,
)


def _shell_pockets(map_id: str, workspace: Optional[Path]) -> List[Dict[str, Any]]:
    """The map's living-shell pockets (for wardens), from the same template names the builder tries."""
    if workspace is None:
        return []
    base = Path(workspace) / "data" / "base_templates" / canonical_map_id(map_id)
    for name in ("armada_t15_v1.json", "living_shell_v1.json", "cortex_core_v1.json",
                 "armada_placeholder_v1.json", "living_placeholder_v1.json"):
        tpl = load_json(base / name, {}) if (base / name).is_file() else {}
        if tpl.get("pockets"):
            return list(tpl["pockets"])
    return []

def entry_zones_for(state: Dict[str, Any], map_id: str, workspace: Optional[Path] = None) -> Dict[str, List[str]]:
    """faction -> zone ids it controls on this map (zoneMemory truth, current zone ids)."""
    out: Dict[str, List[str]] = {}
    for zone_id, zone in ((state.get("zoneMemory") or {}).get(map_id) or {}).items():
        if not isinstance(zone, dict):
            continue
        ctrl = str(zone.get("controllingFaction") or (zone.get("abstract") or {}).get("control") or "").lower()
        if ctrl in ("", "neutral", "contested", "wild", "none"):
            continue
        zid = str(canonical_zone_id(zone_id, workspace) or zone_id)
        out.setdefault(ctrl, [])
        if zid not in out[ctrl]:
            out[ctrl].append(zid)
    return {k: sorted(v) for k, v in sorted(out.items())}


def wild_zones_for(state: Dict[str, Any], map_id: str, workspace: Optional[Path] = None) -> List[str]:
    """Zone ids the wild controls on this map (zoneMemory truth, current zone ids)."""
    out = set()
    for zone_id, zone in ((state.get("zoneMemory") or {}).get(map_id) or {}).items():
        if isinstance(zone, dict) and str(zone.get("controllingFaction") or (zone.get("abstract") or {}).get("control") or "").lower() == "wild":
            out.add(str(canonical_zone_id(zone_id, workspace) or zone_id))
    return sorted(out)


def materialize_next_intent(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    ensure_roster(state)
    ensure_commerce(state, workspace)
    ensure_faction_banks(state)
    # Drop 2: acts shape the mission. Act 3 IS the path-keyed finale — it
    # overrides contracts, Mode A walks, and the spine outright.
    act_info = act_profile_for_state(state)
    finale_plan = finale_plan_for_state(state)
    # Preference: hub C&C stamp / debrief pick beat the authored opening.
    # Opening only fills a fresh campaign when the player has not sealed a
    # theater-board drop (otherwise center raids get stomped by SE plateau).
    standing = None if finale_plan else load_sortie_order(workspace)
    hub_sealed = bool(standing and _is_hub_stamped_sortie(standing))
    debrief_sealed = bool(standing and _is_player_debrief_sortie(standing))
    opening = None
    if not finale_plan and not hub_sealed and not debrief_sealed:
        opening = opening_sortie_order(state, workspace)
    sortie = opening if opening else (None if finale_plan else standing)
    if opening and workspace is not None:
        # Keep the compiler-facing order files in lockstep with the intent. Do
        # not overwrite a hub stamp or in-engine debrief pick.
        outbox = Path(workspace) / "outbox"
        for name in ("next_sortie_choice.json", "next_sortie_order.json"):
            path = outbox / name
            try:
                existing = load_json(path) if path.exists() else None
                if existing and (
                    _is_player_debrief_sortie(existing) or _is_hub_stamped_sortie(existing)
                ):
                    continue
                outbox.mkdir(parents=True, exist_ok=True)
                save_json(path, opening)
            except Exception:
                pass
    # Drop 4 bug fix: a standing order aimed at ground the patron already
    # holds is spent (stale from a previous mission) — discard it and let
    # Mode A walk the quest board fresh instead of re-issuing it forever.
    # Hub C&C stamps are exempt: the player just clicked that wound on purpose
    # (home probe / own-base contracts are valid).
    if (
        sortie
        and sortie.get("mapId")
        and sortie.get("targetZoneId")
        and not _is_hub_stamped_sortie(sortie)
    ):
        _s_map = canonical_map_id(sortie["mapId"])
        _zm = ((state.get("zoneMemory") or {}).get(_s_map) or {}).get(str(sortie["targetZoneId"])) or {}
        _ctrl = _zm.get("controllingFaction") or (_zm.get("abstract") or {}).get("control") or "neutral"
        _bloc = "nullmercs" if _ctrl in ("nullmercs", "ashwalkers") else _ctrl
        _patron = sortie.get("patron") or "nullmercs"
        _patron = "nullmercs" if _patron in ("nullmercs", "ashwalkers") else _patron
        if _bloc == _patron:
            sortie = None
    # Mode A kernel: if no explicit order, walk same-map graph for a legal contract.
    if not sortie and not finale_plan:
        sortie = generate_mode_a_sortie(state, workspace) or {}
        if sortie:
            # Persist so compiler / validator see the same pick.
            try:
                if workspace is not None:
                    outp = Path(workspace) / "outbox" / "next_sortie_order.json"
                    outp.parent.mkdir(parents=True, exist_ok=True)
                    save_json(outp, sortie)
            except Exception:
                pass
    if finale_plan:
        map_id = finale_plan["mapId"]
        deploy_zone = finale_plan["deploymentZoneId"]
        objective = copy.deepcopy(finale_plan["objective"])
        contract_active = False
        sortie = {}
    elif sortie and sortie.get("mapId") and sortie.get("targetZoneId"):
        map_id = canonical_map_id(sortie["mapId"])
        # Mode A: refuse accidental map hops when a session home map is set.
        # Explicit hub theater stamps are intentional travel — never rewrite them
        # back onto sessionHomeMap (that is what swapped Rock Jungle → Greenest).
        home = _session_home_map(state, workspace)
        if (
            home
            and map_id != home
            and (sortie.get("sessionMode") or "same_map") == "same_map"
            and not _is_hub_stamped_sortie(sortie)
        ):
            # Re-roll quests locked to home map.
            alt = generate_mode_a_sortie(
                {**state, "history": (state.get("history") or []) + [{"mapId": home}]},
                workspace,
            )
            if alt and canonical_map_id(alt.get("mapId")) == home:
                sortie = alt
                map_id = home
        from_zones = list(sortie.get("fromZoneIds") or [])
        # Hub C&C board may stamp deploymentZoneId explicitly (G2 glue).
        deploy_zone = (
            sortie.get("deploymentZoneId")
            or (from_zones[0] if from_zones else None)
        )
        if not deploy_zone:
            # Fall back to first zone held by patron bloc on this map.
            patron = sortie.get("patron")
            patron_bloc = "nullmercs" if patron in ("nullmercs", "ashwalkers") else patron
            zones_on_map = (state.get("zoneMemory") or {}).get(map_id, {}) or {}
            for zid, zm in zones_on_map.items():
                ctrl = zm.get("controllingFaction") or (zm.get("abstract") or {}).get("control")
                bloc = "nullmercs" if ctrl in ("nullmercs", "ashwalkers") else ctrl
                if bloc == patron_bloc:
                    deploy_zone = zid
                    break
        if not deploy_zone:
            # Stay on map: first zoneMemory key or graph deploy-eligible.
            zones_on_map = (state.get("zoneMemory") or {}).get(map_id, {}) or {}
            deploy_zone = next(iter(zones_on_map.keys()), None)
            if not deploy_zone:
                _, deploy_zone = choose_next_map_zone(state, workspace)
                map_id = canonical_map_id(sortie["mapId"])
        objective = objective_from_sortie(sortie, state, workspace)
        # Multi-capture from hub board (arc 2+): primary stays targetZoneId.
        caps = list(sortie.get("captureZoneIds") or [])
        secondary = list(
            sortie.get("secondaryCaptureZoneIds")
            or (caps[1:] if len(caps) > 1 else [])
        )
        if secondary:
            objective["secondaryCaptureZoneIds"] = secondary
            objective["captureZoneIds"] = caps if caps else (
                [objective.get("targetZoneId")] + secondary
            )
        contract_active = True
    else:
        map_id, deploy_zone = choose_next_map_zone(state, workspace)
        objective = objective_for_map(map_id, state, workspace)
        contract_active = False
        sortie = {}

    pressure = zone_pressure_summary(state, map_id)
    zones = state.get("zoneMemory", {}).get(map_id, {})
    rehydrate = []
    for zone_id, zone in zones.items():
        snapshot = zone.get("baseSnapshot")
        if snapshot:
            rehydrate.append({
                "zoneId": zone_id,
                "control": zone.get("controllingFaction"),
                "snapshot": snapshot,
            })
    family = map_family(map_id)
    voice = load_ketha_voice(workspace)
    title = pick_title(voice, map_id, state.get("campaignId", CAMPAIGN_ID), state.get("missionNumber", 1))
    if (sortie or {}).get("openingMission"):
        title = "Opening Raid - Greenest Fields Decoy Farms" if title else None
    elif contract_active:
        title = objective.get("label") or objective.get("targetZoneId")
    if finale_plan:
        title = finale_plan["title"]
    rep = state.get("reputation", {}) or {}
    merc_rep = float(rep.get("nullmercs", 43) or 43)
    mission_num = int(state.get("missionNumber", 1) or 1)
    esc_plan = build_escalation_plan(state, map_id, objective, finale_plan, workspace)
    adj_mode = "required" if mission_num <= 3 else ("preferred" if mission_num <= 6 else "forward")
    # Hub extract mark wins when stamped on the sortie order.
    # Pass five: the company lands where it chose to extract to last time (manifest destination)
    # when that zone is on this map; otherwise where the sortie says.
    _camp = state.get("camp") or {}
    if _camp.get("nextPadZoneId") and (_camp.get("nextPadMapId") in (None, map_id)):
        _zm_map = (state.get("zoneMemory") or {}).get(map_id) or {}
        if str(_camp["nextPadZoneId"]) in _zm_map:
            deploy_zone = str(_camp["nextPadZoneId"])
    # Raiders: in and out from the same ground. The pad IS the deployment zone; traversal to
    # another map is a travel sortie, not a different extraction pad.
    extraction_zone = None if finale_plan else deploy_zone
    # Carry sandbox flavor from debrief pick into intent.
    flavor = (sortie or {}).get("flavor")
    against = (sortie or {}).get("against") or objective.get("enemyFaction") or "armada"
    patron = (sortie or {}).get("patron") or objective.get("patron") or "nullmercs"
    intent = {
        "schemaVersion": INTENT_SCHEMA,
        "campaignId": state.get("campaignId", CAMPAIGN_ID),
        "missionId": state.get("currentMissionId", mission_id(int(state.get("missionNumber", 1)))),
        "missionNumber": int(state.get("missionNumber", 1)),
        "act": act_info,
        "finale": finale_plan,
        "mapId": map_id,
        "deploymentZoneId": deploy_zone,
        "extractionZoneId": extraction_zone,
        "objective": objective["kind"],
        "objectiveTarget": objective,
        "patron": patron,
        "targetZoneId": objective.get("targetZoneId"),
        "fromZoneIds": list(objective.get("fromZoneIds") or (sortie or {}).get("fromZoneIds") or []),
        "contractXp": objective.get("contractXp") or (sortie or {}).get("contractXp"),
        "contractDifficulty": objective.get("difficulty") or (sortie or {}).get("difficulty"),
        "namedDefender": objective.get("namedDefender") or (sortie or {}).get("namedDefender"),
        "openingMission": bool((sortie or {}).get("openingMission")),
        "openingDoctrine": (sortie or {}).get("openingDoctrine"),
        "openingForce": copy.deepcopy((sortie or {}).get("openingForce")),
        "sessionMode": (sortie or {}).get("sessionMode") or "same_map",
        "occupationModel": (sortie or {}).get("occupationModel") or "living_shell",
        "captureMode": (
            (sortie or {}).get("captureMode")
            or (objective.get("captureMode") if isinstance(objective, dict) else None)
        ),
        "freeTnbMint": False if (
            (sortie or {}).get("captureMode")
            or (isinstance(objective, dict) and objective.get("captureMode"))
        ) else None,
        "shellScars": ((state.get("shellScars") or {}).get(map_id) or {}),
        # The waterline this mission inherits from the planet's water cycle.
        "hydrology": map_waterline(state, map_id, workspace),
        "factionBanks": ensure_faction_banks(state),
        "enemyInfrastructure": zone_infrastructure_for(map_id, workspace),
        "title": title,
        "escalationPlan": esc_plan,
        "briefing": generate_briefing(state, voice, map_id, family, objective, pressure, esc_plan),
        "debriefCandidates": generate_debrief_candidates(state, voice),
        "beats": generate_beats(state, voice, family, objective,
                                map_waterline(state, map_id, workspace)),
        "persistentBaseRehydrate": rehydrate,
        # Who may bring reinforcements in, and where: the zones each faction truly holds on this
        # map. The gadget lets a team enter only on the map edge inside one of its own zones, out
        # of the player's sight. Truth, not belief: this is the world deciding, not the company.
        "entryZones": entry_zones_for(state, map_id, workspace),
        # Zones the wild truly holds here (the dens on them are placed below, once the pad is final).
        "wildZones": wild_zones_for(state, map_id, workspace),
        # The doors on this map, for the in-game board: where each leads and whether the
        # company's ledger says it holds it.
        "doors": [dict(zoneId=zid, **d) for zid, d in _roads.door_markers(state, workspace, map_id).items()],
        "offscreenPressureSummary": pressure,
        "roster": build_roster_intent(state),
        "commerce": build_commerce_intent(state, workspace),
        "worldConflict": {
            # Keep wild as wild — Rock Jungle founding must not rewrite to Armada.
            "primaryEnemy": against if against else "armada",
            "accentFaction": (
                None if against in ("wild", "neutral")
                else ("cortex" if against != "cortex" else "armada")
            ),
            "patron": patron,
            "armadaTenebriumCrisis": bool(
                (state.get("worldFlags") or {}).get("armadaTenebriumCrisis", True)
            ),
            "armadaTenebriumCrisisBlurb": (
                "Armada High Command has no Tenebrium left — they poured the black-hole "
                "metal into a continent of autonomous decoy commanders farming wind, solar, "
                "and converters across the scar. Their build-power is frozen; their eco shells "
                "are already spent."
            ),
            "nullMercs": {
                "reputation": round(merc_rep, 1),
                "alliedWithPlayer": merc_rep >= 40.0,
                "footholdScale": merc_foothold_scale(merc_rep),
                "footholdZoneIds": [
                    zid for zid, z in zones.items()
                    if (z.get("controllingFaction") or z.get("abstract", {}).get("control")) in ("nullmercs", "ashwalkers")
                ],
            },
        },
        "expectedEnemyScale": expected_map_enemy_scale(state, map_id),
        "hazardPolicy": "escalating_reset" if family == "wild" else "none",
        "economy": _economy_for_intent(state),
        "progression": ensure_progression(state),
        "difficultyPresentation": _difficulty_presentation(state, map_id),
        "flavor": flavor,
        "storyTags": intent_story_tags(map_id, family, pressure)
            + (["contract"] if contract_active else [])
            + (["com_solar_farm"] if flavor == "com_solar_farm" else [])
            + ([act_info["name"]] if act_info else [])
            + (["finale", "finale-" + str(finale_plan.get("kind"))] if finale_plan else [])
            + (["epilogue"] if state.get("campaignComplete") else []),
        "campaignComplete": bool(state.get("campaignComplete")),
        "environment": {
            "mapFamily": family,
            "campaignClockMinutes": round(float(state.get("campaignClockMinutes", 0.0)), 2),
            "targetDuration": (sortie or {}).get("targetDuration")
                or ("40min" if finale_plan else "10min"),
        },
        "dialogueHooks": intent_story_tags(map_id, family, pressure),
        "storyReason": (
            f"Path {finale_plan['pathKey']} finale ({finale_plan['kind']}): the campaign's closing battle on {map_id}."
            if finale_plan
            else (
                "Opening raid: hit Armada decoy farms in Greenest Fields with Thugs and Legion Karkinos, then extract."
                if (sortie or {}).get("openingMission")
                else f"Contract for {patron} against {against} on {map_id}/{objective.get('targetZoneId')}"
            )
            if contract_active
            else story_reason_for_intent(map_id, family, pressure)
        ),
        "contractActive": contract_active,
        # Hub dropping list (stamp sortie_roster). apply_sealed keeps that
        # list. It fills the whole company only when no list was named.
        "source": (sortie or {}).get("source"),
        "hubChoiceId": (sortie or {}).get("hubChoiceId"),
        "deployAces": list((sortie or {}).get("deployAces") or []),
        "crewBand": list((sortie or {}).get("crewBand") or []),
        "missionCallIns": list((sortie or {}).get("missionCallIns") or []),
        "captureZoneIds": list(
            objective.get("captureZoneIds")
            or (sortie or {}).get("captureZoneIds")
            or ([objective.get("targetZoneId")] if objective.get("targetZoneId") else [])
        ),
        "secondaryCaptureZoneIds": list(
            objective.get("secondaryCaptureZoneIds")
            or (sortie or {}).get("secondaryCaptureZoneIds")
            or []
        ),
    }
    apply_sealed_company_to_packet(intent, state, workspace)
    # Authored content still names zones that a re-cut retired; translate the
    # whole intent forward in one place rather than trusting every source.
    intent = canonicalize_zone_ids(intent, workspace)
    separate_intent_zones(intent, workspace, state=state)
    # The field's standing set piece and the wild's dens, placed around the final pad.
    pad = intent.get("deploymentZoneId")
    intent["wildDens"] = _theaters.wild_dens(state, map_id, workspace, pad)
    # Whoever the company left here is still here: the gadget stands them where they stood.
    intent["fieldPeople"] = _mf.field_people(state, map_id)
    # Taking ground: the presence a claim needs here, and when the wound is a door, the exit the
    # extraction moves to once it is ours (verdance.world.claim, game_verdance_exfil.lua).
    intent["claimValue"] = claim_need(map_id, workspace)
    wound = (intent.get("captureZoneIds") or [intent.get("targetZoneId")])[0]
    if wound and _roads.is_door(wound, workspace) and wound != pad:
        intent["exitDoorZoneId"] = wound
    # The field ranks up each visit (verdance.world.visit_tiers): a harder war bake, wardens on a shell
    # field, a shorter raptor grace.
    visit_tier = _vt.plan(state, map_id, _shell_pockets(map_id, workspace))
    intent["visitTier"] = visit_tier
    if visit_tier.get("label") and isinstance(intent.get("briefing"), dict):
        intent["briefing"].setdefault("lines", []).append({"speaker": "ketha", "text": visit_tier["label"], "tag": "visit"})
    # The Eye of Horus: whoever thinks better of the company hires it (verdance.world.eye_story).
    if canonical_map_id(map_id) == _eye.MAP_ID and not intent.get("finale"):
        pad_xz = _theaters._point(_theaters._zones(map_id, workspace).get(str(pad), {})) if pad else None
        eye = _eye.story(state, pad_xz)
        intent["eyeStory"] = eye
        intent["objectiveTarget"] = _eye.objective(eye)
        intent["objective"] = intent["objectiveTarget"]["kind"]
        intent["targetZoneId"] = intent["objectiveTarget"]["targetZoneId"]
        for k in ("captureZoneIds", "secondaryCaptureZoneIds", "exitDoorZoneId"):
            intent.pop(k, None)
        if isinstance(intent.get("briefing"), dict):
            intent["briefing"].setdefault("lines", []).append(
                {"speaker": "ketha", "text": _eye.BRIEFING[eye["patron"]], "tag": "contract"})
    theater = _theaters.theater_for(state, map_id, workspace, pad, visit_tier["tier"])
    if theater:
        intent["theater"] = theater
        if theater.get("kind") == "kings_showdown":
            _theaters.solo_command(intent)
    # Bonds that are worth something on the field: rank-B XP, rank-A gifts. The gadget applies a
    # row only when both heroes of the pair actually drop.
    intent.update(_synergy.bond_perks(state, [h.get("heroId") for h in (intent.get("roster") or {}).get("heroes") or []], workspace))
    intent["operationSummary"] = operation_summary({
        "id": intent.get("hubChoiceId") or intent.get("missionId"),
        "label": intent.get("title") or "Company operation",
        "blurb": intent.get("storyReason") or "Secure the marked objective and bring the company home.",
        "effect": {"mapId": map_id, "contractKind": intent.get("objective")},
    })
    narrative_view = narrative_project(state, workspace=workspace)
    active_thread = next((t for t in narrative_view.get("threads", []) if t["stage"] == "Committed" and map_id in t["maps"]), None)
    if active_thread:
        intent["narrativeContext"] = {"threadId": active_thread["id"], "purpose": active_thread["reason"],
                                      "perspectives": active_thread["perspectives"]}
        intent["briefing"]["lines"].append({"speaker": "ketha", "text": active_thread["reason"], "tag": "commitment"})
        for perspective in active_thread["perspectives"]:
            if perspective["speaker"] != "ketha":
                intent["briefing"]["lines"].append({"speaker": perspective["speaker"], "text": perspective["text"], "tag": "company"})
    # Pass three: the sortie carries the company's BELIEF about the planned map into the Drop
    # (not truth). Pass 4 will draw it on the HUD until line of sight confirms or surprises.
    try:
        if workspace is not None:
            intent["intel"] = _bh.intel_for_intent(state, Path(workspace), map_id)
            # and the same belief as a Lua table the mod can VFS.Include (generated/va_intel_current.lua)
            _il.write_intel_lua(intent, Path(workspace))
            _il.write_pad_lua(intent, state, Path(workspace))
    except Exception as e:  # noqa: BLE001
        print(f"VA_INTENT_INTEL_SKIP {e}")
    return intent


def process_result(state: Dict[str, Any], result: Dict[str, Any], telemetry: Optional[Dict[str, Any]], workspace: Path, translation: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    narrative_before = world_snapshot(state)
    narrative_evidence = {k: copy.deepcopy(result[k]) for k in ("observedZoneIds", "deployAces", "deployedHeroes", "sortieHeroes") if k in result}
    state = migrate_state(state)
    ensure_zone_memory(state, workspace)
    # Normalize is law: MatchResult v2 fields only (no raw override soup).
    credit: Dict[str, Any] = {}
    try:
        # What ground the company holds as it lifts, and what of it was an enemy's: the verdict
        # reads these (a sortie is won by the ground held, not by one fixed checkbox).
        result = _mf.with_ground(state, result, workspace)
    except Exception:
        pass
    try:

        normalized = normalize_result(result)
        result = result_v2_to_v1_fields(normalized)
        credit = credit_from_result(result)
        result["resultKey"] = credit.get("resultKey") or result.get("resultKey")
        result["status"] = credit.get("verdict") or result.get("status")
        result["verdict"] = credit.get("verdict")
        result["freeTnbMint"] = False
    except Exception:
        try:

            credit = credit_from_result(result)
        except Exception:
            credit = {
                "verdict": result.get("status") or "incomplete",
                "resultKey": result_key(result),
                "fullSuccess": result.get("status") == "victory",
                "anyPositive": result.get("status") in ("victory", "partial"),
                "zoneFlip": False,
                "xpTier": "full" if result.get("status") == "victory" else "none",
                "advanceMission": result.get("status") in ("victory", "partial", "defeat"),
                "applyState": True,
                "credits": {},
                "freeTnbMint": False,
                "headline": "Result",
                "changed": [],
                "nextAction": "mark_board",
                "terminalReason": result.get("terminalReason") or "",
            }

    map_id = canonical_map_id(result.get("deploymentMapId") or result.get("mapId") or (telemetry or {}).get("map", {}).get("mapId"))
    elapsed = get_elapsed_minutes(result, telemetry, map_id)
    key = str(credit.get("resultKey") or result_key(result))
    result["resultKey"] = key

    # incomplete: do not mutate campaign (bring_home surfaces debrief only)
    if credit.get("verdict") == "incomplete" or not credit.get("applyState", True):
        intent = materialize_next_intent(state, workspace)
        events = generate_story_events(state, result, None, False, workspace)
        try:

            debrief = presentable_debrief(credit)
        except Exception:
            debrief = {
                "ok": False,
                "verdict": "incomplete",
                "headline": "Result not home — Retry extract or Abandon.",
                "resultKey": key,
                "duplicate": False,
            }
        return state, {
            "processed": False,
            "reason": "incomplete",
            "resultKey": key,
            "status": "incomplete",
            "verdict": "incomplete",
            "debrief": debrief,
            "credit": credit,
        }, intent, events

    # abandon: history bead only, no mission bump, no flips
    if credit.get("verdict") == "abandon":
        processed = key not in state.setdefault("processedResults", {})
        if not processed:
            intent = materialize_next_intent(state, workspace)
            events = generate_story_events(state, result, None, False, workspace)
            try:

                debrief = presentable_debrief(credit, duplicate=True)
            except Exception:
                debrief = {"duplicate": True, "resultKey": key}
            return state, {
                "processed": False,
                "reason": "duplicate",
                "resultKey": key,
                "debrief": debrief,
                "credit": credit,
            }, intent, events
        bead = append_history_bead(state, result, elapsed, {})
        bead.setdefault("storyTags", []).append("abandon")
        state["processedResults"][key] = {
            "processedAt": bead["timestamp"],
            "beadIndex": len(state["history"]) - 1,
            "elapsedMinutes": elapsed,
            "verdict": "abandon",
        }
        intent = materialize_next_intent(state, workspace)
        events = generate_story_events(state, result, bead, True, workspace)
        try:

            debrief = presentable_debrief(credit)
        except Exception:
            debrief = {"verdict": "abandon", "headline": "Left the field."}
        return state, {
            "processed": True,
            "resultKey": key,
            "status": "abandon",
            "verdict": "abandon",
            "zoneFlipped": False,
            "nodeClaimed": False,
            "freeTnbMint": False,
            "advanceMission": False,
            "bead": bead,
            "debrief": debrief,
            "credit": credit,
            "mapId": map_id,
        }, intent, events

    processed = key not in state.setdefault("processedResults", {})
    if not processed:
        # Intent/events for the response only — never mutate live state on a
        # duplicate (company seal / roster ensure would otherwise stick).
        intent = materialize_next_intent(copy.deepcopy(state), workspace)
        events = generate_story_events(copy.deepcopy(state), result, None, False, workspace)
        try:

            debrief = presentable_debrief(credit, duplicate=True)
        except Exception:
            debrief = {"duplicate": True, "resultKey": key, "headline": "Already applied."}
        return state, {
            "processed": False,
            "reason": "duplicate",
            "resultKey": key,
            "debrief": debrief,
            "credit": credit,
        }, intent, events

    try:

        ensure_company(state, workspace)
    except Exception:
        pass

    # The world evolves here, in Python, once per homecoming. BAR only reported facts.
    old_clock = float(state.get("campaignClockMinutes", 0.0) or 0.0)
    state["campaignClockMinutes"] = round(old_clock + elapsed, 4)
    measured_zones = update_measured_zone_memory(state, result, telemetry, workspace)
    dv_flips = apply_zone_dv(state, result, workspace)
    door_changes = _roads.record_homecoming(state, result, workspace)
    graph_delta = apply_graph_deltas(state, result, elapsed)
    # The Eye's contracts name their enemy (verdance.world.eye_story); the result only names the job.
    if not result.get("against"):
        _ek = str(result.get("objectiveKind") or result.get("objectiveArchetype") or "")
        if _ek in ("hunt_scouts", "raze_camp"):
            result = {**result, "against": "armada" if _ek == "hunt_scouts" else "cortex"}
    apply_reputation_companion(state, result, elapsed)
    try:
        evaluate_home_clear(state, result)
    except Exception:
        pass
    clean_extract = bool((credit.get("credits") or {}).get("cleanExtract")) or (
        result.get("extractionStatus", "") in ("clean", "success") or bool(result.get("cleanExtract"))
    )
    # Clean extract with a holding stack seeds the exfil pad as an Ashwalker
    # sortie origin (belief-majority base) for later inland / return raids.
    if clean_extract:
        extract_pad = (
            result.get("extractionZoneId")
            or (result.get("objectiveTarget") or {}).get("extractionZoneId")
            or result.get("deploymentZoneId")
        )
        if extract_pad:
            try:

                stack = result.get("extractStackWeight")
                if stack is None:
                    # Presence left on the pad: prefer explicit unit count, else 1.0.
                    stack = float(
                        result.get("extractUnitCount")
                        or result.get("unitsExtracted")
                        or 1.0
                    )
                _lz_seed.seed_ashwalker_pad(
                    state,
                    canonical_map_id(map_id),
                    canonical_zone_id(str(extract_pad), workspace),
                    stack_weight=max(1.0, float(stack)),
                )
            except Exception:
                pass
    # Credit table law: fullSuccess for win tables; anyPositive for partial paths.
    success = bool(credit.get("fullSuccess"))
    any_positive = bool(credit.get("anyPositive"))
    xp_tier = str(credit.get("xpTier") or "none")
    # Roster uses success for full gains; partial gets half via xp flag on result
    result["_xpTier"] = xp_tier
    roster_success = success or (xp_tier == "partial")
    update_roster(state, result, roster_success, clean_extract)
    # Abstract regrow first: heal *prior* scars over campaign time, then stamp new scars.
    regrow_report = apply_abstract_regrow(state, map_id, elapsed)
    apply_shell_scars(state, result, map_id)
    apply_surviving_installs(state, result, map_id)
    apply_player_footprint(state, result, map_id)

    # WO-006 / WO-005: Character Wreck Rule & Roster update.
    chars = state.setdefault("characters", default_v1_state()["characters"])
    named_outcomes = result.get("namedOutcomes", [])
    for outcome in named_outcomes:
        char_id = outcome.get("charId")
        res = outcome.get("outcome")  # dead, recovered, wounded
        if char_id in chars:
            c = chars[char_id]
            if res == "dead":
                c["status"] = "dead"
            elif res in ("recovered", "wounded"):
                # Going down leaves a scar either way; only a hero still down at the end is wounded.
                c["wounds"] = c.get("wounds", 0) + 1
                if not isinstance(c.get("scars"), list):
                    c["scars"] = []
                c["scars"].append(f"wound_{c['wounds']}")
                c["status"] = "wounded" if res == "wounded" else "active"
    for hero in (state.get("roster") or {}).get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        if hid not in chars or not isinstance(chars[hid], dict):
            continue
        camp = float(hero.get("campaignXp") or 0.0)
        sheet_target = camp * 12.5
        chars[hid]["xp"] = max(float(chars[hid].get("xp") or 0), sheet_target)
        if hero.get("status") == "dead":
            chars[hid]["status"] = "dead"
        elif hero.get("status") == "wounded":
            chars[hid]["status"] = "wounded"
        elif hero.get("status") == "active" and chars[hid].get("status") != "dead":
            chars[hid]["status"] = "active"

    # Zone flip: credit table only (capture claim or non-capture victory).
    zone_flipped = False
    target_zone_id = result.get("targetZoneId") or (
        result.get("objectiveTarget", {}).get("targetZoneId")
        if isinstance(result.get("objectiveTarget"), dict)
        else None
    )
    patron = result.get("patron") or "nullmercs"
    patron_bloc = "nullmercs" if patron in ("nullmercs", "ashwalkers") else patron
    node_claimed = bool((credit.get("credits") or {}).get("nodeClaimed")) or bool(
        result.get("nodeClaimed")
    ) or (result.get("capturePhase") == "claimed")
    capture_claim_report = None
    allow_flip = bool(credit.get("zoneFlip"))
    # A sortie won by ground: the ground that changed hands is the flip (the presence rule already
    # moved it); the assigned target is not handed to the patron on top of that.
    ground_win = result.get("objectiveCompleteHow") == _mf.GROUND_TAKEN and bool(result.get("groundTaken"))
    if ground_win:
        allow_flip = False
    try:

        if is_capture_result(result):
            # Only claim when credit table says flip (requires nodeClaimed)
            capture_claim_report = apply_node_claim(
                state, result, map_id=map_id, success=allow_flip and node_claimed
            )
            node_claimed = bool(capture_claim_report.get("claimed"))
            zone_flipped = bool(capture_claim_report.get("zoneFlipped") or capture_claim_report.get("claimed"))
        elif allow_flip and target_zone_id and map_id in state.get("zoneMemory", {}):
            zone_mem = state["zoneMemory"][map_id].get(target_zone_id)
            if zone_mem:
                zone_mem["controllingFaction"] = patron_bloc
                absr = zone_mem.setdefault("abstract", {})
                absr["control"] = patron_bloc
                zone_flipped = True
    except Exception:
        if allow_flip and target_zone_id and map_id in state.get("zoneMemory", {}):
            zone_mem = state["zoneMemory"][map_id].get(target_zone_id)
            if zone_mem:
                is_cap = bool(
                    result.get("captureMode")
                    or result.get("capturePhase") in ("clear", "hold", "claimed")
                )
                if is_cap and not node_claimed:
                    pass
                else:
                    zone_mem["controllingFaction"] = patron_bloc
                    absr = zone_mem.setdefault("abstract", {})
                    absr["control"] = patron_bloc
                    if node_claimed:
                        absr["claimedNode"] = True
                        absr["captureMode"] = result.get("captureMode") or "clear_hold_shell"
                    zone_flipped = True
                    claims = state.setdefault("nodeClaims", {}).setdefault(map_id, [])
                    if node_claimed:
                        claims.append(
                            {
                                "zoneId": target_zone_id,
                                "patron": patron_bloc,
                                "pocketCleared": bool(result.get("pocketCleared") or node_claimed),
                                "freeTnbMint": False,
                                "resultKey": result.get("resultKey"),
                                "at": utc_now(),
                            }
                        )
    if ground_win:
        zone_flipped = True
    # Commerce: fullSuccess for victory awards; partial still settles loans lightly
    settle = settle_commerce_after_sortie(
        state, result, success or any_positive, clean_extract, zone_flipped, workspace
    )
    if (node_claimed or (capture_claim_report or {}).get("claimed")) and isinstance(settle, dict):
        settle.setdefault("notes", []).append("capture claim settled with freeTnbMint=false")
    attachment_delta = None
    try:

        _att.ensure_attachments(state)
        attachment_delta = _att.update_attachments_from_result(
            state, result, success=success or any_positive, zone_flipped=zone_flipped
        )
        _wt.power_response(state)
    except Exception:
        attachment_delta = None
    spectral = spectral_summary(translation, state) if translation else None
    if spectral:
        state["lastSpectral"] = spectral
    graph_measured = measure_graph_from_world(state, result, spectral)
    update_destroyed_objectives(state, result)
    reset_live_raptors_but_escalate(state, result, elapsed, workspace)
    offscreen_tick = tick_offscreen_zones(state, map_id, measured_zones, elapsed, workspace)
    front_flips = apply_front_decay(state, map_id, measured_zones, elapsed)
    regression_flips = apply_player_regression(state, map_id, measured_zones, elapsed, workspace)
    clash_report: Optional[Dict[str, Any]] = None
    try:
        clash_report = _clash.run_offscreen_clashes(
            state,
            workspace,
            active_map_id=map_id,
            dt_minutes=elapsed,
            seed_key=str(result.get("resultKey") or key),
        )
    except Exception:
        clash_report = None
    bead = append_history_bead(state, result, elapsed, graph_delta)
    if door_changes:
        bead["doors"] = door_changes
        tags = bead.setdefault("storyTags", [])
        if any(d["held"] for d in door_changes):
            tags.append("door-taken")
        if any(not d["held"] for d in door_changes):
            tags.append("door-lost")
    if ground_win:
        bead.setdefault("storyTags", []).append("ground-taken")
        bead["groundTaken"] = list(result.get("groundTaken") or [])
    if dv_flips:
        bead["zonesChangedHands"] = list(dv_flips)
        if any(((state.get("zoneMemory") or {}).get(map_id, {}).get(z) or {}).get("controllingFaction") == "ashwalkers"
               for z in dv_flips):
            bead.setdefault("storyTags", []).append("presence-established")
    if front_flips:
        bead.setdefault("storyTags", []).append("territory-lost")
    if regression_flips:
        bead.setdefault("storyTags", []).append("player-regression")
    if clash_report and int(clash_report.get("flips") or 0) > 0:
        bead.setdefault("storyTags", []).append("offscreen-clash-flip")
    elif clash_report and int(clash_report.get("clashes") or 0) > 0:
        bead.setdefault("storyTags", []).append("offscreen-clash")
    bead["verdict"] = credit.get("verdict")
    bead["terminalReason"] = credit.get("terminalReason")
    bead["resultKey"] = key
    bead["offscreenTick"] = offscreen_tick
    if clash_report:
        bead["offscreenClash"] = {
            "clashes": clash_report.get("clashes"),
            "flips": clash_report.get("flips"),
        }
    state["processedResults"][key] = {
        "processedAt": bead["timestamp"],
        "beadIndex": len(state["history"]) - 1,
        "elapsedMinutes": elapsed,
        "verdict": credit.get("verdict"),
    }
    if credit.get("advanceMission", True):
        result_number = int(result.get("missionNumber", state.get("missionNumber", 1)))
        state["missionNumber"] = max(int(state.get("missionNumber", 1)) + 1, result_number + 1)
        state["currentMissionId"] = mission_id(state["missionNumber"])
        # The planet's water moves between missions, not during them: a basin
        # fills over a few sorties and drains over a few more.
        advance_planet_hydrology(state, workspace)
    # Consume a one-shot travel stamp from debrief/hub; lastSortie keeps Mode A
    # chains without stealing Ashwalker home onto a raid theater.
    travel = result.get("nextMapOverride") or result.get("travelIntent")
    if isinstance(travel, dict) and travel.get("mapId"):
        state["nextMapOverride"] = {
            "mapId": canonical_map_id(travel.get("mapId")),
            "deploymentZoneId": canonical_zone_id(
                travel.get("deploymentZoneId") or travel.get("targetZoneId") or "unknown_zone",
                workspace,
            ),
        }
    else:
        state.pop("nextMapOverride", None)
    if map_id:
        state["lastSortieMapId"] = canonical_map_id(map_id)
        if result.get("mapSpent") or result.get("theaterExhausted"):
            spent = state.setdefault("spentTheaters", {})
            if isinstance(spent, dict):
                spent[canonical_map_id(map_id)] = {
                    "at": utc_now(),
                    "missionNumber": int(result.get("missionNumber") or state.get("missionNumber") or 0),
                }
        # Ashwalker home is homeCamp / Rock Jungle. Raid theaters (Greenest, Eye, …)
        # must not rewrite sessionHomeMap — that trapped players on an emptied GF.
        camp_home = canonical_map_id(
            ((state.get("homeCamp") or {}).get("mapId"))
            or state.get("homeMapId")
            or "the_rock_jungle"
        )
        mid = canonical_map_id(map_id)
        journey = str(
            result.get("journey")
            or (result.get("sortie") or {}).get("journey")
            or ""
        ).lower()
        home_intent = bool(
            result.get("homeClearAttempt")
            or journey in ("home_founding", "home_clear", "home_hold")
            or mid == camp_home
        )
        if home_intent:
            state["sessionHomeMap"] = mid
        else:
            state["sessionHomeMap"] = camp_home or state.get("sessionHomeMap") or mid
        state.setdefault("sessionMode", result.get("sessionMode") or state.get("sessionMode") or "same_map")
        state.setdefault(
            "occupationModel",
            result.get("occupationModel") or state.get("occupationModel") or "living_shell",
        )
    # Drop 3: the campaign answers the result — recruits sign on, act-2
    # victories mint earned specials, and a finale victory closes the book.
    completed_mission = int(result.get("missionNumber", state.get("missionNumber", 1)) or 1)
    hero_joins = apply_recruitment_beats(state, result, success, completed_mission)
    # Field wreck/rez recruits from BAR (company preamble leftovers).
    # Joins + losses (blasted rescue wreck → fieldPool status=lost).
    field_losses: list = []
    try:

        field_losses = apply_field_recruit_losses_from_result(
            state, result, workspace=workspace
        ) or []
        field_joins = apply_field_recruits_from_result(
            state, result, workspace=workspace, full_success=bool(success)
        )
        if field_joins:
            hero_joins = list(hero_joins or []) + list(field_joins)
    except Exception as field_exc:
        # Never silently drop rescues — muster ownership depends on this path.
        try:
            print(f"VA_FIELD_RECRUIT_APPLY_FAIL {field_exc}")
        except Exception:
            pass
        field_joins = []
    walker = {"event": "scrap"}
    try:
        walker = apply_commander_story(state, result, hero_joins, workspace)
    except Exception as com_exc:
        try:
            print(f"VA_COMMANDER_STORY_FAIL {com_exc}")
        except Exception:
            pass
    else:
        if walker.get("event") == "unlocked":
            bead.setdefault("storyTags", []).append("commander-unlocked")
            bead["commander"] = walker
        elif walker.get("event") == "scrapped":
            bead.setdefault("storyTags", []).append("commander-scrapped")
            bead["commander"] = walker
    act_grant = apply_act_rewards(state, completed_mission, success)
    campaign_completed = False
    if success and act_for_mission(completed_mission) >= 3 and not state.get("campaignComplete"):
        campaign_completed = True
        state["campaignComplete"] = {
            "at": utc_now(),
            "missionNumber": completed_mission,
            "finaleKind": (finale_plan_for_state({**state, "missionNumber": completed_mission}) or {}).get("kind"),
            "pathSignal": state.get("pathSignal"),
        }
        # Rescued heroes who saw the campaign through become starting options from now on.
        try:
            from verdance.company.company import unlock_rescued_survivors
            gained = unlock_rescued_survivors(state, workspace)
            if gained:
                state["campaignComplete"]["unlocked"] = gained
        except Exception:  # noqa: BLE001
            pass
    if hero_joins:
        bead.setdefault("storyTags", []).append("hero-joined")
        # Readings layer: the bead must carry WHO joined, not just that someone did.
        bead["joined"] = [
            {"heroId": str(j.get("heroId") or j.get("id") or ""), "name": str(j.get("name") or "")}
            for j in hero_joins if isinstance(j, dict)
        ]
    # Readings layer: stamp named hero outcomes so the roll can be rebuilt from history.
    try:
        _outcomes = []
        for _o in (result.get("namedOutcomes") or []):
            if isinstance(_o, dict) and _o.get("charId"):
                _outcomes.append({"charId": str(_o["charId"]), "outcome": str(_o.get("outcome") or "")})
        _hr = result.get("heroResults") if isinstance(result.get("heroResults"), dict) else {}
        _seen = {o["charId"] for o in _outcomes}
        for _hid, _h in _hr.items():
            if isinstance(_h, dict) and _h.get("status") and str(_hid) not in _seen:
                _outcomes.append({"charId": str(_hid), "outcome": str(_h.get("status"))})
        if _outcomes:
            bead["namedOutcomes"] = _outcomes
    except Exception:
        pass
    if act_grant:
        bead.setdefault("storyTags", []).append("earned-specials")
    if campaign_completed:
        bead.setdefault("storyTags", []).append("campaign-complete")
    # Drop 4: bonus secondary marks pay out in merc standing. Required ones
    # gate victory in the gadget, so a processed win already implies them.
    bonus_secondaries = [
        s for s in (result.get("secondaryResults") or [])
        if isinstance(s, dict) and s.get("completed") and not s.get("required")
    ]
    if bonus_secondaries and result.get("status") in ("victory", "partial"):
        rep_map = state.setdefault("reputation", {})
        merc_now = float(rep_map.get("nullmercs", 43.0) or 43.0)
        rep_map["nullmercs"] = round(min(100.0, merc_now + 1.5 * len(bonus_secondaries)), 1)
        bead.setdefault("storyTags", []).append("secondary-cleared")
    else:
        bonus_secondaries = []
    narrative_event = accept_narrative_result(state, {**result, **narrative_evidence, "resultKey": key, "mapId": map_id}, credit, workspace, narrative_before)
    sortie_consume = consume_played_hub_sorties(workspace, result, map_id)
    # The manifest (pass five): people left stand where they stood; the destination moves the pad.
    try:
        _mfr = _mf.fold_manifest(state, result, bead, workspace)
        if not _mfr.get("skipped"):
            print(f"VA_MANIFEST left={_mfr.get('left')} dest={_mfr.get('destination')} verdict={_mfr.get('verdict')}")
    except Exception as _mx:  # noqa: BLE001
        print(f"VA_MANIFEST_FAIL {_mx}")
    # Belief world (Umwelt): fold this homecoming into the company's comprehension,
    # stamp the surprise (briefed vs found) on the bead, split truth from intel.
    # Skips cleanly when Umwelt is not importable; never blocks homecoming.
    if workspace is not None:
        try:
            _oc = bead.get("offscreenClash") or {}
            _new_fronts = int(_oc.get("clashes") or 0) + int(_oc.get("flips") or 0)
            _before = max(0, len(state.get("frontEvents") or []) - _new_fronts)
            _bf = _bh.fold_homecoming(state, result, bead, Path(workspace), before_front_count=_before)
            if _bf.get("skipped"):
                try:
                    print(f"VA_BELIEF_SKIP {_bf.get('reason')}")
                except Exception:
                    pass
        except Exception as _bx:
            try:
                print(f"VA_BELIEF_FAIL {_bx}")
            except Exception:
                pass
    # Readings layer (DERIVE faces; never world truth): rho_N over readings, attractor,
    # and the occasions the cast has to speak to. Written once per homecoming so
    # once-lines and recency carry forward. Failure here must never block homecoming.
    if workspace is not None:
        try:
            _ws = Path(workspace)
            _out = _ws / "outbox"
            _out.mkdir(parents=True, exist_ok=True)
            _prev_face = None
            _face_path = _out / "readings.latest.json"
            if _face_path.exists():
                try:
                    _prev_face = json.loads(_face_path.read_text(encoding="utf-8-sig"))
                    if _prev_face.get("generatedFrom", {}).get("campaignId") != state.get("campaignId"):
                        _prev_face = None
                except Exception:
                    _prev_face = None
            _face = _readings.project(json.loads(json.dumps(state)), _ws, _prev_face)
            # The story state after this sortie rides on its bead, so the path can be replayed.
            if state.get("history") and isinstance(state["history"][-1], dict):
                state["history"][-1]["story"] = _readings.snapshot(_face)
            _prev_occ = None
            _occ_path = _out / "occasions.latest.json"
            if _occ_path.exists():
                try:
                    _prev_occ = json.loads(_occ_path.read_text(encoding="utf-8-sig"))
                except Exception:
                    _prev_occ = None
            _occ = _occasions.build(_face, state, _ws, _prev_occ)
            _face_path.write_text(json.dumps(_face, indent=2, ensure_ascii=False), encoding="utf-8")
            _occ_path.write_text(json.dumps(_occ, indent=2, ensure_ascii=False), encoding="utf-8")
            (_out / "occasions.latest.md").write_text(_occasions.markdown(_occ), encoding="utf-8")
            # The dance tape (S3 shape): this homecoming's verbs, truth/goodness/beauty on the
            # bead, and the chronicle folded the brain-ant way.
            try:
                _dance.fold_homecoming(state, bead, _face, _occ, _ws, previous_face=_prev_face)
                _chron.write(state, _ws)
            except Exception as _dx:
                try:
                    print(f"VA_DANCE_FAIL {_dx}")
                except Exception:
                    pass
        except Exception as _rx:
            try:
                print(f"VA_READINGS_FAIL {_rx}")
            except Exception:
                pass
    intent = materialize_next_intent(state, workspace)
    events = generate_story_events(state, result, bead, True, workspace)
    extra_changed = []
    if zone_flipped:
        extra_changed.append("zone flipped")
    if node_claimed:
        extra_changed.append("node claimed")
    for j in hero_joins:
        extra_changed.append("{} joined the company".format(j["name"]))
    for lost in field_losses:
        if isinstance(lost, dict):
            extra_changed.append(
                "{} rescue lost — scrubbed from the wild".format(lost.get("name") or lost.get("heroId") or "recruit")
            )
    if act_grant:
        extra_changed.append("earned: {}".format(act_grant["label"]))
    for s in bonus_secondaries:
        extra_changed.append("bonus mark cleared: {} (+merc standing)".format(s.get("id") or "secondary"))
    if campaign_completed:
        extra_changed.append("CAMPAIGN COMPLETE — the ashes hold")
    # Drop-as-collapse: surface G axis moves on the debrief (GRAPH_COLLAPSE_SSOT).
    collapse = None
    try:

        extra_changed.extend(collapse_chips(graph_delta, graph_measured, max_chips=6))
        extra_changed.extend(character_collapse_chips(state, {"heroJoins": hero_joins}))
        collapse = collapse_payload(
            graph_after=state.get("graph"),
            graph_delta=graph_delta,
            graph_measured=graph_measured,
        )
    except Exception:
        collapse = None
    try:

        debrief = presentable_debrief(credit, extra_changed=extra_changed)
    except Exception:
        debrief = {
            "verdict": credit.get("verdict"),
            "headline": credit.get("headline"),
            "resultKey": key,
            "changed": extra_changed,
        }
    if isinstance(debrief, dict) and collapse:
        debrief["collapse"] = collapse
    if isinstance(debrief, dict) and narrative_event:
        debrief["narrativeEvent"] = narrative_event
    if campaign_completed and isinstance(debrief, dict):
        voice = load_ketha_voice(workspace)
        epilogue = pick_line(
            voice, "debrief.campaign_complete",
            state.get("campaignId", CAMPAIGN_ID), completed_mission,
        ) or "The war is over. The clans stand. Whatever grows here now grows ours."
        debrief["headline"] = epilogue
        debrief["epilogue"] = True
    report = {
        "processed": True,
        "resultKey": key,
        "elapsedMinutes": elapsed,
        "campaignClockMinutes": state["campaignClockMinutes"],
        "measuredZones": measured_zones,
        "graphDelta": graph_delta,
        "graphMeasured": graph_measured,
        "collapse": collapse,
        "spectral": spectral,
        "zoneFlipped": zone_flipped,
        "nodeClaimed": node_claimed,
        "freeTnbMint": False,
        "captureClaim": capture_claim_report,
        "regrow": regrow_report,
        "bead": bead,
        "sessionHomeMap": state.get("sessionHomeMap"),
        "sessionMode": state.get("sessionMode"),
        "sortieConsume": sortie_consume,
        "mapId": map_id,
        "targetZoneId": target_zone_id,
        "status": credit.get("verdict") or result.get("status"),
        "verdict": credit.get("verdict"),
        "terminalReason": credit.get("terminalReason"),
        "credit": credit,
        "debrief": debrief,
        "advanceMission": bool(credit.get("advanceMission", True)),
        "objectiveArchetype": result.get("objectiveArchetype") or (
            (result.get("objectiveTarget") or {}).get("kind") if isinstance(result.get("objectiveTarget"), dict) else None
        ),
        "attachmentDelta": attachment_delta,
        "worldResponse": state.get("worldResponse"),
        "offscreenTick": offscreen_tick,
        "offscreenClash": clash_report,
        "bpAccess": bp_access(state),
        "heroJoins": hero_joins,
        "actGrant": act_grant,
        "narrativeEvent": narrative_event,
        "bonusSecondaries": len(bonus_secondaries),
        "campaignComplete": bool(state.get("campaignComplete")),
    }
    return state, report, intent, events



def command_advance(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    result_path = Path(args.result) if args.result else workspace / "inbox" / "latest_va_result.json"
    telemetry_path = Path(args.telemetry) if args.telemetry else workspace / "outbox" / "bar_zone_telemetry.latest.json"
    translation_path = Path(args.translation) if getattr(args, "translation", "") else workspace / "inbox" / "latest_va_translation.json"
    outdir = Path(args.outdir) if args.outdir else workspace / "outbox"
    state_raw = load_json(state_path) if state_path.exists() else default_v1_state()
    result = load_json(result_path)
    telemetry = load_json(telemetry_path) if telemetry_path.exists() else None
    translation = load_json(translation_path) if translation_path.exists() else None
    state, report, intent, events = process_result(state_raw, result, telemetry, workspace, translation)

    if args.write_state:
        if state_path.exists() and state_raw.get("schemaVersion") != STATE_SCHEMA:
            backup = state_path.with_suffix(state_path.suffix + ".pre_v1_backup")
            if not backup.exists():
                backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
        save_json(state_path, state)
    save_json(outdir / "advance_report.v1.json", report)
    save_json(outdir / "next_mission_intent.json", intent)
    save_json(outdir / "story_events.latest.json", events)
    save_json(outdir / "war_map.json", build_war_map(state))
    print(json.dumps(report, indent=2))
    return 0


def command_intent(args: argparse.Namespace) -> int:
    """Materialize next_mission_intent.json from campaign state alone (no result needed)."""
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    outdir = Path(args.outdir) if args.outdir else workspace / "outbox"
    raw = load_json(state_path) if state_path.exists() else default_v1_state()
    state = migrate_state(raw)
    ensure_zone_memory(state, workspace)
    intent = materialize_next_intent(state, workspace)
    save_json(outdir / "next_mission_intent.json", intent)
    save_json(outdir / "war_map.json", build_war_map(state))
    print(json.dumps({"missionId": intent.get("missionId"), "mapId": intent.get("mapId"), "objective": intent.get("objective")}, indent=2))
    return 0


def command_init_state(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    state_path = Path(args.state) if args.state else workspace / "state" / "campaign_state.json"
    raw = load_json(state_path) if state_path.exists() else default_v1_state()
    state = migrate_state(raw)
    ensure_zone_memory(state, workspace)
    if args.write_state:
        if state_path.exists() and raw.get("schemaVersion") != STATE_SCHEMA:
            backup = state_path.with_suffix(state_path.suffix + ".pre_v1_backup")
            if not backup.exists():
                backup.write_text(state_path.read_text(encoding="utf-8"), encoding="utf-8")
        save_json(state_path, state)
    print(json.dumps({"schemaVersion": state["schemaVersion"], "zoneMaps": len(state.get("zoneMemory", {})), "writeState": bool(args.write_state)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verdance Story Engine v1")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-state")
    init.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    init.add_argument("--state", default="")
    init.add_argument("--write-state", action="store_true")
    init.set_defaults(func=command_init_state)

    intent = sub.add_parser("intent")
    intent.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    intent.add_argument("--state", default="")
    intent.add_argument("--outdir", default="")
    intent.set_defaults(func=command_intent)

    adv = sub.add_parser("advance")
    adv.add_argument("--workspace", default=str(Path.home() / "Documents" / "BAR_Verdance_Workspace"))
    adv.add_argument("--state", default="")
    adv.add_argument("--result", default="")
    adv.add_argument("--telemetry", default="")
    adv.add_argument("--translation", default="")
    adv.add_argument("--outdir", default="")
    adv.add_argument("--write-state", action="store_true")
    adv.set_defaults(func=command_advance)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


__all__ = [
    "build_parser",
    "command_advance",
    "command_init_state",
    "command_intent",
    "main",
    "materialize_next_intent",
    "process_result",
]


if __name__ == "__main__":
    raise SystemExit(main())
