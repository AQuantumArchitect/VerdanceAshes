#!/usr/bin/env python3
"""Single credit table for Campaign ↔ BAR resolution.

Law: process_result and all side effects (flip, XP, commerce, graph) must
derive decisions only from credit_from_result(). No success-soup elsewhere.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

VERDICTS = frozenset({"victory", "partial", "defeat", "abandon", "incomplete"})

# Capture archetypes — flip only when node claimed.
_CAPTURE_KINDS = frozenset({"seize_lane", "gate_control", "hold_plateau"})

_VICTORY_STATUSES = frozenset({"victory", "victoryClean"})
_PARTIAL_STATUSES = frozenset({"partial", "extracted"})
_DEFEAT_STATUSES = frozenset({"defeat", "failed", "failure"})
_ABANDON_STATUSES = frozenset({"abandon", "abandoned", "quit"})
_INCOMPLETE_STATUSES = frozenset({"incomplete", "unknown", "active", "inactive", ""})

# Human headlines for hub debrief — keep in sync with docs/UI_ASH_CONSOLE.md
# and mod/.../va_ash_tokens.lua Ash.VERDICT (+ app/showoff VERDICT_UI).
_HEADLINES = {
    "victory": "Success.",
    "partial": "Partial success.",
    "defeat": "Defeat.",
    "abandon": "Withdrawn.",
    "incomplete": "Result pending — retry recovery or withdraw.",
}

# Short banners for BAR/hub cards (same dialect)
_BANNERS = {
    "victory": "SUCCESS",
    "partial": "PARTIAL SUCCESS",
    "defeat": "DEFEAT",
    "abandon": "WITHDRAWN",
    "incomplete": "RESULT PENDING",
}

_REASON_HINTS = {
    "extracted": "Clean pull-out after the objective.",
    "extracted_bypass": "Bypassed the hard target and extracted.",
    "extracted_bail": "Left early and held extract — partial success.",
    "extracted_voluntary": "Exfil button — left on purpose; partial success.",
    "extracted_recruit_lost": "Rescue wreck destroyed; company extracted with partial success.",
    "objective_complete_no_extraction_zone": "Objective done (no extract zone on seed).",
    "soft_clock_rescue_failed": "Mission timed out after the rescue failed. Extraction was not completed.",
    "operation_complete_no_extraction": "Operation completed; this mission has no extraction phase.",
    "soft_clock_no_extract": "Objective done; clock hit before extract.",
    "soft_clock_marks_open": "Primary done; clock hit with marks still open.",
    "soft_clock_timeout": "Soft clock expired mid-fight.",
    "player_wiped": "Force wiped.",
    "force_spent": "No combat power and no production left.",
    "gameover_external": "Engine game-over (resign / external).",
    "node_claimed": "Node claimed under regrow pressure.",
    "debug_command": "Debug terminal.",
}


def _s(v: Any, default: str = "") -> str:
    return str(v if v is not None else default)


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


def _i(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def is_capture_kind(result: Dict[str, Any]) -> bool:
    if result.get("captureMode") in (True, 1, "1", "true", "clear_hold_shell"):
        return True
    if _b(result.get("nodeClaimed")) or result.get("capturePhase") in (
        "clear",
        "hold",
        "claimed",
    ):
        # Only treat as capture path if phase/claim signals present with mode/arch
        arch = _s(
            result.get("objectiveArchetype")
            or result.get("objectiveKind")
            or (result.get("objectiveTarget") or {}).get("kind")
            if isinstance(result.get("objectiveTarget"), dict)
            else ""
        )
        if arch in _CAPTURE_KINDS or result.get("captureMode"):
            return True
    arch = _s(
        result.get("objectiveArchetype")
        or result.get("objectiveKind")
        or (
            (result.get("objectiveTarget") or {}).get("kind")
            if isinstance(result.get("objectiveTarget"), dict)
            else ""
        )
    )
    if arch in _CAPTURE_KINDS:
        return True
    # Explicit credits block from gadget
    credits = result.get("credits") if isinstance(result.get("credits"), dict) else {}
    if credits.get("nodeClaimed") is not None and result.get("captureMode"):
        return True
    return bool(result.get("captureMode"))


def resolve_verdict(result: Dict[str, Any]) -> str:
    """Map raw/normalized status → protocol verdict enum."""
    if result.get("verdict") in VERDICTS:
        return str(result["verdict"])
    status = _s(result.get("status") or result.get("verdict") or result.get("result")).lower()
    if status in _VICTORY_STATUSES:
        return "victory"
    if status in _PARTIAL_STATUSES:
        return "partial"
    if status in _DEFEAT_STATUSES:
        return "defeat"
    if status in _ABANDON_STATUSES:
        return "abandon"
    if status in _INCOMPLETE_STATUSES or status == "unknown":
        # Prefer incomplete only when explicitly incomplete; bare unknown → incomplete
        if status in ("incomplete", "unknown", "active", "inactive", ""):
            return "incomplete" if status in ("incomplete", "unknown", "") else "incomplete"
    # Legacy: success flag without status
    if _b(result.get("success")) and status not in _DEFEAT_STATUSES:
        return "victory"
    return "incomplete"


def build_result_key(result: Dict[str, Any]) -> str:
    """Hardened idempotency key (chapter + reason + frame)."""
    if result.get("resultKey") and "|ch" in str(result.get("resultKey")):
        return str(result["resultKey"])
    # Prefer gadget-provided if it already has enough parts
    existing = _s(result.get("resultKey"))
    campaign = _s(result.get("campaignId") or "verdance_ashes")
    mid = _s(result.get("missionId") or "va_unknown")
    mn = _i(result.get("missionNumber"), 0)
    ch = _i(result.get("chapterIndex"), 1)
    verdict = resolve_verdict(result)
    reason = _s(result.get("terminalReason") or "none").replace("|", "_")
    frame = _i(result.get("frame") or result.get("elapsedFrames") or result.get("gameFrame"), 0)
    hard = f"{campaign}|{mid}|{mn}|ch{ch}|{verdict}|{reason}|f{frame}"
    # If existing key is non-empty and already unique-ish with chapter, keep it
    if existing and existing.count("|") >= 3 and "ch" in existing:
        return existing
    return hard


def _credits_block(result: Dict[str, Any], verdict: str) -> Dict[str, bool]:
    raw = result.get("credits") if isinstance(result.get("credits"), dict) else {}
    objective_complete = _b(
        raw.get("objectiveComplete")
        if "objectiveComplete" in raw
        else result.get("objectiveComplete"),
        False,
    )
    if not objective_complete:
        # Destroyed objectives / complete status in objectiveResults
        destroyed = result.get("destroyedObjectiveIds") or result.get("destroyedObjectives") or []
        if destroyed:
            objective_complete = True
        for x in result.get("objectiveResults") or []:
            if isinstance(x, dict) and x.get("status") in ("complete", "destroyed"):
                objective_complete = True
                break

    node_claimed = _b(
        raw.get("nodeClaimed") if "nodeClaimed" in raw else result.get("nodeClaimed"),
        False,
    )
    if result.get("capturePhase") == "claimed":
        node_claimed = True

    pocket_cleared = _b(
        raw.get("pocketCleared") if "pocketCleared" in raw else result.get("pocketCleared"),
        False,
    )
    clean_extract = _b(
        raw.get("cleanExtract") if "cleanExtract" in raw else result.get("cleanExtract"),
        False,
    )
    if not clean_extract:
        ext = _s(result.get("extractionStatus")).lower()
        clean_extract = ext in ("clean", "success")

    capture = is_capture_kind(result)
    # zoneFlipEligible: capture only on claim; non-capture only on full victory + objective
    if "zoneFlipEligible" in raw:
        zone_flip_eligible = _b(raw.get("zoneFlipEligible"), False)
    elif capture:
        zone_flip_eligible = node_claimed and verdict in ("victory", "partial")
    else:
        zone_flip_eligible = verdict == "victory" and (
            objective_complete or clean_extract or _b(result.get("success"), False)
        )

    raid_credit = _b(raw.get("raidCredit"), False)
    if not raid_credit and not capture and objective_complete and verdict in ("victory", "partial"):
        raid_credit = True

    return {
        "objectiveComplete": bool(objective_complete),
        "nodeClaimed": bool(node_claimed),
        "pocketCleared": bool(pocket_cleared),
        "zoneFlipEligible": bool(zone_flip_eligible),
        "cleanExtract": bool(clean_extract),
        "raidCredit": bool(raid_credit),
        "isCapturePath": bool(capture),
    }


def credit_from_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return CreditDecision for process_result and debrief UI.

    Fields:
      verdict, terminalReason, resultKey, credits,
      xpTier: full|partial|loss|none,
      advanceMission: bool,
      applyState: bool,          # run process_result credit paths
      zoneFlip: bool,
      freeTnbMint: always False,
      headline, reasonHint, changed (list[str])
    """
    if not isinstance(result, dict):
        result = {}

    verdict = resolve_verdict(result)
    reason = _s(result.get("terminalReason") or "")
    credits = _credits_block(result, verdict)
    result_key = build_result_key({**result, "verdict": verdict, "terminalReason": reason})

    # XP tier + advance
    if verdict == "victory":
        xp_tier = "full"
        advance = True
        apply_state = True
    elif verdict == "partial":
        xp_tier = "partial"
        advance = True
        apply_state = True
    elif verdict == "defeat":
        xp_tier = "loss"
        advance = True
        apply_state = True
    elif verdict == "abandon":
        xp_tier = "none"
        advance = False
        apply_state = True  # bead only; process_result may short-circuit
    else:  # incomplete
        xp_tier = "none"
        advance = False
        apply_state = False

    zone_flip = bool(credits["zoneFlipEligible"]) and verdict in ("victory", "partial")
    if verdict in ("defeat", "abandon", "incomplete"):
        zone_flip = False

    # Legacy "success" for callers that still need a bool: full victory only for
    # commerce win tables; partial is NOT success.
    full_success = verdict == "victory"
    any_positive = verdict in ("victory", "partial")

    changed: list[str] = []
    if zone_flip:
        changed.append("zone flip eligible")
    else:
        if credits["isCapturePath"] and not credits["nodeClaimed"]:
            changed.append("no zone flip (claim incomplete)")
        elif verdict == "partial":
            changed.append("no zone flip (partial)")
        elif verdict == "defeat":
            changed.append("no zone flip (defeat)")

    if xp_tier == "full":
        changed.append("xp full")
    elif xp_tier == "partial":
        changed.append("xp partial")
    elif xp_tier == "loss":
        changed.append("xp loss / scars")
    else:
        changed.append("no campaign xp")

    if not advance:
        changed.append("mission number held")
    else:
        changed.append("mission advances")

    changed.append("freeTnbMint=false")

    headline = _HEADLINES.get(verdict, _HEADLINES["incomplete"])
    if reason and reason in _REASON_HINTS:
        # Keep headline short; hint separate
        pass
    reason_hint = _REASON_HINTS.get(reason, reason or "—")
    # Prefix side_* bail reasons that share one hint family.
    if reason_hint == reason and reason.startswith("extracted_side_"):
        reason_hint = "Side work done, then held extract — partial success."

    objective_failed = _b(
        result.get("objectiveFailed") or result.get("rescueContractFailed"), False
    )
    if objective_failed or reason == "extracted_recruit_lost":
        changed.append("rescue contract failed")

    return {
        "schemaVersion": "verdance-match-credit/1.0",
        "verdict": verdict,
        "terminalReason": reason,
        "resultKey": result_key,
        "credits": credits,
        "xpTier": xp_tier,
        "advanceMission": advance,
        "applyState": apply_state,
        "zoneFlip": zone_flip,
        "fullSuccess": full_success,
        "anyPositive": any_positive,
        "objectiveFailed": objective_failed,
        "freeTnbMint": False,
        "banner": _BANNERS.get(verdict, _BANNERS["incomplete"]),
        "headline": headline,
        "reasonHint": reason_hint,
        "changed": changed,
        "nextAction": (
            "mark_board"
            if advance
            else ("retry_or_abandon" if verdict == "incomplete" else "drop_or_mark")
        ),
    }


def presentable_debrief(
    credit: Dict[str, Any],
    *,
    extra_changed: Optional[list] = None,
    duplicate: bool = False,
) -> Dict[str, Any]:
    """Hub-facing debrief card."""
    changed = list(credit.get("changed") or [])
    if extra_changed:
        changed.extend(extra_changed)
    if duplicate:
        return {
            "ok": True,
            "verdict": credit.get("verdict"),
            "banner": _BANNERS.get(str(credit.get("verdict") or ""), _BANNERS["incomplete"]),
            "headline": "Already applied.",
            "terminalReason": credit.get("terminalReason"),
            "changed": ["duplicate resultKey — state unchanged"],
            "nextAction": "mark_board",
            "resultKey": credit.get("resultKey"),
            "duplicate": True,
        }
    return {
        "ok": bool(credit.get("applyState") or credit.get("verdict") == "incomplete"),
        "verdict": credit.get("verdict"),
        "banner": credit.get("banner") or _BANNERS.get(str(credit.get("verdict") or ""), _BANNERS["incomplete"]),
        "headline": credit.get("headline"),
        "terminalReason": credit.get("terminalReason"),
        "reasonHint": credit.get("reasonHint"),
        "objectiveFailed": bool(credit.get("objectiveFailed")),
        "changed": changed,
        "nextAction": credit.get("nextAction"),
        "resultKey": credit.get("resultKey"),
        "duplicate": False,
        "zoneFlip": credit.get("zoneFlip"),
        "xpTier": credit.get("xpTier"),
        "freeTnbMint": False,
    }


def xp_multiplier(tier: str) -> float:
    if tier == "full":
        return 1.0
    if tier == "partial":
        return 0.5
    if tier == "loss":
        return 0.25  # fought and lost still banks a little blood
    return 0.0
