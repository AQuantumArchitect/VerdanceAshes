"""
Derive the same-map zone adjacency graph.

Two modes, picked per map:

  cells  -- schema 2.0 zone maps own explicit grid cells, so two zones are
            neighbours when their cells touch across ground something can
            actually cross. If a terrain raster is available, contact over
            impassable cells (cliff faces, deep water) does not count as a land
            edge; a water crossing is recorded only when both zones carry water.
  rects  -- legacy zone maps: fall back to rectangle proximity/overlap.

Emits data/zone_maps/authored/zone_adjacency.json
"""
import json
import math
import os
from collections import defaultdict

AUTHORED_DIR = os.path.join("data", "zone_maps", "authored")
TERRAIN_DIR = os.path.join("data", "terrain")
OUTPUT_PATH = os.path.join(AUTHORED_DIR, "zone_adjacency.json")

CH = {name: i for i, name in enumerate(
    ["height", "slope", "water", "buildable", "metal",
     "tankSpeed", "shipSpeed", "featureCount", "featureMetal"])}

# A land edge needs at least this many touching cell pairs, so a diagonal
# nick between two zones does not become a marching route.
MIN_CONTACT_CELLS = 2


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def bounds_touch_or_overlap(b1, b2, margin=0.08):
    x_overlap = max(0, min(b1["xMax"], b2["xMax"]) - max(b1["xMin"], b2["xMin"]))
    z_overlap = max(0, min(b1["zMax"], b2["zMax"]) - max(b1["zMin"], b2["zMin"]))
    dx = max(0, max(b1["xMin"], b2["xMin"]) - min(b1["xMax"], b2["xMax"]))
    dz = max(0, max(b1["zMin"], b2["zMin"]) - min(b1["zMax"], b2["zMax"]))
    return math.hypot(dx, dz) <= margin or (x_overlap > 0 and z_overlap > 0)


def zone_cells(zone):
    """Explicit cell mask, run-length encoded as [startIndex, length]."""
    runs = zone.get("cells")
    if not runs:
        return []
    out = []
    for run in runs:
        if isinstance(run, (list, tuple)) and len(run) == 2:
            start, length = int(run[0]), int(run[1])
            out.extend(range(start, start + length))
        else:
            out.append(int(run))
    return out


def grid_res(zone_map):
    grid = zone_map.get("grid") or {}
    if grid.get("res"):
        return int(grid["res"])
    for zone in zone_map.get("zones") or []:
        cell_grid = zone.get("cellGrid") or {}
        if cell_grid.get("cols"):
            return int(cell_grid["cols"])
    return 0


def derive_from_cells(zone_map, terrain):
    res = grid_res(zone_map)
    zones = zone_map.get("zones") or []
    owner = {}
    for zone in zones:
        for idx in zone_cells(zone):
            owner.setdefault(idx, zone["zoneId"])
    if not owner or res <= 0:
        return None

    cells = (terrain or {}).get("cells") or []

    def passable(idx):
        if not cells or idx >= len(cells):
            return True
        cell = cells[idx]
        return cell[CH["water"]] < 0.6 and cell[CH["slope"]] < 0.45 and cell[CH["tankSpeed"]] > 0.05

    def wet(idx):
        if not cells or idx >= len(cells):
            return False
        return cells[idx][CH["water"]] >= 0.5

    land_contacts = defaultdict(int)
    water_contacts = defaultdict(int)
    for idx, zid in owner.items():
        row, col = divmod(idx, res)
        for nb in ((idx - res if row > 0 else None),
                   (idx + res if row < res - 1 else None),
                   (idx - 1 if col > 0 else None),
                   (idx + 1 if col < res - 1 else None)):
            if nb is None:
                continue
            other = owner.get(nb)
            if not other or other == zid:
                continue
            key = tuple(sorted((zid, other)))
            if passable(idx) and passable(nb):
                land_contacts[key] += 1
            elif wet(idx) and wet(nb):
                water_contacts[key] += 1

    adjacency = {zone["zoneId"]: set() for zone in zones}
    for key, count in land_contacts.items():
        if count >= MIN_CONTACT_CELLS:
            adjacency[key[0]].add(key[1])
            adjacency[key[1]].add(key[0])
    for key, count in water_contacts.items():
        if count >= MIN_CONTACT_CELLS and key[1] not in adjacency[key[0]]:
            adjacency[key[0]].add(key[1])
            adjacency[key[1]].add(key[0])

    connect_isolated(zones, adjacency)
    return {k: sorted(v) for k, v in adjacency.items()}


def zone_point(zone):
    anchor = zone.get("anchor") or {}
    if anchor.get("x") is not None:
        return (float(anchor["x"]), float(anchor["z"]))
    b = zone.get("bounds") or {}
    return ((float(b.get("xMin", 0)) + float(b.get("xMax", 1))) / 2.0,
            (float(b.get("zMin", 0)) + float(b.get("zMax", 1))) / 2.0)


def connect_isolated(zones, adjacency):
    """A zone with no neighbours is unreachable on the quest board, so tie it
    to the nearest one rather than stranding it."""
    for zone in zones:
        zid = zone["zoneId"]
        if adjacency[zid]:
            continue
        point = zone_point(zone)
        best, best_dist = None, float("inf")
        for other in zones:
            if other["zoneId"] == zid:
                continue
            d = math.hypot(*(a - b for a, b in zip(point, zone_point(other))))
            if d < best_dist:
                best_dist, best = d, other["zoneId"]
        if best:
            adjacency[zid].add(best)
            adjacency[best].add(zid)


def derive_from_rects(zone_map):
    zones = zone_map.get("zones") or []
    adjacency = {z["zoneId"]: set() for z in zones}
    for i, z1 in enumerate(zones):
        for z2 in zones[i + 1:]:
            if bounds_touch_or_overlap(z1["bounds"], z2["bounds"], margin=0.10):
                adjacency[z1["zoneId"]].add(z2["zoneId"])
                adjacency[z2["zoneId"]].add(z1["zoneId"])
    connect_isolated(zones, adjacency)
    return {k: sorted(v) for k, v in adjacency.items()}


def derive_adjacency_for_map(zone_map, terrain=None):
    if zone_map.get("zones") and any(z.get("cells") for z in zone_map["zones"]):
        derived = derive_from_cells(zone_map, terrain)
        if derived:
            return derived
    return derive_from_rects(zone_map)


def generate_adjacency_file():
    full_graph = {}
    total_zones = 0
    modes = {}
    for name in sorted(os.listdir(AUTHORED_DIR)):
        if not name.endswith(".authored.zone_map.json"):
            continue
        zone_map = load_json(os.path.join(AUTHORED_DIR, name))
        map_key = zone_map.get("mapId") or name.split(".")[0]
        terrain_path = os.path.join(TERRAIN_DIR, f"{map_key}.terrain.json")
        terrain = load_json(terrain_path) if os.path.exists(terrain_path) else None
        adj = derive_adjacency_for_map(zone_map, terrain)
        full_graph[map_key] = adj
        total_zones += len(adj)
        uses_cells = any(z.get("cells") for z in zone_map.get("zones") or [])
        modes[map_key] = ("cells" if uses_cells else "rects") + ("+terrain" if terrain else "")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(full_graph, fh, indent=2)

    print(f"Wrote zone adjacency for {len(full_graph)} maps ({total_zones} zones) to {OUTPUT_PATH}")
    for map_key, mode in sorted(modes.items()):
        print(f"  {map_key}: {mode}, {len(full_graph[map_key])} zones, "
              f"{sum(len(v) for v in full_graph[map_key].values()) // 2} edges")


if __name__ == "__main__":
    generate_adjacency_file()
