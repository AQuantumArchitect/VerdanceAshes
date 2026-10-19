#!/usr/bin/env python3
"""Turn telemetry already on disk into a behaviour prior for the cartographer.

The cartography behaviour survey has not been run, so this reconstructs the best
available substitute from the June 2026 telemetry:

  * `grid_survey` packets bin the map on an 8x8 GRID -- a genuine, if coarse,
    spatial raster of where the war was at 1-2.5 sim-minutes.
  * `authored_baseline` / `player_team_*` packets run out to 89 sim-minutes but
    only resolve to the 6-7 authored RECTANGLES, so their mass has to be spread
    back over each rectangle's cells.

Both are weak. The grid is coarse and early; the rect back-projection is
literally rectangle-shaped and cannot know where inside a rectangle anything
stood. Everything emitted here is stamped `source: "legacy_prior"` and a
`fidelity` grade so nothing downstream mistakes it for measurement.

The output uses the same schema `parse_cartography_log_v1.py` writes, so
`CellGrid` consumes it unchanged -- including its resolution remapping, which is
what lets an 8x8 prior inform a 96x96 grid without piling into one corner.

    python tools/legacy_behaviour_prior_v1.py
    python tools/legacy_behaviour_prior_v1.py --maps koom_valley
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from zone_cartographer_v1 import CH  # noqa: E402

SCHEMA = "verdance-behaviour-raster/1.0"
GRID_ID = re.compile(r"_G(\d\d)_(\d\d)$")

# Telemetry reports value classes, not the position-binned channels the live
# cartography gadget emits. This is the honest mapping between them:
#   presence  <- totalUnitValue      (everything standing there)
#   structure <- defensiveValue + buildPower
#   defence   <- defensiveValue
#   traffic   <- armyValue           (mobile combat mass, not a movement count)
#   loss      <- unavailable; the packets record no deaths by position
CHANNEL_NOTE = ("territory=defensiveValue (DV-only ownership), "
                "structure=defensiveValue+buildPower, defence=defensiveValue, "
                "traffic=armyValue, loss=unmeasured")


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def packet_map_id(packet: Dict[str, Any]) -> Optional[str]:
    m = packet.get("map")
    if isinstance(m, dict) and m.get("mapId"):
        return str(m["mapId"])
    return None


def collect_packets(ws: Path) -> Dict[str, List[Tuple[Path, Dict[str, Any]]]]:
    out: Dict[str, List[Tuple[Path, Dict[str, Any]]]] = defaultdict(list)
    for path in (ws / "headless_runs").rglob("telemetry_packet.json"):
        try:
            packet = load_json(path)
        except Exception:
            continue
        map_id = packet_map_id(packet)
        zones = packet.get("zones")
        if not map_id or not isinstance(zones, dict) or not zones:
            continue
        out[map_id].append((path, packet))
    return out


def is_grid_packet(packet: Dict[str, Any]) -> bool:
    return any(GRID_ID.search(k) for k in (packet.get("zones") or {}))


def grid_dimensions(packet: Dict[str, Any]) -> int:
    rows = 0
    cols = 0
    for key in packet.get("zones") or {}:
        m = GRID_ID.search(key)
        if m:
            rows = max(rows, int(m.group(1)) + 1)
            cols = max(cols, int(m.group(2)) + 1)
    return max(rows, cols)


def zone_metrics(entry: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """Per ally team: the four channels we can reconstruct."""
    out: Dict[str, Dict[str, float]] = {}
    for team in entry.get("teams") or []:
        metrics = team.get("metrics") or {}
        ally = str(team.get("allyTeamId", team.get("teamId", 0)))
        bucket = out.setdefault(ally, {"presence": 0.0, "structure": 0.0,
                                       "defence": 0.0, "traffic": 0.0})
        army = float(metrics.get("armyValue", 0.0) or 0.0)
        build = float(metrics.get("buildPower", 0.0) or 0.0)
        defv = float(metrics.get("defensiveValue", 0.0) or 0.0)
        total = float(metrics.get("totalUnitValue", 0.0) or 0.0) or (army + build + defv)
        bucket["presence"] += total
        bucket["structure"] += defv + build
        bucket["defence"] += defv
        bucket["traffic"] += army
    return out


def teams_of(packet: Dict[str, Any]) -> List[Dict[str, Any]]:
    seen: Dict[int, Dict[str, Any]] = {}
    for team in packet.get("teams") or []:
        tid = int(team.get("teamId", 0))
        seen[tid] = {
            "team": tid,
            "allyTeam": str(team.get("allyTeamId", tid)),
            "side": str(team.get("side") or ""),
            "ai": bool(team.get("isAi")),
            "dead": bool(team.get("isDead")),
        }
    return [seen[k] for k in sorted(seen)]


def build_from_grid(packets: List[Tuple[Path, Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    """One raster from the 8x8 grid survey: the latest frame of each run, summed."""
    latest: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    res = 0
    teams: List[Dict[str, Any]] = []
    for path, packet in packets:
        if not is_grid_packet(packet):
            continue
        res = max(res, grid_dimensions(packet))
        run = str(path.parent.parent.parent.name)
        frame = int(packet.get("frame", 0) or 0)
        if run not in latest or frame > latest[run][0]:
            latest[run] = (frame, packet)
        if not teams:
            teams = teams_of(packet)
    if not latest or res <= 0:
        return None

    allies: Dict[str, Dict[str, Dict[str, float]]] = {}
    contact: Dict[str, int] = {}
    max_frame = 0
    for frame, packet in latest.values():
        max_frame = max(max_frame, frame)
        for key, entry in (packet.get("zones") or {}).items():
            m = GRID_ID.search(key)
            if not m:
                continue
            idx = str(int(m.group(1)) * res + int(m.group(2)))
            per_ally = zone_metrics(entry)
            if len(per_ally) > 1:
                contact.setdefault(idx, frame)
            for ally, channels in per_ally.items():
                bucket = allies.setdefault(ally, {"presence": {}, "structure": {},
                                                  "loss": {}, "traffic": {}, "defence": {}})
                for name, value in channels.items():
                    if value:
                        bucket[name][idx] = bucket[name].get(idx, 0.0) + value
    if not allies:
        return None
    return {
        "grid": {"res": res},
        "teams": teams,
        "milestones": [{"frame": max_frame, "seconds": round(max_frame / 30.0, 1),
                        "samples": len(latest), "allies": allies, "contact": contact}],
        "runs": len(latest),
    }


def build_from_rects(packets: List[Tuple[Path, Dict[str, Any]]], terrain: Dict[str, Any],
                     zone_map: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Back-project rect-zone telemetry onto cells.

    Presence and traffic spread evenly over the rectangle; structure and defence
    are weighted by buildability and metal, because a factory cannot have stood
    on unbuildable ground even though the rectangle says it did."""
    res = int(terrain["grid"]["res"])
    cells = terrain["cells"]
    zones = {str(z.get("zoneId")): z for z in (zone_map.get("zones") or [])}
    if not zones:
        return None

    cell_index: Dict[str, List[int]] = {}
    for zid, zone in zones.items():
        bounds = zone.get("bounds") or {}
        if not bounds:
            continue
        members = []
        for r in range(res):
            zn = (r + 0.5) / res
            if not (float(bounds["zMin"]) <= zn < float(bounds["zMax"])):
                continue
            for c in range(res):
                if float(bounds["xMin"]) <= (c + 0.5) / res < float(bounds["xMax"]):
                    members.append(r * res + c)
        if members:
            cell_index[zid] = members
    if not cell_index:
        return None

    latest: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    teams: List[Dict[str, Any]] = []
    for path, packet in packets:
        if is_grid_packet(packet):
            continue
        if not any(k in zones for k in (packet.get("zones") or {})):
            continue
        run = str(path.parent.parent.parent.name)
        frame = int(packet.get("frame", 0) or 0)
        if run not in latest or frame > latest[run][0]:
            latest[run] = (frame, packet)
        if not teams:
            teams = teams_of(packet)
    if not latest:
        return None

    allies: Dict[str, Dict[str, Dict[str, float]]] = {}
    contact: Dict[str, int] = {}
    max_frame = 0
    for frame, packet in latest.values():
        max_frame = max(max_frame, frame)
        for zid, entry in (packet.get("zones") or {}).items():
            members = cell_index.get(str(zid))
            if not members:
                continue
            per_ally = zone_metrics(entry)
            if len(per_ally) > 1:
                for idx in members:
                    contact.setdefault(str(idx), frame)
            build_w = [max(0.05, cells[i][CH["buildable"]] + cells[i][CH["metal"]] * 4.0)
                       for i in members]
            build_total = sum(build_w) or 1.0
            flat = 1.0 / len(members)
            for ally, channels in per_ally.items():
                bucket = allies.setdefault(ally, {"presence": {}, "structure": {},
                                                  "loss": {}, "traffic": {}, "defence": {}})
                for name, value in channels.items():
                    if not value:
                        continue
                    weighted = name in ("structure", "defence")
                    for k, idx in enumerate(members):
                        share = (build_w[k] / build_total) if weighted else flat
                        key = str(idx)
                        bucket[name][key] = bucket[name].get(key, 0.0) + value * share
    if not allies:
        return None
    return {
        "grid": {"res": res},
        "teams": teams,
        "milestones": [{"frame": max_frame, "seconds": round(max_frame / 30.0, 1),
                        "samples": len(latest), "allies": allies, "contact": contact}],
        "runs": len(latest),
    }


def write_raster(dest: Path, map_id: str, config_id: str, body: Dict[str, Any],
                 fidelity: str, note: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schemaVersion": SCHEMA,
        "mapId": map_id,
        "configId": config_id,
        "grid": body["grid"],
        "teams": body["teams"],
        "milestones": body["milestones"],
        "source": "legacy_prior",
        "fidelity": fidelity,
        "note": note,
        "channelMapping": CHANNEL_NOTE,
        "runs": body.get("runs", 0),
    }
    dest.write_text(json.dumps(payload), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Behaviour prior from existing telemetry")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--maps", default="")
    ap.add_argument("--zones", default="authored")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    wanted = [m.strip() for m in args.maps.split(",") if m.strip()]
    by_map = collect_packets(ws)
    if not by_map:
        print("no telemetry packets found under headless_runs/", file=sys.stderr)
        return 1

    print(f"{'map':<18}{'grid prior':>28}{'rect prior':>28}")
    for map_id in sorted(by_map):
        if wanted and map_id not in wanted:
            continue
        packets = by_map[map_id]
        out_dir = ws / "data" / "behavior" / map_id
        grid_note = rect_note = "-"

        grid = build_from_grid(packets)
        if grid:
            write_raster(out_dir / "legacy_grid.raster.json", map_id, "legacy_grid", grid,
                         "coarse-early",
                         f"June 8x8 grid survey, {grid['runs']} runs, to frame "
                         f"{grid['milestones'][0]['frame']}")
            grid_note = (f"{grid['grid']['res']}x{grid['grid']['res']}, "
                         f"{grid['runs']} runs, f{grid['milestones'][0]['frame']}")

        terrain_path = ws / "data" / "terrain" / f"{map_id}.terrain.json"
        zone_path = ws / "data" / "zone_maps" / args.zones / f"{map_id}.authored.zone_map.json"
        if terrain_path.exists() and zone_path.exists():
            rect = build_from_rects(packets, load_json(terrain_path), load_json(zone_path))
            if rect:
                write_raster(out_dir / "legacy_rect.raster.json", map_id, "legacy_rect", rect,
                             "rectangle-shaped-late",
                             f"authored-rect telemetry back-projected, {rect['runs']} runs, "
                             f"to frame {rect['milestones'][0]['frame']}")
                rect_note = (f"{len(rect['teams'])} teams, {rect['runs']} runs, "
                             f"f{rect['milestones'][0]['frame']}")

        print(f"{map_id:<18}{grid_note:>28}{rect_note:>28}")
    print("\nboth priors are weak and stamped source=legacy_prior; "
          "loss is unmeasured in either")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
