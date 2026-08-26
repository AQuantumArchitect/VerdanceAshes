#!/usr/bin/env python3
"""Strategic campaign seat — fair hub choices + kernel settle (attachments).

Loop:
  observe fair hub/dossier → PICK_CONTRACT | REST | TALK | DEPLOY | SHOP_STUB
  → kernel_sim sortie settle → attachments + world_tick

Does not read raw enemy HP or full ρ. Default brain is local heuristic;
optional --ant later.

Usage:
  python -m quantum_bar_ai.strategic_seat --workspace ../.. --sorties 10 --seeds 3
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# tools/ on path
_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import attachments_v1 as att_mod  # noqa: E402
import kernel_campaign_sim_v1 as ksim  # noqa: E402
import world_tick_v1 as wt  # noqa: E402
import verdance_story_engine_v1 as engine  # noqa: E402


ACTIONS = (
    "PICK_CONTRACT",
    "DEPLOY",
    "REST",
    "TALK",
    "SHOP_STUB",
    "ABORT_SESSION",
)


def fair_observe(state: Dict[str, Any], intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the seat is allowed to see."""
    graph = state.get("graph") or {}
    commerce = state.get("commerce") or {}
    wr = state.get("worldResponse") or {}
    dossier = att_mod.fair_dossier(state)
    card = {}
    if intent:
        obj = intent.get("objectiveTarget") if isinstance(intent.get("objectiveTarget"), dict) else {}
        card = {
            "mapId": intent.get("mapId"),
            "missionId": intent.get("missionId"),
            "objective": (obj or {}).get("kind") or intent.get("objective"),
            "targetZoneId": (obj or {}).get("targetZoneId"),
            "title": intent.get("briefingTitle") or intent.get("title"),
            "sessionMode": intent.get("sessionMode") or "same_map",
            "occupationModel": intent.get("occupationModel") or "living_shell",
            "pushbackHint": list((intent.get("worldResponse") or wr).get("pushbackEvents") or [])[:3],
        }
    # Fair scarcity / war bands only
    q7 = float(graph.get("q7_resource_scarcity") or 0.5)
    q0 = float(graph.get("q0_armada_cortex") or 0.5)
    return {
        "card": card,
        "dossier": dossier,
        "tnbBand": "empty" if commerce.get("tenebrium", 0) <= 0 else ("thin" if (commerce.get("tenebrium") or 0) < 4 else ("solid" if (commerce.get("tenebrium") or 0) < 9 else "heavy")),
        "creditsBand": "poor" if (commerce.get("credits") or 0) < 30 else "ok",
        "scarcityBand": "critical" if q7 > 0.85 else ("high" if q7 > 0.65 else "manageable"),
        "warBand": "cortex_ascendant" if q0 >= 0.6 else ("armada_stable" if q0 <= 0.4 else "contested"),
        "loanScrutiny": bool(wr.get("loanScrutiny")),
        "softContracts": bool(wr.get("softContracts")),
    }


def local_policy(obs: Dict[str, Any], rng: random.Random, *, can_deploy: bool) -> str:
    """Heuristic strategic brain — fun-biased, attachment-aware."""
    dossier = obs.get("dossier") or {}
    agents = dossier.get("agents") or {}
    vane = agents.get("vane") or {}
    ketha = agents.get("ketha") or {}
    wounds = int(vane.get("wounds") or 0) + int(ketha.get("wounds") or 0)
    dead = vane.get("status") == "dead" or ketha.get("status") == "dead"

    if dead:
        return "REST" if rng.random() < 0.5 else "TALK"

    if wounds >= 3:
        return "REST" if rng.random() < 0.7 else "TALK"

    if obs.get("scarcityBand") == "critical" and rng.random() < 0.25:
        return "SHOP_STUB"

    # Prefer talk early sometimes for attachment drama
    if rng.random() < 0.12:
        return "TALK"
    if wounds >= 1 and rng.random() < 0.3:
        return "REST"

    if can_deploy:
        return "DEPLOY"
    return "PICK_CONTRACT"


def run_seat(
    workspace: Path,
    *,
    sorties: int = 10,
    seed: int = 0,
    home_map: str = "koom_valley",
) -> Dict[str, Any]:
    """Full strategic session using kernel sim primitives."""
    rng = random.Random(seed)
    tw = ksim._seed_workspace(workspace)
    try:
        state = ksim._fresh_state(tw, home_map=home_map)
        log: List[Dict[str, Any]] = []
        deployed = 0
        strategic_actions = 0

        while deployed < sorties:
            ksim._clear_sortie_stamps(tw)
            strength = wt.player_strength(state)
            wt.power_response(state, strength)
            intent = engine.materialize_next_intent(state, tw)
            intent = wt.apply_power_to_intent(intent, state)
            obs = fair_observe(state, intent)
            action = local_policy(obs, rng, can_deploy=True)
            strategic_actions += 1

            entry: Dict[str, Any] = {
                "action": action,
                "obs": {
                    "tnbBand": obs.get("tnbBand"),
                    "scarcityBand": obs.get("scarcityBand"),
                    "warBand": obs.get("warBand"),
                    "card": obs.get("card"),
                },
            }

            if action == "ABORT_SESSION":
                entry["abort"] = True
                log.append(entry)
                break
            if action == "REST":
                entry["rest"] = att_mod.apply_rest(state, "all")
                wt.world_tick(state, hours_offline=2.0, map_id=home_map, rest=False)
                log.append(entry)
                continue
            if action == "TALK":
                who = "ketha" if rng.random() < 0.6 else "vane"
                entry["talk"] = att_mod.apply_talk_bond(state, who)
                log.append(entry)
                continue
            if action == "SHOP_STUB":
                # Fair stub: spend credits fictionally if any; no UI
                commerce = state.setdefault("commerce", {})
                credits = int(commerce.get("credits") or 0)
                if credits >= 25:
                    commerce["credits"] = credits - 15
                    commerce["tenebrium"] = int(commerce.get("tenebrium") or 0)  # no free mint
                    entry["shop"] = {"spentCredits": 15, "note": "broker listing stub"}
                else:
                    entry["shop"] = {"spentCredits": 0, "note": "too poor"}
                log.append(entry)
                continue
            if action in ("DEPLOY", "PICK_CONTRACT"):
                profile = ksim._pick_profile(rng, strength, deployed)
                # Policy bias: wounded → avoid defeat-heavy if possible by soft profile prefer
                if (obs.get("dossier") or {}).get("agents", {}).get("vane", {}).get("wounds", 0) >= 2:
                    if rng.random() < 0.4:
                        profile = rng.choice(["partial", "clean_win", "eco_raid_scavenge"])
                result = ksim.synthesize_result(
                    intent, state, profile, rng=rng, sortie_index=deployed + 1
                )
                state, report, next_intent, events = engine.process_result(
                    state, result, None, tw, None
                )
                att_delta = att_mod.update_attachments_from_result(
                    state,
                    result,
                    success=bool(result.get("success")),
                    zone_flipped=bool(report.get("zoneFlipped") or report.get("nodeClaimed")),
                )
                tick = wt.world_tick(
                    state,
                    hours_offline=0.75,
                    map_id=str(intent.get("mapId") or home_map),
                    rest=False,
                )
                entry["deploy"] = {
                    "profile": profile,
                    "status": result.get("status"),
                    "success": result.get("success"),
                    "mapId": result.get("mapId"),
                    "zoneId": result.get("targetZoneId"),
                    "nodeClaimed": result.get("nodeClaimed"),
                    "tnb": result.get("tenebriumBank"),
                    "memories": att_delta.get("memories"),
                    "pushback": (tick.get("power") or {}).get("pushbackEvents"),
                }
                log.append(entry)
                deployed += 1
                continue

            log.append(entry)

        fun_run = {
            "seed": seed,
            "history": [
                {
                    "profile": (e.get("deploy") or {}).get("profile"),
                    "success": (e.get("deploy") or {}).get("success"),
                }
                for e in log
                if e.get("deploy")
            ],
            "attachments": att_mod.fair_dossier(state),
            "pushbackEvents": list(
                ((state.get("worldResponse") or {}).get("pushbackEvents") or [])
            ),
            "contractHistogram": {},
        }
        # rebuild histogram from deploys
        for e in log:
            d = e.get("deploy") or {}
            if d.get("profile"):
                # use objective from obs if present
                pass
        score = ksim.fun_score(
            {
                "history": [
                    {
                        "profile": (e.get("deploy") or {}).get("profile") or "rest",
                        "success": (e.get("deploy") or {}).get("success", True),
                    }
                    for e in log
                    if e.get("deploy")
                ],
                "attachments": att_mod.fair_dossier(state),
                "pushbackEvents": fun_run["pushbackEvents"],
                "contractHistogram": {"seize_lane": deployed},
            }
        )
        return {
            "seed": seed,
            "deployed": deployed,
            "strategicActions": strategic_actions,
            "log": log,
            "end": {
                "tenebrium": (state.get("commerce") or {}).get("tenebrium"),
                "credits": (state.get("commerce") or {}).get("credits"),
                "missionNumber": state.get("missionNumber"),
                "strength": wt.player_strength(state),
                "q7": (state.get("graph") or {}).get("q7_resource_scarcity"),
            },
            "attachments": att_mod.fair_dossier(state),
            "fun": score,
        }
    finally:
        import shutil

        shutil.rmtree(tw, ignore_errors=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Strategic seat over kernel sim")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--sorties", type=int, default=10)
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--map", default="koom_valley", dest="home_map")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    # If cwd is tools/quantum_bar_ai, climb
    if not (ws / "state").exists() and (ws.parent.parent / "state").exists():
        ws = ws.parent.parent

    runs = []
    for i in range(max(1, args.seeds)):
        s = args.seed + i
        print(f"[strategic_seat] seed={s}", flush=True)
        r = run_seat(ws, sorties=args.sorties, seed=s, home_map=args.home_map)
        runs.append(r)
        print(
            f"  deployed={r['deployed']} fun={r['fun']['score']} "
            f"tnb={r['end'].get('tenebrium')} drama={r['fun'].get('drama')}",
            flush=True,
        )

    out = {
        "schemaVersion": "verdance-strategic-seat/1.0",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
        "meanFun": round(sum(r["fun"]["score"] for r in runs) / max(1, len(runs)), 3),
    }
    print(json.dumps({"meanFun": out["meanFun"], "seeds": len(runs)}, indent=2))

    if args.write or args.seeds > 1:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_dir = ws / "headless_runs" / f"strategic_seat_{stamp}"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "report.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        latest = ws / "outbox" / "strategic_seat.latest.json"
        slim = {
            "meanFun": out["meanFun"],
            "runDir": str(run_dir),
            "ends": [r["end"] for r in runs],
            "fun": [r["fun"] for r in runs],
            "attachmentSample": (runs[0].get("attachments") if runs else {}),
        }
        latest.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {run_dir}", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
