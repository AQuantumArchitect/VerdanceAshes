#!/usr/bin/env python3
"""Molecule → doctrine readout D(u) — Stage 1 shadow.

SSOT temperament: data/story/hero_umwelt.json
Hand doctrine:    data/story/hero_codex.json + IntentResolver DOCTRINE profiles
Shadow face:      outbox/molecule_doctrine_shadow.json

Law: shadow only. Never --live. Codex hard gates (Kiln no-bail) stay overrides.

Usage:
  python tools/molecule_doctrine_v1.py table
  python tools/molecule_doctrine_v1.py apply --shadow
  python tools/molecule_doctrine_v1.py diff
  python tools/molecule_doctrine_v1.py smoke
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
HERO_PATH = ROOT / "data" / "story" / "hero_umwelt.json"
CODEX_PATH = ROOT / "data" / "story" / "hero_codex.json"
SHADOW_PATH = ROOT / "outbox" / "molecule_doctrine_shadow.json"
LUA_PATH = (
    ROOT
    / "mod"
    / "VerdanceAshes.sdd"
    / "luarules"
    / "gadgets"
    / "include"
    / "va_molecule_doctrine.lua"
)
SCHEMA = "verdance-molecule-doctrine-shadow/1.0"

AXES = [
    "energy",
    "offense",
    "mobility",
    "sight",
    "pad",
    "craft",
    "heat",
    "fog",
    "sky",
    "ledger",
]

# Mirrored from va_intent_resolver.lua M.DOCTRINE (hand profiles).
HAND_PROFILES: dict[str, dict[str, Any]] = {
    "phobos": {
        "squad": "frontline",
        "kiteBias": 0.95,
        "bailBias": 0.95,
        "craftBias": 0.20,
        "pushBias": 0.50,
        "flock": True,
    },
    "rez": {
        "squad": "soak",
        "kiteBias": 0.30,
        "bailBias": 0.70,
        "craftBias": 1.00,
        "pushBias": 0.10,
        "flock": False,
    },
    "skirm": {
        "squad": "skirm",
        "kiteBias": 1.05,
        "bailBias": 1.00,
        "craftBias": 0.10,
        "pushBias": 0.65,
        "flock": False,
    },
    "line": {
        "squad": "frontline",
        "kiteBias": 0.55,
        "bailBias": 0.85,
        "craftBias": 0.15,
        "pushBias": 0.55,
        "flock": False,
    },
    "kiln": {
        "squad": "siege",
        "kiteBias": 0.02,
        "bailBias": 0.02,
        "craftBias": 0.0,
        "pushBias": 1.25,
        "flock": False,
        "preferDefenses": True,
        "allowKite": False,
        "allowBail": False,
    },
    "siege_plod": {
        "squad": "siege",
        "kiteBias": 0.08,
        "bailBias": 0.25,
        "craftBias": 0.0,
        "pushBias": 1.05,
        "flock": False,
        "preferDefenses": True,
        "allowKite": False,
        "allowBail": True,
    },
    "arty": {
        "squad": "backline",
        "kiteBias": 0.85,
        "bailBias": 0.80,
        "craftBias": 0.0,
        "pushBias": 0.20,
        "flock": False,
        "preferDefenses": True,
        "allowKite": True,
        "allowBail": True,
    },
    "fog_siege": {
        "squad": "backline",
        "kiteBias": 1.00,
        "bailBias": 0.90,
        "craftBias": 0.0,
        "pushBias": 0.18,
        "flock": False,
        "preferDefenses": True,
        "allowKite": True,
        "allowBail": True,
    },
    "aa_saint": {
        "squad": "soak",
        "kiteBias": 0.25,
        "bailBias": 0.75,
        "craftBias": 0.10,
        "pushBias": 0.15,
        "flock": False,
    },
    "pad": {
        "squad": "soak",
        "kiteBias": 0.15,
        "bailBias": 0.70,
        "craftBias": 0.35,
        "pushBias": 0.05,
        "flock": False,
    },
    "dirty": {
        "squad": "skirm",
        "kiteBias": 0.70,
        "bailBias": 0.90,
        "craftBias": 0.55,
        "pushBias": 0.45,
        "flock": False,
    },
    "hive": {
        "squad": "soak",
        "kiteBias": 0.20,
        "bailBias": 0.15,
        "craftBias": 1.05,
        "pushBias": 0.40,
        "flock": False,
        "allowKite": False,
        "allowBail": False,
    },
    "constructor": {
        "squad": "soak",
        "kiteBias": 0.40,
        "bailBias": 0.80,
        "craftBias": 0.95,
        "pushBias": 0.15,
        "flock": False,
    },
    "eco_heart": {
        "squad": "soak",
        "kiteBias": 0.05,
        "bailBias": 0.60,
        "craftBias": 0.50,
        "pushBias": 0.0,
        "flock": False,
        "allowKite": False,
    },
    "eyes": {
        "squad": "skirm",
        "kiteBias": 1.10,
        "bailBias": 1.05,
        "craftBias": 0.15,
        "pushBias": 0.20,
        "flock": False,
    },
    "default": {
        "squad": "frontline",
        "kiteBias": 0.70,
        "bailBias": 0.95,
        "craftBias": 0.30,
        "pushBias": 0.45,
        "flock": False,
    },
}

BIAS_KEYS = ("kiteBias", "bailBias", "craftBias", "pushBias")
GATE_KEYS = ("preferDefenses", "allowBail", "allowKite")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clamp(v: float, lo: float = 0.0, hi: float = 1.35) -> float:
    return max(lo, min(hi, v))


def _round(v: float, n: int = 3) -> float:
    return round(float(v), n)


def load_umwelt(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or HERO_PATH).read_text(encoding="utf-8-sig"))


def load_codex(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or CODEX_PATH).read_text(encoding="utf-8-sig"))


def axes_of(hero: dict[str, Any]) -> dict[str, float]:
    raw = hero.get("axes") or {}
    return {a: float(raw.get(a, 0.0) or 0.0) for a in AXES}


def hand_for_hero(codex_row: dict[str, Any] | None) -> dict[str, Any]:
    """Merged hand doctrine: profile(kind) + per-hero gates/verb."""
    row = codex_row or {}
    kind = str(row.get("doctrine") or "default")
    base = dict(HAND_PROFILES.get(kind) or HAND_PROFILES["default"])
    out: dict[str, Any] = {
        "kind": kind,
        "kiteBias": float(base.get("kiteBias", 0.7)),
        "bailBias": float(base.get("bailBias", 0.95)),
        "craftBias": float(base.get("craftBias", 0.3)),
        "pushBias": float(base.get("pushBias", 0.45)),
        "flock": bool(base.get("flock", False)),
        "squad": str(base.get("squad") or "frontline"),
        "preferDefenses": bool(
            row["preferDefenses"]
            if "preferDefenses" in row
            else base.get("preferDefenses", False)
        ),
        "allowBail": bool(
            row["allowBail"] if "allowBail" in row else base.get("allowBail", True)
        ),
        "allowKite": bool(
            row["allowKite"] if "allowKite" in row else base.get("allowKite", True)
        ),
        "verb": str(row.get("combatVerb") or base.get("verb") or "hold"),
    }
    return out


def derive_naive(axes: dict[str, float]) -> dict[str, Any]:
    """D(u) from molecule alone — Stage 1 shadow mapping."""
    mob = axes["mobility"]
    pad = axes["pad"]
    off = axes["offense"]
    heat = axes["heat"]
    ene = axes["energy"]
    craft = axes["craft"]
    sight = axes["sight"]
    fog = axes["fog"]
    sky = axes["sky"]
    ledger = axes["ledger"]

    kite = 0.55 + 0.40 * mob - 0.35 * pad + 0.05 * sight
    bail = 0.72 + 0.18 * mob - 0.12 * pad - 0.40 * max(0.0, heat) - 0.12 * max(0.0, off - ene)
    craft_b = 0.18 + 0.50 * craft + 0.28 * ene - 0.18 * max(0.0, off) - 0.10 * max(0.0, heat)
    push = 0.38 + 0.38 * off + 0.32 * heat - 0.28 * ene - 0.18 * pad + 0.08 * max(0.0, -craft)

    prefer_def = (pad >= 0.55) or (heat >= 0.45 and off >= 0.45) or (
        pad >= 0.35 and off >= 0.55
    )
    # mobility-led kite permission; pad/heat-hunger refuse kite
    allow_kite = (mob >= -0.15) and (pad < 0.75) and (heat < 0.65)
    allow_bail = True

    # Kiln = heat-hunger *plod* (need −mobility). Mira (+heat +off, mob≥0) is arty, not kiln.
    kilnish = heat >= 0.5 and off >= 0.5 and ene <= 0.05 and mob <= -0.4
    # Arty / sparkle: heat+offense with room to kite (not pad-plod).
    artyish = heat >= 0.5 and off >= 0.4 and mob >= -0.1 and pad <= 0.1 and not kilnish
    hivish = craft >= 0.85 and pad >= 0.4 and mob <= -0.2 and off <= 0.2
    notes: list[str] = []

    if kilnish:
        notes.append("kilnish: +heat/+off/−ene/−mob → no kite/bail, push up, preferDefenses")
        allow_kite = False
        allow_bail = False
        prefer_def = True
        push = max(push, 1.10)
        kite = min(kite, 0.08)
        bail = min(bail, 0.08)
        craft_b = min(craft_b, 0.05)

    if artyish:
        notes.append("artyish: +heat/+off with kite room → preferDefenses, soft push, keep kite")
        prefer_def = True
        push = min(push, 0.35)
        kite = max(kite, 0.70)
        bail = max(bail, 0.65)

    if hivish and not kilnish:
        notes.append("hivish: +craft/+pad/−mob → low bail/kite, craft up")
        allow_kite = False
        allow_bail = False
        craft_b = max(craft_b, 0.95)
        kite = min(kite, 0.25)
        bail = min(bail, 0.20)

    # Preferred verb from dominant temperament (naive)
    scores = {
        "kite": mob - pad + 0.2 * sight,
        "hold": pad - mob + 0.15 * ene,
        "push": off + 0.3 * heat - 0.2 * ene,
        "plod": heat + 0.4 * off + 0.3 * pad - ene,
        "craft": craft + 0.5 * ene - 0.3 * off,
        "hide": fog + 0.4 * sight - 0.2 * pad,
        "snipe": sight + 0.3 * mob - 0.2 * pad,
        "grow": craft + pad - mob,
        "sparkle": heat * 0.5 + sight * 0.3 + (1.0 if prefer_def and kite > 0.5 else 0.0),
    }
    if sky >= 0.6:
        scores["kite"] += 0.25
    if ledger >= 0.5:
        scores["push"] += 0.1
    if ene >= 0.5 and off <= 0 and pad >= 0.5:
        scores["hold"] += 0.55  # eco-heart stay, not hive-grow
    if artyish:
        scores["sparkle"] += 0.8
        scores["plod"] -= 0.5
    if kilnish:
        scores["plod"] += 1.0
    verb = max(scores, key=scores.get)

    scout_mark = _clamp(0.5 + 0.45 * (sight + fog), 0.0, 1.0)

    return {
        "kiteBias": _round(_clamp(kite)),
        "bailBias": _round(_clamp(bail)),
        "craftBias": _round(_clamp(craft_b)),
        "pushBias": _round(_clamp(push)),
        "preferDefenses": bool(prefer_def),
        "allowBail": bool(allow_bail),
        "allowKite": bool(allow_kite),
        "verb": verb,
        "flock": bool(mob >= 0.7 and pad <= -0.5 and off >= 0.4),
        "scoutMarkBias": _round(scout_mark),
        "kilnish": bool(kilnish),
        "artyish": bool(artyish),
        "hivish": bool(hivish),
        "notes": notes,
    }


def apply_codex_gates(
    derived: dict[str, Any], hand: dict[str, Any]
) -> dict[str, Any]:
    """Sacred hard gates from hand/codex win; biases stay molecule-derived."""
    out = dict(derived)
    out["allowBail"] = bool(hand["allowBail"])
    out["allowKite"] = bool(hand["allowKite"])
    # preferDefenses: if hand insists True (siege/pad/kiln), keep; else molecule
    if hand.get("preferDefenses") is True:
        out["preferDefenses"] = True
    # Kiln / hive identity: if hand forbids bail/kite, clamp biases to match story
    if hand["allowKite"] is False:
        out["kiteBias"] = _round(min(float(out["kiteBias"]), 0.15))
    if hand["allowBail"] is False:
        out["bailBias"] = _round(min(float(out["bailBias"]), 0.15))
    if hand.get("kind") == "kiln":
        out["pushBias"] = _round(max(float(out["pushBias"]), 1.10))
        out["preferDefenses"] = True
        out.setdefault("notes", [])
        if isinstance(out["notes"], list):
            out["notes"] = list(out["notes"]) + ["codex kiln gates applied"]
    if hand.get("kind") == "hive":
        out["craftBias"] = _round(max(float(out["craftBias"]), 0.95))
        out.setdefault("notes", [])
        if isinstance(out["notes"], list):
            out["notes"] = list(out["notes"]) + ["codex hive gates applied"]
    # Verb: keep molecule suggestion but annotate hand verb separately
    out["handVerb"] = hand.get("verb")
    return out


def _delta(hand: dict[str, Any], gated: dict[str, Any]) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for k in BIAS_KEYS:
        d[k] = _round(float(hand.get(k, 0)) - float(gated.get(k, 0)))
    for k in GATE_KEYS:
        hv = bool(hand.get(k))
        gv = bool(gated.get(k))
        if hv != gv:
            d[k] = {"hand": hv, "derived": gv}
    if hand.get("verb") != gated.get("verb"):
        d["verb"] = {"hand": hand.get("verb"), "derived": gated.get("verb")}
    return d


def build_shadow(
    *,
    umwelt: dict[str, Any] | None = None,
    codex: dict[str, Any] | None = None,
) -> dict[str, Any]:
    umwelt = umwelt or load_umwelt()
    codex = codex or load_codex()
    by_codex = {
        str(h["heroId"]): h
        for h in (codex.get("heroes") or [])
        if isinstance(h, dict) and h.get("heroId")
    }
    rows: list[dict[str, Any]] = []
    for hero in umwelt.get("heroes") or []:
        if not isinstance(hero, dict) or not hero.get("heroId"):
            continue
        hid = str(hero["heroId"])
        ax = axes_of(hero)
        hand = hand_for_hero(by_codex.get(hid))
        naive = derive_naive(ax)
        gated = apply_codex_gates(naive, hand)
        delta = _delta(hand, gated)
        abs_bias = sum(abs(float(delta.get(k, 0))) for k in BIAS_KEYS)
        rows.append(
            {
                "heroId": hid,
                "name": hero.get("name") or by_codex.get(hid, {}).get("name") or hid,
                "glyph": hero.get("glyph"),
                "doctrine": hand.get("kind"),
                "axes": {a: _round(ax[a]) for a in AXES},
                "hand": {
                    k: hand[k]
                    for k in (
                        "kind",
                        "kiteBias",
                        "bailBias",
                        "craftBias",
                        "pushBias",
                        "preferDefenses",
                        "allowBail",
                        "allowKite",
                        "verb",
                        "flock",
                        "squad",
                    )
                },
                "derived": {
                    k: naive[k]
                    for k in (
                        "kiteBias",
                        "bailBias",
                        "craftBias",
                        "pushBias",
                        "preferDefenses",
                        "allowBail",
                        "allowKite",
                        "verb",
                        "flock",
                        "scoutMarkBias",
                        "kilnish",
                        "artyish",
                        "hivish",
                    )
                    if k in naive
                },
                "derivedGated": {
                    k: gated[k]
                    for k in (
                        "kiteBias",
                        "bailBias",
                        "craftBias",
                        "pushBias",
                        "preferDefenses",
                        "allowBail",
                        "allowKite",
                        "verb",
                        "scoutMarkBias",
                    )
                    if k in gated
                },
                "delta": delta,
                "absBiasDelta": _round(abs_bias),
                "notes": list(naive.get("notes") or [])
                + [n for n in (gated.get("notes") or []) if n not in (naive.get("notes") or [])],
            }
        )
    rows.sort(key=lambda r: (-float(r["absBiasDelta"]), str(r["heroId"])))
    return {
        "schemaVersion": SCHEMA,
        "mode": "shadow",
        "generatedAt": _now_iso(),
        "mapping": {
            "+mobility -pad": "↑kiteBias, ↓preferDefenses",
            "+pad -mobility": "↓kiteBias, ↑preferDefenses / hold",
            "+offense +heat -energy": "↑pushBias, kiln-ish gates",
            "+craft +energy": "↑craftBias",
            "+sight +fog": "scoutMarkBias (data only)",
            "codexGates": "allowBail/allowKite/kiln/hive override derived",
        },
        "liveCombat": False,
        "heroCount": len(rows),
        "heroes": rows,
    }


def write_shadow(doc: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    doc = doc or build_shadow()
    out = path or SHADOW_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _lua_bool(v: Any) -> str:
    return "true" if bool(v) else "false"


def write_lua(doc: dict[str, Any] | None = None, path: Path | None = None) -> Path:
    """Emit Stage 4 D(u) cache for soft blend / shadow compare. Regenerated; do not hand-edit."""
    doc = doc or build_shadow()
    out = path or LUA_PATH
    lines = [
        "-- Verdance molecule doctrine D(u) cache (GENERATED by tools/molecule_doctrine_v1.py apply --shadow).",
        "-- Soft-blend source for va_molecule_policy=soft. Hard gates still come from hand/codex at runtime.",
        "-- Do not hand-edit.",
        "",
        "local M = {}",
        "",
        f'M.SCHEMA = "{SCHEMA}"',
        f'M.GENERATED_AT = "{doc.get("generatedAt", "")}"',
        "M.SOFT_ALPHA = 0.28  -- Stage 4 default blend toward D(u) when mode=soft",
        "",
        "M.DERIVED = {",
    ]
    for r in sorted(doc.get("heroes") or [], key=lambda x: str(x.get("heroId") or "")):
        hid = str(r.get("heroId") or "")
        g = r.get("derivedGated") or {}
        lines.append(
            f"  {hid} = {{"
            f" kiteBias = {float(g.get('kiteBias', 0.7)):.3f},"
            f" bailBias = {float(g.get('bailBias', 0.7)):.3f},"
            f" craftBias = {float(g.get('craftBias', 0.3)):.3f},"
            f" pushBias = {float(g.get('pushBias', 0.45)):.3f},"
            f" preferDefenses = {_lua_bool(g.get('preferDefenses'))},"
            f" allowBail = {_lua_bool(g.get('allowBail'))},"
            f" allowKite = {_lua_bool(g.get('allowKite'))},"
            f" }},"
        )
    lines.extend(
        [
            "}",
            "",
            "function M.forHero(heroId)",
            '  heroId = tostring(heroId or "")',
            "  return M.DERIVED[heroId]",
            "end",
            "",
            "return M",
            "",
        ]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def cmd_table(_args: argparse.Namespace) -> int:
    doc = build_shadow()
    print(
        f"{'hero':12} {'kind':12} {'hand kite/push/craft':22} "
        f"{'D(u) kite/push/craft':22} {'|Δ|':6} gates"
    )
    print("-" * 100)
    for r in doc["heroes"]:
        h = r["hand"]
        g = r["derivedGated"]
        hand_s = f"{h['kiteBias']:.2f}/{h['pushBias']:.2f}/{h['craftBias']:.2f}"
        der_s = f"{g['kiteBias']:.2f}/{g['pushBias']:.2f}/{g['craftBias']:.2f}"
        gate_bits = []
        if h["allowBail"] != g["allowBail"] or h["allowKite"] != g["allowKite"]:
            gate_bits.append("gateΔ")
        if h["preferDefenses"] != g["preferDefenses"]:
            gate_bits.append("defΔ")
        if r.get("notes"):
            gate_bits.append(";".join(r["notes"])[:40])
        print(
            f"{r['heroId']:12} {str(r['doctrine']):12} {hand_s:22} {der_s:22} "
            f"{r['absBiasDelta']:6.2f} {' '.join(gate_bits)}"
        )
    print(f"# {doc['heroCount']} heroes · shadow only · no live combat")
    # Sanity pins
    by = {r["heroId"]: r for r in doc["heroes"]}
    pins = []
    b = by.get("brakhov")
    if b:
        g = b["derivedGated"]
        ok = (g["allowBail"] is False and g["allowKite"] is False and g["pushBias"] >= 1.0)
        pins.append(("Kiln gates", ok, f"push={g['pushBias']} bail={g['allowBail']} kite={g['allowKite']}"))
    v = by.get("vane")
    if v:
        g = v["derivedGated"]
        ok = g["kiteBias"] >= 0.85
        pins.append(("Vane kite", ok, f"kite={g['kiteBias']}"))
    hh = by.get("hearth")
    if hh:
        g = hh["derivedGated"]
        ok = g["kiteBias"] <= 0.25 and g["pushBias"] <= 0.25
        pins.append(("Hearth hold", ok, f"kite={g['kiteBias']} push={g['pushBias']}"))
    print("\nSanity pins:")
    for name, ok, detail in pins:
        print(f"  [{'OK' if ok else 'WARN'}] {name}: {detail}")
    return 0 if all(p[1] for p in pins) else 1


def cmd_apply(args: argparse.Namespace) -> int:
    if getattr(args, "live", False):
        print(
            "REFUSED: --live still means replacing hand doctrine wholesale. "
            "Use apply --shadow (emits D(u) cache) and in-game va_molecule_policy=soft.",
            file=sys.stderr,
        )
        return 2
    if not getattr(args, "shadow", False):
        print("Specify --shadow. Example: apply --shadow", file=sys.stderr)
        return 2
    doc = build_shadow()
    path = write_shadow(doc)
    lua = write_lua(doc)
    print(f"Wrote shadow face: {path}")
    print(f"Wrote D(u) lua cache: {lua}")
    print(f"heroes={doc['heroCount']} mode={doc['mode']} liveCombat={doc['liveCombat']}")
    return 0


def cmd_diff(_args: argparse.Namespace) -> int:
    if not SHADOW_PATH.is_file():
        write_shadow()
        print(f"(created missing shadow face at {SHADOW_PATH})")
    doc = json.loads(SHADOW_PATH.read_text(encoding="utf-8"))
    # Highlight largest disagreements
    rows = sorted(doc.get("heroes") or [], key=lambda r: -float(r.get("absBiasDelta") or 0))
    print("Top |hand − D(u)_gated| bias disagreements:")
    print(f"{'hero':12} {'|Δ|':6} {'Δkite':7} {'Δpush':7} {'Δcraft':7} {'Δbail':7} notes")
    for r in rows[:15]:
        d = r.get("delta") or {}
        notes = ";".join(r.get("notes") or [])[:48]
        print(
            f"{r['heroId']:12} {r.get('absBiasDelta', 0):6.2f} "
            f"{float(d.get('kiteBias', 0)):+7.2f} "
            f"{float(d.get('pushBias', 0)):+7.2f} "
            f"{float(d.get('craftBias', 0)):+7.2f} "
            f"{float(d.get('bailBias', 0)):+7.2f} {notes}"
        )
    # Gate mismatches
    gate_miss = [
        r
        for r in rows
        if any(k in (r.get("delta") or {}) for k in GATE_KEYS)
    ]
    if gate_miss:
        print(f"\nGate mismatches (hand vs gated derived): {len(gate_miss)}")
        for r in gate_miss[:10]:
            d = r["delta"]
            bits = [f"{k}={d[k]}" for k in GATE_KEYS if k in d]
            print(f"  {r['heroId']}: {', '.join(bits)}")
    else:
        print("\nGate mismatches: none (codex gates applied cleanly)")
    return 0


def cmd_smoke(_args: argparse.Namespace) -> int:
    doc = build_shadow()
    path = write_shadow(doc)
    by = {r["heroId"]: r for r in doc["heroes"]}
    checks = []
    # Kiln
    b = by["brakhov"]
    g = b["derivedGated"]
    checks.append(("kiln_no_bail", g["allowBail"] is False))
    checks.append(("kiln_no_kite", g["allowKite"] is False))
    checks.append(("kiln_push", g["pushBias"] >= 1.0))
    checks.append(("kiln_prefer_def", g["preferDefenses"] is True))
    checks.append(("kiln_flag", by["brakhov"]["derived"].get("kilnish") is True))
    # Mira must NOT collapse into kiln
    m = by["mira"]
    checks.append(("mira_not_kiln", m["derived"].get("kilnish") is not True))
    checks.append(("mira_kite", m["derivedGated"]["kiteBias"] >= 0.65))
    checks.append(("mira_soft_push", m["derivedGated"]["pushBias"] <= 0.45))
    # Phobos / Hearth
    checks.append(("vane_kite", by["vane"]["derivedGated"]["kiteBias"] >= 0.85))
    checks.append(("hearth_low_kite", by["hearth"]["derivedGated"]["kiteBias"] <= 0.25))
    checks.append(("hearth_low_push", by["hearth"]["derivedGated"]["pushBias"] <= 0.25))
    # Schema / count
    checks.append(("hero_count", doc["heroCount"] == 35))
    checks.append(("shadow_mode", doc["mode"] == "shadow" and doc["liveCombat"] is False))
    checks.append(("file_written", path.is_file()))
    # --live refusal
    class _A:
        live = True
        shadow = False

    refused = cmd_apply(_A()) == 2
    checks.append(("live_refused", refused))

    ok = all(v for _, v in checks)
    print(json.dumps({"ok": ok, "path": str(path), "checks": dict(checks)}, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Molecule → doctrine D(u) shadow readout")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("table", help="Print hand vs D(u) table + sanity pins")
    sub.add_parser("diff", help="Show largest hand vs shadow disagreements")
    sub.add_parser("smoke", help="Write shadow + assert Kiln/Vane/Hearth pins")

    ap = sub.add_parser("apply", help="Write shadow face (never live)")
    ap.add_argument(
        "--shadow",
        action="store_true",
        help="Write outbox/molecule_doctrine_shadow.json",
    )
    ap.add_argument(
        "--live",
        action="store_true",
        help="REFUSED until Stage 4 — kept so CLI documents the gate",
    )

    args = p.parse_args(argv)
    if args.cmd == "table":
        return cmd_table(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "apply":
        return cmd_apply(args)
    if args.cmd == "smoke":
        return cmd_smoke(args)
    p.error(f"unknown cmd {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
