"""Cinematic friend-demo hearth for the Verdance campaign story.

Writes app/showoff/ (and mirrors into app/story/latest/show.html)
so anyone can open a self-playing gallery without installing BAR.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .suite import _workspace_root


def build_show_html(story: dict[str, Any], *, art_rel: dict[str, str] | None = None) -> str:
    """Full cinematic autoplay page. art_rel maps keys -> relative image paths."""
    art_rel = art_rel or {}
    payload = {
        "title": story.get("title") or "Verdance's Ashes",
        "tagline": story.get("tagline")
        or "A mind that commits under fog - and walks the campaign home.",
        "arc_blurb": story.get("arc_blurb") or "",
        "agent": story.get("agent"),
        "billing": story.get("billing"),
        "cleared": story.get("cleared"),
        "hard_wins": story.get("hard_wins"),
        "missions": story.get("missions"),
        "seed": story.get("seed"),
        "difficulty": story.get("difficulty"),
        "arcs": story.get("arcs") or [],
        "chapters": [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "map_name": c.get("map_name"),
                "kind": c.get("kind"),
                "verdict": c.get("verdict"),
                "won": c.get("won"),
                "verdict_line": (c.get("verdict_line") or "").replace("**", ""),
                "situation": (c.get("narrative_open") or [None])[0],
                "briefing": c.get("briefing_lines") or [],
                "beats": (c.get("beats") or [])[:6],
            }
            for c in (story.get("chapters") or [])
        ],
        "barks": story.get("barks") or [],
        "art": art_rel,
    }
    data_json = json.dumps(payload, ensure_ascii=False)
    # escape for script tag
    data_json = data_json.replace("</", "<\\/")

    poster = art_rel.get("poster", "")
    scars = art_rel.get("scars", "")
    graph = art_rel.get("graph", "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<meta name="theme-color" content="#070e0b"/>
<title>Verdance's Ashes - Live Demo</title>
<style>
:root {{
  --bg:#050a08; --ink:#eef6ee; --muted:#7d9584; --edge:#3d8f55;
  --gold:#d4c49a; --steam:#7ec8ff; --panel:rgba(12,24,18,.82);
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; height:100%; background:var(--bg); color:var(--ink);
  font-family:"Segoe UI",system-ui,sans-serif; overflow:hidden; }}
.stage {{ position:relative; width:100%; height:100%; overflow:hidden; }}
.bg {{
  position:absolute; inset:0; background-size:cover; background-position:center;
  filter:saturate(1.05) brightness(.55); transform:scale(1.08);
  transition: background-image .8s ease, filter .6s ease;
}}
.bg::after {{
  content:""; position:absolute; inset:0;
  background: linear-gradient(180deg, rgba(5,10,8,.35) 0%, rgba(5,10,8,.55) 40%, rgba(5,10,8,.92) 100%),
              radial-gradient(ellipse at 50% 20%, rgba(61,143,85,.18), transparent 55%);
}}
.vignette {{
  position:absolute; inset:0; pointer-events:none;
  box-shadow: inset 0 0 120px 40px rgba(0,0,0,.65);
}}
.hud {{
  position:absolute; left:0; right:0; top:0; padding:1.1rem 1.4rem;
  display:flex; justify-content:space-between; align-items:flex-start;
  z-index:5; gap:1rem;
}}
.brand {{ font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; color:var(--steam); }}
.brand strong {{ display:block; font-size:1.05rem; letter-spacing:.04em; color:var(--gold);
  text-transform:none; margin-top:.2rem; font-weight:600; }}
.badges {{ display:flex; flex-wrap:wrap; gap:.35rem; justify-content:flex-end; }}
.badge {{
  font-size:.65rem; letter-spacing:.08em; text-transform:uppercase;
  padding:.22rem .55rem; border-radius:999px;
  border:1px solid rgba(61,143,85,.4); color:var(--edge);
  background:rgba(0,0,0,.35); backdrop-filter:blur(6px);
}}
.badge.gold {{ color:var(--gold); border-color:rgba(212,196,154,.35); }}
.badge.steam {{ color:var(--steam); border-color:rgba(126,200,255,.35); }}
.badge.good {{ color:#7dff8a; border-color:rgba(125,255,138,.35); }}

.center {{
  position:absolute; left:50%; top:42%; transform:translate(-50%,-50%);
  width:min(46rem, 92vw); text-align:center; z-index:4;
  transition: opacity .45s ease, transform .45s ease;
}}
.center.swap {{ opacity:0; transform:translate(-50%,-46%); }}
.kicker {{ color:var(--steam); letter-spacing:.16em; text-transform:uppercase;
  font-size:.72rem; margin-bottom:.6rem; }}
h1 {{
  margin:0; font-weight:600; color:var(--gold);
  font-size:clamp(1.6rem, 4.2vw, 2.6rem); line-height:1.15;
  text-shadow:0 8px 40px rgba(0,0,0,.6);
}}
.sub {{ color:var(--muted); margin:.7rem auto 0; max-width:34rem; font-size:.95rem; }}
.voice {{
  margin:1.1rem auto 0; max-width:32rem; font-style:italic; color:var(--gold);
  border-left:3px solid var(--edge); padding:.55rem .9rem; text-align:left;
  background:rgba(0,0,0,.28); border-radius:0 10px 10px 0;
}}
.beats {{
  margin:1rem auto 0; max-width:36rem; text-align:left; font-size:.82rem;
  color:var(--ink); opacity:.9;
}}
.beats div {{ margin:.28rem 0; padding-left:.4rem; border-left:2px solid rgba(61,143,85,.35); }}

.bottom {{
  position:absolute; left:0; right:0; bottom:0; z-index:6;
  padding:0 1.2rem 1.1rem;
}}
.progress {{
  height:3px; background:rgba(255,255,255,.08); border-radius:99px; overflow:hidden;
  margin-bottom:.75rem;
}}
.progress > i {{
  display:block; height:100%; width:0%; background:linear-gradient(90deg, var(--edge), var(--steam));
  transition: width .2s linear;
}}
.rail {{
  display:flex; gap:.35rem; overflow-x:auto; padding-bottom:.35rem;
  scrollbar-width:none;
}}
.rail::-webkit-scrollbar {{ display:none; }}
.dot {{
  flex:0 0 auto; width:10px; height:10px; border-radius:50%;
  background:rgba(255,255,255,.18); border:0; cursor:pointer; padding:0;
}}
.dot.won {{ background:#5fd86a; box-shadow:0 0 8px rgba(95,216,106,.45); }}
.dot.active {{ transform:scale(1.35); outline:2px solid var(--gold); outline-offset:2px; }}

.controls {{
  position:absolute; right:1.1rem; bottom:3.2rem; z-index:7;
  display:flex; gap:.4rem;
}}
.controls button {{
  background:rgba(0,0,0,.45); border:1px solid rgba(61,143,85,.4);
  color:var(--ink); border-radius:8px; padding:.4rem .7rem; cursor:pointer;
  font-size:.75rem; backdrop-filter:blur(6px);
}}
.controls button:hover {{ border-color:var(--gold); color:var(--gold); }}

.intro {{
  position:absolute; inset:0; z-index:10; display:flex; align-items:center; justify-content:center;
  background:radial-gradient(ellipse at center, #0f2418 0%, #050a08 70%);
  transition: opacity .8s ease;
}}
.intro.hide {{ opacity:0; pointer-events:none; }}
.intro-card {{
  text-align:center; max-width:36rem; padding:2rem 1.5rem;
}}
.intro-card img {{
  width:min(520px, 86vw); border-radius:14px; border:1px solid rgba(61,143,85,.35);
  box-shadow:0 20px 60px rgba(0,0,0,.55); margin-bottom:1.2rem;
}}
.intro-card h1 {{ font-size:clamp(1.5rem, 3.5vw, 2.2rem); color:var(--gold); margin:0 0 .4rem; }}
.intro-card p {{ color:var(--muted); margin:0 auto 1.2rem; max-width:28rem; }}
.intro-card button {{
  background:linear-gradient(135deg, #2d6b42, #1a3f2a); border:1px solid var(--edge);
  color:var(--ink); font-size:1rem; padding:.75rem 1.6rem; border-radius:999px;
  cursor:pointer; letter-spacing:.04em;
}}
.intro-card button:hover {{ filter:brightness(1.12); }}
.score {{
  display:grid; grid-template-columns:repeat(3,1fr); gap:.5rem; margin:1rem 0 1.2rem;
}}
.score div {{
  background:rgba(0,0,0,.35); border:1px solid rgba(61,143,85,.3); border-radius:10px;
  padding:.55rem .3rem; font-size:.72rem; color:var(--muted);
}}
.score strong {{ display:block; color:var(--edge); font-size:1.05rem; margin-top:.15rem; }}

.bark {{
  position:absolute; left:50%; bottom:4.6rem; transform:translateX(-50%);
  width:min(36rem, 90vw); z-index:5; text-align:center;
  background:rgba(6,14,10,.8); border:1px solid rgba(126,200,255,.25);
  border-radius:12px; padding:.55rem .9rem; backdrop-filter:blur(8px);
  transition: opacity .4s ease;
}}
.bark .who {{ font-size:.65rem; letter-spacing:.14em; text-transform:uppercase; color:var(--steam); }}
.bark .what {{ font-size:.9rem; margin-top:.15rem; }}

.finale {{
  position:absolute; inset:0; z-index:8; display:none; align-items:center; justify-content:center;
  background:rgba(5,10,8,.88); backdrop-filter:blur(4px);
}}
.finale.show {{ display:flex; }}
.finale-card {{ text-align:center; max-width:32rem; padding:1.5rem; }}
.finale-card h2 {{ color:var(--gold); margin:0 0 .5rem; }}
.finale-card p {{ color:var(--muted); }}
</style>
</head>
<body>
<div class="stage" id="stage">
  <div class="bg" id="bg"></div>
  <div class="vignette"></div>

  <div class="intro" id="intro">
    <div class="intro-card">
      {"<img src='" + poster + "' alt='Verdance key art'/>" if poster else ""}
      <div class="brand">QUANTUM PLAYER PROXY</div>
      <h1>Verdance's Ashes</h1>
      <p id="intro-tag">A mind that commits under fog.</p>
      <div class="score" id="intro-score"></div>
      <button type="button" id="startBtn">Play the campaign story</button>
      <p style="margin-top:1rem;font-size:.75rem;color:var(--muted)">Autoplay · 15 sorties · fair AI seat</p>
    </div>
  </div>

  <div class="hud">
    <div class="brand">VERDANCE'S ASHES<strong id="hud-title">Campaign</strong></div>
    <div class="badges" id="hud-badges"></div>
  </div>

  <div class="center" id="center">
    <div class="kicker" id="kicker">Arc 1</div>
    <h1 id="title">…</h1>
    <p class="sub" id="sub"></p>
    <div class="voice" id="voice" hidden></div>
    <div class="beats" id="beats"></div>
  </div>

  <div class="bark" id="bark" hidden>
    <div class="who" id="bark-who"></div>
    <div class="what" id="bark-what"></div>
  </div>

  <div class="controls">
    <button type="button" id="btnPrev">Prev</button>
    <button type="button" id="btnPause">Pause</button>
    <button type="button" id="btnNext">Next</button>
  </div>

  <div class="bottom">
    <div class="progress"><i id="prog"></i></div>
    <div class="rail" id="rail"></div>
  </div>

  <div class="finale" id="finale">
    <div class="finale-card">
      {"<img src='" + scars + "' alt='Three scars' style='width:min(480px,86vw);border-radius:12px;margin-bottom:1rem;border:1px solid rgba(61,143,85,.35)'/>" if scars else ""}
      <h2>Three scars. Campaign cleared.</h2>
      <p id="finale-line">The proxy never saw the hidden numbers - only the fog, the graph, and the will to extract.</p>
      <button type="button" id="replay" style="margin-top:1rem;background:rgba(61,143,85,.25);border:1px solid var(--edge);color:var(--ink);padding:.6rem 1.2rem;border-radius:999px;cursor:pointer">Replay</button>
    </div>
  </div>
</div>

<script>
const DATA = {data_json};
const ART = DATA.art || {{}};
const SECONDS_PER = 5.5;
let idx = 0;
let playing = false;
let t0 = 0;
let raf = 0;
let barkI = 0;

function arcOf(ch) {{
  const id = (ch && ch.id) || '';
  const n = parseInt(id.split('_').pop(), 10) || 0;
  if (n <= 5) return '1';
  if (n <= 10) return '2';
  return '3';
}}
function bgFor(i) {{
  const ch = DATA.chapters[i] || {{}};
  const a = arcOf(ch);
  if (a === '1' && ART.poster) return ART.poster;
  if (a === '2' && ART.scars) return ART.scars;
  if (a === '3' && ART.scars) return ART.scars;
  if (ART.graph) return ART.graph;
  return ART.poster || '';
}}

function boot() {{
  document.getElementById('intro-tag').textContent = DATA.tagline || '';
  const arcs = DATA.arcs || [];
  const score = document.getElementById('intro-score');
  if (arcs.length) {{
    score.innerHTML = arcs.map(a =>
      `<div>Arc ${{a.id}} · ${{a.title || ''}}<strong>${{a.wins}}/${{a.total}}</strong></div>`
    ).join('');
  }} else {{
    score.innerHTML = `<div>Missions<strong>${{DATA.hard_wins}}/${{DATA.missions}}</strong></div>
      <div>Seed<strong>${{DATA.seed}}</strong></div>
      <div>Status<strong>${{DATA.cleared ? 'CLEARED' : 'OPEN'}}</strong></div>`;
  }}
  const badges = document.getElementById('hud-badges');
  badges.innerHTML = [
    `<span class="badge steam">${{DATA.billing || 'free'}}</span>`,
    `<span class="badge">${{DATA.agent || 'proxy'}}</span>`,
    `<span class="badge gold">seed ${{DATA.seed}}</span>`,
    `<span class="badge good">${{DATA.cleared ? 'CLEARED' : (DATA.hard_wins+'/'+DATA.missions)}}</span>`,
  ].join('');
  const rail = document.getElementById('rail');
  rail.innerHTML = (DATA.chapters || []).map((c,i) =>
    `<button class="dot ${{c.won ? 'won' : ''}}" data-i="${{i}}" title="${{(c.title||'').replace(/"/g,'')}}"></button>`
  ).join('');
  rail.querySelectorAll('.dot').forEach(d => d.onclick = () => jump(+d.dataset.i));
  if (ART.poster) document.getElementById('bg').style.backgroundImage = `url('${{ART.poster}}')`;
}}

function show(i) {{
  const chs = DATA.chapters || [];
  if (!chs.length) return;
  idx = ((i % chs.length) + chs.length) % chs.length;
  const ch = chs[idx];
  const center = document.getElementById('center');
  center.classList.add('swap');
  setTimeout(() => {{
    document.getElementById('kicker').textContent =
      `Arc ${{arcOf(ch)}} · ${{ch.kind || ''}} · ${{ch.map_name || ''}}`;
    document.getElementById('title').textContent = ch.title || ch.id || 'Sortie';
    document.getElementById('sub').textContent = ch.situation || ch.verdict_line || '';
    const bl = (ch.briefing || []).find(b => b && b.text);
    const voice = document.getElementById('voice');
    if (bl) {{
      voice.hidden = false;
      voice.textContent = `${{bl.speaker || 'voice'}}: ${{bl.text}}`;
    }} else {{
      voice.hidden = true;
    }}
    document.getElementById('beats').innerHTML =
      (ch.beats || []).slice(0,4).map(b => `<div>${{b}}</div>`).join('');
    document.getElementById('hud-title').textContent =
      `${{idx+1}} / ${{chs.length}} · ${{ch.verdict || ''}}`;
    const bg = bgFor(idx);
    if (bg) document.getElementById('bg').style.backgroundImage = `url('${{bg}}')`;
    document.querySelectorAll('.dot').forEach((d,j) => d.classList.toggle('active', j===idx));
    center.classList.remove('swap');
  }}, 220);
  t0 = performance.now();
}}

function tickBark() {{
  const barks = DATA.barks || [];
  if (!barks.length) return;
  const b = barks[barkI % barks.length];
  barkI++;
  const el = document.getElementById('bark');
  el.hidden = false;
  document.getElementById('bark-who').textContent = b.speaker || 'voice';
  document.getElementById('bark-what').textContent = b.text || '';
}}

function frame(now) {{
  if (!playing) return;
  const elapsed = (now - t0) / 1000;
  const p = Math.min(1, elapsed / SECONDS_PER);
  document.getElementById('prog').style.width = (p * 100) + '%';
  if (p >= 1) {{
    if (idx >= (DATA.chapters||[]).length - 1) {{
      playing = false;
      document.getElementById('finale').classList.add('show');
      document.getElementById('btnPause').textContent = 'Play';
      return;
    }}
    show(idx + 1);
    tickBark();
  }}
  raf = requestAnimationFrame(frame);
}}

function start() {{
  document.getElementById('intro').classList.add('hide');
  document.getElementById('finale').classList.remove('show');
  playing = true;
  document.getElementById('btnPause').textContent = 'Pause';
  show(0);
  tickBark();
  cancelAnimationFrame(raf);
  raf = requestAnimationFrame(frame);
}}
function jump(i) {{
  document.getElementById('finale').classList.remove('show');
  show(i);
  if (playing) {{
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(frame);
  }}
}}
function toggle() {{
  playing = !playing;
  document.getElementById('btnPause').textContent = playing ? 'Pause' : 'Play';
  if (playing) {{
    t0 = performance.now() - (parseFloat(document.getElementById('prog').style.width)||0)/100*SECONDS_PER*1000;
    raf = requestAnimationFrame(frame);
  }} else {{
    cancelAnimationFrame(raf);
  }}
}}

document.getElementById('startBtn').onclick = start;
document.getElementById('btnNext').onclick = () => jump(idx+1);
document.getElementById('btnPrev').onclick = () => jump(idx-1);
document.getElementById('btnPause').onclick = toggle;
document.getElementById('replay').onclick = start;
document.addEventListener('keydown', e => {{
  if (e.key === ' ' || e.key === 'Enter') {{
    if (!document.getElementById('intro').classList.contains('hide')) start();
    else toggle();
  }}
  if (e.key === 'ArrowRight') jump(idx+1);
  if (e.key === 'ArrowLeft') jump(idx-1);
}});
boot();
// auto-start after short beat when ?auto=1
if (location.search.includes('auto=1')) setTimeout(start, 900);
</script>
</body>
</html>
"""


def write_showoff(
    story: dict[str, Any],
    *,
    workspace: Path | None = None,
    art_files: dict[str, Path] | None = None,
) -> dict[str, str]:
    """Materialize app/showoff + story/latest/show.html."""
    ws = workspace or _workspace_root()
    show_dir = ws / "app" / "showoff"
    show_dir.mkdir(parents=True, exist_ok=True)
    art_dir = show_dir / "art"
    art_dir.mkdir(parents=True, exist_ok=True)

    art_rel: dict[str, str] = {}
    if art_files:
        for key, src in art_files.items():
            src = Path(src)
            if src.is_file():
                dest = art_dir / f"{key}{src.suffix or '.jpg'}"
                try:
                    if src.resolve() != dest.resolve():
                        shutil.copy2(src, dest)
                except OSError:
                    # file locked / same path — keep existing dest if present
                    if not dest.is_file():
                        dest.write_bytes(src.read_bytes())
                art_rel[key] = f"art/{dest.name}"

    # also pick up any already-present art
    for key in ("poster", "scars", "graph"):
        if key in art_rel:
            continue
        for p in art_dir.glob(f"{key}.*"):
            art_rel[key] = f"art/{p.name}"
            break

    html = build_show_html(story, art_rel=art_rel)
    (show_dir / "index.html").write_text(html, encoding="utf-8")
    (show_dir / "story.json").write_text(
        json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # friend-facing blurb
    blurb = _friend_blurb(story)
    (show_dir / "SHOW_TO_FRIENDS.md").write_text(blurb, encoding="utf-8")
    (show_dir / "README.txt").write_text(
        "VERDANCE SHOW-OFF\n"
        "=================\n"
        "Double-click index.html  OR  run SHOW_OFF.bat from the workspace.\n"
        "Fullscreen the browser. Hit space. Watch 15 sorties autoplay.\n",
        encoding="utf-8",
    )

    # mirror cinematic page next to normal gallery
    latest = ws / "app" / "story" / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    (latest / "show.html").write_text(html, encoding="utf-8")
    # fix art paths for latest/show.html (art lives in ../../showoff/art)
    if art_rel:
        html_latest = build_show_html(
            story,
            art_rel={k: f"../../showoff/{v}" for k, v in art_rel.items()},
        )
        (latest / "show.html").write_text(html_latest, encoding="utf-8")

    return {
        "show_dir": str(show_dir),
        "index": str(show_dir / "index.html"),
        "show_html": str(latest / "show.html"),
        "art": art_rel,
    }


def _friend_blurb(story: dict[str, Any]) -> str:
    wins = story.get("hard_wins")
    total = story.get("missions")
    return f"""# Verdance's Ashes - show this to friends

**Tagline:** {story.get("tagline") or "A mind that commits under fog."}

## What you're looking at (30 second pitch)

I built a single-player campaign for **Beyond All Reason** where an AI plays
as a *fair player proxy* - it only sees what a human would: mission briefings,
a coarse HUD, and a quantum-style belief graph. No god-mode. No cheat sensors.

It just cleared the full campaign:

- **{wins}/{total} missions** across **three arcs**
- Strike raids -> eco expand -> siege / wilds / multipressure climax
- Multi-seed lock at difficulty 1.0
- A trained "BAR brain" learning eco + combat from the run tapes

## Demo in 10 seconds

1. Open `index.html` (or run `SHOW_OFF.bat` in the design workspace)
2. Click **Play the campaign story** (or wait if autoplay)
3. Watch the proxy walk 15 sorties through the quantum graph

In BAR: type `/vastory` for the in-game panel.

## Why it's cool

- Fair AI seat (honest fog-of-war cognition)
- Eco manifold priors from industrial ROI structure costs
- Story told *through* the belief graph, not after the fact
- Dual rooms: design forge vs customer My Games release

---
Generated from proxy story · agent=`{story.get("agent")}` · seed=`{story.get("seed")}`
"""
