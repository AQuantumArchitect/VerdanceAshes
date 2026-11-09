#!/usr/bin/env python3
"""Word audit of the camp talks, for the writing pass (owner direction 2026-11-09: the dialogue and
the questions are cluttered; tighter and more meaningful). Counts what a player reads per talk: the
setup, the beats and the answers. Prints the distribution and the longest talks.

    python tools/talk_word_audit_v1.py                 authored talks (data/story/camp_talks_authored.json)
    python tools/talk_word_audit_v1.py --all           also the generated ones (camp_talks.json)
    python tools/talk_word_audit_v1.py --top 25 --md docs/writing/talk_audit.md
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")


def words(s) -> int:
    return len(WORD.findall(str(s or "")))


def talk_words(t: dict) -> dict:
    beats = t.get("beats") or []
    narr = sum(words(b.get("line")) for b in beats if b.get("speaker") == "narrator")
    spoken = sum(words(b.get("line")) for b in beats if b.get("speaker") != "narrator")
    answers = t.get("answers") or t.get("choices") or []
    ans = sum(words(a.get("label") or a.get("text")) for a in answers if isinstance(a, dict))
    setup = words(t.get("setup"))
    return {"id": t.get("id"), "title": t.get("title"), "beats": len(beats), "narration": narr + setup,
            "spoken": spoken, "answers": ans, "total": narr + setup + spoken + ans,
            "longestLine": max((words(b.get("line")) for b in beats), default=0)}


def load(path: Path) -> list:
    d = json.loads(path.read_text(encoding="utf-8-sig"))
    return d.get("talks") if isinstance(d, dict) else d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--md", help="write the report as Markdown here")
    a = ap.parse_args()
    talks = load(ROOT / "data" / "story" / "camp_talks_authored.json")
    if a.all:
        talks += load(ROOT / "data" / "story" / "camp_talks.json")
    rows = [talk_words(t) for t in talks if isinstance(t, dict)]
    tot = [r["total"] for r in rows]
    q = statistics.quantiles(tot, n=10) if len(tot) >= 10 else tot
    lines = [f"# Camp talk word audit ({len(rows)} talks{', authored and generated' if a.all else ', authored'})", "",
             f"Words a player reads per talk: median {statistics.median(tot):.0f}, 90th percentile {q[-1]:.0f}, "
             f"max {max(tot)}. Beats per talk: median {statistics.median(r['beats'] for r in rows):.0f}. "
             f"Narration is {sum(r['narration'] for r in rows) / max(1, sum(tot)):.0%} of all words.", "",
             f"## The {a.top} longest", "", "| Talk | Title | Beats | Narration | Spoken | Answers | Total | Longest line |",
             "|---|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: -r["total"])[: a.top]:
        lines.append(f"| `{r['id']}` | {r['title']} | {r['beats']} | {r['narration']} | {r['spoken']} | {r['answers']} | {r['total']} | {r['longestLine']} |")
    text = "\n".join(lines) + "\n"
    if a.md:
        Path(a.md).parent.mkdir(parents=True, exist_ok=True)
        Path(a.md).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
