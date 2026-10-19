#!/usr/bin/env python3
"""Agent attachment ledger — heroes, merc foothold, grudges (kernel, fair-facing).

Strategic seats and humans care who lives. Attachments bias quests and debrief
lines; they never grant god-mode HP or raw enemy tables.
"""
from __future__ import annotations

import copy
from itertools import combinations
from typing import Any, Dict, List, Optional

SCHEMA = "verdance-attachments/1.0"

DEFAULT_AGENTS = {
    "vane": {
        "id": "vane",
        "name": "Ash-Captain Vane",
        "kind": "hero",
        "bond": 0.45,
        "wounds": 0,
        "status": "active",
        "scarTags": [],
        "memoryLines": ["Leads the warband into ash."],
    },
    "ketha": {
        "id": "ketha",
        "name": "Ketha",
        "kind": "hero",
        "bond": 0.55,
        "wounds": 0,
        "status": "active",
        "scarTags": [],
        "memoryLines": ["Watches the graph and your back."],
    },
    "null_foothold": {
        "id": "null_foothold",
        "name": "Null Merc foothold",
        "kind": "faction_contact",
        "favor": 0.35,
        "betrayed": False,
        "memoryLines": ["One scrap-line crew on each map."],
    },
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def ensure_attachments(state: Dict[str, Any]) -> Dict[str, Any]:
    """Install / migrate attachment ledger on campaign state."""
    att = state.get("attachments")
    if not isinstance(att, dict) or att.get("schemaVersion") != SCHEMA:
        att = {
            "schemaVersion": SCHEMA,
            "agents": copy.deepcopy(DEFAULT_AGENTS),
            "grudges": [],
            "patrons": [],
            "events": [],
        }
        # Mirror existing character wounds if present
        chars = state.get("characters") or {}
        for hid in ("vane", "ketha"):
            c = chars.get(hid) if isinstance(chars, dict) else None
            if isinstance(c, dict) and hid in att["agents"]:
                att["agents"][hid]["wounds"] = int(c.get("wounds") or 0)
                att["agents"][hid]["status"] = str(c.get("status") or "active")
        rep = state.get("reputation") or {}
        nm = float(rep.get("nullmercs") or 40.0)
        att["agents"]["null_foothold"]["favor"] = _clamp(nm / 100.0)
        state["attachments"] = att
    else:
        agents = att.setdefault("agents", {})
        for k, v in DEFAULT_AGENTS.items():
            if k not in agents:
                agents[k] = copy.deepcopy(v)
        att.setdefault("grudges", [])
        att.setdefault("patrons", [])
        att.setdefault("events", [])
    return state["attachments"]


def fair_dossier(state: Dict[str, Any], *, max_memory: int = 3) -> Dict[str, Any]:
    """Player/LLM-facing strip — names + recent memory only."""
    att = ensure_attachments(state)
    agents_out = {}
    for aid, a in (att.get("agents") or {}).items():
        if not isinstance(a, dict):
            continue
        mem = list(a.get("memoryLines") or [])[-max_memory:]
        entry: Dict[str, Any] = {
            "id": aid,
            "name": a.get("name") or aid,
            "kind": a.get("kind"),
            "status": a.get("status", "active"),
            "memoryLines": mem,
        }
        if "bond" in a:
            entry["bondBand"] = _bond_band(float(a.get("bond") or 0))
            entry["wounds"] = int(a.get("wounds") or 0)
        if "favor" in a:
            entry["favorBand"] = _favor_band(float(a.get("favor") or 0))
            entry["betrayed"] = bool(a.get("betrayed"))
        agents_out[aid] = entry
    grudges = []
    for g in (att.get("grudges") or [])[-5:]:
        if isinstance(g, dict):
            grudges.append(
                {
                    "faction": g.get("faction"),
                    "zoneId": g.get("zoneId"),
                    "intensityBand": _favor_band(float(g.get("intensity") or 0)),
                }
            )
    return {
        "schemaVersion": SCHEMA,
        "agents": agents_out,
        "grudges": grudges,
        "eventCount": len(att.get("events") or []),
    }


def _bond_band(b: float) -> str:
    if b >= 0.75:
        return "devoted"
    if b >= 0.5:
        return "solid"
    if b >= 0.3:
        return "thin"
    return "frayed"


def _favor_band(f: float) -> str:
    if f >= 0.7:
        return "allied"
    if f >= 0.45:
        return "warm"
    if f >= 0.25:
        return "cool"
    return "hostile"


def _push_memory(agent: Dict[str, Any], line: str, cap: int = 12) -> None:
    mem = agent.setdefault("memoryLines", [])
    if not isinstance(mem, list):
        mem = []
        agent["memoryLines"] = mem
    mem.append(str(line)[:160])
    if len(mem) > cap:
        agent["memoryLines"] = mem[-cap:]


def _log_event(att: Dict[str, Any], kind: str, detail: Dict[str, Any]) -> None:
    ev = att.setdefault("events", [])
    ev.append({"kind": kind, **detail})
    if len(ev) > 80:
        att["events"] = ev[-80:]


def update_attachments_from_result(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    success: bool,
    zone_flipped: bool = False,
) -> Dict[str, Any]:
    """Apply match outcome to attachment ledger. Returns summary deltas."""
    att = ensure_attachments(state)
    agents = att["agents"]
    deltas: Dict[str, Any] = {"wounds": {}, "bond": {}, "favor": {}, "grudges": 0, "memories": []}
    map_id = str(result.get("mapId") or result.get("deploymentMapId") or "")
    zone = str(result.get("targetZoneId") or "")
    status = str(result.get("status") or result.get("verdict") or "")

    # Heroes from namedOutcomes or hero status fields
    named = result.get("namedOutcomes") or []
    if isinstance(named, list):
        for o in named:
            if not isinstance(o, dict):
                continue
            cid = str(o.get("charId") or o.get("heroId") or "")
            if cid not in agents:
                continue
            outcome = str(o.get("outcome") or "")
            a = agents[cid]
            if outcome == "dead":
                a["status"] = "dead"
                a["bond"] = _clamp(float(a.get("bond") or 0.4) - 0.15)
                tag = f"fallen_{map_id or 'field'}"
                scars = a.setdefault("scarTags", [])
                if tag not in scars:
                    scars.append(tag)
                line = f"{a.get('name')} fell on {zone or map_id or 'the field'}."
                _push_memory(a, line)
                deltas["memories"].append(line)
                deltas["bond"][cid] = -0.15
            elif outcome in ("wounded", "recovered"):
                a["wounds"] = int(a.get("wounds") or 0) + 1
                a["status"] = "wounded"
                a["bond"] = _clamp(float(a.get("bond") or 0.4) + 0.05)
                line = f"{a.get('name')} took a wound ({a['wounds']}) but held."
                _push_memory(a, line)
                deltas["wounds"][cid] = a["wounds"]
                deltas["memories"].append(line)
                deltas["bond"][cid] = 0.05

    # Hero results dict (alternate shape)
    heroes = result.get("heroes") or result.get("heroResults") or {}
    if isinstance(heroes, dict):
        for hid, hr in heroes.items():
            if hid not in agents:
                continue
            if not isinstance(hr, dict):
                continue
            st = str(hr.get("status") or hr.get("outcome") or "")
            if st == "dead" and agents[hid].get("status") != "dead":
                agents[hid]["status"] = "dead"
                agents[hid]["bond"] = _clamp(float(agents[hid].get("bond") or 0.4) - 0.12)
                line = f"{agents[hid].get('name')} listed dead after the sortie."
                _push_memory(agents[hid], line)
                deltas["memories"].append(line)

    # Null merc favor from rep if present, else outcome bias
    nf = agents.get("null_foothold")
    if isinstance(nf, dict):
        rep_nm = (state.get("reputation") or {}).get("nullmercs")
        if rep_nm is not None:
            nf["favor"] = _clamp(float(rep_nm) / 100.0)
        else:
            delta = 0.04 if success else -0.06
            if zone_flipped:
                delta += 0.03
            nf["favor"] = _clamp(float(nf.get("favor") or 0.3) + delta)
            deltas["favor"]["null_foothold"] = delta
        if success and zone_flipped:
            line = f"Foothold crews claim credit for {zone or map_id}."
            _push_memory(nf, line)
            deltas["memories"].append(line)
        elif not success:
            line = f"Null scrap-line cursed the botched run on {zone or map_id}."
            _push_memory(nf, line)
            deltas["memories"].append(line)

    # Grudges: fail or bloody against faction
    against = str(result.get("against") or result.get("enemyFaction") or "armada")
    if not success or status in ("defeat", "fail", "abort"):
        intensity = 0.35 if not success else 0.2
        _add_grudge(att, against, zone, intensity)
        deltas["grudges"] = 1
    elif success and zone_flipped:
        # Soften grudge on that zone if any
        for g in att.get("grudges") or []:
            if isinstance(g, dict) and g.get("zoneId") == zone:
                g["intensity"] = _clamp(float(g.get("intensity") or 0) - 0.1)

    # Bond boost on clean win with both heroes alive
    if success and status in ("victory", "victoryClean", "extracted", "partial"):
        for hid in ("vane", "ketha"):
            a = agents.get(hid)
            if isinstance(a, dict) and a.get("status") != "dead":
                before = float(a.get("bond") or 0.4)
                a["bond"] = _clamp(before + 0.03)
                deltas["bond"][hid] = deltas["bond"].get(hid, 0) + 0.03

    # Co-deploy support XP — pairs that shared the Drop thicken (FE loop).
    pair_delta = apply_co_deploy_support(state, result, success=success)
    if pair_delta.get("pairs"):
        deltas["pairBonds"] = pair_delta["pairs"]

    _log_event(
        att,
        "sortie_settle",
        {
            "success": success,
            "mapId": map_id,
            "zoneId": zone,
            "status": status,
            "zoneFlipped": zone_flipped,
            "coDeployPairs": list((pair_delta.get("pairs") or {}).keys()),
        },
    )

    # L3 hero observe — append-only tape (best-effort; never block settle).
    try:
        import hero_observe_v1 as _obs  # noqa: WPS433

        obs = _obs.try_append_sortie(
            state,
            result,
            success=success,
            zone_flipped=zone_flipped,
            pair_delta=pair_delta,
            ran_on=str(result.get("ran_on") or result.get("source") or "player"),
        )
        if isinstance(obs, dict):
            deltas["heroObserve"] = {
                "ok": obs.get("ok"),
                "skipped": obs.get("skipped"),
                "key": obs.get("key"),
            }
    except Exception:  # noqa: BLE001
        deltas["heroObserve"] = {"ok": False, "error": "emit_failed"}

    return deltas


def _deployed_hero_ids(result: Dict[str, Any], state: Dict[str, Any]) -> List[str]:
    """Best-effort deployed roster from result / plan / company."""
    ids: List[str] = []
    for key in ("deployAces", "deployedHeroes", "sortieHeroes"):
        raw = result.get(key)
        if isinstance(raw, list):
            for x in raw:
                if isinstance(x, dict):
                    hid = x.get("id") or x.get("heroId")
                    if hid:
                        ids.append(str(hid))
                elif x:
                    ids.append(str(x))
    plan = result.get("deployPlan") or {}
    if isinstance(plan, dict):
        for x in plan.get("deployAces") or []:
            ids.append(str(x))
    # Fall back to living company band+core
    if not ids:
        company = state.get("company") or {}
        for key in ("core", "band", "joinedLater"):
            for x in company.get(key) or []:
                if isinstance(x, dict):
                    hid = x.get("id") or x.get("heroId")
                    if hid:
                        ids.append(str(hid))
                elif x:
                    ids.append(str(x))
    # Dedup, drop dead
    att = ensure_attachments(state)
    agents = att.get("agents") or {}
    out: List[str] = []
    seen = set()
    for hid in ids:
        if hid in seen:
            continue
        seen.add(hid)
        a = agents.get(hid)
        if isinstance(a, dict) and a.get("status") == "dead":
            continue
        out.append(hid)
    return out


def apply_co_deploy_support(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    success: bool,
) -> Dict[str, Any]:
    """Raise pair-bond points for every co-deployed pair (survivors).

    Win: +6 points per pair. Partial/extract: +4. Loss: +2 (shared mud still bonds).
    Caps at 100. Seeds pairBonds rows as needed.
    """
    ensure_pair_bonds(state)
    deployed = _deployed_hero_ids(result, state)
    if len(deployed) < 2:
        return {"pairs": {}, "deployed": deployed}
    if success:
        status = str(result.get("status") or result.get("verdict") or "")
        bump = 6.0 if status in ("victory", "victoryClean") else 4.0
    else:
        bump = 2.0
    pairs_out: Dict[str, Any] = {}
    for a, b in combinations(deployed, 2):
        r = apply_pair_talk(state, a, b, talk_id=None, delta=bump)
        if r.get("ok"):
            pairs_out[str(r.get("pairId"))] = {
                "a": a,
                "b": b,
                "delta": bump,
                "after": r.get("after"),
                "rank": r.get("rank"),
            }
    return {"pairs": pairs_out, "deployed": deployed, "bump": bump}


def _add_grudge(att: Dict[str, Any], faction: str, zone_id: str, intensity: float) -> None:
    grudges = att.setdefault("grudges", [])
    for g in grudges:
        if isinstance(g, dict) and g.get("faction") == faction and g.get("zoneId") == zone_id:
            g["intensity"] = _clamp(float(g.get("intensity") or 0) + intensity * 0.5)
            return
    grudges.append(
        {
            "faction": faction,
            "zoneId": zone_id or None,
            "intensity": _clamp(intensity),
        }
    )
    if len(grudges) > 12:
        att["grudges"] = grudges[-12:]


def apply_rest(state: Dict[str, Any], hero_id: str = "all") -> Dict[str, Any]:
    """Strategic REST: heal one wound band, lift bond slightly, stress down."""
    att = ensure_attachments(state)
    healed = []
    targets = list(att["agents"].keys()) if hero_id == "all" else [hero_id]
    for hid in targets:
        a = att["agents"].get(hid)
        if not isinstance(a, dict) or a.get("kind") != "hero":
            continue
        if a.get("status") == "dead":
            continue
        w = int(a.get("wounds") or 0)
        if w > 0:
            a["wounds"] = w - 1
            if a["wounds"] == 0:
                a["status"] = "active"
            healed.append(hid)
        a["bond"] = _clamp(float(a.get("bond") or 0.4) + 0.02)
        _push_memory(a, f"{a.get('name')} rested between sorties.")
    # Companion stress if present
    comp = state.get("companion")
    if isinstance(comp, dict):
        comp["stress"] = max(0, float(comp.get("stress") or 0) - 8)
        comp["morale"] = min(100, float(comp.get("morale") or 70) + 5)
    _log_event(att, "rest", {"healed": healed, "heroId": hero_id})
    return {"healed": healed}


def apply_talk_bond(state: Dict[str, Any], hero_id: str = "ketha") -> Dict[str, Any]:
    """Strategic TALK: deepen one bond channel (fair, no combat cheat)."""
    att = ensure_attachments(state)
    a = att["agents"].get(hero_id)
    if not isinstance(a, dict):
        return {"ok": False, "reason": "unknown_agent"}
    before = float(a.get("bond") or a.get("favor") or 0.4)
    if "bond" in a:
        a["bond"] = _clamp(before + 0.06)
        after = a["bond"]
    else:
        a["favor"] = _clamp(before + 0.05)
        after = a["favor"]
    line = f"Long talk with {a.get('name')} — trust thickens."
    _push_memory(a, line)
    _log_event(att, "talk", {"heroId": hero_id, "before": before, "after": after})
    return {"ok": True, "heroId": hero_id, "before": before, "after": after, "line": line}


def _pair_key(a: str, b: str) -> str:
    x, y = sorted([str(a), str(b)])
    return f"{x}__{y}"


def ensure_pair_bonds(state: Dict[str, Any]) -> Dict[str, Any]:
    """Foundation: undirected pair-bond map on attachments (FE support ranks later).

    Values are 0–100 support points (hub aces.bonds style). G0 live channel
    remains vane↔ketha; the web seeds other pairs at 0 until talks/co-deploy.
    """
    att = ensure_attachments(state)
    pairs = att.setdefault("pairBonds", {})
    if not isinstance(pairs, dict):
        pairs = {}
        att["pairBonds"] = pairs
    # Seed core channel if missing
    pk = _pair_key("vane", "ketha")
    if pk not in pairs:
        pairs[pk] = {
            "a": "vane",
            "b": "ketha",
            "points": 10,
            "rank": "C",
            "talksDone": [],
        }
    return pairs


def apply_pair_talk(
    state: Dict[str, Any],
    hero_a: str,
    hero_b: str,
    *,
    talk_id: Optional[str] = None,
    delta: float = 8.0,
) -> Dict[str, Any]:
    """Foundation mutator: deepen a pair bond after a camp talk stub."""
    pairs = ensure_pair_bonds(state)
    att = ensure_attachments(state)
    a, b = str(hero_a), str(hero_b)
    if a == b:
        return {"ok": False, "reason": "same_hero"}
    pk = _pair_key(a, b)
    row = pairs.get(pk)
    if not isinstance(row, dict):
        row = {"a": a, "b": b, "points": 0, "rank": None, "talksDone": []}
        pairs[pk] = row
    before = float(row.get("points") or 0)
    after = _clamp(before + float(delta), 0.0, 100.0)
    row["points"] = after
    # Rank bands: C <25, B <55, A >=55 (mirrors camp_talk unlock bondMin)
    if after >= 55:
        row["rank"] = "A"
    elif after >= 25:
        row["rank"] = "B"
    elif after > 0:
        row["rank"] = "C"
    else:
        row["rank"] = None
    done = list(row.get("talksDone") or [])
    if talk_id and talk_id not in done:
        done.append(str(talk_id))
        row["talksDone"] = done[-12:]
    # Mirror onto characters.*.bonds for hub aces projection
    chars = state.setdefault("characters", {})
    if isinstance(chars, dict):
        for src, dst, pts in ((a, b, after), (b, a, after)):
            ch = chars.get(src)
            if not isinstance(ch, dict):
                ch = {"id": src, "bonds": {}}
                chars[src] = ch
            bonds = ch.setdefault("bonds", {})
            if isinstance(bonds, dict):
                bonds[dst] = int(round(pts))
    _log_event(
        att,
        "pair_talk",
        {"pairId": pk, "talkId": talk_id, "before": before, "after": after},
    )
    return {
        "ok": True,
        "pairId": pk,
        "before": before,
        "after": after,
        "rank": row.get("rank"),
        "talkId": talk_id,
    }


def grudge_zone_bias(state: Dict[str, Any]) -> Dict[str, float]:
    """zoneId -> bonus score for quest ranking (prefer return contracts)."""
    att = ensure_attachments(state)
    out: Dict[str, float] = {}
    for g in att.get("grudges") or []:
        if not isinstance(g, dict):
            continue
        z = g.get("zoneId")
        if not z:
            continue
        out[str(z)] = out.get(str(z), 0.0) + float(g.get("intensity") or 0) * 0.5
    return out


def power_signals_from_attachments(state: Dict[str, Any]) -> Dict[str, float]:
    """Aggregate attachment-derived strength for power-response curve."""
    att = ensure_attachments(state)
    agents = att.get("agents") or {}
    vane = agents.get("vane") or {}
    ketha = agents.get("ketha") or {}
    nf = agents.get("null_foothold") or {}
    bond = (float(vane.get("bond") or 0) + float(ketha.get("bond") or 0)) / 2.0
    wounds = int(vane.get("wounds") or 0) + int(ketha.get("wounds") or 0)
    alive = sum(
        1
        for h in (vane, ketha)
        if isinstance(h, dict) and h.get("status") != "dead"
    )
    return {
        "bond": bond,
        "wounds": float(wounds),
        "heroesAlive": float(alive),
        "nullFavor": float(nf.get("favor") or 0),
        "grudgeCount": float(len(att.get("grudges") or [])),
    }
