#!/usr/bin/env python3
"""Support Web — parametric Fire Emblem-style relationship graph + camp-talk stubs.

SSOT output: data/story/support_web.json
  generate / list / chart / talks / seeds / apply

Chemistry is derived from hero_codex temperament × position × doctrine.
Authored seeds always win over pure scores (Vane↔Ketha, Mira↔Kettle, …).
Camp talks stay stubs here — hub/kernel wiring is a later pass.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
CODEX_PATH = ROOT / "data" / "story" / "hero_codex.json"
WEB_PATH = ROOT / "data" / "story" / "support_web.json"
TALKS_PATH = ROOT / "data" / "story" / "camp_talks.json"
AUTHORED_TALKS_PATH = ROOT / "data" / "story" / "camp_talks_authored.json"
UMWELT_PATH = ROOT / "data" / "story" / "hero_umwelt.json"
CHART_MD = ROOT / "docs" / "SUPPORT_WEB.md"
UMWELT_MD = ROOT / "docs" / "HERO_UMWELT.md"
EMBED_JS = ROOT / "app" / "showoff" / "support_web.embed.js"
TALKS_EMBED_JS = ROOT / "app" / "showoff" / "camp_talks.embed.js"
UMWELT_EMBED_JS = ROOT / "app" / "showoff" / "hero_umwelt.embed.js"

# Uexküll-style carriers of significance — compact "icon molecule" per hero.
# Values in [-1, +1]. SpaceWheat cognifold rhyme: readable polarity face, not a god-brain.
UMWELT_AXES = (
    "energy",  # + supply / - hunger (Hearth vs Kiln)
    "offense",  # + push defenses / - refuse the wall
    "mobility",  # + kite-move / - stay-pad
    "sight",  # + recon marks / spotter
    "pad",  # + hold home circle / siege face
    "craft",  # + build/rez/grow
    "heat",  # + fire / riot
    "fog",  # + stealth / hide / spotter haze
    "sky",  # + air domain
    "ledger",  # + count/contract/debt
)

SCHEMA = "verdance-support-web/1.0"
TALKS_SCHEMA = "verdance-camp-talks/1.0"

# Complementary temperament pairs → (polarity, motif)
COMPLEMENTS: Dict[frozenset, Tuple[str, str]] = {
    frozenset({"heat", "plod"}): ("friction", "fire meets weight"),
    frozenset({"gleeful", "saint"}): ("attract", "joy needs a ceiling"),
    frozenset({"fog", "glass"}): ("friction", "hide vs shatter"),
    frozenset({"debt", "contract"}): ("mirror", "two ledgers"),
    frozenset({"captain", "swarm"}): ("mentor", "one thought, many legs"),
    frozenset({"door", "pad"}): ("attract", "threshold and hearth"),
    frozenset({"sky", "garden"}): ("attract", "altitude feeds roots"),
    frozenset({"mischief", "count"}): ("friction", "chaos vs ledger"),
    frozenset({"heat", "fog"}): ("friction", "roast vs invoice"),
    frozenset({"plod", "glass"}): ("friction", "anvil vs kite"),
    frozenset({"saint", "debt"}): ("attract", "tithe and arrears"),
    frozenset({"captain", "door"}): ("mentor", "orders at the gate"),
    frozenset({"gleeful", "heat"}): ("mirror", "two kinds of burn"),
    frozenset({"swarm", "garden"}): ("mirror", "grow vs mint"),
    frozenset({"sky", "fog"}): ("attract", "ceiling and veil"),
    frozenset({"captain", "glass"}): ("mentor", "pack and brittle edge"),
    frozenset({"plod", "pad"}): ("attract", "weight that stays"),
    frozenset({"mischief", "gleeful"}): ("mirror", "grins that escalate"),
    frozenset({"heat", "sky"}): ("friction", "burn the ceiling"),
    frozenset({"count", "contract"}): ("mirror", "math and invoice"),
    frozenset({"door", "plod"}): ("attract", "hinge and weight"),
    frozenset({"fog", "mischief"}): ("attract", "tricks in the haze"),
    frozenset({"saint", "pad"}): ("attract", "holy furniture"),
    frozenset({"swarm", "glass"}): ("friction", "many vs one thin"),
}

# Doctrine drama — signature rivalries / partnerships
DOCTRINE_DRAMA: Dict[frozenset, Tuple[str, str, float]] = {
    frozenset({"kiln", "fog_siege"}): ("rivalry", "roast vs soft invoice", 0.55),
    frozenset({"arty", "aa_saint"}): ("bond", "fireworks need a clear sky", 0.50),
    frozenset({"phobos", "line"}): ("tension", "flock vs tread command", 0.35),
    frozenset({"eco_heart", "constructor"}): ("bond", "stay-burn vs build-out", 0.30),
    frozenset({"skirm", "line"}): ("tension", "kite vs hold", 0.25),
    frozenset({"kiln", "siege_plod"}): ("mirror", "two ways to arrive", 0.28),
    frozenset({"pad", "aa_saint"}): ("bond", "dirt circle and sky hymn", 0.32),
    frozenset({"hive", "eyes"}): ("tension", "grow quiet vs see loud", 0.22),
    frozenset({"dirty", "pad"}): ("friction", "mines vs owned dirt", 0.30),
    frozenset({"skirm", "arty"}): ("bond", "close confetti and far confetti", 0.40),
}

# Same-position workplace flavor
POSITION_FLAVOR = {
    "line": ("sibling", "same dirt, different hinge"),
    "skirmish": ("rivalry", "who kites cleaner"),
    "siege": ("rivalry", "who owns the wall"),
    "eyes": ("sibling", "shared fog payroll"),
    "eco": ("sibling", "shared ledger of sun"),
    "shield": ("sibling", "same circle, different tooth"),
    "core_skirm": ("mentor", "pack heart"),
    "core_rez": ("mentor", "life-line"),
}

# Authored seeds — always present, override polarity/motif/score floor
AUTHOR_SEEDS: List[Dict[str, Any]] = [
    {
        "a": "vane",
        "b": "ketha",
        "polarity": "bond",
        "motif": "captain and unfinished sentences",
        "score": 0.95,
        "authored": True,
        "talkTitle": "Pack memory",
    },
    {
        "a": "mira",
        "b": "kettle",
        "polarity": "bond",
        "motif": "fireworks need a clear sky",
        "score": 0.88,
        "authored": True,
        "talkTitle": "Ceiling for confetti",
    },
    {
        "a": "brakhov",
        "b": "vale",
        "polarity": "rivalry",
        "motif": "roast vs soft invoice",
        "score": 0.86,
        "authored": True,
        "talkTitle": "Heat and the bill",
    },
    {
        "a": "mira",
        "b": "kit",
        "polarity": "mirror",
        "motif": "parade and walking fireworks",
        "score": 0.82,
        "authored": True,
        "talkTitle": "Two confettis",
    },
    {
        "a": "grath",
        "b": "nox",
        "polarity": "mirror",
        "motif": "wages and weather arrears",
        "score": 0.80,
        "authored": True,
        "talkTitle": "Two debts",
    },
    {
        "a": "vane",
        "b": "quill",
        "polarity": "tension",
        "motif": "flock captain vs tread marshal",
        "score": 0.78,
        "authored": True,
        "talkTitle": "Who gives the order",
    },
    {
        "a": "hearth",
        "b": "lumen",
        "polarity": "bond",
        "motif": "coal furniture and grid saint",
        "score": 0.76,
        "authored": True,
        "talkTitle": "Quiet suns",
    },
    {
        "a": "noctua",
        "b": "ceil",
        "polarity": "tension",
        "motif": "flight paths vs gunship manners",
        "score": 0.74,
        "authored": True,
        "talkTitle": "Altitude arguments",
    },
    {
        "a": "rusk",
        "b": "odessa",
        "polarity": "sibling",
        "motif": "gate door and ford door",
        "score": 0.72,
        "authored": True,
        "talkTitle": "Two hinges",
    },
    {
        "a": "brakhov",
        "b": "anvil",
        "polarity": "mirror",
        "motif": "roast plod and wet plod",
        "score": 0.70,
        "authored": True,
        "talkTitle": "Ways of arriving",
    },
    {
        "a": "veil",
        "b": "volt",
        "polarity": "friction",
        "motif": "fog payroll vs lightning wound",
        "score": 0.68,
        "authored": True,
        "talkTitle": "See or hide",
    },
    {
        "a": "spoke",
        "b": "tick",
        "polarity": "sibling",
        "motif": "wheels and plurals",
        "score": 0.66,
        "authored": True,
        "talkTitle": "How eyes multiply",
    },
]

POLARITY_OPENERS = {
    "bond": (
        "{a} keeps the quiet. {b} fills it.",
        "You two keep finding the same fire.",
    ),
    "rivalry": (
        "{a} does not blink first. Neither does {b}.",
        "Same wall. Different religion.",
    ),
    "friction": (
        "{a}'s method scrapes {b}'s.",
        "The camp hears the argument before the words.",
    ),
    "mirror": (
        "Same ledger, different ink.",
        "Looking at {b}, {a} almost recognizes a face.",
    ),
    "mentor": (
        "{a} sets the pace. {b} learns the cost.",
        "Orders travel farther when someone younger carries them.",
    ),
    "sibling": (
        "Same dirt. Different scar.",
        "You argue like people who already shared a trench.",
    ),
    "tension": (
        "The room gets smaller when both of you stand in it.",
        "Not enemies. Not easy.",
    ),
    "attract": (
        "Something in {a} makes {b} stay one more minute.",
        "The hearth notices before either of you does.",
    ),
}


def load_codex(path: Path = CODEX_PATH) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def heroes(codex: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [h for h in (codex.get("heroes") or []) if isinstance(h, dict) and h.get("heroId")]


def pair_id(a: str, b: str) -> str:
    x, y = sorted([a, b])
    return f"{x}__{y}"


def _temps(h: Dict[str, Any]) -> Set[str]:
    return {str(t) for t in (h.get("temperament") or [])}


def _clamp_axis(v: float) -> float:
    return max(-1.0, min(1.0, round(float(v), 3)))


def hero_umwelt_molecule(h: Dict[str, Any]) -> Dict[str, Any]:
    """Build a compact polarity molecule — carriers of significance for this hero.

    Uexküll: only marks that interest the organism. SpaceWheat rhyme: a readable
    cognifold-ish icon vector, not a densified god-brain.
    """
    temps = _temps(h)
    pos = str(h.get("position") or "")
    doc = str(h.get("doctrine") or "")
    verb = str(h.get("combatVerb") or "")
    axes = {k: 0.0 for k in UMWELT_AXES}

    # Position priors — what column of the war they live in
    pos_bias = {
        "eco": {"energy": 0.55, "pad": 0.35, "craft": 0.45, "offense": -0.35, "mobility": -0.25},
        "siege": {"offense": 0.55, "energy": -0.35, "heat": 0.25, "mobility": -0.2, "pad": -0.15},
        "line": {"offense": 0.25, "pad": 0.2, "mobility": -0.1},
        "skirmish": {"mobility": 0.55, "offense": 0.15, "pad": -0.35},
        "eyes": {"sight": 0.7, "fog": 0.25, "offense": -0.2, "mobility": 0.3},
        "shield": {"pad": 0.55, "offense": -0.15, "sky": 0.15},
        "core_skirm": {"mobility": 0.45, "offense": 0.2, "sight": 0.15},
        "core_rez": {"craft": 0.7, "pad": 0.25, "offense": -0.4, "mobility": -0.1},
    }
    for k, v in (pos_bias.get(pos) or {}).items():
        axes[k] += v

    # Doctrine — effector world
    doc_bias = {
        "eco_heart": {"energy": 0.85, "pad": 0.55, "mobility": -0.7, "offense": -0.55, "craft": 0.2},
        "kiln": {"energy": -0.85, "offense": 0.9, "heat": 0.8, "mobility": -0.45, "pad": -0.35, "fog": -0.4},
        "siege_plod": {"energy": -0.45, "offense": 0.65, "mobility": -0.4, "pad": 0.1},
        "arty": {"offense": 0.35, "heat": 0.45, "mobility": 0.15, "pad": -0.2, "energy": -0.25},
        "fog_siege": {"fog": 0.75, "offense": 0.35, "mobility": 0.2, "heat": -0.3, "energy": -0.2},
        "phobos": {"mobility": 0.7, "sight": 0.2, "offense": 0.25, "pad": -0.4},
        "skirm": {"mobility": 0.6, "offense": 0.2, "pad": -0.35},
        "line": {"offense": 0.3, "pad": 0.25, "mobility": -0.15},
        "eyes": {"sight": 0.75, "fog": 0.35, "mobility": 0.35, "offense": -0.15},
        "constructor": {"craft": 0.7, "energy": 0.2, "pad": 0.15, "offense": -0.25},
        "rez": {"craft": 0.85, "pad": 0.2, "offense": -0.5},
        "pad": {"pad": 0.8, "mobility": -0.5, "offense": -0.2},
        "aa_saint": {"sky": 0.75, "pad": 0.35, "offense": -0.1},
        "dirty": {"fog": 0.55, "craft": 0.25, "mobility": 0.3, "pad": -0.2},
        "hive": {"craft": 0.65, "pad": 0.3, "mobility": -0.15, "sight": -0.1},
    }
    for k, v in (doc_bias.get(doc) or {}).items():
        axes[k] += v

    # Temperament marks
    temp_bias = {
        "heat": {"heat": 0.45, "offense": 0.15},
        "plod": {"mobility": -0.4, "offense": 0.2, "pad": 0.1},
        "pad": {"pad": 0.45, "mobility": -0.25},
        "fog": {"fog": 0.5, "sight": 0.15},
        "glass": {"mobility": 0.25, "pad": -0.2},
        "gleeful": {"heat": 0.25, "mobility": 0.15},
        "saint": {"pad": 0.2, "craft": 0.15, "offense": -0.1},
        "swarm": {"craft": 0.15, "sight": 0.1},
        "garden": {"energy": 0.25, "craft": 0.25, "pad": 0.15},
        "sky": {"sky": 0.5, "mobility": 0.15},
        "debt": {"ledger": 0.45},
        "contract": {"ledger": 0.4},
        "count": {"ledger": 0.45, "sight": 0.1},
        "captain": {"offense": 0.15, "mobility": 0.1},
        "door": {"pad": 0.25, "offense": 0.1},
        "mischief": {"fog": 0.25, "craft": 0.15},
    }
    for t in temps:
        for k, v in (temp_bias.get(t) or {}).items():
            axes[k] += v

    # Combat verb
    verb_bias = {
        "plod": {"mobility": -0.35, "offense": 0.35},
        "push": {"offense": 0.4, "mobility": 0.1},
        "hold": {"pad": 0.35, "mobility": -0.25},
        "kite": {"mobility": 0.45, "pad": -0.25},
        "hide": {"fog": 0.35, "mobility": 0.2},
        "snipe": {"sight": 0.35, "mobility": 0.15, "pad": -0.15},
        "sparkle": {"heat": 0.3, "offense": 0.2},
        "craft": {"craft": 0.4},
        "grow": {"craft": 0.45, "pad": 0.15},
    }
    for k, v in (verb_bias.get(verb) or {}).items():
        axes[k] += v

    axes = {k: _clamp_axis(v) for k, v in axes.items()}
    # Dominant marks = the organism's actual umwelt (threshold)
    marks = sorted(
        ((k, v) for k, v in axes.items() if abs(v) >= 0.35),
        key=lambda kv: -abs(kv[1]),
    )
    glyph = "·".join(
        (("+" if v > 0 else "−") + k[:3]) for k, v in marks[:4]
    ) or "·idle·"
    return {
        "heroId": str(h.get("heroId")),
        "name": _name(h) if "voice" in h or h.get("name") else str(h.get("heroId")),
        "axes": axes,
        "marks": [{"axis": k, "value": v} for k, v in marks],
        "glyph": glyph,
        "position": pos,
        "doctrine": doc,
    }


def _siege_shape(axes: Dict[str, Any]) -> float:
    """Pad-committed stay face — the wall that needs eyes."""
    pad = float(axes.get("pad") or 0)
    mob = float(axes.get("mobility") or 0)
    off = float(axes.get("offense") or 0)
    if pad < 0.45 or mob > -0.2:
        return 0.0
    return pad * 0.75 + max(0.0, -mob) * 0.35 + max(0.0, off) * 0.2


def _spotter_shape(axes: Dict[str, Any]) -> float:
    """Sight/fog recon face — eyes for the wall."""
    sight = float(axes.get("sight") or 0)
    fog = float(axes.get("fog") or 0)
    if sight < 0.4 and fog < 0.45:
        return 0.0
    return max(0.0, sight) * 0.75 + max(0.0, fog) * 0.55


def umwelt_couple(
    ma: Dict[str, Any], mb: Dict[str, Any]
) -> Dict[str, Any]:
    """Functional-circle score from two molecules.

    Opposite signs on the same axis = complementary carriers (cultivate).
    Same signs = mirror resonance. Energy opposition is especially loud —
    supply meets hunger — without being an authored override.

    Cross-axis: pad-heavy siege/hold faces cultivate against sight/fog
    spotters (spot meets siege) — same soft law as energy, not a force seed.
    """
    aa = ma.get("axes") or {}
    bb = mb.get("axes") or {}
    complement = 0.0
    mirror = 0.0
    couples: List[Dict[str, Any]] = []
    for axis in UMWELT_AXES:
        va = float(aa.get(axis) or 0)
        vb = float(bb.get(axis) or 0)
        if abs(va) < 0.25 or abs(vb) < 0.25:
            continue
        if va * vb < 0:
            # Opposite polarity — functional circle
            strength = abs(va) * abs(vb)
            # Energy + offense + sight/fog opposition are high-signal war marks
            if axis == "energy":
                weight = 1.35
            elif axis == "offense":
                weight = 1.15
            elif axis in ("sight", "fog"):
                weight = 1.2
            else:
                weight = 1.0
            complement += strength * weight
            couples.append(
                {
                    "axis": axis,
                    "kind": "complement",
                    "a": va,
                    "b": vb,
                    "strength": round(strength * weight, 3),
                }
            )
        else:
            strength = abs(va) * abs(vb)
            mirror += strength * 0.55
            couples.append(
                {
                    "axis": axis,
                    "kind": "mirror",
                    "a": va,
                    "b": vb,
                    "strength": round(strength * 0.55, 3),
                }
            )

    # Cross-axis cultivation: siege/hold pad face ↔ spotter sight/fog.
    # Same-axis loop misses this because siege molecules often have ~0 sight.
    sw_a, sw_b = _siege_shape(aa), _siege_shape(bb)
    sp_a, sp_b = _spotter_shape(aa), _spotter_shape(bb)
    siege_spot_strength = 0.0
    if sw_a >= 0.35 and sp_b >= 0.35:
        siege_spot_strength = sw_a * sp_b * 1.3
        couples.append(
            {
                "axis": "siege_sight",
                "kind": "complement",
                "cross": ["pad", "sight|fog"],
                "a": round(sw_a, 3),
                "b": round(sp_b, 3),
                "strength": round(siege_spot_strength, 3),
            }
        )
        complement += siege_spot_strength
    elif sw_b >= 0.35 and sp_a >= 0.35:
        siege_spot_strength = sw_b * sp_a * 1.3
        couples.append(
            {
                "axis": "siege_sight",
                "kind": "complement",
                "cross": ["pad", "sight|fog"],
                "a": round(sp_a, 3),
                "b": round(sw_b, 3),
                "strength": round(siege_spot_strength, 3),
            }
        )
        complement += siege_spot_strength

    couples.sort(key=lambda c: -float(c["strength"]))
    # Map raw couple energy into a capped contribution. Energy + siege↔spotter
    # complements get a slightly higher ceiling so they can compete with pad
    # mirror clusters — still parametric, not an authored override.
    raw = complement * 0.55 + mirror * 0.25
    has_energy = any(
        c.get("axis") == "energy" and c.get("kind") == "complement" for c in couples
    )
    has_siege_spot = any(
        c.get("axis") == "siege_sight" and c.get("kind") == "complement" for c in couples
    )
    ceiling = 0.62 if (has_energy or has_siege_spot) else 0.55
    boost = max(0.0, min(ceiling, raw))
    polarity = "tension"
    motif = "umwelt couple"
    if couples:
        top = couples[0]
        axis = top["axis"]
        if top["kind"] == "complement":
            if axis == "energy":
                polarity = "bond"
                motif = "supply meets hunger"
            elif axis == "siege_sight":
                polarity = "attract"
                motif = "spot meets siege"
            elif axis == "offense":
                polarity = "attract"
                motif = "push meets refuse"
            elif axis == "mobility":
                polarity = "friction"
                motif = "stay meets stride"
            elif axis == "fog":
                polarity = "friction"
                motif = "haze meets glare"
            elif axis == "sight":
                polarity = "attract"
                motif = "eyes for the wall"
            else:
                polarity = "attract"
                motif = f"{axis} functional circle"
        else:
            polarity = "mirror"
            motif = f"shared {axis} mark"
    # Prefer siege↔spotter motif when that cross couple is loud enough,
    # unless energy already owns the primary mark.
    if has_siege_spot and not has_energy and siege_spot_strength >= 0.35:
        polarity = "attract"
        motif = "spot meets siege"
    return {
        "boost": round(boost, 3),
        "polarity": polarity,
        "motif": motif,
        "couples": couples[:5],
        "complement": round(complement, 3),
        "mirror": round(mirror, 3),
        "energyLocked": bool(has_energy and boost >= 0.4),
        "spotterLocked": bool(
            has_siege_spot and not has_energy and boost >= 0.4 and siege_spot_strength >= 0.35
        ),
        "siegeSpotStrength": round(siege_spot_strength, 3),
    }


def score_pair(
    ha: Dict[str, Any],
    hb: Dict[str, Any],
    *,
    mol_a: Optional[Dict[str, Any]] = None,
    mol_b: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Parametric chemistry between two heroes (tags + umwelt molecules)."""
    ta, tb = _temps(ha), _temps(hb)
    shared = sorted(ta & tb)
    pos_a = str(ha.get("position") or "")
    pos_b = str(hb.get("position") or "")
    doc_a = str(ha.get("doctrine") or "")
    doc_b = str(hb.get("doctrine") or "")

    score = 0.0
    polarity = "tension"
    motifs: List[str] = []
    reasons: List[str] = []
    umwelt_meta: Optional[Dict[str, Any]] = None

    # Umwelt molecule couple — cultivate functional circles (no authored force)
    mol_a = mol_a or hero_umwelt_molecule(ha)
    mol_b = mol_b or hero_umwelt_molecule(hb)
    couple = umwelt_couple(mol_a, mol_b)
    energy_locked = False
    spotter_locked = False
    if couple["boost"] > 0.08:
        score += float(couple["boost"])
        polarity = str(couple["polarity"])
        motifs.insert(0, str(couple["motif"]))
        reasons.append(
            f"umwelt {couple['motif']} (complement={couple['complement']})"
        )
        umwelt_meta = couple
        energy_locked = bool(couple.get("energyLocked"))
        spotter_locked = bool(couple.get("spotterLocked"))

    motif_locked = energy_locked or spotter_locked

    # Shared temperament — sibling resonance
    if shared:
        score += 0.18 * len(shared)
        motifs.append("shared:" + "+".join(shared))
        reasons.append(f"shared temperament {shared}")
        if polarity == "tension":
            polarity = "sibling" if len(shared) == 1 else "mirror"

    # Complementary tags (prefer distinctive polarities over plain sibling)
    best_comp: Optional[Tuple[str, str, float]] = None
    for t1 in ta:
        for t2 in tb:
            key = frozenset({t1, t2})
            if key in COMPLEMENTS and t1 != t2:
                pol, motif = COMPLEMENTS[key]
                # Slight preference: friction/rivalry/mentor over soft attract
                weight = {
                    "rivalry": 0.38,
                    "friction": 0.36,
                    "mentor": 0.35,
                    "mirror": 0.34,
                    "bond": 0.34,
                    "attract": 0.32,
                    "sibling": 0.30,
                    "tension": 0.30,
                }.get(pol, 0.34)
                if best_comp is None or weight > best_comp[2]:
                    best_comp = (pol, motif, weight)
    if best_comp:
        pol, motif, boost = best_comp
        score += boost
        # Strong energy / siege↔spotter umwelt couples keep primary motif
        if motif_locked:
            motifs.append(motif)
        else:
            polarity = pol
            motifs.insert(0, motif)
        reasons.append(f"complement ({motif})")

    # Same position workplace
    if pos_a and pos_a == pos_b:
        pol, motif = POSITION_FLAVOR.get(pos_a, ("sibling", "same column"))
        score += 0.14
        if polarity in ("tension", "sibling") and not best_comp:
            polarity = pol
        motifs.append(motif)
        reasons.append(f"same position {pos_a}")

    # Adjacent columns (line↔skirmish, siege↔shield, eco↔eyes, siege↔eyes, …)
    adjacent = {
        frozenset({"line", "skirmish"}),
        frozenset({"line", "siege"}),
        frozenset({"siege", "shield"}),
        frozenset({"eyes", "skirmish"}),
        frozenset({"eco", "shield"}),
        frozenset({"eco", "eyes"}),
        frozenset({"siege", "eyes"}),
        frozenset({"shield", "eyes"}),
        frozenset({"line", "eyes"}),
        frozenset({"core_skirm", "skirmish"}),
        frozenset({"core_rez", "shield"}),
        frozenset({"core_rez", "eco"}),
    }
    if frozenset({pos_a, pos_b}) in adjacent:
        score += 0.10
        reasons.append(f"adjacent columns {pos_a}/{pos_b}")

    # Doctrine drama — wins polarity + primary motif unless umwelt locked
    dkey = frozenset({doc_a, doc_b})
    if doc_a and doc_b and dkey in DOCTRINE_DRAMA:
        pol, motif, boost = DOCTRINE_DRAMA[dkey]
        score += boost
        if motif_locked:
            motifs.append(motif)
        else:
            polarity = pol
            motifs = [motif] + [m for m in motifs if m != motif]
        reasons.append(f"doctrine drama {doc_a}/{doc_b}")

    # Combat verb clash / rhyme
    va = str(ha.get("combatVerb") or "")
    vb = str(hb.get("combatVerb") or "")
    if va and vb and va == vb:
        score += 0.08
        reasons.append(f"same verb {va}")
    elif {va, vb} <= {"plod", "push", "hold"}:
        score += 0.06
        reasons.append("front-weight verbs")
    elif {va, vb} <= {"kite", "hide", "snipe", "sparkle"}:
        score += 0.06
        reasons.append("soft-edge verbs")

    # Faction rhyme
    fa = str(ha.get("faction") or "")
    fb = str(hb.get("faction") or "")
    if fa and fb and fa == fb and fa not in ("mixed", "?"):
        score += 0.05
        reasons.append(f"same faction {fa}")
    elif fa and fb and fa != fb and "mixed" not in (fa, fb):
        score += 0.04
        reasons.append("cross-faction contract tension")

    score = max(0.0, min(1.0, score))
    out = {
        "score": round(score, 3),
        "polarity": polarity,
        "motifs": motifs[:4],
        "sharedTemperament": shared,
        "reasons": reasons,
    }
    if umwelt_meta:
        out["umwelt"] = {
            "motif": umwelt_meta.get("motif"),
            "boost": umwelt_meta.get("boost"),
            "couples": umwelt_meta.get("couples") or [],
            "spotterLocked": bool(umwelt_meta.get("spotterLocked")),
            "siegeSpotStrength": umwelt_meta.get("siegeSpotStrength"),
        }
    return out


def _hook(h: Dict[str, Any]) -> str:
    return str((h.get("voice") or {}).get("hook") or h.get("name") or h.get("heroId"))


def _name(h: Dict[str, Any]) -> str:
    return str(h.get("name") or h.get("heroId"))


_RANK_BRIDGES = {
    "B": (
        "Still hearing you in the kit after the Drop.",
        "Then keep hearing it. The ash does not edit us clean.",
    ),
    "A": (
        "If the next wall takes one of us, the other finishes the work.",
        "That's not a promise. That's logistics.",
    ),
}


def make_talk_stub(
    ha: Dict[str, Any],
    hb: Dict[str, Any],
    *,
    polarity: str,
    motif: str,
    rank: str = "C",
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Parametric C/B/A camp-talk seed from voice hooks + polarity."""
    aid = str(ha["heroId"])
    bid = str(hb["heroId"])
    an, bn = _name(ha), _name(hb)
    ah, bh = _hook(ha), _hook(hb)
    openers = POLARITY_OPENERS.get(polarity, POLARITY_OPENERS["tension"])
    line0 = openers[0].format(a=an, b=bn)
    line1 = openers[1].format(a=an, b=bn)
    pos_a = str(ha.get("position") or "field")
    pos_b = str(hb.get("position") or "field")

    beats: List[Dict[str, str]] = [
        {
            "speaker": "narrator",
            "line": f"{motif.rstrip('.').capitalize()}. {line0}",
        },
        {"speaker": aid, "line": ah},
        {"speaker": bid, "line": bh},
        {
            "speaker": "narrator",
            "line": f"{pos_a} seat beside {pos_b}. {line1}",
        },
    ]

    if rank in ("B", "A"):
        b0, b1 = _RANK_BRIDGES["B"]
        beats.append({"speaker": aid, "line": b0})
        beats.append({"speaker": bid, "line": b1})
    if rank == "A":
        a0, a1 = _RANK_BRIDGES["A"]
        beats.append({"speaker": aid, "line": a0})
        beats.append({"speaker": bid, "line": a1})
        beats.append(
            {
                "speaker": "narrator",
                "line": f"Support locks. {an} and {bn} leave the hearth different.",
            }
        )

    return {
        "pairId": pair_id(aid, bid),
        "a": aid,
        "b": bid,
        "rank": rank,
        "title": title or motif[:48].title(),
        "polarity": polarity,
        "motif": motif,
        "unlock": {
            "coDeploy": 1 if rank == "C" else (2 if rank == "B" else 3),
            "campLevelMin": 0 if rank == "C" else (1 if rank == "B" else 2),
            "bondMin": 0 if rank == "C" else (25 if rank == "B" else 55),
        },
        "beats": beats,
        "generated": True,
    }


def generate_web(
    codex: Dict[str, Any],
    *,
    min_score: float = 0.42,
    max_degree: int = 5,
    top_edges: int = 64,
) -> Dict[str, Any]:
    rows = heroes(codex)
    by_id = {str(h["heroId"]): h for h in rows}
    molecules = {str(h["heroId"]): hero_umwelt_molecule(h) for h in rows}

    # Score all pairs (umwelt molecules cultivate complementary links)
    scored: List[Dict[str, Any]] = []
    for ha, hb in combinations(rows, 2):
        aid, bid = str(ha["heroId"]), str(hb["heroId"])
        chem = score_pair(
            ha, hb, mol_a=molecules[aid], mol_b=molecules[bid]
        )
        scored.append(
            {
                "a": aid,
                "b": bid,
                **chem,
            }
        )
    scored.sort(key=lambda e: (-float(e["score"]), e["a"], e["b"]))

    # Apply authored seeds (force include + override)
    seed_map = {pair_id(s["a"], s["b"]): s for s in AUTHOR_SEEDS}
    by_pair = {pair_id(e["a"], e["b"]): e for e in scored}
    for pid, seed in seed_map.items():
        a, b = seed["a"], seed["b"]
        if a not in by_id or b not in by_id:
            continue
        base = by_pair.get(pid) or {
            "a": a,
            "b": b,
            "score": 0.0,
            "polarity": "bond",
            "motifs": [],
            "sharedTemperament": [],
            "reasons": [],
        }
        base["score"] = max(float(base.get("score") or 0), float(seed["score"]))
        base["polarity"] = seed["polarity"]
        base["motifs"] = [seed["motif"]] + [
            m for m in (base.get("motifs") or []) if m != seed["motif"]
        ]
        base["authored"] = True
        base["talkTitle"] = seed.get("talkTitle")
        base["reasons"] = ["authored seed"] + list(base.get("reasons") or [])
        by_pair[pid] = base

    def _energy_cultivation(edge: Dict[str, Any]) -> float:
        """Soft tie-break: energy functional circles surface when scores tie.

        Not an authored force — only reorders near-equal parametric scores so
        supply↔hunger is not buried under alphabet/degree noise.
        """
        um = edge.get("umwelt") or {}
        for c in um.get("couples") or []:
            if c.get("axis") == "energy" and c.get("kind") == "complement":
                return float(c.get("strength") or 0)
        return 0.0

    def _spotter_cultivation(edge: Dict[str, Any]) -> float:
        """Soft tie-break: siege↔spotter circles surface after energy.

        Spot meets siege — eyes for the wall — without authored force seeds.
        """
        um = edge.get("umwelt") or {}
        if um.get("siegeSpotStrength"):
            return float(um.get("siegeSpotStrength") or 0)
        for c in um.get("couples") or []:
            if c.get("axis") == "siege_sight" and c.get("kind") == "complement":
                return float(c.get("strength") or 0)
        return 0.0

    candidates = sorted(
        by_pair.values(),
        key=lambda e: (
            -float(e["score"]),
            -_energy_cultivation(e),
            -_spotter_cultivation(e),
            e["a"],
            e["b"],
        ),
    )

    # Degree-capped selection: keep high scores + all authored
    degree: Dict[str, int] = defaultdict(int)
    chosen: List[Dict[str, Any]] = []

    def try_add(edge: Dict[str, Any], *, force: bool = False) -> bool:
        a, b = edge["a"], edge["b"]
        if not force and (degree[a] >= max_degree or degree[b] >= max_degree):
            return False
        if any(pair_id(e["a"], e["b"]) == pair_id(a, b) for e in chosen):
            return False
        chosen.append(edge)
        degree[a] += 1
        degree[b] += 1
        return True

    for edge in candidates:
        if edge.get("authored"):
            try_add(edge, force=True)

    for edge in candidates:
        if edge.get("authored"):
            continue
        if float(edge["score"]) < min_score:
            continue
        if len(chosen) >= top_edges:
            break
        try_add(edge)

    # Build edge records + talk stubs (C always; B/A skeletons for authored/high)
    edges_out: List[Dict[str, Any]] = []
    talks: List[Dict[str, Any]] = []
    for edge in sorted(chosen, key=lambda e: (-float(e["score"]), e["a"], e["b"])):
        a, b = edge["a"], edge["b"]
        ha, hb = by_id[a], by_id[b]
        polarity = str(edge.get("polarity") or "tension")
        motif = (edge.get("motifs") or ["ash chemistry"])[0]
        title = edge.get("talkTitle") or motif
        eid = pair_id(a, b)
        edge_row = {
            "id": eid,
            "a": a,
            "b": b,
            "score": edge["score"],
            "polarity": polarity,
            "motifs": edge.get("motifs") or [],
            "sharedTemperament": edge.get("sharedTemperament") or [],
            "reasons": edge.get("reasons") or [],
            "authored": bool(edge.get("authored")),
            "aName": _name(ha),
            "bName": _name(hb),
            "aHook": _hook(ha),
            "bHook": _hook(hb),
            "aGlyph": (molecules.get(a) or {}).get("glyph"),
            "bGlyph": (molecules.get(b) or {}).get("glyph"),
            "talkIds": {
                "C": f"{eid}:C",
                "B": f"{eid}:B",
                "A": f"{eid}:A",
            },
        }
        if edge.get("umwelt"):
            edge_row["umwelt"] = edge["umwelt"]
        edges_out.append(edge_row)
        ranks = ["C"]
        if edge.get("authored") or float(edge["score"]) >= 0.72:
            ranks.append("B")
        if edge.get("authored") and float(edge["score"]) >= 0.78:
            ranks.append("A")
        for rank in ranks:
            stub = make_talk_stub(
                ha, hb, polarity=polarity, motif=motif, rank=rank, title=str(title)
            )
            stub["id"] = f"{eid}:{rank}"
            talks.append(stub)

    nodes = []
    for h in rows:
        hid = str(h["heroId"])
        mol = molecules.get(hid) or {}
        nodes.append(
            {
                "heroId": hid,
                "name": _name(h),
                "position": h.get("position"),
                "temperament": list(h.get("temperament") or []),
                "doctrine": h.get("doctrine"),
                "hook": _hook(h),
                "degree": degree.get(hid, 0),
                "umweltGlyph": mol.get("glyph"),
                "umweltMarks": mol.get("marks") or [],
            }
        )

    return {
        "schemaVersion": SCHEMA,
        "notes": (
            "Parametric FE-style support web. Edges from hero_codex chemistry + "
            "umwelt molecule couples (Uexküll carriers / SpaceWheat-ish polarity icons). "
            "Authored seeds only pin story pairs — energy + siege↔spotter links must cultivate. "
            "Camp talks: stubs + camp_talks_authored.json. G0 live channel: vane↔ketha."
        ),
        "params": {
            "minScore": min_score,
            "maxDegree": max_degree,
            "topEdges": top_edges,
            "heroCount": len(rows),
            "edgeCount": len(edges_out),
            "talkCount": len(talks),
            "authoredSeeds": len(AUTHOR_SEEDS),
            "umweltAxes": list(UMWELT_AXES),
        },
        "polarityVocab": sorted(POLARITY_OPENERS.keys()),
        "molecules": list(molecules.values()),
        "nodes": nodes,
        "edges": edges_out,
        "talks": talks,
    }


def _load_authored_talks() -> Dict[str, Dict[str, Any]]:
    """Hand SSOT + any generated=false rows already on disk."""
    keep: Dict[str, Dict[str, Any]] = {}
    for path in (AUTHORED_TALKS_PATH, TALKS_PATH):
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            continue
        for t in doc.get("talks") or []:
            if not isinstance(t, dict) or not t.get("id"):
                continue
            # Author file always wins; on TALKS_PATH only keep hand flags
            if path == AUTHORED_TALKS_PATH or t.get("generated") is False:
                row = dict(t)
                row["generated"] = False
                keep[str(row["id"])] = row
    return keep


def write_talks_file(web: Dict[str, Any], path: Path = TALKS_PATH) -> None:
    payload = {
        "schemaVersion": TALKS_SCHEMA,
        "notes": (
            "Camp/base talk stubs keyed by pairId + rank (C/B/A). "
            "Parametric from support_web_v1; hand scripts in camp_talks_authored.json "
            "win on merge (generated=false)."
        ),
        "talks": web.get("talks") or [],
    }
    keep = _load_authored_talks()
    if keep:
        merged = []
        seen = set()
        for t in payload["talks"]:
            tid = t.get("id")
            if tid in keep:
                merged.append(keep[tid])
                seen.add(tid)
            else:
                merged.append(t)
                seen.add(tid)
        for tid, t in keep.items():
            if tid not in seen:
                merged.append(t)
        payload["talks"] = merged
        payload["authoredCount"] = len(keep)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Slim embed for offline hearth
    slim_talks = []
    for t in payload["talks"]:
        slim_talks.append(
            {
                "id": t.get("id"),
                "pairId": t.get("pairId"),
                "a": t.get("a"),
                "b": t.get("b"),
                "rank": t.get("rank"),
                "title": t.get("title"),
                "polarity": t.get("polarity"),
                "motif": t.get("motif"),
                "generated": t.get("generated"),
                "unlock": t.get("unlock"),
                "beats": t.get("beats"),
            }
        )
    TALKS_EMBED_JS.parent.mkdir(parents=True, exist_ok=True)
    TALKS_EMBED_JS.write_text(
        "window.VA_CAMP_TALKS = "
        + json.dumps(
            {"schemaVersion": TALKS_SCHEMA, "talks": slim_talks},
            ensure_ascii=False,
        )
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {TALKS_EMBED_JS}")


def matrix_markdown(web: Dict[str, Any]) -> str:
    nodes = web.get("nodes") or []
    edges = web.get("edges") or []
    by_id = {n["heroId"]: n for n in nodes}
    lines = [
        "# Support Web — parametric relationship map",
        "",
        "_Generated by `tools/support_web_v1.py chart`. SSOT: `data/story/support_web.json`._",
        "",
        f"- Heroes: **{web.get('params', {}).get('heroCount', len(nodes))}**",
        f"- Edges: **{web.get('params', {}).get('edgeCount', len(edges))}** "
        f"(max degree {web.get('params', {}).get('maxDegree')})",
        f"- Talk stubs: **{web.get('params', {}).get('talkCount', 0)}**",
        f"- Authored seeds: **{web.get('params', {}).get('authoredSeeds', 0)}**",
        "",
        "## How chemistry works",
        "",
        "Edges score from **umwelt molecule couples** (opposite polarity axes = "
        "functional circles — supply↔hunger, push↔refuse), plus shared temperament, "
        "complementary tags, same/adjacent position, doctrine drama, and verb/faction "
        "rhyme. Degree is capped. Authored seeds pin story pairs only — energy links "
        "must cultivate from molecules (`docs/HERO_UMWELT.md`).",
        "",
        "## Top edges",
        "",
        "| score | pair | polarity | motif | authored | glyphs |",
        "|---|---|---|---|---|---|",
    ]
    for e in sorted(edges, key=lambda x: -float(x.get("score") or 0))[:40]:
        motif = (e.get("motifs") or ["—"])[0].replace("|", "/")
        flag = "yes" if e.get("authored") else ""
        glyphs = f"`{e.get('aGlyph') or '·'}` / `{e.get('bGlyph') or '·'}`"
        lines.append(
            f"| {e.get('score'):.2f} | {_name_short(e)} | {e.get('polarity')} | "
            f"{motif} | {flag} | {glyphs} |"
        )

    # Adjacency by hero
    adj: Dict[str, List[Tuple[float, str, str]]] = defaultdict(list)
    for e in edges:
        a, b = e["a"], e["b"]
        adj[a].append((float(e["score"]), b, str(e.get("polarity"))))
        adj[b].append((float(e["score"]), a, str(e.get("polarity"))))

    lines.extend(["", "## Adjacency (per hero)", ""])
    for hid in sorted(adj.keys(), key=lambda h: (-len(adj[h]), h)):
        node = by_id.get(hid) or {}
        name = node.get("name") or hid
        temps = ",".join(node.get("temperament") or [])
        lines.append(f"### {name} (`{hid}`) — {node.get('position')} [{temps}]")
        for score, other, pol in sorted(adj[hid], reverse=True):
            on = (by_id.get(other) or {}).get("name") or other
            lines.append(f"- **{score:.2f}** {pol} → {on} (`{other}`)")
        lines.append("")

    lines.extend(
        [
            "## Camp talks (plug-in)",
            "",
            "Talk stubs live in `data/story/camp_talks.json` (pair × rank C/B/A).",
            "Hand scripts: `data/story/camp_talks_authored.json`.",
            "Unlock gates: `coDeploy`, `campLevelMin`, `bondMin`.",
            "",
            "### Shipped thin",
            "Hub hearth eligible talks · `POST /api/camp-talk` · co-deploy pair XP ·",
            "umwelt molecules (`docs/HERO_UMWELT.md`).",
            "Cultivated couples: energy **supply meets hunger** · siege↔spotter "
            "**spot meets siege** (soft boost, not authored force).",
            "",
            "### Hero graph umwelt foundation",
            "Analytical face + co-evolve → play-observe → tensor roadmap:",
            "`docs/HERO_GRAPH_UMWELT_FOUNDATION.md` · `tools/hero_graph_analyze_v1.py`.",
            "",
            "### Dev wishlist",
            "**Full cognifold implementation** (BAR × SpaceWheat × hero molecules,",
            "live bridge, hub panel, sortie→observe stamps) — see",
            "`docs/UMWELT_GYM_PATHWAY.md` § Dev wishlist. Post-playtest / G0-out.",
            "",
            "**Relationship → AI augments** (wishlist): pair-bond soft micro — e.g. scouts",
            "dodge Fatboy/Tzar knock cones, spotter marks bias siege plod, Warder↔Commando",
            "mine ring. SSOT: `data/story/support_ai_augments.json` · notes in",
            "`docs/HERO_GRAPH_UMWELT_FOUNDATION.md`. Not G0; human seal before combat feel.",
            "",
            "G0 still treats **Vane↔Ketha** as the primary live bond channel;",
            "the web + molecules are the parametric map we grow into.",
            "",
        ]
    )
    return "\n".join(lines)


def _name_short(e: Dict[str, Any]) -> str:
    return f"{e.get('aName') or e.get('a')} ↔ {e.get('bName') or e.get('b')}"


def write_umwelt_files(web: Dict[str, Any]) -> None:
    mols = web.get("molecules") or []
    payload = {
        "schemaVersion": "verdance-hero-umwelt/1.0",
        "notes": (
            "Per-hero umwelt molecules — Uexküll carriers of significance as a "
            "compact polarity icon (SpaceWheat cognifold rhyme). Derived from "
            "hero_codex position/doctrine/temperament/verb. Used by support_web "
            "to cultivate complementary links (e.g. energy supply↔hunger, "
            "siege↔spotter spot meets siege)."
        ),
        "axes": list(UMWELT_AXES),
        "heroes": mols,
    }
    UMWELT_PATH.parent.mkdir(parents=True, exist_ok=True)
    UMWELT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    UMWELT_EMBED_JS.parent.mkdir(parents=True, exist_ok=True)
    UMWELT_EMBED_JS.write_text(
        "window.VA_HERO_UMWELT = "
        + json.dumps(payload, ensure_ascii=False)
        + ";\n",
        encoding="utf-8",
    )
    lines = [
        "# Hero Umwelt — polarity molecules",
        "",
        "_Generated by `tools/support_web_v1.py`. SSOT: `data/story/hero_umwelt.json`._",
        "",
        "Each hero is a small **icon molecule**: axes in [-1,+1] that mark what "
        "their self-world cares about (energy, offense, mobility, sight, pad, "
        "craft, heat, fog, sky, ledger). Complementary signs couple into the "
        "support web — cultivated, not forced.",
        "",
        "## Molecules",
        "",
        "| hero | glyph | top marks |",
        "|---|---|---|",
    ]
    for m in sorted(mols, key=lambda x: str(x.get("heroId"))):
        marks = ", ".join(
            f"{'+' if float(x['value'])>0 else ''}{x['value']:.2f} {x['axis']}"
            for x in (m.get("marks") or [])[:4]
        )
        lines.append(
            f"| {m.get('name')} (`{m.get('heroId')}`) | `{m.get('glyph')}` | {marks} |"
        )
    # Energy extremes — show cultivation candidates
    by_energy = sorted(
        mols,
        key=lambda m: -abs(float((m.get("axes") or {}).get("energy") or 0)),
    )
    lines.extend(["", "## Energy polarity (supply ↔ hunger)", ""])
    for m in by_energy[:8]:
        e = float((m.get("axes") or {}).get("energy") or 0)
        lines.append(f"- **{e:+.2f}** {m.get('name')} (`{m.get('heroId')}`)")

    # Spotter / siege shapes — cross-axis cultivation candidates
    def _spot_mark(m: Dict[str, Any]) -> float:
        ax = m.get("axes") or {}
        return max(0.0, float(ax.get("sight") or 0)) * 0.75 + max(
            0.0, float(ax.get("fog") or 0)
        ) * 0.55

    def _siege_mark(m: Dict[str, Any]) -> float:
        ax = m.get("axes") or {}
        pad = float(ax.get("pad") or 0)
        mob = float(ax.get("mobility") or 0)
        if pad < 0.45 or mob > -0.2:
            return 0.0
        return pad * 0.75 + max(0.0, -mob) * 0.35

    spotters = [m for m in mols if _spot_mark(m) >= 0.35]
    sieges = [m for m in mols if _siege_mark(m) >= 0.35]
    spotters.sort(key=lambda m: -_spot_mark(m))
    sieges.sort(key=lambda m: -_siege_mark(m))
    lines.extend(
        [
            "",
            "## Siege ↔ spotter (spot meets siege)",
            "",
            "Cross-axis cultivation: pad-heavy stay faces couple with sight/fog "
            "recon — soft boost + tie-break, not authored seeds.",
            "",
            "### Spotters",
            "",
        ]
    )
    for m in spotters[:10]:
        ax = m.get("axes") or {}
        lines.append(
            f"- `{m.get('heroId')}` sight={float(ax.get('sight') or 0):+.2f} "
            f"fog={float(ax.get('fog') or 0):+.2f}"
        )
    lines.extend(["", "### Siege / hold faces", ""])
    for m in sieges[:10]:
        ax = m.get("axes") or {}
        lines.append(
            f"- `{m.get('heroId')}` pad={float(ax.get('pad') or 0):+.2f} "
            f"mob={float(ax.get('mobility') or 0):+.2f}"
        )
    lines.extend(
        [
            "",
            "## Analysis / foundation",
            "",
            "`python tools/hero_graph_analyze_v1.py [--write]`",
            "",
            "L2 map pressures: `data/story/map_umwelt.json` · "
            "`python tools/map_umwelt_v1.py fit --map the_rock_jungle`",
            "",
            "L3 observe tape: `python tools/hero_observe_v1.py status`",
            "",
            "Layer cake: `docs/HERO_GRAPH_UMWELT_FOUNDATION.md`.",
            "",
            "## Dev wishlist",
            "",
            "Thin molecules are shipped. **Full cognifold** (shared BAR×SW×hero face,",
            "live bridge, hub panel, observe stamps) lives on",
            "`docs/UMWELT_GYM_PATHWAY.md` § Dev wishlist — post-playtest.",
            "",
        ]
    )
    UMWELT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {UMWELT_PATH}")
    print(f"wrote {UMWELT_EMBED_JS}")
    print(f"wrote {UMWELT_MD}")


def cmd_generate(args: argparse.Namespace) -> int:
    codex = load_codex()
    web = generate_web(
        codex,
        min_score=args.min_score,
        max_degree=args.max_degree,
        top_edges=args.top_edges,
    )
    # Strip talks from web SSOT (talks file is separate); keep talkIds on edges
    talks = web.pop("talks", [])
    molecules = web.get("molecules") or []
    web_slim = dict(web)
    WEB_PATH.parent.mkdir(parents=True, exist_ok=True)
    WEB_PATH.write_text(json.dumps(web_slim, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    web_slim["talks"] = talks  # restore for talks writer
    write_talks_file(web_slim, TALKS_PATH)
    write_umwelt_files(web_slim)
    print(f"wrote {WEB_PATH} edges={web_slim['params']['edgeCount']}")
    print(f"wrote {TALKS_PATH} talks={web_slim['params']['talkCount']}")
    print(f"molecules={len(molecules)}")
    if args.chart:
        CHART_MD.write_text(matrix_markdown(web_slim), encoding="utf-8")
        print(f"wrote {CHART_MD}")
    if args.embed:
        _write_embed(web_slim)
    return 0


def _write_embed(web: Dict[str, Any]) -> None:
    slim = {
        "schemaVersion": web.get("schemaVersion"),
        "params": web.get("params"),
        "nodes": [
            {
                "heroId": n["heroId"],
                "name": n["name"],
                "position": n["position"],
                "temperament": n.get("temperament"),
                "degree": n.get("degree"),
                "umweltGlyph": n.get("umweltGlyph"),
            }
            for n in (web.get("nodes") or [])
        ],
        "edges": [
            {
                "id": e["id"],
                "a": e["a"],
                "b": e["b"],
                "score": e["score"],
                "polarity": e["polarity"],
                "motifs": e.get("motifs"),
                "authored": e.get("authored"),
                "aName": e.get("aName"),
                "bName": e.get("bName"),
                "aGlyph": e.get("aGlyph"),
                "bGlyph": e.get("bGlyph"),
                "umwelt": e.get("umwelt"),
            }
            for e in (web.get("edges") or [])
        ],
    }
    EMBED_JS.parent.mkdir(parents=True, exist_ok=True)
    body = "window.VA_SUPPORT_WEB = " + json.dumps(slim, ensure_ascii=False) + ";\n"
    EMBED_JS.write_text(body, encoding="utf-8")
    print(f"wrote {EMBED_JS}")


def cmd_list(args: argparse.Namespace) -> int:
    if not WEB_PATH.is_file():
        print("no support_web.json — run generate first", file=sys.stderr)
        return 1
    web = json.loads(WEB_PATH.read_text(encoding="utf-8-sig"))
    edges = web.get("edges") or []
    if args.hero:
        hid = args.hero
        edges = [e for e in edges if e.get("a") == hid or e.get("b") == hid]
    if args.polarity:
        edges = [e for e in edges if e.get("polarity") == args.polarity]
    edges = sorted(edges, key=lambda e: -float(e.get("score") or 0))
    for e in edges[: args.limit]:
        flag = "*" if e.get("authored") else " "
        print(
            f"{flag} {e.get('score'):.2f}  {e.get('polarity'):8}  "
            f"{e.get('aName')} ↔ {e.get('bName')}  — {(e.get('motifs') or [''])[0]}"
        )
    print(f"# {len(edges)} edges shown (limit {args.limit})")
    return 0


def cmd_chart(args: argparse.Namespace) -> int:
    if not WEB_PATH.is_file():
        print("no support_web.json — run generate first", file=sys.stderr)
        return 1
    web = json.loads(WEB_PATH.read_text(encoding="utf-8-sig"))
    # reattach talks count from camp_talks if present
    if TALKS_PATH.is_file():
        talks = json.loads(TALKS_PATH.read_text(encoding="utf-8-sig"))
        web["talks"] = talks.get("talks") or []
        web.setdefault("params", {})["talkCount"] = len(web["talks"])
    md = matrix_markdown(web)
    if args.write:
        CHART_MD.write_text(md, encoding="utf-8")
        print(f"wrote {CHART_MD}")
    else:
        print(md)
    return 0


def cmd_talks(args: argparse.Namespace) -> int:
    if not TALKS_PATH.is_file():
        print("no camp_talks.json — run generate first", file=sys.stderr)
        return 1
    data = json.loads(TALKS_PATH.read_text(encoding="utf-8-sig"))
    talks = data.get("talks") or []
    if args.pair:
        pid = args.pair if "__" in args.pair else None
        if not pid:
            parts = args.pair.replace(",", "__").replace("-", "__").split("__")
            if len(parts) >= 2:
                pid = pair_id(parts[0].strip(), parts[1].strip())
        talks = [t for t in talks if t.get("pairId") == pid or t.get("id", "").startswith(str(pid))]
    if args.rank:
        talks = [t for t in talks if t.get("rank") == args.rank]
    for t in talks[: args.limit]:
        print(f"## {t.get('id')} — {t.get('title')} [{t.get('polarity')}]")
        for beat in t.get("beats") or []:
            print(f"  {beat.get('speaker')}: {beat.get('line')}")
        print()
    print(f"# {len(talks)} talks")
    return 0


def cmd_seeds(_: argparse.Namespace) -> int:
    for s in AUTHOR_SEEDS:
        print(
            f"{s['score']:.2f}  {s['polarity']:8}  {s['a']} ↔ {s['b']}  — {s['motif']}"
        )
    print(f"# {len(AUTHOR_SEEDS)} authored seeds")
    return 0


def cmd_molecules(args: argparse.Namespace) -> int:
    codex = load_codex()
    rows = heroes(codex)
    mols = [hero_umwelt_molecule(h) for h in rows]
    if args.hero:
        mols = [m for m in mols if m.get("heroId") == args.hero]
    if args.sort == "energy":
        mols.sort(key=lambda m: float((m.get("axes") or {}).get("energy") or 0))
    else:
        mols.sort(key=lambda m: str(m.get("heroId")))
    for m in mols:
        axes = m.get("axes") or {}
        e = float(axes.get("energy") or 0)
        o = float(axes.get("offense") or 0)
        print(
            f"{m.get('heroId'):12} E={e:+.2f} O={o:+.2f}  {m.get('glyph')}  "
            f"{m.get('name')}"
        )
    if args.couple and len(args.couple) >= 2:
        a, b = args.couple[0], args.couple[1]
        by = {m["heroId"]: m for m in [hero_umwelt_molecule(h) for h in rows]}
        if a in by and b in by:
            c = umwelt_couple(by[a], by[b])
            print(
                f"# couple {a}↔{b}: boost={c['boost']} {c['polarity']} — {c['motif']}"
            )
            for row in c.get("couples") or []:
                print(
                    f"    {row['kind']:11} {row['axis']:8} "
                    f"{row['a']:+.2f}×{row['b']:+.2f} → {row['strength']:.3f}"
                )
    print(f"# {len(mols)} molecules")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Regenerate + write chart + embed. Optional hub projection hook later."""
    args.min_score = getattr(args, "min_score", 0.42)
    args.max_degree = getattr(args, "max_degree", 5)
    args.top_edges = getattr(args, "top_edges", 64)
    args.chart = True
    args.embed = True
    return cmd_generate(args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p_gen = sp.add_parser("generate", help="Build support_web.json + camp_talks.json")
    p_gen.add_argument("--min-score", type=float, default=0.42)
    p_gen.add_argument("--max-degree", type=int, default=5)
    p_gen.add_argument("--top-edges", type=int, default=64)
    p_gen.add_argument("--chart", action="store_true")
    p_gen.add_argument("--embed", action="store_true")
    p_gen.set_defaults(func=cmd_generate)

    p_list = sp.add_parser("list", help="List edges")
    p_list.add_argument("--hero")
    p_list.add_argument("--polarity")
    p_list.add_argument("--limit", type=int, default=40)
    p_list.set_defaults(func=cmd_list)

    p_chart = sp.add_parser("chart", help="Print / write relationship map markdown")
    p_chart.add_argument("--write", action="store_true")
    p_chart.set_defaults(func=cmd_chart)

    p_talks = sp.add_parser("talks", help="Dump camp-talk stubs")
    p_talks.add_argument("--pair", help="heroA__heroB or a,b")
    p_talks.add_argument("--rank", choices=["C", "B", "A"])
    p_talks.add_argument("--limit", type=int, default=20)
    p_talks.set_defaults(func=cmd_talks)

    p_seeds = sp.add_parser("seeds", help="Show authored seed pairs")
    p_seeds.set_defaults(func=cmd_seeds)

    p_mol = sp.add_parser("molecules", help="Show hero umwelt polarity molecules")
    p_mol.add_argument("--hero")
    p_mol.add_argument("--sort", choices=["id", "energy"], default="id")
    p_mol.add_argument(
        "--couple",
        nargs=2,
        metavar=("A", "B"),
        help="Print umwelt couple detail for two heroIds",
    )
    p_mol.set_defaults(func=cmd_molecules)

    p_apply = sp.add_parser("apply", help="generate + chart + embed")
    p_apply.add_argument("--min-score", type=float, default=0.42)
    p_apply.add_argument("--max-degree", type=int, default=5)
    p_apply.add_argument("--top-edges", type=int, default=64)
    p_apply.set_defaults(func=cmd_apply)

    args = ap.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
