#!/usr/bin/env python3
"""Carry the campaign across a zone re-cut.

The cartographer writes new zone maps to data/zone_maps/derived/. This tool
compares them with the live ones in data/zone_maps/authored/, works out which
new zone inherits each old one (by overlap, weighted by measured activity),
and -- with --apply -- promotes the new maps and repoints everything that
names a zone:

  * data/zone_maps/authored/zone_id_migration.json   (old -> new, kept for the
    world graph's authored cross-map links and for reading old history beads)
  * state/campaign_state.json zoneMemory              (control carried over)
  * outbox/next_sortie_order.json + hub_deploy_plan.latest.json (standing orders)
  * data/base_templates/*/ living shells + bake recipes (pockets re-tagged by
    where their units actually stand)

Then it rebuilds adjacency and the world zone graph.

Usage:
  python tools/migrate_zone_ids_v1.py              # dry run, prints the plan
  python tools/migrate_zone_ids_v1.py --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def zone_cells(zone: Dict[str, Any], res: int) -> List[int]:
    runs = zone.get("cells")
    if runs:
        out: List[int] = []
        for run in runs:
            if isinstance(run, (list, tuple)) and len(run) == 2:
                out.extend(range(int(run[0]), int(run[0]) + int(run[1])))
            else:
                out.append(int(run))
        return out
    bounds = zone.get("bounds") or {}
    if not bounds:
        return []
    out = []
    for row in range(res):
        z = (row + 0.5) / res
        if not (float(bounds.get("zMin", 0)) <= z <= float(bounds.get("zMax", 1))):
            continue
        for col in range(res):
            x = (col + 0.5) / res
            if float(bounds.get("xMin", 0)) <= x <= float(bounds.get("xMax", 1)):
                out.append(row * res + col)
    return out


def grid_res(zone_map: Dict[str, Any], default: int = 48) -> int:
    grid = zone_map.get("grid") or {}
    if grid.get("res"):
        return int(grid["res"])
    for zone in zone_map.get("zones") or []:
        cell_grid = zone.get("cellGrid") or {}
        if cell_grid.get("cols"):
            return int(cell_grid["cols"])
    return default


def cell_weights(ws: Path, map_id: str, res: int) -> Dict[int, float]:
    """Measured activity per cell, so overlap is judged by where the war was,
    not by raw area."""
    behaviour_dir = ws / "data" / "behavior" / map_id
    weights: Dict[int, float] = defaultdict(float)
    if not behaviour_dir.exists():
        return weights
    for path in sorted(behaviour_dir.glob("*.raster.json")):
        raster = load_json(path)
        if not raster or int((raster.get("grid") or {}).get("res") or 0) != res:
            continue
        milestones = raster.get("milestones") or []
        if not milestones:
            continue
        for channels in (milestones[-1].get("allies") or {}).values():
            for idx_s, value in (channels.get("presence") or {}).items():
                weights[int(idx_s)] += float(value)
    return weights


def map_zone_ids(ws: Path, old_map: Dict[str, Any], new_map: Dict[str, Any]) -> Dict[str, Any]:
    map_id = new_map.get("mapId") or old_map.get("mapId")
    res = grid_res(new_map)
    weights = cell_weights(ws, str(map_id), res)

    new_owner: Dict[int, str] = {}
    for zone in new_map.get("zones") or []:
        for idx in zone_cells(zone, res):
            new_owner.setdefault(idx, str(zone.get("zoneId")))

    mapping: Dict[str, str] = {}
    detail: List[Dict[str, Any]] = []
    for zone in old_map.get("zones") or []:
        old_id = str(zone.get("zoneId"))
        overlap: Dict[str, float] = defaultdict(float)
        for idx in zone_cells(zone, res):
            new_id = new_owner.get(idx)
            if new_id:
                overlap[new_id] += weights.get(idx, 0.0) + 1e-3   # area breaks ties
        if not overlap:
            detail.append({"from": old_id, "to": None, "share": 0.0})
            continue
        total = sum(overlap.values()) or 1.0
        best_id, best_val = max(overlap.items(), key=lambda kv: kv[1])
        mapping[old_id] = best_id
        detail.append({"from": old_id, "to": best_id, "share": round(best_val / total, 3),
                       "alternatives": sorted(((k, round(v / total, 3)) for k, v in overlap.items()
                                               if k != best_id), key=lambda kv: -kv[1])[:2]})
    return {"mapId": map_id, "mapping": mapping, "detail": detail,
            "newZones": [str(z.get("zoneId")) for z in new_map.get("zones") or []]}


def zone_for_point(zone_map: Dict[str, Any], nx: float, nz: float) -> Optional[str]:
    res = grid_res(zone_map)
    col = min(res - 1, max(0, int(nx * res)))
    row = min(res - 1, max(0, int(nz * res)))
    idx = row * res + col
    for zone in zone_map.get("zones") or []:
        if idx in set(zone_cells(zone, res)):
            return str(zone.get("zoneId"))
    return None


def retag_base_templates(ws: Path, new_maps: Dict[str, Dict[str, Any]],
                         mapping: Dict[str, str], apply: bool) -> List[str]:
    """Living-shell pockets store real world positions, so they can be re-tagged
    from the ground itself rather than through the id mapping."""
    notes: List[str] = []
    base_dir = ws / "data" / "base_templates"
    if not base_dir.exists():
        return notes
    sizes = {}
    for map_id in new_maps:
        terrain = load_json(ws / "data" / "terrain" / f"{map_id}.terrain.json")
        if terrain:
            sizes[map_id] = (float(terrain["size"]["x"]), float(terrain["size"]["z"]))

    for path in sorted(base_dir.glob("*/*.json")):
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        map_id = str(data.get("mapId") or path.parent.name)
        new_map = new_maps.get(map_id)
        if not new_map:
            continue
        changed = False
        for pocket in data.get("pockets") or []:
            old_id = pocket.get("zoneId")
            new_id = None
            px, pz = pocket.get("x"), pocket.get("z")
            if px is not None and pz is not None and map_id in sizes:
                sx, sz = sizes[map_id]
                new_id = zone_for_point(new_map, float(px) / sx, float(pz) / sz)
            if not new_id and old_id:
                new_id = mapping.get(str(old_id))
            if new_id and new_id != old_id:
                pocket["zoneId"] = new_id
                changed = True
        for key in ("zoneId", "targetZoneId", "deployZoneId"):
            if data.get(key) and mapping.get(str(data[key])):
                data[key] = mapping[str(data[key])]
                changed = True
        if changed:
            notes.append(f"retag {path.relative_to(ws)}")
            if apply:
                save_json(path, data)
    return notes


def deep_remap(node: Any, mapping: Dict[str, str]) -> Tuple[Any, int]:
    """Replace every old zone id anywhere in the document.

    A key list cannot be trusted here: the hub deploy plan nests its zones under
    `marks.deployZoneId` / `marks.extractZoneId`, and a future writer will pick
    some other name again. Zone ids are distinctive enough to match on value."""
    if isinstance(node, str):
        replacement = mapping.get(node)
        return (replacement, 1) if replacement and replacement != node else (node, 0)
    if isinstance(node, list):
        count = 0
        out_list = []
        for item in node:
            value, hits = deep_remap(item, mapping)
            out_list.append(value)
            count += hits
        return out_list, count
    if isinstance(node, dict):
        count = 0
        out_dict = {}
        for key, item in node.items():
            value, hits = deep_remap(item, mapping)
            out_dict[key] = value
            count += hits
        return out_dict, count
    return node, 0


def remap_orders(ws: Path, mapping: Dict[str, str], apply: bool,
                 new_maps: Optional[Dict[str, Dict[str, Any]]] = None) -> List[str]:
    notes: List[str] = []
    targets = [
        ws / "outbox" / "next_sortie_order.json",
        ws / "outbox" / "next_sortie_order.last.json",
        ws / "outbox" / "hub_deploy_plan.latest.json",
        # An already-materialized intent survives a migration still pointing at
        # zones that no longer exist, and the compiler reads it verbatim -- the
        # next mission would be built against dead ids.
        ws / "outbox" / "next_mission_intent.json",
    ]
    for path in targets:
        data = load_json(path)
        if not isinstance(data, dict):
            continue
        data, hits = deep_remap(data, mapping)
        if not hits:
            continue
        notes.extend(separate_collapsed_order(data, new_maps or {}))
        notes.append(f"repoint {path.relative_to(ws)} ({hits} ids)")
        if apply:
            save_json(path, data)
    return notes


def cell_neighbours(zone_map: Optional[Dict[str, Any]], zone_id: str) -> List[str]:
    """Zones whose cells touch this one, straight off the run-length masks."""
    if not zone_map:
        return []
    grid = zone_map.get("grid") or {}
    res = int(grid.get("res") or 0)
    if res <= 0:
        return []
    owner: Dict[int, str] = {}
    for zone in zone_map.get("zones") or []:
        zid = str(zone.get("zoneId"))
        for start, length in zone.get("cells") or []:
            for idx in range(int(start), int(start) + int(length)):
                owner[idx] = zid
    out: List[str] = []
    for idx, zid in owner.items():
        if zid != zone_id:
            continue
        row, col = divmod(idx, res)
        for nb, ok in ((idx - res, row > 0), (idx + res, row < res - 1),
                       (idx - 1, col > 0), (idx + 1, col < res - 1)):
            other = owner.get(nb) if ok else None
            if other and other != zone_id and other not in out:
                out.append(other)
    return sorted(out)


def separate_collapsed_order(data: Dict[str, Any],
                             new_maps: Dict[str, Dict[str, Any]]) -> List[str]:
    """A remap can fold deploy, target and extract into one zone.

    Three old rectangles overlapping one new zone is a perfectly good mapping,
    but it leaves an order that says "land on the objective and extract from the
    objective" -- no mission at all. Push the deploy and extraction points onto
    distinct adjacent zones instead."""
    notes: List[str] = []
    marks = data.get("marks") if isinstance(data.get("marks"), dict) else {}
    target = data.get("targetZoneId")
    if not isinstance(target, str):
        capture = marks.get("captureZoneIds")
        target = capture[0] if isinstance(capture, list) and capture else None
    if not isinstance(target, str):
        return notes
    # Neighbours come from the NEW cell masks directly: the adjacency file is
    # not rebuilt until the end of the migration, so reading it here would ask
    # the old zone graph about zones that do not exist in it yet.
    neighbours = cell_neighbours(new_maps.get(str(data.get("mapId") or "")), target)
    taken = {target}
    holders = [(data, "deploymentZoneId"), (data, "extractionZoneId"),
               (marks, "deployZoneId"), (marks, "extractZoneId")]
    for holder, key in holders:
        value = holder.get(key)
        if not isinstance(value, str):
            continue
        if value not in taken:
            taken.add(value)
            continue
        replacement = next((z for z in neighbours if z not in taken), None)
        if replacement is None:
            notes.append(f"  WARNING {key} collapsed onto {target} and no free neighbour exists")
            continue
        holder[key] = replacement
        taken.add(replacement)
        notes.append(f"  separate {key}: {target} -> {replacement} (was the objective's own zone)")
    return notes


def rebuild_zone_memory(ws: Path, new_maps: Dict[str, Dict[str, Any]],
                        mapping: Dict[str, str], apply: bool) -> List[str]:
    """Rebuild zoneMemory around the new zones, carrying each new zone's control
    from whichever old zone it inherits."""
    state_path = ws / "state" / "campaign_state.json"
    state = load_json(state_path)
    if not isinstance(state, dict):
        return ["no campaign state to migrate"]
    zone_memory = state.get("zoneMemory") or {}
    inverse: Dict[str, List[str]] = defaultdict(list)
    for old_id, new_id in mapping.items():
        inverse[new_id].append(old_id)

    notes: List[str] = []
    for map_id, zone_map in new_maps.items():
        old_entries = zone_memory.get(map_id) or {}
        rebuilt: Dict[str, Any] = {}
        for zone in zone_map.get("zones") or []:
            new_id = str(zone.get("zoneId"))
            source = None
            for old_id in inverse.get(new_id, []):
                if old_id in old_entries:
                    source = old_entries[old_id]
                    break
            entry = dict(source) if source else {}
            entry["mapId"] = map_id
            entry["zoneId"] = new_id
            entry["label"] = zone.get("label") or new_id
            if not entry.get("abstract"):
                entry["abstract"] = {
                    "baseStrength": 0.0, "militaryPressure": 0.0, "fortification": 0.0,
                    "economyMomentum": 0.0, "hazardPressure": 0.0, "objectiveDamage": 0.0,
                    "control": entry.get("controllingFaction") or "neutral", "instability": 0.5,
                }
            entry.setdefault("lastMeasuredRaw", {})
            entry.setdefault("objectiveState", {})
            entry.setdefault("baseSnapshot", {})
            entry.setdefault("hazardPressure", 0.0)
            entry.setdefault("lastUpdatedCampaignMinute", 0.0)
            entry.setdefault("controllingFaction", entry["abstract"].get("control") or "neutral")
            entry["confidence"] = "estimated"
            rebuilt[new_id] = entry
        carried = sum(1 for zid in rebuilt if inverse.get(zid))
        notes.append(f"{map_id}: zoneMemory {len(old_entries)} -> {len(rebuilt)} zones "
                     f"({carried} inherited control)")
        zone_memory[map_id] = rebuilt

    if apply:
        state["zoneMemory"] = zone_memory
        save_json(state_path, state)
    return notes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Migrate the campaign onto re-cut zones")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--derived-dir", default="")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    authored = ws / "data" / "zone_maps" / "authored"
    derived = Path(args.derived_dir) if args.derived_dir else ws / "data" / "zone_maps" / "derived"
    if not derived.exists() or not any(derived.glob("*.zone_map.json")):
        print(f"No derived zone maps in {derived} -- run tools/zone_cartographer_v1.py first.",
              file=sys.stderr)
        return 2

    combined: Dict[str, str] = {}
    per_map: Dict[str, Any] = {}
    new_maps: Dict[str, Dict[str, Any]] = {}
    for new_path in sorted(derived.glob("*.zone_map.json")):
        new_map = load_json(new_path)
        map_id = str(new_map.get("mapId") or new_path.name.split(".")[0])
        old_map = load_json(authored / f"{map_id}.authored.zone_map.json") or {"zones": []}
        result = map_zone_ids(ws, old_map, new_map)
        new_maps[map_id] = new_map
        per_map[map_id] = result
        combined.update(result["mapping"])

        print(f"{map_id}: {len(old_map.get('zones') or [])} old -> {len(new_map.get('zones') or [])} new")
        for row in result["detail"]:
            arrow = row["to"] or "(nothing -- old zone had no overlap)"
            print(f"  {row['from']:<32} -> {arrow:<28} share={row['share']:.2f}")

    notes: List[str] = []
    notes += rebuild_zone_memory(ws, new_maps, combined, args.apply)
    notes += remap_orders(ws, combined, args.apply, new_maps)
    notes += retag_base_templates(ws, new_maps, combined, args.apply)

    print("")
    for note in notes:
        print(f"  {note}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to promote the derived maps and repoint the campaign.")
        return 0

    migration = {
        "schemaVersion": "verdance-zone-id-migration/1.0",
        "zones": combined,
        "byMap": {k: v["mapping"] for k, v in per_map.items()},
        "unmapped": sorted(row["from"] for result in per_map.values()
                           for row in result["detail"] if not row["to"]),
    }
    save_json(authored / "zone_id_migration.json", migration)

    for new_path in sorted(derived.glob("*.zone_map.json")):
        new_map = load_json(new_path)
        map_id = str(new_map.get("mapId") or new_path.name.split(".")[0])
        shutil.copyfile(new_path, authored / f"{map_id}.authored.zone_map.json")
    print(f"promoted {len(new_maps)} zone maps into {authored}")

    for tool in ("derive_zone_adjacency.py", "build_world_zone_graph.py", "validate_world_zone_graph.py"):
        print(f"\n$ python tools/{tool}")
        proc = subprocess.run([sys.executable, str(ws / "tools" / tool)], cwd=str(ws),
                              capture_output=True, text=True)
        print(proc.stdout.strip() or proc.stderr.strip())
        if proc.returncode != 0:
            print(f"  {tool} failed", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
