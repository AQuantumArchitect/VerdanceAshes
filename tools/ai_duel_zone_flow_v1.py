#!/usr/bin/env python3
"""Turn AI-duel headless runs into a measured picture of how zones feed each other.

The authored zone maps were cut from a reconstructed behaviour prior
(``derivedFrom.behaviourSource == "legacy_prior"`` on all seven maps), and the
zone scorecard says so in as many words: a reconstructed prior "cannot tell a
quiet zone from an unvisited one". Adjacency on top of that is pure geometry --
``derive_zone_adjacency.py`` joins zones whose cells touch across passable
ground. Neither says anything about where armies actually go.

This reads the AI duel suite (``run_ai_duel_suite.ps1``) and answers that with
measurement:

  * which zones ever hold anything, and for which AI seat
  * which authored adjacency edges actually carry traffic ("live"), which never
    do ("inert"), and which observed crossings are not authored edges at all
    ("unauthored" -- either a real route the geometry missed, or units taking a
    path the adjacency model says does not exist)
  * the seat ladder per map: who wins, by how much, and how fast

Usage:
  python tools/ai_duel_zone_flow_v1.py --workspace .
  python tools/ai_duel_zone_flow_v1.py --suite reports/map_surveys/latest_ai_duel_suite.json
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Any:
    # Every PowerShell producer in this repo writes UTF8-with-BOM.
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def edge_key(a: str, b: str) -> str:
    return f"{a}|{b}" if a < b else f"{b}|{a}"


def load_authored_edges(workspace: Path) -> Dict[str, set]:
    path = workspace / "data" / "zone_maps" / "authored" / "zone_adjacency.json"
    if not path.exists():
        return {}
    raw = load_json(path)
    out: Dict[str, set] = {}
    for map_id, neighbours in raw.items():
        if not isinstance(neighbours, dict):
            continue
        edges = set()
        for zone, others in neighbours.items():
            for other in others or []:
                edges.add(edge_key(str(zone), str(other)))
        out[map_id] = edges
    return out


def load_zone_labels(workspace: Path, map_id: str) -> Dict[str, str]:
    path = (
        workspace
        / "data"
        / "zone_maps"
        / "authored"
        / f"{map_id}.authored.zone_map.json"
    )
    if not path.exists():
        return {}
    raw = load_json(path)
    return {
        str(z.get("zoneId")): str(z.get("label") or z.get("zoneId"))
        for z in raw.get("zones") or []
    }


def load_zone_roles(workspace: Path, map_id: str) -> Dict[str, str]:
    path = (
        workspace
        / "data"
        / "zone_maps"
        / "authored"
        / f"{map_id}.authored.zone_map.json"
    )
    if not path.exists():
        return {}
    raw = load_json(path)
    return {str(z.get("zoneId")): str(z.get("role") or "") for z in raw.get("zones") or []}


def load_zone_anchors(workspace: Path, map_id: str) -> Dict[str, Dict[str, float]]:
    """Normalized plan-view camp anchors, for plotting zones in map space."""
    path = (
        workspace
        / "data"
        / "zone_maps"
        / "authored"
        / f"{map_id}.authored.zone_map.json"
    )
    if not path.exists():
        return {}
    raw = load_json(path)
    out: Dict[str, Dict[str, float]] = {}
    for z in raw.get("zones") or []:
        zid = str(z.get("zoneId"))
        anchor = z.get("anchor") or {}
        if anchor.get("x") is not None:
            out[zid] = {"x": float(anchor["x"]), "z": float(anchor["z"])}
        else:
            b = z.get("bounds") or {}
            if b:
                out[zid] = {
                    "x": (float(b.get("xMin", 0)) + float(b.get("xMax", 1))) / 2.0,
                    "z": (float(b.get("zMin", 0)) + float(b.get("zMax", 1))) / 2.0,
                }
    return out


def team_roles_from_runs(map_runs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Team roles as declared by the run manifest, when it declares them.

    load_team_roles below infers roles from the ai_duel scenario file, which is
    only correct when an ai_duel scenario is what actually ran. A tracked human
    session runs the campaign scenario instead: same map, potentially different
    team numbering, and no ai_duel variant describing it. Reading the duel file
    anyway would silently classify the human's own team as a raptor on a map whose
    numbering happens to differ, and subtract their traffic from every corridor.

    So a run may state its own roles. When any run on the map does, that wins.
    """
    duel: List[int] = []
    raptor: List[int] = []
    saw = False
    for s in map_runs:
        dt = s.get("duelTeams")
        rt = s.get("raptorTeams")
        if dt is None and rt is None:
            continue
        saw = True
        for t in dt or []:
            if int(t) not in duel:
                duel.append(int(t))
        for t in rt or []:
            if int(t) not in raptor:
                raptor.append(int(t))
    if not saw:
        return None
    return {"duel": duel[:2], "raptor": raptor, "npc": []}


def load_team_roles(workspace: Path, map_id: str) -> Dict[str, Any]:
    """Which teams are duelling, which are wildlife, which are NPC filler.

    Two of the seven maps carry a RaptorsAI team (the_rock_jungle team 2,
    all_that_simmers team 4). The engine's own balance verdict lumps every
    non-player team into "enemy", so on those maps valueRatio measures the raptor
    swarm rather than the duel -- the first Rock Jungle run reported
    playerValue 2780 against enemyValue 270966. Raptors also roam, and accounted
    for 597 of that run's 934 border crossings. Both need separating out.
    """
    path = workspace / "data" / "scenarios" / "ai_duel" / f"{map_id}.ai_duel.json"
    if not path.exists():
        return {"duel": [], "raptor": [], "npc": []}
    raw = load_json(path)
    variants = raw.get("variants") or []
    if not variants:
        return {"duel": [], "raptor": [], "npc": []}
    ais = variants[0].get("ai") or []
    raptor = [int(a["team"]) for a in ais if str(a.get("shortName")) == "RaptorsAI"]
    non_raptor = [int(a["team"]) for a in ais if str(a.get("shortName")) != "RaptorsAI"]
    return {
        "duel": non_raptor[:2],
        "raptor": raptor,
        "npc": non_raptor[2:],
    }


def summarize_run(run: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pull the zone flow + per-milestone occupancy out of one completed run."""
    run_dir = run.get("runDir")
    if not run_dir:
        return None
    run_path = Path(run_dir)
    # Two producers, one reader. calibration_data.json is what the headless profiler
    # and the PowerShell harvester write; session.json is what the in-client recorder
    # widget writes straight from LuaUI, with no external process in the loop. The
    # packets inside are byte-identical -- the same gadget authored both -- so only
    # the wrapper differs.
    calib_path = run_path / "calibration_data.json"
    if not calib_path.exists():
        calib_path = run_path / "session.json"
    if not calib_path.exists():
        return None
    try:
        calib = load_json(calib_path)
    except Exception:
        return None

    flow = calib.get("zoneFlow") or {}
    edges: Dict[str, Dict[str, Any]] = {}
    for e in flow.get("edges") or []:
        a, b = str(e.get("from")), str(e.get("to"))
        key = edge_key(a, b)
        by_team = {int(t["team"]): int(t["crossings"]) for t in (e.get("byTeam") or [])}
        edges[key] = {
            "zones": sorted([a, b]),
            "crossings": int(e.get("crossings") or 0),
            "byTeam": by_team,
        }

    # Per-milestone zone occupancy, from the telemetry packets the profiler saved
    # alongside each milestone.
    timeline: List[Dict[str, Any]] = []
    for snap in calib.get("snapshots") or []:
        # actualFrame is the harvester's label for it; the raw gadget packet the
        # recorder widget stores verbatim calls it frame.
        frame = snap.get("actualFrame")
        if frame is None:
            frame = snap.get("frame")
        # The harvester flattens zones into a telemetryZones list. The widget stores
        # the packet untouched, where zones is an object keyed by zone id. Same
        # per-team buckets underneath either way.
        tzones = snap.get("telemetryZones")
        if not tzones:
            raw_zones = snap.get("zones")
            if isinstance(raw_zones, dict):
                tzones = list(raw_zones.values())
            else:
                tzones = []
        zones_present: Dict[str, Dict[int, float]] = {}
        for tz in tzones:
            zid = str(tz.get("zoneId") or "")
            if not zid:
                continue
            per_team = {}
            for t in tz.get("teams") or []:
                # The profiler flattens the gadget's per-zone team buckets, so
                # totalUnitValue sits directly on the team; the raw telemetry
                # packet nests it under metrics. Accept either.
                val = t.get("totalUnitValue")
                if val is None:
                    val = (t.get("metrics") or {}).get("totalUnitValue")
                val = float(val or 0.0)
                if val > 0:
                    per_team[int(t.get("teamId"))] = val
            if per_team:
                zones_present[zid] = per_team
        bal = snap.get("balance") or {}
        # Per-team totals summed from the zone buckets. This is the duel-only
        # measure: the engine's own playerValue/enemyValue folds raptors and NPC
        # filler into "enemy".
        team_values: Dict[int, float] = defaultdict(float)
        for per_team in zones_present.values():
            for team, val in per_team.items():
                team_values[team] += val
        timeline.append(
            {
                "frame": frame,
                "minutes": round((frame or 0) / 1800.0, 1),
                "verdict": bal.get("verdict"),
                "valueRatio": bal.get("valueRatio"),
                "playerValue": bal.get("playerValue"),
                "enemyValue": bal.get("enemyValue"),
                "teamValues": {int(k): round(v, 1) for k, v in team_values.items()},
                "zones": zones_present,
            }
        )

    return {
        "id": run.get("id"),
        "mapId": run.get("mapId"),
        "mapTitle": run.get("mapTitle"),
        "variant": run.get("variant"),
        "seatA": run.get("seatA"),
        "seatB": run.get("seatB"),
        "seatALabel": run.get("seatALabel"),
        "seatBLabel": run.get("seatBLabel"),
        "playerTeamID": run.get("playerTeamID", 0),
        # Optional, manifest-declared. Present on tracked human sessions, absent on
        # the AI duel runs (which fall back to reading the ai_duel scenario).
        "seatKind": run.get("seatKind"),
        "duelTeams": run.get("duelTeams"),
        "raptorTeams": run.get("raptorTeams"),
        "lastVerdict": run.get("lastVerdict"),
        "lastRatio": run.get("lastRatio"),
        "elapsedSeconds": run.get("elapsedSeconds"),
        "flowSampleEvery": flow.get("sampleEvery"),
        "edges": edges,
        "timeline": timeline,
    }


def analyze(workspace: Path, suite_path: Path) -> Dict[str, Any]:
    suite = load_json(suite_path)
    authored = load_authored_edges(workspace)

    runs = [
        r
        for r in (suite.get("results") or [])
        if str(r.get("status")) == "completed"
    ]
    summaries = [s for s in (summarize_run(r) for r in runs) if s]

    by_map: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in summaries:
        by_map[str(s["mapId"])].append(s)

    maps_out: Dict[str, Any] = {}
    for map_id, map_runs in sorted(by_map.items()):
        labels = load_zone_labels(workspace, map_id)
        roles = load_zone_roles(workspace, map_id)
        team_roles = team_roles_from_runs(map_runs) or load_team_roles(workspace, map_id)
        raptor_teams = set(team_roles["raptor"])
        duel_teams = list(team_roles["duel"])
        all_zones = set(labels)
        raptor_crossings = 0

        edge_totals: Dict[str, int] = defaultdict(int)
        edge_runs: Dict[str, int] = defaultdict(int)
        edge_by_team: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        zone_peak: Dict[str, float] = defaultdict(float)
        zone_peak_team: Dict[str, int] = {}
        zone_runs_seen: Dict[str, int] = defaultdict(int)

        for s in map_runs:
            for key, e in s["edges"].items():
                by_team = {int(k): int(v) for k, v in (e.get("byTeam") or {}).items()}
                # Raptors roam the whole map and would otherwise dominate the
                # traffic picture on the two maps that have them.
                duel_only = sum(n for t, n in by_team.items() if t not in raptor_teams)
                raptor_crossings += sum(n for t, n in by_team.items() if t in raptor_teams)
                if duel_only <= 0:
                    continue
                edge_totals[key] += duel_only
                edge_runs[key] += 1
                for team, n in by_team.items():
                    if team not in raptor_teams:
                        edge_by_team[key][team] += n
            seen_this_run = set()
            for step in s["timeline"]:
                for zid, per_team in (step.get("zones") or {}).items():
                    total = sum(per_team.values())
                    if total > zone_peak[zid]:
                        zone_peak[zid] = total
                        # Whoever held the most value at the peak owns the zone
                        # visually; ties fall to the lower team id.
                        zone_peak_team[zid] = max(
                            sorted(per_team), key=lambda t: per_team[t]
                        )
                    seen_this_run.add(zid)
            for zid in seen_this_run:
                zone_runs_seen[zid] += 1

        authored_edges = authored.get(map_id, set())
        measured_edges = set(edge_totals)
        # Total orders, not partial. Ties previously fell through to set
        # iteration order, which Python randomizes per process, so two runs of
        # this tool over identical inputs emitted different -- and undiffable --
        # reports. The numbers never moved; only the rows did.
        live = sorted(authored_edges & measured_edges, key=lambda k: (-edge_totals[k], k))
        inert = sorted(authored_edges - measured_edges)
        unauthored = sorted(measured_edges - authored_edges, key=lambda k: (-edge_totals[k], k))

        occupied = {z for z in all_zones if zone_peak.get(z, 0) > 0}
        touched = occupied | {
            z for key in measured_edges for z in key.split("|")
        }
        dead = sorted(all_zones - touched)

        # Seat ladder: for each run, seat A is the reported "player" side.
        seat_records: Dict[str, List[float]] = defaultdict(list)
        matchups = []
        for s in map_runs:
            # Prefer the duel-only ratio (team A value over team B value, summed
            # from the zone buckets) over the engine's playerValue/enemyValue,
            # which counts raptors and NPC filler as "enemy".
            duel_ratio = None
            if len(duel_teams) == 2 and s["timeline"]:
                tv = (s["timeline"][-1].get("teamValues") or {})
                a_val = float(tv.get(duel_teams[0], 0.0))
                b_val = float(tv.get(duel_teams[1], 0.0))
                if b_val > 0:
                    duel_ratio = a_val / b_val
                elif a_val > 0:
                    duel_ratio = 999.0
            ratio = duel_ratio if duel_ratio is not None else s.get("lastRatio")
            if ratio is None:
                continue
            ratio = float(ratio)
            matchups.append(
                {
                    "seatA": s["seatA"],
                    "seatB": s["seatB"],
                    "seatALabel": s["seatALabel"],
                    "seatBLabel": s["seatBLabel"],
                    "valueRatio": round(ratio, 3),
                    "engineRatio": s.get("lastRatio"),
                    "ratioSource": "duel_only" if duel_ratio is not None else "engine",
                    "verdict": s["lastVerdict"],
                    # In a mirror the two seat labels are identical, so naming the
                    # seat says nothing. Name the side instead -- which is the
                    # whole point of a mirror: it isolates start position.
                    "mirror": s["seatA"] == s["seatB"],
                    "winner": (
                        "tie"
                        if 0.9 <= ratio <= 1.1
                        else (
                            ("team 0 (A side)" if ratio > 1.1 else "team 1 (B side)")
                            if s["seatA"] == s["seatB"]
                            else (s["seatALabel"] if ratio > 1.1 else s["seatBLabel"])
                        )
                    ),
                }
            )
            if s["seatA"] != s["seatB"]:
                seat_records[s["seatA"]].append(ratio)
                # The mirror view for seat B is the reciprocal of A-over-B.
                seat_records[s["seatB"]].append(1.0 / ratio if ratio else 0.0)

        ladder = sorted(
            (
                {
                    "seat": seat,
                    "meanRatio": round(sum(v) / len(v), 3),
                    "samples": len(v),
                }
                for seat, v in seat_records.items()
            ),
            key=lambda r: (-r["meanRatio"], r["seat"]),
        )

        maps_out[map_id] = {
            "mapTitle": map_runs[0]["mapTitle"],
            "runCount": len(map_runs),
            "zoneCount": len(all_zones),
            "authoredEdgeCount": len(authored_edges),
            "duelTeams": duel_teams,
            "raptorTeams": sorted(raptor_teams),
            "raptorCrossingsExcluded": raptor_crossings,
            "liveEdges": [
                {
                    "zones": key.split("|"),
                    "labels": [labels.get(z, z) for z in key.split("|")],
                    "crossings": edge_totals[key],
                    "runs": edge_runs[key],
                    "byTeam": dict(edge_by_team[key]),
                }
                for key in live
            ],
            "inertEdges": [
                {"zones": key.split("|"), "labels": [labels.get(z, z) for z in key.split("|")]}
                for key in inert
            ],
            "unauthoredEdges": [
                {
                    "zones": key.split("|"),
                    "labels": [labels.get(z, z) for z in key.split("|")],
                    "crossings": edge_totals[key],
                    "runs": edge_runs[key],
                    "byTeam": dict(edge_by_team[key]),
                }
                for key in unauthored
            ],
            "deadZones": [{"zoneId": z, "label": labels.get(z, z), "role": roles.get(z, "")} for z in dead],
            "anchors": load_zone_anchors(workspace, map_id),
            "zonePeaks": [
                {
                    "zoneId": z,
                    "label": labels.get(z, z),
                    "role": roles.get(z, ""),
                    "peakValue": round(zone_peak[z], 1),
                    "peakTeam": zone_peak_team.get(z),
                    "runsSeen": zone_runs_seen.get(z, 0),
                }
                for z in sorted(all_zones, key=lambda z: (-zone_peak.get(z, 0), z))
            ],
            "matchups": matchups,
            "seatLadder": ladder,
        }

    # Cross-map seat ladder.
    global_seat: Dict[str, List[float]] = defaultdict(list)
    for m in maps_out.values():
        for row in m["seatLadder"]:
            global_seat[row["seat"]].extend([row["meanRatio"]] * row["samples"])

    return {
        "schemaVersion": "verdance-ai-duel-zone-flow/0.1",
        "suitePath": str(suite_path),
        "suiteStatus": suite.get("status"),
        "suiteSource": suite.get("source"),
        "seatKinds": sorted({str(s.get("seatKind")) for s in summaries if s.get("seatKind")}),
        "runsAnalyzed": len(summaries),
        "maps": maps_out,
        "seatLadder": sorted(
            (
                {"seat": s, "meanRatio": round(sum(v) / len(v), 3), "samples": len(v)}
                for s, v in global_seat.items()
            ),
            key=lambda r: (-r["meanRatio"], r["seat"]),
        ),
    }


def render_markdown(report: Dict[str, Any]) -> str:
    out: List[str] = []
    add = out.append
    # The same analyser now serves two suites. Saying "AI Duel" over a page of
    # human sessions is the kind of stale header that gets believed later.
    human = ("human" in (report.get("seatKinds") or [])
             or report.get("suiteSource") == "in_client_recorder")
    add("# Tracked play: measured zone flow" if human else "# AI Duel: measured zone flow")
    add("")
    add(
        f"Runs analyzed: **{report['runsAnalyzed']}**  |  suite status: "
        f"`{report.get('suiteStatus')}`"
    )
    add("")
    add(
        "Authored adjacency is geometric -- two zones are neighbours when their "
        "cells touch across passable ground. This compares that against where "
        "units actually crossed."
    )
    add("")

    if report.get("seatLadder"):
        add("## Seat ladder (all maps)")
        add("")
        add("| Seat | Mean value ratio (own side / opponent) | Samples |")
        add("| --- | ---: | ---: |")
        for row in report["seatLadder"]:
            add(f"| `{row['seat']}` | {row['meanRatio']} | {row['samples']} |")
        add("")

    for map_id, m in report["maps"].items():
        add(f"## {m['mapTitle']} (`{map_id}`)")
        add("")
        add(
            f"{m['runCount']} run(s) | {m['zoneCount']} zones | "
            f"{m['authoredEdgeCount']} authored edges | "
            f"{len(m['liveEdges'])} live, {len(m['inertEdges'])} inert, "
            f"{len(m['unauthoredEdges'])} unauthored"
        )
        add("")

        if m["matchups"]:
            add("### Matchups")
            add("")
            add("| Seat A | Seat B | Value ratio A/B | Verdict | Winner |")
            add("| --- | --- | ---: | --- | --- |")
            for mu in m["matchups"]:
                add(
                    f"| {mu['seatALabel']} | {mu['seatBLabel']} | {mu['valueRatio']} "
                    f"| {mu['verdict']} | {mu['winner']} |"
                )
            add("")

        if m["liveEdges"]:
            add("### Live corridors (authored and used)")
            add("")
            add("| From | To | Crossings | Runs |")
            add("| --- | --- | ---: | ---: |")
            for e in m["liveEdges"][:15]:
                add(f"| {e['labels'][0]} | {e['labels'][1]} | {e['crossings']} | {e['runs']} |")
            add("")

        if m["unauthoredEdges"]:
            add("### Unauthored crossings (units moved where adjacency says they cannot)")
            add("")
            add("| From | To | Crossings | Runs |")
            add("| --- | --- | ---: | ---: |")
            for e in m["unauthoredEdges"][:15]:
                add(f"| {e['labels'][0]} | {e['labels'][1]} | {e['crossings']} | {e['runs']} |")
            add("")

        if m["inertEdges"]:
            add("### Inert corridors (authored, never used)")
            add("")
            add(
                ", ".join(f"{e['labels'][0]} <-> {e['labels'][1]}" for e in m["inertEdges"][:20])
            )
            add("")

        if m["deadZones"]:
            add("### Dead zones (no unit ever entered)")
            add("")
            add(", ".join(f"{z['label']} (`{z['role']}`)" for z in m["deadZones"]))
            add("")

        never_held = [z for z in m["zonePeaks"] if z["peakValue"] <= 0]
        if never_held:
            add(
                f"### Never held ({len(never_held)} of {m['zoneCount']}) "
                "-- crossed or empty, but never occupied"
            )
            add("")
            add(", ".join(f"{z['label']} (`{z['role']}`)" for z in never_held))
            add("")

        add("### Zone peaks")
        add("")
        add("| Zone | Role | Peak unit value | Runs seen |")
        add("| --- | --- | ---: | ---: |")
        for z in m["zonePeaks"][:15]:
            add(f"| {z['label']} | {z['role']} | {z['peakValue']} | {z['runsSeen']} |")
        add("")

    return "\n".join(out) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze AI duel zone flow")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--suite", default="")
    ap.add_argument("--out-json", default="")
    ap.add_argument("--out-md", default="")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    suite_path = (
        Path(args.suite).resolve()
        if args.suite
        else ws / "reports" / "map_surveys" / "latest_ai_duel_suite.json"
    )
    if not suite_path.exists():
        print(f"No suite manifest at {suite_path}", file=sys.stderr)
        return 2

    report = analyze(ws, suite_path)

    out_json = Path(args.out_json) if args.out_json else ws / "reports" / "ai_duel_zone_flow.latest.json"
    out_md = Path(args.out_md) if args.out_md else ws / "reports" / "ai_duel_zone_flow.latest.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    with io.open(out_md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))

    print(f"Analyzed {report['runsAnalyzed']} run(s) across {len(report['maps'])} map(s).")
    for row in report.get("seatLadder") or []:
        print(f"  {row['seat']:<16} meanRatio={row['meanRatio']} n={row['samples']}")
    print(f"JSON: {out_json}")
    print(f"MD:   {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
