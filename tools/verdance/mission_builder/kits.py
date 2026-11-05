"""Unit specs, the company's kits and the enemy camps' rings (port of build_next_mission_v1.ps1).

A spec is one row of a base recipe: ``unitDefName``, ``count`` and an offset (``dx``, ``dz``) from
the force's base, ``spacing`` between the units it places, and optional flags the gadget reads
(``atMetalSpots``, ``patrol``, ``at`` for a baked field's exact positions, hero and commerce stamps).
Everything here is a pure function of its arguments; the field assembly lives in ``field.py``.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from verdance.mission_builder._ps import D, I, S, T, R, arr, eq, g, has, ieq, ilike, imatch

Spec_ = Dict[str, Any]


def each(v: Any) -> List[Any]:
    """``foreach ($x in $v)``: null runs no times, a list runs per element, anything else once."""
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        return list(v)
    return [v]


def props(v: Any) -> List[tuple]:
    """``$v.PSObject.Properties`` of an object read from JSON: its (name, value) pairs in order."""
    if isinstance(v, dict):
        return list(v.items())
    return []


def Spec(Def: Any, Count: Any, Dx: Any, Dz: Any, Spacing: Any = 90, AtSpots: bool = False,
         PatrolX: Any = None, PatrolZ: Any = None, Patrol: Any = None, At: Any = None) -> Spec_:
    s: Spec_ = {"unitDefName": S(Def), "count": max(1, I(Count)), "dx": I(Dx), "dz": I(Dz), "spacing": I(Spacing)}
    if AtSpots:
        s["atMetalSpots"] = True
    # A baked field (Koom's war): flat [x, z, facing, hp%] per unit, x and z normalized. The gadget
    # stands each unit exactly there, as hurt as the war left it.
    if At is not None:
        s["at"] = arr(At)
        s["exact"] = True
    if Patrol is not None:
        s["patrol"] = arr(Patrol)
    elif PatrolX is not None:
        s["patrolX"] = D(PatrolX)
        s["patrolZ"] = D(PatrolZ)
    return s


def scaled_count(base: int, scale: float) -> int:
    """Get-ScaledCount: at least one, the base scaled and rounded half to even."""
    return I(max(1.0, R(base * float(scale))))


def patrol_sweep(px: float, pz: float) -> List[Dict[str, float]]:
    """Two waypoints straddling a screen point: with CMD.PATROL the unit loops spawn -> wp1 -> wp2 ->
    spawn, an actual sweep instead of a one-way clump."""
    px = float(px)
    pz = float(pz)
    return [
        {"x": max(0.03, min(0.97, px - 0.05)), "z": max(0.03, min(0.97, pz + 0.05))},
        {"x": max(0.03, min(0.97, px + 0.05)), "z": max(0.03, min(0.97, pz - 0.05))},
    ]


# --- Faction tables ------------------------------------------------------------------------------

FACTION: Dict[str, Dict[str, Any]] = {
    "Armada": {
        "mex": "armmex", "wind": "armwin", "solar": "armsolar", "advsolar": "armadvsol",
        "llt": "armllt", "hlt": "armbeamer", "aa": "armrl", "radar": "armrad", "wall": "armdrag",
        "mstor": "armmstor", "estor": "armestor", "conv": "armmakr", "lab": "armlab", "nano": "armnanotc",
        "raider": "armpw", "skirm": "armham", "assault": "armwar",
        "bigGun": "armguard", "popup": "armpb", "fus": "armfus", "arad": "armarad", "targ": "armtarg",
        "fort": "armfort", "lrpc": "armbrtha",
        "rgb": [0.25, 0.48, 1.0],
    },
    "Cortex": {
        "mex": "cormex", "wind": "corwin", "solar": "corsolar", "advsolar": "coradvsol",
        "llt": "corllt", "hlt": "corhlt", "aa": "corrl", "radar": "corrad", "wall": "cordrag",
        "mstor": "cormstor", "estor": "corestor", "conv": "cormakr", "lab": "corlab", "nano": "cornanotc",
        "raider": "corak", "skirm": "corthud", "assault": "corstorm",
        "bigGun": "corpun", "popup": "corvipe", "fus": "corfus", "arad": "corarad", "targ": "cortarg",
        "fort": "corfort", "lrpc": "corint",
        "rgb": [1.0, 0.20, 0.16],
    },
}

# Null Mercs field Legion-family scrap-line chassis like the player's clans - outsider tech on both -
# but fly ash-grey null colors. Their camps are lean: quick eco, light teeth, and patrols that press
# the Armada approaches.
MERC: Dict[str, Any] = {
    "mex": "legmex", "wind": "legwin", "solar": "legsolar", "radar": "legrad",
    "llt": "leglht", "mg": "legmg", "aa": "legrl", "wall": "legdrag", "mstor": "legmstor",
    "lab": "leglab", "nano": "legnanotc",
    "raider": "leggat", "skirm": "legcen", "assault": "legjav",
    "rgb": [0.63, 0.62, 0.66],
}


def faction(side: Any) -> Optional[Dict[str, Any]]:
    """``$FACTION[$Side]``: the hashtable lookup ignores case; a miss is null."""
    for k, v in FACTION.items():
        if ieq(k, side):
            return v
    return None


# --- The company's kits -------------------------------------------------------------------------

def add_commerce_deploy_to_kit(kit: List[Spec_], commerce: Any) -> List[Spec_]:
    """WO-043: broker deployables (loan packs, Crash of Brutes, Cortex grunt fab printer, faction
    constructors, fab nanos).

    SPAWN RULE (one owner): in BAR these units are spawned ONCE, by VA_LOGISTICS.spawnCommerceDeployKit
    in game_verdance_campaign.lua, straight from mission.commerce.deploy. The copies composed into the
    player kit here are for the layout / previews only; every one of them is stamped commerceDeploy=true
    plus a packageTag, and the gadget's setup spawn skips any spec carrying that stamp
    (VA_CREW_isCommerceKitSpec). An untagged nano or constructor used to pass the gadget's anchor-keep
    filter and land twice.
    """
    kit = list(kit)
    if not T(commerce) or not has(commerce, "deploy"):
        return kit
    deploy = arr(commerce.get("deploy"))
    if len(deploy) == 0:
        return kit
    i = 0
    for d in deploy:
        if not T(d):
            continue
        kind = S(g(d, "kind")) if T(g(d, "kind")) else "package"
        ox = -200 + (55 * (i % 5))
        oz = -280 - (40 * math.floor(i / 5))
        # Same fallback id the gadget uses for an unlisted item (kit_<1-based index>).
        if T(g(d, "packageTag")):
            tag = S(g(d, "packageTag"))
        elif T(g(d, "listingId")):
            tag = S(g(d, "listingId"))
        else:
            tag = "kit_" + str(i + 1)
        if ieq(kind, "unit_printer"):
            fac = S(g(d, "factoryDef")) if T(g(d, "factoryDef")) else "corlab"
            product = S(g(d, "product")) if T(g(d, "product")) else "corak"
            printer = Spec(fac, 1, ox - 40, oz + 20, 100)
            printer["unitPrinter"] = True
            printer["printerProduct"] = product
            printer["printerMetalIncome"] = D(g(d, "metalIncome")) if g(d, "metalIncome") is not None else 8
            printer["printerEnergyIncome"] = D(g(d, "energyIncome")) if g(d, "energyIncome") is not None else 40
            printer["packageTag"] = tag
            printer["commerceDeploy"] = True
            kit.append(printer)
            seed = max(0, I(g(d, "seedCount"))) if g(d, "seedCount") is not None else 4
            if seed > 0:
                seed_spec = Spec(product, seed, ox + 80, oz, 70)
                seed_spec["packageTag"] = tag + "_seed"
                seed_spec["commerceDeploy"] = True
                kit.append(seed_spec)
        elif ieq(kind, "nano"):
            ndef = S(g(d, "unitDef")) if T(g(d, "unitDef")) else "cornanotc"
            nc = max(1, I(g(d, "count"))) if g(d, "count") is not None else 1
            n_spec = Spec(ndef, nc, ox - 80, oz + 40, 90)
            n_spec["packageTag"] = tag
            n_spec["commerceDeploy"] = True
            kit.append(n_spec)
        elif ieq(kind, "constructor"):
            cdef = S(g(d, "unitDef")) if T(g(d, "unitDef")) else "armck"
            cc = max(1, I(g(d, "count"))) if g(d, "count") is not None else 1
            c_spec = Spec(cdef, cc, ox, oz + 60, 90)
            c_spec["packageTag"] = tag
            c_spec["commerceDeploy"] = True
            kit.append(c_spec)
        else:
            # package / loan pack
            udef = S(g(d, "unitDef")) if T(g(d, "unitDef")) else None
            cnt = max(1, I(g(d, "count"))) if g(d, "count") is not None else 1
            if not T(udef):
                continue
            p_spec = Spec(udef, cnt, ox, oz, 85)
            if g(d, "healthFrac") is not None:
                p_spec["healthFrac"] = D(g(d, "healthFrac"))
            if g(d, "healthFracMin") is not None:
                p_spec["healthFracMin"] = D(g(d, "healthFracMin"))
            if g(d, "healthFracMax") is not None:
                p_spec["healthFracMax"] = D(g(d, "healthFracMax"))
            if eq(g(d, "loan"), True) or eq(g(d, "loan"), 1):
                p_spec["loanPackage"] = True
            p_spec["packageTag"] = tag
            p_spec["commerceDeploy"] = True
            kit.append(p_spec)
        i += 1
    return kit


def _family_switch(family: str, table: Dict[str, Any], default: Any = None) -> Any:
    for k, v in table.items():
        if ieq(family, k):
            return v
    return default


def tactics_player_kit(family: str, roster: Any, resource_mod: float = 1.0, unit_printer: Any = None,
                       commerce: Any = None) -> List[Spec_]:
    """Arc A/B ground-tactics kit: NO commander. Same doctrine as strike team: Wheelies + Phobos army
    + rez bots. No Ballistas (missile bots). Vane = Karkinos."""
    del roster, resource_mod
    kit = [
        Spec("legrad", 1, 40, -60, 100),
        Spec("leglht", 2, -120, -120, 130),
        Spec("legscout", 4, -60, 130, 90),
        Spec("legcen", 10, 80, -210, 85),
        Spec("legkark", 1, 140, -180, 100),
        Spec("legrezbot", 5, -170, 60, 80),
    ]
    # Thin metal trickle so rez bots can work; not a full expand base.
    kit += [
        Spec("legmex", 1, -140, 120, 120, True),
        Spec("legwin", 2, 120, 160, 90),
    ]
    # WO-033: unit printer - lab locked to Phobos (gadget enforces). Skip the default legion printer
    # when commerce already fields a bought Cortex grunt fab.
    has_commerce_printer = False
    if T(commerce) and has(commerce, "deploy"):
        for d in each(arr(commerce.get("deploy"))):
            if T(d) and ieq(S(g(d, "kind")), "unit_printer"):
                has_commerce_printer = True
                break
    if T(unit_printer) and T(g(unit_printer, "def")) and not has_commerce_printer:
        p_count = 1
        if g(unit_printer, "count") is not None:
            p_count = max(1, I(g(unit_printer, "count")))
        printer = Spec(S(g(unit_printer, "def")), p_count, -220, 40, 100)
        printer["unitPrinter"] = True
        printer["printerProduct"] = S(g(unit_printer, "product")) if T(g(unit_printer, "product")) else "legcen"
        printer["printerMetalIncome"] = D(g(unit_printer, "metalIncome")) if g(unit_printer, "metalIncome") is not None else 10
        printer["printerEnergyIncome"] = D(g(unit_printer, "energyIncome")) if g(unit_printer, "energyIncome") is not None else 50
        kit.append(printer)
        # Seed a few Phobos so player is not waiting on the first print.
        kit.append(Spec(printer["printerProduct"], 6, 100, -100, 70))
    kit = add_commerce_deploy_to_kit(kit, commerce)
    tail = _family_switch(family, {
        "tempo": lambda: Spec("legcen", 2, -60, -260, 90),
        "siege": lambda: Spec("legcen", 2, -200, -200, 90),
        "wild": lambda: Spec("leglht", 1, 200, -140, 130),
    }, lambda: Spec("legcen", 2, 140, -260, 90))
    kit.append(tail())
    # Heroes sealed by hub muster / gadget packs: do not bake the roster into the seed.
    return kit


def cadre_xp_bag(roster: Any, def_name: str) -> Optional[Dict[str, float]]:
    """roster.cadreXp[def] -> seed xp / craftXp for the next drop."""
    if not T(roster) or not T(def_name):
        return None
    bank = None
    if has(roster, "cadreXp") and T(roster.get("cadreXp")):
        bank = roster["cadreXp"]
    if not T(bank):
        return None
    bag = None
    if isinstance(bank, dict):
        # PSObject property lookup ignores case.
        for k, v in bank.items():
            if ieq(k, def_name):
                bag = v
                break
    if not T(bag):
        return None
    xp = 0.0
    craft = 0.0
    if g(bag, "xp") is not None:
        xp = D(g(bag, "xp"))
    elif g(bag, "avgXp") is not None:
        xp = D(g(bag, "avgXp"))
    elif g(bag, "peakXp") is not None:
        xp = D(g(bag, "peakXp")) * 0.85
    if g(bag, "craftXp") is not None:
        craft = D(g(bag, "craftXp"))
    elif g(bag, "avgCraftXp") is not None:
        craft = D(g(bag, "avgCraftXp"))
    if xp <= 0 and craft <= 0:
        return None
    return {"xp": xp, "craftXp": craft}


def set_spec_cadre_xp(spec: Any, roster: Any) -> Any:
    if not T(spec) or not T(roster):
        return spec
    # Named heroes carry their own xp via the heroId path: do not overwrite.
    if T(g(spec, "heroId")):
        return spec
    bag = cadre_xp_bag(roster, S(g(spec, "unitDefName")))
    if not T(bag):
        return spec
    if bag["xp"] > 0:
        spec["xp"] = D(bag["xp"])
    if bag["craftXp"] > 0:
        spec["craftXp"] = D(bag["craftXp"])
    return spec


def apply_cadre_xp_to_kit(kit: List[Spec_], roster: Any) -> List[Spec_]:
    """Stamp banked veteran XP onto every non-hero kit unit so BAR SetUnitExperience restores the
    majority of field XP between rounds."""
    return [set_spec_cadre_xp(s, roster) for s in each(kit) if T(s)]


def add_reserve_to_kit(kit: List[Spec_], roster: Any) -> List[Spec_]:
    """The company's reserve: roster.cadre is what the player chose to bring this drop (the hub's
    Reserve panel, clamped to the lift limit in Python). Every kit gets it the same way, all of it,
    any unit type but a commander."""
    if not T(roster) or not T(g(roster, "cadre")):
        return kit
    kit = list(kit)
    i = 0
    for name, value in props(roster["cadre"]):
        def_name = S(name)
        cnt = I(value)
        if cnt > 0 and not imatch(def_name, r"^(arm|cor|leg)com$"):
            r = Spec(def_name, cnt, -130 - 70 * (i % 3), -160 - 70 * math.floor(i / 3), 90)
            r["reserve"] = True  # the gadget lands reserve specs with the company
            kit.append(r)
            i += 1
    return kit


def add_hero_specs(kit: List[Spec_], heroes: Any) -> List[Spec_]:
    """Pillar C heroes: named Fire-Emblem roster units riding with the kit. Each hero replaces one
    generic unit of its type when possible so total force size stays balance-neutral. Cracked-farm
    carries level/rank into the seed."""
    kit = list(kit)
    if not T(heroes):
        return kit
    i = 0
    for h in each(heroes):
        # Locked / reserved contracts (e.g. Spoke) do not deploy until unlocked.
        if ieq(S(g(h, "status")), "locked"):
            continue
        def_name = S(g(h, "unitDef"))
        hid = S(g(h, "heroId"))
        name = S(g(h, "name"))
        # Alpha opening roles: Vane is the named Phobos (legcen) striker and Ketha is the named field
        # rez-bot. Neither role is a commander suit.
        if ieq(hid, "vane") or imatch(name, "Vane"):
            def_name = "legcen"
        if ieq(hid, "ketha") or imatch(name, "Ketha"):
            def_name = "legrezbot"
        # Spoke: wheelie scout tech specialist
        if ieq(hid, "spoke") or ieq(S(g(h, "trait")), "wheelie_mentor"):
            def_name = "legscout"
        if not def_name or ilike(def_name, "*com"):
            def_name = "legkark"
        for s in kit:
            if ieq(g(s, "unitDefName"), def_name) and I(g(s, "count")) > 1:
                s["count"] = I(s["count"]) - 1
                break
        spec = Spec(def_name, 1, -40 + 90 * i, 50 + 45 * i, 100)
        spec["heroId"] = S(g(h, "heroId"))
        spec["heroName"] = name
        spec["missionCritical"] = T(g(h, "missionCritical"))
        spec["heroHpMult"] = D(g(h, "hpMult")) if g(h, "hpMult") is not None else 1.4
        if ieq(hid, "ketha") or imatch(name, "Ketha"):
            spec["heroHpMult"] = max(2.5, D(spec["heroHpMult"]))
            spec["heroBuildPowerMult"] = 3.0
            spec["heroRole"] = "field_rez_support"
        elif ieq(hid, "vane") or imatch(name, "Vane"):
            spec["heroRole"] = "phobos_striker"
        spec["heroXp"] = D(g(h, "xp")) if g(h, "xp") is not None else 0.25
        if g(h, "level") is not None:
            spec["heroLevel"] = I(g(h, "level"))
        if g(h, "rank") is not None:
            spec["heroRank"] = S(g(h, "rank"))
        if g(h, "campaignXp") is not None:
            spec["heroCampaignXp"] = D(g(h, "campaignXp"))
        if T(g(h, "trait")):
            spec["heroTrait"] = S(g(h, "trait"))
        if T(g(h, "traits")):
            spec["heroTraits"] = arr(g(h, "traits"))
        kit.append(spec)
        i += 1
    return kit


def player_kit(family: str) -> List[Spec_]:
    kit = [
        Spec("legmex", 3, -140, 120, 120, True),
        Spec("legwin", 4, 120, 160, 90),
        Spec("legsolar", 2, 240, 80, 90),
        Spec("legrad", 1, 40, -60, 100),
        Spec("leglht", 2, -120, -120, 130),
        Spec("legmg", 1, 60, -160, 100),
        Spec("legcen", 3, 80, -210, 95),
        Spec("legjav", 2, 260, -230, 110),
    ]
    extra = _family_switch(family, {
        "economy": lambda: [Spec("legck", 2, 180, 240, 90), Spec("legwin", 2, 320, 200, 85)],
        "tempo": lambda: [Spec("leggat", 2, -60, -260, 90), Spec("legcen", 1, 140, -260, 95)],
        "siege": lambda: [Spec("legjav", 2, -200, -200, 110), Spec("legrl", 1, -40, -60, 100)],
        "wild": lambda: [Spec("legmg", 1, -180, -60, 100), Spec("leglht", 1, 200, -140, 130)],
    })
    if extra:
        kit += extra()
    return kit


def player_kit_from_roster(family: str, roster: Any, resource_mod: float = 1.0, commerce: Any = None) -> List[Spec_]:
    """Economy floor plus the veteran cadre. The commander, when the arc allows one, is BAR's single
    start unit. This kit must not spawn a second legcom."""
    # q7 scarcity thins the economy floor (resourceModifier from the graph).
    wind = max(2, I(R(4 * float(resource_mod))))
    kit = [
        Spec("legmex", 3, -140, 120, 120, True),
        Spec("legwin", wind, 120, 160, 90),
        Spec("legsolar", 2, 240, 80, 90),
        Spec("legrad", 1, 40, -60, 100),
    ]
    cadre_total = 0
    if T(g(roster, "cadre")):
        for name, value in props(roster["cadre"]):
            cnt = I(value)
            if cnt > 0 and not imatch(S(name), r"^(arm|cor|leg)com"):
                cadre_total += cnt  # spawned by add_reserve_to_kit
    # Floor: a thin cadre (fresh campaign or a rout) still fields a minimum strike element.
    if cadre_total < 4:
        kit.append(Spec("legcen", 4 - cadre_total, 80, -210, 95))
    active: List[Any] = []
    commander = g(roster, "commander")
    if T(commander) and T(g(commander, "activePerks")):
        active = arr(g(commander, "activePerks"))
    if iin_list("rapid_deploy", active):
        kit.append(Spec("legjav", 1, 200, -230, 110))
    extra = _family_switch(family, {
        "economy": lambda: Spec("legck", 1, 180, 240, 90),
        "tempo": lambda: Spec("leggat", 1, -60, -260, 90),
        "siege": lambda: Spec("legrl", 1, -40, -60, 100),
        "wild": lambda: Spec("leglht", 1, 200, -140, 130),
    })
    if extra:
        kit.append(extra())
    # A rez bot rides with every warband: hero wrecks must be recoverable.
    kit.append(Spec("legrezbot", 1, -170, 60, 80))
    return add_commerce_deploy_to_kit(kit, commerce)


def iin_list(needle: str, haystack: List[Any]) -> bool:
    """``$list -contains "x"``: case-insensitive for strings."""
    return any(isinstance(x, str) and x.lower() == needle.lower() for x in haystack)


def finale_kit_from_roster(family: str, roster: Any, resource_mod: float = 1.0, commerce: Any = None) -> List[Spec_]:
    """Drop 2 Act 3: massive starting conditions; the whole campaign walks out. Established economy +
    factory floor + defenses + a real army, then every living hero. One commander only: BAR's start
    unit, not a second spec in this kit."""
    del family, resource_mod
    kit = [
        Spec("legmex", 5, -160, 130, 120, True),
        Spec("legwin", 10, 140, 180, 85),
        Spec("legsolar", 6, 260, 90, 90),
        Spec("legmstor", 1, 60, 250, 100),
        Spec("legrad", 2, 40, -60, 160),
        Spec("leglab", 1, -300, -140, 130),
        Spec("legnanotc", 3, -210, -230, 90),
        Spec("legdrag", 10, -60, -320, 40),
        Spec("leglht", 4, -140, -140, 140),
        Spec("legmg", 2, 60, -170, 110),
        Spec("legrl", 2, -40, -80, 150),
        Spec("legscout", 6, -70, 140, 85),
        Spec("legcen", 16, 90, -220, 80),
        Spec("leggat", 6, -90, -260, 90),
        Spec("legjav", 6, 240, -240, 100),
        Spec("legkark", 2, 170, 40, 110),
        Spec("legrezbot", 6, -170, 70, 80),
    ]
    kit = add_commerce_deploy_to_kit(kit, commerce)
    # Finale: still spawn named heroes from the roster (the full company walks out).
    heroes = roster.get("heroes") if (T(roster) and has(roster, "heroes")) else None
    return add_hero_specs(kit, heroes)


def opening_strike_team(commerce: Any) -> List[Spec_]:
    """Mission one is a mercenary pre-bought punch, not a persistent commander deployment. Kept
    explicit so progressed or stale campaign state cannot leak a second commander, Incinerator, or
    generic Javelins into the opener."""
    vane = Spec("legcen", 1, -70, -80, 90)
    vane["heroId"] = "vane"
    vane["heroName"] = "Ash-Captain Vane"
    vane["heroRole"] = "phobos_striker"
    vane["heroHpMult"] = 1.65
    vane["heroXp"] = 0.25

    ketha = Spec("legrezbot", 1, -150, 70, 80)
    ketha["heroId"] = "ketha"
    ketha["heroName"] = "Ketha"
    ketha["heroRole"] = "field_rez_support"
    ketha["heroHpMult"] = 2.5
    ketha["heroBuildPowerMult"] = 3.0
    ketha["heroXp"] = 0.05

    kit = [Spec("legkark", 2, 120, 20, 105), vane, ketha, Spec("legrezbot", 5, -150, 70, 80)]
    # Buy-everything: no free Punch. Owned packs (Punch, Crash, fabs, constructors) ride only via
    # commerce.deploy -> add_commerce_deploy_to_kit / gadget logistics.
    return add_commerce_deploy_to_kit(kit, commerce)


# --- Enemy camp rings ---------------------------------------------------------------------------
# Camps are assembled from faction rings (eco / perimeter / production / patrol) around an objective
# CENTERPIECE. Only the centerpiece force carries role=objective_target, so destruction missions are
# surgical strikes into a defended camp instead of base-wipes.

def ring_eco(t: Dict[str, Any], s: float) -> List[Spec_]:
    return [
        Spec(t.get("mex"), 4, -160, 120, 120, True),
        Spec(t.get("wind"), scaled_count(4, s), 140, 170, 85),
        Spec(t.get("solar"), scaled_count(2, s), 260, 60, 95),
        Spec(t.get("mstor"), 1, 60, 240, 100),
        Spec(t.get("conv"), scaled_count(2, s), 320, 170, 95),
    ]


def ring_perimeter(t: Dict[str, Any], s: float, fx: int, fz: int) -> List[Spec_]:
    # FX/FZ point from the camp toward the player: defenses face the approach.
    return [
        Spec(t.get("llt"), scaled_count(4, s), 170 * fx, 150 * fz, 150),
        Spec(t.get("wall"), scaled_count(8, s), 270 * fx, 240 * fz, 40),
        Spec(t.get("aa"), 2, -90 * fx, 60 * fz, 170),
        Spec(t.get("radar"), 1, 0, -80, 100),
    ]


def ring_production(t: Dict[str, Any]) -> List[Spec_]:
    return [Spec(t.get("lab"), 1, -300, -150, 120), Spec(t.get("nano"), 2, -210, -240, 90)]


def ring_patrol(t: Dict[str, Any], s: float, px: float, pz: float, front_band: bool = False) -> List[Spec_]:
    # WO-004: front-band sorties field a thin screen at start; packs arrive as waves.
    sweep = patrol_sweep(px, pz)
    if front_band:
        return [
            Spec(t.get("raider"), scaled_count(3, s), 120, -300, 80, Patrol=sweep),
            Spec(t.get("skirm"), scaled_count(2, s), -140, -320, 90, Patrol=sweep),
            Spec(t.get("assault"), scaled_count(1, s), 20, -390, 95, Patrol=sweep),
        ]
    return [
        Spec(t.get("raider"), scaled_count(4, s), 120, -300, 80, Patrol=sweep),
        Spec(t.get("skirm"), scaled_count(3, s), -140, -320, 90, Patrol=sweep),
        Spec(t.get("assault"), scaled_count(3, s), 20, -390, 95, Patrol=sweep),
    ]


def ring_fortify(t: Dict[str, Any], fx: int, fz: int) -> List[Spec_]:
    return [
        Spec(t.get("hlt"), 2, 110 * fx, -70 * fz, 180),
        Spec(t.get("popup"), 1, 200 * fx, 120 * fz, 100),
        Spec(t.get("bigGun"), 1, -50, 40, 100),
    ]


def ring_jammers(t: Dict[str, Any]) -> List[Spec_]:
    """Cortex hideout flavor: radar jammer towers + a cloaking field so the base reads as hidden until
    you are on top of it (eye_of_horus)."""
    del t
    return [
        Spec("corjamt", 2, -60, 120, 160),
        Spec("corjamt", 1, 180, -40, 160),
        Spec("corshroud", 1, 0, -30, 100),
    ]


def centerpiece_lrpc(t: Dict[str, Any]) -> List[Spec_]:
    return [Spec(t.get("lrpc"), 1, 0, 0, 100)]


def support_lrpc(t: Dict[str, Any]) -> List[Spec_]:
    return [Spec(t.get("fus"), 1, 140, 80, 110), Spec(t.get("fort"), 6, -90, -120, 42)]


def centerpiece_command_post(t: Dict[str, Any]) -> List[Spec_]:
    return [Spec(t.get("arad"), 1, 0, 0, 100), Spec(t.get("fus"), 1, 130, 60, 110), Spec(t.get("hlt"), 1, -110, -60, 120)]


def centerpiece_hives(hazard: float) -> List[Spec_]:
    """Two roosts and the Queen's Nest. Burning the roosts is fine; the queen wakes when her nest falls
    (or her anger fills), never because the roost count ran low (raptor_spawner_defense.lua)."""
    del hazard
    return [
        Spec("raptor_hive", 1, -120, -40, 240),
        Spec("raptor_hive", 1, 140, 80, 240),
        Spec("va_queen_nest", 1, 0, -240, 300),
    ]


def merc_foothold(s: float, px: float, pz: float, fx: int, fz: int, ally_power: float = 1.0) -> List[Spec_]:
    """WO-038: allyPower scales the kit. High = javelin shred (M1 adjunct). Low = light guns."""
    p = max(0.1, min(1.0, float(ally_power)))
    specs = [
        Spec(MERC["radar"], 1, 0, -70, 100),
        Spec(MERC["llt"], scaled_count(max(1, I(3 * p)), s), 160 * fx, 140 * fz, 150),
        Spec(MERC["raider"], scaled_count(max(1, I(3 * p)), s), 110, -290, 80, Patrol=patrol_sweep(px, pz)),
        Spec(MERC["skirm"], scaled_count(max(1, I(2 * p)), s), -130, -310, 90, Patrol=patrol_sweep(px, pz)),
    ]
    # Keep the foothold readable as a SimpleAI builder. Do not leak the old generic Javelin blob into
    # the opener; named Phobos Vane is the only elite assault signature in the first sortie.
    if p >= 0.7:
        specs.append(Spec(MERC["skirm"], scaled_count(2, s), 10, -370, 95, Patrol=patrol_sweep(px, pz)))
        specs.append(Spec(MERC["mg"], 1, 230 * fx, 90 * fz, 110))
        specs.append(Spec(MERC["lab"], 1, -290, -140, 120))
        specs.append(Spec(MERC["nano"], 1, -200, -230, 90))
        specs.append(Spec(MERC["mex"], 2, -140, 110, 120, True))
        specs.append(Spec(MERC["wind"], scaled_count(3, s), 130, 160, 85))
    elif p >= 0.4:
        specs.append(Spec(MERC["skirm"], 1, 10, -370, 95, Patrol=patrol_sweep(px, pz)))
        specs.append(Spec(MERC["aa"], 1, -80 * fx, 60 * fz, 160))
        specs.append(Spec(MERC["mex"], 1, -140, 110, 120, True))
        specs.append(Spec(MERC["wind"], 2, 130, 160, 85))
    else:
        # Peer/strike-lead: thin support screen, no lab, no javelin blob.
        specs.append(Spec(MERC["aa"], 1, -80 * fx, 60 * fz, 160))
        specs.append(Spec(MERC["mg"], 1, 230 * fx, 90 * fz, 110))
    return specs


def ring_raptor_garrison(hazard: float) -> List[Spec_]:
    swarm_scale = 1.0 + (2.0 * max(0.0, min(1.0, float(hazard))))
    return [
        Spec("raptor_turret_basic_t2_v1", 3, -140, 90, 150),
        Spec("raptor_land_swarmer_basic_t1_v1", scaled_count(10, swarm_scale), 130, -100, 70),
        Spec("raptor_land_swarmer_basic_t2_v1", scaled_count(4, swarm_scale), -200, -150, 80),
    ]


def scatter(def_name: str, total: int, spread: float = 520, per_cluster: int = 2, phase: int = 0,
            spacing: int = 60, at_spots: bool = False) -> List[Spec_]:
    """Several small specs of one def spread deterministically (golden-angle spiral, no RNG) so
    buildings read as organic sprawl rather than a tidy grid."""
    specs: List[Spec_] = []
    if not def_name or total <= 0:
        return specs
    clusters = max(1.0, math.ceil(total / float(per_cluster)))
    placed = 0
    i = 0
    while placed < total:
        n = min(per_cluster, total - placed)
        ang = (i * 2.399963) + (phase * 0.7)
        rad = spread * math.sqrt((i + 0.5) / clusters)
        dx = I(R(rad * math.cos(ang)))
        dz = I(R(rad * math.sin(ang)))
        specs.append(Spec(def_name, n, dx, dz, spacing, at_spots))
        placed += n
        i += 1
    return specs


def baked_specs(units: Any) -> List[Spec_]:
    """Baked units ([def, x, z, facing, hp, ...] rows from a war snapshot or a scout camp) as one exact
    spec per unit type: positions flat x z facing hp, placed where the bake left them."""
    by_def: Dict[str, List[float]] = {}
    keys: Dict[str, str] = {}
    for u in each(arr(units)):
        d = S(u[0])
        k = d.lower()  # [ordered]@{} keys ignore case
        if k not in by_def:
            by_def[k] = []
            keys[k] = d
        by_def[k] += [D(u[1]), D(u[2]), D(u[3]), D(u[4])]
    return [Spec(keys[k], I(len(v) / 4), 0, 0, 0, False, None, None, None, v) for k, v in by_def.items()]
