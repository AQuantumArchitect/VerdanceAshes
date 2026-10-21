#!/usr/bin/env python3
"""Score a zone map against measured evidence, instead of against taste.

Two evidence sources, same report:

  legacy  -- per-zone telemetry packets already on disk from the June 2026
             authored surveys (headless_runs/fib_profiler_*/milestones/*/
             telemetry_packet.json). Gives coverage, salience, contestedness
             and role fit. Terrain metrics stay "unmeasured".

  raster  -- cell rasters from the cartography survey (data/terrain/*.terrain.json
             + data/behavior/<map>/*.raster.json). Adds terrain purity, anchor
             validity and zone separation, and measures coverage per cell rather
             than per zone.

Run it on the CURRENT zone maps to get the empirical case for a remap, then on
the new ones to show the delta.

Usage:
  python tools/zone_scorecard_v1.py [--workspace .] [--source legacy|raster|auto]
                                    [--zone-dir data/zone_maps/authored]
                                    [--out outbox/zone_scorecard.latest.md]
                                    [--json outbox/zone_scorecard.latest.json]
                                    [--label "current zones"]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

WS_DEFAULT = Path(__file__).resolve().parents[1]

SCHEMA = "verdance-zone-scorecard/1.0"

# Thresholds. These are the contract: a zone map either clears them or it does not.
COVERAGE_PASS = 0.90
COVERAGE_WARN = 0.75
DEAD_ZONE_PEAK_SHARE = 0.01
CONTEST_MIN_FOR_LANES = 0.30
PURITY_WATER_WARN = 0.35
ANCHOR_SLOPE_MAX = 0.30

# What each authored role CLAIMS about behaviour, and therefore what the
# measurement has to show for the role to be honest.
ROLE_EXPECTATION = {
    "legion_start": "base",
    "defender_start": "base",
    "armada_start": "base",
    "cortex_start": "base",
    "start": "base",
    "energy_edge": "economy",
    "main_field": "economy",
    "lane": "transit",
    "causeway": "transit",
    "approach_lane": "transit",
    "siege_approach": "transit",
    "scar_entrance": "transit",
    "gate": "transit",
    "contested_default": "transit",
    "plateau": "hold",
    "island_chain": "hold",
    "rim_control": "hold",
    "flank_pocket": "hold",
    "central_objective": "hold",
    "citadel": "fortress",
    "fortress": "fortress",
    "relay": "transit",
    "legion_start": "base",
    "primary_lane": "transit",
    "approach_gate": "transit",
    "exposed_crossing": "transit",
    "crossfire_route": "transit",
    "flank_lane": "transit",
    "secondary_route": "transit",
    "reserve": "economy",
    "wild": "hazard",
    "swamp": "hold",
    "raptor_wilds": "hazard",
    "raptor_hazard": "hazard",
}

HAZARD_HINTS = ("raptor", "scavenger", "critter", "chicken")


def quest_generator_roles() -> set:
    """Roles the quest generator can actually read. A zone whose role is missing
    here silently falls through to the seize_lane default, which is how every
    board ended up the same kind before Drop 4."""
    from verdance.company import quest_generator as qg

    return set(qg.ROLE_ARCHETYPE)


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_zone_maps(zone_dir: Path) -> Dict[str, Dict[str, Any]]:
    maps: Dict[str, Dict[str, Any]] = {}
    for path in sorted(zone_dir.glob("*.zone_map.json")):
        data = load_json(path)
        if not data or not data.get("zones"):
            continue
        map_id = data.get("mapId") or path.name.split(".")[0]
        maps[map_id] = data
    return maps


# ---------------------------------------------------------------------------
# Legacy evidence: per-zone telemetry packets
# ---------------------------------------------------------------------------

def iter_legacy_packets(ws: Path) -> Iterable[Dict[str, Any]]:
    runs = ws / "headless_runs"
    if not runs.exists():
        return
    for packet_path in sorted(runs.glob("fib_profiler_*/milestones/*/telemetry_packet.json")):
        data = load_json(packet_path)
        if isinstance(data, dict) and data.get("zones"):
            data["_source"] = str(packet_path.relative_to(ws))
            yield data


def team_value(team: Dict[str, Any]) -> float:
    return float(((team.get("metrics") or {}).get("totalUnitValue")) or 0.0)


def is_hazard_team(team: Dict[str, Any]) -> bool:
    counts = team.get("unitCountsByDef") or {}
    for name in counts:
        if any(hint in name for hint in HAZARD_HINTS):
            return True
    return False


def summarize_legacy(ws: Path, zone_maps: Dict[str, Dict[str, Any]],
                     variants: Sequence[str] = ()) -> Dict[str, Any]:
    """Aggregate every June milestone packet into per-zone behaviour shares.

    Packets are only counted for a map when their zone ids actually belong to
    that map's zone map -- the corpus also contains 8x8 grid-survey packets
    (instrumentation cells, not zones) and campaign-mission packets."""
    per_map: Dict[str, Dict[str, Any]] = {}
    for packet in iter_legacy_packets(ws):
        map_id = ((packet.get("map") or {}).get("mapId")) or ""
        if map_id not in zone_maps:
            continue
        variant = str(packet.get("variantId") or "")
        if variants and variant not in variants:
            continue
        authored_ids = {str(z.get("zoneId")) for z in zone_maps[map_id].get("zones") or []}
        packet_ids = {str(k) for k in (packet.get("zones") or {})}
        if not packet_ids or len(packet_ids & authored_ids) < max(1, len(packet_ids) // 2):
            continue
        entry = per_map.setdefault(map_id, {
            "samples": 0, "runs": set(), "frames": set(), "variants": defaultdict(int),
            "zoneValue": defaultdict(float), "zoneStructure": defaultdict(float),
            "zoneDefensive": defaultdict(float), "zoneHazard": defaultdict(float),
            "zoneContestHits": defaultdict(int), "zoneActiveHits": defaultdict(int),
            "zoneFirstFrame": {}, "mapValue": 0.0, "zonedValue": 0.0,
        })
        entry["samples"] += 1
        entry["variants"][variant] += 1
        source = packet["_source"].replace("\\", "/")
        entry["runs"].add(source.split("/")[1] if "/" in source else source)
        frame = int(packet.get("frame") or 0)
        entry["frames"].add(frame)

        map_total = sum(team_value(t) for t in (packet.get("teams") or []))
        entry["mapValue"] += map_total

        for zone_id, zone in (packet.get("zones") or {}).items():
            teams = zone.get("teams") or []
            zone_total = sum(team_value(t) for t in teams)
            entry["zonedValue"] += zone_total
            entry["zoneValue"][zone_id] += zone_total
            for team in teams:
                metrics = team.get("metrics") or {}
                if is_hazard_team(team):
                    entry["zoneHazard"][zone_id] += team_value(team)
                entry["zoneStructure"][zone_id] += float(metrics.get("structureCount") or 0)
                entry["zoneDefensive"][zone_id] += float(metrics.get("defensiveValue") or 0)
            # Contested = at least two ally teams each holding a real share here.
            by_ally: Dict[Any, float] = defaultdict(float)
            for team in teams:
                by_ally[team.get("allyTeamId")] += team_value(team)
            serious = [v for v in by_ally.values() if v >= max(200.0, 0.05 * zone_total)]
            if zone_total > 0:
                entry["zoneActiveHits"][zone_id] += 1
                prev = entry["zoneFirstFrame"].get(zone_id)
                if prev is None or frame < prev:
                    entry["zoneFirstFrame"][zone_id] = frame
            if len(serious) >= 2:
                entry["zoneContestHits"][zone_id] += 1

    for entry in per_map.values():
        entry["runs"] = sorted(entry["runs"])
        entry["frames"] = sorted(entry["frames"])
        entry["variants"] = dict(entry["variants"])
    return per_map


def score_legacy_map(map_id: str, zone_map: Dict[str, Any], agg: Dict[str, Any]) -> Dict[str, Any]:
    zones = zone_map.get("zones") or []
    samples = max(1, int(agg["samples"]))
    map_value = agg["mapValue"] or 0.0
    zoned_value = agg["zonedValue"] or 0.0
    coverage = (zoned_value / map_value) if map_value > 0 else 0.0

    total_zone_value = sum(agg["zoneValue"].values()) or 1.0
    zone_rows = []
    for zone in zones:
        zid = str(zone.get("zoneId"))
        value = agg["zoneValue"].get(zid, 0.0)
        share = value / total_zone_value
        active = agg["zoneActiveHits"].get(zid, 0)
        active_fraction = active / samples if samples else 0.0
        # Contest is conditional: WHEN the war reached this zone, was it fought
        # over? Dividing by all samples would just re-measure how often anything
        # happened here, which activeFraction already says.
        contested = agg["zoneContestHits"].get(zid, 0) / active if active else 0.0
        hazard = agg["zoneHazard"].get(zid, 0.0)
        hazard_frac = (hazard / value) if value > 0 else 0.0
        structures = agg["zoneStructure"].get(zid, 0.0) / samples
        defensive = agg["zoneDefensive"].get(zid, 0.0)
        defensive_frac = (defensive / value) if value > 0 else 0.0
        role = str(zone.get("role") or "")
        expectation = ROLE_EXPECTATION.get(role, "unclassified")

        verdicts: List[str] = []
        if share < DEAD_ZONE_PEAK_SHARE:
            verdicts.append("FAIL: dead zone (the war never goes here)")
        if active_fraction < 0.34 and share >= DEAD_ZONE_PEAK_SHARE:
            verdicts.append(f"WARN: empty in {1 - active_fraction:.0%} of samples")
        if expectation == "transit" and contested < CONTEST_MIN_FOR_LANES and share >= DEAD_ZONE_PEAK_SHARE:
            verdicts.append(f"FAIL: role claims a lane but contest={contested:.2f} when reached")
        if expectation == "hazard" and hazard_frac < 0.25:
            verdicts.append(f"FAIL: role claims wilds but hazard mass={hazard_frac:.2f}")
        if expectation == "base" and structures < 3:
            verdicts.append("WARN: role claims a base but almost nothing is built here")
        if expectation == "fortress" and defensive_frac < 0.25:
            verdicts.append(f"WARN: role claims a fortress but defence={defensive_frac:.2f}")
        if expectation == "unclassified" and role:
            verdicts.append(f"WARN: role '{role}' has no measurable expectation")

        zone_rows.append({
            "zoneId": zid,
            "label": zone.get("label") or zid,
            "role": role,
            "expectation": expectation,
            "activityShare": round(share, 4),
            "activeFraction": round(active_fraction, 3),
            "contested": round(contested, 3),
            "hazardFraction": round(hazard_frac, 3),
            "defensiveFraction": round(defensive_frac, 3),
            "meanStructures": round(structures, 1),
            "activeSamples": active,
            "verdicts": verdicts,
            "status": "FAIL" if any(v.startswith("FAIL") for v in verdicts)
                      else ("WARN" if verdicts else "PASS"),
        })

    zone_rows.sort(key=lambda r: -r["activityShare"])
    coverage_status = ("PASS" if coverage >= COVERAGE_PASS
                       else "WARN" if coverage >= COVERAGE_WARN else "FAIL")
    return {
        "mapId": map_id,
        "mapName": zone_map.get("mapName") or map_id,
        "source": "legacy",
        "samples": samples,
        "runs": agg["runs"],
        "frames": agg["frames"],
        "variants": agg.get("variants") or {},
        "coverage": round(coverage, 4),
        "coverageStatus": coverage_status,
        "zoneCount": len(zone_rows),
        "deadZones": [z["zoneId"] for z in zone_rows if z["activityShare"] < DEAD_ZONE_PEAK_SHARE],
        "failing": [z["zoneId"] for z in zone_rows if z["status"] == "FAIL"],
        "zones": zone_rows,
    }


# ---------------------------------------------------------------------------
# Raster evidence: cell-level terrain + behaviour
# ---------------------------------------------------------------------------

CH = {name: i for i, name in enumerate(
    ["height", "slope", "water", "buildable", "metal",
     "tankSpeed", "shipSpeed", "featureCount", "featureMetal"])}


def zone_cells(zone: Dict[str, Any], res: int) -> List[int]:
    """Cells belonging to a zone: explicit mask if present, else its rect."""
    if zone.get("cells"):
        cells = zone["cells"]
        if cells and isinstance(cells[0], list) and len(cells[0]) == 2:
            out: List[int] = []
            for start, length in cells:          # run-length encoded
                out.extend(range(int(start), int(start) + int(length)))
            return out
        return [int(c) for c in cells]
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


def behaviour_totals(rasters: Sequence[Dict[str, Any]]) -> Tuple[Dict[int, float], Dict[int, float],
                                                                 Dict[int, float], Dict[int, Dict[str, float]]]:
    """Per-cell presence, loss and traffic summed over configs, plus per-ally presence."""
    presence: Dict[int, float] = defaultdict(float)
    loss: Dict[int, float] = defaultdict(float)
    traffic: Dict[int, float] = defaultdict(float)
    by_ally: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for raster in rasters:
        milestones = raster.get("milestones") or []
        if not milestones:
            continue
        final = milestones[-1]          # accumulators are cumulative
        for ally, channels in (final.get("allies") or {}).items():
            for idx_s, value in (channels.get("presence") or {}).items():
                idx = int(idx_s)
                presence[idx] += float(value)
                by_ally[idx][ally] += float(value)
            for idx_s, value in (channels.get("loss") or {}).items():
                loss[int(idx_s)] += float(value)
            for idx_s, value in (channels.get("traffic") or {}).items():
                traffic[int(idx_s)] += float(value)
    return presence, loss, traffic, by_ally


def score_raster_map(map_id: str, zone_map: Dict[str, Any], terrain: Dict[str, Any],
                     rasters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    res = int(terrain["grid"]["res"])
    cells = terrain["cells"]
    presence, loss, traffic, by_ally = behaviour_totals(rasters)
    total_presence = sum(presence.values()) or 1.0

    owner: Dict[int, str] = {}
    for zone in zone_map.get("zones") or []:
        for idx in zone_cells(zone, res):
            owner.setdefault(idx, str(zone.get("zoneId")))

    covered = sum(v for idx, v in presence.items() if idx in owner)
    coverage = covered / total_presence

    zone_rows = []
    for zone in zone_map.get("zones") or []:
        zid = str(zone.get("zoneId"))
        idxs = [i for i in zone_cells(zone, res) if owner.get(i) == zid]
        if not idxs:
            zone_rows.append({"zoneId": zid, "label": zone.get("label") or zid,
                              "role": zone.get("role") or "", "status": "FAIL",
                              "verdicts": ["FAIL: zone owns no cells"], "activityShare": 0.0})
            continue
        zone_presence = sum(presence.get(i, 0.0) for i in idxs)
        zone_loss = sum(loss.get(i, 0.0) for i in idxs)
        zone_traffic = sum(traffic.get(i, 0.0) for i in idxs)
        share = zone_presence / total_presence

        water = sum(cells[i][CH["water"]] for i in idxs) / len(idxs)
        buildable = sum(cells[i][CH["buildable"]] for i in idxs) / len(idxs)
        slopes = [cells[i][CH["slope"]] for i in idxs]
        slope_mean = sum(slopes) / len(slopes)
        slope_sd = math.sqrt(sum((s - slope_mean) ** 2 for s in slopes) / len(slopes))
        metal = sum(cells[i][CH["metal"]] for i in idxs) / len(idxs)

        ally_totals: Dict[str, float] = defaultdict(float)
        for i in idxs:
            for ally, value in by_ally.get(i, {}).items():
                ally_totals[ally] += value
        serious = [v for v in ally_totals.values() if v >= max(200.0, 0.1 * zone_presence)]
        contested = len(serious) >= 2

        anchor = zone.get("anchor") or {}
        anchor_status = "unmeasured"
        if anchor:
            ax = float(anchor.get("x", 0.5))
            az = float(anchor.get("z", 0.5))
            col = min(res - 1, max(0, int(ax * res)))
            row = min(res - 1, max(0, int(az * res)))
            cell = cells[row * res + col]
            ok = cell[CH["buildable"]] > 0.4 and cell[CH["water"]] < 0.25 and cell[CH["slope"]] < ANCHOR_SLOPE_MAX
            anchor_status = "ok" if ok else "invalid"

        verdicts: List[str] = []
        if share < DEAD_ZONE_PEAK_SHARE:
            verdicts.append("FAIL: dead zone (no measured activity)")
        expectation = ROLE_EXPECTATION.get(str(zone.get("role") or ""), "unclassified")
        if expectation == "transit" and not contested:
            verdicts.append("FAIL: role claims a lane but only one bloc ever holds it")
        if expectation in ("base", "hold", "fortress") and buildable < 0.25:
            verdicts.append(f"WARN: role expects building but buildable={buildable:.2f}")
        if water > PURITY_WATER_WARN and expectation not in ("hazard",):
            verdicts.append(f"WARN: {water:.0%} water inside a land-role zone")
        if anchor_status == "invalid":
            verdicts.append("FAIL: anchor is not buildable/dry/flat")
        if anchor_status == "unmeasured":
            verdicts.append("WARN: no anchor authored (camps fall back to rect centre)")

        zone_rows.append({
            "zoneId": zid,
            "label": zone.get("label") or zid,
            "role": zone.get("role") or "",
            "expectation": expectation,
            "cellCount": len(idxs),
            "activityShare": round(share, 4),
            "lossShare": round(zone_loss / (sum(loss.values()) or 1.0), 4),
            "traffic": round(zone_traffic, 1),
            "contested": contested,
            "water": round(water, 3),
            "buildable": round(buildable, 3),
            "slopeMean": round(slope_mean, 3),
            "slopeSd": round(slope_sd, 3),
            "metal": round(metal, 4),
            "anchor": anchor_status,
            "verdicts": verdicts,
            "status": "FAIL" if any(v.startswith("FAIL") for v in verdicts)
                      else ("WARN" if verdicts else "PASS"),
        })

    zone_rows.sort(key=lambda r: -r["activityShare"])
    coverage_status = ("PASS" if coverage >= COVERAGE_PASS
                       else "WARN" if coverage >= COVERAGE_WARN else "FAIL")
    return {
        "mapId": map_id,
        "mapName": zone_map.get("mapName") or map_id,
        "source": "raster",
        "configs": [r.get("configId") for r in rasters],
        "fidelity": {str(r.get("configId")): str(r.get("fidelity") or "measured")
                     for r in rasters},
        "coverage": round(coverage, 4),
        "coverageStatus": coverage_status,
        "zoneCount": len(zone_rows),
        "deadZones": [z["zoneId"] for z in zone_rows if z["activityShare"] < DEAD_ZONE_PEAK_SHARE],
        "failing": [z["zoneId"] for z in zone_rows if z["status"] == "FAIL"],
        "zones": zone_rows,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Zone scorecard -- {report['label']}")
    lines.append("")
    lines.append(f"Evidence: **{report['source']}**. "
                 f"{report['mapCount']} maps, {report['zoneCount']} zones.")
    lines.append("")
    lines.append("Coverage is the share of measured war that lands inside SOME zone; "
                 "everything else happens on ground no zone describes. Cell-mask "
                 "zones tile the map, so they read 100% by construction -- on those "
                 "maps the number to read is the per-zone detail, not coverage.")
    lines.append("")
    fidelity = report.get("evidenceFidelity") or {}
    if fidelity:
        lines.append("**How much to trust this.** Behaviour here comes from "
                     + ", ".join(f"`{k}` ({v})" for k, v in sorted(fidelity.items()))
                     + ". A prior reconstructed from older, coarser telemetry cannot "
                     "tell a quiet zone from an unvisited one, so \"dead\" below means "
                     "*this evidence saw nothing there* -- not that the ground is dead. "
                     "Run the behaviour survey before treating those as verdicts.")
        lines.append("")
    unreadable = report.get("rolesUnknownToQuestGenerator") or {}
    if unreadable:
        zone_hits = sum(len(v) for v in unreadable.values())
        lines.append(f"**{len(unreadable)} zone roles ({zone_hits} zones) are unreadable by the quest "
                     "generator** and silently fall through to the `seize_lane` default: "
                     + ", ".join(f"`{k}`" for k in unreadable))
        lines.append("")
    lines.append("| Map | Zones | Coverage | Dead | Failing | Verdict |")
    lines.append("|---|---|---|---|---|---|")
    for entry in report["maps"]:
        lines.append("| {} | {} | {:.0%} | {} | {} | {} |".format(
            entry["mapId"], entry["zoneCount"], entry["coverage"],
            len(entry["deadZones"]), len(entry["failing"]), entry["coverageStatus"]))
    lines.append("")

    for entry in report["maps"]:
        lines.append(f"## {entry['mapName']} ({entry['mapId']})")
        lines.append("")
        if entry["source"] == "legacy":
            variant_mix = ", ".join(f"{k}x{v}" for k, v in sorted((entry.get("variants") or {}).items()))
            lines.append(f"Samples: {entry['samples']} milestone packets across "
                         f"{len(entry['runs'])} runs ({variant_mix}); frames {entry['frames']}.")
            lines.append("")
            lines.append("| Zone | Role | Share | Occupied | Contested | Hazard | Structures | Verdict |")
            lines.append("|---|---|---|---|---|---|---|---|")
            for zone in entry["zones"]:
                lines.append("| {} | {} | {:.1%} | {:.0%} | {:.2f} | {:.2f} | {:.1f} | {} |".format(
                    zone["label"], zone["role"], zone["activityShare"], zone["activeFraction"],
                    zone["contested"], zone["hazardFraction"], zone["meanStructures"], zone["status"]))
        else:
            lines.append(f"Configs: {', '.join(str(c) for c in entry.get('configs') or [])}")
            lines.append("")
            lines.append("| Zone | Role | Cells | Share | Loss | Contested | Water | Build | Anchor | Verdict |")
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            for zone in entry["zones"]:
                lines.append("| {} | {} | {} | {:.1%} | {:.1%} | {} | {:.2f} | {:.2f} | {} | {} |".format(
                    zone.get("label"), zone.get("role"), zone.get("cellCount", 0),
                    zone.get("activityShare", 0), zone.get("lossShare", 0),
                    "yes" if zone.get("contested") else "no",
                    zone.get("water", 0), zone.get("buildable", 0),
                    zone.get("anchor", "-"), zone.get("status")))
        lines.append("")
        notes = [(z["label"], v) for z in entry["zones"] for v in z.get("verdicts") or []]
        if notes:
            lines.append("Findings:")
            for label, verdict in notes:
                lines.append(f"- **{label}**: {verdict}")
            lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Score zone maps against measured evidence")
    ap.add_argument("--workspace", default=str(WS_DEFAULT))
    ap.add_argument("--zone-dir", default="")
    ap.add_argument("--source", choices=["auto", "legacy", "raster"], default="auto")
    ap.add_argument("--out", default="")
    ap.add_argument("--json", dest="json_out", default="")
    ap.add_argument("--label", default="current zones")
    ap.add_argument("--variants", default="",
                    help="comma-separated legacy variantIds to include (default: all that match the zone map)")
    args = ap.parse_args(argv)

    ws = Path(args.workspace)
    zone_dir = Path(args.zone_dir) if args.zone_dir else ws / "data" / "zone_maps" / "authored"
    zone_maps = load_zone_maps(zone_dir)
    if not zone_maps:
        print(f"No zone maps found in {zone_dir}", file=sys.stderr)
        return 2

    source = args.source
    if source == "auto":
        source = "raster" if (ws / "data" / "terrain").exists() and any(
            (ws / "data" / "terrain").glob("*.terrain.json")) else "legacy"

    entries: List[Dict[str, Any]] = []
    if source == "raster":
        for map_id, zone_map in sorted(zone_maps.items()):
            terrain = load_json(ws / "data" / "terrain" / f"{map_id}.terrain.json")
            if not terrain:
                continue
            rasters = [load_json(p) for p in sorted((ws / "data" / "behavior" / map_id).glob("*.raster.json"))] \
                if (ws / "data" / "behavior" / map_id).exists() else []
            rasters = [r for r in rasters if r]
            entries.append(score_raster_map(map_id, zone_map, terrain, rasters))
    else:
        variants = tuple(v.strip() for v in args.variants.split(",") if v.strip())
        aggregates = summarize_legacy(ws, zone_maps, variants)
        for map_id, zone_map in sorted(zone_maps.items()):
            agg = aggregates.get(map_id)
            if not agg:
                continue
            entries.append(score_legacy_map(map_id, zone_map, agg))

    if not entries:
        print("No evidence found for any zone map.", file=sys.stderr)
        return 1

    known_roles = quest_generator_roles()
    unreadable: Dict[str, List[str]] = defaultdict(list)
    if known_roles:
        for map_id, zone_map in sorted(zone_maps.items()):
            for zone in zone_map.get("zones") or []:
                role = str(zone.get("role") or "")
                if role and role not in known_roles:
                    unreadable[role].append(f"{map_id}:{zone.get('zoneId')}")

    report = {
        "schemaVersion": SCHEMA,
        "label": args.label,
        "source": source,
        "rolesUnknownToQuestGenerator": {k: v for k, v in sorted(unreadable.items())},
        "zoneDir": str(zone_dir),
        "mapCount": len(entries),
        "zoneCount": sum(e["zoneCount"] for e in entries),
        "meanCoverage": round(sum(e["coverage"] for e in entries) / len(entries), 4),
        "evidenceFidelity": {k: v for entry in entries
                             for k, v in (entry.get("fidelity") or {}).items()},
        "deadZoneCount": sum(len(e["deadZones"]) for e in entries),
        "failingZoneCount": sum(len(e["failing"]) for e in entries),
        "maps": entries,
    }

    md_path = Path(args.out) if args.out else ws / "outbox" / "zone_scorecard.latest.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path = Path(args.json_out) if args.json_out else ws / "outbox" / "zone_scorecard.latest.json"
    json_path.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(f"{report['mapCount']} maps, {report['zoneCount']} zones, source={source}")
    print(f"mean coverage {report['meanCoverage']:.1%}, "
          f"{report['deadZoneCount']} dead zones, {report['failingZoneCount']} failing")
    print(f"-> {md_path}")
    print(f"-> {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
