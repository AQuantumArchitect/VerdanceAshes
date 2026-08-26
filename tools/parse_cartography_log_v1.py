#!/usr/bin/env python3
"""Parse a BAR infolog written by game_verdance_cartography.lua into rasters.

Two products, both keyed to the same square grid:

  terrain  -> data/terrain/<mapId>.terrain.json
              what the ENGINE says the map is (height, slope, water, buildability,
              metal, per-move-class speeds, feature mass) plus BAR's metal spot
              list, map-authored start positions, and engine start boxes.

  behaviour -> data/behavior/<mapId>/<configId>.raster.json
              what the BOTS did on it (presence, structures, losses, mobile
              traffic, first-contact frame) binned into the same cells and
              sampled at milestone frames.

Both are sparse where sparsity pays: terrain is a dense row-major array (every
cell has terrain), behaviour is index-keyed dicts (most cells stay empty).

Usage:
  python tools/parse_cartography_log_v1.py --infolog <path> [--workspace .]
                                           [--terrain-out PATH] [--behaviour-out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

WS_DEFAULT = Path(__file__).resolve().parents[1]

TERRAIN_SCHEMA = "verdance-terrain-raster/1.0"
BEHAVIOUR_SCHEMA = "verdance-behaviour-raster/1.0"

TERRAIN_CHANNELS = [
    "height", "slope", "water", "buildable", "metal",
    "tankSpeed", "shipSpeed", "featureCount", "featureMetal",
]

# Infolog lines are prefixed with [t=..][f=..]; match the marker anywhere.
def _marker(name: str) -> re.Pattern:
    return re.compile(re.escape(name) + r"\s+(.*)$")


META_RE = _marker("VA_TERRAIN_META")
MAPNAME_RE = _marker("VA_TERRAIN_MAPNAME")
ROW_RE = _marker("VA_TERRAIN_ROW")
SPOT_RE = _marker("VA_TERRAIN_SPOT")
STARTPOS_RE = _marker("VA_TERRAIN_STARTPOS")
STARTBOX_RE = _marker("VA_TERRAIN_STARTBOX")
TEAM_RE = _marker("VA_CARTO_TEAM")
MILESTONE_RE = _marker("VA_CARTO_MILESTONE")
CELLS_RE = _marker("VA_CARTO_CELLS")
CONTACT_RE = _marker("VA_CARTO_CONTACT")
ARMED_RE = _marker("VA_CART_ARMED")


def parse_kv(text: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for token in text.split():
        if "=" in token:
            k, _, v = token.partition("=")
            out[k] = v
    return out


def num(value: str) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return int(f) if f.is_integer() else f


def parse_log(text: str) -> Dict[str, Any]:
    meta: Dict[str, str] = {}
    armed: Dict[str, str] = {}
    rows: Dict[int, List[List[float]]] = {}
    spots: List[Dict[str, float]] = []
    start_positions: List[Dict[str, Any]] = []
    start_boxes: List[Dict[str, Any]] = []
    teams: List[Dict[str, Any]] = []
    milestones: Dict[int, Dict[str, Any]] = {}
    map_name = ""

    for line in text.splitlines():
        if "VA_CART" not in line and "VA_TERRAIN" not in line:
            continue

        m = ARMED_RE.search(line)
        if m:
            armed = parse_kv(m.group(1))
            continue

        m = MAPNAME_RE.search(line)
        if m:
            map_name = m.group(1).strip()
            continue

        m = META_RE.search(line)
        if m:
            meta = parse_kv(m.group(1))
            continue

        m = ROW_RE.search(line)
        if m:
            parts = m.group(1).split(None, 1)
            if len(parts) == 2:
                row = int(parts[0])
                rows[row] = [[num(v) for v in cell.split(",")] for cell in parts[1].split("|")]
            continue

        m = SPOT_RE.search(line)
        if m:
            bits = m.group(1).split()
            if len(bits) >= 3:
                spots.append({"x": num(bits[0]), "z": num(bits[1]), "metal": num(bits[2])})
            continue

        m = STARTPOS_RE.search(line)
        if m:
            bits = m.group(1).split()
            if len(bits) >= 3:
                start_positions.append({"team": bits[0], "x": num(bits[1]), "z": num(bits[2])})
            continue

        m = STARTBOX_RE.search(line)
        if m:
            bits = m.group(1).split()
            if len(bits) >= 5:
                start_boxes.append({
                    "allyTeam": int(num(bits[0])),
                    "x1": num(bits[1]), "z1": num(bits[2]),
                    "x2": num(bits[3]), "z2": num(bits[4]),
                })
            continue

        m = TEAM_RE.search(line)
        if m:
            kv = parse_kv(m.group(1))
            teams.append({
                "team": int(num(kv.get("team", "0"))),
                "allyTeam": int(num(kv.get("ally", "0"))),
                "side": kv.get("side", ""),
                "ai": kv.get("ai") == "true",
                "dead": kv.get("dead") == "true",
            })
            continue

        m = CELLS_RE.search(line)
        if m:
            kv = parse_kv(m.group(1))
            frame = int(num(kv.get("f", "0")))
            ally = int(num(kv.get("a", "0")))
            body = m.group(1).split(None, 3)
            if len(body) < 4:
                continue
            entry = milestones.setdefault(frame, {"frame": frame, "allies": {}, "contact": {}})
            bucket = entry["allies"].setdefault(str(ally), {
                "presence": {}, "structure": {}, "loss": {}, "traffic": {}, "defence": {},
            })
            for record in body[3].split(";"):
                fields = record.split(",")
                if len(fields) < 5:
                    continue
                idx = fields[0]
                bucket["presence"][idx] = num(fields[1])
                bucket["structure"][idx] = num(fields[2])
                bucket["loss"][idx] = num(fields[3])
                bucket["traffic"][idx] = num(fields[4])
                if len(fields) >= 6:
                    bucket["defence"][idx] = num(fields[5])
            continue

        m = CONTACT_RE.search(line)
        if m:
            kv = parse_kv(m.group(1))
            frame = int(num(kv.get("f", "0")))
            body = m.group(1).split(None, 3)
            if len(body) < 3:
                continue
            payload = body[-1]
            entry = milestones.setdefault(frame, {"frame": frame, "allies": {}, "contact": {}})
            for record in payload.split(";"):
                fields = record.split(",")
                if len(fields) < 2:
                    continue
                entry["contact"][fields[0]] = int(num(fields[1]))
            continue

        m = MILESTONE_RE.search(line)
        if m and "MILESTONE_END" not in line:
            kv = parse_kv(m.group(1))
            frame = int(num(kv.get("frame", "0")))
            entry = milestones.setdefault(frame, {"frame": frame, "allies": {}, "contact": {}})
            entry["seconds"] = num(kv.get("seconds", "0"))
            entry["samples"] = int(num(kv.get("samples", "0")))
            entry["mapId"] = kv.get("mapId", "")
            entry["configId"] = kv.get("config", "")
            continue

    return {
        "armed": armed,
        "meta": meta,
        "mapName": map_name,
        "rows": rows,
        "spots": spots,
        "startPositions": start_positions,
        "startBoxes": start_boxes,
        "teams": teams,
        "milestones": milestones,
    }


def build_terrain(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    meta = parsed["meta"]
    rows = parsed["rows"]
    if not meta or not rows:
        return None
    res = int(num(meta.get("res", "0")))
    if res <= 0:
        return None
    missing = [r for r in range(res) if r not in rows]
    cells: List[List[float]] = []
    for r in range(res):
        row = rows.get(r) or [[0] * len(TERRAIN_CHANNELS)] * res
        cells.extend(row)
    return {
        "schemaVersion": TERRAIN_SCHEMA,
        "mapId": meta.get("mapId", "unknown"),
        "mapName": parsed.get("mapName", ""),
        "size": {"x": int(num(meta.get("sx", "0"))), "z": int(num(meta.get("sz", "0")))},
        "grid": {
            "res": res,
            "cellW": num(meta.get("cellW", "0")),
            "cellH": num(meta.get("cellH", "0")),
            "squareSize": int(num(meta.get("squareSize", "8"))),
            "metalSquare": int(num(meta.get("metalSquare", "16"))),
        },
        "channels": TERRAIN_CHANNELS,
        "cells": cells,
        "metalSpots": parsed["spots"],
        "startPositions": parsed["startPositions"],
        "startBoxes": parsed["startBoxes"],
        "teams": parsed["teams"],
        "incompleteRows": missing,
    }


def build_behaviour(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    milestones = parsed["milestones"]
    if not milestones:
        return None
    armed = parsed["armed"]
    ordered = [milestones[f] for f in sorted(milestones)]
    map_id = armed.get("mapId") or next((m.get("mapId") for m in ordered if m.get("mapId")), "unknown")
    config_id = armed.get("config") or next((m.get("configId") for m in ordered if m.get("configId")), "default")
    res = int(num(armed.get("res", "0"))) or int(num(parsed["meta"].get("res", "0")))
    return {
        "schemaVersion": BEHAVIOUR_SCHEMA,
        "mapId": map_id,
        "configId": config_id,
        "grid": {"res": res},
        "teams": parsed["teams"],
        "milestones": ordered,
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Parse cartography infolog into terrain/behaviour rasters")
    ap.add_argument("--infolog", required=True)
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--terrain-out", default="")
    ap.add_argument("--behaviour-out", default="")
    ap.add_argument("--map-id", default="")
    ap.add_argument("--config-id", default="")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    log_path = Path(args.infolog)
    if not log_path.exists():
        print(f"infolog not found: {log_path}", file=sys.stderr)
        return 2
    text = log_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_log(text)

    written: List[str] = []

    terrain = build_terrain(parsed)
    if terrain:
        if args.map_id:
            terrain["mapId"] = args.map_id
        out = Path(args.terrain_out) if args.terrain_out else ws / "data" / "terrain" / f"{terrain['mapId']}.terrain.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(terrain, indent=1), encoding="utf-8")
        written.append(f"terrain: {out} ({len(terrain['cells'])} cells, "
                       f"{len(terrain['metalSpots'])} metal spots, "
                       f"{len(terrain['incompleteRows'])} missing rows)")

    behaviour = build_behaviour(parsed)
    if behaviour:
        if args.map_id:
            behaviour["mapId"] = args.map_id
        if args.config_id:
            behaviour["configId"] = args.config_id
        out = (Path(args.behaviour_out) if args.behaviour_out
               else ws / "data" / "behavior" / behaviour["mapId"] / f"{behaviour['configId']}.raster.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(behaviour, indent=1), encoding="utf-8")
        frames = [m["frame"] for m in behaviour["milestones"]]
        written.append(f"behaviour: {out} (milestones {frames})")

    if not written:
        print("No cartography markers found in the infolog.", file=sys.stderr)
        return 1
    for line in written:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
