"""Rule-based offline brain — maps mood snapshot → discrete combat action.

This is the default proxy when Grok is unavailable or when we want
deterministic iteration. LLM brain may override with the same action vocab.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mood import MoodSnapshot

ACTIONS = (
    # combat / strike
    "PUSH_OBJECTIVE",
    "PROBE",
    "FLANK",
    "HOLD_AND_HEAL",
    "RALLY",
    "FALLBACK",
    "EXTRACT",
    "WAIT",
    # eco / expand (arcs 2–3 + normal BAR brain)
    "BUILD_MEX",
    "BUILD_ENERGY",
    "BUILD_CON",
    "EXPAND_FRONT",
    "RECLAIM",
    "TECH_UP",
    "DEFEND_BASE",
)

# Mission kinds that expect eco vocabulary
ECO_KINDS = frozenset({"eco_expand", "siege", "multipressure"})
SURVIVE_KINDS = frozenset({"survive_wilds"})
HOLD_KINDS = frozenset({"seize_lane", "hold_plateau"})


@dataclass
class Decision:
    action: str
    reason: str
    source: str = "policy"  # policy | llm | hybrid
    confidence: float = 0.6
    extras: dict | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "source": self.source,
            "confidence": self.confidence,
            "extras": self.extras or {},
        }


def decide(
    mood: MoodSnapshot,
    *,
    mission_kind: str = "eco_raid",
    recent: list[str] | None = None,
    allow_eco: bool = False,
    eco_bands: dict[str, str] | None = None,
    no_metal_map: bool = False,
    width_band: str | None = None,
) -> Decision:
    """Pick one action from mood + mission archetype.

    Arc 1 strike: approach → objective → extract (no base).
    Arc 2–3: may allow eco actions when allow_eco and eco is dry.
    """
    recent = recent or []
    eco_bands = eco_bands or {}
    s = mood.signed()
    agg = s["aggression"]
    caut = s["caution"]
    foc = s["focus"]
    press = s["pressure"]
    coh = s["cohesion"]
    mom = s["momentum"]

    obj = mood.objective
    thr = mood.threat
    clk = mood.clock
    adv = mood.advantage
    p_str = mood.player_strength
    heroes = min(mood.hero_vane_alive, mood.hero_ketha_alive)

    # Stall detectors from recent tape (anti-FLANK-death-spiral)
    tail = recent[-12:]
    flank_run = sum(1 for a in tail if a == "FLANK")
    probe_run = sum(1 for a in tail if a == "PROBE")
    build_run = sum(
        1
        for a in tail
        if a in ("BUILD_MEX", "BUILD_ENERGY", "BUILD_CON", "TECH_UP", "EXPAND_FRONT")
    )
    no_push = sum(1 for a in tail if a not in ("PUSH_OBJECTIVE", "EXTRACT"))
    stuck = len(tail) >= 8 and obj < 0.35 and flank_run + probe_run >= 6

    # Terminal: objective done → extract
    if obj >= 0.93 or mood.progress >= 0.93:
        return Decision("EXTRACT", "objective complete — get out", confidence=0.9)

    # Nearly done: finish
    if 0.75 <= max(obj, mood.progress) < 0.93:
        if thr > 0.7 and heroes < 0.55:
            return Decision("HOLD_AND_HEAL", "nearly done but bleeding — patch then finish", confidence=0.8)
        if mission_kind in ECO_KINDS and eco_bands.get("eco") in ("dry", "thin") and build_run < 3:
            return Decision("BUILD_ENERGY", "nearly done but eco dry — top up then finish", confidence=0.72)
        return Decision("PUSH_OBJECTIVE", "nearly complete — finish the objective", confidence=0.85)

    # Force melted / heroes critical — survival first
    if p_str < 0.28 or adv < 0.28:
        if thr > 0.45:
            return Decision("FALLBACK", "force melted — break contact", confidence=0.88)
        return Decision("HOLD_AND_HEAL", "force thin — reconstitute", confidence=0.82)

    if heroes < 0.35:
        return Decision("FALLBACK", "heroes critical — break contact", confidence=0.85)

    if heroes < 0.55 and thr > 0.55:
        return Decision("HOLD_AND_HEAL", "heroes hurt under fire — stabilize", confidence=0.8)

    # Survive wilds: cohesion and heal bias
    if mission_kind in SURVIVE_KINDS:
        if coh < -0.1 or thr > 0.55:
            return Decision("RALLY", "wilds — keep the knot tight", confidence=0.8)
        if p_str < 0.5:
            return Decision("HOLD_AND_HEAL", "wilds attrition — reconstitute", confidence=0.78)
        if obj < 0.3 and probe_run < 3:
            return Decision("PROBE", "wild corridor — probe the choke", confidence=0.7)
        if thr > 0.45 and flank_run < 3:
            return Decision("FLANK", "wilds contact — refuse the ambush lane", confidence=0.7)
        return Decision("PUSH_OBJECTIVE", "wilds path — advance the corridor", confidence=0.68)

    # Eco phase (arcs 2–3 / normal BAR): grow when dry and not under extreme fire
    if allow_eco and thr < 0.65 and obj < 0.7:
        metal_b = eco_bands.get("metal", "thin")
        energy_b = eco_bands.get("energy", "thin")
        eco_b = eco_bands.get("eco", "thin")
        bp_b = eco_bands.get("buildpower", "thin")
        if energy_b in ("dry", "thin") or (no_metal_map and energy_b != "fat"):
            if build_run < 6 or energy_b == "dry":
                return Decision("BUILD_ENERGY", "eco dry energy — plant power", confidence=0.78)
        if not no_metal_map and metal_b in ("dry", "thin"):
            if build_run < 6 or metal_b == "dry":
                return Decision("BUILD_MEX", "eco dry metal — plant mex", confidence=0.78)
        if bp_b in ("dry", "thin") and thr < 0.5 and build_run < 5:
            return Decision("BUILD_CON", "need buildpower — spawn con", confidence=0.7)
        if mission_kind in ECO_KINDS and eco_b in ("dry", "thin") and obj < 0.45:
            return Decision("EXPAND_FRONT", "eco footprint thin — expand", confidence=0.68)
        if mission_kind == "siege" and eco_b in ("steady", "fat") and thr > 0.4:
            if flank_run < 3 and caut > 0:
                return Decision("FLANK", "siege — work a dead angle", confidence=0.7)
            return Decision("PUSH_OBJECTIVE", "siege eco ready — pressure the wall", confidence=0.72)
        if mission_kind == "siege" and eco_b in ("dry", "thin"):
            return Decision("BUILD_ENERGY", "siege needs feed — grow eco first", confidence=0.75)
        if thr > 0.55 and eco_b in ("steady", "fat"):
            return Decision("DEFEND_BASE", "pressure on eco — defend the plant", confidence=0.7)

    # Anti-stall combat
    if stuck:
        if allow_eco and thr < 0.5 and build_run < 4:
            return Decision("EXPAND_FRONT", "stalled — expand then re-push", confidence=0.72)
        if p_str > 0.45 and thr < 0.7:
            return Decision("PUSH_OBJECTIVE", "stalled on probe/flank — commit the push", confidence=0.8)
        return Decision("HOLD_AND_HEAL", "stalled and weak — reset then push", confidence=0.75)

    if flank_run >= 5 and obj < 0.5:
        return Decision("PUSH_OBJECTIVE", "flank exhausted — frontal commit", confidence=0.78)

    if probe_run >= 6 and thr < 0.55:
        return Decision("PUSH_OBJECTIVE", "probe complete — advance", confidence=0.75)

    # Late clock
    if clk > 0.7 and obj < 0.65:
        if adv > 0.4 and p_str > 0.35:
            return Decision("PUSH_OBJECTIVE", "clock red — commit the push", confidence=0.8)
        if thr > 0.55:
            return Decision("FALLBACK", "clock red + overmatched — live", confidence=0.65)
        if allow_eco and thr < 0.45:
            return Decision("EXPAND_FRONT", "clock red weak contact — last expand then push", confidence=0.6)
        return Decision("PROBE", "clock red but weak — probe for opening", confidence=0.65)

    if coh < -0.25 and thr > 0.35:
        return Decision("RALLY", "force scattered under threat — regroup", confidence=0.7)

    if adv > 0.55 and thr < 0.7 and p_str > 0.4 and (agg > -0.1 or foc > 0.1 or mom > 0.0):
        if caut > 0.2 and obj < 0.25 and thr > 0.35 and flank_run < 3 and no_push < 8:
            return Decision("FLANK", "advantage with caution — short flank", confidence=0.68)
        return Decision("PUSH_OBJECTIVE", "advantage + focus — push objective", confidence=0.75)

    if thr > 0.6 and adv < 0.48:
        if caut > -0.1 or press > 0.15 or p_str < 0.5:
            return Decision("FALLBACK", "overmatched — fall back", confidence=0.72)
        return Decision("HOLD_AND_HEAL", "overmatched but aggressive — hold", confidence=0.6)

    if obj < 0.2 and mood.progress < 0.15:
        if allow_eco and thr < 0.4 and build_run < 3:
            return Decision("BUILD_ENERGY", "early expand window — plant power", confidence=0.7)
        if thr < 0.45 and probe_run < 4:
            return Decision("PROBE", "early — probe approach", confidence=0.7)
        if thr >= 0.45 and flank_run < 2:
            return Decision("FLANK", "early contact — brief flank", confidence=0.65)
        return Decision("PUSH_OBJECTIVE", "early phase done — push", confidence=0.7)

    if mom < -0.15 and thr < 0.55 and p_str > 0.4:
        return Decision("PUSH_OBJECTIVE", "stalled — force contact with objective", confidence=0.65)

    if thr > 0.55 and p_str < 0.55:
        return Decision("HOLD_AND_HEAL", "midfight pressure — steady", confidence=0.58)

    if mission_kind in ("eco_raid", "strike_relay", "siege", "multipressure") and obj > 0.4:
        return Decision("PUSH_OBJECTIVE", f"{mission_kind} mid — finish the job", confidence=0.68)

    if mission_kind in HOLD_KINDS and obj > 0.3:
        if thr > 0.5:
            return Decision("HOLD_AND_HEAL", "lane fight — hold the mark", confidence=0.68)
        return Decision("PUSH_OBJECTIVE", "lane open — take the mark", confidence=0.7)

    if obj > 0.55:
        return Decision("PUSH_OBJECTIVE", "objective in sight — finish", confidence=0.7)

    # Width-band manifold bias (solution geometry feel — fair only)
    wb = (width_band or "open").lower()
    if wb == "narrow":
        # clear action vector — commit primary combat line
        if thr < 0.7 and p_str > 0.35:
            return Decision("PUSH_OBJECTIVE", "narrow card — clear vector push", confidence=0.72)
        return Decision("HOLD_AND_HEAL", "narrow card under fire — steady then push", confidence=0.65)
    if wb == "wide" and allow_eco and thr < 0.55 and obj < 0.55:
        # multipath: eco and defend both legitimate
        if eco_bands.get("eco") in ("dry", "thin") and build_run < 5:
            return Decision("EXPAND_FRONT", "wide card — multipath expand", confidence=0.62)
        if thr > 0.4:
            return Decision("DEFEND_BASE", "wide card — hold plant while options open", confidence=0.58)

    return Decision("PUSH_OBJECTIVE", "default advance", confidence=0.55)


def action_effects(action: str) -> dict[str, float]:
    """How an action biases the abstract combat sim rates."""
    table = {
        "PUSH_OBJECTIVE": {
            "dmg_out": 1.25,
            "dmg_in": 1.15,
            "approach": 0.08,
            "obj_rate": 0.07,
            "cohesion": -0.02,
            "heal": 0.0,
        },
        "PROBE": {
            "dmg_out": 0.6,
            "dmg_in": 0.55,
            "approach": 0.04,
            "obj_rate": 0.02,
            "cohesion": 0.01,
            "heal": 0.01,
        },
        "FLANK": {
            "dmg_out": 1.1,
            "dmg_in": 0.85,
            "approach": 0.05,
            "obj_rate": 0.045,
            "cohesion": -0.03,
            "heal": 0.0,
        },
        "HOLD_AND_HEAL": {
            "dmg_out": 0.45,
            "dmg_in": 0.7,
            "approach": 0.0,
            "obj_rate": 0.01,
            "cohesion": 0.04,
            "heal": 0.08,
        },
        "RALLY": {
            "dmg_out": 0.5,
            "dmg_in": 0.6,
            "approach": 0.01,
            "obj_rate": 0.01,
            "cohesion": 0.12,
            "heal": 0.04,
        },
        "FALLBACK": {
            "dmg_out": 0.35,
            "dmg_in": 0.45,
            "approach": -0.04,
            "obj_rate": 0.0,
            "cohesion": 0.06,
            "heal": 0.05,
        },
        "EXTRACT": {
            "dmg_out": 0.3,
            "dmg_in": 0.5,
            "approach": -0.02,
            "obj_rate": 0.0,
            "cohesion": 0.05,
            "heal": 0.02,
            "extract_push": 0.15,
        },
        "WAIT": {
            "dmg_out": 0.4,
            "dmg_in": 0.5,
            "approach": 0.0,
            "obj_rate": 0.005,
            "cohesion": 0.02,
            "heal": 0.03,
        },
        "BUILD_MEX": {
            "dmg_out": 0.25,
            "dmg_in": 0.55,
            "approach": 0.0,
            "obj_rate": 0.015,
            "cohesion": 0.02,
            "heal": 0.01,
            "eco": 1.0,
        },
        "BUILD_ENERGY": {
            "dmg_out": 0.25,
            "dmg_in": 0.5,
            "approach": 0.0,
            "obj_rate": 0.015,
            "cohesion": 0.02,
            "heal": 0.01,
            "eco": 1.0,
        },
        "BUILD_CON": {
            "dmg_out": 0.3,
            "dmg_in": 0.55,
            "approach": 0.01,
            "obj_rate": 0.01,
            "cohesion": 0.03,
            "heal": 0.01,
            "eco": 0.8,
        },
        "EXPAND_FRONT": {
            "dmg_out": 0.55,
            "dmg_in": 0.75,
            "approach": 0.03,
            "obj_rate": 0.03,
            "cohesion": -0.01,
            "heal": 0.0,
            "eco": 0.7,
        },
        "RECLAIM": {
            "dmg_out": 0.2,
            "dmg_in": 0.45,
            "approach": -0.01,
            "obj_rate": 0.005,
            "cohesion": 0.02,
            "heal": 0.02,
            "eco": 0.5,
        },
        "TECH_UP": {
            "dmg_out": 0.35,
            "dmg_in": 0.55,
            "approach": 0.0,
            "obj_rate": 0.02,
            "cohesion": 0.01,
            "heal": 0.0,
            "eco": 0.9,
        },
        "DEFEND_BASE": {
            "dmg_out": 0.7,
            "dmg_in": 0.65,
            "approach": -0.01,
            "obj_rate": 0.02,
            "cohesion": 0.05,
            "heal": 0.03,
            "eco": 0.2,
        },
    }
    return dict(table.get(action, table["WAIT"]))
