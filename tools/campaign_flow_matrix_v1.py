#!/usr/bin/env python3
"""The campaign arc, read as a density matrix over the planet's zone lattice.

A scouting instrument. It assembles the whole campaign as one quantum object
and rolls it along the mission spine, so the SHAPE of the arc can be looked at
before any of it is spent on units and mechanics.

The object
----------
Basis: every zone on the planet -- 102 today, across seven maps -- plus one
extra mode for the planet's water. Dimension 103.

Each faction is a pure state |psi_f>: an amplitude spread over the ground it
holds and the corridors that ground can reach. The campaign is their mixture

    rho = sum_f w_f |psi_f><psi_f|  /  sum_f w_f

which is Hermitian, positive semi-definite and unit-trace by construction -- a
real density matrix, not a matrix that merely looks like one. Its rank is the
number of live powers, so the entire nonzero spectrum falls out of the small
faction Gram matrix

    G_fg = sqrt(w_f w_g) <psi_f|psi_g>

exactly, and fast enough to roll a whole campaign in well under a second. The
overlap <psi_f|psi_g> is the honest definition of two powers being entangled:
their reach runs through the same ground.

What the numbers say
--------------------
  purity Tr(rho^2)  1.0 = one power owns the whole story; low = a crowded war
  entropy S         von Neumann, in nats; exp(S) = effective number of powers
  gap lam1 - lam2   how decisively the leading power leads
  participation     how many zones the leading mode actually occupies, 0..1
  coherence         off-diagonal mass: how much of the war is CORRIDOR rather
                    than position. A campaign of disconnected sieges has none.
  water             rho's weight on the hydrology mode: how much of the
                    planet's story is underwater this mission

Provenance -- what is measured and what is a guess
--------------------------------------------------
Measured, used as-is: the zone lattice and its adjacency, the per-zone flood
curves, the planet water cycle, the act boundaries, the escalation ladder, and
the authored starting control in state/campaign_state.json.

AUTHORED, and the part to argue with: everything in FLOW below -- how much of a
zone a sortie converts, how far that spills, how fast the empires eat neutral
ground while the player's back is turned. The campaign's shape hangs on these
few numbers and they are guesses until a real playthrough measures them. They
are deliberately few, and deliberately at the top of the file.

Reads only. Never writes campaign state.

Usage:
  python tools/campaign_flow_matrix_v1.py --workspace .
  python tools/campaign_flow_matrix_v1.py --missions 18 --profile grinding
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import escalation_ladder_v1 as ladder  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402

SCHEMA = "verdance-campaign-flow/2.1"

# --------------------------------------------------------------------------
# The authored half. A handful of numbers decide the shape of the arc.
# --------------------------------------------------------------------------

FLOW: Dict[str, float] = {
    # Share of a visited zone's mass a sortie converts to the player.
    "claim": 0.55,
    # Share converted in each same-map neighbour of a visited zone -- the
    # sortie's shadow, the ground that changes hands because of what happened
    # next door rather than because anyone fought over it.
    "spill": 0.22,
    # Share of the neutral mass the empires absorb per mission, everywhere the
    # player is not. Scaled by the escalation ladder, so the world hardens
    # faster later. This is the clock the campaign is racing.
    "offscreen": 0.06,
    # How far a power's amplitude reaches along the lattice per diffusion step,
    # and how many steps. Two steps means "a zone I hold, its neighbours, and
    # their neighbours" carry my presence -- the source of all coherence here.
    "reach": 0.35,
    "steps": 2.0,
    # Scale of the Armada-NullMercs war relative to neutral absorption: how
    # hard the locally more active empire pushes the other's border zones.
    "rivalry": 0.5,
}

# Alternate readings of the same arc. Only the authored knobs move.
PROFILES: Dict[str, Dict[str, float]] = {
    "clean": {},
    "grinding": {"claim": 0.34, "spill": 0.12, "offscreen": 0.085},
    "losing": {"claim": 0.20, "spill": 0.06, "offscreen": 0.115},
    # Deliberately past anything a real player could do. It earns its place as
    # the upper bound: whatever shape the campaign has under `sweeping` is the
    # best shape this structure can produce, so anything missing there is
    # missing from the structure rather than from the player.
    "sweeping": {"claim": 0.95, "spill": 0.60, "offscreen": 0.005},
}

# How much of a faction's drowned holdings shows up as weight on the water
# mode. 1.0 would say a flooded zone is entirely a fact about water; this says
# it stays mostly a fact about the ground, and water is the loud minority.
HYDRO_GAIN = 0.6

# Same-map borders carry a power's reach freely; a strategic link between maps
# is a thinner thread, and must not let two theatres read as one place.
LINK_WEIGHT = {"same_map": 1.0, "strategic_link": 0.35}

PLAYER = "ashwalkers"
EMPIRES = ("armada", "cortex", "wild", "nullmercs")

# Unclaimed ground is not a power and does not get a state.
#
# It is tempting to give it one -- 82 of 102 zones read neutral at the opening,
# and a mode that large dominates every spectrum it appears in. But a power is
# coherent because it can move force along its corridors, and unclaimed ground
# cannot move anywhere. Modelled as one field it spans all seven maps at once
# and reads as the loudest thing in the campaign from the first mission to the
# last; modelled as seven it is still seven things nobody is doing. Either way
# the number it produces is a fact about the modelling, not about the war.
#
# So rho is over the powers actually contesting the planet. Empty ground shows
# up the way empty ground should: as near-zero weight on those zones, and in
# the separate control readout, which counts it honestly.
NEUTRAL = "neutral"

# --------------------------------------------------------------------------
# Temperaments: how each empire's activity rides the planet's swing.
#
# The hydrology already makes the terrain dynamic; this makes the factions
# dynamic the same way. `swing` is how much the waterlines moved into this
# mission, 0..1. An empire's activity that mission is
#
#     clamp(base + swingGain * swing + stillGain * (1 - swing))
#
# per map, using that map's own swing -- so a stable theatre and a drowning
# theatre pull differently on the same empire in the same mission.
#
# The owner's judgment call under test: the NullMercs are paid lines, and
# contracts are written when the ground holds still; the Armada is the
# adaptation faction, most active when the world is moving. The Cortex is
# deliberately NOT dynamic -- "they just continue to bunker and scout" -- so
# their entry is a constant, and their only expansion is a trickle into
# unclaimed ground on maps they already occupy. Every number here is a guess;
# the temperament experiment sweeps the gains.
# --------------------------------------------------------------------------

TEMPERAMENT: Dict[str, Dict[str, float]] = {
    "armada":    {"base": 0.35, "swingGain": 1.0, "stillGain": 0.0},
    "nullmercs": {"base": 0.35, "swingGain": 0.0, "stillGain": 1.0},
    "cortex":    {"base": 0.25, "swingGain": 0.0, "stillGain": 0.0},
}

# The Cortex are sturdy: anyone converting cortex ground -- the player included
# -- gets this fraction of the normal share. The engine agrees in its own way:
# offscreen clashes cannot flip armada or cortex ground at all (SOFT_CONTROLS).
CORTEX_HOLD = 0.15

# The raptors bloom in the wake of receding water -- a biological echo of the
# hydrology, one beat behind it. Per wild-presence map:
#
#     bloom(t) = decay * bloom(t-1) + gain * recession(t - lag)
#
# where recession is how far that map's waterline fell between two missions.
# While blooming, the wild converts ground on its own maps (unclaimed ground
# at full rate, empires at half, never the player's) and its weight in rho is
# temporarily boosted so the bloom is visible in the spectrum before subsiding.
BLOOM: Dict[str, float] = {
    "gain": 0.6,
    "decay": 0.45,
    "claim": 0.30,
    "spectral": 1.2,
    "lag": 1.0,
}

# The Ashwalkers stop being a raiding party halfway through. During the
# transition window the claim rate sags and frontier ground -- player zones on
# maps the mission is not on -- becomes convertible by whichever empire is
# locally most active. After the window the claim rises above baseline: the
# factory-backed press. Whether the dip is earned back with interest is what
# the regression experiment measures, not what these numbers assert.
PLAYER_ARC: Dict[str, float] = {
    "regressStart": 4.0,
    "regressEnd": 6.0,
    "regressClaim": 0.5,
    "regressHold": 0.5,
    # The transition's own pressure scale. It cannot ride `offscreen` -- that
    # rate is sized for eating unclaimed ground and would never dent a live
    # front. Giving ground has to be visible or the beat does not exist.
    "regressPressure": 0.3,
    "factoryClaim": 1.25,
}

# Opening drafts: candidate starting occupations, applied as overlays inside
# the instrument only. The authored state on disk stays exactly what it is;
# the owner picks a winner from the rolled results before anything is written.
OPENING_NAMES = ("current", "cold_war", "armada_ascendant", "patchwork")

# --------------------------------------------------------------------------
# The weather beneath the weather: seasons, tides, wind.
# --------------------------------------------------------------------------

# The planet's churn is conserved: the travelling wave keeps SOME theatre
# loud every mission, so at constant amplitude the planet as a whole never
# calms down and "the world is stable" is only ever true of a theatre.
# Seasons are the fix the first living-factions pass named: a slow envelope
# on the circulation's amplitude. The campaign opens in the calm, storms near
# the middle of each period, and the empires' eras -- merc contracts written
# in the calm, armada surges riding the storm -- get room to exist at
# campaign scale. depth 0 turns seasons off.
SEASONS: Dict[str, float] = {
    "period": 7.0,   # missions per full calm-storm-calm turn
    "depth": 0.6,    # how much of the cycle's amplitude the deep calm removes
    "offset": 0.0,   # where in the season mission 1 lands; 0 = the calm
}

# Owner-directed re-tuning of individual theatres, applied inside the
# instrument. Each entry stands in for an authored zone-map or hydrology edit
# until the translation pass lands it.
HYDRO_TUNE: Dict[str, Dict[str, float]] = {
    # "koom valley is getting too flooded, it should have room for some
    # permanent infrastructure on the flats away from the pools." The
    # waterline is capped: the pools and the scar still fill -- about a
    # quarter of the valley's weighted ground at the cap -- and the flats
    # above it never do.
    "koom_valley": {"cap": 0.45},
    # "rock jungle needs more water dynamics to drive raptor presence." The
    # measured curves say its water is standing water: shallows near-full at
    # every level, a flood swing of 0.065, so louder weather above it moves
    # nothing. The karst response is deepened instead -- every zone's flood
    # share moves `response` times as far from its resting share per unit of
    # waterline. The jungle drains and refills through the rock.
    "the_rock_jungle": {"response": 4.0},
}

# Within a mission the water is not a constant either. When a map's line is
# rising between missions, the ascending phase arrives as intermittent
# floods -- pulses on the ten-to-twenty-minute scale, a superposition of the
# old level and the new rather than a step between them. The instrument
# fights the average of the two levels when claiming there, and the pulses'
# recessions feed the raptors the same mission, no beat of lag.
TIDE: Dict[str, float] = {
    "pulses": 3.0,     # floods per rising mission; reporting and translation
    "bloomFeed": 0.5,  # rise times this joins the bloom's food immediately
}

# The wind is the other weather. Each map's range is authored in the map pool
# ("W4-12 avg6e/t" style); the storm runs the wind to the top of its range,
# the calm to the bottom, and the wind sets the pace of every economy on that
# map:  eco = floor + gain * (wind - poolMin) / (poolMax - poolMin).
# Tabula at the height of a storm runs nearly twice the pace of All That
# Simmers in a deep calm.
WIND: Dict[str, float] = {"floor": 0.7, "gain": 0.6}

# Owner calibration, verbatim: "expect the player to be massively more
# impactful then you expect." A straight multiplier on the player's claim and
# spill. Every protagonism finding is re-read under it by the impact
# experiment; the regime sweep runs at impact 1.0 so its claim axis still
# means what it says.
PLAYER_IMPACT = 2.0


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


# --------------------------------------------------------------------------
# The lattice
# --------------------------------------------------------------------------

class Lattice:
    """The planet as a weighted graph of zones, plus one mode for its water.

    Zone weight is share-of-its-own-map's-ground times a terrain multiplier,
    with every map contributing an equal share of the planet. That is a choice,
    not a measurement: it says the seven maps are seven equal theatres and a
    zone matters in proportion to how much of its theatre it is, sharpened by
    metal, chokes and buildable ground.
    """

    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        graph = load_json(self.workspace / "data" / "zone_maps" / "world_zone_graph.v1.json")
        nodes = [n for n in graph.get("nodes") or [] if n.get("zoneId")]
        self.nodes: List[Dict[str, Any]] = sorted(
            nodes, key=lambda n: (str(n.get("mapId")), str(n.get("zoneId")))
        )
        self.zone_ids: List[str] = [str(n["zoneId"]) for n in self.nodes]
        self.index: Dict[str, int] = {z: i for i, z in enumerate(self.zone_ids)}
        self.n = len(self.zone_ids)
        self.dim = self.n + 1  # + the water mode
        self.hydro_index = self.n
        self.map_of = {str(n["zoneId"]): str(n.get("mapId")) for n in self.nodes}
        self.role_of = {str(n["zoneId"]): str(n.get("role") or "") for n in self.nodes}
        self.label_of = {str(n["zoneId"]): str(n.get("label") or n["zoneId"]) for n in self.nodes}
        self.maps: List[str] = sorted({m for m in self.map_of.values()})

        self.zones_by_map: Dict[str, List[str]] = {m: [] for m in self.maps}
        for zid, mid in self.map_of.items():
            self.zones_by_map[mid].append(zid)
        for mid in self.zones_by_map:
            self.zones_by_map[mid].sort()

        self.weight: Dict[str, float] = self._zone_weights()
        self.neighbours: Dict[str, List[Tuple[str, float]]] = self._neighbours(graph)
        self.same_map_neighbours: Dict[str, List[str]] = {
            zid: [o for o, _w in nb if self.map_of.get(o) == self.map_of.get(zid)]
            for zid, nb in self.neighbours.items()
        }
        self.flood: Dict[str, Dict[str, Any]] = self._flood_curves()
        self.wind: Dict[str, Dict[str, float]] = self._wind()
        self.propagator = self._propagator()

    # -- construction ------------------------------------------------------

    def _zone_weights(self) -> Dict[str, float]:
        raw: Dict[str, float] = {}
        for mid in self.maps:
            zids = self.zones_by_map[mid]
            cells = {}
            for zid in zids:
                ev = self.nodes[self.index[zid]].get("evidence") or {}
                cells[zid] = float(ev.get("cellCount", 0.0) or 0.0)
            total = sum(cells.values()) or 1.0
            peak_metal = max(
                (float((self.nodes[self.index[z]].get("evidence") or {}).get("metalSpots", 0) or 0)
                 for z in zids), default=0.0
            ) or 1.0
            for zid in zids:
                ev = self.nodes[self.index[zid]].get("evidence") or {}
                metal = float(ev.get("metalSpots", 0) or 0) / peak_metal
                choke = clamp(float(ev.get("choke", 0.0) or 0.0))
                build = clamp(float(ev.get("buildable", 0.0) or 0.0))
                mult = 1.0 + 0.8 * metal + 0.4 * choke + 0.3 * build
                raw[zid] = (cells[zid] / total) * mult
        # Every map is one seventh of the planet.
        out: Dict[str, float] = {}
        for mid in self.maps:
            sub = sum(raw[z] for z in self.zones_by_map[mid]) or 1.0
            for zid in self.zones_by_map[mid]:
                out[zid] = raw[zid] / sub / len(self.maps)
        return out

    def _neighbours(self, graph: Dict[str, Any]) -> Dict[str, List[Tuple[str, float]]]:
        nb: Dict[str, List[Tuple[str, float]]] = {z: [] for z in self.zone_ids}
        for edge in graph.get("edges") or []:
            a, b = str(edge.get("from")), str(edge.get("to"))
            if a not in nb or b not in nb:
                continue
            kind = str(edge.get("kind") or "same_map")
            cost = max(1.0, float(edge.get("cost", 1) or 1))
            w = LINK_WEIGHT.get(kind, 0.5) / cost
            nb[a].append((b, w))
            nb[b].append((a, w))
        for zid in nb:
            nb[zid].sort()
        return nb

    def _flood_curves(self) -> Dict[str, Dict[str, Any]]:
        """Per-zone submerged share as a function of the map's waterline."""
        out: Dict[str, Dict[str, Any]] = {}
        for mid in self.maps:
            path = (self.workspace / "data" / "zone_maps" / "authored"
                    / (mid + ".authored.zone_map.json"))
            if not path.exists():
                continue
            data = load_json(path)
            levels = ((data.get("waterline") or {}).get("levels")) or []
            for zone in data.get("zones") or []:
                zid = str(zone.get("zoneId"))
                if zid not in self.index:
                    continue
                hyd = zone.get("hydrology") or {}
                out[zid] = {
                    "levels": [float(x) for x in levels],
                    "submergedAt": [float(x) for x in (hyd.get("submergedAt") or [])],
                    "floodsAt": float(hyd.get("floodsAt", 2.0) or 2.0),
                    "restingSubmerged": float(hyd.get("restingSubmerged", 0.0) or 0.0),
                }
        return out

    def _wind(self) -> Dict[str, Dict[str, float]]:
        """Per-map wind range, parsed from the authored map-pool heuristics.

        The pool writes wind as "W4-12 avg6e/t": minimum, maximum, average
        energy per tick. These are the workspace's own authored readings of
        the real maps' mapinfo wind, which is the thing that actually drives
        eco speed in BAR.
        """
        out: Dict[str, Dict[str, float]] = {}
        path = self.workspace / "data" / "map_pool" / "seven_maps.json"
        if not path.exists():
            return out
        for rec in load_json(path).get("maps") or []:
            mid = str(rec.get("id"))
            text = str((rec.get("heuristics") or {}).get("wind") or "")
            m = re.match(r"W(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s+avg(\d+(?:\.\d+)?)", text)
            if mid in self.zones_by_map and m:
                out[mid] = {"min": float(m.group(1)), "max": float(m.group(2)),
                            "avg": float(m.group(3))}
        return out

    def _propagator(self) -> List[List[Tuple[int, float]]]:
        """Row-normalised (I + reach*W) as a sparse adjacency, built once."""
        rows: List[List[Tuple[int, float]]] = []
        beta = float(FLOW["reach"])
        for zid in self.zone_ids:
            nb = self.neighbours[zid]
            total = sum(w for _o, w in nb) or 1.0
            row = [(self.index[zid], 1.0)]
            row.extend((self.index[o], beta * w / total) for o, w in nb)
            rows.append(row)
        return rows

    # -- queries -----------------------------------------------------------

    def submerged(self, zone_id: str, level: float) -> float:
        """Share of a zone underwater at this waterline (linear between rungs).

        A map with a HYDRO_TUNE `response` has its karst deepened: the flood
        share moves that many times as far from its resting share per unit of
        waterline, so standing water becomes living water.
        """
        curve = self.flood.get(zone_id)
        if not curve or not curve["levels"] or not curve["submergedAt"]:
            return 0.0
        levels, shares = curve["levels"], curve["submergedAt"]
        if level <= levels[0]:
            raw = clamp(shares[0])
        elif level >= levels[-1]:
            raw = clamp(shares[-1])
        else:
            raw = clamp(shares[-1])
            for k in range(1, len(levels)):
                if level <= levels[k]:
                    span = levels[k] - levels[k - 1]
                    t = 0.0 if span <= 0 else (level - levels[k - 1]) / span
                    raw = clamp(shares[k - 1] + t * (shares[k] - shares[k - 1]))
                    break
        resp = float(HYDRO_TUNE.get(self.map_of.get(zone_id, ""), {})
                     .get("response", 1.0))
        if resp == 1.0:
            return raw
        rest = clamp(shares[0])
        return clamp(rest + resp * (raw - rest))

    def flood_swing(self, map_id: str) -> float:
        """How much of a map's weighted ground the waterline moves, end to end.

        A map whose swing is near zero -- Greenest Fields' dry ramp -- has no
        weather to speak of, however the phase turns above it.
        """
        zids = self.zones_by_map.get(map_id) or []
        total = sum(self.weight[z] for z in zids) or 1.0
        full = sum(self.weight[z] * self.submerged(z, 1.0) for z in zids) / total
        dry = sum(self.weight[z] * self.submerged(z, 0.0) for z in zids) / total
        return full - dry

    def diffuse(self, vec: List[float], steps: int) -> List[float]:
        for _ in range(max(0, steps)):
            out = [0.0] * self.n
            for i, row in enumerate(self.propagator):
                v = vec[i]
                if v == 0.0:
                    continue
                for j, w in row:
                    out[j] += v * w
            vec = out
        return vec


# --------------------------------------------------------------------------
# Occupation: who holds what, mission by mission
# --------------------------------------------------------------------------

def seed_occupation(lattice: Lattice, state: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Mission-1 holdings, straight off the authored control in campaign state.

    82 of 102 zones read neutral today. That is not a gap in the data -- it is
    the campaign's opening position: a planet almost entirely unclaimed, which
    is the mass the whole arc then spends itself converting.
    """
    occ: Dict[str, Dict[str, float]] = {}
    memory = state.get("zoneMemory") or {}
    for zid in lattice.zone_ids:
        mid = lattice.map_of[zid]
        entry = (memory.get(mid) or {}).get(zid) or {}
        faction = str(
            entry.get("controllingFaction")
            or (entry.get("abstract") or {}).get("control")
            or "neutral"
        )
        occ.setdefault(faction, {})[zid] = lattice.weight[zid]
    return occ


def map_mass(lattice: Lattice, occ: Dict[str, Dict[str, float]],
             faction: str, map_id: str) -> float:
    zones = occ.get(faction) or {}
    return sum(zones.get(z, 0.0) for z in lattice.zones_by_map[map_id])


def _claim_whole_zone(occ: Dict[str, Dict[str, float]], zone_id: str, to: str) -> float:
    """Hand a zone's entire unclaimed mass to a faction. Opening drafts only."""
    amount = occ.get(NEUTRAL, {}).get(zone_id, 0.0)
    if amount <= 0.0:
        return 0.0
    occ[NEUTRAL][zone_id] = 0.0
    holder = occ.setdefault(to, {})
    holder[zone_id] = holder.get(zone_id, 0.0) + amount
    return amount


def _grow_block(lattice: Lattice, occ: Dict[str, Dict[str, float]],
                faction: str, map_id: str, target_share: float) -> None:
    """Grow a faction's holding on one map to a share of that map's mass.

    Growth is contiguous: each step claims the heaviest unclaimed zone
    adjacent to the block, falling back to the heaviest unclaimed zone
    anywhere on the map only when the frontier is exhausted -- a detached
    garrison rather than salted noise. Deterministic throughout.
    """
    zids = lattice.zones_by_map[map_id]
    total = sum(lattice.weight[z] for z in zids) or 1.0
    if map_mass(lattice, occ, faction, map_id) <= 0.0:
        seedable = sorted((z for z in zids if occ.get(NEUTRAL, {}).get(z, 0.0) > 0.0),
                          key=lambda z: (-lattice.weight[z], z))
        if not seedable:
            return
        _claim_whole_zone(occ, seedable[0], faction)
    guard = len(zids) + 1
    while map_mass(lattice, occ, faction, map_id) / total < target_share and guard > 0:
        guard -= 1
        block = {z for z in zids if occ.get(faction, {}).get(z, 0.0) > 0.0}
        frontier = sorted(
            (z for z in zids
             if occ.get(NEUTRAL, {}).get(z, 0.0) > 0.0
             and any(nb in block for nb in lattice.same_map_neighbours.get(z, []))),
            key=lambda z: (-lattice.weight[z], z))
        anywhere = sorted((z for z in zids if occ.get(NEUTRAL, {}).get(z, 0.0) > 0.0),
                          key=lambda z: (-lattice.weight[z], z))
        pick = frontier[0] if frontier else (anywhere[0] if anywhere else None)
        if pick is None:
            return
        _claim_whole_zone(occ, pick, faction)


def apply_opening(lattice: Lattice, occ: Dict[str, Dict[str, float]],
                  name: str) -> Dict[str, Dict[str, float]]:
    """One of the drafted starting occupations, applied as an overlay.

    Mutates and returns `occ`. Only unclaimed ground is reassigned: the
    player's opening, the cortex enclaves and the wild hives stay exactly as
    authored, whatever the draft. The state on disk is never touched -- the
    winner becomes a state edit later, on the owner's pick, not here.
    """
    if name in ("", "current"):
        return occ
    if name == "cold_war":
        # Two empires facing each other across every theatre, grown one zone
        # at a time in alternation so neither outruns the other to the middle.
        for mid in lattice.maps:
            total = sum(lattice.weight[z] for z in lattice.zones_by_map[mid]) or 1.0
            for _round in range(len(lattice.zones_by_map[mid])):
                grew = False
                for faction in ("armada", "nullmercs"):
                    if map_mass(lattice, occ, faction, mid) / total < 0.28:
                        before = map_mass(lattice, occ, faction, mid)
                        _grow_block(lattice, occ, faction, mid,
                                    (before / total) + 1e-9)
                        # one frontier zone per turn: grow to "just past current"
                        if map_mass(lattice, occ, faction, mid) > before:
                            grew = True
                if not grew:
                    break
    elif name == "armada_ascendant":
        # The occupying power, garrisoned everywhere -- except the cortex
        # crater, which it merely watches. The mercs are paid pockets inside.
        for mid in lattice.maps:
            _grow_block(lattice, occ, "armada", mid,
                        0.15 if mid == "eye_of_horus" else 0.5)
        for mid in lattice.maps:
            if map_mass(lattice, occ, "nullmercs", mid) > 0.0:
                before = map_mass(lattice, occ, "nullmercs", mid)
                total = sum(lattice.weight[z] for z in lattice.zones_by_map[mid]) or 1.0
                _grow_block(lattice, occ, "nullmercs", mid, (before / total) + 1e-9)
    elif name == "patchwork":
        # A planet of contracts: many small merc holdings, the armada
        # concentrated in a few strongholds.
        for mid in lattice.maps:
            total = sum(lattice.weight[z] for z in lattice.zones_by_map[mid]) or 1.0
            open_zones = sorted(z for z in lattice.zones_by_map[mid]
                                if occ.get(NEUTRAL, {}).get(z, 0.0) > 0.0)
            for z in open_zones[::2]:
                if map_mass(lattice, occ, "nullmercs", mid) / total >= 0.35:
                    break
                _claim_whole_zone(occ, z, "nullmercs")
        for mid in lattice.maps:
            if map_mass(lattice, occ, "armada", mid) > 0.0:
                _grow_block(lattice, occ, "armada", mid, 0.18)
    else:
        raise ValueError("unknown opening draft: {0}".format(name))
    return occ


def convert(occ: Dict[str, Dict[str, float]], zone_id: str, to: str, share: float) -> float:
    """Move `share` of every other holder's mass at this zone to `to`.

    Cortex ground yields at CORTEX_HOLD times the normal rate -- for everyone,
    the player included. Bunkers are bunkers.
    """
    share = clamp(share)
    if share <= 0.0:
        return 0.0
    moved = 0.0
    for faction, zones in occ.items():
        if faction == to:
            continue
        held = zones.get(zone_id, 0.0)
        if held <= 0.0:
            continue
        take = held * share * (CORTEX_HOLD if faction == "cortex" else 1.0)
        zones[zone_id] = held - take
        moved += take
    if moved > 0.0:
        holder = occ.setdefault(to, {})
        holder[zone_id] = holder.get(zone_id, 0.0) + moved
    return moved


def convert_from(occ: Dict[str, Dict[str, float]], zone_id: str,
                 frm: str, to: str, share: float) -> float:
    """Move `share` of one specific holder's mass at this zone to `to`."""
    share = clamp(share)
    held = occ.get(frm, {}).get(zone_id, 0.0)
    if share <= 0.0 or held <= 0.0:
        return 0.0
    take = held * share * (CORTEX_HOLD if frm == "cortex" else 1.0)
    occ[frm][zone_id] = held - take
    holder = occ.setdefault(to, {})
    holder[zone_id] = holder.get(zone_id, 0.0) + take
    return take


def mission_stop(lattice: Lattice, state: Dict[str, Any], number: int,
                 workspace: Path) -> Dict[str, Any]:
    """Where mission N happens, and what it is trying to take.

    The spine and the per-map objective tables still speak in pre-migration
    zone ids; the engine translates them forward at point of use, so this does
    the same rather than keeping a second copy of the mapping.
    """
    act = engine.act_for_mission(number)
    if act >= 3:
        path = str(state.get("pathSignal") or "B")
        plan = engine.FINALE_PLANS.get(path) or engine.FINALE_PLANS["B"]
        map_id = str(plan["mapId"])
        deploy = engine.canonical_zone_id(plan["deploymentZoneId"], workspace)
        target = engine.canonical_zone_id(plan["objective"]["targetZoneId"], workspace)
        kind = str(plan["kind"])
    else:
        map_id, deploy_raw = engine.ALPHA_SPINE[(number - 1) % len(engine.ALPHA_SPINE)]
        deploy = engine.canonical_zone_id(deploy_raw, workspace)
        objective = engine.objective_for_map(map_id, state) or {}
        target = engine.canonical_zone_id(objective.get("targetZoneId"), workspace)
        kind = str(objective.get("kind") or "sortie")
    if target not in lattice.index:
        target = deploy
    # Migration folded some old rectangles together; the engine separates them
    # again when it materialises the intent, and so must this.
    if deploy == target:
        options = sorted(z for z in lattice.same_map_neighbours.get(target, []) if z != target)
        if options:
            deploy = options[0]
    plan = ladder.plan_for_mission(number, is_finale=(act >= 3), workspace=workspace)
    window = plan.get("scaleWindow") or [1.0, 1.6]
    return {
        "missionNumber": number,
        "act": act,
        "mapId": map_id,
        "deployZoneId": deploy,
        "targetZoneId": target,
        "objectiveKind": kind,
        "escalation": round((float(window[0]) + float(window[1])) / 2.0, 3),
        "objectiveStrength": plan.get("objectiveStrength"),
    }


ABSORBERS = ("armada", "cortex", "nullmercs")


def resolve_mission(lattice: Lattice, occ: Dict[str, Dict[str, float]],
                    stop: Dict[str, Any], level: float,
                    flow: Dict[str, float],
                    dyn: Optional["Dynamics"] = None) -> Dict[str, Any]:
    """Play one mission abstractly: the player takes ground, the world moves.

    A drowned zone resists being claimed -- you cannot hold what is underwater
    -- so the claim scales by the dry share. The objective is still allowed to
    be flooded; taking a drowned basin is a fine mission, just a slower one.

    Without a Dynamics context the world behaves statically: every empire at
    its base activity, no bloom, no player transition. With one, everywhere
    the player is not:

      - each empire absorbs unclaimed ground in proportion to its presence
        and its weather-driven activity;
      - the locally more active of Armada and NullMercs pushes the other's
        border zones, so the front between them moves with the weather;
      - during the player's raiding-to-factories transition, their frontier
        ground yields to whichever empire is locally most awake;

    and on the wild maps, visited or not, the raptor bloom converts ground in
    the wake of receding water.
    """
    number = int(stop["missionNumber"])
    map_id = stop["mapId"]
    esc = float(stop["escalation"])
    claim_mult = dyn.claim_mult(number) if dyn else 1.0
    impact = dyn.player_impact if dyn else 1.0
    eco_here = dyn.eco(map_id, number) if dyn else 1.0

    def drier(zid: str) -> float:
        # The mission fights the tide's average, not the end-of-mission line.
        if dyn is not None:
            return 1.0 - dyn.mission_submerged(lattice, zid, number)
        return 1.0 - lattice.submerged(zid, level)

    claimed = 0.0
    for zid in (stop["deployZoneId"], stop["targetZoneId"]):
        if zid not in lattice.index:
            continue
        claimed += convert(occ, zid, PLAYER,
                           flow["claim"] * drier(zid) * claim_mult
                           * impact * eco_here)
    seen = {stop["deployZoneId"], stop["targetZoneId"]}
    spilled = 0.0
    for zid in list(seen):
        for nb in lattice.same_map_neighbours.get(zid, []):
            if nb in seen:
                continue
            seen.add(nb)
            spilled += convert(occ, nb, PLAYER,
                               flow["spill"] * drier(nb) * claim_mult
                               * impact * eco_here)

    absorbed: Dict[str, float] = {}
    rivalry: Dict[str, float] = {}
    bloomed = 0.0
    regressed = 0.0
    for other in lattice.maps:
        zids = lattice.zones_by_map[other]
        if other != map_id:
            # Each empire present eats unclaimed ground at a rate set by its
            # temperament under this map's weather, split by presence. The sum
            # of the rates never exceeds one, so the ground cannot be eaten
            # twice. Cortex is only ever present where it already sits, so its
            # trickle stays inside its own theatres by construction.
            present: Dict[str, float] = {}
            for faction in ABSORBERS:
                mass = map_mass(lattice, occ, faction, other)
                if mass > 1e-12:
                    present[faction] = mass
            total_present = sum(present.values())
            eco_there = dyn.eco(other, number) if dyn else 1.0
            if total_present > 0.0:
                rates = {}
                for faction, mass in present.items():
                    act = (dyn.activity(faction, other, number) if dyn
                           else TEMPERAMENT.get(faction, {}).get("base", 0.0))
                    rates[faction] = (clamp(flow["offscreen"] * esc * act
                                            * eco_there)
                                      * (mass / total_present))
                for zid in zids:
                    neutral = occ.get(NEUTRAL, {}).get(zid, 0.0)
                    if neutral <= 0.0:
                        continue
                    for faction, rate in sorted(rates.items()):
                        take = neutral * rate
                        if take <= 0.0:
                            continue
                        occ[NEUTRAL][zid] -= take
                        holder = occ.setdefault(faction, {})
                        holder[zid] = holder.get(zid, 0.0) + take
                        absorbed[faction] = absorbed.get(faction, 0.0) + take

            # The war the campaign is set against: whichever of the two
            # empires the weather favours here pushes the other's border.
            if dyn is not None:
                act_a = dyn.activity("armada", other, number)
                act_n = dyn.activity("nullmercs", other, number)
                attacker, defender = (("armada", "nullmercs") if act_a >= act_n
                                      else ("nullmercs", "armada"))
                rate = clamp(flow["offscreen"] * esc * flow.get("rivalry", 0.0)
                             * abs(act_a - act_n) * eco_there)
                if rate > 0.0 and attacker in present:
                    block = {z for z in zids
                             if occ.get(attacker, {}).get(z, 0.0) > 1e-12}
                    for zid in zids:
                        if occ.get(defender, {}).get(zid, 0.0) <= 1e-12:
                            continue
                        touching = zid in block or any(
                            nb in block
                            for nb in lattice.same_map_neighbours.get(zid, []))
                        if touching:
                            moved = convert_from(occ, zid, defender, attacker, rate)
                            if moved > 0.0:
                                rivalry[attacker] = rivalry.get(attacker, 0.0) + moved

            # The transition: while the player retools from raids to
            # factories, their frontier yields to whoever is most awake.
            if dyn is not None and dyn.regressing(number):
                best_f, best_act = None, 0.0
                for faction in ("armada", "nullmercs"):
                    if faction in present:
                        act = dyn.activity(faction, other, number)
                        if act > best_act:
                            best_f, best_act = faction, act
                if best_f is not None:
                    pressure = clamp(dyn.player_arc["regressPressure"] * esc
                                     * best_act * eco_there
                                     * (1.0 - dyn.player_arc["regressHold"]))
                    for zid in zids:
                        if occ.get(PLAYER, {}).get(zid, 0.0) > 1e-12:
                            regressed += convert_from(occ, zid, PLAYER, best_f, pressure)

        # The bloom does not care where the player is.
        bloom = dyn.bloom_at(other, number) if dyn else 0.0
        if bloom > 1e-9:
            rate = clamp(bloom * dyn.bloom_knobs["claim"])
            for zid in zids:
                moved = convert_from(occ, zid, NEUTRAL, "wild", rate)
                for faction in ABSORBERS:
                    moved += convert_from(occ, zid, faction, "wild", rate * 0.5)
                bloomed += moved

    return {
        "claimed": round(claimed, 5),
        "spilled": round(spilled, 5),
        "absorbed": {k: round(v, 5) for k, v in sorted(absorbed.items())},
        "rivalry": {k: round(v, 5) for k, v in sorted(rivalry.items())},
        "bloomed": round(bloomed, 5),
        "regressed": round(regressed, 5),
        "eco": round(eco_here, 4),
        "tide": dyn.tide_at(map_id, number) if dyn else None,
    }


# --------------------------------------------------------------------------
# The density matrix
# --------------------------------------------------------------------------

def faction_states(lattice: Lattice, occ: Dict[str, Dict[str, float]],
                   levels: Dict[str, float],
                   flow: Dict[str, float],
                   wild_boost: float = 0.0) -> Tuple[List[str], List[List[float]], List[float]]:
    """|psi_f> for each live power, and its weight w_f.

    A power's amplitude starts as sqrt of the mass it holds -- so |psi(i)|^2
    reads back as presence -- then diffuses along the lattice, which is where
    every off-diagonal element of rho comes from. Two zones couple when some
    power has amplitude at both: because it holds ground within reach of each,
    or because it stands in both places at once. Ground that nobody holds and
    nobody can reach couples to nothing, which is the whole difference from a
    similarity measure, where two equally empty zones read as identical and
    therefore maximally entangled.

    The drowned share of a power's holdings is lifted off the ground and onto
    the water mode, so a flooded theatre stops reading as territory and starts
    reading as weather.
    """
    names: List[str] = []
    vecs: List[List[float]] = []
    weights: List[float] = []
    for faction in sorted(occ):
        if faction == NEUTRAL:
            continue
        zones = occ[faction]
        mass = sum(zones.values())
        if mass <= 1e-9:
            continue
        dry = [0.0] * lattice.n
        drowned = 0.0
        for zid, held in zones.items():
            idx = lattice.index.get(zid)
            if idx is None or held <= 0.0:
                continue
            sub = lattice.submerged(zid, levels.get(lattice.map_of[zid], 0.0))
            dry[idx] = math.sqrt(max(0.0, held * (1.0 - sub)))
            drowned += held * sub
        spread = lattice.diffuse(dry, int(flow["steps"]))
        # Diffusion is not norm-preserving: (I + beta*W) hands every neighbour a
        # copy without taking anything back, so the ground amplitude inflates
        # while the water amplitude does not. Left uncorrected that alone would
        # bury the water mode -- a scaling artefact reading as a finding. Put
        # the spread back on the dry mass it started from.
        dry_mass = sum(x * x for x in dry)
        spread_norm = sum(x * x for x in spread)
        if spread_norm > 1e-18 and dry_mass > 0.0:
            rescale = math.sqrt(dry_mass / spread_norm)
            spread = [x * rescale for x in spread]
        vec = spread + [HYDRO_GAIN * math.sqrt(max(0.0, drowned))]
        norm = math.sqrt(sum(x * x for x in vec))
        if norm <= 1e-12:
            continue
        names.append(faction)
        vecs.append([x / norm for x in vec])
        # A blooming wild counts for more than the ground it holds: the boost
        # makes the surge visible in the spectrum, and renormalisation below
        # takes the extra weight out of everyone else's share, as a panic
        # about the raptors should.
        if faction == "wild" and wild_boost > 0.0:
            mass *= 1.0 + wild_boost
        weights.append(mass)
    total = sum(weights) or 1.0
    return names, vecs, [w / total for w in weights]


def density(lattice: Lattice, names: Sequence[str], vecs: Sequence[Sequence[float]],
            weights: Sequence[float]) -> Dict[str, Any]:
    """Everything rho has to say, without ever forming rho.

    rho = sum_f w_f |psi_f><psi_f| has rank len(names) -- five or six, never
    103 -- so its whole nonzero spectrum is the spectrum of the Gram matrix
    G_fg = sqrt(w_f w_g) <psi_f|psi_g>. That is exact, not an approximation,
    and it turns a 103x103 eigenproblem into a 6x6 one.
    """
    k = len(names)
    if k == 0:
        return {"eigenvalues": [], "diagonal": [0.0] * lattice.dim,
                "vecs": [], "weights": [], "names": []}
    gram = [[0.0] * k for _ in range(k)]
    for a in range(k):
        for b in range(a, k):
            dot = sum(x * y for x, y in zip(vecs[a], vecs[b]))
            g = math.sqrt(weights[a] * weights[b]) * dot
            gram[a][b] = g
            gram[b][a] = g
    vals, gvecs = engine.jacobi_eigen(gram)
    order = sorted(range(k), key=lambda i: -vals[i])
    eigenvalues = [max(0.0, vals[i]) for i in order]

    # The leading mode, lifted back into zone space.
    lead = gvecs[order[0]]
    mode = [0.0] * lattice.dim
    for f in range(k):
        c = lead[f] * math.sqrt(weights[f])
        if c == 0.0:
            continue
        vf = vecs[f]
        for i in range(lattice.dim):
            mode[i] += c * vf[i]
    norm = math.sqrt(sum(x * x for x in mode)) or 1.0
    mode = [x / norm for x in mode]

    diagonal = [0.0] * lattice.dim
    for f in range(k):
        w, vf = weights[f], vecs[f]
        for i in range(lattice.dim):
            diagonal[i] += w * vf[i] * vf[i]
    out = {
        "eigenvalues": eigenvalues,
        "gramOrder": [names[i] for i in order],
        "leadMode": mode,
        "leadCoeffs": {names[f]: round(lead[f], 5) for f in range(k)},
        "diagonal": diagonal,
        "vecs": [list(v) for v in vecs],
        "weights": list(weights),
        "names": list(names),
    }
    if k > 1:
        second = gvecs[order[1]]
        out["secondCoeffs"] = {names[f]: round(second[f], 5) for f in range(k)}
    return out


def dense(lattice: Lattice, rho: Dict[str, Any]) -> List[List[float]]:
    """Form rho for real. Only worth it to look at it or to check it -- the
    observables never need this and never build it."""
    vecs, weights = rho.get("vecs") or [], rho.get("weights") or []
    dim = lattice.dim
    out = [[0.0] * dim for _ in range(dim)]
    for w, v in zip(weights, vecs):
        for i in range(dim):
            wi = w * v[i]
            if wi == 0.0:
                continue
            row = out[i]
            for j in range(dim):
                row[j] += wi * v[j]
    return out


def coherence_l1(lattice: Lattice, rho: Dict[str, Any]) -> float:
    """Sum of |rho_ij| off the diagonal: the share of the war that is corridor.

    Computed straight from the factorisation, one row at a time, so the full
    103x103 matrix is never held.
    """
    vecs, weights = rho.get("vecs") or [], rho.get("weights") or []
    if not vecs:
        return 0.0
    dim = lattice.dim
    total = 0.0
    for i in range(dim):
        coeffs = [w * v[i] for w, v in zip(weights, vecs)]
        if all(abs(c) < 1e-15 for c in coeffs):
            continue
        for j in range(i + 1, dim):
            s = 0.0
            for c, v in zip(coeffs, vecs):
                s += c * v[j]
            total += abs(s)
    return 2.0 * total


def observables(lattice: Lattice, rho: Dict[str, Any],
                occ: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
    vals = rho.get("eigenvalues") or []
    if not vals:
        return {}
    purity = sum(v * v for v in vals)
    entropy = -sum(v * math.log(v) for v in vals if v > 1e-12)
    lam1 = vals[0]
    lam2 = vals[1] if len(vals) > 1 else 0.0
    mode = rho["leadMode"]
    zone_w = [mode[i] * mode[i] for i in range(lattice.n)]
    tot = sum(zone_w) or 1e-9
    zone_w = [w / tot for w in zone_w]
    ipr = sum(w * w for w in zone_w) or 1e-9
    part_ratio = 1.0 / ipr
    participation = clamp((part_ratio - 1.0) / max(1.0, lattice.n - 1))
    water = rho["diagonal"][lattice.hydro_index]
    mass = {f: sum(z.values()) for f, z in occ.items()}
    mass_total = sum(mass.values()) or 1.0
    # The second power: whose story the subplot is. The lead mode's own
    # protagonist is excluded -- a big player bleeds into every mode, and
    # "the player, again" is not an answer to "who is the antagonist". And
    # the rivalry overlap: how much of the two empires' wars runs through the
    # same ground -- <psi_armada|psi_nullmercs>, their honest entanglement.
    second = rho.get("secondCoeffs") or {}
    lead_coeffs = rho.get("leadCoeffs") or {}
    lead_f = (max(lead_coeffs.items(), key=lambda kv: abs(kv[1]))[0]
              if lead_coeffs else None)
    contenders = {f: v for f, v in second.items() if f != lead_f}
    second_mode = (max(contenders.items(), key=lambda kv: abs(kv[1]))[0]
                   if contenders else None)
    names = rho.get("names") or []
    overlap = None
    if "armada" in names and "nullmercs" in names:
        va = rho["vecs"][names.index("armada")]
        vn = rho["vecs"][names.index("nullmercs")]
        overlap = abs(sum(x * y for x, y in zip(va, vn)))
    return {
        "purity": round(purity, 5),
        "entropy": round(entropy, 5),
        "effectivePowers": round(math.exp(entropy), 4),
        "lambda1": round(lam1, 5),
        "lambda2": round(lam2, 5),
        "gap": round(lam1 - lam2, 5),
        "participation": round(participation, 5),
        "occupiedZones": round(part_ratio, 2),
        "coherence": round(coherence_l1(lattice, rho), 5),
        "water": round(water, 5),
        "control": {f: round(m / mass_total, 4) for f, m in sorted(mass.items()) if m > 1e-9},
        "leadCoeffs": rho.get("leadCoeffs", {}),
        "secondMode": second_mode,
        "secondCoeffs": second,
        "rivalryOverlap": round(overlap, 5) if overlap is not None else None,
    }


def top_zones(lattice: Lattice, rho: Dict[str, Any], limit: int = 6) -> List[Dict[str, Any]]:
    diagonal = rho["diagonal"]
    ranked = sorted(range(lattice.n), key=lambda i: -diagonal[i])[:limit]
    out = []
    for i in ranked:
        zid = lattice.zone_ids[i]
        out.append({
            "zoneId": zid,
            "mapId": lattice.map_of[zid],
            "label": lattice.label_of[zid],
            "role": lattice.role_of[zid],
            "rho": round(diagonal[i], 5),
        })
    return out


# --------------------------------------------------------------------------
# The arc
# --------------------------------------------------------------------------

def waterlines(state: Dict[str, Any], workspace: Path, phase: float) -> Dict[str, float]:
    """Per-map waterline at a given point in the planet's circulation.

    Runs the engine's own water cycle on a throwaway copy of the state, so the
    numbers here and the numbers a real mission would see are the same code.
    """
    probe = json.loads(json.dumps(state))
    hydro = engine.ensure_planet_hydrology(probe, workspace)
    hydro["phase"] = phase
    engine.distribute_planet_water(hydro)
    levels = {mid: float(rec.get("level", 0.0) or 0.0)
              for mid, rec in (hydro.get("maps") or {}).items()}
    # Owner-directed caps (HYDRO_TUNE): a capped map's pools fill and its
    # flats never do, whatever the circulation sends it.
    for mid, tune in HYDRO_TUNE.items():
        cap = tune.get("cap")
        if cap is not None and mid in levels:
            levels[mid] = min(levels[mid], float(cap))
    return levels


def bloom_series(recessions: Sequence[float], gain: float, decay: float) -> List[float]:
    """The raptor population wave a sequence of waterline recessions feeds.

    Pure so it can be tested against synthetic weather: bloom(t) =
    decay * bloom(t-1) + gain * recession(t). Lag is applied by the caller
    shifting the recession sequence, not here.
    """
    out: List[float] = []
    b = 0.0
    for r in recessions:
        b = decay * b + gain * max(0.0, r)
        out.append(b)
    return out


class Dynamics:
    """The world's pulse, precomputed for one whole arc.

    Everything time-varying that is not the player's own doing lives here:
    the per-map waterlines, the swing signal derived from them, each empire's
    activity under its temperament, and the raptor bloom trailing the floods.
    Precomputed up front so a rolled arc stays deterministic and cheap, and so
    an experiment can override any one piece without touching the others.

    `force_swing` pins every map's swing to a constant -- not a scenario the
    planet can produce, which is exactly why it is here: it isolates the
    temperament mechanism from the weather for directional tests.
    """

    def __init__(self, lattice: Lattice, state: Dict[str, Any], workspace: Path,
                 missions: int,
                 temperament: Optional[Dict[str, Dict[str, float]]] = None,
                 player_arc: Optional[Dict[str, float]] = None,
                 bloom: Optional[Dict[str, float]] = None,
                 phase_step: Optional[float] = None,
                 phase_offset: float = 0.0,
                 force_swing: Optional[float] = None,
                 seasons: Optional[Dict[str, float]] = None,
                 tide: Optional[Dict[str, float]] = None,
                 wind: Optional[Dict[str, float]] = None,
                 player_impact: Optional[float] = None) -> None:
        self.temperament = {f: dict(v) for f, v in TEMPERAMENT.items()}
        for f, over in (temperament or {}).items():
            self.temperament.setdefault(f, {}).update(over)
        self.player_arc = dict(PLAYER_ARC)
        self.player_arc.update(player_arc or {})
        self.bloom_knobs = dict(BLOOM)
        self.bloom_knobs.update(bloom or {})
        self.seasons = dict(SEASONS)
        self.seasons.update(seasons or {})
        self.tide_knobs = dict(TIDE)
        self.tide_knobs.update(tide or {})
        self.wind_knobs = dict(WIND)
        self.wind_knobs.update(wind or {})
        self.player_impact = (PLAYER_IMPACT if player_impact is None
                              else float(player_impact))
        self.phase_step = (engine.HYDRO_PHASE_STEP if phase_step is None
                           else float(phase_step))
        self.phase_offset = float(phase_offset)
        self.missions = int(missions)

        # The wind: per-map ranges from the map pool, normalised across it.
        self._wind_range = {m: dict(v) for m, v in lattice.wind.items()}
        mins = [w["min"] for w in self._wind_range.values()]
        maxs = [w["max"] for w in self._wind_range.values()]
        self._wind_lo = min(mins) if mins else 0.0
        self._wind_hi = max(maxs) if maxs else 1.0

        lag = max(0, int(self.bloom_knobs.get("lag", 0)))
        back = lag + 2  # swing needs one step of history, the bloom lag more

        # The waterline every map would see at every mission, plus a tail of
        # pre-campaign weather: the planet was circulating before mission 1,
        # and both the swing into the opening and the lagged bloom know it.
        self.levels: Dict[int, Dict[str, float]] = {}
        for n in range(-back, self.missions + 1):
            self.levels[n] = waterlines(state, workspace, self.phase_of(n))

        # The seasons: each map's deviation from its own mid-level is scaled
        # by the amplitude the season allows that mission. The circulation
        # still turns in a deep calm; it turns quietly. This is what lets the
        # planet as a whole have stable stretches -- without it the conserved
        # travelling wave keeps some theatre loud every single mission.
        depth = clamp(float(self.seasons.get("depth", 0.0)))
        if depth > 0.0:
            span = list(range(-back, self.missions + 1))
            mid_level: Dict[str, float] = {}
            for mid in lattice.maps:
                vals = [self.levels[n].get(mid, 0.0) for n in span]
                mid_level[mid] = (min(vals) + max(vals)) / 2.0
            caps = {m: float(HYDRO_TUNE.get(m, {}).get("cap", 1.0))
                    for m in lattice.maps}
            for n in span:
                amp = 1.0 - depth * (1.0 - self.storm(n))
                self.levels[n] = {
                    mid: clamp(mid_level[mid]
                               + amp * (self.levels[n].get(mid, 0.0)
                                        - mid_level[mid]),
                               0.0, caps[mid])
                    for mid in lattice.maps}

        # Swing: how far the waterlines moved into this mission. Each map is
        # read against its own loudest moment in this arc, so Koom's quiet is
        # measured against Koom's roar, not against the planet's -- otherwise
        # every mid-sized theatre reads as permanently still and the mercs
        # never sleep. A map whose flood moves no ground (Greenest Fields)
        # swings zero by fiat, whatever its waterline does. The planet swing
        # is the flood-weighted mean, against its own peak.
        fswing = {mid: max(0.0, lattice.flood_swing(mid)) for mid in lattice.maps}
        fs_total = sum(fswing.values()) or 1.0
        raw: Dict[int, Dict[str, float]] = {}
        for n in range(-back + 1, self.missions + 1):
            raw[n] = {mid: abs(self.levels[n][mid] - self.levels[n - 1][mid])
                      for mid in lattice.maps}
        peak_of = {mid: max((raw[n][mid] for n in raw), default=0.0)
                   for mid in lattice.maps}
        self._swing: Dict[int, Dict[str, float]] = {}
        self._planet: Dict[int, float] = {}
        planet_raw: Dict[int, float] = {}
        for n, row in raw.items():
            if force_swing is not None:
                self._swing[n] = {mid: clamp(force_swing) for mid in row}
                planet_raw[n] = clamp(force_swing)
                continue
            per = {}
            for mid, v in row.items():
                if fswing[mid] <= 1e-9 or peak_of[mid] <= 1e-9:
                    per[mid] = 0.0
                else:
                    per[mid] = clamp(v / peak_of[mid])
            self._swing[n] = per
            planet_raw[n] = sum(per[mid] * fswing[mid] for mid in per) / fs_total
        planet_peak = max(planet_raw.values(), default=0.0)
        for n, v in planet_raw.items():
            self._planet[n] = (v if force_swing is not None
                               else (v / planet_peak if planet_peak > 0 else 0.0))

        # The bloom, per wild-presence map, fed by lagged recession.
        occ = seed_occupation(lattice, state)
        self.wild_maps = sorted({lattice.map_of[z]
                                 for z in (occ.get("wild") or {})
                                 if (occ.get("wild") or {}).get(z, 0.0) > 0.0})
        gain = float(self.bloom_knobs.get("gain", 0.0))
        decay = clamp(float(self.bloom_knobs.get("decay", 0.0)))
        feed = float(self.tide_knobs.get("bloomFeed", 0.0))
        self._bloom: Dict[str, Dict[int, float]] = {}
        for mid in self.wild_maps:
            span = list(range(-back + 1 + lag, self.missions + 1))
            food: List[float] = []
            for n in span:
                # The mission-scale recession, one beat behind the flood; and
                # the tide's pulses, which flood and recede inside the rising
                # mission itself and feed the raptors on the spot.
                lagged = max(0.0, self.levels[n - lag - 1][mid]
                             - self.levels[n - lag][mid])
                rise = max(0.0, self.levels[n][mid] - self.levels[n - 1][mid])
                food.append(lagged + feed * rise)
            series = bloom_series(food, gain, decay)
            self._bloom[mid] = dict(zip(span, series))

    # -- queries -----------------------------------------------------------

    def phase_of(self, number: int) -> float:
        return round(self.phase_offset + (number - 1) * self.phase_step, 6)

    def levels_at(self, number: int) -> Dict[str, float]:
        return self.levels.get(number) or {}

    def storm(self, number: float) -> float:
        """Where the season stands: 0 the deep calm, 1 the height of the storm."""
        period = float(self.seasons.get("period", 0.0) or 0.0)
        if period <= 0.0:
            return 0.5
        x = (number - 1) / period + float(self.seasons.get("offset", 0.0))
        return 0.5 - 0.5 * math.cos(2.0 * math.pi * x)

    def tide_at(self, map_id: str, number: int) -> Dict[str, Any]:
        """The water's motion inside one mission on one map.

        Rising missions carry the intermittent floods -- the ascending phase
        as a superposition of the old level and the new, pulsing on the
        ten-to-twenty-minute scale. Falling missions are the drain the lagged
        bloom already eats; slack missions hold their line.
        """
        now = (self.levels.get(number) or {}).get(map_id, 0.0)
        prev = (self.levels.get(number - 1) or {}).get(map_id, now)
        delta = now - prev
        if delta > 1e-6:
            return {"dir": "rising", "range": round(delta, 4),
                    "pulses": int(self.tide_knobs.get("pulses", 0))}
        if delta < -1e-6:
            return {"dir": "falling", "range": round(-delta, 4), "pulses": 0}
        return {"dir": "slack", "range": 0.0, "pulses": 0}

    def mission_submerged(self, lattice: Lattice, zone_id: str,
                          number: int) -> float:
        """A zone's flooded share averaged over the mission's own tide.

        The waterline is not a constant inside a mission: the line moves from
        where it stood to where it is going, in pulses when rising, so what a
        claim fights is the average of the two levels, not the snapshot at
        either end.
        """
        mid = lattice.map_of.get(zone_id, "")
        now = (self.levels.get(number) or {}).get(mid, 0.0)
        prev = (self.levels.get(number - 1) or {}).get(mid, now)
        return 0.5 * (lattice.submerged(zone_id, now)
                      + lattice.submerged(zone_id, prev))

    def wind_at(self, map_id: str, number: int) -> float:
        """The wind on this map this mission, run up its range by the storm."""
        rec = self._wind_range.get(map_id)
        if not rec:
            return (self._wind_lo + self._wind_hi) / 2.0
        s = self.storm(number)
        return rec["min"] + (rec["max"] - rec["min"]) * s

    def eco(self, map_id: str, number: int) -> float:
        """The pace of everyone's economy on this map, set by the wind."""
        span = (self._wind_hi - self._wind_lo) or 1.0
        w01 = clamp((self.wind_at(map_id, number) - self._wind_lo) / span)
        return (float(self.wind_knobs.get("floor", 1.0))
                + float(self.wind_knobs.get("gain", 0.0)) * w01)

    def mean_eco(self, number: int) -> float:
        maps = sorted(self._wind_range)
        if not maps:
            return 1.0
        return sum(self.eco(m, number) for m in maps) / len(maps)

    def swing_at(self, map_id: str, number: int) -> float:
        return (self._swing.get(number) or {}).get(map_id, 0.0)

    def planet_swing(self, number: int) -> float:
        return self._planet.get(number, 0.0)

    def activity(self, faction: str, map_id: str, number: int) -> float:
        t = self.temperament.get(faction)
        if not t:
            return 0.0
        s = self.swing_at(map_id, number)
        return clamp(float(t.get("base", 0.0))
                     + float(t.get("swingGain", 0.0)) * s
                     + float(t.get("stillGain", 0.0)) * (1.0 - s))

    def mean_activity(self, faction: str, number: int) -> float:
        rows = self._swing.get(number) or {}
        if not rows:
            return float(self.temperament.get(faction, {}).get("base", 0.0))
        return sum(self.activity(faction, mid, number) for mid in rows) / len(rows)

    def bloom_at(self, map_id: str, number: int) -> float:
        return (self._bloom.get(map_id) or {}).get(number, 0.0)

    def planet_bloom(self, number: int) -> float:
        return max((self.bloom_at(mid, number) for mid in self.wild_maps),
                   default=0.0)

    def regressing(self, number: int) -> bool:
        return (self.player_arc["regressStart"] <= number
                <= self.player_arc["regressEnd"])

    def claim_mult(self, number: int) -> float:
        if self.regressing(number):
            return float(self.player_arc["regressClaim"])
        if number > self.player_arc["regressEnd"]:
            return float(self.player_arc["factoryClaim"])
        return 1.0


def run_arc(lattice: Lattice, state: Dict[str, Any], workspace: Path,
            missions: int, profile: str = "clean",
            dyn: Optional[Dynamics] = None,
            opening: str = "current") -> Dict[str, Any]:
    flow = dict(FLOW)
    flow.update(PROFILES.get(profile, {}))
    if dyn is None:
        dyn = Dynamics(lattice, state, workspace, missions)
    occ = apply_opening(lattice, seed_occupation(lattice, state), opening)
    steps: List[Dict[str, Any]] = []

    def pulse(number: int) -> Dict[str, Any]:
        return {
            "planetSwing": round(dyn.planet_swing(number), 4),
            "storm": round(dyn.storm(number), 4),
            "ecoMean": round(dyn.mean_eco(number), 4),
            "activity": {f: round(dyn.mean_activity(f, number), 4)
                         for f in sorted(dyn.temperament)},
            "bloom": round(dyn.planet_bloom(number), 4),
            "claimMult": round(dyn.claim_mult(number), 4) if number >= 1 else 1.0,
        }

    # Mission 0: the opening position, before anyone has done anything.
    levels = dyn.levels_at(1)
    names, vecs, weights = faction_states(lattice, occ, levels, flow)
    rho = density(lattice, names, vecs, weights)
    steps.append({
        "missionNumber": 0,
        "act": 0,
        "mapId": None,
        "objectiveKind": "opening position",
        "waterlines": {k: round(v, 4) for k, v in sorted(levels.items())},
        "dynamics": pulse(0),
        "observables": observables(lattice, rho, occ),
        "topZones": top_zones(lattice, rho),
    })

    for number in range(1, missions + 1):
        levels = dyn.levels_at(number)
        stop = mission_stop(lattice, state, number, workspace)
        outcome = resolve_mission(lattice, occ, stop,
                                  levels.get(stop["mapId"], 0.0), flow, dyn)
        boost = dyn.bloom_knobs.get("spectral", 0.0) * dyn.planet_bloom(number)
        names, vecs, weights = faction_states(lattice, occ, levels, flow,
                                              wild_boost=boost)
        rho = density(lattice, names, vecs, weights)
        record = dict(stop)
        record.update({
            "phase": dyn.phase_of(number),
            "waterline": round(levels.get(stop["mapId"], 0.0), 4),
            "waterlines": {k: round(v, 4) for k, v in sorted(levels.items())},
            "dynamics": pulse(number),
            "outcome": outcome,
            "observables": observables(lattice, rho, occ),
            "topZones": top_zones(lattice, rho),
        })
        steps.append(record)
    return {"profile": profile,
            "opening": opening,
            "flow": {k: round(v, 4) for k, v in sorted(flow.items())},
            "steps": steps}


# --------------------------------------------------------------------------
# Reading it back
# --------------------------------------------------------------------------

def water_against_spine(lattice: Lattice, state: Dict[str, Any], workspace: Path,
                        missions: int) -> Dict[str, Any]:
    """Every map's waterline at every mission, and which one is being played.

    The planet's circulation turns once every six missions; the mission spine
    turns once every seven. Whether a map is ever SEEN with water in it is
    decided entirely by how those two periods line up, and nothing in the
    campaign currently checks that they do.
    """
    rows: List[Dict[str, Any]] = []
    for number in range(1, missions + 1):
        phase = round((number - 1) * engine.HYDRO_PHASE_STEP, 6)
        levels = waterlines(state, workspace, phase)
        stop = mission_stop(lattice, state, number, workspace)
        rows.append({
            "missionNumber": number,
            "mapId": stop["mapId"],
            "levels": {k: round(v, 4) for k, v in sorted(levels.items())},
        })
    seen: Dict[str, List[float]] = {}
    for row in rows:
        seen.setdefault(str(row["mapId"]), []).append(row["levels"].get(row["mapId"], 0.0))
    span: Dict[str, Dict[str, float]] = {}
    for mid in lattice.maps:
        reachable = [r["levels"].get(mid, 0.0) for r in rows]
        visited = seen.get(mid) or []
        # How much of a map's ground the flood actually moves, end to end. A
        # map whose swing is small has nothing to gain from better timing.
        span[mid] = {
            "visits": len(visited),
            "seenAt": [round(v, 3) for v in visited],
            "peakAvailable": round(max(reachable) if reachable else 0.0, 3),
            "peakSeen": round(max(visited), 3) if visited else 0.0,
            "floodSwing": round(lattice.flood_swing(mid), 3),
        }
    return {"rows": rows, "perMap": span}


def regime_map(lattice: Lattice, state: Dict[str, Any], workspace: Path,
               missions: int,
               claims: Sequence[float] = (0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95),
               offscreens: Sequence[float] = (0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.10),
               ) -> Dict[str, Any]:
    """When -- and whether -- the campaign becomes a story about the player.

    For each pair of authored knobs, the mission at which the player first
    becomes the largest component of the dominant mode. That is the moment the
    war stops being something happening to them. It is worth sweeping because
    it does not behave like a difficulty slider: across most of the grid the
    answer is either "mission 1 or 2" or "never", with very little in between.
    """
    grid: List[Dict[str, Any]] = []
    # One weather for the whole sweep, at impact 1.0 -- the claim axis is
    # the effective claim, so it still means what it says under PLAYER_IMPACT.
    dyn = Dynamics(lattice, state, workspace, missions, player_impact=1.0)
    for claim in claims:
        for off in offscreens:
            knobs = dict(FLOW)
            knobs.update({"claim": claim, "spill": claim * 0.4, "offscreen": off})
            PROFILES["__probe__"] = dict(knobs)
            arc = run_arc(lattice, state, workspace, missions, "__probe__",
                          dyn=dyn)
            leads_at: Optional[int] = None
            for step in arc["steps"]:
                coeffs = step["observables"].get("leadCoeffs") or {}
                if not coeffs:
                    continue
                top = max(coeffs.items(), key=lambda kv: abs(kv[1]))[0]
                if top == PLAYER:
                    leads_at = int(step["missionNumber"])
                    break
            last = arc["steps"][-1]["observables"]
            grid.append({
                "claim": claim, "offscreen": off,
                "playerLeadsAt": leads_at,
                "finalPurity": round(last["purity"], 4),
                "finalGap": round(last["gap"], 4),
                "finalReach": round(last["participation"], 4),
            })
    PROFILES.pop("__probe__", None)
    return {"missions": missions, "claims": list(claims),
            "offscreens": list(offscreens), "grid": grid}


# --------------------------------------------------------------------------
# The experiments: developing the outcomes the owner asked about
# --------------------------------------------------------------------------

MODE_GLYPH = {"armada": "A", "nullmercs": "N", "cortex": "c",
              "wild": "w", "ashwalkers": "p"}


def player_leads_at(arc: Dict[str, Any]) -> Optional[int]:
    """First mission where the player is the largest piece of the lead mode."""
    for step in arc["steps"]:
        coeffs = step["observables"].get("leadCoeffs") or {}
        if coeffs and max(coeffs.items(), key=lambda kv: abs(kv[1]))[0] == PLAYER:
            return int(step["missionNumber"])
    return None


def second_mode_track(arc: Dict[str, Any]) -> str:
    """The antagonist's identity, mission by mission, as a glyph string."""
    out = []
    for step in arc["steps"][1:]:
        mode = step["observables"].get("secondMode")
        out.append(MODE_GLYPH.get(mode, "-") if mode else "-")
    return "".join(out)


def experiment_temperament(lattice: Lattice, state: Dict[str, Any],
                           workspace: Path, missions: int,
                           gains: Sequence[float] = (0.0, 0.5, 1.0, 1.5, 2.0),
                           opening: str = "cold_war") -> Dict[str, Any]:
    """Does the antagonist's identity actually ride the weather?

    Sweeps how hard the Armada leans into the swing against how hard the
    NullMercs lean into the still, and counts how often the second power's
    identity flips between them across the arc. Zero everywhere would say the
    temperament mechanism cannot express through the occupation; a large
    number at high gain would say the weather is playing the campaign.
    """
    grid: List[Dict[str, Any]] = []
    for ga in gains:
        for gn in gains:
            dyn = Dynamics(lattice, state, workspace, missions, temperament={
                "armada": {"swingGain": ga},
                "nullmercs": {"stillGain": gn},
            })
            arc = run_arc(lattice, state, workspace, missions, "clean",
                          dyn=dyn, opening=opening)
            track = second_mode_track(arc)
            empire_seq = [g for g in track if g in ("A", "N")]
            flips = sum(1 for a, b in zip(empire_seq, empire_seq[1:]) if a != b)
            last = arc["steps"][-1]["observables"]
            grid.append({
                "armadaSwingGain": ga,
                "nullmercsStillGain": gn,
                "antagonistFlips": flips,
                "secondModes": track,
                "finalArmada": last["control"].get("armada", 0.0),
                "finalMercs": last["control"].get("nullmercs", 0.0),
                "finalPlayer": last["control"].get(PLAYER, 0.0),
                "playerLeadsAt": player_leads_at(arc),
            })
    return {"gains": list(gains), "opening": opening, "grid": grid}


def experiment_regression(lattice: Lattice, state: Dict[str, Any],
                          workspace: Path, missions: int,
                          claims: Sequence[float] = (0.3, 0.5, 0.7),
                          holds: Sequence[float] = (0.2, 0.5, 0.8),
                          factories: Sequence[float] = (1.0, 1.25, 1.5),
                          opening: str = "cold_war") -> Dict[str, Any]:
    """The shape of the stumble: how deep, and is it earned back with interest.

    The ridge worth living on is where the player visibly gives ground in the
    transition window and still ends past their pre-dip self -- between
    "never really dips" on one side and "never recovers" on the other.
    """
    start = int(PLAYER_ARC["regressStart"])
    end = int(PLAYER_ARC["regressEnd"])
    grid: List[Dict[str, Any]] = []
    for rc in claims:
        for rh in holds:
            for fc in factories:
                dyn = Dynamics(lattice, state, workspace, missions, player_arc={
                    "regressClaim": rc, "regressHold": rh, "factoryClaim": fc,
                })
                arc = run_arc(lattice, state, workspace, missions, "clean",
                              dyn=dyn, opening=opening)
                masses = [s["observables"]["control"].get(PLAYER, 0.0)
                          for s in arc["steps"]]
                pure = [s["observables"]["purity"] for s in arc["steps"]]
                pre = masses[start - 1]
                dip = min(masses[start:end + 1])
                dip_at = masses.index(dip, start)
                recovered = next((i for i in range(end + 1, len(masses))
                                  if masses[i] > pre), None)
                grid.append({
                    "regressClaim": rc, "regressHold": rh, "factoryClaim": fc,
                    "preDipMass": round(pre, 4),
                    "dipMass": round(dip, 4),
                    "dipDepth": round(pre - dip, 4),
                    "dipMission": dip_at,
                    "recoveredAt": recovered,
                    "finalMass": round(masses[-1], 4),
                    "purityPeakMission": pure.index(max(pure)),
                })
    return {"claims": list(claims), "holds": list(holds),
            "factories": list(factories), "opening": opening, "grid": grid}


def experiment_openings(lattice: Lattice, state: Dict[str, Any],
                        workspace: Path, missions: int,
                        profiles: Sequence[str] = ("clean", "grinding",
                                                   "losing", "sweeping"),
                        ) -> Dict[str, Any]:
    """The four drafted worlds, rolled side by side for the owner to pick from."""
    dyn = Dynamics(lattice, state, workspace, missions)
    rows: List[Dict[str, Any]] = []
    for opening in OPENING_NAMES:
        for profile in profiles:
            arc = run_arc(lattice, state, workspace, missions, profile,
                          dyn=dyn, opening=opening)
            first = arc["steps"][0]["observables"]
            last = arc["steps"][-1]["observables"]
            rows.append({
                "opening": opening,
                "profile": profile,
                "openingPowers": first["effectivePowers"],
                "openingNeutral": first["control"].get(NEUTRAL, 0.0),
                "playerLeadsAt": player_leads_at(arc),
                "secondModes": second_mode_track(arc),
                "finalPurity": last["purity"],
                "finalPlayer": last["control"].get(PLAYER, 0.0),
                "finalArmada": last["control"].get("armada", 0.0),
                "finalMercs": last["control"].get("nullmercs", 0.0),
            })
    return {"profiles": list(profiles), "rows": rows}


def experiment_phase(lattice: Lattice, state: Dict[str, Any],
                     workspace: Path, missions: int,
                     offsets: Sequence[float] = (0.0, 1.0 / 12.0, 1.0 / 6.0,
                                                 0.25, 1.0 / 3.0, 5.0 / 12.0, 0.5),
                     steps: Sequence[float] = (1.0 / 5.0, 1.0 / 7.0),
                     opening: str = "cold_war") -> Dict[str, Any]:
    """Counterfactual weather: the same campaign under shifted or retimed rain.

    A global offset is the cheap rotation of HYDRO_RING -- every map's swell
    arrives that much later against the same spine. The alternate steps break
    the 6-against-7 phase-lock a different way, by changing how fast the
    circulation turns. What moves: whether Koom Valley is ever seen flooded,
    which empire the weather ends up favouring, and the arc's closing purity.
    """
    rows: List[Dict[str, Any]] = []
    variants = ([("offset", off, None) for off in offsets]
                + [("step", 0.0, st) for st in steps])
    for kind, off, st in variants:
        dyn = Dynamics(lattice, state, workspace, missions,
                       phase_offset=off, phase_step=st)
        arc = run_arc(lattice, state, workspace, missions, "clean",
                      dyn=dyn, opening=opening)
        seen: Dict[str, List[float]] = {}
        for step_rec in arc["steps"][1:]:
            seen.setdefault(str(step_rec["mapId"]), []).append(
                float(step_rec["waterline"]))
        last = arc["steps"][-1]["observables"]
        track = second_mode_track(arc)
        empire_seq = [g for g in track if g in ("A", "N")]
        rows.append({
            "kind": kind,
            "phaseOffset": round(off, 4),
            "phaseStep": round(st if st is not None else engine.HYDRO_PHASE_STEP, 4),
            "koomSeenPeak": round(max(seen.get("koom_valley") or [0.0]), 3),
            "visitedWaterMean": round(
                sum(v for vs in seen.values() for v in vs)
                / max(1, sum(len(vs) for vs in seen.values())), 3),
            "antagonistFlips": sum(1 for a, b in zip(empire_seq, empire_seq[1:])
                                   if a != b),
            "finalMargin": round(last["control"].get("armada", 0.0)
                                 - last["control"].get("nullmercs", 0.0), 4),
            "finalPurity": last["purity"],
            "finalPlayer": last["control"].get(PLAYER, 0.0),
        })
    return {"opening": opening, "rows": rows}


def experiment_bloom(lattice: Lattice, state: Dict[str, Any],
                     workspace: Path, missions: int,
                     gains: Sequence[float] = (0.3, 0.6, 1.2),
                     decays: Sequence[float] = (0.25, 0.45, 0.7),
                     opening: str = "cold_war") -> Dict[str, Any]:
    """Where the bloom is punctuation and where it becomes a power."""
    grid: List[Dict[str, Any]] = []
    for g in gains:
        for d in decays:
            dyn = Dynamics(lattice, state, workspace, missions,
                           bloom={"gain": g, "decay": d})
            arc = run_arc(lattice, state, workspace, missions, "clean",
                          dyn=dyn, opening=opening)
            blooms = [s["dynamics"]["bloom"] for s in arc["steps"]]
            wild = [s["observables"]["control"].get("wild", 0.0)
                    for s in arc["steps"]]
            track = second_mode_track(arc)
            grid.append({
                "gain": g, "decay": d,
                "peakBloom": round(max(blooms), 4),
                "peakWild": round(max(wild), 4),
                "finalWild": round(wild[-1], 4),
                "wildSecondMissions": track.count("w"),
                "secondModes": track,
            })
    return {"gains": list(gains), "decays": list(decays),
            "opening": opening, "grid": grid}


def experiment_seasons(lattice: Lattice, state: Dict[str, Any],
                       workspace: Path, missions: int,
                       periods: Sequence[float] = (5.0, 7.0, 9.0),
                       depths: Sequence[float] = (0.0, 0.4, 0.8),
                       opening: str = "cold_war") -> Dict[str, Any]:
    """Do the seasons give the planet a real calm and a real storm?

    The conserved travelling wave keeps planetary churn nearly constant, so
    without amplitude modulation "the world is stable" is never true of the
    world -- only of theatres. This sweeps the envelope's period and depth
    and watches whether planetary stability actually varies, whether the
    empires get eras (stretches where the weather favours one of them
    planet-wide), and whether the antagonist's identity starts riding it.
    """
    grid: List[Dict[str, Any]] = []
    for period in periods:
        for depth in depths:
            dyn = Dynamics(lattice, state, workspace, missions,
                           seasons={"period": period, "depth": depth})
            arc = run_arc(lattice, state, workspace, missions, "clean",
                          dyn=dyn, opening=opening)
            swings = [s["dynamics"]["planetSwing"] for s in arc["steps"][1:]]
            track = second_mode_track(arc)
            empire_seq = [g for g in track if g in ("A", "N")]
            flips = sum(1 for a, b in zip(empire_seq, empire_seq[1:]) if a != b)
            eras = "".join(
                ("A" if dyn.mean_activity("armada", s["missionNumber"])
                 > dyn.mean_activity("nullmercs", s["missionNumber"]) else "N")
                for s in arc["steps"][1:])
            last = arc["steps"][-1]["observables"]
            grid.append({
                "period": period, "depth": depth,
                "swingMin": round(min(swings), 3),
                "swingMax": round(max(swings), 3),
                "swingSpread": round(max(swings) - min(swings), 3),
                "eras": eras,
                "antagonistFlips": flips,
                "secondModes": track,
                "finalMargin": round(last["control"].get("armada", 0.0)
                                     - last["control"].get("nullmercs", 0.0), 4),
                "finalPurity": last["purity"],
            })
    return {"periods": list(periods), "depths": list(depths),
            "opening": opening, "grid": grid}


def experiment_impact(lattice: Lattice, state: Dict[str, Any],
                      workspace: Path, missions: int,
                      impacts: Sequence[float] = (1.0, 1.5, 2.0, 2.5, 3.0),
                      ) -> Dict[str, Any]:
    """How the story re-reads if the player is bigger than modelled.

    Owner calibration, verbatim: "expect the player to be massively more
    impactful then you expect." The protagonism finding -- dense openings
    costing the player the dominant mode -- is re-run across impact levels
    and every opening draft, so the opening pick can be made against the
    player's true size rather than the instrument's first guess.
    """
    rows: List[Dict[str, Any]] = []
    start = int(PLAYER_ARC["regressStart"])
    end = int(PLAYER_ARC["regressEnd"])
    for impact in impacts:
        dyn = Dynamics(lattice, state, workspace, missions,
                       player_impact=impact)
        for opening in OPENING_NAMES:
            arc = run_arc(lattice, state, workspace, missions, "clean",
                          dyn=dyn, opening=opening)
            masses = [s["observables"]["control"].get(PLAYER, 0.0)
                      for s in arc["steps"]]
            pre = masses[start - 1] if start < len(masses) else masses[-1]
            window = masses[start:end + 1]
            dip = min(window) if window else pre
            last = arc["steps"][-1]["observables"]
            rows.append({
                "impact": impact, "opening": opening,
                "playerLeadsAt": player_leads_at(arc),
                "dipDepth": round(pre - dip, 4),
                "finalPlayer": round(masses[-1], 4),
                "finalPurity": last["purity"],
            })
    return {"impacts": list(impacts), "rows": rows}


def _bar(value: float, lo: float, hi: float, width: int = 18) -> str:
    span = (hi - lo) or 1.0
    filled = int(round(clamp((value - lo) / span) * width))
    return "#" * filled + "." * (width - filled)


def write_report(payload: Dict[str, Any], path: Path) -> None:
    """A descriptive read of the trajectory. Grades nothing, decides nothing."""
    gen = payload["generatedFrom"]
    arcs = {a["profile"]: a for a in payload["arcs"]}
    lines: List[str] = []
    add = lines.append

    add("# Campaign flow, as a density matrix")
    add("")
    add("Generated by `tools/campaign_flow_matrix_v1.py`. This is a scouting")
    add("report: it describes the shape the campaign currently has, and does not")
    add("say what shape it should have.")
    add("")
    add("| | |")
    add("|---|---|")
    add("| basis | {0} zones + 1 water mode = dimension {1} |".format(
        gen["zones"], gen["dimension"]))
    add("| theatres | {0} maps |".format(gen["maps"]))
    add("| arc | {0} missions |".format(gen["missions"]))
    add("| rank of rho | number of live powers, never more than six |")
    add("")
    add("`rho = sum_f w_f |psi_f><psi_f| / sum_f w_f` over the factions' amplitude")
    add("fields. Hermitian, positive semi-definite and unit-trace by construction.")
    add("Its off-diagonal elements exist only where the zone lattice provides a")
    add("corridor, so coherence here means what it says: two places are entangled")
    add("when the same power's reach runs through both.")
    add("")
    add("**Measured inputs**, used as they stand: the zone lattice and its")
    add("adjacency, the per-zone flood curves, the planet water cycle, the act")
    add("boundaries, the escalation ladder, and the authored starting control in")
    add("`state/campaign_state.json`.")
    add("")
    add("**Authored inputs**, and the part to argue with: the flow knobs. Their")
    add("values are guesses until a real playthrough measures them.")
    add("")

    for name, arc in arcs.items():
        flow = arc["flow"]
        add("- `{0}` - claim {1}, spill {2}, offscreen {3}".format(
            name, flow["claim"], flow["spill"], flow["offscreen"]))
    add("")

    for name, arc in arcs.items():
        add("## The arc: `{0}`".format(name))
        add("")
        add("| # | act | map | water | objective | purity | entropy | powers | gap | occupies | coherence | water in rho |")
        add("|---:|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|")
        for step in arc["steps"]:
            o = step["observables"]
            add("| {0} | {1} | {2} | {3} | {4} | {5:.3f} | {6:.3f} | {7:.2f} | {8:.3f} | {9:.0f}z | {10:.1f} | {11:.4f} |".format(
                step["missionNumber"], step["act"] or "-",
                step.get("mapId") or "*opening*",
                ("{0:.2f}".format(step["waterline"]) if step.get("waterline") is not None else "-"),
                step.get("objectiveKind") or "-",
                o["purity"], o["entropy"], o["effectivePowers"], o["gap"],
                o["occupiedZones"], o["coherence"], o["water"]))
        add("")
        first, last = arc["steps"][0]["observables"], arc["steps"][-1]["observables"]
        steps = arc["steps"]
        pur = [s["observables"]["purity"] for s in steps]
        gap = [s["observables"]["gap"] for s in steps]
        coh = [s["observables"]["coherence"] for s in steps]
        peak = pur.index(max(pur))
        shape = ("tightens the whole way" if peak == len(pur) - 1
                 else "tightens to mission {0}, then gives ground back".format(
                     steps[peak]["missionNumber"]))
        add("Shape: **{0}**. Purity {1:.3f} -> {2:.3f} (peak {3:.3f} at m{4}), "
            "entropy {5:.3f} -> {6:.3f}, effective powers {7:.2f} -> {8:.2f}.".format(
                shape, first["purity"], last["purity"], max(pur),
                steps[peak]["missionNumber"],
                first["entropy"], last["entropy"],
                first["effectivePowers"], last["effectivePowers"]))
        add("")
        add("Gap peaks at m{0} ({1:.3f}), coherence at m{2} ({3:.1f}), "
            "reach ends at {4:.0f} of {5} zones.".format(
                steps[gap.index(max(gap))]["missionNumber"], max(gap),
                steps[coh.index(max(coh))]["missionNumber"], max(coh),
                last["occupiedZones"], gen["zones"]))
        add("")
        leads_at = None
        for step in steps:
            coeffs = step["observables"].get("leadCoeffs") or {}
            if coeffs and max(coeffs.items(), key=lambda kv: abs(kv[1]))[0] == PLAYER:
                leads_at = step["missionNumber"]
                break
        add("The player leads the dominant mode from **{0}**.".format(
            "mission {0}".format(leads_at) if leads_at is not None else "never"))
        add("")
        add("Who the leading mode is, mission by mission:")
        add("")
        add("```")
        for step in arc["steps"]:
            coeffs = sorted(step["observables"].get("leadCoeffs", {}).items(),
                            key=lambda kv: -abs(kv[1]))[:3]
            add("  m{0:<3} {1}".format(
                step["missionNumber"],
                "   ".join("{0} {1:+.3f}".format(k, v) for k, v in coeffs)))
        add("```")
        add("")
        add("Control of the planet, by share of weighted ground:")
        add("")
        add("```")
        for step in arc["steps"]:
            ctrl = step["observables"]["control"]
            add("  m{0:<3} player {1:>5.1%}  |{2}|  unclaimed {3:>5.1%}".format(
                step["missionNumber"], ctrl.get(PLAYER, 0.0),
                _bar(ctrl.get(PLAYER, 0.0), 0.0, 0.6),
                ctrl.get("neutral", 0.0)))
        add("```")
        add("")
        add("The world's pulse under this arc: the season's storm, the swing")
        add("the weather put into each mission, the pace the wind set, what it")
        add("all made of the empires' activity, the raptor bloom trailing the")
        add("floods, and who the second power was:")
        add("")
        add("```")
        for step in arc["steps"]:
            dyn_rec = step.get("dynamics") or {}
            act = dyn_rec.get("activity") or {}
            o = step["observables"]
            ctrl = o["control"]
            add("  m{0:<3} storm {1:>4.2f} swing {2:>4.2f} |{3}| eco {4:>4.2f} "
                "armada {5:.2f} mercs {6:.2f} bloom {7:>4.2f}  2nd {8:<10} "
                "A {9:>5.1%} N {10:>5.1%} w {11:>4.1%}".format(
                    step["missionNumber"],
                    dyn_rec.get("storm", 0.0),
                    dyn_rec.get("planetSwing", 0.0),
                    _bar(dyn_rec.get("planetSwing", 0.0), 0.0, 1.0, 10),
                    dyn_rec.get("ecoMean", 1.0),
                    act.get("armada", 0.0), act.get("nullmercs", 0.0),
                    dyn_rec.get("bloom", 0.0),
                    str(o.get("secondMode") or "-"),
                    ctrl.get("armada", 0.0), ctrl.get("nullmercs", 0.0),
                    ctrl.get("wild", 0.0)))
        add("```")
        add("")

    water = payload.get("water") or {}
    if water:
        add("## Water against the spine")
        add("")
        add("The planet's circulation turns once every six missions. The mission")
        add("spine turns once every seven. Whether a map is ever played with water")
        add("in it depends entirely on how those two periods line up.")
        add("")
        maps = sorted({m for row in water["rows"] for m in row["levels"]})
        add("| # | played | " + " | ".join(m.replace("_", " ") for m in maps) + " |")
        add("|---:|---|" + "---:|" * len(maps))
        for row in water["rows"]:
            cells = []
            for m in maps:
                v = "{0:.2f}".format(row["levels"].get(m, 0.0))
                cells.append("**[{0}]**".format(v) if m == row["mapId"] else v)
            add("| {0} | {1} | {2} |".format(
                row["missionNumber"], (row["mapId"] or "").replace("_", " "),
                " | ".join(cells)))
        add("")
        add("| map | visits | seen at | its own peak | flood swing |")
        add("|---|---:|---|---:|---:|")
        for mid in sorted(water["perMap"], key=lambda m: -water["perMap"][m]["floodSwing"]):
            rec = water["perMap"][mid]
            add("| {0} | {1} | {2} | {3:.2f} | {4:.0%} of the map |".format(
                mid.replace("_", " "), rec["visits"],
                ", ".join("{0:.2f}".format(v) for v in rec["seenAt"]) or "-",
                rec["peakAvailable"], rec["floodSwing"]))
        add("")
        add("`flood swing` is how much of a map's weighted ground the waterline")
        add("moves between empty and full - how much the flood is even capable of")
        add("changing there.")
        add("")
        tune = payload.get("hydroTune") or {}
        if tune.get("koomCap") is not None or tune.get("rockJungleResponse"):
            add("Two theatres are re-tuned here by owner direction, inside the")
            add("instrument only, standing in for authored map edits:")
            add("")
            if tune.get("koomCap") is not None:
                add("- Koom Valley's waterline is capped at {0:.2f}: the pools and"
                    .format(tune["koomCap"]))
                add("  the scar still fill, but at the cap only {0:.0%} of the valley"
                    .format(tune.get("koomFloodedAtCap", 0.0)))
                add("  is ever underwater -- the flats are permanent dry ground,")
                add("  room for infrastructure away from the pools.")
            if tune.get("rockJungleResponse"):
                add("- The Rock Jungle's karst response is deepened {0:.0f}x: its"
                    .format(tune["rockJungleResponse"]))
                add("  measured water is standing water (raw flood swing 0.065),")
                add("  so instead of louder weather its basins are made to drain")
                add("  and refill through the rock. Flood swing is now {0:.2f},"
                    .format(tune.get("rockJungleSwing", 0.0)))
                add("  which is what feeds the raptor bloom there.")
            add("")

    regime = payload.get("regime") or {}
    if regime:
        add("## When the campaign becomes a story about the player")
        add("")
        add("For each pair of authored knobs, the mission at which the player")
        add("first becomes the largest component of the dominant mode -- the")
        add("point where the war stops being something happening to them. `-`")
        add("means it never happens.")
        add("")
        offs = regime["offscreens"]
        add("| claim \\ offscreen | " + " | ".join("{0:.2f}".format(o) for o in offs) + " |")
        add("|---:|" + "---:|" * len(offs))
        by_key = {(g["claim"], g["offscreen"]): g for g in regime["grid"]}
        for claim in regime["claims"]:
            cells = []
            for off in offs:
                g = by_key.get((claim, off))
                if not g:
                    cells.append("-")
                elif g["playerLeadsAt"] is None:
                    cells.append("-")
                else:
                    cells.append(str(g["playerLeadsAt"]))
            add("| {0:.2f} | {1} |".format(claim, " | ".join(cells)))
        add("")
        led = [g["playerLeadsAt"] for g in regime["grid"]
               if g["playerLeadsAt"] is not None]
        early = [m for m in led if m <= 2]
        add("{0} of {1} settings hand the player the lead at some point, {2} of "
            "them by mission {3}. The two that never do sit in one corner: the "
            "lowest claim rate against the fastest offscreen clock.".format(
                len(led), len(regime["grid"]), len(early), 2))
        add("")
        add("So the question the grid answers is not *whether* the player becomes")
        add("the story -- across almost the whole space they do, and early. It is")
        add("how tightly the story closes once they have, which the second grid")
        add("shows moving smoothly from {0:.3f} to {1:.3f}.".format(
            min(g["finalPurity"] for g in regime["grid"]),
            max(g["finalPurity"] for g in regime["grid"])))
        add("")
        add("Final purity across the same grid -- how tightly the story closes:")
        add("")
        add("| claim \\ offscreen | " + " | ".join("{0:.2f}".format(o) for o in offs) + " |")
        add("|---:|" + "---:|" * len(offs))
        for claim in regime["claims"]:
            cells = []
            for off in offs:
                g = by_key.get((claim, off))
                cells.append("{0:.3f}".format(g["finalPurity"]) if g else "-")
            add("| {0:.2f} | {1} |".format(claim, " | ".join(cells)))
        add("")

    exps = payload.get("experiments") or {}
    if exps:
        add("## The dynamics experiments")
        add("")
        add("The living-world mechanisms -- temperaments riding the swing, the")
        add("Armada-NullMercs front, the raptor bloom, the player's transition")
        add("-- each swept across its authored knobs. All of these run on the")
        add("`cold_war` opening draft except the openings comparison itself: a")
        add("planet two empires already contest is where empire dynamics are")
        add("legible. Second-mode tracks read one glyph per mission:")
        add("A armada, N nullmercs, c cortex, w wild, p player, - none.")
        add("")

    temper = exps.get("temperament") or {}
    if temper:
        add("### Does the antagonist alternate with the weather?")
        add("")
        add("Antagonist flips (changes of second-power identity between the two")
        add("empires) across the arc, as the Armada leans harder into the swing")
        add("(rows) and the NullMercs lean harder into the still (columns):")
        add("")
        gains = temper["gains"]
        by_g = {(g["armadaSwingGain"], g["nullmercsStillGain"]): g
                for g in temper["grid"]}
        add("| armada \\ mercs | " + " | ".join("{0:.1f}".format(g) for g in gains) + " |")
        add("|---:|" + "---:|" * len(gains))
        for ga in gains:
            cells = []
            for gn in gains:
                g = by_g.get((ga, gn))
                cells.append(str(g["antagonistFlips"]) if g else "-")
            add("| {0:.1f} | {1} |".format(ga, " | ".join(cells)))
        add("")
        add("Second-mode tracks along the matched diagonal:")
        add("")
        add("```")
        for ga in gains:
            g = by_g.get((ga, ga))
            if g:
                add("  gain {0:.1f}   {1}   final armada {2:.1%}  mercs {3:.1%}  "
                    "player {4:.1%}".format(
                        ga, g["secondModes"], g["finalArmada"],
                        g["finalMercs"], g["finalPlayer"]))
        add("```")
        add("")

    regress = exps.get("regression") or {}
    if regress:
        add("### The shape of the stumble")
        add("")
        add("The player's transition from raiding party to factories, swept over")
        add("how hard the claim sags, how loosely the frontier is held, and how")
        add("hard the factory-backed press comes back. `recovered` is the first")
        add("mission the player's holdings exceed their pre-dip value; `-` means")
        add("the arc ends before they do.")
        add("")
        add("| claim x | hold | factory x | dip depth | dip at | recovered | final | purity peak |")
        add("|---:|---:|---:|---:|---:|---:|---:|---:|")
        for g in regress["grid"]:
            add("| {0:.2f} | {1:.2f} | {2:.2f} | {3:.4f} | m{4} | {5} | {6:.3f} | m{7} |".format(
                g["regressClaim"], g["regressHold"], g["factoryClaim"],
                g["dipDepth"], g["dipMission"],
                ("m{0}".format(g["recoveredAt"]) if g["recoveredAt"] is not None
                 else "-"),
                g["finalMass"], g["purityPeakMission"]))
        add("")

    opens = exps.get("openings") or {}
    if opens:
        add("### The four drafted worlds")
        add("")
        add("Candidate opening occupations, rolled through every profile. These")
        add("are overlays inside the instrument; the state on disk is untouched")
        add("until the owner picks one.")
        add("")
        add("| opening | profile | powers at m0 | unclaimed at m0 | player leads | final purity | player | armada | mercs |")
        add("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in opens["rows"]:
            add("| {0} | {1} | {2:.2f} | {3:.1%} | {4} | {5:.3f} | {6:.1%} | {7:.1%} | {8:.1%} |".format(
                r["opening"], r["profile"], r["openingPowers"],
                r["openingNeutral"],
                ("m{0}".format(r["playerLeadsAt"]) if r["playerLeadsAt"] is not None
                 else "-"),
                r["finalPurity"], r["finalPlayer"], r["finalArmada"],
                r["finalMercs"]))
        add("")

    phase = exps.get("phase") or {}
    if phase:
        add("### Counterfactual weather")
        add("")
        add("The same campaign under shifted or retimed rain. A global offset is")
        add("the cheap rotation of HYDRO_RING; the alternate steps change how")
        add("fast the circulation turns against the seven-map spine.")
        add("")
        add("| variant | offset | step | koom seen at best | mean water seen | flips | armada-mercs margin | final purity |")
        add("|---|---:|---:|---:|---:|---:|---:|---:|")
        for r in phase["rows"]:
            add("| {0} | {1:.3f} | {2:.3f} | {3:.2f} | {4:.2f} | {5} | {6:+.3f} | {7:.3f} |".format(
                r["kind"], r["phaseOffset"], r["phaseStep"], r["koomSeenPeak"],
                r["visitedWaterMean"], r["antagonistFlips"], r["finalMargin"],
                r["finalPurity"]))
        add("")

    bloom = exps.get("bloom") or {}
    if bloom:
        add("### The bloom: punctuation or power")
        add("")
        add("| gain | decay | peak bloom | peak wild | final wild | missions wild is 2nd |")
        add("|---:|---:|---:|---:|---:|---:|")
        for g in bloom["grid"]:
            add("| {0:.2f} | {1:.2f} | {2:.2f} | {3:.1%} | {4:.1%} | {5} |".format(
                g["gain"], g["decay"], g["peakBloom"], g["peakWild"],
                g["finalWild"], g["wildSecondMissions"]))
        add("")

    seasons = exps.get("seasons") or {}
    if seasons:
        add("### The seasons: a calm to be calm in")
        add("")
        add("The travelling wave conserves the planet's churn, so without an")
        add("amplitude envelope the planet is never stable -- only theatres")
        add("are. The envelope swept here is the fix: `spread` is how far the")
        add("planet's swing actually travels across the arc (0 would mean the")
        add("weather never changes character), and `eras` reads one glyph per")
        add("mission for which empire the weather favours planet-wide.")
        add("")
        add("| period | depth | swing min | swing max | spread | eras | flips | A-N margin | purity |")
        add("|---:|---:|---:|---:|---:|---|---:|---:|---:|")
        for g in seasons["grid"]:
            add("| {0:.0f} | {1:.1f} | {2:.2f} | {3:.2f} | {4:.2f} | `{5}` | {6} | {7:+.3f} | {8:.3f} |".format(
                g["period"], g["depth"], g["swingMin"], g["swingMax"],
                g["swingSpread"], g["eras"], g["antagonistFlips"],
                g["finalMargin"], g["finalPurity"]))
        add("")

    impact = exps.get("impact") or {}
    if impact:
        add("### How big the player really is")
        add("")
        add("Owner calibration: \"expect the player to be massively more")
        add("impactful then you expect.\" The same arcs, with the player's")
        add("claim and spill scaled -- the four opening drafts re-read against")
        add("the player's true size. The default the instrument now runs at")
        add("is impact {0:.1f}.".format(PLAYER_IMPACT))
        add("")
        add("| impact | opening | player leads | dip depth | final player | final purity |")
        add("|---:|---|---:|---:|---:|---:|")
        for r in impact["rows"]:
            add("| {0:.1f} | {1} | {2} | {3:.4f} | {4:.1%} | {5:.3f} |".format(
                r["impact"], r["opening"],
                ("m{0}".format(r["playerLeadsAt"])
                 if r["playerLeadsAt"] is not None else "-"),
                r["dipDepth"], r["finalPlayer"], r["finalPurity"]))
        add("")

    if exps:
        add("## Where these shapes would land")
        add("")
        add("Pointers for the translation pass, once shapes are chosen here.")
        add("Nothing below has been changed.")
        add("")
        add("- Temperaments -> `tick_zone`'s per-actor growth rates and")
        add("  `offscreen_clash_v1.ACTOR_BIAS`, keyed off `state[\"hydrology\"]`,")
        add("  which no engine system reads today.")
        add("- The Armada-NullMercs front -> `run_offscreen_clashes`, whose")
        add("  SOFT_CONTROLS currently exempts armada ground from ever flipping.")
        add("- The player's transition -> `apply_front_decay`, whose pressure")
        add("  gate (0.35) never opens in a fresh campaign.")
        add("- The bloom -> `reset_live_raptors_but_escalate` and the hazard")
        add("  model, fed by lagged waterline recession.")
        add("- Counterfactual weather -> the `HYDRO_RING` offsets (data change).")
        add("- The seasons -> an amplitude term on the circulation in")
        add("  `ensure_planet_hydrology` / `distribute_planet_water`, advanced")
        add("  per mission alongside the phase.")
        add("- The tides -> the campaign gadget: scripted in-mission flood")
        add("  pulses on the 10-20 minute scale while a map's line is rising.")
        add("- Koom Valley's cap -> the authored `koom_valley` zone-map")
        add("  waterline levels (flats above the capped line never flood).")
        add("- The Rock Jungle's karst -> the authored `the_rock_jungle`")
        add("  hydrology `submergedAt` curves, deepened to match the response.")
        add("- The wind -> the maps' real `minWind`/`maxWind` already drive eco")
        add("  in BAR; the season would set each mission's wind range in the")
        add("  generated startscript.")
        add("- Player impact -> the escalation ladder's scale windows and force")
        add("  generation, recalibrated against real playthrough data.")
        add("- The chosen opening draft -> an authored edit of")
        add("  `state/campaign_state.json` zoneMemory, owner-triggered.")
        add("")
        add("Standing defects noted while reading the engine, untouched here:")
        add("`offscreenActors` is keyed entirely by retired zone ids (45 of 45")
        add("stale; `ensure_zone_memory`'s setdefault will add new-id entries")
        add("alongside the orphans rather than heal them), and `map_waterline`")
        add("truncates the float phase to an int in the intent payload.")
        add("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").strip().split("\n")[0])
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--missions", type=int, default=0,
                    help="arc length; 0 = whatever the act structure delivers")
    ap.add_argument("--profile", default="", help="one profile, or blank for all")
    ap.add_argument("--json", default="", help="write the full trajectory here")
    ap.add_argument("--report", default="", help="write the markdown read here")
    ap.add_argument("--no-regime", action="store_true",
                    help="skip the knob sweep (49 extra arcs)")
    ap.add_argument("--no-experiments", action="store_true",
                    help="skip the dynamics experiments (~90 extra arcs)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    ws = Path(args.workspace).resolve()
    lattice = Lattice(ws)
    state = load_json(ws / "state" / "campaign_state.json")
    missions = args.missions or (engine.ACT2_END_MISSION + 1)
    profiles = [args.profile] if args.profile else list(PROFILES)

    arcs = [run_arc(lattice, state, ws, missions, p) for p in profiles]
    payload = {
        "schemaVersion": SCHEMA,
        "generatedFrom": {
            "zones": lattice.n,
            "maps": len(lattice.maps),
            "dimension": lattice.dim,
            "missions": missions,
        },
        "arcs": arcs,
        "water": water_against_spine(lattice, state, ws, missions),
    }
    if not args.no_regime:
        payload["regime"] = regime_map(lattice, state, ws, missions)
    koom = HYDRO_TUNE.get("koom_valley", {})
    trj = HYDRO_TUNE.get("the_rock_jungle", {})
    koom_zones = lattice.zones_by_map.get("koom_valley") or []
    koom_total = sum(lattice.weight[z] for z in koom_zones) or 1.0
    cap = float(koom.get("cap", 1.0))
    payload["hydroTune"] = {
        "koomCap": koom.get("cap"),
        "koomFloodedAtCap": round(
            sum(lattice.weight[z] * lattice.submerged(z, cap)
                for z in koom_zones) / koom_total, 4),
        "rockJungleResponse": trj.get("response"),
        "rockJungleSwing": round(lattice.flood_swing("the_rock_jungle"), 3),
    }
    if not args.no_experiments:
        payload["experiments"] = {
            "temperament": experiment_temperament(lattice, state, ws, missions),
            "regression": experiment_regression(lattice, state, ws, missions),
            "openings": experiment_openings(lattice, state, ws, missions),
            "phase": experiment_phase(lattice, state, ws, missions),
            "bloom": experiment_bloom(lattice, state, ws, missions),
            "seasons": experiment_seasons(lattice, state, ws, missions),
            "impact": experiment_impact(lattice, state, ws, missions),
        }
    out = Path(args.json) if args.json else ws / "outbox" / "campaign_flow.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    report = Path(args.report) if args.report else ws / "outbox" / "campaign_flow.latest.md"
    write_report(payload, report)
    print("{0} zones + water = dimension {1}; {2} missions; {3} profile(s) -> {4}".format(
        lattice.n, lattice.dim, missions, len(arcs), out))
    for arc in arcs:
        first = arc["steps"][0]["observables"]
        last = arc["steps"][-1]["observables"]
        print("  {0:9s} purity {1:.3f} -> {2:.3f}   entropy {3:.3f} -> {4:.3f}"
              "   powers {5:.2f} -> {6:.2f}".format(
                  arc["profile"], first["purity"], last["purity"],
                  first["entropy"], last["entropy"],
                  first["effectivePowers"], last["effectivePowers"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
