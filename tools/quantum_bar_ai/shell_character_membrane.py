"""Living-shell character membrane — zone-occupied umwelt for campaign craft.

Bakes map-pool + living-shell learnings into a campaign-compatible density
membrane. Fair rule: proxy player never reads this raw; only derived briefings,
raid/wrath hints, and solution geometry leak out.

Sources (do not invent lore):
  - data/map_pool/seven_maps.json
  - data/base_templates/*/bake_recipe.json + grow_profiles.json
  - outbound 36/37/38, map_calibration_recommendations
  - lane_war geometries for Koom / ATS

Axes (diag of rho):
  0 eco_surface   — solar/wind/converter raid surface
  1 defense_teeth — LLT/HLT/wall after strip
  2 fortress      — citadel / hard BARb cores
  3 lane_mass     — fluid scar / swamp lane weight
  4 wild_hazard   — raptor / pathing (not strip-shell)
  5 multi_faction — ARM/COR/NMC co-occupation
  6 tech_spike    — late-tech / MIRV glass / dealer core
  7 siege_depth   — outer belts + citadel spine
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from quantum_bar_ai.quantum_membrane import shannon_entropy, von_neumann_diag

SHELL_AXES = (
    "eco_surface",
    "defense_teeth",
    "fortress",
    "lane_mass",
    "wild_hazard",
    "multi_faction",
    "tech_spike",
    "siege_depth",
)

# Documented character priors (execution freeze outbound 38 + calibration).
# Values are expectation weights on shell axes 0..1 before normalize.
MAP_PRIORS: dict[str, dict[str, float]] = {
    "greenest_fields": {
        "eco_surface": 0.92,
        "defense_teeth": 0.35,
        "fortress": 0.12,
        "lane_mass": 0.15,
        "wild_hazard": 0.05,
        "multi_faction": 0.05,
        "tech_spike": 0.18,
        "siege_depth": 0.08,
    },
    "eye_of_horus": {
        "eco_surface": 0.45,
        "defense_teeth": 0.55,
        "fortress": 0.72,
        "lane_mass": 0.22,
        "wild_hazard": 0.08,
        "multi_faction": 0.55,
        "tech_spike": 0.88,
        "siege_depth": 0.40,
    },
    "koom_valley": {
        "eco_surface": 0.48,
        "defense_teeth": 0.50,
        "fortress": 0.28,
        "lane_mass": 0.90,
        "wild_hazard": 0.10,
        "multi_faction": 0.35,
        "tech_spike": 0.20,
        "siege_depth": 0.18,
    },
    "tabula": {
        "eco_surface": 0.50,
        "defense_teeth": 0.62,
        "fortress": 0.58,
        "lane_mass": 0.30,
        "wild_hazard": 0.08,
        "multi_faction": 0.25,
        "tech_spike": 0.28,
        "siege_depth": 0.45,
    },
    "ancient_bastion": {
        "eco_surface": 0.38,
        "defense_teeth": 0.85,
        "fortress": 0.92,
        "lane_mass": 0.20,
        "wild_hazard": 0.05,
        "multi_faction": 0.10,
        "tech_spike": 0.35,
        "siege_depth": 0.95,
    },
    "the_rock_jungle": {
        "eco_surface": 0.18,
        "defense_teeth": 0.25,
        "fortress": 0.08,
        "lane_mass": 0.15,
        "wild_hazard": 0.92,
        "multi_faction": 0.20,
        "tech_spike": 0.10,
        "siege_depth": 0.05,
    },
    "all_that_simmers": {
        "eco_surface": 0.52,
        "defense_teeth": 0.55,
        "fortress": 0.48,
        "lane_mass": 0.78,
        "wild_hazard": 0.70,
        "multi_faction": 0.85,
        "tech_spike": 0.40,
        "siege_depth": 0.30,
    },
}

# growProfile -> how it tilts the membrane after a bake/placeholder sample
GROW_TILT: dict[str, dict[str, float]] = {
    "sprawl": {"eco_surface": 0.12, "defense_teeth": -0.05, "fortress": -0.04},
    "hold": {"eco_surface": 0.02, "defense_teeth": 0.04},
    "fortify_easy": {"defense_teeth": 0.08, "fortress": 0.04},
    "fortify": {"defense_teeth": 0.14, "fortress": 0.10, "lane_mass": 0.06},
    "fortify_hard": {"defense_teeth": 0.18, "fortress": 0.20, "siege_depth": 0.12},
    "aggressive_core": {"defense_teeth": 0.16, "fortress": 0.14, "tech_spike": 0.08},
    "scrap": {"eco_surface": -0.10, "defense_teeth": -0.02, "multi_faction": 0.06},
    "thin": {"eco_surface": -0.15, "defense_teeth": -0.12, "fortress": -0.10},
}

# Arc kinds that should load living shells when a template exists
SHELL_KINDS = (
    "eco_raid",
    "eco_expand",
    "economy_disrupt",
    "seize_lane",
    "strike_relay",
    "hold_plateau",
    "siege",
    "multipressure",
    "gate_control",
    "survive_wilds",
)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class ShellCharacter:
    """Per-map living-shell character membrane."""

    map_id: str
    diag: list[float] = field(default_factory=lambda: [0.125] * 8)
    # off-diagonal coherence buckets: eco-def, lane-wild, fort-siege (real only)
    coh_eco_def: float = 0.15
    coh_lane_wild: float = 0.10
    coh_fort_siege: float = 0.20
    grow_profiles: list[str] = field(default_factory=list)
    pockets: int = 0
    unit_count: int = 0
    wrath_pack: str = ""
    wrath_seconds: int = 120
    descriptor: str = ""
    blurb: str = ""
    raid_hint_override: str = ""
    arc_kinds: list[str] = field(default_factory=list)
    capture_later: str = ""
    source: str = "prior"  # prior | placeholder | bake

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        tot = sum(max(0.0, d) for d in self.diag) or 1.0
        self.diag = [_clamp01(d / tot) * (tot / max(tot, 1e-9)) for d in self.diag]
        # re-normalize to sum 1 for entropy / expectation
        tot = sum(max(0.0, d) for d in self.diag) or 1.0
        self.diag = [max(0.0, d) / tot for d in self.diag]
        self.coh_eco_def = _clamp01(self.coh_eco_def)
        self.coh_lane_wild = _clamp01(self.coh_lane_wild)
        self.coh_fort_siege = _clamp01(self.coh_fort_siege)

    def expect(self) -> dict[str, float]:
        return {SHELL_AXES[i]: self.diag[i] for i in range(len(SHELL_AXES))}

    def purity(self) -> float:
        """Lower purity = multipath occupation (more mixed character)."""
        return sum(d * d for d in self.diag)

    def width(self) -> float:
        """Solution-space width proxy from shell character entropy."""
        return von_neumann_diag(self.diag) / math.log(len(SHELL_AXES))

    def raid_hint(self) -> str:
        """Pick dominant raid fantasy from relative axis rank (post-normalize)."""
        # Recipe character-card override wins when authored (outbound 38 freeze).
        if self.raid_hint_override:
            return self.raid_hint_override
        e = self.expect()
        # Priority order matches map characters (outbound 38), not raw 0.5 cutoffs.
        ranked = sorted(e.items(), key=lambda kv: kv[1], reverse=True)
        top = ranked[0][0]
        second = ranked[1][0] if len(ranked) > 1 else top
        if top == "wild_hazard" or (e["wild_hazard"] >= 0.18 and e["eco_surface"] < 0.12):
            return "survive_pathing"
        if top == "siege_depth" or (e["siege_depth"] >= 0.16 and e["fortress"] >= 0.14):
            return "bite_outer_rings"
        if top == "tech_spike" or (e["tech_spike"] >= 0.16 and e["fortress"] >= 0.12):
            return "strike_core_extract"
        if top == "lane_mass" or (e["lane_mass"] >= 0.16 and second in ("defense_teeth", "eco_surface", "multi_faction")):
            return "seize_or_raid_lane"
        if top == "eco_surface" or e["eco_surface"] >= 0.18:
            return "raid_eco_extract"
        if top in ("fortress", "defense_teeth", "siege_depth"):
            return "bite_outer_rings"
        return "clear_node_hold"

    def fair_briefing_tags(self) -> list[str]:
        """Leak-safe tags for briefings / HUD bands (not raw rho)."""
        e = self.expect()
        mean = sum(e.values()) / max(1, len(e))
        tags = []
        if e["eco_surface"] >= mean:
            tags.append("eco_dense")
        if e["defense_teeth"] >= mean:
            tags.append("toothy")
        if e["fortress"] >= mean:
            tags.append("fortified")
        if e["lane_mass"] >= mean:
            tags.append("lane_front")
        if e["wild_hazard"] >= mean:
            tags.append("wild")
        if e["multi_faction"] >= mean:
            tags.append("multi_faction")
        if e["tech_spike"] >= mean:
            tags.append("tech_spike")
        if e["siege_depth"] >= mean:
            tags.append("siege")
        return tags or ["occupied"]

    def apply_grow_profile(self, profile: str, weight: float = 1.0) -> None:
        tilt = GROW_TILT.get(profile) or {}
        w = max(0.0, min(2.0, weight))
        for axis, delta in tilt.items():
            if axis in SHELL_AXES:
                i = SHELL_AXES.index(axis)
                self.diag[i] = max(0.01, self.diag[i] + delta * w * 0.08)
        if profile not in self.grow_profiles:
            self.grow_profiles.append(profile)
        # BARb fortify couples eco-def coherence (more D around eco)
        if profile.startswith("fortify") or profile == "aggressive_core":
            self.coh_eco_def = _clamp01(self.coh_eco_def + 0.05 * w)
            self.coh_fort_siege = _clamp01(self.coh_fort_siege + 0.04 * w)
        if profile == "sprawl":
            self.coh_eco_def = _clamp01(self.coh_eco_def - 0.02 * w)
        self.normalize()

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["expect"] = self.expect()
        d["purity"] = round(self.purity(), 4)
        d["width"] = round(self.width(), 4)
        d["raid_hint"] = self.raid_hint()
        d["fair_tags"] = self.fair_briefing_tags()
        d["axes"] = list(SHELL_AXES)
        d["character_card"] = {
            "descriptor": self.descriptor,
            "blurb": self.blurb,
            "arc_kinds": list(self.arc_kinds),
            "raid_hint": self.raid_hint(),
            "capture_later": self.capture_later,
            "wrath": {"packId": self.wrath_pack, "responseSeconds": self.wrath_seconds},
            "grow_profiles": list(self.grow_profiles),
            "unit_count": self.unit_count,
            "source": self.source,
        }
        return d

    @classmethod
    def from_prior(cls, map_id: str) -> "ShellCharacter":
        prior = MAP_PRIORS.get(map_id) or MAP_PRIORS["greenest_fields"]
        diag = [float(prior.get(a, 0.1)) for a in SHELL_AXES]
        return cls(map_id=map_id, diag=diag, source="prior")


def load_shell_from_workspace(workspace: str | Path, map_id: str) -> ShellCharacter:
    """Build membrane from prior + bake_recipe grow profiles + template stats."""
    ws = Path(workspace)
    sc = ShellCharacter.from_prior(map_id)

    def _read_json(path: Path) -> dict[str, Any]:
        # PowerShell Set-Content often writes UTF-8 BOM.
        return json.loads(path.read_text(encoding="utf-8-sig"))

    recipe_path = ws / "data" / "base_templates" / map_id / "bake_recipe.json"
    if recipe_path.is_file():
        rec = _read_json(recipe_path)
        sc.descriptor = str(rec.get("character") or sc.descriptor)
        card = rec.get("characterCard") or {}
        if card.get("descriptor"):
            sc.descriptor = str(card.get("descriptor") or sc.descriptor)
        sc.blurb = str(card.get("blurb") or rec.get("blurb") or "")
        sc.raid_hint_override = str(
            card.get("raidHint") or rec.get("raidHint") or ""
        )
        arcs = card.get("arcKinds") or rec.get("arcKinds") or []
        sc.arc_kinds = [str(a) for a in arcs]
        sc.capture_later = str(
            card.get("captureLater") or rec.get("captureLater") or ""
        )
        wrath = rec.get("wrathDefault") or card.get("wrath") or {}
        sc.wrath_pack = str(wrath.get("packId") or "")
        sc.wrath_seconds = int(wrath.get("responseSeconds") or 120)
        for st in rec.get("starts") or []:
            gp = str(st.get("growProfile") or "hold")
            dens = float(st.get("densityScale") or 1.0)
            sc.apply_grow_profile(gp, weight=dens)
            sc.pockets += 1

    # Prefer real bake, then placeholders
    base = ws / "data" / "base_templates" / map_id
    tpl = None
    for name in (
        "living_shell_v1.json",
        "armada_t15_v1.json",
        "armada_placeholder_v1.json",
        "living_placeholder_v1.json",
    ):
        p = base / name
        if p.is_file():
            tpl = _read_json(p)
            break
    if tpl:
        sc.unit_count = int(tpl.get("unitCount") or len(tpl.get("units") or []))
        sc.source = str(tpl.get("source") or "placeholder")
        if not sc.pockets:
            sc.pockets = len(tpl.get("pockets") or [])
        # Sample unit mix to nudge axes
        defs = [str(u.get("unitDefName") or "") for u in (tpl.get("units") or [])]
        n = max(1, len(defs))
        eco_n = sum(1 for d in defs if any(k in d for k in ("solar", "win", "makr", "fus", "estor")))
        def_n = sum(1 for d in defs if any(k in d for k in ("llt", "hlt", "beamer", "rl", "pb", "guard", "drag", "fort", "mg", "lht")))
        sc.diag[0] = max(0.05, sc.diag[0] * 0.6 + 0.4 * (eco_n / n))
        sc.diag[1] = max(0.05, sc.diag[1] * 0.6 + 0.4 * (def_n / n))
        sc.normalize()

    return sc


def _cloud_locus_status(ws: Path) -> dict[str, Any]:
    """Campaign-compatible compute locus: shell sims prefer cloud (outbound 40)."""
    harvest_path = ws / "outbox" / "cloud_bake_harvest.latest.json"
    bundle_path = ws / "outbox" / "cloud_bake_bundle.latest.json"
    sync_path = ws / "outbox" / "cloud_runtime_sync.latest.json"
    cfg_path = ws / "data" / "cloud" / "cloud_config.json"
    status: dict[str, Any] = {
        "preferred_locus": "cloud",
        "fallback_locus": "local_headless",
        "config_ready": cfg_path.is_file(),
        "reason": "Local IconsAtlas stall; BARb/SimpleAI grow bakes run on cloud VM.",
        "doc": "scripts/forge/cloud/README.md",
    }
    if harvest_path.is_file():
        try:
            h = json.loads(harvest_path.read_text(encoding="utf-8-sig"))
            status["last_harvest_ok"] = int(h.get("okCount") or 0)
            status["last_harvest_total"] = int(h.get("total") or 0)
            status["last_harvest_at"] = h.get("finishedAt")
        except Exception:
            status["last_harvest_ok"] = 0
    if bundle_path.is_file():
        try:
            b = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            status["latest_bundle"] = b.get("bundleName")
            status["bundle_maps"] = b.get("mapIds")
        except Exception:
            pass
    if sync_path.is_file():
        try:
            s = json.loads(sync_path.read_text(encoding="utf-8-sig"))
            status["runtime_synced_at"] = s.get("syncedAt")
            status["runtime_host"] = s.get("host")
        except Exception:
            pass
    return status


def build_seven_map_membrane(workspace: str | Path) -> dict[str, Any]:
    """Full pool membrane pack for campaign craft / umweltd."""
    ws = Path(workspace)
    maps = list(MAP_PRIORS.keys())
    characters = {m: load_shell_from_workspace(ws, m).as_dict() for m in maps}
    # Pool-level coherence: multipressure when multi_faction high across pool
    multi = sum(characters[m]["expect"]["multi_faction"] for m in maps) / len(maps)
    wild = sum(characters[m]["expect"]["wild_hazard"] for m in maps) / len(maps)
    real_baked = sum(
        1
        for m in maps
        if (ws / "data" / "base_templates" / m / "living_shell_v1.json").is_file()
        or (ws / "data" / "base_templates" / m / "armada_t15_v1.json").is_file()
    )
    return {
        "schemaVersion": "verdance-shell-character-membrane/1.1",
        "axes": list(SHELL_AXES),
        "shellKinds": list(SHELL_KINDS),
        "pool": {
            "multi_faction_mean": round(multi, 4),
            "wild_hazard_mean": round(wild, 4),
            "map_count": len(maps),
            "real_baked_shells": real_baked,
            "placeholder_shells": len(maps) - real_baked,
        },
        "compute": _cloud_locus_status(ws),
        "maps": characters,
        "fair_rule": "Proxy never reads raw diag; use fair_tags + raid_hint only.",
        "learnings": [
            "Grow rates: SimpleAI sprawl vs BARb easy/medium/hard for base texture after strip.",
            "Shell sims preferred on cloud (outbound 40); strip + campaign stay local.",
            "Headless must use --write-dir + --isolation + --only-local; va_shell_bake skips occupation spawn.",
        ],
    }


def shell_solution_geometry(sc: ShellCharacter) -> dict[str, Any]:
    """Map shell character to campaign MissionSolutionSpace-compatible fields."""
    e = sc.expect()
    vectors = ["PROBE", "PUSH_OBJECTIVE"]
    predicates = []
    if e["eco_surface"] > 0.45:
        vectors += ["RECLAIM"]
        predicates.append("eco_wreck")
    if e["lane_mass"] > 0.45:
        vectors += ["EXPAND_FRONT", "HOLD_AND_HEAL"]
        predicates.append("lane_hold")
    if e["tech_spike"] > 0.5 or e["fortress"] > 0.55:
        vectors += ["FLANK", "TECH_UP"]
        predicates.append("strike_cut")
    if e["siege_depth"] > 0.5:
        vectors += ["FALLBACK", "RALLY"]
        predicates.append("siege_break")
    if e["wild_hazard"] > 0.5:
        vectors += ["FALLBACK", "HOLD_AND_HEAL"]
        predicates.append("survive_clock")
    predicates.append("objective_hold")
    vectors.append("EXTRACT")
    # decoys: building when raid-only
    decoys = []
    if e["eco_surface"] > 0.5 and e["siege_depth"] < 0.4:
        decoys = ["BUILD_MEX", "BUILD_CON", "EXPAND_FRONT"]
    return {
        "width": round(sc.width(), 4),
        "vector_clarity": round(1.0 - sc.width() * 0.5, 4),
        "primary_vectors": vectors[:3],
        "viable_vectors": list(dict.fromkeys(vectors)),
        "win_predicates": list(dict.fromkeys(predicates)),
        "decoy_vectors": decoys,
        "raid_hint": sc.raid_hint(),
        "fair_tags": sc.fair_briefing_tags(),
        "wrath": {"packId": sc.wrath_pack, "responseSeconds": sc.wrath_seconds},
    }


if __name__ == "__main__":
    import os
    import sys

    ws = os.environ.get(
        "VERDANCE_WORKSPACE",
        r"C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace",
    )
    if len(sys.argv) > 1:
        ws = sys.argv[1]
    pack = build_seven_map_membrane(ws)
    out = Path(ws) / "outbox" / "shell_character_membrane.latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pack, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    for mid, ch in pack["maps"].items():
        print(
            f"  {mid:20s} units={ch.get('unit_count', 0):4d} "
            f"hint={ch['raid_hint']:22s} tags={','.join(ch['fair_tags'])} "
            f"profiles={ch.get('grow_profiles')}"
        )
