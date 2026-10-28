"""
WO-003: Sortie order contract validator.

Reads a VA-SORTIE/1 packet (terse or markdown) or a JSON sortie order from
outbox/next_sortie_order.json, validates it against the world zone graph
(data/zone_maps/world_zone_graph.v1.json; legacy zone_adjacency.json fallback),
and either:
  - writes outbox/next_sortie_order.json  (schema verdance-sortie-order/1.0)
  - or prints a rejection with a named reason and exits non-zero.

Usage:
  python tools/validate_sortie_contract.py --sortie <path_to_sortie_json>
  python tools/validate_sortie_contract.py --packet "<VA-SORTIE/1 terse text>"
"""

import argparse
import json
import re
from pathlib import Path

# Allow `python tools/validate_sortie_contract.py` from workspace root.

from verdance.world import zone_graph as wzg

SORTIE_SCHEMA = "verdance-sortie-order/1.0"
STATE_PATH = Path("state/campaign_state.json")
OUTPUT_PATH = Path("outbox/next_sortie_order.json")

BLOC = {
    "ashwalkers": "nullmercs",
    "nullmercs": "nullmercs",
    "armada": "armada",
    "cortex": "cortex",
    "wild": "wild",
    "neutral": "neutral",
}
PATRONS = {"nullmercs", "armada", "cortex"}


def load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    txt = p.read_text(encoding="utf-8-sig")
    return json.loads(txt)


def save_json(p: Path, data: dict):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_zone_control(state: dict, map_id: str, zone_id: str) -> str:
    zm = state.get("zoneMemory", {}).get(map_id, {}).get(zone_id, {})
    return zm.get("controllingFaction") or zm.get("abstract", {}).get("control") or "neutral"


def validate_contract(sortie: dict, adjacency: dict, state: dict) -> list[str]:
    """Returns list of rejection reasons (empty = valid)."""
    errors = []

    map_id = sortie.get("mapId") or sortie.get("map")
    zone_id = sortie.get("targetZoneId") or sortie.get("zone")
    patron = sortie.get("patron")
    from_zones = sortie.get("fromZoneIds") or sortie.get("from", [])
    if isinstance(from_zones, str):
        from_zones = [z.strip() for z in from_zones.split(",") if z.strip()]

    # Rule 1: single target zone
    if not zone_id:
        errors.append("REJECT_NO_TARGET_ZONE: contract must specify exactly one target zone")
        return errors

    # Rule 2: patron must be a valid contractor
    if patron not in PATRONS:
        errors.append(f"REJECT_INVALID_PATRON: '{patron}' is not a valid patron (must be nullmercs, armada, or cortex)")

    # Rule 3: zone must not already belong to patron bloc
    patron_bloc = BLOC.get(patron, patron)
    current_ctrl = get_zone_control(state, map_id, zone_id)
    current_bloc = BLOC.get(current_ctrl, current_ctrl)
    if current_bloc == patron_bloc:
        errors.append(
            f"REJECT_ZONE_ALREADY_HELD: '{zone_id}' is already held by {current_ctrl} (bloc={current_bloc}), "
            f"which is the patron's own bloc ({patron_bloc})"
        )

    # Rule 4: adjacency — target zone must border at least one zone the patron holds
    map_adj = adjacency.get(map_id, {})
    if map_id not in adjacency:
        errors.append(f"REJECT_UNKNOWN_MAP: '{map_id}' has no adjacency graph entry")
        return errors

    if zone_id not in map_adj:
        errors.append(f"REJECT_UNKNOWN_ZONE: '{zone_id}' not found in adjacency graph for '{map_id}'")
        return errors

    # Find patron-held zones on this map
    map_zones = state.get("zoneMemory", {}).get(map_id, {})
    patron_held = set()
    for zid, zmem in map_zones.items():
        ctrl = zmem.get("controllingFaction") or zmem.get("abstract", {}).get("control") or "neutral"
        if BLOC.get(ctrl, ctrl) == patron_bloc:
            patron_held.add(zid)

    # Also include explicit fromZoneIds as patron-held (the deck's declared from set)
    for fz in from_zones:
        patron_held.add(fz)

    neighbors = set(map_adj.get(zone_id, []))
    if not neighbors.intersection(patron_held):
        errors.append(
            f"REJECT_NOT_ADJACENT: '{zone_id}' does not border any zone held by patron bloc '{patron_bloc}'. "
            f"Patron-held zones on map: {sorted(patron_held) or '[none in state — from_zones required]'}. "
            f"Target zone neighbors: {sorted(neighbors)}"
        )

    return errors


def parse_terse_packet(text: str) -> dict:
    """Parse a VA-SORTIE/1 terse packet into a dict."""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    out = {}
    for line in lines:
        if line.startswith("MAP "):
            out["mapId"] = line[4:].strip()
        elif line.startswith("ZONE "):
            out["targetZoneId"] = line[5:].strip()
        elif line.startswith("PATRON "):
            out["patron"] = line[7:].strip()
        elif line.startswith("AGAINST "):
            out["against"] = line[8:].strip()
        elif line.startswith("OBJ "):
            out["objectiveArchetype"] = line[4:].strip()
        elif line.startswith("FROM "):
            out["fromZoneIds"] = [z.strip() for z in line[5:].split(",")]
        elif line.startswith("DIFF "):
            m = re.match(r"DIFF (\d+)/(\d+)\s*target=(\S+)", line)
            if m:
                out["difficulty"] = int(m.group(1))
                out["difficultyMax"] = int(m.group(2))
                out["targetDuration"] = m.group(3)
        elif line.startswith("XP "):
            out["contractXp"] = int(line[3:].strip())
        elif line.startswith("PATH "):
            out["pathSignal"] = line[5:].strip()
        elif line.startswith("NAMED "):
            parts = line[6:].split()
            if len(parts) >= 3:
                out["namedDefender"] = {"id": parts[0], "name": " ".join(parts[1:2]), "details": parts[2:]}
        elif line.startswith("GRAPH "):
            out["graphSnapshot"] = {}
            for tok in line[6:].split():
                k, _, v = tok.partition("=")
                try:
                    out["graphSnapshot"][k] = float(v)
                except ValueError:
                    pass
        elif line.startswith("DERIV "):
            out["derived"] = {}
            for tok in line[6:].split():
                k, _, v = tok.partition("=")
                out["derived"][k] = v
        elif line.startswith("HOLD "):
            out["holdString"] = line[5:].strip()
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="WO-003: Validate and write sortie contract")
    parser.add_argument("--sortie", default="", help="Path to a JSON sortie order file")
    parser.add_argument("--packet", default="", help="VA-SORTIE/1 terse packet text")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not write output")
    args = parser.parse_args(argv)

    ws = Path(args.workspace).resolve()
    # Kernel atlas: world_zone_graph.v1 (same_map edges); legacy adjacency fallback.
    adj = wzg.load_full_adjacency(ws, kinds=("same_map",))
    state = load_json(ws / STATE_PATH)

    if args.packet:
        sortie = parse_terse_packet(args.packet)
    elif args.sortie:
        sortie = load_json(Path(args.sortie))
    else:
        # Try the live outbox file
        sortie = load_json(ws / OUTPUT_PATH)
        if not sortie:
            print("ERROR: No sortie input. Pass --sortie <file> or --packet '<text>'")
            return 2

    errors = validate_contract(sortie, adj, state)
    if errors:
        print("CONTRACT REJECTED:")
        for e in errors:
            print(f"  {e}")
        return 1

    # Build the canonical sortie order schema
    patron = sortie.get("patron", "nullmercs")
    order = {
        "schemaVersion": SORTIE_SCHEMA,
        "campaignId": state.get("campaignId", "verdance_ashes"),
        "mapId": sortie.get("mapId") or sortie.get("map"),
        "targetZoneId": sortie.get("targetZoneId") or sortie.get("zone"),
        "patron": patron,
        "patronBloc": BLOC.get(patron, patron),
        "against": sortie.get("against"),
        "fromZoneIds": sortie.get("fromZoneIds", []),
        "objectiveArchetype": sortie.get("objectiveArchetype"),
        "difficulty": sortie.get("difficulty"),
        "targetDuration": sortie.get("targetDuration", "10min"),
        "contractXp": sortie.get("contractXp"),
        "pathSignal": sortie.get("pathSignal"),
        "namedDefender": sortie.get("namedDefender"),
        "graphSnapshot": sortie.get("graphSnapshot"),
        "derived": sortie.get("derived"),
        "valid": True,
    }

    if not args.dry_run:
        out_path = ws / OUTPUT_PATH
        save_json(out_path, order)
        print(f"CONTRACT ACCEPTED → {out_path}")
    else:
        print("CONTRACT VALID (dry-run, not written)")

    print(json.dumps({k: v for k, v in order.items() if v is not None}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
