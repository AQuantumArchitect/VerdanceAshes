#!/usr/bin/env python3
"""Sortie + Result contract v2 adapters (kernel).

Normalizes today's multi-schema surfaces into:
  - verdance-sortie-contract/2.0
  - verdance-match-result/2.0

Does not require UI. Writers still emit v1-compatible fields for gadgets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import load_json
from verdance.belief import manifest as _mf
from verdance.belief.match_credit import credit_from_result, resolve_verdict

SORTIE_V2 = "verdance-sortie-contract/2.0"
RESULT_V2 = "verdance-match-result/2.0"
INTENT_V1 = "verdance-mission-intent/1.0"
SORTIE_V1 = "verdance-sortie-order/1.0"
RESULT_V1 = "verdance-match-result/1.0"


def _s(v: Any, default: str = "") -> str:
    return str(v if v is not None else default)


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _b(v: Any, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def normalize_sortie(raw: Dict[str, Any], *, campaign_id: str = "verdance_ashes") -> Dict[str, Any]:
    """Accept sortie order, debrief pick, or intent-ish dict → sortie contract v2."""
    if not isinstance(raw, dict):
        raw = {}
    map_id = raw.get("mapId") or raw.get("map") or raw.get("deploymentMapId")
    target = raw.get("targetZoneId") or raw.get("zone") or raw.get("objectiveTarget")
    if isinstance(target, dict):
        target = target.get("targetZoneId") or target.get("id")
    from_z = raw.get("fromZoneIds") or raw.get("from") or []
    if isinstance(from_z, str):
        from_z = [z.strip() for z in from_z.split(",") if z.strip()]
    deploy = raw.get("deploymentZoneId") or (from_z[0] if from_z else None)
    extract = raw.get("extractionZoneId")
    arch = (
        raw.get("objectiveArchetype")
        or raw.get("kind")
        or raw.get("objective")
        or raw.get("contractKind")
    )
    caps = raw.get("captureZoneIds") or []
    if not isinstance(caps, list):
        caps = []
    # If only primary present, synthesize capture list
    if not caps and target:
        caps = [_s(target)]
    secondary = raw.get("secondaryCaptureZoneIds")
    if not isinstance(secondary, list) or not secondary:
        secondary = list(caps[1:]) if len(caps) > 1 else []
    arch_s = _s(arch or "seize_lane")
    # Capture kinds claim living shell nodes (clear pocket + hold under regrow).
    _CAPTURE_KINDS = frozenset({"seize_lane", "gate_control", "hold_plateau"})
    capture_mode = raw.get("captureMode")
    if capture_mode in (True, 1, "1", "true", "clear_hold_shell"):
        capture_mode = "clear_hold_shell"
    elif arch_s in _CAPTURE_KINDS:
        capture_mode = "clear_hold_shell"
    else:
        capture_mode = None
    return {
        "schemaVersion": SORTIE_V2,
        "campaignId": raw.get("campaignId") or campaign_id,
        "mapId": _s(map_id),
        "targetZoneId": _s(target),
        "deploymentZoneId": _s(deploy) if deploy else None,
        "extractionZoneId": _s(extract) if extract else None,
        "fromZoneIds": list(from_z or []),
        "captureZoneIds": [_s(z) for z in caps if z],
        "secondaryCaptureZoneIds": [_s(z) for z in secondary if z],
        "hubChoiceId": raw.get("hubChoiceId") or raw.get("choiceId"),
        "deployAces": list(raw.get("deployAces") or []),
        "crewBand": list(raw.get("crewBand") or raw.get("crew_band") or []),
        "repDelta": raw.get("repDelta") if isinstance(raw.get("repDelta"), dict) else {},
        "patron": _s(raw.get("patron") or "nullmercs"),
        "against": _s(raw.get("against") or raw.get("enemyFaction") or "armada"),
        "objectiveArchetype": arch_s,
        "sessionMode": _s(raw.get("sessionMode") or "same_map"),  # Mode A default
        "occupationModel": _s(raw.get("occupationModel") or "living_shell"),
        "captureMode": capture_mode,
        "difficulty": raw.get("difficulty") or raw.get("contractDifficulty"),
        "contractXp": raw.get("contractXp"),
        "namedDefender": raw.get("namedDefender"),
        "pathSignal": raw.get("pathSignal"),
        "graphSnapshot": raw.get("graphSnapshot"),
        "commerceDeploy": raw.get("commerceDeploy") or raw.get("commerce"),
        "worldFlags": {
            "armadaTenebriumCrisis": _b(
                (raw.get("worldFlags") or {}).get("armadaTenebriumCrisis")
                if isinstance(raw.get("worldFlags"), dict)
                else raw.get("armadaTenebriumCrisis"),
                True,
            ),
        },
        "valid": _b(raw.get("valid"), True),
        "sourceSchemas": [raw.get("schemaVersion")] if raw.get("schemaVersion") else [],
        "source": raw.get("source"),
        "derived": raw.get("derived") if isinstance(raw.get("derived"), dict) else None,
        "openingMission": raw.get("openingMission"),
        "openingDoctrine": raw.get("openingDoctrine"),
        "fromDebrief": raw.get("fromDebrief"),
        "debriefPick": raw.get("debriefPick"),
    }


def sortie_v2_to_v1_order(s: Dict[str, Any]) -> Dict[str, Any]:
    """Down-adapt for existing validate_sortie_contract / materialize paths."""
    return {
        "schemaVersion": SORTIE_V1,
        "campaignId": s.get("campaignId"),
        "mapId": s.get("mapId"),
        "targetZoneId": s.get("targetZoneId"),
        "deploymentZoneId": s.get("deploymentZoneId"),
        "extractionZoneId": s.get("extractionZoneId"),
        "fromZoneIds": list(s.get("fromZoneIds") or []),
        "captureZoneIds": list(s.get("captureZoneIds") or []),
        "secondaryCaptureZoneIds": list(s.get("secondaryCaptureZoneIds") or []),
        "hubChoiceId": s.get("hubChoiceId"),
        "deployAces": list(s.get("deployAces") or []),
        "crewBand": list(s.get("crewBand") or []),
        "repDelta": s.get("repDelta") if isinstance(s.get("repDelta"), dict) else {},
        "patron": s.get("patron"),
        "against": s.get("against"),
        "objectiveArchetype": s.get("objectiveArchetype"),
        "difficulty": s.get("difficulty"),
        "contractXp": s.get("contractXp"),
        "namedDefender": s.get("namedDefender"),
        "pathSignal": s.get("pathSignal"),
        "graphSnapshot": s.get("graphSnapshot"),
        "valid": s.get("valid", True),
        "sessionMode": s.get("sessionMode"),
        "occupationModel": s.get("occupationModel"),
        "captureMode": s.get("captureMode"),
        # Provenance — hub stamp vs opening vs debrief (materialize priority).
        "source": s.get("source"),
        "derived": s.get("derived") if isinstance(s.get("derived"), dict) else None,
        "openingMission": s.get("openingMission"),
    }


def normalize_result(raw: Dict[str, Any], *, campaign_id: str = "verdance_ashes") -> Dict[str, Any]:
    """Normalize gadget/infolog result JSON → result contract v2 (authoritative).

    Credits + verdict come from match_credit_v1 when available.
    """
    if not isinstance(raw, dict):
        raw = {}
    # Law: Lua reports facts, Python interprets. The gadget result carries no verdict,
    # no credits block and no extraction judgement (pass nine); whatever an older result
    # still carries under those names is dropped here so it can never steer the credit
    # table. status on a current result is the terminal KIND (extracted | wiped | closed).
    raw = dict(raw)
    for _k in ("credits", "zoneFlipped", "zoneFlipEligible", "cleanExtract", "freeTnbMint",
               "mapSpent", "theaterExhausted"):
        raw.pop(_k, None)
    terminal_kind = _s(raw.get("status") or "")
    if terminal_kind not in ("extracted", "wiped", "closed"):
        terminal_kind = ""
    # Pass five: the manifest is the ending; the verdict is read off it (manifest_v1).
    try:
        _v = _mf.verdict_from(raw)
        if _v:
            raw["status"] = _v
            raw["verdict"] = _v
        _es = _mf.extraction_status_from(raw)
        if _es is not None:
            raw["extractionStatus"] = _es
        # Won by ground, not by the checkbox: the company ended holding what it took from an enemy.
        if _v == "victory" and raw.get("groundTaken") and not _mf.objective_done(raw):
            raw["objectiveComplete"] = True
            raw["objectiveCompleteHow"] = _mf.GROUND_TAKEN
    except Exception:  # noqa: BLE001
        pass
    status = raw.get("status") or raw.get("verdict") or raw.get("result")
    # Clean extraction = the company lifted with no enemy on the pad (manifest.enemyOnPad == 0).
    # Legacy results without a manifest keep their own extractionStatus / clean flag.
    ext = _s(raw.get("extractionStatus")).lower()
    clean_extract = ext in ("clean", "success") or _b(raw.get("clean"), False)
    heroes = raw.get("heroes") or raw.get("heroResults") or {}
    survivors = raw.get("playerSurvivors") if isinstance(raw.get("playerSurvivors"), dict) else {}
    survivor_xp = (
        raw.get("playerSurvivorXp") if isinstance(raw.get("playerSurvivorXp"), dict) else {}
    )
    loan_hp = raw.get("loanUnitHp") if isinstance(raw.get("loanUnitHp"), dict) else {}
    scars = raw.get("shellScars") or raw.get("scars") or []
    capture_mode = (
        "clear_hold_shell"
        if raw.get("captureMode") in (True, 1, "1", "true", "clear_hold_shell")
        else (raw.get("captureMode") if raw.get("captureMode") else None)
    )
    node_claimed = _b(raw.get("nodeClaimed"), False) or _s(raw.get("capturePhase")) == "claimed"
    # Credit table is law for verdict / success / resultKey
    credit: Dict[str, Any] = {}
    try:

        seed = {
            **raw,
            "status": status,
            "cleanExtract": clean_extract,
            "nodeClaimed": node_claimed,
            "captureMode": capture_mode,
            "frame": raw.get("frame") or raw.get("elapsedFrames") or raw.get("gameFrame"),
        }
        credit = credit_from_result(seed)
        verdict = credit.get("verdict") or resolve_verdict(seed)
        success = bool(credit.get("fullSuccess"))
        result_key = credit.get("resultKey") or _s(raw.get("resultKey") or raw.get("key"))
        free_tnb = False
        credits_block = credit.get("credits") or {}
    except Exception:
        # Fallback without credit module
        verdict = _s(status or "incomplete")
        if verdict in ("victory", "victoryClean"):
            verdict = "victory"
            success = True
        elif verdict in ("partial", "extracted"):
            verdict = "partial"
            success = False
        elif verdict in ("defeat", "failed", "failure"):
            verdict = "defeat"
            success = False
        elif verdict in ("abandon", "abandoned"):
            success = False
        else:
            verdict = verdict if verdict in (
                "victory", "partial", "defeat", "abandon", "incomplete"
            ) else "incomplete"
            success = False
        result_key = _s(raw.get("resultKey") or raw.get("key"))
        free_tnb = False
        credits_block = {
            "objectiveComplete": _b(raw.get("objectiveComplete"), False),
            "nodeClaimed": node_claimed,
            "pocketCleared": _b(raw.get("pocketCleared"), False),
            "zoneFlipEligible": node_claimed if capture_mode else (verdict == "victory"),
            "cleanExtract": clean_extract,
            "raidCredit": False,
        }

    chapter = _i(raw.get("chapterIndex"), 0)
    if chapter <= 0:
        chapter = 1

    # Zone flip is the credit table's call (capture: claim; raid: full victory), never the gadget's.
    zone_flipped = bool(credit.get("zoneFlip")) if credit else bool(
        (credits_block or {}).get("zoneFlipEligible") and verdict in ("victory", "partial")
    )

    return {
        "schemaVersion": RESULT_V2,
        "campaignId": raw.get("campaignId") or campaign_id,
        "resultKey": result_key,
        "sortieId": raw.get("sortieId") or raw.get("hubChoiceId") or raw.get("choiceId"),
        "missionId": raw.get("missionId"),
        "missionNumber": _i(raw.get("missionNumber"), 0),
        "mapId": _s(raw.get("mapId") or raw.get("deploymentMapId")),
        "chapterIndex": chapter,
        "verdict": verdict,
        "status": verdict,  # flatten for legacy process_result readers
        "terminalKind": terminal_kind,  # what the gadget reported: extracted | wiped | closed
        "terminalReason": _s(raw.get("terminalReason") or ""),
        "success": success,
        "cleanExtract": clean_extract,
        "zoneFlipped": zone_flipped,
        "targetZoneId": raw.get("targetZoneId"),
        "deploymentZoneId": raw.get("deploymentZoneId"),
        "extractionZoneId": raw.get("extractionZoneId"),
        "extractionStatus": raw.get("extractionStatus"),
        "objectiveComplete": _b(
            (credits_block or {}).get("objectiveComplete"),
            _b(raw.get("objectiveComplete"), False),
        ),
        # Gadget facts about how the primary resolved (pass nine; absent on older results).
        "objectiveKind": raw.get("objectiveKind"),
        "objectiveMode": raw.get("objectiveMode"),
        "objectiveCompleteHow": _s(raw.get("objectiveCompleteHow") or ""),
        "groundHeld": list(raw.get("groundHeld") or []) if isinstance(raw.get("groundHeld"), list) else [],
        "groundTaken": list(raw.get("groundTaken") or []) if isinstance(raw.get("groundTaken"), list) else [],
        "objectiveCompleteFrame": _i(raw.get("objectiveCompleteFrame"), 0),
        "nodeClaimedFrame": _i(raw.get("nodeClaimedFrame"), 0),
        "requiredMarksLeft": _i(raw.get("requiredMarksLeft"), 0),
        "allObjectivesDone": _b(raw.get("allObjectivesDone"), False),
        # Rescue-contract fail latch from gadget (partial RTB path).
        "objectiveFailed": _b(
            raw.get("objectiveFailed") or raw.get("rescueContractFailed"), False
        ),
        "objectiveFailReason": _s(
            raw.get("objectiveFailReason") or raw.get("rescueContractFailReason") or ""
        ),
        "objectiveFailHero": _s(
            raw.get("objectiveFailHero")
            or raw.get("rescueFailHero")
            or raw.get("rescueContractFailHero")
            or ""
        ),
        "rescueContractFailed": _b(
            raw.get("rescueContractFailed") or raw.get("objectiveFailed"), False
        ),
        "heroes": heroes,
        "heroResults": raw.get("heroResults") if isinstance(raw.get("heroResults"), dict) else heroes,
        "namedOutcomes": raw.get("namedOutcomes") if isinstance(raw.get("namedOutcomes"), list) else [],
        "recruitedHeroIds": (
            list(raw.get("recruitedHeroIds") or raw.get("recruitedHeroes") or [])
            if isinstance(raw.get("recruitedHeroIds") or raw.get("recruitedHeroes") or [], list)
            else []
        ),
        "playerSurvivors": survivors,
        "playerSurvivorXp": survivor_xp,
        "loanUnitHp": loan_hp,
        "tenebrium": {
            "bank": _i(raw.get("tenebriumBank"), -1),
            "looted": _i(raw.get("tenebriumLooted"), 0),
            "spent": _i(raw.get("tenebriumSpent"), 0),
            "lost": _i(raw.get("tenebriumLost"), 0),
        },
        "tenebriumBank": _i(raw.get("tenebriumBank"), -1),
        "tenebriumLooted": _i(raw.get("tenebriumLooted"), 0),
        "tenebriumSpent": _i(raw.get("tenebriumSpent"), 0),
        "tenebriumLost": _i(raw.get("tenebriumLost"), 0),
        "metalStored": raw.get("metalStored"),
        "metalStorage": raw.get("metalStorage"),
        "metalKExtracted": _i(raw.get("metalKExtracted"), -1),
        "armadaTenebriumCrisis": _b(raw.get("armadaTenebriumCrisis"), True),
        "shellScars": scars,
        "survivingInstalls": (
            raw.get("survivingInstalls")
            if isinstance(raw.get("survivingInstalls"), list)
            else (raw.get("survivingInstallations") if isinstance(raw.get("survivingInstallations"), list) else [])
        ),
        # None when absent — apply_player_footprint must not wipe prior pads
        # on truncated/legacy results. Explicit [] still clears.
        "playerFootprint": (
            raw.get("playerFootprint")
            if isinstance(raw.get("playerFootprint"), list)
            else (raw.get("zoneFootprint") if isinstance(raw.get("zoneFootprint"), list) else None)
        ),
        "playerFootprintPresent": (
            isinstance(raw.get("playerFootprint"), list)
            or isinstance(raw.get("zoneFootprint"), list)
        ),
        # Pass three belief contract (pass 4 fills these from the gadget):
        #   observedZones {zoneId: eta 0..1} — line-of-sight share per zone, recency weighted.
        #   beliefExport  {zoneId: {ours, held, strength, threat}} — what the HUD showed at exit, at its own eta.
        # Absent → the fold falls back to a footprint proxy; never invented here.
        "observedZones": (raw.get("observedZones") if isinstance(raw.get("observedZones"), dict) else None),
        "manifest": (raw.get("manifest") if isinstance(raw.get("manifest"), dict) else None),
        "beliefExport": (raw.get("beliefExport") if isinstance(raw.get("beliefExport"), dict) else None),
        #   zoneDv {zoneId: {faction: metal}} — defensive value standing in each zone at the end (a fact).
        "zoneDv": (raw.get("zoneDv") if isinstance(raw.get("zoneDv"), dict) else None),
        "destroyedObjectives": raw.get("destroyedObjectives") or raw.get("destroyedObjectiveIds") or [],
        "destroyedObjectiveIds": raw.get("destroyedObjectiveIds") or raw.get("destroyedObjectives") or [],
        "objectiveResults": raw.get("objectiveResults") or [],
        # Drop 4: per-secondary-objective ledger from the gadget (bonus marks
        # pay merc standing on the engine side).
        "secondaryResults": raw.get("secondaryResults") or [],
        "elapsedFrames": _i(raw.get("elapsedFrames") or raw.get("gameFrame") or raw.get("frame"), 0),
        "frame": _i(raw.get("frame") or raw.get("elapsedFrames") or raw.get("gameFrame"), 0),
        "elapsedMinutes": raw.get("elapsedMinutes"),
        "nodeClaimed": node_claimed,
        "pocketCleared": _b(raw.get("pocketCleared"), False),
        "capturePhase": _s(raw.get("capturePhase") or "idle"),
        "captureMode": capture_mode,
        "regrowWaves": _i(raw.get("regrowWaves"), 0),
        # Law: never free-mint Tnb on claim
        "occupationModel": _s(raw.get("occupationModel") or "living_shell"),
        "sessionMode": _s(raw.get("sessionMode") or "same_map"),
        "softContinueArmed": _b(raw.get("softContinueArmed"), False),
        "patron": raw.get("patron"),
        "pathSignal": raw.get("pathSignal"),
        "objectiveArchetype": raw.get("objectiveArchetype")
        or (
            (raw.get("objectiveTarget") or {}).get("kind")
            if isinstance(raw.get("objectiveTarget"), dict)
            else None
        ),
        "credits": credits_block,
        "credit": credit or None,
        "sourceSchemas": [raw.get("schemaVersion")] if raw.get("schemaVersion") else [],
    }


def result_v2_to_v1_fields(r: Dict[str, Any]) -> Dict[str, Any]:
    """Expand v2 result into flat v1-ish fields process_result already understands."""
    tnb = r.get("tenebrium") or {}
    return {
        "schemaVersion": RESULT_V1,
        "campaignId": r.get("campaignId"),
        "resultKey": r.get("resultKey"),
        "sortieId": r.get("sortieId"),
        "missionId": r.get("missionId"),
        "missionNumber": r.get("missionNumber"),
        "mapId": r.get("mapId"),
        "deploymentMapId": r.get("mapId"),
        "status": r.get("verdict") or r.get("status"),
        "verdict": r.get("verdict") or r.get("status"),
        "terminalReason": r.get("terminalReason"),
        "success": r.get("success"),
        "cleanExtract": r.get("cleanExtract"),
        "zoneFlipped": r.get("zoneFlipped"),
        "targetZoneId": r.get("targetZoneId"),
        "deploymentZoneId": r.get("deploymentZoneId"),
        "extractionZoneId": r.get("extractionZoneId"),
        "extractionStatus": r.get("extractionStatus"),
        "objectiveComplete": r.get("objectiveComplete"),
        "objectiveKind": r.get("objectiveKind"),
        "objectiveMode": r.get("objectiveMode"),
        "objectiveCompleteHow": r.get("objectiveCompleteHow"),
        "groundHeld": r.get("groundHeld") or [],
        "groundTaken": r.get("groundTaken") or [],
        "objectiveCompleteFrame": r.get("objectiveCompleteFrame"),
        "nodeClaimedFrame": r.get("nodeClaimedFrame"),
        "requiredMarksLeft": r.get("requiredMarksLeft"),
        "allObjectivesDone": r.get("allObjectivesDone"),
        "terminalKind": r.get("terminalKind"),
        "objectiveFailed": r.get("objectiveFailed"),
        "objectiveFailReason": r.get("objectiveFailReason"),
        "objectiveFailHero": r.get("objectiveFailHero"),
        "rescueContractFailed": r.get("rescueContractFailed") or r.get("objectiveFailed"),
        "heroes": r.get("heroes"),
        "heroResults": r.get("heroResults") or r.get("heroes"),
        "namedOutcomes": r.get("namedOutcomes") or [],
        "recruitedHeroIds": list(r.get("recruitedHeroIds") or []),
        "playerSurvivors": r.get("playerSurvivors"),
        "playerSurvivorXp": r.get("playerSurvivorXp"),
        "loanUnitHp": r.get("loanUnitHp"),
        "tenebriumBank": (tnb.get("bank") if isinstance(tnb, dict) else r.get("tenebriumBank")),
        "tenebriumLooted": (tnb.get("looted") if isinstance(tnb, dict) else r.get("tenebriumLooted", 0)),
        "tenebriumSpent": (tnb.get("spent") if isinstance(tnb, dict) else r.get("tenebriumSpent", 0)),
        "tenebriumLost": (tnb.get("lost") if isinstance(tnb, dict) else r.get("tenebriumLost", 0)),
        "metalStored": r.get("metalStored"),
        "metalStorage": r.get("metalStorage"),
        "metalKExtracted": r.get("metalKExtracted"),
        "armadaTenebriumCrisis": r.get("armadaTenebriumCrisis"),
        "shellScars": r.get("shellScars"),
        "survivingInstalls": r.get("survivingInstalls") or [],
        # Preserve absent vs explicit-empty for footprint credit (no silent wipe).
        **(
            {"playerFootprint": r.get("playerFootprint")}
            if r.get("playerFootprintPresent") or isinstance(r.get("playerFootprint"), list)
            else {}
        ),
        "destroyedObjectives": r.get("destroyedObjectives"),
        "destroyedObjectiveIds": r.get("destroyedObjectiveIds") or r.get("destroyedObjectives"),
        **({"observedZones": r.get("observedZones")} if isinstance(r.get("observedZones"), dict) else {}),
        **({"manifest": r.get("manifest")} if isinstance(r.get("manifest"), dict) else {}),
        **({"beliefExport": r.get("beliefExport")} if isinstance(r.get("beliefExport"), dict) else {}),
        **({"zoneDv": r.get("zoneDv")} if isinstance(r.get("zoneDv"), dict) else {}),
        "objectiveResults": r.get("objectiveResults") or [],
        "secondaryResults": r.get("secondaryResults") or [],
        "elapsedFrames": r.get("elapsedFrames"),
        "frame": r.get("frame") or r.get("elapsedFrames"),
        "elapsedMinutes": r.get("elapsedMinutes"),
        "chapterIndex": r.get("chapterIndex"),
        "nodeClaimed": r.get("nodeClaimed"),
        "pocketCleared": r.get("pocketCleared"),
        "capturePhase": r.get("capturePhase"),
        "captureMode": r.get("captureMode"),
        "regrowWaves": r.get("regrowWaves"),
        "occupationModel": r.get("occupationModel"),
        "sessionMode": r.get("sessionMode"),
        "softContinueArmed": r.get("softContinueArmed"),
        "patron": r.get("patron"),
        "pathSignal": r.get("pathSignal"),
        "objectiveArchetype": r.get("objectiveArchetype"),
        "credits": r.get("credits"),
        "credit": r.get("credit"),
    }


def intent_from_sortie_v2(s: Dict[str, Any], base_intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Stamp sortie v2 fields onto a mission intent dict."""
    intent = dict(base_intent or {})
    intent.setdefault("schemaVersion", INTENT_V1)
    intent["mapId"] = s.get("mapId") or intent.get("mapId")
    intent["targetZoneId"] = s.get("targetZoneId")
    intent["deploymentZoneId"] = s.get("deploymentZoneId") or intent.get("deploymentZoneId")
    intent["extractionZoneId"] = s.get("extractionZoneId") or intent.get("extractionZoneId")
    intent["fromZoneIds"] = list(s.get("fromZoneIds") or [])
    intent["captureZoneIds"] = list(s.get("captureZoneIds") or intent.get("captureZoneIds") or [])
    intent["secondaryCaptureZoneIds"] = list(
        s.get("secondaryCaptureZoneIds") or intent.get("secondaryCaptureZoneIds") or []
    )
    if s.get("hubChoiceId"):
        intent["hubChoiceId"] = s.get("hubChoiceId")
    if s.get("deployAces"):
        intent["deployAces"] = list(s.get("deployAces") or [])
    if s.get("crewBand"):
        intent["crewBand"] = list(s.get("crewBand") or [])
    intent["objective"] = s.get("objectiveArchetype") or intent.get("objective")
    intent["patron"] = s.get("patron")
    intent["sessionMode"] = s.get("sessionMode") or "same_map"
    intent["occupationModel"] = s.get("occupationModel") or "living_shell"
    if s.get("captureMode"):
        intent["captureMode"] = s.get("captureMode")
    intent["sortieContractV2"] = s
    return intent



def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Contract v2 normalize probe")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--sortie", default="outbox/next_sortie_order.json")
    ap.add_argument("--result", default="inbox/latest_va_result.json")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    s_raw = load_json(ws / args.sortie, {})
    r_raw = load_json(ws / args.result, {})
    s2 = normalize_sortie(s_raw)
    r2 = normalize_result(r_raw)
    out = {
        "sortieV2": s2,
        "resultV2": r2,
        "sortieV1": sortie_v2_to_v1_order(s2),
        "resultV1": result_v2_to_v1_fields(r2),
    }
    print(json.dumps(out, indent=2)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
