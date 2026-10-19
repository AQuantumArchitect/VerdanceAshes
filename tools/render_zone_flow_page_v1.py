#!/usr/bin/env python3
"""Render the measured zone-flow analysis as a standalone survey-plate page.

Reads reports/ai_duel_zone_flow.latest.json (from ai_duel_zone_flow_v1.py) and
draws, per map, a plan-view plot of the authored zone anchors with the measured
unit traffic laid over them: solid lines where units actually crossed an authored
corridor, dashed ash where the corridor exists but nothing used it, and ember
where units crossed between zones the adjacency model does not join at all.

Colours are BAR's own: Armada blue, Cortex red.

Usage:
  python tools/render_zone_flow_page_v1.py --workspace .
"""
from __future__ import annotations

import argparse
import html
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

# Team id -> faction class. The duel matrix seats team 0 Armada, team 1 Cortex.
TEAM_CLASS = {0: "armada", 1: "cortex"}


def load_json(path: Path) -> Any:
    with io.open(path, encoding="utf-8-sig") as fh:
        return json.load(fh)


def esc(s: Any) -> str:
    return html.escape(str(s), quote=True)


def short_label(zone_id: str) -> str:
    """GF_NW_BASTION -> NW BASTION. The map prefix is redundant inside a plate."""
    parts = str(zone_id).split("_")
    return " ".join(parts[1:]) if len(parts) > 1 else str(zone_id)


def dominant_team(by_team: Dict[str, int]) -> Optional[int]:
    if not by_team:
        return None
    items = sorted(((int(k), int(v)) for k, v in by_team.items()), key=lambda kv: (-kv[1], kv[0]))
    return items[0][0]


def render_plot(m: Dict[str, Any], size: int = 1000) -> str:
    anchors = m.get("anchors") or {}
    if not anchors:
        return '<p class="empty">No zone anchors available for this map.</p>'

    peaks = {z["zoneId"]: z for z in m.get("zonePeaks") or []}
    max_peak = max([z["peakValue"] for z in peaks.values()] or [0]) or 1.0

    all_edges: List[Dict[str, Any]] = []
    for e in m.get("inertEdges") or []:
        all_edges.append({**e, "kind": "inert", "crossings": 0})
    for e in m.get("liveEdges") or []:
        all_edges.append({**e, "kind": "live"})
    for e in m.get("unauthoredEdges") or []:
        all_edges.append({**e, "kind": "unauthored"})
    max_cross = max([e.get("crossings", 0) for e in all_edges] or [1]) or 1

    def pos(zid: str):
        a = anchors.get(zid)
        if not a:
            return None
        return (a["x"] * size, a["z"] * size)

    out: List[str] = []
    out.append(
        f'<svg class="plot" viewBox="0 0 {size} {size}" role="img" '
        f'aria-label="Zone traffic plot for {esc(m.get("mapTitle"))}">'
    )

    # Faint plan grid: the survey sheet under the measurement.
    out.append('<g class="grid">')
    for i in range(1, 10):
        p = i * size / 10
        out.append(f'<line x1="{p:.0f}" y1="0" x2="{p:.0f}" y2="{size}" />')
        out.append(f'<line x1="0" y1="{p:.0f}" x2="{size}" y2="{p:.0f}" />')
    out.append("</g>")
    out.append(f'<rect class="frame" x="1" y="1" width="{size-2}" height="{size-2}" />')

    # Edges under nodes. Inert first so live traffic always draws on top.
    for kind in ("inert", "unauthored", "live"):
        out.append(f'<g class="edges edge-{kind}">')
        for e in [x for x in all_edges if x["kind"] == kind]:
            a, b = e["zones"][0], e["zones"][1]
            pa, pb = pos(a), pos(b)
            if not pa or not pb:
                continue
            cross = int(e.get("crossings", 0))
            width = 1.2 if kind == "inert" else 1.6 + 6.0 * math.sqrt(cross / max_cross)
            cls = ""
            if kind == "live":
                dom = dominant_team(e.get("byTeam") or {})
                cls = f' team-{TEAM_CLASS.get(dom, "other")}' if dom is not None else ""
            title = (
                f'{short_label(a)} to {short_label(b)}: '
                f'{cross} crossing(s)' if kind != "inert" else
                f'{short_label(a)} to {short_label(b)}: authored, never used'
            )
            out.append(
                f'<line class="edge{cls}" x1="{pa[0]:.1f}" y1="{pa[1]:.1f}" '
                f'x2="{pb[0]:.1f}" y2="{pb[1]:.1f}" stroke-width="{width:.2f}">'
                f"<title>{esc(title)}</title></line>"
            )
        out.append("</g>")

    # Zone nodes.
    out.append('<g class="nodes">')
    for zid, a in anchors.items():
        x, y = a["x"] * size, a["z"] * size
        z = peaks.get(zid, {})
        peak = float(z.get("peakValue") or 0.0)
        role = z.get("role") or ""
        if peak > 0:
            r = 10 + 34 * math.sqrt(peak / max_peak)
            team = z.get("peakTeam")
            cls = f'held team-{TEAM_CLASS.get(team, "other")}'
        else:
            r = 7
            cls = "vacant"
        out.append(
            f'<circle class="node {cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}">'
            f"<title>{esc(short_label(zid))} ({esc(role)}) peak unit value "
            f"{esc(int(peak))}</title></circle>"
        )
    out.append("</g>")

    # Labels last so nothing overdraws them.
    out.append('<g class="labels">')
    for zid, a in anchors.items():
        x, y = a["x"] * size, a["z"] * size
        z = peaks.get(zid, {})
        r = (
            10 + 34 * math.sqrt(float(z.get("peakValue") or 0.0) / max_peak)
            if float(z.get("peakValue") or 0.0) > 0
            else 7
        )
        out.append(
            f'<text class="zlabel" x="{x:.1f}" y="{(y + r + 26):.1f}" '
            f'text-anchor="middle">{esc(short_label(zid))}</text>'
        )
    out.append("</g>")
    out.append("</svg>")
    return "".join(out)


def render_map_section(map_id: str, m: Dict[str, Any]) -> str:
    live = m.get("liveEdges") or []
    inert = m.get("inertEdges") or []
    unauth = m.get("unauthoredEdges") or []
    peaks = m.get("zonePeaks") or []
    held = [z for z in peaks if z["peakValue"] > 0]
    total_cross = sum(int(e.get("crossings", 0)) for e in live + unauth)

    rows = []
    for e in live[:10]:
        dom = dominant_team(e.get("byTeam") or {})
        cls = TEAM_CLASS.get(dom, "other") if dom is not None else "other"
        rows.append(
            f'<tr><td>{esc(e["labels"][0])}</td><td>{esc(e["labels"][1])}</td>'
            f'<td class="num"><span class="chip {cls}">{esc(e["crossings"])}</span></td></tr>'
        )
    live_table = (
        '<table class="data"><thead><tr><th>From</th><th>To</th>'
        '<th class="num">Crossings</th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
        if rows
        else '<p class="empty">No corridor carried traffic.</p>'
    )

    peak_rows = "".join(
        f'<tr><td>{esc(z["label"])}</td><td class="role">{esc(z["role"])}</td>'
        f'<td class="num">{esc(int(z["peakValue"]))}</td></tr>'
        for z in peaks[:10]
    )

    matchup_rows = "".join(
        f'<tr><td>{esc(mu["seatALabel"])}</td><td>{esc(mu["seatBLabel"])}</td>'
        f'<td class="num">{esc(mu["valueRatio"])}</td>'
        f'<td>{esc(mu["verdict"])}</td>'
        f'<td class="winner">{esc(mu["winner"])}</td></tr>'
        for mu in (m.get("matchups") or [])
    )

    raptor_excluded = int(m.get("raptorCrossingsExcluded") or 0)
    raptor_stat = (
        f'<span><b>{esc(raptor_excluded)}</b> raptor crossings excluded</span>'
        if raptor_excluded
        else ""
    )
    raptor_note = ""
    if m.get("raptorTeams"):
        raptor_note = (
            '<div class="note ember"><h4>Wildlife excluded</h4><p>This map carries a '
            f'RaptorsAI team ({", ".join("team " + str(t) for t in m["raptorTeams"])}). '
            "Raptors roam the whole map and the engine's own balance verdict counts "
            "them as \"enemy\", so both the traffic figures and the value ratios here "
            "are duel-only: raptor units are excluded from crossings, and the ratio is "
            "team A's value over team B's rather than player-over-everyone.</p></div>"
        )

    unauth_note = ""
    if unauth:
        items = ", ".join(
            f'{esc(e["labels"][0])} &rarr; {esc(e["labels"][1])} ({esc(e["crossings"])})'
            for e in unauth[:8]
        )
        unauth_note = (
            '<div class="note ember"><h4>Crossed where adjacency says they cannot</h4>'
            f"<p>{items}</p></div>"
        )

    dead = m.get("deadZones") or []
    dead_note = ""
    if dead:
        dead_note = (
            '<div class="note ash"><h4>Never entered</h4><p>'
            + ", ".join(f'{esc(z["label"])}' for z in dead)
            + "</p></div>"
        )

    return f"""
<section class="plate">
  <header class="plate-head">
    <h2>{esc(m.get('mapTitle'))}</h2>
    <div class="plate-stats">
      <span><b>{esc(m.get('runCount'))}</b> runs</span>
      <span><b>{esc(len(held))}</b>/{esc(m.get('zoneCount'))} zones held</span>
      <span><b>{esc(len(live))}</b>/{esc(m.get('authoredEdgeCount'))} corridors live</span>
      <span><b>{esc(total_cross)}</b> crossings</span>
      {raptor_stat}
    </div>
  </header>
  <div class="plate-body">
    <figure class="plot-wrap">
      {render_plot(m)}
      <figcaption>Plan view, north up. Node area is peak unit value held;
      line weight is measured crossings.</figcaption>
    </figure>
    <div class="plate-side">
      <h3>Busiest corridors</h3>
      <div class="scroll">{live_table}</div>
      <h3>Zone occupancy peaks</h3>
      <div class="scroll"><table class="data"><thead><tr><th>Zone</th><th>Role</th>
      <th class="num">Peak value</th></tr></thead><tbody>{peak_rows}</tbody></table></div>
      {unauth_note}
      {dead_note}
      {raptor_note}
    </div>
  </div>
  <div class="matchups">
    <h3>Matchups</h3>
    <div class="scroll"><table class="data"><thead><tr><th>Seat A (Armada)</th>
    <th>Seat B (Cortex)</th><th class="num">Value ratio A/B</th><th>Verdict</th>
    <th>Ahead</th></tr></thead><tbody>{matchup_rows}</tbody></table></div>
  </div>
</section>
"""


def render_page(report: Dict[str, Any], meta: Dict[str, Any]) -> str:
    ladder_rows = "".join(
        f'<tr><td class="seat">{esc(r["seat"])}</td>'
        f'<td class="num">{esc(r["meanRatio"])}</td>'
        f'<td class="num">{esc(r["samples"])}</td></tr>'
        for r in report.get("seatLadder") or []
    )
    sections = "".join(
        render_map_section(map_id, m) for map_id, m in (report.get("maps") or {}).items()
    )
    maps_n = len(report.get("maps") or {})

    return f"""<title>Verdance Zone Traffic Survey</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500&display=swap">
<style>
:root {{
  --ground: #F1F3ED;
  --surface: #FAFBF7;
  --ink: #171C15;
  --muted: #5C6459;
  --hairline: #D5DACE;
  --armada: #3C7FB8;
  --cortex: #B84A3E;
  --live: #4F8B34;
  --ash: #98A192;
  --ember: #B26A22;
  --grid: #E3E7DD;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground: #0E120C;
    --surface: #161B14;
    --ink: #E7EBE2;
    --muted: #949D8F;
    --hairline: #2A3127;
    --armada: #6BA8DB;
    --cortex: #DD7264;
    --live: #7FBC5C;
    --ash: #5F6859;
    --ember: #D89246;
    --grid: #1F251D;
  }}
}}
:root[data-theme="dark"] {{
  --ground: #0E120C;
  --surface: #161B14;
  --ink: #E7EBE2;
  --muted: #949D8F;
  --hairline: #2A3127;
  --armada: #6BA8DB;
  --cortex: #DD7264;
  --live: #7FBC5C;
  --ash: #5F6859;
  --ember: #D89246;
  --grid: #1F251D;
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  font-size: 15px;
  line-height: 1.55;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 3rem 1.5rem 5rem; }}

.masthead {{ border-bottom: 2px solid var(--ink); padding-bottom: 1.5rem; margin-bottom: 2.5rem; }}
.eyebrow {{
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 0.72rem; letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 0.6rem;
}}
h1 {{
  font-family: "IBM Plex Sans Condensed", "IBM Plex Sans", sans-serif;
  font-weight: 700; font-size: clamp(2rem, 5vw, 3.1rem); line-height: 1.02;
  letter-spacing: -0.015em; margin: 0 0 0.7rem; text-wrap: balance;
}}
.standfirst {{ max-width: 62ch; color: var(--muted); margin: 0; font-size: 1.02rem; }}

.summary {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1px; background: var(--hairline); border: 1px solid var(--hairline);
  margin: 2rem 0 3rem;
}}
.summary div {{ background: var(--surface); padding: 0.9rem 1rem; }}
.summary .k {{
  font-family: "IBM Plex Mono", monospace; font-size: 0.68rem;
  letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted);
}}
.summary .v {{
  font-family: "IBM Plex Sans Condensed", sans-serif; font-weight: 700;
  font-size: 1.7rem; line-height: 1.15; font-variant-numeric: tabular-nums;
}}

h2 {{
  font-family: "IBM Plex Sans Condensed", sans-serif; font-weight: 700;
  font-size: 1.6rem; letter-spacing: -0.01em; margin: 0;
}}
h3 {{
  font-family: "IBM Plex Mono", monospace; font-size: 0.72rem;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted);
  margin: 1.6rem 0 0.6rem; font-weight: 500;
}}
h3:first-child {{ margin-top: 0; }}
h4 {{
  font-family: "IBM Plex Mono", monospace; font-size: 0.7rem;
  letter-spacing: 0.12em; text-transform: uppercase; margin: 0 0 0.35rem;
}}

.legend {{ display: flex; flex-wrap: wrap; gap: 1.1rem; margin: 0 0 2.5rem;
  font-family: "IBM Plex Mono", monospace; font-size: 0.75rem; color: var(--muted); }}
.legend span {{ display: inline-flex; align-items: center; gap: 0.45rem; }}
.swatch {{ width: 22px; height: 0; border-top-width: 3px; border-top-style: solid; }}
.sw-armada {{ border-color: var(--armada); }}
.sw-cortex {{ border-color: var(--cortex); }}
.sw-inert {{ border-color: var(--ash); border-top-style: dashed; }}
.sw-ember {{ border-color: var(--ember); border-top-style: dotted; }}

.plate {{ border-top: 1px solid var(--hairline); padding-top: 1.6rem; margin-top: 2.6rem; }}
.plate-head {{ display: flex; flex-wrap: wrap; align-items: baseline;
  justify-content: space-between; gap: 0.8rem; margin-bottom: 1.2rem; }}
.plate-stats {{ display: flex; flex-wrap: wrap; gap: 1.1rem;
  font-family: "IBM Plex Mono", monospace; font-size: 0.76rem; color: var(--muted); }}
.plate-stats b {{ color: var(--ink); font-variant-numeric: tabular-nums; }}

.plate-body {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 2rem; align-items: start; }}
@media (max-width: 860px) {{ .plate-body {{ grid-template-columns: 1fr; }} }}

figure.plot-wrap {{ margin: 0; }}
figcaption {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.6rem; max-width: 46ch; }}
svg.plot {{ width: 100%; height: auto; display: block; background: var(--surface); }}
svg.plot .grid line {{ stroke: var(--grid); stroke-width: 1; }}
svg.plot .frame {{ fill: none; stroke: var(--hairline); stroke-width: 2; }}
svg.plot .edge {{ stroke: var(--ash); stroke-linecap: round; fill: none; }}
svg.plot .edge-inert .edge {{ stroke: var(--ash); stroke-dasharray: 7 9; opacity: 0.55; }}
svg.plot .edge-unauthored .edge {{ stroke: var(--ember); stroke-dasharray: 2 7; opacity: 0.9; }}
svg.plot .edge-live .edge {{ opacity: 0.85; }}
svg.plot .edge.team-armada {{ stroke: var(--armada); }}
svg.plot .edge.team-cortex {{ stroke: var(--cortex); }}
svg.plot .edge.team-other {{ stroke: var(--live); }}
svg.plot .node {{ stroke-width: 2.5; }}
svg.plot .node.vacant {{ fill: none; stroke: var(--ash); stroke-width: 1.5; }}
svg.plot .node.held.team-armada {{ fill: var(--armada); fill-opacity: 0.22; stroke: var(--armada); }}
svg.plot .node.held.team-cortex {{ fill: var(--cortex); fill-opacity: 0.22; stroke: var(--cortex); }}
svg.plot .node.held.team-other {{ fill: var(--live); fill-opacity: 0.22; stroke: var(--live); }}
svg.plot .zlabel {{
  font-family: "IBM Plex Mono", monospace; font-size: 19px;
  fill: var(--muted); letter-spacing: 0.04em;
}}

.scroll {{ overflow-x: auto; }}
table.data {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
table.data th {{
  font-family: "IBM Plex Mono", monospace; font-size: 0.66rem;
  letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted);
  text-align: left; font-weight: 500; padding: 0.4rem 0.6rem 0.4rem 0;
  border-bottom: 1px solid var(--hairline); white-space: nowrap;
}}
table.data td {{ padding: 0.38rem 0.6rem 0.38rem 0; border-bottom: 1px solid var(--hairline); }}
table.data .num {{ text-align: right; font-variant-numeric: tabular-nums;
  font-family: "IBM Plex Mono", monospace; padding-right: 0; }}
table.data .role, table.data .winner {{ color: var(--muted);
  font-family: "IBM Plex Mono", monospace; font-size: 0.78rem; }}
.chip {{ display: inline-block; min-width: 2.2em; padding: 0.08em 0.45em;
  border-radius: 2px; font-weight: 500; }}
.chip.armada {{ background: color-mix(in srgb, var(--armada) 20%, transparent); color: var(--armada); }}
.chip.cortex {{ background: color-mix(in srgb, var(--cortex) 20%, transparent); color: var(--cortex); }}
.chip.other {{ background: color-mix(in srgb, var(--live) 20%, transparent); color: var(--live); }}

.note {{ margin-top: 1.5rem; padding: 0.8rem 0 0 0.9rem; border-left: 3px solid var(--ash); }}
.note.ember {{ border-color: var(--ember); }}
.note.ash {{ border-color: var(--ash); }}
.note p {{ margin: 0; font-size: 0.85rem; color: var(--muted); }}
.note.ember h4 {{ color: var(--ember); }}
.note.ash h4 {{ color: var(--muted); }}

.matchups {{ margin-top: 2rem; }}
.seat {{ font-family: "IBM Plex Mono", monospace; }}
.empty {{ color: var(--muted); font-size: 0.85rem; font-style: italic; margin: 0; }}
:focus-visible {{ outline: 2px solid var(--live); outline-offset: 2px; }}
</style>

<div class="wrap">
  <header class="masthead">
    <p class="eyebrow">Verdance's Ashes &middot; headless AI duel matrix</p>
    <h1>Where the armies actually go</h1>
    <p class="standfirst">The authored zone maps were cut from a reconstructed
    behaviour prior, and corridors between zones are pure geometry &mdash; two zones
    are neighbours when their cells touch across passable ground. Nothing in that
    says where units move. This is the measurement: SimpleAI, BARbarIAn hard and
    BARbarIAn hard_aggressive played against each other headlessly, with every
    border crossing sampled every five seconds.</p>
  </header>

  <div class="summary">
    <div><div class="k">Runs analysed</div><div class="v">{esc(report.get('runsAnalyzed'))}</div></div>
    <div><div class="k">Maps</div><div class="v">{esc(maps_n)}</div></div>
    <div><div class="k">Suite status</div><div class="v" style="font-size:1.05rem">{esc(report.get('suiteStatus'))}</div></div>
    <div><div class="k">Milestones</div><div class="v" style="font-size:1.05rem">{esc(meta.get('milestones','3,5,8,13 min'))}</div></div>
  </div>

  <h3>Seat ladder &mdash; mean value ratio, own side over opponent</h3>
  <div class="scroll">
    <table class="data">
      <thead><tr><th>Seat</th><th class="num">Mean ratio</th><th class="num">Samples</th></tr></thead>
      <tbody>{ladder_rows}</tbody>
    </table>
  </div>

  <div class="legend" style="margin-top:2rem">
    <span><i class="swatch sw-armada"></i> Armada traffic</span>
    <span><i class="swatch sw-cortex"></i> Cortex traffic</span>
    <span><i class="swatch sw-inert"></i> Authored corridor, never used</span>
    <span><i class="swatch sw-ember"></i> Crossed, but not an authored corridor</span>
  </div>

  {sections}
</div>
"""


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render zone-flow survey page")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--report", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--milestones", default="3, 5, 8, 13 min")
    args = ap.parse_args(argv)

    ws = Path(args.workspace).resolve()
    report_path = (
        Path(args.report).resolve()
        if args.report
        else ws / "reports" / "ai_duel_zone_flow.latest.json"
    )
    report = load_json(report_path)
    out = Path(args.out) if args.out else ws / "reports" / "zone_flow_survey.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    with io.open(out, "w", encoding="utf-8") as fh:
        fh.write(render_page(report, {"milestones": args.milestones}))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
