"""Reputation, companion mood and the XP/level ladders shared by roster and heroes.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

from typing import Any, Dict

from verdance.common import clamp
from .schema import default_v1_state

def get_character_rank(xp: float | int) -> str:
    val = int(xp)
    if val >= 3000:
        return "Marshal"
    elif val >= 2200:
        return "Warden"
    elif val >= 1500:
        return "Captain"
    elif val >= 800:
        return "Proven"
    return "Runner"


# Faction rep starts (v0.8.3). Cortex dealers want customers; Armada is cold.
REP_START_ARMADA = 18.0
REP_START_CORTEX = 70.0
REP_START_NULLMERCS = 48.0

# Crater / Cortex gear destruction — rapid plunge (they want customers until you bomb them).
CORTEX_CRATER_MAPS = frozenset({"eye_of_horus", "eyeofhorus"})
CORTEX_GRUDGE_VICTORY = -18.0
CORTEX_GRUDGE_PARTIAL = -10.0
CORTEX_GRUDGE_DEFEAT_DAMAGE = -4.0
ARMADA_RAID_HIT = -3.0  # modest when raiding Armada eco


def _result_destroyed_any(result: Dict[str, Any]) -> bool:
    destroyed = result.get("destroyedObjectiveIds") or result.get("destroyedObjectives") or []
    if destroyed:
        return True
    for item in result.get("objectiveResults") or []:
        if isinstance(item, dict) and item.get("status") in ("complete", "destroyed"):
            return True
    if float(result.get("objectiveDamage") or 0) > 0.15:
        return True
    if result.get("zoneFlipped") or result.get("nodeClaimed"):
        return True
    return False


def apply_reputation_companion(state: Dict[str, Any], result: Dict[str, Any], elapsed: float) -> Dict[str, Any]:
    status = result.get("status", "unknown")
    extraction = result.get("extractionStatus", "")
    rep = state.setdefault("reputation", {})
    comp = state.setdefault("companion", {})
    if "clans" in rep:
        rep["nullmercs"] = clamp((float(rep.pop("clans")) + float(rep.get("nullmercs", 44.0))) / 2.0, 0, 100)
    for key, default in default_v1_state()["reputation"].items():
        rep.setdefault(key, default)
    for key, default in default_v1_state()["companion"].items():
        comp.setdefault(key, default)
    clean_extract = extraction in ("clean", "success") or bool(result.get("cleanExtract"))
    # Credit-table aligned: full victory only for big rep bump; partial is hinge.
    verdict = result.get("verdict") or status
    if verdict in ("victory", "victoryClean") or status == "victory":
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) + 3.0, 0, 100)
        comp["xp"] = clamp(float(comp.get("xp", 0)) + 0.04, 0, 99)
        comp["morale"] = clamp(float(comp.get("morale", 70)) + (4 if clean_extract else 2), 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) - (5 if clean_extract else 1), 0, 100)
    elif verdict in ("partial", "extracted") or status in ("partial", "extracted"):
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) + 1.0, 0, 100)
        comp["xp"] = clamp(float(comp.get("xp", 0)) + 0.015, 0, 99)
        comp["morale"] = clamp(float(comp.get("morale", 70)) + 1, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 1, 0, 100)
    elif verdict in ("defeat", "failed", "failure") or status in ("defeat", "failed", "failure"):
        rep["nullmercs"] = clamp(float(rep.get("nullmercs", 48.0)) - 3.0, 0, 100)
        comp["morale"] = clamp(float(comp.get("morale", 70)) - 5, 0, 100)
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 8 + max(0, elapsed - 20) * 0.1, 0, 100)
    elif verdict == "abandon":
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 3, 0, 100)
    else:
        comp["stress"] = clamp(float(comp.get("stress", 12)) + 2, 0, 100)

    # Explicit plan repDelta (hub / stamp).
    for faction, delta in (result.get("repDelta") or {}).items():
        try:
            rep[str(faction)] = clamp(float(rep.get(faction, 50.0)) + float(delta), 0, 100)
        except (TypeError, ValueError):
            pass

    map_id = str(result.get("mapId") or result.get("map") or "").lower().replace(" ", "_")
    against = str(result.get("against") or result.get("enemyFaction") or "").lower()
    destroyed = _result_destroyed_any(result)
    is_victory = verdict in ("victory", "victoryClean") or status == "victory"
    is_partial = verdict in ("partial", "extracted") or status in ("partial", "extracted")
    is_defeat = verdict in ("defeat", "failed", "failure") or status in ("defeat", "failed", "failure")

    # Cortex crater grudge — blow up their stuff, customers become enemies fast.
    cortex_theater = map_id in CORTEX_CRATER_MAPS or "cortex" in against or against == "cor"
    if cortex_theater and destroyed:
        if is_victory:
            hit = CORTEX_GRUDGE_VICTORY
        elif is_partial:
            hit = CORTEX_GRUDGE_PARTIAL
        elif is_defeat:
            hit = CORTEX_GRUDGE_DEFEAT_DAMAGE
        else:
            hit = CORTEX_GRUDGE_PARTIAL * 0.5
        rep["cortex"] = clamp(float(rep.get("cortex", REP_START_CORTEX)) + hit, 0, 100)

    # Modest Armada cool-off when you raid their eco works.
    if against == "armada" and destroyed and (is_victory or is_partial):
        rep["armada"] = clamp(float(rep.get("armada", REP_START_ARMADA)) + ARMADA_RAID_HIT, 0, 100)

    return {"reputation": rep, "companion": comp}


# Pillar C: commander progression. XP accrues per sortie; each level unlocks one
# perk the compiler/gadget turns into a tangible starting-force bonus.
# Cracked-farm mode stretches the ladder so late-campaign heroes feel absurd.
ROSTER_XP_PER_LEVEL = 80.0
ROSTER_MAX_LEVEL = 8
PERK_LADDER = {
    2: "field_repair",     # extra starting build power
    3: "veteran_cadre",    # the lift carries one more sortie's worth (reserve.lift_cap)
    4: "rapid_deploy",     # one bonus starting unit
    5: "ash_resolve",      # tougher commander
    6: "blood_tempo",      # extra metal/energy on deploy
    7: "named_guard",      # tougher hero HP floor
    8: "cracked_core",     # commander + heroes start highly experienced
}

# Named-hero campaign XP (integer ladder). Never decreases on death — scars and
# status may, but the blood learned stays on the character sheet.
HERO_CAMPAIGN_XP_PER_LEVEL = 100.0
HERO_MAX_LEVEL = 12
# BAR unit experience floors by hero level (engine combat bonuses scale with this).
# Level 1 ~ green, level 6 solid vet, level 12 endgame cracked.
HERO_BAR_XP_PER_LEVEL = 0.35   # was 0.55: level 5 sat at 2.35 XP, close to the veterancy caps
HERO_BAR_XP_BASE = 0.15


def ensure_progression(state: Dict[str, Any]) -> Dict[str, Any]:
    """Operator-facing progression + difficulty dial.

    mode:
      - cracked_farm (default): farm XP, heroes snowball hard, death keeps XP
      - standard: modest gains, still XP-persist-on-death
    difficultyDial: explicit 0.75–1.25 multiplier (clarity over hidden graph).
    xpMultiplier: extra farm rate without touching enemy scale.
    """
    prog = state.setdefault("progression", {})
    if not isinstance(prog, dict):
        prog = {}
        state["progression"] = prog
    prog.setdefault("mode", "cracked_farm")
    prog.setdefault("difficultyDial", 1.0)
    prog.setdefault("xpMultiplier", 1.0)
    prog.setdefault("farmSortiesEnabled", True)
    prog.setdefault("xpPersistOnDeath", True)  # always honored; flag is documentary
    # Soft clamp so bad saves cannot invent absurd dials.
    try:
        prog["difficultyDial"] = float(clamp(float(prog.get("difficultyDial", 1.0)), 0.7, 1.35))
    except (TypeError, ValueError):
        prog["difficultyDial"] = 1.0
    try:
        prog["xpMultiplier"] = float(clamp(float(prog.get("xpMultiplier", 1.0)), 0.5, 3.0))
    except (TypeError, ValueError):
        prog["xpMultiplier"] = 1.0
    if str(prog.get("mode", "")).lower() not in ("cracked_farm", "standard"):
        prog["mode"] = "cracked_farm"
    return prog


def hero_level_from_campaign_xp(campaign_xp: float) -> int:
    return int(min(HERO_MAX_LEVEL, 1 + int(max(0.0, float(campaign_xp or 0.0)) // HERO_CAMPAIGN_XP_PER_LEVEL)))


def bar_unit_xp_from_campaign(campaign_xp: float, peak_bar_xp: float = 0.0) -> float:
    """Map campaign ladder → BAR SetUnitExperience value (power fantasy)."""
    level = hero_level_from_campaign_xp(campaign_xp)
    from_level = HERO_BAR_XP_BASE + (level - 1) * HERO_BAR_XP_PER_LEVEL
    return round(max(float(peak_bar_xp or 0.0), from_level), 4)


def hero_hp_mult_from_level(level: int, critical: bool, wounded: bool) -> float:
    base = 1.45 if critical else 1.35
    scaled = base * (1.0 + max(0, int(level) - 1) * 0.085)
    if wounded:
        scaled *= 0.82
    return round(min(2.75, scaled), 3)


def hero_rank_label(level: int) -> str:
    # L3–L4 used to say "Blooded" — read as wounded. "Proven" is the career rung.
    if level >= 11:
        return "Cracked"
    if level >= 9:
        return "Legend"
    if level >= 7:
        return "Marshal"
    if level >= 5:
        return "Captain"
    if level >= 3:
        return "Proven"
    return "Runner"


def normalize_hero_rank_label(rank: Any) -> str:
    """Map legacy display ranks onto the current ladder."""
    r = str(rank or "").strip()
    if not r:
        return "Runner"
    low = r.lower()
    if low in ("blooded", "bloodied"):
        return "Proven"
    if low == "green":
        return "Runner"
    return r


__all__ = [
    "ARMADA_RAID_HIT",
    "CORTEX_CRATER_MAPS",
    "CORTEX_GRUDGE_DEFEAT_DAMAGE",
    "CORTEX_GRUDGE_PARTIAL",
    "CORTEX_GRUDGE_VICTORY",
    "HERO_BAR_XP_BASE",
    "HERO_BAR_XP_PER_LEVEL",
    "HERO_CAMPAIGN_XP_PER_LEVEL",
    "HERO_MAX_LEVEL",
    "PERK_LADDER",
    "REP_START_ARMADA",
    "REP_START_CORTEX",
    "REP_START_NULLMERCS",
    "ROSTER_MAX_LEVEL",
    "ROSTER_XP_PER_LEVEL",
    "_result_destroyed_any",
    "apply_reputation_companion",
    "bar_unit_xp_from_campaign",
    "ensure_progression",
    "get_character_rank",
    "hero_hp_mult_from_level",
    "hero_level_from_campaign_xp",
    "hero_rank_label",
    "normalize_hero_rank_label",
]
