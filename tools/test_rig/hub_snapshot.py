"""Hub snapshot: play N sorties without BAR (tests/playthrough_campaign's fake results) and keep the
hub's state, with the narrative embedded, so the hub page can be opened map-only at that point.

    python tools/test_rig/hub_snapshot.py 6 /some/out/dir
    python tools/test_rig/flow_walk.py /some/out/dir /some/shots/dir
"""
import json, os, shutil, sys, time, subprocess
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests")); sys.path.insert(0, str(REPO / "tools"))
from playthrough_campaign import fresh_workspace, pick_choice, plan_for, fake_result, jload
N = int(sys.argv[1]); OUT = Path(sys.argv[2]).resolve()   # resolve: the run chdirs into a temp workspace
os.environ.setdefault("VA_PERSPECTIVES_SYNC", "1"); os.environ.setdefault("VA_PERSPECTIVES_NOSPAWN", "1")
ws = fresh_workspace(); os.chdir(ws); sys.path.insert(0, str(ws / "tools"))
env = dict(os.environ, PYTHONPATH=str(ws / "tools"))
subprocess.run([sys.executable, "-m", "verdance.campaign.engine", "init-state", "--workspace", str(ws), "--write-state"], capture_output=True, cwd=str(ws), env=env)
from verdance_kernel.api import CampaignKernel
k = CampaignKernel(ws)
sp, hp, ip = ws/"state"/"campaign_state.json", ws/"app"/"showoff"/"hub_state.json", ws/"outbox"/"next_mission_intent.json"
boards = {}
for f in (ws/"data"/"zone_maps").glob("*.json"):
    try: d = jload(f); boards[d.get("mapId") or f.stem] = d
    except Exception: pass
k.rebuild_hub(skip_apply=True); k.seal_company(band=["pavise","solarium","halbard"])
for n in range(1, N + 1):
    k.rebuild_hub(skip_apply=True); hs, st = jload(hp), jload(sp)
    choice, _ = pick_choice(hs); plan = plan_for(hs, choice, boards)
    if ip.exists(): ip.unlink()
    k.commit_deploy(plan, launch=False)
    for _ in range(240):
        if ip.is_file(): break
        time.sleep(0.25)
    intent = jload(ip)
    (ws/"inbox").mkdir(exist_ok=True)
    (ws/"inbox"/"latest_va_result.json").write_text(json.dumps(fake_result(st, intent, plan, hs, n, (jload(sp).get("roster") or {}).get("cadre") or {})))
    k.bring_home(extract=False)
    print("sortie", n, plan["mapId"], "->", jload(sp).get("missionNumber"), flush=True)
k.rebuild_hub(skip_apply=True)
# the narrative as the live kernel would serve it (with null answers), embedded for map-only viewing
hub = jload(hp); hub["narrative"] = k.narrative_surface()["narrative"]
OUT.mkdir(parents=True, exist_ok=True)
for f in (ws/"app"/"showoff").iterdir():
    if f.is_file() and f.suffix in (".json", ".js"): shutil.copy2(f, OUT/f.name)
(OUT/"hub_state.json").write_text(json.dumps(hub))
(OUT/"hub_state.embed.js").write_text("window.HUB_STATE = " + json.dumps(hub) + ";\n")
print("wrote", OUT)
