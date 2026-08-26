"""Turn fair-arc tapes into the story the proxy player told through the graph.

Player-legal only: briefing, HUD phases, beliefs, thoughts, actions, verdicts.
Never injects SimTruth into the narrative surface (operator appendix optional).
"""
from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _action_phrase(action: str) -> str:
    table = {
        "PUSH_OBJECTIVE": "committed on the objective",
        "FLANK": "cut a flank",
        "PROBE": "probed the approach",
        "HOLD_AND_HEAL": "held ground and patched the team",
        "RALLY": "rallied the formation",
        "FALLBACK": "fell back to buy space",
        "EXTRACT": "pushed for extraction",
        "SUPPRESS": "laid down suppression",
        "BUILD_MEX": "planted metal extractors",
        "BUILD_ENERGY": "raised wind and solar",
        "BUILD_CON": "rolled another constructor",
        "EXPAND_FRONT": "pushed the eco footprint forward",
        "RECLAIM": "reclaimed wrecks into stockpile",
        "TECH_UP": "climbed a tech rung",
        "DEFEND_BASE": "turned guns home to guard the plant",
    }
    return table.get(action.upper(), action.lower().replace("_", " "))


def _verdict_line(verdict: str, title: str) -> str:
    if verdict in ("extracted", "objective_complete"):
        return f"**{title}** — mission complete ({verdict.replace('_', ' ')})."
    if verdict == "heroes_dead":
        return f"**{title}** — the strike team broke. Heroes down."
    if verdict.startswith("timeout"):
        return f"**{title}** — the clock won ({verdict.replace('_', ' ')})."
    return f"**{title}** — ended as {verdict}."


def _pick_beats(tape: list[dict[str, Any]], *, max_beats: int = 8) -> list[dict[str, Any]]:
    """Sample the quantum-graph path: ant turns + phase changes + key thoughts."""
    if not tape:
        return []
    beats: list[dict[str, Any]] = []
    last_phase = None
    for row in tape:
        phase = (row.get("hud") or {}).get("phase")
        backend = row.get("backend") or ""
        thoughts = row.get("thoughts") or []
        interesting = (
            backend.startswith("ant")
            or phase != last_phase
            or any("ant subscription" in str(t) for t in thoughts)
            or row.get("action") in ("EXTRACT", "FLANK", "FALLBACK")
        )
        if interesting:
            beats.append(row)
            last_phase = phase
    # always bookend
    if tape[0] not in beats:
        beats.insert(0, tape[0])
    if tape[-1] not in beats:
        beats.append(tape[-1])
    # thin if too many
    if len(beats) > max_beats:
        step = max(1, len(beats) // max_beats)
        head = [beats[0]]
        mid = beats[1:-1:step][: max_beats - 2]
        tail = [beats[-1]]
        beats = head + mid + tail
    return beats


def _mission_chapter(result: dict[str, Any]) -> dict[str, Any]:
    card = result.get("player_card") or {}
    title = card.get("title") or result.get("mission_id") or "sortie"
    mid = result.get("mission_id") or "?"
    tape = result.get("tape") or []
    thoughts = result.get("thoughts") or []
    actions = result.get("actions") or []
    hist = Counter(actions)
    top_actions = [a for a, _ in hist.most_common(4)]
    beats = _pick_beats(tape)

    narrative_lines: list[str] = []
    situation = card.get("situation") or ""
    if situation:
        narrative_lines.append(situation.strip())
    how = card.get("how_to_win") or card.get("objective_text") or ""
    if how:
        narrative_lines.append(f"Orders: {how.strip()}")

    beat_lines: list[str] = []
    for b in beats:
        tick = b.get("tick", 0)
        action = b.get("action") or "?"
        reason = (b.get("reason") or "").strip()
        backend = b.get("backend") or ""
        mood = b.get("mood") or ""
        phase = (b.get("hud") or {}).get("phase") or ""
        contact = (b.get("hud") or {}).get("contact") or ""
        voice = "steam" if "ant" in backend else "chassis"
        clause = _action_phrase(action)
        bit = f"t{tick:03d} [{voice}] {clause}"
        if phase or contact:
            bit += f" — HUD {phase}/{contact}".rstrip("/")
        if mood:
            bit += f" · belief: {mood}"
        if reason:
            bit += f" · “{reason[:140]}”"
        beat_lines.append(bit)

    ant_thoughts = [
        t for t in thoughts if isinstance(t, str) and ("ant subscription" in t or t.startswith("ant "))
    ]
    other_thoughts = [
        t for t in thoughts if isinstance(t, str) and t not in ant_thoughts
    ][-6:]

    briefing = card.get("briefing_lines") or []
    chapter = {
        "id": mid,
        "title": title,
        "map_name": card.get("map_name"),
        "kind": card.get("kind"),
        "verdict": result.get("verdict"),
        "won": bool(result.get("won")),
        "ticks": result.get("ticks"),
        "progress": result.get("progress"),
        "heroes_alive_frac": result.get("heroes_alive_frac"),
        "backends": result.get("backends") or {},
        "top_actions": top_actions,
        "situation": situation,
        "objective": card.get("objective_text") or card.get("plain_objective"),
        "briefing_lines": briefing,
        "narrative_open": narrative_lines,
        "beats": beat_lines,
        "ant_thoughts": ant_thoughts[-8:],
        "closing_thoughts": other_thoughts,
        "verdict_line": _verdict_line(str(result.get("verdict") or "?"), title),
    }
    return chapter


def build_story(report: dict[str, Any], *, title: str | None = None) -> dict[str, Any]:
    """Build a player-facing story document from a play_first_arc / play_campaign report."""
    results = report.get("results") or []
    chapters = [_mission_chapter(r) for r in results]
    cleared = bool(report.get("cleared") or report.get("cleared_all_arcs"))
    agent = report.get("agent") or "unknown"
    billing = report.get("llm_billing") or (
        "subscription" if report.get("use_ant") else "free"
    )
    hard = int(report.get("hard_wins") or sum(1 for c in chapters if c.get("won")))
    total = int(report.get("missions") or len(chapters))
    multi = total > 5 or bool(report.get("by_arc") or report.get("arcs_played"))
    default_title = (
        "Verdance Campaign — Proxy Player Story"
        if multi
        else "Verdance First Arc — Proxy Player Story"
    )

    if multi and cleared:
        arc_blurb = (
            f"The proxy player cleared the Verdance campaign ({total} sorties across "
            "strike, expand, and climax arcs) — reading only briefings, the coarse HUD "
            "(including eco bands when building was allowed), and an imperfect belief graph."
        )
    elif multi:
        arc_blurb = (
            f"The proxy player fought the multi-arc campaign and held {hard}/{total} missions. "
            "What follows is what they believed and chose — not the hidden sim."
        )
    elif cleared:
        arc_blurb = (
            "The proxy player cleared the first arc of Verdance's Ashes — five sorties, "
            "strike team only, no base building — reading only the briefing, the coarse HUD, "
            "and an imperfect belief graph."
        )
    else:
        arc_blurb = (
            f"The proxy player fought the first arc and held {hard}/{total} missions. "
            "What follows is what they believed and chose — not the hidden sim."
        )

    prose_parts: list[str] = [
        f"# {title or default_title}",
        "",
        f"*Told through the quantum graph · agent=`{agent}` · billing=`{billing}` · "
        f"seed={report.get('seed')} · difficulty={report.get('difficulty')}*",
        "",
        arc_blurb,
        "",
    ]
    ARC_TITLES = {
        "1": ("First Scar", "Strike team. No base. Heroes and dirt."),
        "2": ("Second Scar", "Expand and tempo. Plant what pays. Hold what you plant."),
        "3": ("Third Scar", "Siege, wilds, multipressure. Cut the last knot."),
    }
    if report.get("by_arc"):
        prose_parts.append("### Arc scoreboard")
        prose_parts.append("")
        for arc_id, bucket in sorted((report.get("by_arc") or {}).items()):
            t, _ = ARC_TITLES.get(str(arc_id), (f"Arc {arc_id}", ""))
            prose_parts.append(
                f"- **Arc {arc_id} — {t}:** {bucket.get('wins')}/{bucket.get('total')} · "
                f"cleared={bucket.get('cleared')}"
            )
        prose_parts.append("")

    current_arc = None
    for i, ch in enumerate(chapters, 1):
        mid = str(ch.get("id") or "")
        try:
            n = int(mid.split("_")[-1])
        except ValueError:
            n = i
        arc = "1" if n <= 5 else ("2" if n <= 10 else "3")
        if arc != current_arc:
            current_arc = arc
            at, ablurb = ARC_TITLES.get(arc, (f"Arc {arc}", ""))
            prose_parts.append(f"## ✦ Arc {arc}: {at}")
            prose_parts.append("")
            prose_parts.append(f"*{ablurb}*")
            prose_parts.append("")

        prose_parts.append(f"### Chapter {i}: {ch['title']}")
        prose_parts.append("")
        if ch.get("map_name"):
            prose_parts.append(f"**Map:** {ch['map_name']} · **Kind:** `{ch.get('kind')}`")
            prose_parts.append("")
        for line in ch.get("narrative_open") or []:
            prose_parts.append(line)
            prose_parts.append("")
        for bl in ch.get("briefing_lines") or []:
            if isinstance(bl, dict):
                prose_parts.append(f"> **{bl.get('speaker', '?')}:** {bl.get('text', '')}")
            else:
                prose_parts.append(f"> {bl}")
        if ch.get("briefing_lines"):
            prose_parts.append("")
        prose_parts.append("#### Through the graph")
        prose_parts.append("")
        for beat in ch.get("beats") or []:
            prose_parts.append(f"- {beat}")
        prose_parts.append("")
        if ch.get("ant_thoughts"):
            prose_parts.append("#### Ant steam (subscription)")
            prose_parts.append("")
            for t in ch["ant_thoughts"]:
                prose_parts.append(f"- {t}")
            prose_parts.append("")
        prose_parts.append(ch["verdict_line"])
        prose_parts.append("")

    prose_parts.append("---")
    prose_parts.append("")
    if cleared and multi:
        prose_parts.append(
            "### Epilogue\n\n"
            "Three scars. Fifteen sorties. The proxy never saw the hidden numbers — "
            "only the briefing, the coarse HUD, the belief graph, and the tools of a "
            "player who has to live with imperfect knowledge. That is the art: a mind "
            "that commits under fog and still walks the campaign home.\n"
        )
    prose_parts.append(
        f"**Campaign result:** {hard}/{total} hard wins · cleared={cleared} · "
        f"ant_calls={report.get('llm_calls')}"
    )
    prose = "\n".join(prose_parts)

    barks: list[dict[str, str]] = []
    for ch in chapters:
        barks.append(
            {
                "speaker": "overmind",
                "text": f"{ch['title']}: {ch.get('objective') or 'sortie'}",
            }
        )
        for bl in (ch.get("briefing_lines") or [])[:2]:
            if isinstance(bl, dict):
                barks.append(
                    {
                        "speaker": str(bl.get("speaker") or "ketha"),
                        "text": str(bl.get("text") or ""),
                    }
                )
        for t in (ch.get("ant_thoughts") or [])[:2]:
            clean = re.sub(r"^ant subscription[^→]*→\s*", "", t).strip()
            if clean:
                barks.append({"speaker": "proxy", "text": clean[:180]})
        barks.append(
            {
                "speaker": "overmind",
                "text": ch["verdict_line"].replace("**", ""),
            }
        )

    # Arc rollup for GUI / HTML gallery
    arcs_ui: list[dict[str, Any]] = []
    by_arc = report.get("by_arc") or {}
    for arc_id in ("1", "2", "3"):
        if arc_id not in by_arc and not any(
            _chapter_arc(c) == arc_id for c in chapters
        ):
            continue
        t, ablurb = {
            "1": ("First Scar", "Strike team. No base. Heroes and dirt."),
            "2": ("Second Scar", "Expand and tempo. Plant what pays."),
            "3": ("Third Scar", "Siege, wilds, multipressure."),
        }.get(arc_id, (f"Arc {arc_id}", ""))
        chs = [c for c in chapters if _chapter_arc(c) == arc_id]
        bucket = by_arc.get(arc_id) or {
            "wins": sum(1 for c in chs if c.get("won")),
            "total": len(chs),
            "cleared": all(c.get("won") for c in chs) if chs else False,
        }
        arcs_ui.append(
            {
                "id": arc_id,
                "title": t,
                "blurb": ablurb,
                "wins": bucket.get("wins"),
                "total": bucket.get("total") or len(chs),
                "cleared": bucket.get("cleared"),
                "chapter_ids": [c.get("id") for c in chs],
            }
        )

    story = {
        "schemaVersion": "verdance-proxy-story/0.2",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "title": title or default_title,
        "agent": agent,
        "billing": billing,
        "cleared": cleared,
        "hard_wins": hard,
        "missions": total,
        "seed": report.get("seed"),
        "difficulty": report.get("difficulty"),
        "use_ant": report.get("use_ant"),
        "ant_every_n": report.get("ant_every_n"),
        "llm_calls": report.get("llm_calls"),
        "arc_blurb": arc_blurb,
        "arcs": arcs_ui,
        "by_arc": by_arc,
        "chapters": chapters,
        "barks": barks,
        "markdown": prose,
        "tagline": (
            "A mind that commits under fog — and walks the campaign home."
            if cleared
            else "Imperfect knowledge. Honest scars. Still walking."
        ),
        "fairness": {
            "sees": [
                "PlayerFacingCard",
                "FairHUD",
                "eco bands (when building allowed)",
                "umwelt belief graph",
                "tool thoughts",
            ],
            "never_sees": ["SimTruth", "enemy_scale", "raw HP", "RNG"],
        },
    }
    return story


def _chapter_arc(ch: dict[str, Any]) -> str:
    mid = str(ch.get("id") or "")
    try:
        n = int(mid.split("_")[-1])
    except ValueError:
        return "1"
    if n <= 5:
        return "1"
    if n <= 10:
        return "2"
    return "3"


def story_to_lua(story: dict[str, Any]) -> str:
    """Serialize story as a Lua table for the BAR widget."""

    def esc(s: str) -> str:
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\r", "")
        )

    lines = [
        "-- Auto-generated proxy player story (quantum graph). Do not edit by hand.",
        "return {",
        f'  schemaVersion = "{esc(story.get("schemaVersion", ""))}",',
        f'  title = "{esc(story.get("title", ""))}",',
        f'  tagline = "{esc(story.get("tagline", ""))}",',
        f'  generatedAt = "{esc(story.get("generatedAt", ""))}",',
        f'  agent = "{esc(story.get("agent", ""))}",',
        f'  billing = "{esc(story.get("billing", ""))}",',
        f'  cleared = {"true" if story.get("cleared") else "false"},',
        f'  hardWins = {int(story.get("hard_wins") or 0)},',
        f'  missions = {int(story.get("missions") or 0)},',
        f'  seed = {int(story.get("seed") or 0)},',
        f'  difficulty = {float(story.get("difficulty") or 1.0)},',
        f'  arcBlurb = "{esc(story.get("arc_blurb", ""))}",',
        "  arcs = {",
    ]
    for a in story.get("arcs") or []:
        lines.append("    {")
        lines.append(f'      id = "{esc(a.get("id", ""))}",')
        lines.append(f'      title = "{esc(a.get("title", ""))}",')
        lines.append(f'      blurb = "{esc(a.get("blurb", ""))}",')
        lines.append(f'      wins = {int(a.get("wins") or 0)},')
        lines.append(f'      total = {int(a.get("total") or 0)},')
        lines.append(f'      cleared = {"true" if a.get("cleared") else "false"},')
        lines.append("    },")
    lines.append("  },")
    lines.append("  barks = {")
    for b in story.get("barks") or []:
        lines.append(
            f'    {{ speaker = "{esc(b.get("speaker", ""))}", '
            f'text = "{esc(b.get("text", ""))}" }},'
        )
    lines.append("  },")
    lines.append("  chapters = {")
    for ch in story.get("chapters") or []:
        lines.append("    {")
        lines.append(f'      id = "{esc(ch.get("id", ""))}",')
        lines.append(f'      title = "{esc(ch.get("title", ""))}",')
        lines.append(f'      mapName = "{esc(ch.get("map_name") or "")}",')
        lines.append(f'      kind = "{esc(ch.get("kind") or "")}",')
        lines.append(f'      arc = "{esc(_chapter_arc(ch))}",')
        lines.append(f'      verdict = "{esc(ch.get("verdict") or "")}",')
        lines.append(f'      won = {"true" if ch.get("won") else "false"},')
        lines.append(f'      verdictLine = "{esc(ch.get("verdict_line") or "")}",')
        lines.append("      beats = {")
        for beat in (ch.get("beats") or [])[:10]:
            # shorten for Lua GUI readability
            short = beat if len(str(beat)) < 160 else str(beat)[:157] + "..."
            lines.append(f'        "{esc(short)}",')
        lines.append("      },")
        lines.append("    },")
    lines.append("  },")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def write_story_bundle(
    story: dict[str, Any],
    out_dir: Path,
    *,
    also_lua: Path | None = None,
    also_latest: Path | None = None,
) -> dict[str, str]:
    """Write markdown, json, html fragment, lua; return paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    md = out_dir / "STORY.md"
    md.write_text(story["markdown"], encoding="utf-8")
    paths["markdown"] = str(md)

    js = out_dir / "story.json"
    # don't duplicate huge markdown twice in json consumers if needed — keep it
    js.write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
    paths["json"] = str(js)

    html = out_dir / "index.html"
    html.write_text(_story_html(story), encoding="utf-8")
    paths["html"] = str(html)

    lua_text = story_to_lua(story)
    lua_path = out_dir / "proxy_story_current.lua"
    lua_path.write_text(lua_text, encoding="utf-8")
    paths["lua"] = str(lua_path)

    if also_lua is not None:
        also_lua = Path(also_lua)
        also_lua.parent.mkdir(parents=True, exist_ok=True)
        also_lua.write_text(lua_text, encoding="utf-8")
        paths["mod_lua"] = str(also_lua)

    if also_latest is not None:
        also_latest = Path(also_latest)
        also_latest.parent.mkdir(parents=True, exist_ok=True)
        also_latest.write_text(json.dumps(story, indent=2, ensure_ascii=False), encoding="utf-8")
        paths["latest_json"] = str(also_latest)

    return paths


def _story_html(story: dict[str, Any]) -> str:
    """Gallery hearth — structured campaign art, not just markdown dump."""
    title = story.get("title") or "Proxy Story"
    tagline = story.get("tagline") or ""
    chapters = story.get("chapters") or []
    arcs = story.get("arcs") or []
    cleared = bool(story.get("cleared"))
    hard = story.get("hard_wins")
    total = story.get("missions")

    # Arc scoreboard cards
    arc_cards = []
    for a in arcs:
        mark = "cleared" if a.get("cleared") else "open"
        arc_cards.append(
            f"""<article class="arc-card {mark}">
  <div class="arc-num">Arc { _h(str(a.get('id'))) }</div>
  <h3>{_h(a.get('title') or '')}</h3>
  <p class="muted">{_h(a.get('blurb') or '')}</p>
  <div class="arc-score">{int(a.get('wins') or 0)}/{int(a.get('total') or 0)}</div>
</article>"""
        )
    if not arc_cards and chapters:
        # synthesize from chapters if arcs missing
        for aid, t, bl in (
            ("1", "First Scar", "Strike"),
            ("2", "Second Scar", "Expand"),
            ("3", "Third Scar", "Climax"),
        ):
            chs = [c for c in chapters if _chapter_arc(c) == aid]
            if not chs:
                continue
            w = sum(1 for c in chs if c.get("won"))
            arc_cards.append(
                f"""<article class="arc-card {'cleared' if w == len(chs) else 'open'}">
  <div class="arc-num">Arc {aid}</div>
  <h3>{t}</h3>
  <p class="muted">{bl}</p>
  <div class="arc-score">{w}/{len(chs)}</div>
</article>"""
            )

    # Timeline of missions
    timeline = []
    for i, ch in enumerate(chapters, 1):
        won = bool(ch.get("won"))
        timeline.append(
            f"""<button type="button" class="node {'won' if won else 'lost'}" data-ch="{i-1}" title="{_h(ch.get('title') or '')}">
  <span class="dot"></span>
  <span class="lab">{_h(ch.get('id') or f'#{i}')}</span>
</button>"""
        )

    # Chapter panels
    panels = []
    for i, ch in enumerate(chapters):
        beats_html = "".join(
            f"<li>{_h(b)}</li>" for b in (ch.get("beats") or [])[:8]
        )
        voices = []
        for bl in (ch.get("briefing_lines") or [])[:3]:
            if isinstance(bl, dict):
                voices.append(
                    f"<blockquote><strong>{_h(bl.get('speaker','?'))}:</strong> "
                    f"{_h(bl.get('text',''))}</blockquote>"
                )
        sit = "".join(f"<p>{_h(line)}</p>" for line in (ch.get("narrative_open") or [])[:2])
        panels.append(
            f"""<section class="chapter" id="ch-{i}" data-arc="{_h(_chapter_arc(ch))}" hidden>
  <header>
    <span class="badge arc">Arc {_h(_chapter_arc(ch))}</span>
    <span class="badge">{_h(ch.get('kind') or '')}</span>
    <span class="badge {'good' if ch.get('won') else 'bad'}">{_h(ch.get('verdict') or '')}</span>
  </header>
  <h2>{_h(ch.get('title') or '')}</h2>
  <p class="mapline">{_h(ch.get('map_name') or '')}</p>
  {sit}
  {''.join(voices)}
  <h3>Through the graph</h3>
  <ul class="beats">{beats_html}</ul>
  <p class="verdict">{_h((ch.get('verdict_line') or '').replace('**',''))}</p>
</section>"""
        )

    barks_js = json.dumps(
        [{"speaker": b.get("speaker"), "text": b.get("text")} for b in (story.get("barks") or [])],
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{_h(title)}</title>
<style>
  :root {{
    --bg: #070e0b; --panel: #0e1a14; --panel2: #13241b; --ink: #e8f2e8;
    --muted: #7d9584; --edge: #3d8f55; --gold: #d4c49a; --steam: #7ec8ff;
    --warn: #e0a040; --bad: #e07060; --glow: rgba(61,143,85,.35);
  }}
  * {{ box-sizing: border-box; }}
  html {{ scroll-behavior: smooth; }}
  body {{
    margin: 0; min-height: 100vh; color: var(--ink);
    font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
    background:
      radial-gradient(ellipse 80% 50% at 50% -10%, #1a3a28 0%, transparent 55%),
      radial-gradient(ellipse 40% 30% at 90% 80%, rgba(126,200,255,.06), transparent 50%),
      var(--bg);
    line-height: 1.55;
  }}
  .shell {{ max-width: 58rem; margin: 0 auto; padding: 2rem 1.25rem 5rem; }}
  .hero {{
    text-align: center; padding: 2.5rem 1.5rem 2rem;
    border: 1px solid rgba(61,143,85,.4); border-radius: 18px;
    background: linear-gradient(165deg, var(--panel2), var(--panel));
    box-shadow: 0 20px 60px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.04);
    position: relative; overflow: hidden;
  }}
  .hero::before {{
    content: ""; position: absolute; inset: -40% -20% auto;
    height: 80%; background: radial-gradient(circle, var(--glow), transparent 60%);
    pointer-events: none;
  }}
  .hero h1 {{
    margin: 0 0 .4rem; font-weight: 600; letter-spacing: .03em;
    color: var(--gold); font-size: clamp(1.4rem, 3vw, 2rem); position: relative;
  }}
  .tagline {{
    color: var(--steam); font-style: italic; margin: .5rem auto 1rem;
    max-width: 32rem; position: relative;
  }}
  .badges {{ display: flex; flex-wrap: wrap; gap: .4rem; justify-content: center; position: relative; }}
  .badge {{
    display: inline-block; padding: .2rem .65rem; border-radius: 999px;
    background: rgba(61,143,85,.18); color: var(--edge); font-size: .72rem;
    letter-spacing: .04em; text-transform: uppercase;
  }}
  .badge.steam {{ background: rgba(126,200,255,.12); color: var(--steam); }}
  .badge.gold {{ background: rgba(212,196,154,.15); color: var(--gold); }}
  .badge.good {{ background: rgba(64,200,90,.15); color: #6fdf7a; }}
  .badge.bad {{ background: rgba(224,112,96,.15); color: var(--bad); }}
  .badge.arc {{ background: rgba(212,196,154,.12); color: var(--gold); }}
  .blurb {{
    margin: 1.25rem auto 0; max-width: 38rem; color: var(--muted); font-size: .95rem;
    position: relative;
  }}
  .arcs {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(10.5rem, 1fr));
    gap: .85rem; margin: 1.75rem 0 1.25rem;
  }}
  .arc-card {{
    background: var(--panel); border: 1px solid rgba(61,143,85,.3);
    border-radius: 12px; padding: 1rem 1.1rem; transition: transform .15s, border-color .15s;
  }}
  .arc-card:hover {{ transform: translateY(-2px); border-color: var(--edge); }}
  .arc-card.cleared {{ border-color: rgba(111,223,122,.45); }}
  .arc-num {{ font-size: .7rem; text-transform: uppercase; letter-spacing: .12em; color: var(--muted); }}
  .arc-card h3 {{ margin: .25rem 0; color: var(--gold); font-size: 1.05rem; }}
  .arc-card .muted {{ margin: 0; color: var(--muted); font-size: .82rem; }}
  .arc-score {{ margin-top: .65rem; font-size: 1.35rem; color: var(--edge); font-weight: 600; }}
  .timeline {{
    display: flex; flex-wrap: wrap; gap: .35rem; justify-content: center;
    margin: 1rem 0 1.5rem; padding: .75rem; background: rgba(0,0,0,.25);
    border-radius: 12px; border: 1px solid rgba(61,143,85,.2);
  }}
  .node {{
    appearance: none; border: 0; background: transparent; cursor: pointer;
    display: flex; flex-direction: column; align-items: center; gap: .2rem;
    padding: .25rem .35rem; color: var(--muted); font-size: .62rem;
  }}
  .node .dot {{
    width: 12px; height: 12px; border-radius: 50%;
    background: var(--muted); box-shadow: 0 0 0 2px rgba(0,0,0,.4);
  }}
  .node.won .dot {{ background: #6fdf7a; box-shadow: 0 0 10px rgba(111,223,122,.5); }}
  .node.lost .dot {{ background: var(--bad); }}
  .node:hover .lab, .node.active .lab {{ color: var(--gold); }}
  .node.active .dot {{ transform: scale(1.25); }}
  .nav {{
    display: flex; gap: .5rem; justify-content: center; margin-bottom: 1rem;
  }}
  .nav button {{
    background: rgba(61,143,85,.15); border: 1px solid rgba(61,143,85,.4);
    color: var(--ink); border-radius: 8px; padding: .45rem 1rem; cursor: pointer;
    font-size: .85rem;
  }}
  .nav button:hover {{ background: rgba(61,143,85,.3); }}
  .chapter {{
    background: var(--panel); border: 1px solid rgba(61,143,85,.35);
    border-radius: 14px; padding: 1.5rem 1.6rem 1.75rem;
    box-shadow: 0 12px 40px rgba(0,0,0,.3);
    animation: fade .25s ease;
  }}
  .chapter[hidden] {{ display: none !important; }}
  @keyframes fade {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
  .chapter h2 {{ margin: .5rem 0 .15rem; color: var(--gold); font-weight: 600; }}
  .mapline {{ color: var(--muted); margin: 0 0 1rem; font-size: .9rem; }}
  .chapter h3 {{
    color: var(--steam); font-size: .78rem; text-transform: uppercase;
    letter-spacing: .08em; margin: 1.2rem 0 .5rem;
  }}
  blockquote {{
    margin: .5rem 0; padding: .55rem 1rem; border-left: 3px solid var(--edge);
    background: rgba(0,0,0,.22); color: var(--gold); font-style: italic;
  }}
  ul.beats {{ margin: 0; padding-left: 1.1rem; }}
  ul.beats li {{ margin: .4rem 0; color: var(--ink); font-size: .9rem; }}
  .verdict {{ margin-top: 1rem; color: var(--edge); font-weight: 500; }}
  .bark-strip {{
    position: fixed; left: 50%; bottom: 1rem; transform: translateX(-50%);
    width: min(40rem, 92vw); background: rgba(8,18,12,.92);
    border: 1px solid rgba(126,200,255,.35); border-radius: 12px;
    padding: .65rem 1rem; box-shadow: 0 8px 32px rgba(0,0,0,.5);
    backdrop-filter: blur(8px); z-index: 20;
  }}
  .bark-strip .who {{ color: var(--steam); font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; }}
  .bark-strip .what {{ color: var(--ink); font-size: .95rem; margin-top: .15rem; }}
  footer.fair {{
    margin-top: 2rem; text-align: center; color: var(--muted); font-size: .78rem;
  }}
</style>
</head>
<body>
<div class="shell">
  <header class="hero">
    <h1>{_h(title)}</h1>
    <p class="tagline">{_h(tagline)}</p>
    <div class="badges">
      <span class="badge">quantum graph</span>
      <span class="badge steam">{_h(str(story.get("billing") or "free"))}</span>
      <span class="badge">agent {_h(str(story.get("agent") or "?"))}</span>
      <span class="badge gold">seed {_h(str(story.get("seed") or "?"))}</span>
      <span class="badge {'good' if cleared else 'bad'}">
        {"CLEARED " + str(hard) + "/" + str(total) if cleared else str(hard) + "/" + str(total)}
      </span>
    </div>
    <p class="blurb">{_h(story.get("arc_blurb") or "")}</p>
  </header>

  <div class="arcs">
    {"".join(arc_cards)}
  </div>

  <div class="timeline" id="timeline" role="tablist" aria-label="Missions">
    {"".join(timeline)}
  </div>
  <div class="nav">
    <button type="button" id="prev">← Prev</button>
    <button type="button" id="next">Next →</button>
  </div>

  <div id="chapters">
    {"".join(panels)}
  </div>

  <footer class="fair">
    Fair contract: briefing · HUD · eco bands · belief graph · tools —
    never SimTruth · enemy_scale · raw HP · RNG
  </footer>
</div>

<div class="bark-strip" id="bark">
  <div class="who" id="bark-who">overmind</div>
  <div class="what" id="bark-what">…</div>
</div>

<script>
const BARKS = {barks_js};
const n = document.querySelectorAll(".chapter").length;
let idx = 0;
function show(i) {{
  idx = (i + n) % Math.max(n, 1);
  document.querySelectorAll(".chapter").forEach((el, j) => {{
    el.hidden = j !== idx;
  }});
  document.querySelectorAll(".node").forEach((el, j) => {{
    el.classList.toggle("active", j === idx);
  }});
}}
document.querySelectorAll(".node").forEach((el) => {{
  el.addEventListener("click", () => show(+el.dataset.ch));
}});
document.getElementById("prev").onclick = () => show(idx - 1);
document.getElementById("next").onclick = () => show(idx + 1);
if (n) show(0);
let bi = 0;
function tickBark() {{
  if (!BARKS.length) return;
  const b = BARKS[bi % BARKS.length];
  document.getElementById("bark-who").textContent = b.speaker || "voice";
  document.getElementById("bark-what").textContent = b.text || "";
  bi++;
}}
tickBark();
setInterval(tickBark, 4500);
document.addEventListener("keydown", (e) => {{
  if (e.key === "ArrowRight") show(idx + 1);
  if (e.key === "ArrowLeft") show(idx - 1);
}});
</script>
</body>
</html>
"""


def _h(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def story_from_report_path(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # support both raw play_first_arc and beat wrapper
    if "results" in data:
        return build_story(data)
    if "champion" in data and data.get("history_tail"):
        # pull last cleared run if present
        for batch in reversed(data.get("history_tail") or []):
            for run in batch.get("runs") or []:
                if run.get("results"):
                    return build_story(run)
    raise ValueError(f"no fair-arc results in {path}")
