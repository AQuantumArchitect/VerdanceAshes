"""The living shell: an enemy occupation baked into a template, thinned by what the campaign remembers.

Port of the living-shell half of scripts/build_next_mission_v1.ps1: which template a map uses, the
scar sets the campaign state yields (claimed pads, zone memory, the destroyed-units ledger, dead
fusion vaults), the shell payload built from the template, and the company's own footprint merged
back onto it. Functions here read the workspace and the state they are given and touch nothing else;
the teams and forces a shell brings onto the field are added in ``field.py``.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from verdance.mission_builder._ps import CIDict, D, I, S, T, arr, eq, fmt, g, has, ieq, iin, imatch, ilike
from verdance.mission_builder.kits import each, props, scatter

Log = Callable[[str], None]


def read_json(path: Path) -> Any:
    """Get-Content -Raw | ConvertFrom-Json.

    Windows PowerShell 5.1 decodes a file without a BOM as the ANSI code page, so non-ASCII text in a
    BOM-less UTF-8 file read as mojibake on the PC. None of that text reaches the scenario today (the
    only such strings the builder opens are crew_packs.json "fiction"/"blurb" lines and a Rock Jungle
    template's "growMix" note, none of which it copies), so the port reads UTF-8 and does not copy
    that fault.
    """
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def ci_get(obj: Any, name: Any) -> Any:
    """``$obj.$name`` with a computed name: PSObject property lookup ignores case."""
    if isinstance(obj, CIDict):
        return obj.get(name)
    if not isinstance(obj, dict) or name is None:
        return None
    key = S(name)
    if key in obj:
        return obj[key]
    low = key.lower()
    for k, v in obj.items():
        if k.lower() == low:
            return v
    return None


def ci_has(obj: Any, name: Any) -> bool:
    """``$obj.PSObject.Properties[$name]`` with a computed name, ignoring case."""
    if not isinstance(obj, dict) or name is None:
        return False
    low = S(name).lower()
    return any(k.lower() == low for k in obj)


def template_path(ws: Path, map_id: str) -> Optional[Path]:
    """Resolve-LivingShellTemplatePath: the real bake first, then map-specific placeholders, then any
    non-recipe shell json."""
    d = Path(ws) / "data" / "base_templates" / map_id
    if not d.exists():
        return None
    for name in ("armada_t15_v1.json", "living_shell_v1.json", "cortex_core_v1.json",
                 "armada_placeholder_v1.json", "living_placeholder_v1.json"):
        p = d / name
        if p.exists():
            return p
    try:
        files = sorted((p for p in d.iterdir() if p.is_file()), key=lambda p: p.name.lower())
    except OSError:
        return None
    for p in files:
        if ilike(p.name, "*placeholder*.json"):
            return p
    for p in files:
        if ilike(p.name, "*.json") and not ieq(p.name, "bake_recipe.json"):
            return p
    return None


def high_value_def(def_name: str) -> bool:
    """Fusion makers: the optional high-value prize core."""
    if not def_name:
        return False
    n = def_name.lower()
    return bool(re.search("fus", n) or re.search("fusion", n) or re.search("afus", n) or re.search("cafus", n))


def high_value_adjacent_def(def_name: str) -> bool:
    """Beamers / anni sit on GF fusion vaults; destroying the ring is vault death."""
    if not def_name:
        return False
    n = def_name.lower()
    if high_value_def(n):
        return True
    return bool(re.search("beamer", n) or re.search("annihilator", n) or re.search("^arman[ni]", n)
                or re.search("cordoom", n))


def destroyed_high_value_pockets(state: Any, map_id: str) -> CIDict:
    """Get-DestroyedHighValuePockets: a fusion vault is gone when the maker died, the beamer ring died
    hard, heldInstallations says destroyed, or a bonus_fus_* secondary completed."""
    dead = CIDict()
    if not T(state) or not map_id:
        return dead
    bucket = None
    if has(state, "shellScars") and T(state["shellScars"]):
        bucket = ci_get(state["shellScars"], map_id)
    units: List[Any] = []
    if T(bucket) and T(g(bucket, "units")):
        units = arr(bucket["units"])
    adjacent = CIDict()
    for rec in units:
        if not T(rec):
            continue
        if eq(g(rec, "destroyed"), False):
            continue
        def_name = S(g(rec, "unitDefName") if T(g(rec, "unitDefName")) else "")
        pocket = S(g(rec, "pocketId") if T(g(rec, "pocketId")) else "")
        if not pocket:
            continue
        flagged = has(rec, "highValue") and T(rec["highValue"])
        if high_value_def(def_name):
            dead[pocket] = True
            continue
        if flagged or high_value_adjacent_def(def_name):
            if pocket not in adjacent:
                adjacent[pocket] = 0
            adjacent[pocket] = I(adjacent[pocket]) + 1
    # Beamer ring wipe: enough HV-adjacent destroys on the pocket means the vault is dead.
    for pocket in adjacent.keys():
        if I(adjacent[pocket]) >= 3:
            dead[pocket] = True
    # Held installs explicitly marked lost also count.
    if has(state, "heldInstallations") and T(state["heldInstallations"]):
        held = ci_get(state["heldInstallations"], map_id)
        if T(held):
            for name, rec in props(held):
                if T(rec) and ieq(S(g(rec, "status")), "destroyed"):
                    pocket = S(g(rec, "pocketId") if T(g(rec, "pocketId")) else name)
                    if pocket:
                        dead[pocket] = True
    # Completed bonus_fus secondaries from the processed results / history.
    hist: List[Any] = []
    if has(state, "history") and T(state["history"]):
        hist = arr(state["history"])
    for h in hist:
        if not T(h):
            continue
        h_map = S(g(h, "mapId") if T(g(h, "mapId")) else "")
        if h_map and not ieq(h_map, map_id):
            continue
        secs: List[Any] = []
        if has(h, "secondaryResults") and T(h["secondaryResults"]):
            secs = arr(h["secondaryResults"])
        for sr in secs:
            if not T(sr):
                continue
            if T(g(sr, "id")):
                sid = S(sr["id"])
            elif T(g(sr, "objectiveId")):
                sid = S(sr["objectiveId"])
            else:
                sid = ""
            if not ilike(sid, "bonus_fus_*"):
                continue
            done = False
            if eq(g(sr, "completed"), True):
                done = True
            if g(sr, "destroyed") is not None and I(sr["destroyed"]) > 0:
                done = True
            if g(sr, "destroyedCount") is not None and I(sr["destroyedCount"]) > 0:
                done = True
            if not done:
                continue
            pocket = S(g(sr, "pocketId")) if T(g(sr, "pocketId")) else re.sub("^bonus_fus_", "", sid, flags=re.IGNORECASE)
            if pocket:
                dead[pocket] = True
    return dead


_PLAYER_BLOC = ("ashwalkers", "nullmercs")


def scarred_zone_set(state: Any, map_id: str) -> CIDict:
    """Get-ScarredZoneSet: continuity. Pads the player already claimed or scarred must not fully
    respawn."""
    scarred = CIDict()
    if not T(state) or not map_id:
        return scarred
    claimed = None
    if has(state, "claimedNodes") and T(state["claimedNodes"]):
        claimed = ci_get(state["claimedNodes"], map_id)
    if T(claimed):
        for name, rec in props(claimed):
            if T(rec) and (T(g(rec, "pocketCleared")) or T(g(rec, "nodeClaimed"))):
                scarred[S(name)] = {"reason": "claimed", "scar": 1.0}
    zm = None
    if has(state, "zoneMemory") and T(state["zoneMemory"]):
        zm = ci_get(state["zoneMemory"], map_id)
    if T(zm):
        for name, mem in props(zm):
            zid = S(name)
            if not T(mem):
                continue
            ctrl = S(g(mem, "controllingFaction") if T(g(mem, "controllingFaction")) else "")
            scar = 0.0
            abstract = g(mem, "abstract")
            if T(abstract) and g(abstract, "shellScar") is not None:
                scar = D(abstract["shellScar"])
            if iin(ctrl, _PLAYER_BLOC) or scar >= 0.25:
                if zid not in scarred:
                    scarred[zid] = {"reason": "player_bloc" if iin(ctrl, _PLAYER_BLOC) else "shell_scar",
                                    "scar": max(scar, 0.25)}
    ledger = None
    if has(state, "shellScars") and T(state["shellScars"]):
        bucket = ci_get(state["shellScars"], map_id)
        if T(bucket) and T(g(bucket, "byZone")):
            ledger = bucket["byZone"]
    if T(ledger):
        for name, z in props(ledger):
            destroyed = 0
            if T(z) and g(z, "destroyedCount") is not None:
                destroyed = I(z["destroyedCount"])
            # Ambient zone thin only: the exact unitDef+pocket suppress lives in scar_suppress_set.
            # Keep >= 3 so a single stray kill does not haze the whole pad.
            if destroyed >= 3:
                scarred[S(name)] = {"reason": "destroyed_ledger", "scar": min(1.0, 0.2 * destroyed)}
    # Vivarium: the world remembers, and has the last word over the ledger's partial thinning. Ground
    # the company or the Mercs hold is ours (player_bloc); ground the campaign says no empire holds
    # (cleared, empty, wild) is vacant and gets no enemy base from the template. Anyone who comes back
    # was moved there by the simulation, and is in zoneMemory as holder.
    if T(zm):
        for name, mem in props(zm):
            if not T(mem):
                continue
            ctrl = S(g(mem, "controllingFaction") if T(g(mem, "controllingFaction")) else "")
            if not ctrl:
                continue
            if iin(ctrl, _PLAYER_BLOC):
                scarred[S(name)] = {"reason": "player_bloc", "scar": 1.0}
            elif not iin(ctrl, ("armada", "cortex")):
                scarred[S(name)] = {"reason": "vacant", "scar": 1.0}
    return scarred


def scar_suppress_set(state: Any, map_id: str) -> CIDict:
    """Get-ScarSuppressSet: exact burned pads, unitDefName|pocketId (fallback unitDefName|zoneId).
    Light raids that never cross destroyed >= 3 still stay burned on re-Drop."""
    suppress = CIDict()
    if not T(state) or not map_id:
        return suppress
    bucket = None
    if has(state, "shellScars") and T(state["shellScars"]):
        bucket = ci_get(state["shellScars"], map_id)
    units: List[Any] = []
    if T(bucket) and T(g(bucket, "units")):
        units = arr(bucket["units"])
    for rec in units:
        if not T(rec):
            continue
        if eq(g(rec, "destroyed"), False):
            continue
        def_name = S(g(rec, "unitDefName") if T(g(rec, "unitDefName")) else "")
        if not def_name:
            continue
        key = def_name.lower()
        pocket = S(g(rec, "pocketId") if T(g(rec, "pocketId")) else "")
        zone = S(g(rec, "zoneId") if T(g(rec, "zoneId")) else "")
        if pocket:
            suppress[f"{key}|{pocket}"] = True
        elif zone:
            suppress[f"{key}|{zone}"] = True
    return suppress


def pocket_optional(pocket: Any) -> bool:
    """Test-LivingShellPocketOptional: a fusion vault or other high-value bonus pocket."""
    if not T(pocket):
        return False
    if has(pocket, "optionalTarget") and T(pocket["optionalTarget"]):
        return True
    if has(pocket, "highValue") and T(pocket["highValue"]):
        return True
    kind = S(g(pocket, "kind") if T(g(pocket, "kind")) else "")
    return ieq(kind, "fusion_fort")


def _center2(pk: Any) -> Optional[List[float]]:
    c = g(pk, "center")
    if T(c) and len(arr(c)) >= 2:
        return [D(c[0]), D(c[1])]
    return None


def build_from_template(template: Any, team_id: int, primary_zone_id: str, primary_center: Optional[List[float]],
                        commander_policy: str = "", scarred_zones: Any = None, destroyed_hv: Any = None,
                        held_installs: Any = None, scar_suppress: Any = None, log: Log = print) -> Dict[str, Any]:
    """Build-LivingShellFromTemplate."""
    if not T(destroyed_hv):
        destroyed_hv = CIDict()
    if not T(held_installs):
        held_installs = CIDict()
    if not T(scar_suppress):
        scar_suppress = CIDict()
    primary_pocket: Any = None
    matched_zone = False
    all_pockets = arr(g(template, "pockets"))
    combat = [pk for pk in all_pockets if not pocket_optional(pk)]
    if len(combat) < 1:
        combat = arr(g(template, "pockets"))
    for pk in combat:
        if T(g(pk, "primaryCandidate")):
            primary_pocket = S(g(pk, "pocketId"))
            break
    if not T(primary_pocket) and len(combat) > 0:
        primary_pocket = S(g(combat[0], "pocketId"))
    # Prefer the pocket whose zone matches the mission target (never a fusion bonus).
    if primary_zone_id:
        for pk in combat:
            if ieq(S(g(pk, "zoneId")), primary_zone_id):
                primary_pocket = S(g(pk, "pocketId"))
                matched_zone = True
                break
    # Templates can keep legacy zone ids while the authored map has migrated to a more precise graph.
    # Select the physically nearest combat pocket instead of silently spawning a fusion vault or the
    # first pocket at an unrelated objective.
    if not matched_zone and T(primary_center) and len(arr(primary_center)) >= 2:
        best = math.inf
        for pk in combat:
            c = g(pk, "center")
            if not T(c) or len(arr(c)) < 2:
                continue
            dx = D(c[0]) - float(primary_center[0])
            dz = D(c[1]) - float(primary_center[1])
            dist = (dx * dx) + (dz * dz)
            if dist < best:
                best = dist
                primary_pocket = S(g(pk, "pocketId"))
        if T(primary_pocket):
            log(fmt("Living shell: zone {0} has no pocket — nearest combat pad {1}", primary_zone_id, primary_pocket))
    selected_center = None
    for pk in all_pockets:
        if ieq(S(g(pk, "pocketId")), S(primary_pocket)) and T(g(pk, "center")) and len(arr(pk["center"])) >= 2:
            selected_center = [D(pk["center"][0]), D(pk["center"][1])]
            break
    rebase_dx = 0.0
    rebase_dz = 0.0
    if T(primary_center) and T(selected_center):
        rebase_dx = float(primary_center[0]) - selected_center[0]
        rebase_dz = float(primary_center[1]) - selected_center[1]
    pocket_centers = CIDict()
    for pk in all_pockets:
        if T(pk) and T(g(pk, "pocketId")) and _center2(pk) is not None:
            pocket_centers[S(pk["pocketId"])] = _center2(pk)
    # Pocket zone lookup for scar continuity.
    pocket_zone = CIDict()
    pocket_meta = CIDict()
    for pk in all_pockets:
        if not T(pk) or not T(g(pk, "pocketId")):
            continue
        pocket_zone[S(pk["pocketId"])] = S(g(pk, "zoneId"))
        pocket_meta[S(pk["pocketId"])] = pk
    suppressed = CIDict()
    thinned = 0
    units: List[Dict[str, Any]] = []
    repairs = 0
    shell_index = 0
    thin_index = 0
    for u in arr(g(template, "units")):
        u_pocket = S(g(u, "pocketId")) if T(g(u, "pocketId")) else ""
        u_zone = S(g(u, "zoneId")) if T(g(u, "zoneId")) else ""
        if not u_zone and u_pocket and u_pocket in pocket_zone:
            u_zone = S(pocket_zone[u_pocket])
        if T(g(u, "unitDefName")):
            u_def = S(u["unitDefName"])
        elif T(g(u, "def")):
            u_def = S(u["def"])
        else:
            u_def = ""
        u_def_key = u_def.lower()
        # Exact scar suppress: a burned unitDef+pocket stays burned (light raids too).
        if u_def_key and T(scar_suppress) and len(scar_suppress) > 0:
            hit = False
            if u_pocket and f"{u_def_key}|{u_pocket}" in scar_suppress:
                hit = True
            elif u_zone and f"{u_def_key}|{u_zone}" in scar_suppress:
                hit = True
            if hit:
                if u_pocket:
                    suppressed[u_pocket] = True
                thinned += 1
                continue
        scar_info = None
        if T(scarred_zones) and u_zone and u_zone in scarred_zones:
            scar_info = scarred_zones[u_zone]
        pk_meta = pocket_meta[u_pocket] if (u_pocket and u_pocket in pocket_meta) else None
        is_optional = pocket_optional(pk_meta) if T(pk_meta) else False
        # Fusion vault continuity: only despawn when the vault itself died. Ambient zone scars or
        # player_bloc used to wipe the whole beamer ring, which felt like the prize teleported out
        # between sorties.
        hv_dead = bool(u_pocket and u_pocket in destroyed_hv)
        held_by_player = False
        if is_optional and hv_dead:
            suppressed[u_pocket] = True
            thinned += 1
            continue
        if T(scar_info):
            scar = 0.25
            if T(g(scar_info, "scar")):
                scar = D(scar_info["scar"])
            reason = S(g(scar_info, "reason") if T(g(scar_info, "reason")) else "")
            if ieq(reason, "vacant"):
                # Nobody holds this ground: no enemy unit of the template stands on it, prize or not.
                if u_pocket:
                    suppressed[u_pocket] = True
                thinned += 1
                continue
            if is_optional:
                if iin(reason, ("player_bloc", "claimed")):
                    # The prize stays; ownership flips to the company on re-entry.
                    held_by_player = True
                # Else: a contested vault still standing stays enemy-owned unless HV-dead above.
            elif iin(reason, ("claimed", "player_bloc")):
                # Owned dirt: full wipe of enemy occupation. Company pads come back via the
                # playerFootprints merge; no residual enemy on the same pad.
                suppressed[u_pocket] = True
                thinned += 1
                continue
            else:
                # Partial combat scars (shell_scar / destroyed_ledger): ALWAYS leave a thin residual,
                # never empty the whole map because a few solars died. Effective scar is capped so
                # keepChance stays >= ~28%. A per-unit thin index (not shell_index): shell_index only
                # advances on kept units, so a sticky hash used to wipe the entire remainder.
                eff_scar = min(float(scar), 0.70)
                keep_chance = max(0.28, 1.0 - eff_scar)
                thin_index += 1
                h = abs((thin_index * 2654435761) % 1000) / 1000.0
                if h > keep_chance:
                    thinned += 1
                    continue
        # heldInstallations.owner=player even without a claim/scar reason: flip.
        if not held_by_player and u_pocket and T(held_installs):
            held_rec = ci_get(held_installs, u_pocket)
            if T(held_rec) and ieq(S(g(held_rec, "owner")), "player") and not ieq(S(g(held_rec, "status")), "destroyed"):
                held_by_player = True
        x = D(g(u, "x"))
        z = D(g(u, "z"))
        # A shell template is normalized to 0..1. Older Rock Jungle data carried a few accidental 1.x
        # coordinates, which put every affected unit beyond the map and made the game appear to spawn
        # them underwater.
        if x < 0.0 or x > 1.0 or z < 0.0 or z > 1.0:
            center = None
            if T(g(u, "pocketId")) and S(u["pocketId"]) in pocket_centers:
                center = pocket_centers[S(u["pocketId"])]
            if T(center):
                slot = shell_index % 12
                x = float(center[0]) + (0.014 * ((slot % 4) - 1.5))
                z = float(center[1]) + (0.014 * (math.floor(slot / 4) - 1.0))
            repairs += 1
        if T(g(u, "pocketId")) and ieq(S(u["pocketId"]), S(primary_pocket)) and T(selected_center):
            # Keep a selected legacy pocket's formation together, but center it on the current
            # authored target anchor after zone-id migration.
            x += rebase_dx
            z += rebase_dz
        x = max(0.04, min(0.96, x))
        z = max(0.04, min(0.96, z))
        unit_def_name = S(g(u, "unitDefName"))
        keep_class = S(g(u, "keepClass")) if T(g(u, "keepClass")) else "static"
        if ieq(commander_policy, "decoy") and imatch(unit_def_name, "^(arm|cor|leg)com$"):
            # Greenest is a farm of decoy command nodes. Real commanders would turn the visual fiction
            # into an extra autonomous player and duplicate the economy/AI role. Preserve the
            # installation as a decoy instead.
            if imatch(unit_def_name, "^arm"):
                unit_def_name = "armdecom"
            elif imatch(unit_def_name, "^cor"):
                unit_def_name = "cordecom"
            else:
                unit_def_name = "legdecom"
            keep_class = "decoy_node"
        if u_zone:
            row_zone = u_zone
        elif T(g(u, "zoneId")):
            row_zone = S(u["zoneId"])
        else:
            row_zone = ""
        row = {
            "unitDefName": unit_def_name,
            "x": x,
            "z": z,
            "facing": I(u["facing"]) if g(u, "facing") is not None else 0,
            "zoneId": row_zone,
            "pocketId": S(u["pocketId"]) if T(g(u, "pocketId")) else "",
            "keepClass": keep_class,
            "faction": S(u["faction"]) if T(g(u, "faction")) else "",
        }
        if held_by_player:
            row["heldByPlayer"] = True
            row["forceRole"] = "held_install"
        units.append(row)
        shell_index += 1
    if thinned > 0:
        log(fmt("Living shell continuity: suppressed {0} units on scarred/claimed pads ({1} pockets)",
                thinned, len(suppressed)))
    pockets: List[Dict[str, Any]] = []
    for pk in all_pockets:
        zid = S(g(pk, "zoneId"))
        pocket_id = S(g(pk, "pocketId"))
        scarred_pocket = bool(T(scarred_zones) and zid and zid in scarred_zones)
        is_opt = pocket_optional(pk)
        hv_dead_pocket = bool(T(destroyed_hv) and pocket_id and pocket_id in destroyed_hv)
        # Drop optional fusion/HV marks only when the vault itself is dead, not when a neighbouring
        # combat pad is scarred (that left blown vaults highlighted).
        if is_opt and hv_dead_pocket:
            continue
        center = g(pk, "center")
        row = {
            "pocketId": pocket_id,
            "zoneId": S(g(pk, "zoneId")),
            "label": S(g(pk, "label")),
            "kind": S(pk["kind"]) if T(g(pk, "kind")) else "mixed",
            "growProfile": S(pk["growProfile"]) if T(g(pk, "growProfile")) else "",
            # A pocket without a center fails here, as it did in PowerShell (the shell load falls back).
            "center": [D(center[0]), D(center[1])],
            "unitCount": I(pk["unitCount"]) if g(pk, "unitCount") is not None else 0,
            "primaryCandidate": T(g(pk, "primaryCandidate")),
            "scarred": scarred_pocket,
        }
        if has(pk, "optionalTarget") and T(pk["optionalTarget"]):
            row["optionalTarget"] = True
        if has(pk, "highValue") and T(pk["highValue"]):
            row["highValue"] = True
        if ieq(row["kind"], "fusion_fort"):
            row["optionalTarget"] = True
            row["highValue"] = True
        pockets.append(row)
    return {
        "enabled": True,
        "templateId": S(g(template, "templateId")),
        "source": S(template["source"]) if T(g(template, "source")) else "unknown",
        "teamID": team_id,
        "primaryZoneId": primary_zone_id,
        "primaryPocketId": primary_pocket,
        "unitCount": len(units),
        "coordinateRepairs": repairs,
        # Persistent battlefield doctrine: every authored pocket exists before the first contract
        # starts. Same-map selection only promotes surviving units.
        "localPocketOnly": False,
        "units": units,
        "pockets": pockets,
    }


def company_travel_structure_defs(state: Any, ws: Path) -> Set[str]:
    """Get-CompanyTravelStructureDefs: hero bodies and the structures that ship inside their pack.
    Those travel with the dropping list; rehydrating them paints a second Solarium (and the rest of
    that nest) onto wherever they stood last time, often the target."""
    skip: Set[str] = set()
    if not T(state) or not T(g(state, "company")):
        return skip
    pack_path = Path(ws) / "data" / "story" / "crew_packs.json"
    if not pack_path.exists():
        return skip
    try:
        doc = read_json(pack_path)
    except Exception:  # noqa: BLE001
        return skip
    heroes = g(doc, "heroes")
    if not T(heroes):
        return skip
    ids: List[Any] = []
    for k in ("core", "band", "joinedLater"):
        bag = ci_get(state["company"], k)
        if T(bag):
            ids += arr(bag)
    for raw in ids:
        hid = S(raw)
        if not hid or not ci_has(heroes, hid):
            continue
        h = ci_get(heroes, hid)
        if T(g(h, "unitDef")):
            skip.add(S(h["unitDef"]).lower())
        if T(g(h, "escorts")):
            for e in arr(h["escorts"]):
                if T(e) and T(g(e, "unitDef")):
                    skip.add(S(e["unitDef"]).lower())
    return skip


def merge_player_footprint(state: Any, map_id: str, payload: Optional[Dict[str, Any]], ws: Path,
                           log: Log = print) -> Optional[Dict[str, Any]]:
    """Merge-PlayerFootprintIntoShell: the concrete source of truth for company-built pads.

    Living-shell scars and claims suppress enemy occupation; this appends the player's own structures
    so claimed zones are not empty dirt on the next Drop. Coords are Spring elmos (living_shell.lua
    shellCoord accepts elmos when value > 1.5). Hero packs are not pads: they spawn from the dropping
    list, once.
    """
    if not T(state) or not map_id:
        return payload
    fp = None
    if has(state, "playerFootprints") and T(state["playerFootprints"]):
        fp = ci_get(state["playerFootprints"], map_id)
    if not T(fp) or not T(g(fp, "units")):
        return payload
    # Footprint-only shell when the occupation path skipped (kind/template miss).
    if not T(payload):
        payload = {
            "enabled": True,
            "templateId": "player_footprint_only",
            "source": "player_footprints",
            "teamID": 1,
            "primaryZoneId": S(fp["deploymentZoneId"] if T(g(fp, "deploymentZoneId")) else ""),
            "primaryPocketId": "",
            "unitCount": 0,
            "localPocketOnly": False,
            "units": [],
            "pockets": [],
            "spawnLimit": 400,
        }
    units: List[Any] = []
    if T(payload.get("units")):
        units = arr(payload["units"])
    added = 0
    skipped_travel = 0
    skipped_lattice = 0
    size_x = 0.0
    size_z = 0.0
    baseline = Path(ws) / "data" / "scenarios" / "authored" / f"{map_id}.authored_baseline.json"
    if baseline.exists():
        try:
            authored = read_json(baseline)
            if T(g(authored, "map")):
                size_x = D(authored["map"].get("sizeX"))
                size_z = D(authored["map"].get("sizeZ"))
        except Exception:  # noqa: BLE001
            pass
    travel = company_travel_structure_defs(state, ws)
    for u in arr(fp["units"]):
        if not T(u):
            continue
        if T(g(u, "unitDefName")):
            def_name = S(u["unitDefName"])
        elif T(g(u, "def")):
            def_name = S(u["def"])
        else:
            def_name = ""
        if not def_name:
            continue
        if def_name.lower() in travel:
            skipped_travel += 1
            continue
        try:
            x = D(g(u, "x"))
            z = D(g(u, "z"))
        except (TypeError, ValueError):
            continue
        if size_x > 512 and size_z > 512 and x > 1.5 and z > 1.5:
            dx = abs(x / size_x - 0.5)
            dz = abs(z / size_z - 0.5)
            hit_x = (abs(dx - 0.007) < 0.002) or (abs(dx - 0.021) < 0.002)
            hit_z = (abs(dz - 0.007) < 0.002) or (abs(dz - 0.021) < 0.002)
            if hit_x and hit_z:
                skipped_lattice += 1
                continue
        try:
            facing = I(g(u, "facing"))
        except (TypeError, ValueError):
            facing = 0
        units.append({
            "unitDefName": def_name,
            "x": x,
            "z": z,
            "facing": facing,
            "zoneId": S(u["zoneId"] if T(g(u, "zoneId")) else ""),
            "pocketId": "",
            "keepClass": "static",
            "heldByPlayer": True,
            "forceRole": "player_footprint",
            "faction": "ashwalkers",
        })
        added += 1
        if added >= 400:
            break
    if added > 0:
        payload["units"] = units
        payload["unitCount"] = len(units)
        payload["enabled"] = True
        try:
            cur = I(payload.get("spawnLimit"))
        except (TypeError, ValueError):
            cur = 0
        payload["spawnLimit"] = max(cur, len(units))
        log(fmt("Player footprint: rehydrating {0} structures onto living shell", added))
    if skipped_travel > 0:
        log(fmt("Player footprint: left {0} hero-pack structures with the company (not painted onto the map)", skipped_travel))
    if skipped_lattice > 0:
        log(fmt("Player footprint: left {0} center-snap ghosts off the map", skipped_lattice))
    return payload


def rehydrate_specs(snapshot: Any, prefix: str) -> List[Dict[str, Any]]:
    """New-RehydrateSpecs (Drop 3 finale dressing): a persistent-base snapshot (zone telemetry's
    unitCountsByDef) back into placeable specs. Approximate by design: top defs only, per-def and
    total caps, faction-prefix filtered so a bloc never spawns another bloc's hardware.

    PowerShell sorted the counts out of a hashtable, so defs with equal counts came out in hash order;
    here they keep the order they were first seen. No corpus case reaches this (finale overthrow only).
    """
    if not T(snapshot) or not has(snapshot, "teams") or not T(snapshot["teams"]):
        return []
    counts = CIDict()
    for team in arr(snapshot["teams"]):
        if not T(team) or not has(team, "unitCountsByDef") or not T(team["unitCountsByDef"]):
            continue
        for name, value in props(team["unitCountsByDef"]):
            def_name = S(name)
            if not def_name.startswith(prefix):
                continue
            try:
                n = I(value)
            except (TypeError, ValueError):
                n = 0
            if n <= 0:
                continue
            counts[def_name] = (I(counts[def_name]) + n) if def_name in counts else n
    if len(counts) == 0:
        return []
    specs: List[Dict[str, Any]] = []
    phase = 0
    total = 0
    for def_name in sorted(counts.keys(), key=lambda k: -I(counts[k]))[:10]:
        n = min(6, I(counts[def_name]))
        if total + n > 30:
            n = 30 - total
        if n <= 0:
            break
        specs += scatter(def_name, n, 420, 2, phase, 70)
        phase += 2
        total += n
    return specs
