"""Flow walk: open the hub page map-only on a hub snapshot (hub_snapshot.py) and walk the sortie flow
(job, talks, who goes, what comes, debrief), screenshotting each screen with its visible text and word
count. Needs Playwright with Chromium. This is what the playtester agent read (2026-11-04).

    python tools/test_rig/flow_walk.py SNAPSHOT_DIR OUT_DIR
"""
import re, shutil, sys, tempfile, threading, http.server, json
from functools import partial
from pathlib import Path
from playwright.sync_api import sync_playwright
REPO = Path(__file__).resolve().parents[2]; STATE = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
tmp = Path(tempfile.mkdtemp()); shutil.copytree(REPO/"app"/"showoff", tmp, dirs_exist_ok=True)
for f in STATE.iterdir():
    if f.is_file(): shutil.copy2(f, tmp/f.name)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Q, directory=str(tmp)))
threading.Thread(target=httpd.serve_forever, daemon=True).start()
W = lambda t: len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,:%/-]*", t or ""))
rows = []
with sync_playwright() as pw:
    b = pw.chromium.launch(); pg = b.new_page(viewport={"width": 1600, "height": 1000})
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://127.0.0.1:{httpd.server_address[1]}/index.html"); pg.wait_for_timeout(2500)
    for sel in ("#coach-skip",):
        if pg.locator(sel).is_visible(): pg.click(sel)
    def shot(name, sel):
        pg.wait_for_timeout(500); pg.screenshot(path=str(OUT/f"{name}.png"))
        t = pg.locator(sel).inner_text() if pg.locator(sel).count() else ""
        rows.append((name, W(t))); (OUT/f"{name}.txt").write_text(t, encoding="utf-8")
    shot("1_job", "#app")
    pg.click("#btn-deploy"); pg.wait_for_timeout(800)
    shot("2_talks", "#drop-confirm .flow-card")
    n = 0
    while pg.locator("[data-talk-answer]").count() and n < 10:
        btns = pg.locator("[data-talk-answer]")
        # answer the first talk for real, decline the rest: both paths
        (btns.first if n == 0 else pg.locator("[data-talk-answer]", has_text="No time for this.")).click()
        pg.wait_for_timeout(400); n += 1
    rows.append(("talks answered", n)); rows.append(("button after talks", pg.locator("#drop-confirm-go").inner_text()))
    shot("2b_talks_done", "#drop-confirm .flow-card")
    pg.click("#drop-confirm-go"); pg.wait_for_timeout(600)
    shot("3_who", "#drop-confirm .flow-card")
    toggles = pg.locator("#drop-squad [data-crew]")
    rows.append(("toggleable heroes", toggles.count()))
    if toggles.count(): toggles.first.click(); pg.wait_for_timeout(400)
    rows.append(("kicker after leaving one", pg.locator("#drop-squad-kicker").inner_text()))
    pg.click("#drop-confirm-go"); pg.wait_for_timeout(600)
    shot("4_what", "#drop-confirm .flow-card")
    rows.append(("reserve rows", pg.locator(".rv-row").count()))
    plus = pg.locator("[data-rv-plus]:not([disabled])")
    if plus.count(): plus.first.click(); pg.wait_for_timeout(200)
    rows.append(("lift after +", pg.locator(".drop-reserve .drop-squad-kicker").inner_text()))
    rows.append(("last button", pg.locator("#drop-confirm-go").inner_text()))
    pg.click("#drop-confirm-cancel"); pg.wait_for_timeout(300)
    pg.evaluate("""() => window.Verdance.homecoming({verdict:'victory', chips:['zone claimed','scouted Northwest Lane'], hint:'Everyone lifted from Northwest Reserve.',
       moved: (window.HUB_STATE.lastResult && window.HUB_STATE.lastResult.debrief && window.HUB_STATE.lastResult.debrief.moved) || {standing:[{name:'Armada',before:22,after:18,delta:-4},{name:'Cortex',before:61,after:64,delta:3}], marks:[{kind:'scout',label:'Northwest Lane',done:true},{kind:'hero_recover',label:'Vane at the ford',done:false}], rescued:[], lostRescues:[], leftInField:[{name:'Odessa',mapId:'tabula',label:'West Causeway'}]},
       manifest:{kind:'extracted', mapId:'tabula', pad:'T_NW_RESERVE', destination:'camp', going:{heroes:['pavise','ketha','solarium','halbard'], units:9}, staying:{heroes:[], units:0, structures:2}}})""")
    shot("0_debrief", "#homecoming")
    rows.append(("page errors", errs[:5]))
    b.close()
httpd.shutdown()
for r in rows: print(*r)
