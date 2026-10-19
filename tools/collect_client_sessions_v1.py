#!/usr/bin/env python3
"""Collect sessions the in-client recorder widget wrote, into an analysable suite.

gui_verdance_playtest_recorder.lua writes one JSON file per tracked session into
the BAR write directory (LuaUI/Config/verdance/). Those files hold the same
packets the headless AI runs produced -- the synced gadget authored both -- so
once they are copied into a run directory and listed in a suite manifest,
ai_duel_zone_flow_v1.py reads them with no special casing.

This is the whole post-session pipeline for the in-client path: no infolog
parsing, no PowerShell, nothing that has to run while BAR is closing.

  python tools/collect_client_sessions_v1.py            # collect + report
  python tools/collect_client_sessions_v1.py --list     # show what is there
"""
from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Any:
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def bar_data_root(workspace: Path) -> Path:
    cfg_path = workspace / "verdance_config.json"
    if cfg_path.exists():
        cfg = load_json(cfg_path)
        root = cfg.get("barDataRoot")
        if root:
            return Path(root)
    raise SystemExit(f"No barDataRoot in {cfg_path}")


def map_name_index(workspace: Path) -> Dict[str, Dict[str, str]]:
    """BAR's map name -> the campaign's map id.

    The widget only knows Game.mapName ("Greenest Fields 1.3"); every analyser
    lookup (zone labels, roles, anchors, adjacency) is keyed on the campaign id
    ("greenest_fields"). The pool file is the one place both appear together.
    """
    pool = load_json(workspace / "data" / "map_pool" / "seven_maps.json")
    out: Dict[str, Dict[str, str]] = {}
    for m in pool.get("maps") or []:
        entry = {"id": str(m.get("id")), "title": str(m.get("title") or m.get("id"))}
        name = str(m.get("mapName") or "")
        if name:
            out[name.lower()] = entry
        # Also index the bare name, so a map that gets a version bump under the
        # player's feet still resolves rather than silently dropping the session.
        stem = name.split(" v")[0].strip().lower()
        if stem:
            out.setdefault(stem, entry)
    return out


def resolve_map(map_name: str, index: Dict[str, Dict[str, str]]) -> Optional[Dict[str, str]]:
    key = (map_name or "").strip().lower()
    if not key:
        return None
    if key in index:
        return index[key]
    # Longest matching prefix: "Greenest Fields 1.4" against a pool that knows 1.3.
    best = None
    for name, entry in index.items():
        if key.startswith(name) or name.startswith(key):
            if best is None or len(name) > len(best[0]):
                best = (name, entry)
    return best[1] if best else None


def scenario_ai_teams(workspace: Path) -> Optional[Dict[str, List[int]]]:
    """Raptor and non-raptor AI teams, from the scenario the campaign actually built.

    The telemetry packet is not a usable source for this: its per-team `side` is the
    faction ("armada"), and on the_rock_jungle the raptor team's side reads 'Armada'
    like any other. Only the scenario names RaptorsAI, so only the scenario can say
    which team is wildlife.
    """
    path = workspace / "data" / "scenarios" / "generated" / "next_mission_intent.playable.json"
    if not path.exists():
        return None
    try:
        raw = load_json(path)
    except Exception:  # noqa: BLE001
        return None
    variants = raw.get("variants") or []
    if not variants:
        return None
    ais = variants[0].get("ai") or []
    raptors, others = [], []
    for a in ais:
        try:
            tid = int(a.get("team"))
        except (TypeError, ValueError):
            continue
        if str(a.get("shortName")) == "RaptorsAI":
            raptors.append(tid)
        else:
            others.append(tid)
    return {"raptor": sorted(raptors), "other": sorted(others)}


def team_roles(workspace: Path, session: Dict[str, Any], player_team: int) -> Dict[str, Any]:
    """Who the player was actually fighting, and what to discount as wildlife.

    The AI-duel analysis subtracts raptor traffic and raptor value, because on those
    maps raptors were ambient wildlife roaming across a duel between two AI seats,
    and counting them made a Rock Jungle run read playerValue 2780 against
    enemyValue 270966.

    That reasoning inverts in the campaign. Mission 1 is a contract against a raptor
    hive: team 1 is RaptorsAI and there is no other opponent. Subtracting raptors
    there would delete the entire opposition and report the player as unopposed.

    So: raptors are discounted only when somebody else is also fighting.
    """
    info = scenario_ai_teams(workspace)
    raptors = list(info["raptor"]) if info else []
    others = [t for t in (info["other"] if info else []) if t != player_team]

    if others:
        return {
            "duel": [player_team, others[0]],
            "raptor": raptors,
            "note": "raptors discounted as wildlife",
        }
    if raptors:
        return {
            "duel": [player_team, raptors[0]],
            "raptor": [],
            "note": "raptors ARE the opposition; counted, not discounted",
        }
    # No scenario to read, or a scenario with no AI at all. Fall back to whatever
    # non-player teams held value, and discount nothing.
    seen: List[int] = []
    snaps = session.get("snapshots") or []
    if snaps:
        for bucket in snaps[-1].get("teams") or []:
            try:
                tid = int(bucket.get("teamId"))
            except (TypeError, ValueError):
                continue
            if tid != player_team and tid not in seen:
                seen.append(tid)
    duel = [player_team] + (sorted(seen)[:1] if seen else [])
    return {"duel": duel, "raptor": [], "note": "inferred from telemetry; no scenario found"}


def collect(workspace: Path, list_only: bool = False) -> int:
    src_dir = bar_data_root(workspace) / "LuaUI" / "Config" / "verdance"
    if not src_dir.is_dir():
        print(f"No client sessions yet ({src_dir} does not exist).")
        print("Play a mission with tracking armed first.")
        return 1

    files = sorted(src_dir.glob("session_*.json"))
    if not files:
        print(f"No session files in {src_dir}.")
        return 1

    index = map_name_index(workspace)
    runs_root = workspace / "human_runs"
    results: List[Dict[str, Any]] = []
    skipped: List[str] = []

    for f in files:
        try:
            session = load_json(f)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{f.name}: unreadable ({type(exc).__name__})")
            continue

        snaps = session.get("snapshots") or []
        flow = session.get("zoneFlow") or {}
        edges = flow.get("edges") or []
        map_name = str(session.get("mapName") or "")
        resolved = resolve_map(map_name, index)
        player_team = int(session.get("playerTeamID") or 0)
        result = session.get("result") or {}
        verdict = str(result.get("status") or "abandoned")
        frames = session.get("lastFrame") or 0

        if list_only:
            print(f"{f.name}: map={map_name!r} snapshots={len(snaps)} "
                  f"edges={len(edges)} verdict={verdict}")
            continue

        # A session with no crossings measures nothing; listing it would make the
        # analyser report every corridor on the map inert.
        if not edges:
            skipped.append(f"{f.name}: no zone-flow edges (session too short?)")
            continue
        if not snaps:
            skipped.append(f"{f.name}: no occupancy snapshots")
            continue
        if not resolved:
            skipped.append(f"{f.name}: map {map_name!r} is not in the seven-map pool")
            continue

        run_dir = runs_root / f.stem
        run_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, run_dir / "session.json")

        roles = team_roles(workspace, session, player_team)
        last_balance = (snaps[-1].get("balance") or {})
        results.append({
            "status": "completed",
            "runDir": str(run_dir),
            "id": f"{resolved['id']}::{f.stem}",
            "mapId": resolved["id"],
            "mapTitle": resolved["title"],
            "variant": "alpha_player",
            "seatA": "human",
            "seatB": "campaign_ai",
            "seatALabel": "Human",
            "seatBLabel": "campaign_ai",
            "seatKind": "human",
            "playerTeamID": player_team,
            "duelTeams": roles["duel"],
            "raptorTeams": roles["raptor"],
            "lastVerdict": verdict,
            "lastRatio": last_balance.get("valueRatio"),
            "elapsedSeconds": int(frames / 30),
            "sourceFile": str(f),
            "teamRoleNote": roles.get("note"),
        })

    if list_only:
        return 0

    for note in skipped:
        print(f"  skipped {note}")

    if not results:
        print("Nothing collectable yet.")
        return 1

    suite_path = workspace / "reports" / "map_surveys" / "latest_human_suite.json"
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(suite_path, "w", encoding="utf-8") as fh:
        json.dump({
            "schemaVersion": "verdance-human-suite/0.1",
            "status": "completed",
            "source": "in_client_recorder",
            "results": results,
        }, fh, indent=2)

    print(f"Collected {len(results)} session(s) -> {suite_path}")
    for r in results:
        print(f"  {r['mapTitle']:<22} {r['lastVerdict']:<10} "
              f"{r['elapsedSeconds'] // 60}m  team {r['playerTeamID']} "
              f"vs {r['duelTeams'][1] if len(r['duelTeams']) > 1 else '?'}")
        # This choice changes every ratio in the report, so it is stated, not buried.
        print(f"      {r['teamRoleNote']}")
    return 0


def analyse(workspace: Path) -> int:
    suite = workspace / "reports" / "map_surveys" / "latest_human_suite.json"
    if not suite.exists():
        return 1
    cmd = [
        sys.executable, str(workspace / "tools" / "ai_duel_zone_flow_v1.py"),
        "--workspace", str(workspace),
        "--suite", str(suite),
        "--out-json", str(workspace / "reports" / "human_zone_flow.latest.json"),
        "--out-md", str(workspace / "reports" / "human_zone_flow.latest.md"),
    ]
    return subprocess.call(cmd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--list", action="store_true", help="show sessions without collecting")
    ap.add_argument("--no-analyse", action="store_true")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()

    rc = collect(ws, list_only=args.list)
    if rc != 0 or args.list or args.no_analyse:
        return rc
    return analyse(ws)


if __name__ == "__main__":
    raise SystemExit(main())
