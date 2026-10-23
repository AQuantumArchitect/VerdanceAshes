"""The hero roster arc: cadre XP, recruitment beats, act rewards, the commander and the roster half of the intent.

Split out of the single-file story engine in pass ten; the public names are re-exported by
``verdance.campaign`` so ``from verdance.campaign import <name>`` keeps working.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from verdance.common import WORKSPACE_ROOT, clamp, load_json, utc_now
from .schema import default_v1_state
from .acts import act_for_mission
from .progression import (
    CADRE_CAP_BASE,
    PERK_LADDER,
    ROSTER_MAX_LEVEL,
    ROSTER_XP_PER_LEVEL,
    bar_unit_xp_from_campaign,
    ensure_progression,
    hero_hp_mult_from_level,
    hero_level_from_campaign_xp,
    hero_rank_label,
    normalize_hero_rank_label,
)
from .sorties import available_allies

def ensure_roster(state: Dict[str, Any]) -> Dict[str, Any]:
    default = default_v1_state()["roster"]
    roster = state.setdefault("roster", copy.deepcopy(default))
    commander = roster.setdefault("commander", {})
    for key, value in default["commander"].items():
        commander.setdefault(key, copy.deepcopy(value))
    roster.setdefault("cadre", {})
    roster.setdefault("cadreCap", CADRE_CAP_BASE)
    roster.setdefault("cadreXp", {})
    heroes = roster.setdefault("heroes", [])
    known = {str(h.get("heroId")) for h in heroes if isinstance(h, dict)}
    for hero in default["heroes"]:
        if hero["heroId"] not in known:
            heroes.append(copy.deepcopy(hero))
            known.add(str(hero["heroId"]))
    # Drop 3 Wave 2: authored roster heroes join locked; recruitment beats
    # (apply_recruitment_beats) unlock them when their moment lands.
    authored_rows = [h for h in load_hero_roster() if isinstance(h, dict) and h.get("heroId")]
    authored = {str(h.get("heroId")): h for h in authored_rows}
    for hero in authored_rows:
        hid = str(hero.get("heroId"))
        if hid and hid not in known:
            rec = copy.deepcopy(hero)
            rec.setdefault("status", "locked")
            heroes.append(rec)
            known.add(hid)
    # Drop scrapped locked heroes that left the authored catalog (e.g. mirren).
    # Keep anyone still active / wounded / dead on the company roll.
    if authored:
        kept = []
        for hero in heroes:
            if not isinstance(hero, dict):
                continue
            hid = str(hero.get("heroId") or "")
            st = str(hero.get("status") or "").lower()
            if hid in authored or st in ("active", "wounded", "dead", "lost"):
                kept.append(hero)
        heroes[:] = kept
        known = {str(h.get("heroId")) for h in heroes if isinstance(h, dict)}
    # Seed campaignXp from any existing character sheet (legacy integer XP).
    # Also refresh display names / chassis from the authored catalog so the
    # webGUI never keeps leftovers like "Grath Unpaid".
    chars = state.get("characters") or {}
    for hero in heroes:
        if not isinstance(hero, dict):
            continue
        for key, value in {"status": "active", "xp": 0.0, "campaignXp": 0.0,
                           "timesWounded": 0, "missionCritical": False,
                           "peakBarXp": 0.0}.items():
            hero.setdefault(key, value)
        hid = str(hero.get("heroId") or "")
        # You (the first company pick) are mission-critical for the whole campaign.
        if hid and hid == str((state.get("company") or {}).get("you") or ""):
            hero["missionCritical"] = True
            hero["you"] = True
        src = authored.get(hid)
        if isinstance(src, dict):
            if src.get("name"):
                hero["name"] = src["name"]
            if src.get("unitDef"):
                hero["unitDef"] = src["unitDef"]
            if src.get("fiction") and not hero.get("fiction"):
                hero["fiction"] = src.get("fiction")
        c = chars.get(hid) if isinstance(chars, dict) else None
        if isinstance(c, dict):
            if isinstance(src, dict) and src.get("name"):
                c["name"] = src["name"]
            if isinstance(src, dict) and src.get("unitDef"):
                c["unitDef"] = src["unitDef"]
            if float(hero.get("campaignXp") or 0) <= 0:
                # Character sheet used big integers (e.g. 1480); scale into ladder.
                sheet = float(c.get("xp") or 0)
                if sheet >= 50:
                    hero["campaignXp"] = round(sheet * 0.08, 2)  # 1480 → ~118 (L2)
                elif sheet > 0:
                    hero["campaignXp"] = sheet
        # Floor BAR xp from campaign ladder so new saves feel proven, not empty.
        camp = float(hero.get("campaignXp") or 0.0)
        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        hero["peakBarXp"] = peak
        hero["xp"] = bar_unit_xp_from_campaign(camp, peak)
        hero["level"] = hero_level_from_campaign_xp(camp)
        hero["rank"] = normalize_hero_rank_label(hero_rank_label(int(hero["level"])))
    # Soft auto-unlock: high Null Merc rep can free Spoke without broker coins
    # (broker listing still works; this is the reputation path).
    maybe_unlock_wheelie_hero(state)
    ensure_progression(state)
    return roster


def roster_level_for_xp(xp: float) -> int:
    return int(min(ROSTER_MAX_LEVEL, 1 + int(max(0.0, xp) // ROSTER_XP_PER_LEVEL)))


def commander_cadre_cap(commander: Dict[str, Any]) -> int:
    cap = CADRE_CAP_BASE
    if "veteran_cadre" in (commander.get("perks") or []):
        cap += 6
    return cap


def expire_scars(commander: Dict[str, Any], mission_number: int) -> None:
    kept = []
    for scar in commander.get("scars", []) or []:
        if int(scar.get("untilMission", 0)) > mission_number:
            kept.append(scar)
    commander["scars"] = kept


def _sortie_xp_gains(state: Dict[str, Any], result: Dict[str, Any], success: bool, clean: bool) -> Dict[str, float]:
    """Commander + hero campaign XP for this sortie (mode-aware, farm-boosted)."""
    prog = ensure_progression(state)
    cracked = str(prog.get("mode", "cracked_farm")).lower() == "cracked_farm"
    mult = float(prog.get("xpMultiplier", 1.0) or 1.0)
    farm = bool(result.get("farmSortie")) or "farm" in (result.get("storyTags") or [])
    # Base gains: cracked_farm is generous so end-of-campaign heroes are monsters.
    if success:
        cmd = 52.0 + (12.0 if clean else 0.0)
        hero = 70.0 if cracked else 38.0
        if clean:
            hero += 12.0
    elif result.get("status") in ("defeat", "failed", "failure"):
        cmd = 14.0 if cracked else 8.0
        hero = 28.0 if cracked else 12.0  # death still teaches; XP never wiped
    else:
        cmd = 22.0 if cracked else 16.0
        hero = 40.0 if cracked else 20.0
    if farm:
        hero *= 1.85
        cmd *= 1.35
    return {
        "commander": round(cmd * mult, 2),
        "hero": round(hero * mult, 2),
    }


def update_roster(state: Dict[str, Any], result: Dict[str, Any], success: bool, clean: bool) -> Dict[str, Any]:
    """Grow the warband from survivors, level the commander, scar it on defeat.
    Backward-compatible: a result without playerSurvivors leaves the cadre as-is.

    XP rule (operator request 2026-07): campaign XP and peak BAR experience
    NEVER reset on death. Death/wound changes status only; the ladder stays.
    """
    roster = ensure_roster(state)
    commander = roster["commander"]
    status = result.get("status", "unknown")
    defeat = status in ("defeat", "failed", "failure")
    gains = _sortie_xp_gains(state, result, success, clean)

    # The command ledger grows only while the walker is on the field.
    if commander.get("unlocked") is True:
        commander["xp"] = round(float(commander.get("xp", 0.0) or 0.0) + gains["commander"], 2)
        new_level = roster_level_for_xp(commander["xp"])
        if new_level > int(commander.get("level", 1)):
            for lvl in range(int(commander.get("level", 1)) + 1, new_level + 1):
                perk = PERK_LADDER.get(lvl)
                if perk and perk not in commander.setdefault("perks", []):
                    commander["perks"].append(perk)
            commander["level"] = new_level
    # Cap = perk base + act-2 grant bonus (earned specials never squeeze T1 vets).
    roster["cadreCap"] = commander_cadre_cap(commander) + grant_cap_bonus(roster)

    # Cadre: survivors carry; a defeat routs most of them.
    survivors = result.get("playerSurvivors")
    if isinstance(survivors, dict) and survivors:
        keep_fraction = 0.4 if defeat else 1.0
        carried: Dict[str, int] = {}
        for unit_def, count in survivors.items():
            kept = int(math.floor(float(count) * keep_fraction))
            if kept > 0:
                carried[str(unit_def)] = kept
        roster["cadre"] = trim_cadre(carried, roster["cadreCap"])
    elif defeat and roster.get("cadre"):
        # No survivor report but a defeat: rout the carried cadre by 40%.
        routed = {d: int(math.floor(c * 0.6)) for d, c in roster["cadre"].items()}
        roster["cadre"] = {d: c for d, c in routed.items() if c > 0}

    # Veteran XP bank by unitDef — majority retain between drops.
    # Named heroes already track peakBarXp; this covers packs / escorts / cadre.
    _merge_cadre_xp(roster, result, defeat=defeat)

    # Scars: a lost commander limps into the next sortie (perks suppressed then).
    expire_scars(commander, int(state.get("missionNumber", 1)))
    if defeat:
        commander.setdefault("scars", []).append({
            "kind": "wounded",
            "sinceMission": int(state.get("missionNumber", 1)),
            "untilMission": int(state.get("missionNumber", 1)) + 1,
        })

    # Named heroes: Fire Emblem status from gadget heroResults / namedOutcomes.
    # WO-008: dead means dead (status), but XP is permanent.
    for hero in roster.get("heroes", []) or []:
        if isinstance(hero, dict) and hero.get("status") == "wounded":
            hero["status"] = "active"

    hero_results = result.get("heroResults") if isinstance(result.get("heroResults"), dict) else {}
    named_outcomes = result.get("namedOutcomes")
    by_named = {}
    if isinstance(named_outcomes, list) and named_outcomes:
        by_named = {str(o.get("charId")): o for o in named_outcomes if isinstance(o, dict)}

    for hero in roster.get("heroes", []) or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        # --- status from named outcomes or heroResults ---
        if hid in by_named:
            res = str(by_named[hid].get("outcome", ""))
            if res == "dead":
                hero["status"] = "dead"
            elif res == "recovered":
                # went down, was rezzed, came home: in good health (the rescue is story, not a wound)
                hero["status"] = "active"
            elif res == "wounded":
                hero["status"] = "wounded"
                hero["timesWounded"] = int(hero.get("timesWounded", 0) or 0) + 1
            elif res == "survived":
                hero["status"] = "active"
        elif hid in hero_results:
            hr = hero_results[hid]
            if isinstance(hr, dict):
                hr_status = str(hr.get("status", ""))
                if hr_status == "dead":
                    hero["status"] = "dead"
                elif hr_status == "wounded":
                    hero["status"] = "wounded"
                    hero["timesWounded"] = int(hero.get("timesWounded", 0) or 0) + 1
                elif hr_status == "survived":
                    hero["status"] = "active"

        # --- XP: always grow for heroes that appeared in the result; never drop ---
        deployed = hid in by_named or hid in hero_results or not (by_named or hero_results)
        camp_gain = 0.0
        if deployed:
            prev_camp = float(hero.get("campaignXp") or 0.0)
            # Survivors/wounded get full gain; dead still bank a partial (they fought).
            if hero.get("status") == "dead":
                camp_gain = gains["hero"] * 0.65
            elif hero.get("status") == "wounded":
                camp_gain = gains["hero"] * 0.9
            else:
                camp_gain = gains["hero"]
            hero["campaignXp"] = round(prev_camp + camp_gain, 2)

        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        hr = hero_results.get(hid) if isinstance(hero_results.get(hid), dict) else None
        if hr is not None and hr.get("xp") is not None:
            try:
                peak = max(peak, float(hr.get("xp") or 0.0))
            except (TypeError, ValueError):
                pass
        hero["peakBarXp"] = peak
        # Floor BAR combat XP from campaign ladder (cracked heroes by late game).
        hero["xp"] = bar_unit_xp_from_campaign(float(hero.get("campaignXp") or 0.0), peak)
        hero["level"] = hero_level_from_campaign_xp(float(hero.get("campaignXp") or 0.0))
        hero["rank"] = normalize_hero_rank_label(hero_rank_label(int(hero["level"])))
        # Last sortie XP readout for debrief clarity.
        hero["lastSortieXpGain"] = round(camp_gain, 2)

    # Legacy saves: "Blooded" read as wounded — coerce on every homecoming.
    for hero in roster.get("heroes", []) or []:
        if isinstance(hero, dict) and hero.get("rank") is not None:
            hero["rank"] = normalize_hero_rank_label(hero.get("rank"))

    return roster


# Majority retain: packs / escorts keep most of their field XP across drops.
# Heroes already use peakBarXp (100%); cadre uses this keep fraction.
CADRE_XP_KEEP_FRAC = 0.85
CADRE_XP_DEFEAT_FRAC = 0.55


def _merge_cadre_xp(roster: Dict[str, Any], result: Dict[str, Any], *, defeat: bool = False) -> None:
    """Bank per-def combat + craft XP from the match into roster.cadreXp.

    Shape: { unitDef: { xp, craftXp, peakXp, peakCraftXp } }
    xp / craftXp are the *seed* values for the next drop (majority retain).
    """
    detail = result.get("playerSurvivorXp")
    if not isinstance(detail, dict) or not detail:
        return
    keep = CADRE_XP_DEFEAT_FRAC if defeat else CADRE_XP_KEEP_FRAC
    bank = roster.setdefault("cadreXp", {})
    if not isinstance(bank, dict):
        bank = {}
        roster["cadreXp"] = bank
    for unit_def, bag in detail.items():
        if not isinstance(bag, dict):
            continue
        def_name = str(unit_def)
        try:
            peak = float(bag.get("peakXp") or 0.0)
            avg = float(bag.get("avgXp") or 0.0)
            peak_craft = float(bag.get("peakCraftXp") or 0.0)
            avg_craft = float(bag.get("avgCraftXp") or 0.0)
        except (TypeError, ValueError):
            continue
        # Seed from avg (majority of the company), never below prior bank,
        # never above peak. Keep fraction applied to the new field reading.
        field_seed = max(avg, peak * 0.75) * keep
        field_craft = max(avg_craft, peak_craft * 0.75) * keep
        prev = bank.get(def_name) if isinstance(bank.get(def_name), dict) else {}
        prev_xp = float(prev.get("xp") or 0.0)
        prev_craft = float(prev.get("craftXp") or 0.0)
        prev_peak = float(prev.get("peakXp") or 0.0)
        prev_peak_craft = float(prev.get("peakCraftXp") or 0.0)
        bank[def_name] = {
            "xp": round(max(prev_xp * 0.5, field_seed), 4),
            "craftXp": round(max(prev_craft * 0.5, field_craft), 4),
            "peakXp": round(max(prev_peak, peak), 4),
            "peakCraftXp": round(max(prev_peak_craft, peak_craft), 4),
            "avgXp": round(avg, 4),
            "avgCraftXp": round(avg_craft, 4),
        }


def trim_cadre(cadre: Dict[str, int], cap: int) -> Dict[str, int]:
    total = sum(cadre.values())
    if total <= cap:
        return {d: int(c) for d, c in cadre.items() if c > 0}
    # Proportionally scale down to the cap; deterministic order by unit def.
    scale = cap / float(total)
    trimmed: Dict[str, int] = {}
    for unit_def in sorted(cadre):
        kept = int(math.floor(cadre[unit_def] * scale))
        if kept > 0:
            trimmed[unit_def] = kept
    return trimmed


def commander_active_perks(commander: Dict[str, Any]) -> List[str]:
    """Perks in effect this mission — suppressed while the commander is scarred."""
    if commander.get("scars"):
        return []
    return list(commander.get("perks", []) or [])


# ---------------------------------------------------------------------------
# Drop 3 Wave 2: the hero roster arc.
#   - data/story/hero_roster.json ships the authored named heroes, locked.
#   - Recruitment beats unlock them when their moment lands (mission victory,
#     objective kind, reputation, act reached) — the Spoke pattern generalized.
#   - Act-2 victories grant earned T2/T3 units into the cadre: the mechanical
#     heart of "your veterans ARE your tech".
# ---------------------------------------------------------------------------

_HERO_ROSTER_CACHE: Dict[str, List[Dict[str, Any]]] = {}


def load_hero_roster(workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Authored named-hero roster. Heroes ship status=locked with a `recruit`
    spec; apply_recruitment_beats activates them mid-campaign."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "story" / "hero_roster.json")
    here = WORKSPACE_ROOT
    paths.append(here / "data" / "story" / "hero_roster.json")
    for path in paths:
        key = str(path)
        if key in _HERO_ROSTER_CACHE:
            return _HERO_ROSTER_CACHE[key]
        if path.exists():
            try:
                data = load_json(path)
                heroes = data.get("heroes") if isinstance(data, dict) else None
                if isinstance(heroes, list):
                    out = [h for h in heroes if isinstance(h, dict) and h.get("heroId")]
                    _HERO_ROSTER_CACHE[key] = out
                    return out
            except Exception:
                pass
    return []


def apply_recruitment_beats(
    state: Dict[str, Any],
    result: Dict[str, Any],
    full_success: bool,
    completed_mission: int,
) -> List[Dict[str, Any]]:
    """Unlock authored heroes whose recruitment moment just landed.

    Runs once per processed result (duplicates are filtered upstream by the
    resultKey ledger). Returns the join records for debrief/report surfacing
    and stamps state.recentHeroJoins so the NEXT briefing can nod at them.
    """
    roster = state.get("roster") or {}
    rep = state.get("reputation") or {}
    obj_kind = str(
        result.get("objectiveArchetype")
        or ((result.get("objectiveTarget") or {}).get("kind")
            if isinstance(result.get("objectiveTarget"), dict) else "")
        or ""
    )
    joined: List[Dict[str, Any]] = []
    for hero in roster.get("heroes") or []:
        if not isinstance(hero, dict) or str(hero.get("status")) != "locked":
            continue
        spec = hero.get("recruit")
        if not isinstance(spec, dict):
            continue
        kind = str(spec.get("type") or "")
        met = False
        if kind == "mission_victory":
            met = full_success and completed_mission >= int(spec.get("mission") or 1)
        elif kind == "objective_kind":
            kinds = [str(k) for k in (spec.get("kinds") or ([spec.get("kind")] if spec.get("kind") else []))]
            met = full_success and obj_kind in kinds
            if met and spec.get("act"):
                met = act_for_mission(completed_mission) == int(spec["act"])
        elif kind == "rep":
            met = float(rep.get(str(spec.get("faction") or ""), 0) or 0) >= float(spec.get("min") or 0)
        elif kind == "act_reached":
            met = act_for_mission(int(state.get("missionNumber", 1) or 1)) >= int(spec.get("act") or 1)
        if not met:
            continue
        hero["status"] = "active"
        hero["joinedAtMission"] = int(completed_mission)
        hid = str(hero.get("heroId") or "")
        name = str(hero.get("name") or hid.title())
        joined.append({"heroId": hid, "name": name, "unitDef": str(hero.get("unitDef") or "")})
        # Character sheet: existing world characters (Grath, Halq) flip to
        # player=True; fresh recruits get a new sheet.
        chars = state.setdefault("characters", {})
        sheet = chars.get(hid)
        if isinstance(sheet, dict):
            sheet["player"] = True
            if sheet.get("status") != "dead":
                sheet["status"] = "active"
        else:
            chars[hid] = {
                "id": hid, "name": name, "faction": "ashwalkers",
                "unitDef": str(hero.get("unitDef") or ""), "xp": 0,
                "player": True, "home": None, "status": "active",
                "wounds": 0, "scars": [],
            }
    if joined:
        state["recentHeroJoins"] = {
            "missionNumber": int(state.get("missionNumber", 1) or 1),
            "heroIds": [j["heroId"] for j in joined],
            "names": [j["name"] for j in joined],
        }
    return joined


# Act-2 earned specials: victory grants keyed by the mission just won. Verified
# Legion defs only. Grants land in roster.cadre (they persist, fight, and die
# through the normal survivor pipeline) and are ledgered in roster.grants.
ACT2_REWARD_TABLE = {
    6: {"units": {"legshot": 2}, "label": "Riot walkers — a brace of Ephyras"},
    7: {"units": {"legamph": 2}, "label": "Amphibious heat-ray pair for the crossings"},
    8: {"units": {"legbart": 2}, "label": "Napalm barrage engines — the ash spreads"},
    9: {"units": {"leginc": 2}, "label": "Sustained heat-ray pair — the kiln walks"},
    10: {"units": {"legkeres": 1}, "label": "A Keres. The finale wants an answer."},
}
GRANT_CAP_BONUS_MAX = 8


def grant_cap_bonus(roster: Dict[str, Any]) -> int:
    """Granted specials travel as cadre; each raises the cadre cap so rewards
    never squeeze out the T1 veterans (bonus clamped)."""
    total = 0
    for g in roster.get("grants") or []:
        if isinstance(g, dict):
            total += sum(int(c or 0) for c in (g.get("units") or {}).values())
    return min(GRANT_CAP_BONUS_MAX, total)


def apply_act_rewards(
    state: Dict[str, Any], completed_mission: int, full_success: bool
) -> Optional[Dict[str, Any]]:
    """Grant the act-2 earned-tech reward for a full-success mission."""
    if not full_success or act_for_mission(completed_mission) != 2:
        return None
    reward = ACT2_REWARD_TABLE.get(int(completed_mission))
    if not reward:
        return None
    roster = ensure_roster(state)
    grants = roster.setdefault("grants", [])
    for g in grants:
        if isinstance(g, dict) and int(g.get("mission", -1)) == int(completed_mission):
            return None  # belt + braces on top of the resultKey ledger
    cadre = roster.setdefault("cadre", {})
    for unit_def, count in reward["units"].items():
        cadre[unit_def] = int(cadre.get(unit_def, 0) or 0) + int(count)
    rec = {
        "mission": int(completed_mission),
        "units": dict(reward["units"]),
        "label": reward["label"],
        "at": utc_now(),
    }
    grants.append(rec)
    roster["cadreCap"] = commander_cadre_cap(roster.get("commander") or {}) + grant_cap_bonus(roster)
    return rec


def merc_foothold_scale(reputation: float) -> float:
    """How much Null Merc presence stands with you, scaled by standing. Allied
    lines (>=40) field a fuller foothold; wary lines show up thin."""
    if reputation >= 40.0:
        return round(clamp(0.85 + (reputation - 40.0) / 60.0 * 0.5, 0.85, 1.35), 3)
    # Wary lines stay strictly below the allied floor: alliance is a clean step up.
    return round(clamp(0.55 + reputation / 40.0 * 0.25, 0.55, 0.8), 3)


WHEELIE_HERO_REP_UNLOCK = 55.0  # Null Merc standing to auto-sign Spoke


def maybe_unlock_wheelie_hero(state: Dict[str, Any]) -> bool:
    """Unlock Spoke (wheelie mentor) when Null Merc rep is high enough.

    Not a default ace — scout tech specialist whose trait banks XP from
    every Wheelie (legscout) that dies and stamps that floor on new mints.
    """
    rep = float((state.get("reputation") or {}).get("nullmercs") or 0)
    if rep < WHEELIE_HERO_REP_UNLOCK:
        return False
    roster = state.setdefault("roster", {})
    heroes = roster.setdefault("heroes", [])
    for h in heroes:
        if isinstance(h, dict) and str(h.get("heroId")) == "spoke":
            if str(h.get("status")) == "locked":
                h["status"] = "active"
                return True
            return False
    heroes.append({
        "heroId": "spoke",
        "name": "Spoke",
        "unitDef": "legscout",
        "missionCritical": False,
        "status": "active",
        "xp": 0.15,
        "timesWounded": 0,
        "campaignXp": 0.0,
        "peakBarXp": 0.15,
        "level": 1,
        "rank": "Runner",
        "trait": "wheelie_mentor",
        "traits": ["wheelie_mentor", "scout_tech"],
        "unlock": {"path": "nullmercs_rep", "repMin": WHEELIE_HERO_REP_UNLOCK},
    })
    chars = state.setdefault("characters", {})
    chars.setdefault("spoke", {
        "id": "spoke",
        "name": "Spoke",
        "faction": "nullmercs",
        "unitDef": "legscout",
        "xp": 0,
        "player": True,
        "home": None,
        "status": "active",
        "wounds": 0,
        "scars": [],
    })
    return True


def _away_from_camp(state: Dict[str, Any]) -> set:
    """Heroes the camp clock has posted to a zone or who are in transit do not board the Drop
    (pass two: physical locations are real). Recall them first (camp action) to field them."""
    out = set()
    people = ((state.get("camp") or {}).get("people") or {})
    for hid, rec in people.items():
        if isinstance(rec, dict) and rec.get("where") in ("posted", "transit", "field"):
            out.add(str(hid))
    return out


def hero_intent_entries(roster: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The named heroes who deploy this mission: everyone not dead. Wounded
    heroes field at reduced toughness so last sortie's cost is felt.
    Cracked-farm levels scale HP + BAR experience so late heroes feel broken."""
    entries = []
    for hero in roster.get("heroes", []) or []:
        if not isinstance(hero, dict):
            continue
        st = str(hero.get("status") or "active")
        if st in ("dead", "locked"):
            continue
        wounded = st == "wounded"
        camp = float(hero.get("campaignXp") or 0.0)
        level = int(hero.get("level") or hero_level_from_campaign_xp(camp))
        critical = bool(hero.get("missionCritical"))
        peak = max(float(hero.get("peakBarXp") or 0.0), float(hero.get("xp") or 0.0))
        bar_xp = bar_unit_xp_from_campaign(camp, peak)
        trait = str(hero.get("trait") or "")
        traits = list(hero.get("traits") or [])
        if trait and trait not in traits:
            traits.append(trait)
        entries.append({
            "heroId": str(hero.get("heroId")),
            "name": str(hero.get("name", hero.get("heroId"))),
            "unitDef": str(hero.get("unitDef", "legcen")),
            "missionCritical": critical,
            "wounded": wounded,
            "level": level,
            "rank": normalize_hero_rank_label(hero.get("rank") or hero_rank_label(level)),
            "campaignXp": round(camp, 2),
            "hpMult": hero_hp_mult_from_level(level, critical, wounded),
            "xp": bar_xp,
            "trait": trait or None,
            "traits": traits,
        })
    return entries


def commander_is_unlocked(state: Dict[str, Any]) -> bool:
    """The walker fields only when a story beat has set this. Level does not count."""
    roster = state.get("roster") if isinstance(state, dict) else None
    commander = roster.get("commander") if isinstance(roster, dict) else None
    return isinstance(commander, dict) and commander.get("unlocked") is True


def grant_commander(state: Dict[str, Any], reason: str) -> bool:
    """Story grant. Idempotent. Mission number is not a reason."""
    commander = ensure_roster(state)["commander"]
    if commander.get("unlocked") is True:
        return False
    commander["unlocked"] = True
    commander["unlockedBy"] = str(reason or "story")[:80]
    commander["unlockedAt"] = utc_now()
    return True


def scrap_commander(state: Dict[str, Any], reason: str) -> bool:
    """The walker is scrap again. Level and perks stay on the ledger."""
    commander = ensure_roster(state)["commander"]
    if commander.get("unlocked") is not True:
        return False
    commander["unlocked"] = False
    commander["scrappedBy"] = str(reason or "lost")[:80]
    commander["scrappedAt"] = utc_now()
    return True


def load_commander_beats(workspace: Optional[Path] = None) -> List[Dict[str, Any]]:
    """data/story/commander_unlock.json beats. The examples key is not loaded."""
    paths: List[Path] = []
    if workspace is not None:
        paths.append(Path(workspace) / "data" / "story" / "commander_unlock.json")
    paths.append(WORKSPACE_ROOT / "data" / "story" / "commander_unlock.json")
    for path in paths:
        if not path.exists():
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        beats = data.get("beats") if isinstance(data, dict) else None
        if isinstance(beats, list):
            return [b for b in beats if isinstance(b, dict) and b.get("when")]
    return []


def _commander_beat_met(beat: Dict[str, Any], state: Dict[str, Any], result: Dict[str, Any], joined_ids: set) -> bool:
    kind = str(beat.get("when") or "")
    if kind == "hero_joined":
        return str(beat.get("heroId") or "") in joined_ids
    if kind == "story_tag":
        want = str(beat.get("tag") or "")
        tags = [str(t) for t in (result.get("storyTags") or [])]
        sortie = result.get("sortie") if isinstance(result.get("sortie"), dict) else {}
        tags.extend(str(t) for t in (sortie.get("storyTags") or []))
        return bool(want) and want in tags
    if kind == "flag":
        flags = state.get("flags") if isinstance(state.get("flags"), dict) else {}
        return bool(flags.get(str(beat.get("flag") or "")))
    return False


def apply_commander_story(
    state: Dict[str, Any],
    result: Dict[str, Any],
    joined: Optional[List[Any]] = None,
    workspace: Optional[Path] = None,
) -> Dict[str, Any]:
    """Field or scrap the command walker from the story, never from the sortie clock.

    A loss scraps it and does not also grant on that same result. While it is
    scrap, a result tag, a hero with grantsCommander, or a beat in
    data/story/commander_unlock.json can rebuild it.
    """
    result = result if isinstance(result, dict) else {}
    reason = str(result.get("terminalReason") or "")
    if reason == "commander_lost":
        if scrap_commander(state, "commander_lost"):
            return {"event": "scrapped", "reason": "commander_lost"}
        return {"event": "scrap", "reason": "commander_lost"}
    if commander_is_unlocked(state):
        return {"event": "fielded"}
    tags = [str(t) for t in (result.get("storyTags") or [])]
    sortie = result.get("sortie") if isinstance(result.get("sortie"), dict) else {}
    tags.extend(str(t) for t in (sortie.get("storyTags") or []))
    if result.get("unlockCommander") is True or "commander_unlocked" in tags:
        grant_commander(state, "result")
        return {"event": "unlocked", "reason": "result"}
    joined_ids: set = set()
    for item in joined or []:
        if isinstance(item, dict) and item.get("heroId"):
            joined_ids.add(str(item["heroId"]))
        elif isinstance(item, str) and item:
            joined_ids.add(item)
    roster = ensure_roster(state)
    for hero in roster.get("heroes") or []:
        if not isinstance(hero, dict):
            continue
        hid = str(hero.get("heroId") or "")
        if hid in joined_ids and hero.get("grantsCommander") is True:
            grant_commander(state, "hero:" + hid)
            return {"event": "unlocked", "reason": "hero:" + hid}
    for beat in load_commander_beats(workspace):
        if _commander_beat_met(beat, state, result, joined_ids):
            why = str(beat.get("id") or beat.get("when") or "beat")
            grant_commander(state, why)
            return {"event": "unlocked", "reason": why}
    return {"event": "scrap"}


def build_roster_intent(state: Dict[str, Any]) -> Dict[str, Any]:
    roster = ensure_roster(state)
    commander = roster["commander"]
    prog = ensure_progression(state)
    return {
        "commander": {
            "name": commander.get("name"),
            "unitDef": commander.get("unitDef", "legcom"),
            "level": int(commander.get("level", 1)),
            "xp": round(float(commander.get("xp", 0.0) or 0.0), 1),
            "perks": list(commander.get("perks", []) or []),
            "activePerks": commander_active_perks(commander),
            "scarred": bool(commander.get("scars")),
            "unlocked": commander.get("unlocked") is True,
        },
        "cadre": {str(d): int(c) for d, c in (roster.get("cadre") or {}).items() if c},
        "cadreCap": int(roster.get("cadreCap", CADRE_CAP_BASE)),
        "cadreXp": {
            str(d): {
                "xp": round(float((bag or {}).get("xp") or 0.0), 4),
                "craftXp": round(float((bag or {}).get("craftXp") or 0.0), 4),
                "peakXp": round(float((bag or {}).get("peakXp") or 0.0), 4),
                "peakCraftXp": round(float((bag or {}).get("peakCraftXp") or 0.0), 4),
                "avgXp": round(float((bag or {}).get("avgXp") or 0.0), 4),
                "avgCraftXp": round(float((bag or {}).get("avgCraftXp") or 0.0), 4),
            }
            for d, bag in (roster.get("cadreXp") or {}).items()
            if isinstance(bag, dict) and (
                float(bag.get("xp") or 0) > 0
                or float(bag.get("craftXp") or 0) > 0
                or float(bag.get("peakXp") or 0) > 0
            )
        },
        "heroes": [h for h in hero_intent_entries(roster) if h.get("heroId") not in _away_from_camp(state)],
        "awayFromCamp": sorted(_away_from_camp(state)),
        "availableAllies": available_allies(state),
        "progression": {
            "mode": prog.get("mode"),
            "difficultyDial": prog.get("difficultyDial"),
            "xpMultiplier": prog.get("xpMultiplier"),
            "farmSortiesEnabled": bool(prog.get("farmSortiesEnabled")),
            "xpPersistOnDeath": True,
        },
    }


__all__ = [
    "ACT2_REWARD_TABLE",
    "CADRE_XP_DEFEAT_FRAC",
    "CADRE_XP_KEEP_FRAC",
    "GRANT_CAP_BONUS_MAX",
    "WHEELIE_HERO_REP_UNLOCK",
    "_HERO_ROSTER_CACHE",
    "_away_from_camp",
    "_commander_beat_met",
    "_merge_cadre_xp",
    "_sortie_xp_gains",
    "apply_act_rewards",
    "apply_commander_story",
    "apply_recruitment_beats",
    "build_roster_intent",
    "commander_active_perks",
    "commander_cadre_cap",
    "commander_is_unlocked",
    "ensure_roster",
    "expire_scars",
    "grant_cap_bonus",
    "grant_commander",
    "hero_intent_entries",
    "load_commander_beats",
    "load_hero_roster",
    "maybe_unlock_wheelie_hero",
    "merc_foothold_scale",
    "roster_level_for_xp",
    "scrap_commander",
    "trim_cadre",
    "update_roster",
]
