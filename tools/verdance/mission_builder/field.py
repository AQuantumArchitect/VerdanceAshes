"""The field: teams, allyteams, forces, AIs and pacts, one camp at a time.

Each camp is one team on its own allyteam. Camps carry a small objective-tagged centerpiece force plus
an untagged garrison shell. Teams carry an explicit faction tag so telemetry reads the world war
(nullmercs/armada/cortex), not the chassis. The PowerShell builder kept all of this in script-scope
variables its functions wrote to; here it is one ``Field`` object, and the mission-wide numbers the
camps read (enemy scale, facing, patrol target, the arc profile) are attributes the builder sets
before it adds any camp.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from verdance.mission_builder import kits
from verdance.mission_builder import shell as shell_mod
from verdance.mission_builder._ps import (
    CIDict, D, I, S, T, arr, eq, fmt, g, has, hashtable_key_order, ieq, sign,
)
from verdance.mission_builder.kits import FACTION, MERC, Spec, faction, patrol_sweep, scaled_count

Log = Callable[[str], None]

# Kinds that load living-shell occupation when a template exists (outbound 38).
SHELL_CAPABLE_KINDS = ("seize_lane", "hold_plateau", "siege", "multipressure", "gate_control", "survive_wilds")


def start_rect(center: List[float], radius: float = 0.22) -> List[float]:
    x = float(center[0])
    z = float(center[1])
    return [max(0.0, x - radius), max(0.0, z - radius), min(1.0, x + radius), min(1.0, z + radius)]


def clamp01(v: float) -> float:
    return max(0.03, min(0.97, float(v)))


def edge_score(x: float, z: float) -> float:
    """Same rim rule as player infil: reinforcements, footholds and wild nests stay on edges."""
    return min(min(x, 1.0 - x), min(z, 1.0 - z))


def push_to_rim(c: List[float], threshold: float = 0.28) -> List[float]:
    x = float(c[0])
    z = float(c[1])
    if edge_score(x, z) <= threshold:
        return [clamp01(x), clamp01(z)]
    for _ in range(24):
        to_left, to_right, to_top, to_bottom = x, 1.0 - x, z, 1.0 - z
        m = min(min(to_left, to_right), min(to_top, to_bottom))
        if m == to_left:
            x -= 0.04
        elif m == to_right:
            x += 0.04
        elif m == to_top:
            z -= 0.04
        else:
            z += 0.04
        x = clamp01(x)
        z = clamp01(z)
        if edge_score(x, z) <= threshold:
            break
    return [x, z]


def zone_by_id(zone_map: Any, zone_id: Any) -> Any:
    if not T(zone_map) or not T(g(zone_map, "zones")) or not T(zone_id):
        return None
    for z in arr(zone_map["zones"]):
        if eq(g(z, "zoneId"), zone_id):
            return z
    return None


def zone_center(zone: Any, fallback: Optional[List[float]]) -> Optional[List[float]]:
    if not T(zone):
        return fallback
    # Schema 2.0 zones carry a MEASURED anchor: buildable, dry, flat ground. A rect centre is a guess
    # that can land in water or on a cliff face, which is how camps ended up spawning where nothing
    # can be built.
    anchor = g(zone, "anchor")
    if has(zone, "anchor") and T(anchor) and g(anchor, "x") is not None and g(anchor, "z") is not None:
        return [max(0.02, min(0.98, D(anchor["x"]))), max(0.02, min(0.98, D(anchor["z"])))]
    b = g(zone, "bounds")
    if not T(b):
        return fallback
    return [
        max(0.02, min(0.98, ((D(g(b, "xMin")) + D(g(b, "xMax"))) / 2.0))),
        max(0.02, min(0.98, ((D(g(b, "zMin")) + D(g(b, "zMax"))) / 2.0))),
    ]


def _faction_word(side: str) -> str:
    if ieq(side, "Cortex"):
        return "cortex"
    if ieq(side, "Legion"):
        return "nullmercs"
    return "armada"


class Field:
    """Everything the PS1 kept in $script: scope while it laid the camps out."""

    def __init__(self, ws: Path, intent: Dict[str, Any], state: Any, log: Log) -> None:
        self.ws = Path(ws)
        self.intent = intent
        self.state = state
        self.log = log
        # Mission-wide numbers the camps read; the builder sets them before the first camp.
        self.arc_profile: Dict[str, Any] = {}
        self.enemy_scale = 1.0
        self.face_x = 1
        self.face_z = 1
        self.patrol_target: List[float] = [0.5, 0.5]
        self.fortify = False
        self.objective_strength = "surgical"
        self.max_hazard = 0.0
        self.enemy_ai_short = "SimpleAI"
        self.is_finale = False
        self.objective_kind = ""
        self.target_zone_id = ""
        self.mercs_allied = False
        self.enemy_center: List[float] = [0.84, 0.84]
        self.eye_story: Any = None
        # The field itself.
        self.next_team = 1
        self.next_ally_team = 1
        self.ally_teams: List[Dict[str, Any]] = []
        self.teams: List[Dict[str, Any]] = []
        self.forces: List[Dict[str, Any]] = []
        self.ai: List[Dict[str, Any]] = []
        self.alliances: List[Dict[str, Any]] = []
        self.base_recipes: Dict[str, Any] = {}
        self.primary_enemy_team_id: Optional[int] = None
        self.primary_enemy_side: Optional[str] = None
        self.wild_team_id: Optional[int] = None
        self.war_wrecks: List[Any] = []
        self.scout_parties: List[Dict[str, Any]] = []
        self.secondary_meta: List[Dict[str, Any]] = []
        self.living_shell: Optional[Dict[str, Any]] = None
        self.map_occupation: List[Dict[str, Any]] = []
        self.shell_ally_id: Optional[int] = None
        self.shell_faction: Optional[str] = None
        self.kings: List[Dict[str, Any]] = []
        self.used_shell = False

    def _seat(self) -> tuple:
        team_id = self.next_team
        self.next_team += 1
        ally_id = self.next_ally_team
        self.next_ally_team += 1
        return team_id, ally_id

    def _ally(self, a: int, b: int) -> None:
        self.alliances.append({"allyTeamA": a, "allyTeamB": b, "allied": True})

    # --- the living shell -----------------------------------------------------------------------

    def try_apply_living_shell(self, map_id: str, primary_zone_id: str, description: str,
                               enemy_center: List[float], anchor_side: str = "Armada") -> bool:
        path = shell_mod.template_path(self.ws, map_id)
        if path is None:
            return False
        try:
            tpl = shell_mod.read_json(path)
            team_id, ally_id = self._seat()
            side = anchor_side if anchor_side else "Armada"
            self.shell_ally_id = ally_id
            self.shell_faction = _faction_word(side)
            t = faction(side)
            rgb = t["rgb"] if t is not None else FACTION["Armada"]["rgb"]
            self.ally_teams.append({"id": ally_id, "startRect": start_rect(enemy_center, 0.22)})
            self.teams.append({
                "id": team_id, "side": side, "allyTeam": ally_id,
                "base": [enemy_center[0], enemy_center[1]],
                "rgb": rgb,
                "label": f"{side} - Living Shell",
                "faction": _faction_word(side),
            })
            self.base_recipes["shell_anchor"] = []
            self.forces.append({
                "id": "living_shell_anchor",
                "label": description,
                "teamID": team_id,
                "side": side,
                "faction": _faction_word(side),
                "role": "objective_target",
                "zoneId": primary_zone_id,
                "base": {"x": enemy_center[0], "z": enemy_center[1]},
                "recipe": "shell_anchor",
            })
            policy = "decoy" if ieq(map_id, "greenest_fields") else ""
            scarred = shell_mod.scarred_zone_set(self.state, map_id)
            dead_hv = shell_mod.destroyed_high_value_pockets(self.state, map_id)
            suppress = shell_mod.scar_suppress_set(self.state, map_id)
            held = None
            if T(self.state) and has(self.state, "heldInstallations") and T(self.state["heldInstallations"]):
                held = shell_mod.ci_get(self.state["heldInstallations"], map_id)
            if len(scarred) > 0:
                self.log(fmt("Shell scars on {0}: {1}", map_id,
                             ", ".join(f"{k}={S(scarred[k]['reason'])}" for k in scarred.keys())))
            if len(dead_hv) > 0:
                self.log(fmt("Destroyed HV pockets on {0}: {1}", map_id, ", ".join(dead_hv.keys())))
            if len(suppress) > 0:
                self.log(fmt("Exact scar suppress on {0}: {1} keys", map_id, len(suppress)))
            payload = shell_mod.build_from_template(tpl, team_id, primary_zone_id, enemy_center, policy, scarred,
                                                    dead_hv, held, suppress, log=self.log)
            self.living_shell = payload
            payload = shell_mod.merge_player_footprint(self.state, map_id, payload, self.ws, log=self.log)
            self.living_shell = payload
            payload["commanderPolicy"] = policy if policy else "normal"
            payload["spawnLimit"] = I(payload.get("unitCount"))
            if payload["spawnLimit"] < 1:
                payload["spawnLimit"] = 51
            if T(g(self.intent, "openingMission")):
                # The builder historically wrote openingPocketOnly; the gadget reads both.
                payload["openingPocketOnly"] = True
                payload["localPocketOnly"] = True
            # Prefer payload pockets (already HV-dead filtered) over the raw template.
            occ_pockets = arr(payload.get("pockets"))
            if len(occ_pockets) < 1:
                occ_pockets = arr(g(tpl, "pockets"))
            for pk in occ_pockets:
                pocket_id = S(g(pk, "pocketId"))
                if T(dead_hv) and pocket_id and pocket_id in dead_hv:
                    continue
                is_primary = bool(T(payload.get("primaryPocketId")) and ieq(pocket_id, S(payload["primaryPocketId"])))
                occ = {
                    "zoneId": S(g(pk, "zoneId")),
                    "label": S(g(pk, "label")),
                    "kind": S(pk["kind"]) if T(g(pk, "kind")) else "mixed",
                    "growProfile": S(pk["growProfile"]) if T(g(pk, "growProfile")) else "",
                    "teamID": team_id,
                    "preplaced": True,
                    "primary": is_primary,
                    "pocketId": pocket_id,
                    "livingShell": True,
                    "commanderPolicy": policy if policy else "normal",
                }
                if shell_mod.pocket_optional(pk):
                    occ["optionalTarget"] = True
                    occ["highValue"] = True
                self.map_occupation.append(occ)
            self.log(fmt("Living shell: {0} units / {1} pockets from {2}", payload.get("unitCount"),
                         len(arr(g(tpl, "pockets"))), path.name))
            return True
        except Exception as e:  # noqa: BLE001 - the PS1 caught everything here and fell back
            self.log(fmt("Living shell load failed ({0}); falling back.", str(e)))
            return False

    def ensure_player_footprint_shell(self, map_id: str, primary_zone_id: str) -> bool:
        """When try_apply_living_shell did not run (kind/template miss), still emit a minimal
        livingShell so company pads from playerFootprints respawn."""
        if T(self.living_shell):
            self.living_shell = shell_mod.merge_player_footprint(self.state, map_id, self.living_shell, self.ws,
                                                                 log=self.log)
            return False
        fp = None
        if T(self.state) and has(self.state, "playerFootprints") and T(self.state["playerFootprints"]):
            fp = shell_mod.ci_get(self.state["playerFootprints"], map_id)
        if not T(fp) or not T(g(fp, "units")) or len(arr(fp["units"])) < 1:
            return False
        payload = shell_mod.merge_player_footprint(self.state, map_id, None, self.ws, log=self.log)
        if not T(payload) or not T(payload.get("units")) or len(arr(payload["units"])) < 1:
            return False
        if primary_zone_id and not T(payload.get("primaryZoneId")):
            payload["primaryZoneId"] = primary_zone_id
        self.living_shell = payload
        self.used_shell = True
        self.log(fmt("Player footprint: footprint-only living shell ({0} units)", len(arr(payload["units"]))))
        return True

    # --- camps ----------------------------------------------------------------------------------

    def add_faction_camp(self, side: str, center: List[float], centerpiece: Any, label: str, with_eco: bool = True,
                         with_production: bool = False, with_jammers: bool = False, support: Any = None,
                         front_band: bool = False) -> None:
        """A camp is ONE faction end to end: Armada and Cortex are mortal enemies and never share a
        team or allyteam. The centerpiece (objective) and its garrison are the same side."""
        t = faction(side)
        team_id, ally_id = self._seat()
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, 0.20)})
        self.teams.append({"id": team_id, "side": side, "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": t["rgb"], "label": f"{side} - {label}", "faction": side.lower()})
        if T(centerpiece):
            core = f"camp{team_id}_core"
            self.base_recipes[core] = arr(centerpiece)
            self.forces.append({"id": f"camp{team_id}_objective", "label": label, "teamID": team_id, "side": side,
                                "faction": side.lower(), "role": "objective_target",
                                "base": {"x": center[0], "z": center[1]}, "recipe": core})
        # WO-034: static bases never get production labs (SimpleAI + labs = commander soup).
        allow_prod = with_production and eq(self.arc_profile.get("allowEnemyProduction"), True)
        # Drop 3: warband doctrine (act-1 ground control) thins the static shell hard and beefs the
        # roving patrols; the camp reads as a war party's foothold.
        warband = ieq(S(self.arc_profile.get("enemyMode")), "warband")
        es = self.enemy_scale
        garrison: List[Any] = []
        if T(support):
            garrison += arr(support)
        # WO-004: front-band camps keep light eco (worth exploding) but thinner teeth.
        if with_eco:
            s = max(0.45, es * 0.55) if warband else (max(0.55, es * 0.75) if front_band else es)
            garrison += kits.ring_eco(t, s)
        s = max(0.5, es * 0.55) if warband else (max(0.6, es * 0.8) if front_band else es)
        garrison += kits.ring_perimeter(t, s, self.face_x, self.face_z)
        if allow_prod:
            garrison += kits.ring_production(t)
        if with_jammers:
            garrison += kits.ring_jammers(t)
        patrol_scale = es * 1.5 if warband else es
        if front_band and not warband:
            garrison += kits.ring_patrol(t, patrol_scale, self.patrol_target[0], self.patrol_target[1], front_band=True)
        else:
            garrison += kits.ring_patrol(t, patrol_scale, self.patrol_target[0], self.patrol_target[1])
        if self.fortify and not front_band and not warband:
            garrison += kits.ring_fortify(t, self.face_x, self.face_z)
        garrison_recipe = f"camp{team_id}_garrison"
        self.base_recipes[garrison_recipe] = list(garrison)
        # Drop 4 raze strength: on the PRIMARY camp the whole garrison joins the objective book; the
        # mission is "leave nothing of this camp standing", not a surgical centerpiece strike.
        role = "garrison"
        if ieq(self.objective_strength, "raze") and self.primary_enemy_team_id is None:
            role = "objective_target"
            self.log(fmt("RAZE: {0} camp garrison joins the objective book (team {1}).", side, team_id))
        self.forces.append({"id": f"camp{team_id}_garrison", "label": f"{side} garrison", "teamID": team_id,
                            "side": side, "faction": side.lower(), "role": role,
                            "base": {"x": center[0], "z": center[1]}, "recipe": garrison_recipe})
        if ieq(self.enemy_ai_short, "BARb"):
            ai_name = f"BARb({side} {label})"
        elif ieq(self.enemy_ai_short, "SimpleDefenderAI"):
            ai_name = f"SimpleDefender({side} {label})"
        else:
            ai_name = f"SimpleAI({side} {label})"
        self.ai.append({"name": ai_name, "shortName": self.enemy_ai_short, "team": team_id, "version": "<not-versioned>"})
        # Drop 3: the first faction camp anchors roving warband packs (act 1).
        if self.primary_enemy_team_id is None:
            self.primary_enemy_team_id = team_id
            self.primary_enemy_side = side

    def add_raptor_camp(self, center: List[float], as_objective: bool, label: str) -> None:
        team_id, ally_id = self._seat()
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, 0.18)})
        self.teams.append({"id": team_id, "side": "Armada", "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": [0.78, 0.14, 0.92], "label": label, "faction": "wild"})
        if as_objective:
            self.base_recipes[f"camp{team_id}_hives"] = kits.centerpiece_hives(self.max_hazard)
            self.forces.append({"id": f"camp{team_id}_objective", "label": label, "teamID": team_id, "side": "Raptors",
                                "faction": "wild", "role": "objective_target",
                                "base": {"x": center[0], "z": center[1]}, "recipe": f"camp{team_id}_hives"})
        swarm = kits.ring_raptor_garrison(self.max_hazard)
        if not as_objective:
            # Wild pressure has no objective heart. Same three hives, so the jungle is already occupied.
            swarm += kits.centerpiece_hives(self.max_hazard)
        self.base_recipes[f"camp{team_id}_swarm"] = swarm
        self.forces.append({"id": f"camp{team_id}_swarm", "label": "Raptor swarm", "teamID": team_id, "side": "Raptors",
                            "faction": "wild", "role": "garrison" if as_objective else "wild_pressure",
                            "base": {"x": center[0], "z": center[1]}, "recipe": f"camp{team_id}_swarm"})
        self.ai.append({"name": "RaptorsDefenseAI(Verdance)", "shortName": "RaptorsAI", "team": team_id,
                        "version": "<not-versioned>"})
        if self.wild_team_id is None:
            self.wild_team_id = team_id

    def add_wild_dens(self) -> None:
        """Wild ground (the Rock Jungle end to end, the Eye's crater rim): the engine names every den on
        the intent (intent.wildDens: zone, label, point; none on the hive, none near the pad). Each is a
        raptor turret (the wild's defensive value there, so the zone is the wild's until someone
        out-builds it) with a pack that moseys between it and the nearest den and a gunship looping
        wider. Packs carry patrol orders only, so the raptor AI's waves stay its own and these never
        march on the pad unprompted."""
        dens: List[Any] = []
        if has(self.intent, "wildDens") and T(self.intent["wildDens"]):
            dens = arr(self.intent["wildDens"])
        if len(dens) == 0:
            return
        if self.wild_team_id is None:
            self.add_raptor_camp([D(g(dens[0], "x")), D(g(dens[0], "z"))], False, "Raptor wild ground")
        scale = 1.0 + max(0.0, min(1.0, self.max_hazard))
        n = 0
        for den in dens:
            c = [D(g(den, "x")), D(g(den, "z"))]
            near = sorted((d for d in dens if d is not den),
                          key=lambda d: (D(g(d, "x")) - c[0]) * (D(g(d, "x")) - c[0]) + (D(g(d, "z")) - c[1]) * (D(g(d, "z")) - c[1]))
            den_point = {"x": c[0], "z": c[1]}
            walk = [den_point]
            fly = [den_point]
            if len(near) >= 1:
                walk.append({"x": D(g(near[0], "x")), "z": D(g(near[0], "z"))})
                fly.append({"x": D(g(near[0], "x")), "z": D(g(near[0], "z"))})
            if len(near) >= 2:
                fly.append({"x": D(g(near[1], "x")), "z": D(g(near[1], "z"))})
            n += 1
            recipe = fmt("wild_den_{0}_{1}", S(g(den, "zoneId")), n)
            self.base_recipes[recipe] = [
                Spec("raptor_turret_basic_t2_v1", 1, 0, 0, 120),
                Spec("raptor_land_swarmer_basic_t1_v1", scaled_count(5, scale), 90, -60, 70, Patrol=walk),
                Spec("raptor_land_swarmer_basic_t2_v1", scaled_count(2, scale), -110, 70, 80, Patrol=walk),
                Spec("raptor_air_gunship_basic_t2_v1", 1, 0, -160, 90, Patrol=fly),
            ]
            label = S(den["label"]) if T(g(den, "label")) else S(g(den, "zoneId"))
            self.forces.append({"id": recipe, "label": f"Wild den: {label}", "teamID": self.wild_team_id,
                                "side": "Raptors", "faction": "wild", "role": "wild_pressure",
                                "zoneId": S(g(den, "zoneId")), "base": {"x": c[0], "z": c[1]}, "recipe": recipe})
        self.log(fmt("Wild ground: {0} dens.", len(dens)))

    @staticmethod
    def war_faction(fac: str) -> Dict[str, Any]:
        """Get-WarFaction.

        PS FAULT, KEPT: the PS1's parameter was ``[string]$Faction``, and PowerShell variable names
        ignore case, so inside that function ``$FACTION["Armada"]`` indexed the parameter string, not
        the faction table, and came back null. Every Armada and Cortex war seat (standing wars, Eye
        scouts, visit-tier wardens, kings) went out with ``rgb: null`` (all ten standing-war sorties
        of the 2026-11-04 corpus); only the Null Mercs, read from $MERC, had a colour.
        """
        if ieq(fac, "nullmercs"):
            return {"T": MERC, "side": "Legion", "label": "Null Mercs"}
        if ieq(fac, "cortex"):
            return {"T": None, "side": "Cortex", "label": "Cortex"}
        return {"T": None, "side": "Armada", "label": "Armada"}

    def new_war_team(self, fac: str, center: List[float], label: str, rect: float = 0.16) -> Dict[str, Any]:
        w = self.war_faction(fac)
        team_id, ally_id = self._seat()
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, rect)})
        self.teams.append({"id": team_id, "side": w["side"], "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": g(w["T"], "rgb"), "label": f"{w['label']} - {label}", "faction": fac})
        self.ai.append({"name": f"BARb({w['label']} {label})", "shortName": "BARb", "team": team_id,
                        "version": "<not-versioned>"})
        if ieq(fac, "armada") and self.primary_enemy_team_id is None:
            self.primary_enemy_team_id = team_id
            self.primary_enemy_side = "Armada"
        return {"teamID": team_id, "allyID": ally_id, "W": w}

    def add_standing_war(self, theater: Dict[str, Any]) -> None:
        """A standing war (Koom, Tabula, the Bastion, the Eye): each seat is a BARbarian on its own seat,
        and the war was baked (tools/war_bake_v1.py), so each seat's units stand exactly where the sim
        left them, as hurt as it left them, with the bank it held. The company takes the seat the war
        left empty. Seats on one side are allied; the Mercs are the company's allies or not as its
        standing with them says."""
        camps = arr(theater.get("camps"))
        if has(theater, "wrecks") and T(theater["wrecks"]):
            self.war_wrecks = arr(theater["wrecks"])
        side_allies = CIDict()
        for camp in camps:
            c = [D(g(camp, "x")), D(g(camp, "z"))]
            fac = S(g(camp, "faction"))
            wt = self.new_war_team(fac, c, S(g(camp, "label")))
            if has(camp, "profile") and T(camp["profile"]):
                self.ai[-1]["options"] = {"profile": S(camp["profile"])}
            specs = kits.baked_specs(arr(g(camp, "units")))
            field_id = f"war{wt['teamID']}_field"
            self.base_recipes[field_id] = specs
            # The Eye (verdance.world.eye_story): Armada's job makes the Cortex camp the target; Cortex's
            # job makes it the company's ally.
            war_role = "standing_war"
            # Finale A, the Overthrow: the castle guns and the command post in the Keep are the seat the
            # war left standing there. Its structures are the objective's targets (spawn.lua books
            # objective_target structures only), or the finale had nothing to break.
            if self.is_finale and ieq(self.objective_kind, "destroy_key_structure") and self.target_zone_id \
                    and ieq(S(g(camp, "zoneId")), self.target_zone_id):
                war_role = "objective_target"
            if T(self.eye_story) and ieq(fac, "cortex"):
                if ieq(S(g(self.eye_story, "kind")), "raze_camp"):
                    war_role = "objective_target"
                if ieq(S(g(self.eye_story, "alliedWith")), "cortex"):
                    self._ally(0, wt["allyID"])
            force = {"id": field_id, "label": f"{wt['W']['label']} field", "teamID": wt["teamID"],
                     "side": wt["W"]["side"], "faction": fac, "role": war_role, "zoneId": S(g(camp, "zoneId")),
                     "base": {"x": c[0], "z": c[1]}, "recipe": field_id}
            # The Overthrow books the seat's guns and its factories, not its windmills (spawn.lua).
            if war_role == "objective_target" and not T(self.eye_story):
                force["book"] = "guns_and_command"
            if has(camp, "bank") and T(camp["bank"]):
                force["bank"] = {"metal": D(g(camp["bank"], "metal")), "energy": D(g(camp["bank"], "energy"))}
            self.forces.append(force)
            if fac not in side_allies:
                side_allies[fac] = []
            side_allies[fac] = side_allies[fac] + [wt["allyID"]]
            if ieq(fac, "nullmercs") and self.mercs_allied:
                self._ally(0, wt["allyID"])
        for fac in hashtable_key_order(side_allies.keys()):
            ids = list(side_allies[fac])
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    self._ally(ids[i], ids[j])
        # The living shell kept beside the war (keepShell) fights on the war's side of its faction.
        if self.shell_ally_id is not None and T(self.shell_faction) and self.shell_faction in side_allies:
            for aid in side_allies[self.shell_faction]:
                self._ally(self.shell_ally_id, aid)
            if ieq(self.shell_faction, "nullmercs") and self.mercs_allied:
                self._ally(0, self.shell_ally_id)
            self.log(fmt("Living shell kept beside the war: {0} shell allied to the war's {0}", self.shell_faction))
        self.log(fmt("Standing war: {0}", " vs ".join(f"{S(g(c, 'faction'))}@{S(g(c, 'zoneId'))}" for c in camps)))
        if T(self.eye_story):
            self.add_eye_scouts(self.eye_story)

    def add_eye_scouts(self, story: Dict[str, Any]) -> None:
        """The Eye's Armada scouts (verdance.world.eye_story): one Simple AI team per corner the company
        did not land in, empty at the start (game_verdance_scouts.lua strips the engine's commander and
        walks the party in at its arrival time). Allied to the company when Armada is the patron."""
        for p in arr(g(story, "scoutParties")):
            c = [D(g(p, "x")), D(g(p, "z"))]
            zid = S(g(p, "zoneId"))
            wt = self.new_war_team("armada", c, "scouts " + zid, 0.06)
            self.ai[-1]["name"] = f"SimpleAI(Armada scouts {zid})"
            self.ai[-1]["shortName"] = "SimpleAI"
            if ieq(S(g(story, "alliedWith")), "armada"):
                self._ally(0, wt["allyID"])
            # The camp the party built over five minutes (tools/eye_scouts_bake_v1.py), placed as it stood.
            camp = arr(g(p, "camp"))
            if len(camp) > 0:
                rid = f"scout{wt['teamID']}_camp"
                self.base_recipes[rid] = kits.baked_specs(camp)
                self.forces.append({"id": rid, "label": f"Armada scout camp {zid}", "teamID": wt["teamID"],
                                    "side": "Armada", "faction": "armada", "role": "scout_camp", "zoneId": zid,
                                    "base": {"x": c[0], "z": c[1]}, "recipe": rid})
            self.scout_parties.append({"teamID": wt["teamID"], "zoneId": zid, "x": c[0], "z": c[1],
                                       "arriveSeconds": I(g(p, "arriveSeconds")), "units": arr(g(p, "units"))})
        self.log(fmt("Eye scouts: {0} Armada parties ({1} hires the company)", len(arr(g(story, "scoutParties"))),
                     S(g(story, "patron"))))

    def add_kings(self, theater: Dict[str, Any]) -> None:
        """All That Simmers, the kings' showdown: a game of BAR in four corners. Armada and Cortex are
        BARbarians on their seats with their start commanders and nothing else; the company's commander
        is the third king; raptors hold the fourth corner. Everyone is at war with everyone."""
        self.kings = [{"teamID": 0, "faction": "ashwalkers", "label": "The company"}]
        for k in arr(theater.get("kings")):
            wt = self.new_war_team(S(g(k, "faction")), [D(g(k, "x")), D(g(k, "z"))], S(g(k, "label")), 0.12)
            self.kings.append({"teamID": wt["teamID"], "faction": S(g(k, "faction")), "label": f"{wt['W']['label']} king",
                               "zoneId": S(g(k, "zoneId"))})
        # The fourth corner is the wild's (owner call, 2026-11-03): a raptor den with its hives, at war
        # with every king. It is no king: the throne is still the last commander standing.
        if has(theater, "raptorDen") and T(theater["raptorDen"]):
            den = theater["raptorDen"]
            self.add_raptor_camp([D(g(den, "x")), D(g(den, "z"))], False, S(g(den, "label")))
        self.log(fmt("Kings: {0}", ", ".join(S(k["faction"]) for k in self.kings)))

    def add_null_merc_camp(self, center: List[float], scale: float, allied: bool) -> None:
        team_id, ally_id = self._seat()
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, 0.16)})
        self.teams.append({"id": team_id, "side": "Legion", "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": MERC["rgb"], "label": "Null Mercs foothold", "faction": "nullmercs"})
        mfx = sign(self.enemy_center[0] - center[0]) or 1
        mfz = sign(self.enemy_center[1] - center[1]) or 1
        ally_p = D(self.arc_profile["allyPower"]) if self.arc_profile.get("allyPower") is not None else 1.0
        # SimpleAI supplies its own single commander at game start. No second commander in the recipe:
        # the engine commander is the foothold's builder anchor, while the Ashwalker kit stays
        # commander-free until the campaign explicitly reaches a base-building act.
        recipe = kits.merc_foothold(scale, self.patrol_target[0], self.patrol_target[1], mfx, mfz, ally_p)
        self.base_recipes[f"camp{team_id}_mercs"] = recipe
        self.forces.append({"id": f"camp{team_id}_mercs", "label": "Null Mercs foothold", "teamID": team_id,
                            "side": "Legion", "faction": "nullmercs", "role": "merc_foothold",
                            "base": {"x": center[0], "z": center[1]}, "recipe": f"camp{team_id}_mercs"})
        self.ai.append({"name": "SimpleAI(Null Mercs)", "shortName": "SimpleAI", "team": team_id, "version": "<not-versioned>"})
        if allied:
            self._ally(0, ally_id)

    def add_warband_packs(self, frm: List[float], to: List[float], scale: float) -> None:
        """Drop 3 act-1 texture: roving enemy strike packs sweeping the deploy->target axis. They ride
        the PRIMARY enemy camp's team (no new allyteam, no extra AI) so the map reads
        warband-vs-warband without faction-vs-itself accidents."""
        if self.primary_enemy_team_id is None or not T(self.primary_enemy_side):
            return
        t = faction(self.primary_enemy_side)
        if not T(t):
            return
        axis_x = to[0] - frm[0]
        axis_z = to[1] - frm[1]
        length = math.sqrt(axis_x * axis_x + axis_z * axis_z)
        if length < 0.001:
            length = 0.001
        perp_x = -axis_z / length
        perp_z = axis_x / length
        i = 0
        for frac, off in ((0.42, 0.10), (0.68, -0.10)):
            cx = clamp01(frm[0] + axis_x * frac + perp_x * off)
            cz = clamp01(frm[1] + axis_z * frac + perp_z * off)
            # Sweep back toward the deploy approach so packs cross the player's path.
            swx = clamp01(frm[0] + axis_x * (frac - 0.2))
            swz = clamp01(frm[1] + axis_z * (frac - 0.2))
            specs = [
                Spec(t["raider"], scaled_count(4, scale), 60, -60, 80, Patrol=patrol_sweep(swx, swz)),
                Spec(t["skirm"], scaled_count(3, scale), -70, 40, 90, Patrol=patrol_sweep(cx, cz)),
                Spec(t["assault"], scaled_count(2, scale), 0, 100, 95, Patrol=patrol_sweep(swx, swz)),
                Spec(t["radar"], 1, 0, 0, 100),
            ]
            rid = f"warband_pack_{i}"
            self.base_recipes[rid] = specs
            side = self.primary_enemy_side
            self.forces.append({"id": rid, "label": f"{side} warband", "teamID": self.primary_enemy_team_id,
                                "side": side, "faction": side.lower(), "role": "warband",
                                "base": {"x": cx, "z": cz}, "recipe": rid})
            i += 1
        self.log(fmt("Warband packs: {0} roving enemy packs on the {1} axis.", i, self.primary_enemy_side))

    def add_defector_camp(self, side: str, center: List[float], scale: float) -> None:
        """Drop 3 finale dressing: availableAllies defectors become a real allied team on the player's
        flank, grey-tinted hulls of the empire they walked out of."""
        t = faction(side)
        if not T(t):
            return
        team_id, ally_id = self._seat()
        label = "Cortex defectors" if ieq(side, "Cortex") else "Armada deserters"
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, 0.14)})
        self.teams.append({"id": team_id, "side": side, "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": [0.55, 0.55, 0.5], "label": label, "faction": f"{side.lower()}_defectors"})
        pt = self.patrol_target
        specs = [
            Spec(t["raider"], scaled_count(4, scale), 80, -60, 80, Patrol=patrol_sweep(pt[0], pt[1])),
            Spec(t["skirm"], scaled_count(3, scale), -80, 40, 90, Patrol=patrol_sweep(pt[0], pt[1])),
            Spec(t["assault"], scaled_count(2, scale), 0, 100, 95),
            Spec(t["radar"], 1, 0, -60, 100),
            Spec(t["aa"], 1, 60, 60, 150),
        ]
        self.base_recipes[f"camp{team_id}_defectors"] = specs
        self.forces.append({"id": f"camp{team_id}_defectors", "label": label, "teamID": team_id, "side": side,
                            "faction": f"{side.lower()}_defectors", "role": "defector_allies",
                            "base": {"x": center[0], "z": center[1]}, "recipe": f"camp{team_id}_defectors"})
        self.ai.append({"name": f"SimpleAI({label})", "shortName": "SimpleAI", "team": team_id, "version": "<not-versioned>"})
        self._ally(0, ally_id)
        self.log(fmt("Defector allies: {0} stand with the clans this finale.", label))

    def add_secondary_objective_camp(self, side: str, center: List[float], scale: float, secondary_id: str,
                                     required: bool, label: str) -> Optional[Dict[str, Any]]:
        """Drop 4 escalation: a side mark on the board. Small works (the mark itself,
        role=objective_secondary, which the gadget books into its own ledger) behind a light garrison."""
        t = faction(side)
        if not T(t):
            return None
        team_id, ally_id = self._seat()
        kind_word = "Objective" if required else "Bonus mark"
        camp_label = fmt("{0} - {1}", kind_word, label)
        self.ally_teams.append({"id": ally_id, "startRect": start_rect(center, 0.12)})
        self.teams.append({"id": team_id, "side": side, "allyTeam": ally_id, "base": [center[0], center[1]],
                           "rgb": t["rgb"], "label": camp_label, "faction": side.lower()})
        # The mark: a relay works the player must wreck (all of it).
        works = [Spec(t["radar"], 1, 0, 0, 100), Spec(t["solar"], 2, -70, 60, 90), Spec(t["hlt"], 1, 70, -50, 110)]
        # Teeth + a patrol pair; support hardware, NOT part of the mark.
        guard = [
            Spec(t["llt"], 2, -90, -70, 120),
            Spec(t["raider"], scaled_count(3, scale), 40, 130, 85, Patrol=patrol_sweep(center[0], center[1])),
            Spec(t["skirm"], scaled_count(2, scale), -40, -130, 90),
        ]
        self.base_recipes[f"sec{team_id}_works"] = works
        self.base_recipes[f"sec{team_id}_guard"] = guard
        self.forces.append({"id": f"sec{team_id}_works", "label": camp_label, "teamID": team_id, "side": side,
                            "faction": side.lower(), "role": "objective_secondary", "secondaryId": secondary_id,
                            "required": bool(required), "base": {"x": center[0], "z": center[1]},
                            "recipe": f"sec{team_id}_works"})
        self.forces.append({"id": f"sec{team_id}_guard", "label": f"{camp_label} guard", "teamID": team_id, "side": side,
                            "faction": side.lower(), "role": "garrison", "base": {"x": center[0], "z": center[1]},
                            "recipe": f"sec{team_id}_guard"})
        self.ai.append({"name": f"SimpleAI({camp_label})", "shortName": "SimpleAI", "team": team_id,
                        "version": "<not-versioned>"})
        self.log(fmt("Secondary objective: {0} ({1}) at ({2:n2}, {3:n2})", secondary_id,
                     "REQUIRED" if required else "bonus", center[0], center[1]))
        return {"id": secondary_id, "label": label, "required": bool(required), "x": center[0], "z": center[1],
                "teamID": team_id}
