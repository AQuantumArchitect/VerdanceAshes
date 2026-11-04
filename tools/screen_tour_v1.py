#!/usr/bin/env python3
"""Render every screen of a toured campaign and count the words on each.

A tour comes from `autopilot_campaign_v1.py --tour` (no BAR: each sortie builds its real seed, fakes a
clean extraction and brings it home). For each sortie <tour>/NN it keeps hub_before/ (the hub as the
player opens it), seed/ (the BAR seed) and hub_after/ (the debrief). This renders:

  hub_before: the four hub tabs (operations, company, home, chronicle)   Playwright on app/showoff
  hub_after:  the operations tab (the debrief)
  seed:       the briefing, the field and the extraction screens          tools/hud_harness/render.py

and writes <out>/inventory.json and <out>/inventory.md: one row per screen with its word count, so
the UI pass cuts from a measured inventory. The field screen draws fixture people on the real
mission (the in-match rules are the harness's).

    python3 tools/screen_tour_v1.py <tour dir> [--out DIR] [--only 01,05]
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABS = ("operations", "company", "home", "chronicle")
BAR_SCREENS = {"p7_infil": "briefing", "p7_field": "field", "p7_exfil": "extraction"}


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.,:%/-]*", text or ""))


def serve(root: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: D401
            pass
    handler = partial(Quiet, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def hub_page(state_dir: Path) -> Path:
    """The repo's hub page with this moment's state and embeds laid over it."""
    tmp = Path(tempfile.mkdtemp(prefix="va_tour_hub_"))
    shutil.copytree(ROOT / "app" / "showoff", tmp, dirs_exist_ok=True)
    for f in state_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, tmp / f.name)
    return tmp


def shoot_hub(browser, state_dir: Path, out: Path, tabs) -> list[dict]:
    rows = []
    page_dir = hub_page(state_dir)
    httpd = serve(page_dir)
    try:
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{httpd.server_address[1]}/index.html")
        page.wait_for_timeout(2000)
        for tab in tabs:
            btn = page.locator(f'button[data-workspace="{tab}"]')
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(700)
            png = out / f"hub_{tab}.png"
            page.screenshot(path=str(png), full_page=True)
            text = page.evaluate("() => document.body.innerText")
            (out / f"hub_{tab}.txt").write_text(text, encoding="utf-8")
            rows.append({"screen": f"hub · {tab}", "png": str(png), "words": words(text), "errors": errors[:3]})
        page.close()
    finally:
        httpd.shutdown()
        shutil.rmtree(page_dir, ignore_errors=True)
    return rows


def shoot_bar(seed: Path, out: Path) -> list[dict]:
    env = dict(os.environ, VA_SEED_DIR=str(seed), VA_OUT=str(out))
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "hud_harness" / "render.py")], env=env,
                       capture_output=True, text=True, timeout=300)
    rows = []
    for stem, name in BAR_SCREENS.items():
        rec = out / f"{stem}.json"
        if not rec.is_file():
            rows.append({"screen": f"BAR · {name}", "error": (r.stderr or r.stdout)[-400:]})
            continue
        texts = [t[1] for t in json.loads(rec.read_text(encoding="utf-8")) if t and t[0] == "text"]
        (out / f"{stem}.txt").write_text("\n".join(texts), encoding="utf-8")
        rows.append({"screen": f"BAR · {name}", "png": str(out / f"{stem}.png"), "words": words(" ".join(texts))})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tour", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--only", default="", help="comma-separated sortie numbers")
    args = ap.parse_args()
    out_root = (args.out or args.tour / "screens").resolve()
    only = {s.strip().zfill(2) for s in args.only.split(",") if s.strip()}
    from playwright.sync_api import sync_playwright
    inventory = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for nn in sorted(p for p in args.tour.iterdir() if p.is_dir() and p.name.isdigit()):
            if only and nn.name not in only:
                continue
            out = out_root / nn.name
            out.mkdir(parents=True, exist_ok=True)
            intent = json.loads((nn / "intent.json").read_text(encoding="utf-8")) if (nn / "intent.json").is_file() else {}
            where = f"{intent.get('missionNumber') or '?'} · {intent.get('mapId') or intent.get('deploymentMapId') or ''}".strip(" ·")
            rows = []
            if (nn / "hub_before").is_dir():
                rows += shoot_hub(browser, nn / "hub_before", out, TABS)
            if (nn / "seed").is_dir() and any((nn / "seed").glob("*.lua")):
                rows += shoot_bar(nn / "seed", out)
            if (nn / "hub_after").is_dir():
                after = out / "after"
                after.mkdir(exist_ok=True)
                rows += [dict(r, screen=r["screen"].replace("hub ·", "debrief ·")) for r in shoot_hub(browser, nn / "hub_after", after, ("operations",))]
            for r in rows:
                r.update(sortie=nn.name, mission=where)
            inventory += rows
            print(nn.name, where, " ".join(f"{r['screen']}={r.get('words', 'ERR')}" for r in rows), flush=True)
        browser.close()
    (out_root / "inventory.json").write_text(json.dumps(inventory, indent=1), encoding="utf-8")
    lines = ["| sortie | mission | screen | words |", "|---|---|---|---|"]
    lines += [f"| {r['sortie']} | {r['mission']} | {r['screen']} | {r.get('words', 'error')} |" for r in inventory]
    (out_root / "inventory.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", out_root / "inventory.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
