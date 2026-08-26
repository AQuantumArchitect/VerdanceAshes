#!/usr/bin/env python3
"""Cut zones out of measured terrain + bot behaviour.

Input:  data/terrain/<map>.terrain.json      (what the engine says the map is)
        data/behavior/<map>/*.raster.json    (what the bots did on it)
Output: data/zone_maps/authored/<map>.authored.zone_map.json  (schema 2.0)

The method, in one paragraph: every grid cell gets a feature vector (terrain +
behaviour). Seeds are placed at the peaks that matter -- where bases actually
got built, where units actually died, where traffic moves without stopping, and
at the centroids of large passable regions nothing else claimed. Cells are then
assigned to seeds by cheapest path, where "cheap" means similar ground you can
actually walk between; cliffs and deep water are expensive, so a zone does not
leak across a ridge. Small or near-identical regions are merged until the map
has between --min-zones and --max-zones of them. Each surviving region gets a
role from what it measurably IS (not from what a rectangle was called), an
anchor on buildable dry flat ground, and an evidence block recording the numbers
that justified it.

Usage:
  python tools/zone_cartographer_v1.py [--workspace .] [--maps a,b]
                                       [--min-zones 6] [--max-zones 12]
                                       [--out-dir data/zone_maps/authored]
                                       [--dry-run]
"""
from __future__ import annotations

import argparse
import heapq
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import map_symmetry_v1  # noqa: E402

ZONE_SCHEMA = "verdance-zone-map/2.0"

CH = {name: i for i, name in enumerate(
    ["height", "slope", "water", "buildable", "metal",
     "tankSpeed", "shipSpeed", "featureCount", "featureMetal"])}

HAZARD_HINTS = ("raptor", "scavenger", "critter", "chicken")

# Below the zone cap, two neighbours only fold together if they are this alike.
SIMILARITY_MERGE_COST = 0.55
# A region holding less than this share of all measured activity is dead ground
# and gets folded into a neighbour rather than named on the quest board.
DEAD_ZONE_SHARE = 0.01

# Roles emitted here MUST be readable by tools/quest_generator_v1.py --
# a role it does not know silently collapses the board to seize_lane.
ROLE_RULES = [
    # (role, label suffix, predicate over the region signature).
    # Behaviour thresholds are in "times the map average" units.
    ("raptor_wilds", "Wilds", lambda s: s["hazard"] >= 0.4),
    # Mostly-water ground is never a land lane, whatever moves across it.
    ("island_chain", "Shallows", lambda s: s["water"] >= 0.5),
    ("start", "Muster", lambda s: s["hasStart"] and s["structureDensity"] >= 1.0),
    # Hydrology. floodsAt is the normalized waterline at which the zone passes
    # half submerged; NEVER_FLOODS means the campaign's water cycle can never
    # reach it. Ground that drowns is territory of a different kind: worth
    # taking when it is dry, worth abandoning when it is not.
    ("spillway", "Spillway", lambda s: s["floodsAt"] <= 0.7 and s["choke"] >= 0.45),
    ("basin_floor", "Basin", lambda s: s["floodsAt"] <= 0.35),
    ("shoreline", "Shore", lambda s: s["floodsAt"] <= 0.7),
    ("fortress", "Bastion", lambda s: s["defence"] >= 0.35 and s["structureDensity"] >= 1.5),
    ("citadel", "Citadel", lambda s: s["defence"] >= 0.25 and s["structureDensity"] >= 1.0),
    ("main_field", "Field", lambda s: s["structureDensity"] >= 1.5 and s["metal"] >= 0.5),
    ("gate", "Gate", lambda s: s["choke"] >= 0.45 and s["transitDensity"] >= 1.2),
    ("lane", "Lane", lambda s: s["transitDensity"] >= 1.2 or s["fightDensity"] >= 1.5),
    ("energy_edge", "Works", lambda s: s["structureDensity"] >= 1.0 and s["contest"] < 0.25),
    ("island_chain", "Islands", lambda s: s["water"] >= 0.35),
    ("plateau", "Plateau", lambda s: s["relativeHeight"] >= 0.55 and s["buildable"] >= 0.3),
    # A narrow place stays a narrow place even where the behaviour prior is too
    # coarse to show traffic through it.
    ("causeway", "Causeway", lambda s: s["choke"] >= 0.45),
    ("rim_control", "Rim", lambda s: s["relativeHeight"] >= 0.45),
    # Quiet ground you can build on and there is metal under: not a battlefield,
    # but worth raiding. Better than calling half a map "pocket".
    ("reserve", "Reserve", lambda s: s["buildable"] >= 0.5 and s["metal"] > 0.0),
    ("flank_pocket", "Pocket", lambda s: True),
]

COMPASS_CODE = {
    "Northwest": "NW", "North": "N", "Northeast": "NE",
    "West": "W", "Central": "C", "East": "E",
    "Southwest": "SW", "South": "S", "Southeast": "SE",
}

# floodsAt for ground the campaign's waterline can never reach.
NEVER_FLOODS = 2.0

# How many zones each map wants, in unfolded terms. Bigger and more broken maps
# carry more; an open uniform map carries fewer because there is less to say
# about it. All inside the 12-18 band the owner set.
MAP_ZONE_TARGETS = {
    "greenest_fields": 12,
    "eye_of_horus": 12,
    "ancient_bastion": 14,
    "all_that_simmers": 16,
    "tabula": 16,
    "the_rock_jungle": 16,
    "koom_valley": 18,
}
DEFAULT_ZONE_TARGET = 14


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def clamp01(v: float) -> float:
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


class CellGrid:
    """Terrain + behaviour for one map, on a res x res grid."""

    def __init__(self, terrain: Dict[str, Any], rasters: Sequence[Dict[str, Any]],
                 symmetry: Optional[Dict[str, Any]] = None,
                 hydrology: Optional[Dict[str, Any]] = None):
        self.terrain = terrain
        self.res = int(terrain["grid"]["res"])
        self.cells = terrain["cells"]
        self.symmetry = symmetry
        self.hydrology = hydrology
        self.size = (float(terrain["size"]["x"]), float(terrain["size"]["z"]))
        self.map_id = terrain.get("mapId") or "unknown"
        self.map_name = terrain.get("mapName") or self.map_id
        self.starts = [(float(s["x"]), float(s["z"])) for s in terrain.get("startPositions") or []]
        self.metal_spots = terrain.get("metalSpots") or []

        n = self.res * self.res
        self.presence = [0.0] * n
        self.structure = [0.0] * n
        self.loss = [0.0] * n
        self.traffic = [0.0] * n
        self.defence = [0.0] * n
        self.hazard = [0.0] * n
        self.ally_presence: List[Dict[str, float]] = [defaultdict(float) for _ in range(n)]
        self.configs: List[str] = []
        # "measured" once a real cartography survey exists; until then every
        # behaviour number here is reconstructed from older, coarser telemetry
        # and must be readable as such downstream.
        sources = {str(r.get("source") or "measured") for r in rasters}
        self.behaviour_source = ("none" if not rasters
                                 else ("measured" if sources == {"measured"}
                                       else "+".join(sorted(sources))))

        for raster in rasters:
            self.configs.append(str(raster.get("configId") or "?"))
            hazard_allies = self._hazard_allies(raster)
            milestones = raster.get("milestones") or []
            if not milestones:
                continue
            # A behaviour raster binned on a different grid than the terrain must
            # be re-indexed, not truncated: raw indices from a coarser or finer
            # run would silently pile into the top-left of this grid.
            src_res = int(((raster.get("grid") or {}).get("res")) or self.res)
            remap = self._index_remapper(src_res)
            final = milestones[-1]
            for ally, channels in (final.get("allies") or {}).items():
                for key, target in (("presence", self.presence), ("structure", self.structure),
                                    ("loss", self.loss), ("traffic", self.traffic),
                                    ("defence", self.defence)):
                    for idx_s, value in (channels.get(key) or {}).items():
                        idx = remap(int(idx_s))
                        if idx is not None:
                            target[idx] += float(value)
                for idx_s, value in (channels.get("presence") or {}).items():
                    idx = remap(int(idx_s))
                    if idx is not None:
                        self.ally_presence[idx][str(ally)] += float(value)
                        if str(ally) in hazard_allies:
                            self.hazard[idx] += float(value)

        self.total_presence = sum(self.presence) or 1.0
        self.total_structure = sum(self.structure) or 1.0
        self.total_loss = sum(self.loss) or 1.0
        self.total_traffic = sum(self.traffic) or 1.0
        self.total_defence = sum(self.defence) or 1.0
        # A res x res grid over a non-square map has non-square cells: on a
        # 2:1 map an east-west step covers twice the ground a north-south step
        # does. Path costs are scaled so distance means elmos, not cell hops.
        cell_w = self.size[0] / self.res
        cell_h = self.size[1] / self.res
        mean_cell = (cell_w + cell_h) / 2.0 or 1.0
        self.step_x = cell_w / mean_cell
        self.step_z = cell_h / mean_cell

        heights = [c[CH["height"]] for c in self.cells]
        self.h_min, self.h_max = min(heights), max(heights)

        # Symmetry. Zones are cut on the QUOTIENT -- one fundamental domain --
        # and unfolded afterwards, so mirrored zones are exact images of each
        # other rather than two independent cuts that happen to look alike.
        # The cost field the cut walks over is symmetrized too; the true terrain
        # is kept intact for anchors, signatures and evidence, because a camp
        # has to stand on ground that is really buildable, not averagely so.
        self.sym_cells = self.cells
        self.rep = list(range(n))
        self.orbit_size = [1] * n
        if symmetry and symmetry.get("_ops") and len(symmetry["_ops"]) > 1:
            self._apply_symmetry(symmetry["_ops"])
        self.domain_cells = [i for i in range(n) if self.rep[i] == i]
        self.map_totals = {
            "cells": float(n),
            "presence": self.total_presence, "structure": self.total_structure,
            "loss": self.total_loss, "traffic": self.total_traffic,
            "defence": self.total_defence,
        }
        self.domain_totals = {
            "cells": float(len(self.domain_cells)),
            "presence": sum(self.presence[i] for i in self.domain_cells) or 1.0,
            "structure": sum(self.structure[i] for i in self.domain_cells) or 1.0,
            "loss": sum(self.loss[i] for i in self.domain_cells) or 1.0,
            "traffic": sum(self.traffic[i] for i in self.domain_cells) or 1.0,
            "defence": sum(self.defence[i] for i in self.domain_cells) or 1.0,
        }

        self.passable = [self._passable(i) for i in range(n)]
        self.choke = self._betweenness()

    def _index_remapper(self, src_res: int):
        """Map a cell index from a src_res x src_res grid onto this grid."""
        n = self.res * self.res
        if src_res <= 0 or src_res == self.res:
            def same(idx: int):
                return idx if 0 <= idx < n else None
            return same

        res = self.res

        def remap(idx: int):
            if idx < 0 or idx >= src_res * src_res:
                return None
            row, col = divmod(idx, src_res)
            return (row * res // src_res) * res + (col * res // src_res)
        return remap

    @staticmethod
    def _hazard_allies(raster: Dict[str, Any]) -> set:
        """Ally teams that are wildlife rather than a faction."""
        out = set()
        for team in raster.get("teams") or []:
            side = str(team.get("side") or "").lower()
            if any(hint in side for hint in HAZARD_HINTS):
                out.add(str(team.get("allyTeam")))
        return out

    def _apply_symmetry(self, ops: Sequence[Any]) -> None:
        """Average every field over the symmetry orbit and record the quotient."""
        res, n = self.res, self.res * self.res
        self.sym_ops = list(ops)

        orbits: List[List[int]] = []
        for idx in range(n):
            row, col = divmod(idx, res)
            members = sorted({op(row, col, res)[0] * res + op(row, col, res)[1]
                              for op in ops})
            canon = members[0]
            self.rep[idx] = canon
            self.orbit_size[idx] = len(members)
            if canon == idx:
                orbits.append(members)

        # Terrain: a symmetrized copy for the cut to walk over.
        channels = len(self.cells[0])
        sym = [list(c) for c in self.cells]
        for members in orbits:
            for ch in range(channels):
                mean = sum(self.cells[m][ch] for m in members) / len(members)
                for m in members:
                    sym[m][ch] = mean
        self.sym_cells = sym

        # Behaviour: the prior is weak and one-sided by accident of which corner
        # the bots spawned in. Averaging it over the orbit stops that accident
        # from deciding where a zone boundary lands.
        for field in ("presence", "structure", "loss", "traffic", "defence", "hazard"):
            values = getattr(self, field)
            for members in orbits:
                mean = sum(values[m] for m in members) / len(members)
                for m in members:
                    values[m] = mean

    def is_symmetric(self) -> bool:
        return len(self.domain_cells) < self.res * self.res

    def work_cells(self) -> List[int]:
        """Cells the cut actually operates on: the quotient when symmetric."""
        return self.domain_cells

    def work_neighbours(self, idx: int) -> Iterable[int]:
        """Neighbours in quotient space -- crossing the symmetry axis folds back."""
        seen = set()
        for nb in self.neighbours(idx):
            canon = self.rep[nb]
            if canon != idx and canon not in seen:
                seen.add(canon)
                yield canon

    def images_of(self, idx: int) -> List[int]:
        res = self.res
        row, col = divmod(idx, res)
        ops = getattr(self, "sym_ops", None)
        if not ops:
            return [idx]
        out: List[int] = []
        for op in ops:
            rr, cc = op(row, col, res)
            image = rr * res + cc
            if image not in out:
                out.append(image)
        return out

    def step_cost(self, a: int, b: int) -> float:
        """Ground distance of one grid step, in mean-cell units."""
        return self.step_z if abs(a - b) >= self.res else self.step_x

    def _passable(self, idx: int) -> bool:
        # Symmetrized, so growth cannot walk through a gap on one side of the
        # map that its mirror does not have.
        c = self.sym_cells[idx]
        if c[CH["water"]] >= 0.6:
            return False
        return c[CH["slope"]] < 0.45 and c[CH["tankSpeed"]] > 0.05

    def truly_passable(self, idx: int) -> bool:
        """Unsymmetrized -- for anything that has to be true on the ground."""
        c = self.cells[idx]
        if c[CH["water"]] >= 0.6:
            return False
        return c[CH["slope"]] < 0.45 and c[CH["tankSpeed"]] > 0.05

    def neighbours(self, idx: int) -> Iterable[int]:
        row, col = divmod(idx, self.res)
        if row > 0:
            yield idx - self.res
        if row < self.res - 1:
            yield idx + self.res
        if col > 0:
            yield idx - 1
        if col < self.res - 1:
            yield idx + 1

    def cell_norm(self, idx: int) -> Tuple[float, float]:
        row, col = divmod(idx, self.res)
        return ((col + 0.5) / self.res, (row + 0.5) / self.res)

    def cell_world(self, idx: int) -> Tuple[float, float]:
        nx, nz = self.cell_norm(idx)
        return (nx * self.size[0], nz * self.size[1])

    def world_to_idx(self, x: float, z: float) -> int:
        col = min(self.res - 1, max(0, int(x / self.size[0] * self.res)))
        row = min(self.res - 1, max(0, int(z / self.size[1] * self.res)))
        return row * self.res + col

    def relative_height(self, idx: int) -> float:
        span = (self.h_max - self.h_min) or 1.0
        return clamp01((self.cells[idx][CH["height"]] - self.h_min) / span)

    def sym_relative_height(self, idx: int) -> float:
        span = (self.h_max - self.h_min) or 1.0
        return clamp01((self.sym_cells[idx][CH["height"]] - self.h_min) / span)

    def _traverse_anchors(self) -> List[int]:
        """Places worth travelling between: authored starts, base mass peaks,
        and failing both, the extremes of the largest passable region."""
        anchors: List[int] = []
        for x, z in self.starts:
            idx = self.world_to_idx(x, z)
            if self.passable[idx]:
                anchors.append(idx)
        sep = max(3, self.res // 6)
        for idx in local_maxima(self, self.structure, 6, sep):
            if self.passable[idx] and idx not in anchors:
                anchors.append(idx)
        if len(anchors) < 2:
            passable = [i for i in range(self.res * self.res) if self.passable[i]]
            if len(passable) >= 2:
                corners = [(0, 0), (0, self.res - 1), (self.res - 1, 0), (self.res - 1, self.res - 1)]
                for cr, cc in corners:
                    nearest = min(passable, key=lambda i: (divmod(i, self.res)[0] - cr) ** 2
                                                          + (divmod(i, self.res)[1] - cc) ** 2)
                    if nearest not in anchors:
                        anchors.append(nearest)
        return anchors

    def _betweenness(self) -> List[float]:
        """How much of the map's through-traffic MUST cross each cell.

        Shortest paths between anchor pairs over walkable ground; a cell that
        every route has to use is a gate. This is the terrain half of the gate
        test -- the behaviour half is measured traffic."""
        n = self.res * self.res
        counts = [0.0] * n
        anchors = self._traverse_anchors()
        if len(anchors) < 2:
            return counts
        for ai, source in enumerate(anchors):
            dist = [float("inf")] * n
            prev = [-1] * n
            dist[source] = 0.0
            heap: List[Tuple[float, int]] = [(0.0, source)]
            while heap:
                cost, idx = heapq.heappop(heap)
                if cost > dist[idx]:
                    continue
                for nb in self.neighbours(idx):
                    if not self.passable[nb]:
                        continue
                    step = (cost + self.step_cost(idx, nb)
                            + 3.0 * self.cells[nb][CH["slope"]])
                    if step < dist[nb] - 1e-9:
                        dist[nb] = step
                        prev[nb] = idx
                        heapq.heappush(heap, (step, nb))
            for target in anchors[ai + 1:]:
                if dist[target] == float("inf"):
                    continue
                cur = target
                while cur != -1 and cur != source:
                    counts[cur] += 1.0
                    cur = prev[cur]
        peak = max(counts) or 1.0
        return [clamp01(c / peak) for c in counts]

    def transit_score(self, idx: int) -> float:
        """Movement that does not settle: traffic without structures."""
        traffic = self.traffic[idx] / self.total_traffic
        structure = self.structure[idx] / self.total_structure
        return clamp01(traffic * 3.0 - structure * 1.5)

    def has_activity(self) -> bool:
        return sum(self.presence) > 0


def dissimilarity(grid: CellGrid, a: int, b: int) -> float:
    """Cost of letting one zone span both cells."""
    ca, cb = grid.sym_cells[a], grid.sym_cells[b]
    cost = grid.step_cost(a, b)
    cost += 4.0 * abs(grid.sym_relative_height(a) - grid.sym_relative_height(b))
    cost += 3.0 * abs(ca[CH["water"]] - cb[CH["water"]])
    cost += 2.0 * abs(ca[CH["buildable"]] - cb[CH["buildable"]])
    cost += 3.0 * max(ca[CH["slope"]], cb[CH["slope"]])
    if not grid.passable[b]:
        cost += 6.0
    if grid.passable[a] != grid.passable[b]:
        cost += 4.0
    return cost


def local_maxima(grid: CellGrid, values: Sequence[float], count: int,
                 min_sep_cells: int, threshold: float = 0.0) -> List[int]:
    """Highest cells, greedily spaced apart."""
    order = sorted((i for i in grid.work_cells() if values[i] > threshold),
                   key=lambda i: (-values[i], i))
    picked: List[int] = []
    for idx in order:
        row, col = divmod(idx, grid.res)
        if all(max(abs(row - divmod(p, grid.res)[0]), abs(col - divmod(p, grid.res)[1])) >= min_sep_cells
               for p in picked):
            picked.append(idx)
            if len(picked) >= count:
                break
    return picked


def choose_seeds(grid: CellGrid, target: int) -> List[Dict[str, Any]]:
    """Seed where the map has something to say: bases, kills, traffic, starts,
    and the middle of any large region none of those touched.

    On a symmetric map this runs in the fundamental domain and asks for
    target/order seeds -- unfolding multiplies them back up."""
    sep = max(2, grid.res // 10)
    seeds: List[Dict[str, Any]] = []
    used: set = set()

    def add(idx: int, kind: str) -> None:
        idx = grid.rep[idx]
        row, col = divmod(idx, grid.res)
        for seed in seeds:
            srow, scol = divmod(seed["idx"], grid.res)
            if max(abs(row - srow), abs(col - scol)) < sep:
                return
        seeds.append({"idx": idx, "kind": kind})
        used.add(idx)

    for x, z in grid.starts:                       # map-authored start positions
        add(grid.world_to_idx(x, z), "start")
    for idx in local_maxima(grid, grid.structure, target, sep):
        add(idx, "base")
    for idx in local_maxima(grid, grid.loss, target, sep):
        add(idx, "fight")
    transit = [grid.transit_score(i) for i in range(grid.res * grid.res)]
    for idx in local_maxima(grid, transit, target, sep, threshold=0.01):
        add(idx, "transit")
    choke = [grid.choke[i] * (1.0 if grid.passable[i] else 0.0) for i in range(grid.res * grid.res)]
    for idx in local_maxima(grid, choke, max(2, target // 3), sep, threshold=0.35):
        add(idx, "choke")
    # Water that will matter once the waterline moves: the basin floors are
    # their own territory, dry or not, because the campaign floods and drains
    # them and the player is meant to notice.
    for idx in hydrology_seeds(grid, max(2, target // 3), sep):
        add(idx, "basin")

    # Terrain-only seeds for ground nothing above claimed: the centroid of each
    # sizeable unclaimed passable component.
    if len(seeds) < target:
        seen = set()
        components: List[List[int]] = []
        work = grid.work_cells()
        floor = max(4, len(work) // 60)
        for idx in work:
            if idx in seen or not grid.passable[idx]:
                continue
            stack, comp = [idx], []
            seen.add(idx)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in grid.work_neighbours(cur):
                    if nb not in seen and grid.passable[nb]:
                        seen.add(nb)
                        stack.append(nb)
            if len(comp) >= floor:
                components.append(comp)
        components.sort(key=len, reverse=True)
        for comp in components:
            if len(seeds) >= target:
                break
            far = max(comp, key=lambda i: min(
                (max(abs(divmod(i, grid.res)[0] - divmod(s["idx"], grid.res)[0]),
                     abs(divmod(i, grid.res)[1] - divmod(s["idx"], grid.res)[1]))
                 for s in seeds), default=grid.res))
            add(far, "terrain")

    # Water bodies that carry activity deserve their own zone.
    water_activity = [grid.presence[i] if grid.cells[i][CH["water"]] >= 0.5 else 0.0
                      for i in range(grid.res * grid.res)]
    if sum(water_activity) > 0.03 * grid.total_presence:
        for idx in local_maxima(grid, water_activity, 2, sep):
            add(idx, "water")

    return seeds


def hydrology_seeds(grid: CellGrid, count: int, sep: int) -> List[int]:
    """Deepest points of each measured basin, in quotient space."""
    prof = grid.hydrology
    if not prof:
        return []
    heights = [c[CH["height"]] for c in grid.cells]
    out: List[int] = []
    for basin in prof.get("basins", []):
        cells = (prof.get("basinCells") or {}).get(basin["basinId"]) or []
        cells = [i for i in cells if 0 <= i < len(heights)]
        if not cells:
            continue
        deepest = min(cells, key=lambda i: (heights[i], i))
        out.append(grid.rep[deepest])
        if len(out) >= count:
            break
    return out


def grow_regions(grid: CellGrid, seeds: Sequence[Dict[str, Any]]) -> List[int]:
    """Multi-source cheapest-path assignment: every cell joins the seed it is
    cheapest to reach across similar, walkable ground."""
    n = grid.res * grid.res
    owner = [-1] * n
    best = [float("inf")] * n
    heap: List[Tuple[float, int, int]] = []
    for si, seed in enumerate(seeds):
        idx = seed["idx"]
        best[idx] = 0.0
        owner[idx] = si
        heapq.heappush(heap, (0.0, idx, si))
    while heap:
        cost, idx, si = heapq.heappop(heap)
        if cost > best[idx]:
            continue
        for nb in grid.work_neighbours(idx):
            step = cost + dissimilarity(grid, idx, nb)
            if step < best[nb] - 1e-9:
                best[nb] = step
                owner[nb] = si
                heapq.heappush(heap, (step, nb, si))
    return owner


def region_signature(grid: CellGrid, cells: Sequence[int],
                     domain: bool = False) -> Dict[str, float]:
    """What this patch of ground measurably IS.

    Behaviour fields are DENSITIES relative to the map average (1.0 = ordinary
    ground, 3.0 = three times the map's average concentration), so a big quiet
    zone and a small busy one compare honestly.

    `domain=True` means these cells are quotient cells covering one fundamental
    domain, so the averages they are measured against must be the domain's, not
    the whole map's -- otherwise every zone on a mirrored map reads as half as
    busy as it is."""
    presence = sum(grid.presence[i] for i in cells)
    structure = sum(grid.structure[i] for i in cells)
    loss = sum(grid.loss[i] for i in cells)
    traffic = sum(grid.traffic[i] for i in cells)
    defence = sum(grid.defence[i] for i in cells)
    hazard = sum(grid.hazard[i] for i in cells)

    scope = grid.domain_totals if domain else grid.map_totals
    area_share = len(cells) / float(scope["cells"])

    def density(total: float, map_total: float) -> float:
        if map_total <= 0 or area_share <= 0:
            return 0.0
        return (total / map_total) / area_share

    ally_totals: Dict[str, float] = defaultdict(float)
    for i in cells:
        for ally, value in grid.ally_presence[i].items():
            ally_totals[ally] += value
    top = sorted(ally_totals.values(), reverse=True)
    contest = (top[1] / top[0]) if len(top) >= 2 and top[0] > 0 else 0.0

    water = sum(grid.cells[i][CH["water"]] for i in cells) / len(cells)
    buildable = sum(grid.cells[i][CH["buildable"]] for i in cells) / len(cells)
    slope = sum(grid.cells[i][CH["slope"]] for i in cells) / len(cells)
    metal = sum(grid.cells[i][CH["metal"]] for i in cells) / len(cells)
    rel_height = sum(grid.relative_height(i) for i in cells) / len(cells)
    choke = max((grid.choke[i] for i in cells), default=0.0)
    cell_set = set(cells)
    has_start = any((grid.rep[grid.world_to_idx(x, z)] if domain
                     else grid.world_to_idx(x, z)) in cell_set for x, z in grid.starts)

    structure_density = density(structure, scope["structure"])
    traffic_density = density(traffic, scope["traffic"])

    out = {
        "cellCount": float(len(cells)),
        "presenceShare": presence / scope["presence"],
        "presenceDensity": density(presence, scope["presence"]),
        "structureDensity": structure_density,
        "fightDensity": density(loss, scope["loss"]),
        "trafficDensity": traffic_density,
        # Movement that does not settle: the signature of a lane or a gate.
        "transitDensity": traffic_density / max(0.25, structure_density),
        "hazard": (hazard / presence) if presence > 0 else 0.0,
        "defence": (defence / presence) if presence > 0 else 0.0,
        "contest": contest,
        "water": water,
        "buildable": buildable,
        "slope": slope,
        "metal": metal,
        "relativeHeight": rel_height,
        "choke": choke,
        "hasStart": bool(has_start),
    }
    # Role rules read hydrology, so it belongs in every signature -- including
    # the ones the merge compares, or two neighbours that drown differently
    # would look identical to it.
    out.update(zone_hydrology(grid, cells))
    return out


def merge_regions(grid: CellGrid, owner: List[int], seed_count: int,
                  min_zones: int, max_zones: int) -> List[int]:
    """Fold away regions that are too small or too much like their neighbour."""
    work = grid.work_cells()
    # Zone counts are given in UNFOLDED terms; on the quotient we only cut the
    # fundamental domain, so the targets scale down with the symmetry order.
    order = max(1, (grid.res * grid.res) // max(1, len(work)))
    min_zones = max(2, min_zones // order)
    max_zones = max(min_zones, max_zones // order)
    min_cells = max(4, len(work) // (max_zones * 6))
    absolute_floor = max(2, min_zones - 1)

    def regions() -> Dict[int, List[int]]:
        out: Dict[int, List[int]] = defaultdict(list)
        for idx in work:
            oid = owner[idx]
            if oid >= 0:
                out[oid].append(idx)
        return out

    def adjacency(regs: Dict[int, List[int]]) -> Dict[int, set]:
        adj: Dict[int, set] = defaultdict(set)
        for idx in work:
            oid = owner[idx]
            if oid < 0:
                continue
            for nb in grid.work_neighbours(idx):
                nid = owner[nb]
                if nid >= 0 and nid != oid:
                    adj[oid].add(nid)
        return adj

    while True:
        regs = regions()
        if not regs:
            break
        adj = adjacency(regs)
        sigs = {rid: region_signature(grid, cells, domain=grid.is_symmetric())
               for rid, cells in regs.items()}

        victim = None
        # Too small to be a zone, or ground the war never touched at all -- a
        # dead zone is not worth a name on the quest board, so this merge is
        # allowed to take the map below the requested minimum (an absolute
        # floor still applies). Similarity merges below still respect it.
        if len(regs) > absolute_floor:
            small = [rid for rid, cells in regs.items()
                     if len(cells) < min_cells
                     or (grid.has_activity() and sigs[rid]["presenceShare"] < DEAD_ZONE_SHARE)]
            if small:
                victim = min(small, key=lambda rid: (sigs[rid]["presenceShare"], len(regs[rid])))
        if victim is None and len(regs) > min_zones:
            # Merge the pair that costs the least distinctness. Above the cap
            # this is mandatory; below it, only near-identical neighbours fold,
            # so the map does not get carved into look-alike slivers.
            best_pair, best_cost = None, float("inf")
            for rid, neighbours in adj.items():
                for nid in neighbours:
                    if nid <= rid:
                        continue
                    a, b = sigs[rid], sigs[nid]
                    # Densities are unbounded (a gate can be 40x the map
                    # average), so compare them relatively or the cost explodes
                    # and nothing ever merges.
                    def rel(key: str) -> float:
                        av, bv = a[key], b[key]
                        return abs(av - bv) / (abs(av) + abs(bv) + 1.0)
                    cost = (abs(a["relativeHeight"] - b["relativeHeight"]) * 2.0
                            + abs(a["water"] - b["water"]) * 2.0
                            + rel("structureDensity") * 1.2
                            + rel("transitDensity") * 1.2
                            + rel("fightDensity") * 0.8)
                    if a["hasStart"] and b["hasStart"]:
                        cost += 5.0          # never fuse two start positions
                    if assign_role(a)[0] != assign_role(b)[0]:
                        cost += 1.2          # different roles stay separate
                    else:
                        cost *= 0.6          # same kind of ground: fold freely
                    if cost < best_cost:
                        best_cost, best_pair = cost, (rid, nid)
            over_cap = len(regs) > max_zones
            if best_pair and (over_cap or best_cost < SIMILARITY_MERGE_COST):
                victim, target = best_pair
                for idx, oid in enumerate(owner):
                    if oid == victim:
                        owner[idx] = target
                continue
        if victim is None:
            break
        neighbours = adj.get(victim) or set()
        if not neighbours:
            break
        sig_v = sigs[victim]
        target = min(neighbours, key=lambda nid: (
            abs(sigs[nid]["relativeHeight"] - sig_v["relativeHeight"])
            + abs(sigs[nid]["water"] - sig_v["water"])))
        for idx, oid in enumerate(owner):
            if oid == victim:
                owner[idx] = target
    return owner


COMPASS = [
    ("Northwest", 0.33, 0.33), ("North", 0.5, 0.2), ("Northeast", 0.67, 0.33),
    ("West", 0.2, 0.5), ("Central", 0.5, 0.5), ("East", 0.8, 0.5),
    ("Southwest", 0.33, 0.67), ("South", 0.5, 0.8), ("Southeast", 0.67, 0.67),
]


def compass_name(nx: float, nz: float) -> str:
    """Where this sits, by bearing from the map centre.

    Bearing beats a nearest-of-nine-boxes match on symmetric maps: a four-fold
    family lands in four different sectors instead of two zones both being
    called "West" because they share a row."""
    dx, dz = nx - 0.5, nz - 0.5
    if math.hypot(dx, dz) < 0.15:
        return "Central"
    # Screen space: +z is south, so north is -z.
    angle = math.degrees(math.atan2(-dz, dx)) % 360.0
    sector = int((angle + 22.5) // 45) % 8
    return ["East", "Northeast", "North", "Northwest",
            "West", "Southwest", "South", "Southeast"][sector]


def _compass_name_boxes(nx: float, nz: float) -> str:
    return min(COMPASS, key=lambda c: (nx - c[1]) ** 2 + (nz - c[2]) ** 2)[0]


def assign_role(sig: Dict[str, float]) -> Tuple[str, str]:
    for role, suffix, predicate in ROLE_RULES:
        if predicate(sig):
            return role, suffix
    return "flank_pocket", "Pocket"


def rle(indices: Sequence[int]) -> List[List[int]]:
    out: List[List[int]] = []
    for idx in sorted(indices):
        if out and idx == out[-1][0] + out[-1][1]:
            out[-1][1] += 1
        else:
            out.append([idx, 1])
    return out


def routine_waterline(grid: CellGrid) -> Optional[float]:
    """Elevation the campaign's water cycle routinely reaches (level 0.5).

    Above it a camp is safe most of the time; below it, the campaign will drown
    the site sooner or later."""
    prof = grid.hydrology
    if not prof:
        return None
    elevations = prof.get("elevations") or []
    levels = prof.get("levels") or []
    if not elevations:
        return None
    for lvl, elev in zip(levels, elevations):
        if float(lvl) >= 0.5:
            return float(elev)
    return float(elevations[-1])


def unfold_region(grid: CellGrid, cells: Sequence[int]) -> List[List[int]]:
    """One quotient region -> one zone per symmetry image.

    A region sitting mostly ON the axis is its own mirror, so it stays a single
    self-symmetric zone rather than being split into two half-width slivers."""
    ops = getattr(grid, "sym_ops", None)
    if not ops or len(ops) <= 1:
        return [sorted(cells)]
    on_axis = sum(1 for i in cells if grid.orbit_size[i] == 1)
    if on_axis >= 0.5 * len(cells):
        return [sorted({j for i in cells for j in grid.images_of(i)})]

    pieces: List[List[int]] = []
    claimed: set = set()
    for k in range(len(ops)):
        piece: List[int] = []
        for i in cells:
            images = grid.images_of(i)
            j = images[k] if k < len(images) else images[-1]
            if j in claimed:
                continue          # axis cells belong to the first image only
            claimed.add(j)
            piece.append(j)
        if piece:
            pieces.append(sorted(piece))
    return pieces


def zone_hydrology(grid: CellGrid, cells: Sequence[int]) -> Dict[str, Any]:
    """When this ground drowns, and what drowns with it."""
    prof = grid.hydrology
    blank = {"floodsAt": NEVER_FLOODS, "restingSubmerged": 0.0,
             "submergedAt": [], "drownedMetal": 0.0}
    if not prof:
        return blank
    elevations = prof.get("elevations") or []
    levels = prof.get("levels") or []
    if not elevations:
        return blank
    heights = [grid.cells[i][CH["height"]] for i in cells]
    fractions = [round(sum(1 for h in heights if h <= lvl) / len(heights), 3)
                 for lvl in elevations]
    floods_at = NEVER_FLOODS
    for i, frac in enumerate(fractions):
        if frac >= 0.5:
            floods_at = float(levels[i])
            break
    # Metal that goes under with it -- the reason to care that it drained.
    cell_set = set(cells)
    spots = 0
    drowned = 0
    for spot in grid.metal_spots:
        idx = grid.world_to_idx(float(spot["x"]), float(spot["z"]))
        if idx not in cell_set:
            continue
        spots += 1
        if floods_at < NEVER_FLOODS and grid.cells[idx][CH["height"]] <= elevations[
                min(len(elevations) - 1, levels.index(floods_at))]:
            drowned += 1
    return {
        "floodsAt": floods_at,
        "restingSubmerged": fractions[0] if fractions else 0.0,
        "submergedAt": fractions,
        "metalSpots": spots,
        "drownedMetal": round(drowned / spots, 3) if spots else 0.0,
    }


def pick_anchor(grid: CellGrid, cells: Sequence[int],
                dry_above: Optional[float] = None) -> Optional[int]:
    """Best camp site: buildable, dry, flat, close to where the action was.

    `dry_above` is an elevation the site must clear: a camp planted on ground
    the campaign's own water cycle will drown is not a camp site."""
    weight = sum(grid.presence[i] for i in cells)
    if weight > 0:
        cx = sum(grid.cell_norm(i)[0] * grid.presence[i] for i in cells) / weight
        cz = sum(grid.cell_norm(i)[1] * grid.presence[i] for i in cells) / weight
    else:
        cx = sum(grid.cell_norm(i)[0] for i in cells) / len(cells)
        cz = sum(grid.cell_norm(i)[1] for i in cells) / len(cells)
    best, best_score = None, -1.0
    for i in cells:
        cell = grid.cells[i]
        if cell[CH["water"]] >= 0.25 or cell[CH["slope"]] >= 0.30 or cell[CH["buildable"]] <= 0.4:
            continue
        if dry_above is not None and cell[CH["height"]] <= dry_above:
            continue
        nx, nz = grid.cell_norm(i)
        score = cell[CH["buildable"]] * (1.0 - cell[CH["slope"]])
        score /= 1.0 + 3.0 * math.hypot(nx - cx, nz - cz)
        if score > best_score:
            best_score, best = score, i
    return best


def build_zone_map(grid: CellGrid, min_zones: int, max_zones: int) -> Dict[str, Any]:
    seeds = choose_seeds(grid, max_zones)
    if not seeds:
        raise ValueError(f"{grid.map_id}: no seeds could be placed")
    owner = grow_regions(grid, seeds)
    owner = merge_regions(grid, owner, len(seeds), min_zones, max_zones)

    regions: Dict[int, List[int]] = defaultdict(list)
    for idx in grid.work_cells():
        oid = owner[idx]
        if oid >= 0:
            regions[oid].append(idx)

    # Unfold the quotient: each region cut in the fundamental domain becomes one
    # zone per symmetry image, so a mirrored pair is exactly that -- a pair.
    unfolded: List[Tuple[int, List[int]]] = []
    for rid, cells in regions.items():
        for piece in unfold_region(grid, cells):
            unfolded.append((rid, piece))

    prefix = "".join(part[0] for part in grid.map_id.split("_") if part).upper()[:4] or "ZN"
    zones: List[Dict[str, Any]] = []
    used_ids: set = set()

    ordered = sorted(unfolded, key=lambda kv: -sum(grid.presence[i] for i in kv[1]))
    signatures = {id(cells): region_signature(grid, cells) for _, cells in ordered}

    # Mirrored zones are the same ground twice, so they get the same role. Left
    # to itself the rule chain reads them separately and a four-fold family can
    # come out as three spillways and a shoreline, because no real map is
    # symmetric to the last elmo.
    family_role: Dict[int, Tuple[str, str]] = {}
    by_family: Dict[int, List[List[int]]] = defaultdict(list)
    for fam, cells in ordered:
        by_family[fam].append(cells)
    for fam, members in by_family.items():
        votes: Dict[Tuple[str, str], float] = defaultdict(float)
        for cells in members:
            votes[assign_role(signatures[id(cells)])] += len(cells)
        family_role[fam] = max(votes.items(), key=lambda kv: (kv[1], kv[0]))[0]

    for family, cells in ordered:
        sig = signatures[id(cells)]
        role, suffix = family_role[family]
        weight = sum(grid.presence[i] for i in cells) or float(len(cells))
        cx = sum(grid.cell_norm(i)[0] * (grid.presence[i] or 1.0) for i in cells) / weight
        cz = sum(grid.cell_norm(i)[1] * (grid.presence[i] or 1.0) for i in cells) / weight
        where = compass_name(cx, cz)
        # A four-fold map can put four same-role zones in the same compass
        # sector. "Inner"/"Outer" separates them by how far out they sit, which
        # a player can actually act on; a bare numeric suffix cannot.
        code = COMPASS_CODE.get(where, where[:2].upper())
        # A four-fold map puts four same-role zones in one compass sector.
        # Qualify by how far out and which side they sit -- both things a player
        # can act on -- before resorting to a meaningless number.
        radial = "Inner" if math.hypot(cx - 0.5, cz - 0.5) < 0.28 else "Outer"
        meridional = "Upper" if cz < 0.5 else "Lower"
        zone_id, qualifier = None, ""
        for candidate in ("", radial, meridional, f"{radial} {meridional}"):
            parts = [prefix, code] + [w.upper() for w in candidate.split()] + [suffix.upper()]
            trial = "_".join(parts)
            if trial not in used_ids:
                zone_id, qualifier = trial, candidate
                break
        if zone_id is None:
            base_id = f"{prefix}_{code}_{radial.upper()}_{meridional.upper()}_{suffix.upper()}"
            qualifier = f"{radial} {meridional}"
            zone_id, n = base_id, 2
            while zone_id in used_ids:
                zone_id = f"{base_id}{n}"
                n += 1
        used_ids.add(zone_id)
        label = " ".join(p for p in (where, qualifier, suffix) if p)

        # A camp must stand above the routine waterline. If nothing in the zone
        # does, fall back to a dry-at-rest site and let campEligible carry the
        # truth rather than inventing a site that drowns.
        routine = routine_waterline(grid)
        anchor_idx = pick_anchor(grid, cells, dry_above=routine)
        flood_safe = anchor_idx is not None
        if anchor_idx is None:
            anchor_idx = pick_anchor(grid, cells)
        anchor = None
        if anchor_idx is not None:
            ax, az = grid.cell_norm(anchor_idx)
            anchor = {"x": round(ax, 4), "z": round(az, 4)}

        rows = [divmod(i, grid.res)[0] for i in cells]
        cols = [divmod(i, grid.res)[1] for i in cells]
        bounds = {
            "xMin": round(min(cols) / grid.res, 4),
            "xMax": round((max(cols) + 1) / grid.res, 4),
            "zMin": round(min(rows) / grid.res, 4),
            "zMax": round((max(rows) + 1) / grid.res, 4),
        }

        tags = []
        if sig["water"] >= 0.35:
            tags.append("water")
        if sig["relativeHeight"] >= 0.55:
            tags.append("high")
        elif sig["relativeHeight"] <= 0.3:
            tags.append("low")
        if sig["metal"] >= 0.5:
            tags.append("metal")
        if sig["choke"] >= 0.55:
            tags.append("choke")
        if sig["hazard"] >= 0.4:
            tags.append("raptors")
        if sig["contest"] >= 0.35:
            tags.append("contested")
        if sig["hasStart"]:
            tags.append("start")
        if sig["floodsAt"] <= 0.35:
            tags.append("flood")
        elif sig["floodsAt"] <= 0.7:
            tags.append("shore")
        if sig["restingSubmerged"] >= 0.35:
            tags.append("water")
        tags.append(where.lower())

        zones.append({
            "zoneId": zone_id,
            "label": label,
            "role": role,
            "shape": "cells",
            "cellGrid": {"cols": grid.res, "rows": grid.res},
            "cells": rle(cells),
            "bounds": bounds,
            "anchor": anchor,
            # No dry buildable ground means no camp can stand here: the
            # compiler must not try to plant one (open water, sheer cliff),
            # and neither does ground the water cycle routinely takes back.
            "campEligible": anchor is not None and flood_safe,
            "deployEligible": anchor is not None and flood_safe and sig["hazard"] < 0.4,
            "extractEligible": anchor is not None and flood_safe,
            "symmetryFamily": f"F{family}",
            "hydrology": {
                "floodsAt": sig["floodsAt"],
                "restingSubmerged": sig["restingSubmerged"],
                "submergedAt": sig.get("submergedAt", []),
                "metalSpots": sig.get("metalSpots", 0),
                "drownedMetal": sig.get("drownedMetal", 0.0),
                "anchorAboveWaterline": flood_safe,
            },
            "tags": tags,
            "evidence": {k: round(v, 4) if isinstance(v, float) else v
                         for k, v in sig.items() if k != "submergedAt"},
        })

    return {
        "schemaVersion": ZONE_SCHEMA,
        "mapId": grid.map_id,
        "mapName": grid.map_name,
        "coordinateSystem": "normalized-xz",
        "authoringStatus": "derived",
        "grid": {"res": grid.res},
        "targetZoneRange": [min_zones, max_zones],
        "symmetry": {
            "group": (grid.symmetry or {}).get("group", ["identity"]),
            "order": (grid.symmetry or {}).get("order", 1),
            "scores": (grid.symmetry or {}).get("scores", {}),
            "accepted": (grid.symmetry or {}).get("accepted", []),
        },
        "hydrologyRef": (f"data/hydrology/{grid.map_id}.hydrology.json"
                         if grid.hydrology else None),
        "waterline": {
            "levels": (grid.hydrology or {}).get("levels", []),
            "elevations": (grid.hydrology or {}).get("elevations", []),
            "routine": routine_waterline(grid),
            "basins": [b["basinId"] for b in (grid.hydrology or {}).get("basins", [])],
        },
        "derivedFrom": {
            "terrain": f"data/terrain/{grid.map_id}.terrain.json",
            "configs": grid.configs,
            "measuredActivity": round(grid.total_presence, 1),
            "behaviourSource": grid.behaviour_source,
        },
        "notes": ("Cut by tools/zone_cartographer_v1.py from measured terrain and "
                  "AI-vs-AI behaviour. Cells are run-length encoded [startIndex, length] "
                  "over a row-major cellGrid; bounds are derived for legacy consumers. "
                  "Anchors are measured buildable/dry/flat camp sites."),
        "zones": zones,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Derive zone maps from measured rasters")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--min-zones", type=int, default=12)
    ap.add_argument("--max-zones", type=int, default=18)
    ap.add_argument("--zones", type=int, default=0,
                    help="override the per-map zone target")
    ap.add_argument("--symmetry-threshold", type=float, default=0.90)
    ap.add_argument("--no-symmetry", action="store_true")
    ap.add_argument("--no-hydrology", action="store_true")
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    only = [m.strip() for m in args.maps.split(",") if m.strip()]
    terrain_dir = ws / "data" / "terrain"
    # Staging, not the live directory: tools/migrate_zone_ids_v1.py promotes
    # these once the old->new mapping has been inspected.
    out_dir = Path(args.out_dir) if args.out_dir else ws / "data" / "zone_maps" / "derived"
    if not terrain_dir.exists():
        print("No data/terrain yet -- run the cartography survey first "
              "(scripts/run_zone_cartography_survey.ps1 -Mode terrain).", file=sys.stderr)
        return 2

    written = 0
    for terrain_path in sorted(terrain_dir.glob("*.terrain.json")):
        terrain = load_json(terrain_path)
        map_id = terrain.get("mapId") or terrain_path.name.split(".")[0]
        if only and map_id not in only:
            continue
        behaviour_dir = ws / "data" / "behavior" / map_id
        rasters = [load_json(p) for p in sorted(behaviour_dir.glob("*.raster.json"))] \
            if behaviour_dir.exists() else []
        rasters = [r for r in rasters if r]

        symmetry = None
        if not args.no_symmetry:
            symmetry = map_symmetry_v1.detect(terrain, args.symmetry_threshold)
        hydrology = None
        if not args.no_hydrology:
            hydrology = load_json(ws / "data" / "hydrology" / f"{map_id}.hydrology.json")

        target = args.zones or MAP_ZONE_TARGETS.get(map_id, DEFAULT_ZONE_TARGET)
        target = max(args.min_zones, min(args.max_zones, target))

        grid = CellGrid(terrain, rasters, symmetry=symmetry, hydrology=hydrology)
        zone_map = build_zone_map(grid, target, target)

        summary = ", ".join(f"{z['zoneId']}:{z['role']}" for z in zone_map["zones"])
        order = (symmetry or {}).get("order", 1)
        group = ",".join((symmetry or {}).get("accepted", [])) or "none"
        print(f"{map_id}: {len(zone_map['zones'])} zones (target {target}) "
              f"from {len(rasters)} rasters [{grid.behaviour_source}]; "
              f"symmetry order {order} ({group})"
              + (f"; {len(hydrology.get('basins', []))} basins" if hydrology else ""))
        print(f"  {summary}")
        flooding = [z for z in zone_map["zones"] if z["hydrology"]["floodsAt"] <= 0.7]
        if flooding:
            print(f"  {len(flooding)} zones drown before the waterline is half up; "
                  f"{sum(1 for z in zone_map['zones'] if not z['campEligible'])} "
                  "cannot hold a camp")
        if not grid.has_activity():
            print("  warning: no behaviour rasters -- zones are terrain-only")

        if not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{map_id}.authored.zone_map.json"
            out_path.write_text(json.dumps(zone_map, indent=1), encoding="utf-8")
            written += 1
    if not args.dry_run:
        print(f"wrote {written} zone maps -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
