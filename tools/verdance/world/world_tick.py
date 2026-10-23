#!/usr/bin/env python3
"""World tick + power-response curve — density membrane between sorties.

Offscreen war drifts; player power draws pushback. Does not run BAR.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import clamp

from verdance.company import attachments as att_mod
from verdance.world import offscreen_clash as oc
from verdance.company import capture_node_claims as cnc


def player_strength(state: Dict[str, Any]) -> Dict[str, float]:
    """Aggregate player power signals for pushback policy."""
    commerce = state.get("commerce") or {}
    tnb = float(commerce.get("tenebrium") or 0)
    credits = float(commerce.get("credits") or 0)
    claims = 0
    for mid, lst in (state.get("nodeClaims") or {}).items():
        if isinstance(lst, list):
            claims += len(lst)
    # capture_node_claims writes claimedNodes[map][zone]
    for mid, by_z in (state.get("claimedNodes") or {}).items():
        if isinstance(by_z, dict):
            claims += len(by_z)
        elif isinstance(by_z, list):
            claims += len(by_z)
    # also count zone control
    held = 0
    for mid, zones in (state.get("zoneMemory") or {}).items():
        if not isinstance(zones, dict):
            continue
        for zid, zm in zones.items():
            if not isinstance(zm, dict):
                continue
            fac = str(zm.get("controllingFaction") or "")
            if fac in ("ashwalkers", "nullmercs"):
                held += 1
    att_sig = att_mod.power_signals_from_attachments(state)
    # Normalize rough 0..1 strength
    tnb_n = clamp(tnb / 12.0)
    claim_n = clamp(claims / 6.0)
    held_n = clamp(held / 20.0)
    bond_n = float(att_sig.get("bond") or 0)
    favor_n = float(att_sig.get("nullFavor") or 0)
    wound_pen = clamp(float(att_sig.get("wounds") or 0) / 6.0)
    composite = clamp(
        0.28 * tnb_n
        + 0.22 * claim_n
        + 0.18 * held_n
        + 0.18 * bond_n
        + 0.14 * favor_n
        - 0.15 * wound_pen
    )
    return {
        "tenebrium": tnb,
        "credits": credits,
        "nodeClaims": float(claims),
        "zonesHeld": float(held),
        "bond": bond_n,
        "nullFavor": favor_n,
        "wounds": float(att_sig.get("wounds") or 0),
        "composite": composite,
    }


def power_response(state: Dict[str, Any], strength: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Map player strength → world flags / recipe tags / contract pressure.

    Policy table (fiction pushback, not just +enemy HP):
      high Tnb → Armada crisis / loan scrutiny / denser teeth tag
      many claims → regrow pressure ↑ / multipressure contracts
      high Null favor → Armada garrison scale
      high bond + low wounds → riskier deep-strike width
      bloody fails / wounds → soft contracts + scarcity
    """
    s = strength or player_strength(state)
    c = float(s.get("composite") or 0)
    flags: Dict[str, Any] = {
        "armadaTenebriumCrisis": True,  # world default fiction
        "loanScrutiny": False,
        "denseTeeth": False,
        "regrowPressureBoost": 0.0,
        "multipressureContracts": False,
        "armadaGarrisonScale": 1.0,
        "pathWidthBoost": 0.0,
        "softContracts": False,
        "scarcityFloor": None,
        "pushbackEvents": [],
    }
    events: List[str] = []

    if float(s.get("tenebrium") or 0) >= 6 or c >= 0.55:
        flags["loanScrutiny"] = True
        flags["denseTeeth"] = True
        events.append("armada_watches_your_bank")
    if float(s.get("tenebrium") or 0) >= 10 or c >= 0.7:
        flags["armadaTenebriumCrisis"] = True
        events.append("tenebrium_crisis_tightens")

    claims = float(s.get("nodeClaims") or 0)
    if claims >= 2:
        flags["regrowPressureBoost"] = min(0.45, 0.12 * claims)
        events.append("regrow_pressure_rises")
    if claims >= 3 or c >= 0.65:
        flags["multipressureContracts"] = True
        events.append("multipressure_contracts_open")

    favor = float(s.get("nullFavor") or 0)
    if favor >= 0.45:
        flags["armadaGarrisonScale"] = round(1.0 + 0.1 + 0.15 * favor, 3)
        events.append("armada_scales_garrison")

    bond = float(s.get("bond") or 0)
    wounds = float(s.get("wounds") or 0)
    if bond >= 0.55 and wounds <= 1:
        flags["pathWidthBoost"] = 0.12
        events.append("deep_strike_paths_open")
    if wounds >= 3 or c < 0.25:
        flags["softContracts"] = True
        flags["scarcityFloor"] = 0.72
        events.append("world_offers_softer_work")

    # Late campaign φ from clock / mission number
    clock = float(state.get("campaignClockMinutes") or 0)
    mission_n = int(state.get("missionNumber") or 1)
    phi = clamp(max(clock / 600.0, (mission_n - 1) / 15.0))
    if phi >= 0.55:
        flags["pathWidthBoost"] = round(float(flags["pathWidthBoost"]) + 0.08, 3)
        events.append("late_campaign_multipath")

    flags["pushbackEvents"] = events
    flags["playerStrength"] = s
    flags["phi"] = round(phi, 3)

    # Stamp onto state for intent/compiler readers
    wr = state.setdefault("worldResponse", {})
    wr.update({k: v for k, v in flags.items() if k != "pushbackEvents"})
    wr["pushbackEvents"] = list(events)
    wr["updatedAtMission"] = mission_n
    return flags


def world_tick(
    state: Dict[str, Any],
    *,
    hours_offline: float = 1.0,
    map_id: Optional[str] = None,
    rest: bool = False,
    workspace: Any = None,
) -> Dict[str, Any]:
    """Advance offscreen world between sorties.

    - abstract shell regrow
    - zone pressure drift (light)
    - attachment rest if requested
    - power-response recompute
    - optional story engine offscreen hooks when available
    """
    hours = max(0.0, float(hours_offline))
    elapsed_min = hours * 60.0
    report: Dict[str, Any] = {
        "hours": hours,
        "elapsedMinutes": elapsed_min,
        "regrow": None,
        "pressureDrift": [],
        "rest": None,
        "power": None,
        "graphNudge": {},
    }

    att_mod.ensure_attachments(state)
    home = map_id or state.get("sessionHomeMap") or _first_map(state)

    # Abstract regrow: all maps, far theaters at 0.25x offline elapsed
    FAR_RATE = 0.25
    regrow_by_map: Dict[str, Any] = {}
    if elapsed_min > 0:
        map_ids = list((state.get("zoneMemory") or {}).keys()) or ([home] if home else [])
        for mid in map_ids:
            if not mid:
                continue
            rate = 1.0 if str(mid) == str(home) else FAR_RATE
            dt = elapsed_min * rate
            try:
                from verdance import campaign as engine

                regrow_by_map[str(mid)] = engine.apply_abstract_regrow(state, str(mid), dt)
            except Exception:
                try:

                    regrow_by_map[str(mid)] = cnc.apply_abstract_regrow(state, str(mid), dt)
                except Exception as e:
                    regrow_by_map[str(mid)] = {"error": str(e)}
        report["regrow"] = regrow_by_map.get(str(home)) if home else None
        report["regrowByMap"] = regrow_by_map

    # Light offscreen pressure drift: home full, other maps at FAR_RATE
    if hours > 0:
        drifts: List[Dict[str, Any]] = []
        for mid in list((state.get("zoneMemory") or {}).keys()) or ([home] if home else []):
            if not mid:
                continue
            h = hours if str(mid) == str(home) else hours * FAR_RATE
            drifts.extend(_drift_zone_pressure(state, str(mid), h))
        report["pressureDrift"] = drifts

    if rest:
        report["rest"] = att_mod.apply_rest(state, "all")

    # Scarcity / contested ease slowly offline
    graph = state.setdefault("graph", {})
    q7 = float(graph.get("q7_resource_scarcity") or 0.5)
    q6 = float(graph.get("q6_contested") or 0.5)
    # Without player action, scarcity creeps up slightly; contested drifts mid
    dq7 = min(0.04, 0.01 * hours)
    graph["q7_resource_scarcity"] = clamp(q7 + dq7)
    graph["q6_contested"] = clamp(q6 + (0.5 - q6) * min(0.15, 0.03 * hours))
    report["graphNudge"] = {
        "q7_resource_scarcity": graph["q7_resource_scarcity"],
        "q6_contested": graph["q6_contested"],
    }

    # Faction bank fiction: Armada densifies if player strong
    banks = state.setdefault("factionBanks", {})
    if not isinstance(banks, dict):
        banks = {}
        state["factionBanks"] = banks
    strength = player_strength(state)
    if strength["composite"] >= 0.5:
        banks["armada"] = int(banks.get("armada") or 0) + max(1, int(hours))
    report["factionBanks"] = dict(banks)

    # Power response
    report["power"] = power_response(state, strength)

    # Offscreen faction clashes during rest / between sorties
    clash_report = None
    if hours > 0:
        try:

            clash_report = oc.run_offscreen_clashes(
                state,
                Path(workspace) if workspace else None,
                active_map_id=str(home) if home else None,
                dt_minutes=elapsed_min,
                seed_key=f"world_tick|{state.get('missionNumber')}|{hours}",
            )
        except Exception as e:
            clash_report = {"error": str(e)}
    report["clash"] = clash_report

    # Clock
    state["campaignClockMinutes"] = round(
        float(state.get("campaignClockMinutes") or 0) + elapsed_min * 0.25,  # offline is slower than sortie time
        4,
    )

    events = state.setdefault("worldTickEvents", [])
    events.append(
        {
            "hours": hours,
            "home": home,
            "pushback": list((report.get("power") or {}).get("pushbackEvents") or []),
            "clashes": (clash_report or {}).get("clashes"),
            "flips": (clash_report or {}).get("flips"),
        }
    )
    if len(events) > 40:
        state["worldTickEvents"] = events[-40:]

    return report


def _first_map(state: Dict[str, Any]) -> Optional[str]:
    zm = state.get("zoneMemory") or {}
    if isinstance(zm, dict) and zm:
        return next(iter(zm.keys()))
    return "koom_valley"


def _drift_zone_pressure(state: Dict[str, Any], map_id: str, hours: float) -> List[Dict[str, Any]]:
    zones = (state.get("zoneMemory") or {}).get(map_id) or {}
    if not isinstance(zones, dict):
        return []
    out = []
    for zid, zm in list(zones.items())[:12]:
        if not isinstance(zm, dict):
            continue
        absr = zm.setdefault("abstract", {})
        mil = float(absr.get("militaryPressure") or absr.get("pressure") or 0.3)
        # Enemy-held zones densify slightly; player-held fray
        fac = str(zm.get("controllingFaction") or absr.get("control") or "neutral")
        if fac in ("armada", "cortex"):
            mil = clamp(mil + 0.02 * hours)
        elif fac in ("ashwalkers", "nullmercs"):
            mil = clamp(mil + 0.01 * hours * 0.5)
        else:
            mil = clamp(mil + 0.015 * hours)
        absr["militaryPressure"] = round(mil, 4)
        absr["pressure"] = round(mil, 4)
        out.append({"zoneId": zid, "faction": fac, "militaryPressure": absr["militaryPressure"]})
    return out


def apply_power_to_intent(intent: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Stamp worldResponse onto mission intent for compiler / seat fair card."""
    wr = state.get("worldResponse") or power_response(state)
    intent = dict(intent or {})
    intent["worldResponse"] = {
        "denseTeeth": wr.get("denseTeeth"),
        "loanScrutiny": wr.get("loanScrutiny"),
        "regrowPressureBoost": wr.get("regrowPressureBoost"),
        "multipressureContracts": wr.get("multipressureContracts"),
        "armadaGarrisonScale": wr.get("armadaGarrisonScale"),
        "pathWidthBoost": wr.get("pathWidthBoost"),
        "softContracts": wr.get("softContracts"),
        "pushbackEvents": list(wr.get("pushbackEvents") or []),
        "phi": wr.get("phi"),
        "playerStrengthComposite": (wr.get("playerStrength") or {}).get("composite"),
    }
    # Crisis flag path used by commerce / gadgets
    wf = intent.setdefault("worldFlags", {})
    if isinstance(wf, dict):
        wf["armadaTenebriumCrisis"] = bool(wr.get("armadaTenebriumCrisis", True))
        wf["loanScrutiny"] = bool(wr.get("loanScrutiny"))
    return intent


def self_test() -> Dict[str, Any]:
    """Tiny referee without full story engine."""
    state = {
        "missionNumber": 4,
        "campaignClockMinutes": 90,
        "commerce": {"tenebrium": 8, "credits": 40},
        "nodeClaims": {"koom_valley": [{"zoneId": "A"}, {"zoneId": "B"}, {"zoneId": "C"}]},
        "zoneMemory": {
            "koom_valley": {
                "Z1": {"controllingFaction": "nullmercs", "abstract": {}},
                "Z2": {"controllingFaction": "armada", "abstract": {"militaryPressure": 0.4}},
            }
        },
        "graph": {"q7_resource_scarcity": 0.5, "q6_contested": 0.8},
        "reputation": {"nullmercs": 55},
    }
    att_mod.ensure_attachments(state)
    s = player_strength(state)
    pr = power_response(state, s)
    tick = world_tick(state, hours_offline=2.0, map_id="koom_valley", rest=True)
    return {
        "strengthComposite": s["composite"],
        "pushback": pr["pushbackEvents"],
        "denseTeeth": pr["denseTeeth"],
        "tickPushback": (tick.get("power") or {}).get("pushbackEvents"),
        "q7": state["graph"]["q7_resource_scarcity"],
    }


def main() -> int:
    import json
    import sys

    if "--self-test" in sys.argv:
        print(json.dumps(self_test(), indent=2))
        raise SystemExit(0)
    print("world_tick: run by the campaign engine at homecoming; --self-test to check it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
