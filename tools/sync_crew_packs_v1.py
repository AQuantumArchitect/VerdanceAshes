#!/usr/bin/env python3
"""Resolve parametric pack mass from anchors, then sync JSON + Lua roster + embed.

SSOT: data/story/crew_packs.json
  combined = metal + energy / energyPerMetal
  mid/high bands come from packAnchor (Karkinos six / Javelin pair)

Hero sizing modes (hero.sizing):
  fixed      — keep packTotal + escort counts as authored
  leadFill   — set packTotal from massBand target / lead combined
  escortFill — keep lead + fixed escorts; set fillUnit escort count to close the gap

Exempt / scout packs stay fixed. Run: python tools/sync_crew_packs_v1.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
CREW_JSON = ROOT / "data" / "story" / "crew_packs.json"
ROSTER_LUA = (
    ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_crew_roster.lua"
)
EMBED_JS = ROOT / "app" / "showoff" / "crew_packs.embed.js"


def combined(metal: float, energy: float, epm: float) -> int:
    return int(round(float(metal) + float(energy) / float(epm)))


def chassis_combined(chassis: Dict[str, Any], def_name: str, epm: float) -> int:
    row = chassis.get(def_name) or {}
    if not row:
        raise KeyError(f"missing chassis[{def_name}]")
    m = float(row.get("metal") or 0)
    e = float(row.get("energy") or 0)
    got = combined(m, e, epm)
    row["combined"] = got
    return got


def band_target(packs: Dict[str, Any], band: str) -> int:
    anchors = packs.get("packAnchor") or {}
    bands = (packs.get("massPolicy") or {}).get("bands") or {}
    spec = bands.get(band) or {}
    if "combined" in spec:
        return int(spec["combined"])
    ref = spec.get("fromAnchor")
    if ref and ref in anchors:
        return int((anchors[ref] or {}).get("combined") or 0)
    if band == "high":
        return int((anchors.get("javelinPair") or {}).get("combined") or 3000)
    if band == "mid":
        return int((anchors.get("karkinosSix") or {}).get("combined") or 2064)
    raise KeyError(f"unknown mass band {band}")


def count_nearest(target: float, unit: float, min_n: int = 1, max_n: int = 48) -> int:
    if unit <= 0:
        return min_n
    n = int(round(target / unit))
    return max(min_n, min(max_n, n))


def pack_mass(
    hero: Dict[str, Any],
    chassis: Dict[str, Any],
    epm: float,
) -> Tuple[int, int, int]:
    """Return (combined, metal, energy) for lead*packTotal + escorts."""
    lead = str(hero.get("unitDef") or "")
    n = int(hero.get("packTotal") or 1)
    lead_c = chassis_combined(chassis, lead, epm)
    metal = float((chassis[lead].get("metal") or 0)) * n
    energy = float((chassis[lead].get("energy") or 0)) * n
    total = lead_c * n
    for esc in hero.get("escorts") or []:
        if not isinstance(esc, dict):
            continue
        ed = str(esc.get("unitDef") or "")
        ec = int(esc.get("count") or 0)
        if not ed or ec <= 0:
            continue
        ec_c = chassis_combined(chassis, ed, epm)
        total += ec_c * ec
        metal += float((chassis[ed].get("metal") or 0)) * ec
        energy += float((chassis[ed].get("energy") or 0)) * ec
    return int(total), int(round(metal)), int(round(energy))


def ensure_fill_escort(hero: Dict[str, Any], fill_unit: str) -> Dict[str, Any]:
    escorts: List[Dict[str, Any]] = []
    raw = hero.get("escorts") or []
    if isinstance(raw, list):
        escorts = [dict(x) for x in raw if isinstance(x, dict)]
    found = None
    for esc in escorts:
        if str(esc.get("unitDef") or "") == fill_unit:
            found = esc
            break
    if found is None:
        found = {"unitDef": fill_unit, "count": 0, "fill": True}
        escorts.append(found)
    else:
        found["fill"] = True
    hero["escorts"] = escorts
    return found


def fixed_mass_without_fill(
    hero: Dict[str, Any],
    chassis: Dict[str, Any],
    epm: float,
    fill_unit: Optional[str],
) -> int:
    """Mass of lead + non-fill escorts (fill escort count treated as 0)."""
    probe = {
        "unitDef": hero.get("unitDef"),
        "packTotal": hero.get("packTotal") or 1,
        "escorts": [],
    }
    for esc in hero.get("escorts") or []:
        if not isinstance(esc, dict):
            continue
        ed = str(esc.get("unitDef") or "")
        if fill_unit and ed == fill_unit:
            continue
        probe["escorts"].append({"unitDef": ed, "count": int(esc.get("count") or 0)})
    total, _, _ = pack_mass(probe, chassis, epm)
    return total


def resolve_hero(
    hid: str,
    hero: Dict[str, Any],
    packs: Dict[str, Any],
    chassis: Dict[str, Any],
    epm: float,
) -> None:
    policy = packs.get("massPolicy") or {}
    sizing = str(hero.get("sizing") or "fixed")
    band = str(hero.get("massBand") or "")
    if sizing == "fixed" or not band:
        total, metal, energy = pack_mass(hero, chassis, epm)
        hero["packCombined"] = total
        hero["packMetal"] = metal
        hero["packEnergy"] = energy
        hero["extras"] = max(0, int(hero.get("packTotal") or 1) - 1)
        return

    target = band_target(packs, band)
    lead = str(hero.get("unitDef") or "")
    lead_c = chassis_combined(chassis, lead, epm)

    if sizing == "leadFill":
        min_n = int(hero.get("minPackTotal") or 1)
        max_n = int(hero.get("maxPackTotal") or 48)
        n = count_nearest(target, lead_c, min_n=min_n, max_n=max_n)
        hero["packTotal"] = n
        # Drop stale fill escorts on pure lead packs.
        if hero.get("escorts"):
            hero["escorts"] = [
                e
                for e in hero["escorts"]
                if isinstance(e, dict) and not e.get("fill")
            ]
            if not hero["escorts"]:
                hero.pop("escorts", None)
    elif sizing == "escortFill":
        fill_unit = str(hero.get("fillUnit") or "")
        if not fill_unit:
            raise ValueError(f"{hid}: escortFill requires fillUnit")
        fill_row = ensure_fill_escort(hero, fill_unit)
        base = fixed_mass_without_fill(hero, chassis, epm, fill_unit)
        fill_c = chassis_combined(chassis, fill_unit, epm)
        need = max(0, target - base)
        min_f = int(hero.get("minFill") or 0)
        max_f = int(hero.get("maxFill") or 48)
        n = count_nearest(need, fill_c, min_n=max(1, min_f) if need > 0 else 0, max_n=max_f)
        if need <= 0:
            n = min_f
        # If nearest would overshoot badly and floor is closer, prefer floor when >0.
        if n > 0 and fill_c > 0:
            floor_n = max(min_f, min(max_f, int(math.floor(need / fill_c))))
            ceil_n = max(min_f, min(max_f, int(math.ceil(need / fill_c)))) if need > 0 else 0
            candidates = [x for x in {floor_n, n, ceil_n} if x >= 0]
            n = min(candidates, key=lambda x: (abs(base + x * fill_c - target), x))
            n = max(min_f, min(max_f, n))
        fill_row["count"] = int(n)
        fill_row["fill"] = True
        if int(hero.get("packTotal") or 0) <= 0:
            hero["packTotal"] = 1
    else:
        raise ValueError(f"{hid}: unknown sizing {sizing}")

    total, metal, energy = pack_mass(hero, chassis, epm)
    hero["packCombined"] = total
    hero["packMetal"] = metal
    hero["packEnergy"] = energy
    hero["extras"] = max(0, int(hero.get("packTotal") or 1) - 1)
    hero["massTarget"] = target


def refresh_anchor_combined(packs: Dict[str, Any], chassis: Dict[str, Any], epm: float) -> None:
    for key, anchor in (packs.get("packAnchor") or {}).items():
        if not isinstance(anchor, dict):
            continue
        ud = str(anchor.get("unitDef") or "")
        count = int(anchor.get("count") or 0)
        if not ud or count <= 0:
            continue
        unit_c = chassis_combined(chassis, ud, epm)
        anchor["combined"] = unit_c * count


def lua_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def lua_bool(v: bool) -> str:
    return "true" if v else "false"


def emit_roster_lua(packs: Dict[str, Any]) -> str:
    heroes = packs.get("heroes") or {}
    factories = packs.get("factories") or {}
    mentors = packs.get("mentorProducts") or {}
    band_order = packs.get("bandOrder") or []
    if not band_order:
        # Fall back to roleSpread order used historically.
        rs = packs.get("roleSpread") or {}
        order: List[str] = []
        for key in ("heavy", "line", "scout", "specialist", "support"):
            for hid in rs.get(key) or []:
                if hid not in order and hid in heroes:
                    order.append(str(hid))
        for hid in heroes:
            if hid not in order and str((heroes[hid] or {}).get("role") or "") == "band":
                if not (heroes[hid] or {}).get("deprecated"):
                    order.append(str(hid))
        band_order = order

    lines: List[str] = []
    lines.append("-- Verdance crew roster / pack catalog (Muster the Band).")
    lines.append("-- Feel anchors: 2x Javelin, 6x Karkinos. Hire Tnb ONLY for build-power chassis.")
    lines.append("-- Keep in sync with data/story/crew_packs.json (schema 1.6).")
    lines.append("-- GENERATED by tools/sync_crew_packs_v1.py — edit crew_packs.json then regenerate.")
    lines.append("")
    lines.append("local M = {}")
    lines.append("")
    lines.append(f"M.ENERGY_PER_METAL = {int(packs.get('energyPerMetal') or 70)}")
    lines.append("M.KARK_ANCHOR = 6")
    lines.append("M.JAV_ANCHOR = 2")
    lines.append(f"M.SEAT_CAP = {int(packs.get('seatCap') or 3)}")
    lines.append(f"M.START_WALLET_TNB = {int(packs.get('startWalletTnb') or 3)}")
    lines.append(
        f"M.PLAYTEST_ALL_UNLOCKED = {lua_bool(bool(packs.get('playtestAllUnlocked', True)))}"
    )
    lines.append("")
    core = packs.get("core") or ["vane", "ketha"]
    lines.append("M.CORE = { " + ", ".join(lua_str(x) for x in core) + " }")
    lines.append("")
    lines.append("M.HEROES = {")
    for hid, hero in heroes.items():
        if not isinstance(hero, dict):
            continue
        lines.append(f"  {hid} = {{")
        lines.append(f"    name = {lua_str(str(hero.get('name') or hid))},")
        lines.append(f"    role = {lua_str(str(hero.get('role') or 'band'))},")
        lines.append(f"    unitDef = {lua_str(str(hero.get('unitDef') or ''))},")
        lines.append(f"    hireTnb = {int(hero.get('hireTnb') or 0)},")
        if hero.get("hireKm") is not None:
            lines.append(f"    hireKm = {int(hero.get('hireKm') or 0)},")
        lines.append(f"    packTotal = {int(hero.get('packTotal') or 1)},")
        lines.append(f"    extras = {int(hero.get('extras') or max(0, int(hero.get('packTotal') or 1) - 1))},")
        if hero.get("noTnbStake"):
            lines.append("    noTnbStake = true,")
        if hero.get("missionCritical"):
            lines.append("    missionCritical = true,")
        if hero.get("premium"):
            lines.append("    premium = true,")
        if hero.get("deprecated"):
            lines.append("    deprecated = true,")
        if hero.get("factory"):
            lines.append(f"    factory = {lua_str(str(hero.get('factory')))},")
        if hero.get("heroTrait"):
            lines.append(f"    heroTrait = {lua_str(str(hero.get('heroTrait')))},")
        if hero.get("fieldEffect"):
            lines.append(f"    fieldEffect = {lua_str(str(hero.get('fieldEffect')))},")
        if hero.get("formation"):
            lines.append(f"    formation = {lua_str(str(hero.get('formation')))},")
        if hero.get("startXp") is not None:
            lines.append(f"    startXp = {float(hero.get('startXp') or 0)},")
        # swarm = pack drag/speed; pair/solo = player micro / line-spread.
        mind = str(hero.get("packMind") or "").strip().lower()
        if not mind:
            n = int(hero.get("packTotal") or 1)
            if n >= 6:
                mind = "swarm"
            elif n == 2:
                mind = "pair"
            else:
                mind = "solo"
        if mind not in ("swarm", "pair", "solo"):
            mind = "solo"
        lines.append(f"    packMind = {lua_str(mind)},")
        tags = hero.get("tags") or []
        if isinstance(tags, list) and tags:
            lines.append("    tags = { " + ", ".join(lua_str(str(t)) for t in tags) + " },")
        escorts = hero.get("escorts") or []
        if isinstance(escorts, list) and escorts:
            lines.append("    escorts = {")
            for esc in escorts:
                if not isinstance(esc, dict):
                    continue
                ed = str(esc.get("unitDef") or "")
                ec = int(esc.get("count") or 0)
                if not ed or ec <= 0:
                    continue
                lines.append("      {")
                lines.append(f"        unitDef = {lua_str(ed)},")
                lines.append(f"        count = {ec},")
                lines.append("      },")
            lines.append("    },")
        if hero.get("blurb"):
            lines.append(f"    blurb = {lua_str(str(hero.get('blurb')))},")
        lines.append("  },")
    lines.append("}")
    lines.append("")
    lines.append("M.FACTORIES = {")
    for fid, fab in factories.items():
        if not isinstance(fab, dict):
            continue
        lines.append(f"  {fid} = {{")
        if fab.get("structureDef") is None:
            lines.append("    structureDef = nil,")
        else:
            lines.append(f"    structureDef = {lua_str(str(fab.get('structureDef')))},")
        lines.append(f"    boundHero = {lua_str(str(fab.get('boundHero') or ''))},")
        if fab.get("product") is None:
            lines.append("    product = nil,")
        else:
            lines.append(f"    product = {lua_str(str(fab.get('product')))},")
        lines.append(f"    label = {lua_str(str(fab.get('label') or fid))},")
        if fab.get("noTnbStake"):
            lines.append("    noTnbStake = true,")
        lines.append("  },")
    lines.append("}")
    lines.append("")
    lines.append("-- Pack-mentor products (factory / scout mint defs). Campaign + tags read this only.")
    lines.append("M.MENTOR_PRODUCTS = {")
    for mid, products in mentors.items():
        if isinstance(products, dict):
            keys = [k for k, v in products.items() if v]
        elif isinstance(products, list):
            keys = [str(x) for x in products]
        else:
            continue
        inner = ", ".join(f"{k} = true" for k in keys)
        lines.append(f"  {mid} = {{ {inner} }},")
    lines.append("}")
    lines.append("")
    lines.append("M.BAND_ORDER = {")
    # Keep historical wrap style ~3-ish visual lines
    chunk: List[str] = []
    for hid in band_order:
        chunk.append(lua_str(str(hid)))
    # Emit in rows of ~8
    for i in range(0, len(chunk), 8):
        row = ", ".join(chunk[i : i + 8])
        suffix = "," if i + 8 < len(chunk) else ","
        lines.append(f"  {row}{suffix}")
    lines.append("}")
    lines.append("")
    lines.append("function M.isCore(heroId)")
    lines.append('  heroId = tostring(heroId or "")')
    lines.append("  for _, id in ipairs(M.CORE) do")
    lines.append("    if id == heroId then return true end")
    lines.append("  end")
    lines.append("  return false")
    lines.append("end")
    lines.append("")
    lines.append("function M.get(heroId)")
    lines.append('  return M.HEROES[tostring(heroId or "")]')
    lines.append("end")
    lines.append("")
    lines.append("function M.isDeprecated(heroId)")
    lines.append("  local h = M.get(heroId)")
    lines.append("  return h ~= nil and h.deprecated == true")
    lines.append("end")
    lines.append("")
    lines.append("function M.isUnlocked(_heroId, _mission)")
    lines.append("  if M.isDeprecated(_heroId) then return false end")
    lines.append("  if M.PLAYTEST_ALL_UNLOCKED then return true end")
    lines.append("  return true")
    lines.append("end")
    lines.append("")
    lines.append("function M.hireCost(heroId)")
    lines.append("  local h = M.get(heroId)")
    lines.append("  if not h then return 999 end")
    lines.append("  return tonumber(h.hireTnb) or 0")
    lines.append("end")
    lines.append("")
    lines.append("function M.hireKmCost(heroId)")
    lines.append("  local h = M.get(heroId)")
    lines.append("  if not h then return 0 end")
    lines.append('  return tonumber(h.hireKm or h["hireKm$"]) or 0')
    lines.append("end")
    lines.append("")
    lines.append("function M.isMentor(heroId)")
    lines.append('  heroId = tostring(heroId or "")')
    lines.append('  if heroId == "" then return false end')
    lines.append("  local h = M.get(heroId)")
    lines.append("  if h and (h.isMentor == true or h.mentor == true) then return true end")
    lines.append("  if M.MENTOR_PRODUCTS[heroId] then return true end")
    lines.append('  local trait = h and tostring(h.heroTrait or h.trait or "") or ""')
    lines.append('  return trait == "wheelie_mentor" or trait == "scout_tech" or trait == "factory_mentor"')
    lines.append("end")
    lines.append("")
    lines.append("function M.mentorProducts(heroId)")
    lines.append('  return M.MENTOR_PRODUCTS[tostring(heroId or "")]')
    lines.append("end")
    lines.append("")
    lines.append("function M.defaultAutoPick()")
    lines.append('  return { "verse", "grath", "odessa" }')
    lines.append("end")
    lines.append("")
    lines.append("return M")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    packs = json.loads(CREW_JSON.read_text(encoding="utf-8-sig"))
    epm = float(packs.get("energyPerMetal") or 70)
    chassis = packs.get("chassis") or {}

    # Refresh every chassis combined from metal/energy.
    for name, row in chassis.items():
        if isinstance(row, dict):
            chassis_combined(chassis, name, epm)

    refresh_anchor_combined(packs, chassis, epm)

    heroes = packs.get("heroes") or {}
    for hid, hero in heroes.items():
        if isinstance(hero, dict):
            resolve_hero(str(hid), hero, packs, chassis, epm)

    # Keep schema note current.
    packs["schemaVersion"] = "verdance-crew-packs/1.6"

    CREW_JSON.write_text(json.dumps(packs, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ROSTER_LUA.write_text(emit_roster_lua(packs), encoding="utf-8")
    EMBED_JS.write_text(
        "window.CREW_PACKS = " + json.dumps(packs, indent=2, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )

    # Report
    rows = []
    for hid, hero in heroes.items():
        if not isinstance(hero, dict) or hero.get("deprecated"):
            continue
        rows.append(
            (
                int(hero.get("packCombined") or 0),
                str(hid),
                str(hero.get("sizing") or "fixed"),
                str(hero.get("massBand") or "-"),
                int(hero.get("massTarget") or 0),
                int(hero.get("packTotal") or 0),
            )
        )
    rows.sort(reverse=True)
    print("hero            combined  sizing      band   target  packTotal")
    for comb, hid, sizing, band, target, n in rows:
        print(f"{hid:<15} {comb:>8}  {sizing:<10} {band:<5} {target:>6}  {n:>9}")
    print(f"wrote {CREW_JSON}")
    print(f"wrote {ROSTER_LUA}")
    print(f"wrote {EMBED_JS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
