#!/usr/bin/env python3
"""Advance campaign from BAR result and refresh hub_state for the CYOA shell (G4).

Pipeline:
  inbox/latest_va_result.json  (from extract_latest_result.ps1)
    → story engine advance --write-state
    → build_hub_state_v1 with lastResult tokens
    → outbox/hub_result.latest.json  (delta the HTML hub can merge)

Usage:
  python tools/apply_result_to_hub_v1.py
  python tools/apply_result_to_hub_v1.py --workspace .
  python tools/apply_result_to_hub_v1.py --skip-advance   # only rebuild hub from state
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import importlib

import build_hub_state_v1 as _hub_mod  # noqa: E402


def _hub_api():
    """Reload hub builder so long-lived kernel processes pick up edits."""
    mod = importlib.reload(_hub_mod)
    return mod.build_hub, mod.load_json


build_hub, load_json = _hub_api()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_advance(ws: Path, result_path: Path) -> dict:
    engine = ws / "tools" / "verdance_story_engine_v1.py"
    cmd = [
        sys.executable,
        str(engine),
        "advance",
        "--workspace",
        str(ws),
        "--result",
        str(result_path),
        "--write-state",
    ]
    try:
        r = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True, timeout=180)
        report: dict[str, Any] = {
            "ok": r.returncode == 0,
            "returncode": r.returncode,
            "stdout_tail": (r.stdout or "")[-2500:],
            "stderr_tail": (r.stderr or "")[-800:],
        }
        # Prefer structured advance_report if written
        adv = ws / "outbox" / "advance_report.v1.json"
        if adv.is_file():
            try:
                report["advanceReport"] = json.loads(adv.read_text(encoding="utf-8-sig"))
            except Exception:  # noqa: BLE001
                pass
        return report
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def tokens_from_state_and_report(state: dict, report: dict | None) -> list[str]:
    tokens: list[str] = []
    ar = (report or {}).get("advanceReport") or report or {}
    if ar.get("resultKey"):
        tokens.append(f"resultKey={ar['resultKey']}")
    if ar.get("status") or ar.get("verdict"):
        tokens.append(f"verdict={ar.get('status') or ar.get('verdict')}")
    if ar.get("mapId"):
        tokens.append(f"mapId={ar['mapId']}")
    if ar.get("targetZoneId"):
        tokens.append(f"zone={ar['targetZoneId']}")
    if ar.get("zoneFlipped"):
        tokens.append("zoneFlipped=1")
    roster = (state.get("roster") or {}).get("heroes") or []
    for h in roster:
        if not isinstance(h, dict):
            continue
        hid = h.get("heroId")
        gain = h.get("lastSortieXpGain")
        if hid and gain:
            tokens.append(f"xp {hid}+{gain}")
        if hid and h.get("status") == "wounded":
            tokens.append(f"wound {hid}")
        if hid and h.get("status") == "dead":
            tokens.append(f"dead {hid}")
        if hid and h.get("rank"):
            tokens.append(f"rank {hid}={h.get('rank')}")
    rep = state.get("reputation") or {}
    if rep.get("nullmercs") is not None:
        tokens.append(f"rep.nullmercs={round(float(rep.get('nullmercs') or 0), 1)}")
    return tokens


def last_result_payload(state: dict, report: dict | None, plan: dict | None) -> dict:
    ar = (report or {}).get("advanceReport") or report or {}
    debrief = ar.get("debrief") if isinstance(ar.get("debrief"), dict) else None
    if not debrief:
        # Prefer credit table debrief when advance report has credit
        try:
            from match_credit_v1 import presentable_debrief, credit_from_result

            if ar.get("credit"):
                debrief = presentable_debrief(
                    ar["credit"],
                    duplicate=(ar.get("reason") == "duplicate"),
                )
            elif ar.get("resultKey") or ar.get("status") or ar.get("verdict"):
                debrief = presentable_debrief(
                    credit_from_result(
                        {
                            "status": ar.get("status") or ar.get("verdict"),
                            "terminalReason": ar.get("terminalReason"),
                            "resultKey": ar.get("resultKey"),
                            "nodeClaimed": ar.get("nodeClaimed"),
                            "zoneFlipped": ar.get("zoneFlipped"),
                        }
                    ),
                    duplicate=(ar.get("reason") == "duplicate"),
                )
        except Exception:  # noqa: BLE001
            debrief = None
    verdict = (
        (debrief or {}).get("verdict")
        or ar.get("status")
        or ar.get("verdict")
        or "unknown"
    )
    return {
        "at": _now(),
        "choiceId": (plan or {}).get("choiceId") or (plan or {}).get("hubChoiceId"),
        "mapId": ar.get("mapId") or (plan or {}).get("mapId"),
        "contractKind": (plan or {}).get("contractKind")
        or ar.get("objectiveArchetype")
        or "sortie",
        "deployAces": list((plan or {}).get("deployAces") or []),
        "deployPlan": plan,
        "verdict": verdict,
        "resultKey": ar.get("resultKey") or (debrief or {}).get("resultKey"),
        "zoneFlipped": bool(ar.get("zoneFlipped")),
        "terminalReason": ar.get("terminalReason") or (debrief or {}).get("terminalReason"),
        "reasonHint": (debrief or {}).get("reasonHint") or ar.get("reasonHint"),
        "objectiveFailed": bool(
            (debrief or {}).get("objectiveFailed")
            or ar.get("objectiveFailed")
            or ar.get("rescueContractFailed")
        ),
        "objectiveFailHero": ar.get("objectiveFailHero") or "",
        "headline": (debrief or {}).get("headline"),
        "changed": (debrief or {}).get("changed") or [],
        "nextAction": (debrief or {}).get("nextAction"),
        "duplicate": bool((debrief or {}).get("duplicate") or ar.get("reason") == "duplicate"),
        "debrief": debrief,
        "collapse": (debrief or {}).get("collapse") or ar.get("collapse"),
        "graphDelta": ar.get("graphDelta"),
        "graphMeasured": ar.get("graphMeasured"),
        "tokens": tokens_from_state_and_report(state, report),
        "source": "apply_result_to_hub_v1",
    }


def rebuild_hub(ws: Path, last_result: dict | None = None) -> dict:
    build_hub_fn, load_json_fn = _hub_api()
    state_path = ws / "state" / "campaign_state.json"
    war_path = ws / "outbox" / "war_map.json"
    if not state_path.is_file():
        return {"ok": False, "reason": "missing campaign_state"}
    state = load_json_fn(state_path)
    war = load_json_fn(war_path) if war_path.is_file() else {
        "campaignId": state.get("campaignId"),
        "missionNumber": state.get("missionNumber"),
        "regions": [],
    }
    hub = build_hub_fn(state, war)
    if last_result:
        hub["lastResult"] = last_result
        # Append a short history line for the shell
        hist = list(hub.get("history") or [])
        hist.append({
            "at": last_result.get("at"),
            "msg": (
                f"BAR result {last_result.get('verdict')} · "
                f"{last_result.get('mapId')} · "
                + ", ".join((last_result.get("tokens") or [])[:6])
            ),
        })
        hub["history"] = hist[-40:]
        # Only clobber Ketha's tactical open-node after a real BAR result.
        # state_sync / skip-advance rebuilds keep build_hub's advice (grab Tnb,
        # extract, haul home) so the companion stays useful mid-session.
        verdict = str(last_result.get("verdict") or "").lower()
        if verdict and verdict not in ("state_sync", "sync", "none"):
            map_id = last_result.get("mapId") or "the field"
            hub["node"] = dict(hub.get("node") or {})
            reason = str(last_result.get("terminalReason") or "")
            hint = str(last_result.get("reasonHint") or "").strip()
            if last_result.get("objectiveFailed") or reason == "extracted_recruit_lost":
                body = hint or "Rescue scrubbed — company came home as a hinge."
                hub["node"]["text"] = (
                    f"Back from {map_id}. {body} "
                    "Mark the next board when you're ready."
                )
            else:
                hub["node"]["text"] = (
                    f"Back from {map_id}. "
                    f"{last_result.get('verdict', 'done').title()}. "
                    "Aces updated. Mark the next board when you're ready."
                )
            hub["node"]["speaker"] = "ketha"
    hub["flags"] = hub.get("flags") or {}
    hub["flags"]["deployStub"] = False
    hub["flags"]["source"] = "apply_result_to_hub_v1"

    out_json = ws / "app" / "showoff" / "hub_state.json"
    out_embed = ws / "app" / "showoff" / "hub_state.embed.js"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(hub, indent=2) + "\n", encoding="utf-8")
    out_embed.write_text(
        "window.HUB_STATE = " + json.dumps(hub, indent=None) + ";\n",
        encoding="utf-8",
    )
    return {"ok": True, "hubPath": str(out_json), "hub": hub}


def _resolve_session_home(ws: Path, state: dict) -> str | None:
    home = state.get("sessionHomeMap") or state.get("homeMapId")
    if home:
        return str(home)
    # Outbox hint from last hub stamp
    hint = ws / "outbox" / "session_home.latest.json"
    if hint.is_file():
        try:
            data = load_json(hint)
            if data.get("sessionHomeMap"):
                return str(data["sessionHomeMap"])
        except Exception:  # noqa: BLE001
            pass
    hist = state.get("history") or []
    if hist and isinstance(hist[-1], dict) and hist[-1].get("mapId"):
        return str(hist[-1]["mapId"])
    return None


def refresh_mode_a_quests(ws: Path, state: dict) -> dict:
    """Regenerate same-map quest batch for hub open-node Mode A continues."""
    try:
        tools = ws / "tools"
        if str(tools) not in sys.path:
            sys.path.insert(0, str(tools))
        from quest_generator_v1 import generate_quests, write_quest_batch  # noqa: E402

        home = _resolve_session_home(ws, state)
        cands = generate_quests(ws, state, map_id=home, patron="nullmercs", limit=6)
        write_quest_batch(ws, cands)
        # Prefer actual map from first candidate when home was unset
        map_id = home or ((cands[0].get("mapId") if cands else None))
        return {
            "ok": True,
            "mapId": map_id,
            "count": len(cands),
            "labels": [c.get("label") or c.get("targetZoneId") for c in cands[:4]],
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def apply(ws: Path, *, skip_advance: bool = False, result_path: Path | None = None) -> dict:
    result_path = result_path or (ws / "inbox" / "latest_va_result.json")
    plan_path = ws / "outbox" / "hub_deploy_plan.latest.json"
    plan = load_json(plan_path) if plan_path.is_file() else {}

    advance_info: dict[str, Any] = {"skipped": True}
    if not skip_advance:
        if not result_path.is_file():
            return {
                "ok": False,
                "error": f"no result at {result_path}",
                "hint": "Run extract_latest_result.ps1 after a BAR sortie",
            }
        advance_info = run_advance(ws, result_path)

    state = load_json(ws / "state" / "campaign_state.json") if (
        ws / "state" / "campaign_state.json"
    ).is_file() else {}
    # Mode A: refresh quest_batch so hub paints same-map continue choices
    quest_info = refresh_mode_a_quests(ws, state)
    last = last_result_payload(state, advance_info if not advance_info.get("skipped") else None, plan)
    if advance_info.get("skipped"):
        last["verdict"] = "state_sync"
        last["tokens"] = tokens_from_state_and_report(state, None) or ["sync=state_only"]
    if quest_info.get("ok") and quest_info.get("labels"):
        last.setdefault("tokens", []).append(
            f"modeA={quest_info.get('mapId') or '?'}:{quest_info.get('count', 0)}"
        )

    hub_info = rebuild_hub(ws, last_result=last)
    hub = hub_info.get("hub") or {}

    # Presentable debrief card (protocol WP4)
    debrief = last.get("debrief") if isinstance(last.get("debrief"), dict) else {
        "verdict": last.get("verdict"),
        "headline": last.get("headline") or f"BAR result {last.get('verdict')}",
        "terminalReason": last.get("terminalReason"),
        "changed": last.get("changed") or last.get("tokens") or [],
        "nextAction": last.get("nextAction") or "mark_board",
        "resultKey": last.get("resultKey"),
        "duplicate": bool(last.get("duplicate")),
    }
    # If advance wrote advanceReport with debrief, prefer it
    ar = advance_info.get("advanceReport") if isinstance(advance_info, dict) else None
    if isinstance(ar, dict) and isinstance(ar.get("debrief"), dict):
        debrief = ar["debrief"]
        last["debrief"] = debrief
        last["headline"] = debrief.get("headline") or last.get("headline")
        last["verdict"] = debrief.get("verdict") or last.get("verdict")

    # Wallets must ride the debrief patch: the webGUI mergeHubPatch path used to
    # refresh aces/mission/rep while leaving commerce stuck on the pre-sortie bag.
    commerce = hub.get("commerce") if isinstance(hub.get("commerce"), dict) else None
    company = hub.get("company") if isinstance(hub.get("company"), dict) else None
    collapse = (
        (debrief.get("collapse") if isinstance(debrief, dict) else None)
        or last.get("collapse")
        or (ar.get("collapse") if isinstance(ar, dict) else None)
    )
    patch = {
        "schemaVersion": "verdance-hub-result/1.0",
        "at": _now(),
        "ok": bool(hub_info.get("ok")) and (advance_info.get("skipped") or advance_info.get("ok")),
        "advance": advance_info,
        "lastResult": last,
        "debrief": debrief,
        "collapse": collapse,
        "verdict": debrief.get("verdict") or last.get("verdict"),
        "headline": debrief.get("headline"),
        "resultKey": debrief.get("resultKey") or last.get("resultKey"),
        "duplicate": bool(debrief.get("duplicate")),
        "aces": hub.get("aces"),
        "missionNumber": hub.get("missionNumber"),
        "reputation": hub.get("reputation"),
        "regions": [
            {"mapId": r.get("mapId"), "control": r.get("control"), "displayName": r.get("displayName")}
            for r in (hub.get("regions") or [])
        ],
        "graph": hub.get("graph"),
        "graphPressure": hub.get("graphPressure"),
        "spectral": hub.get("spectral"),
        "node": hub.get("node"),
        # Campaign bag SoT (post settle_commerce_after_sortie).
        "tenebrium": hub.get("tenebrium"),
        "commerce": commerce,
        "factionBanks": hub.get("factionBanks"),
        "company": company,
        "homeEval": hub.get("homeEval"),
        "homeCamp": hub.get("homeCamp"),
    }
    # Paint hub node from debrief when present
    if debrief.get("headline") and not advance_info.get("skipped"):
        hub_node = dict(hub.get("node") or {})
        hub_node["text"] = (
            f"{debrief.get('headline')} "
            f"({debrief.get('terminalReason') or debrief.get('verdict') or 'done'}). "
            + (", ".join((debrief.get("changed") or [])[:4]) or "Aces updated.")
        )
        hub_node["speaker"] = "ketha"
        # Re-write hub with richer node if we rebuilt
        if hub_info.get("ok") and last:
            try:
                out_json = ws / "app" / "showoff" / "hub_state.json"
                if out_json.is_file():
                    hub2 = json.loads(out_json.read_text(encoding="utf-8-sig"))
                    hub2["node"] = hub_node
                    hub2["lastResult"] = last
                    out_json.write_text(json.dumps(hub2, indent=2) + "\n", encoding="utf-8")
                    out_embed = ws / "app" / "showoff" / "hub_state.embed.js"
                    out_embed.write_text(
                        "window.HUB_STATE = " + json.dumps(hub2, indent=None) + ";\n",
                        encoding="utf-8",
                    )
                    patch["node"] = hub_node
            except Exception:  # noqa: BLE001
                pass
    out = ws / "outbox" / "hub_result.latest.json"
    save_json(out, patch)
    return {
        "ok": patch["ok"],
        "at": patch["at"],
        "hubResultPath": str(out),
        "advance": advance_info,
        "questRefresh": quest_info,
        "lastResult": last,
        "debrief": debrief,
        "verdict": patch.get("verdict"),
        "headline": patch.get("headline"),
        "hubRebuild": {"ok": hub_info.get("ok"), "path": hub_info.get("hubPath")},
        "missionNumber": patch["missionNumber"],
        "sessionHomeMap": state.get("sessionHomeMap") or hub.get("sessionHomeMap"),
        # Post-settle wallets for advance response + mergeHubPatch clients.
        "tenebrium": patch.get("tenebrium"),
        "commerce": patch.get("commerce"),
        "company": patch.get("company"),
        "factionBanks": patch.get("factionBanks"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Advance + refresh hub from BAR result")
    ap.add_argument("--workspace", default=str(ROOT))
    ap.add_argument("--result", default="", help="Path to latest_va_result.json")
    ap.add_argument("--skip-advance", action="store_true", help="Only rebuild hub from state")
    args = ap.parse_args(argv)
    ws = Path(args.workspace).resolve()
    rp = Path(args.result) if args.result else None
    report = apply(ws, skip_advance=args.skip_advance, result_path=rp)
    print(json.dumps({k: v for k, v in report.items() if k != "hub"}, indent=2, default=str))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
