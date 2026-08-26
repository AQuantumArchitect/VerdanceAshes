"""Player-facing observations only — no omniscient combat truth.

The proxy may see what a human player sees on the Verdance HUD / briefing:
  - mission card text (situation, objective, how-to-win, threats flavor)
  - phase + soft clock
  - fuzzy contact / pressure bands
  - objective progress as coarse bars (not exact %)
  - hero status tags (OK / wounded / critical / down)
  - last action outcome flavor

It must NOT see raw sim knobs: enemy_scale, exact enemy_strength,
RNG seeds, or hidden unit tables. Those stay in SimTruth.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from typing import Any


def _band(x: float, *, labels: tuple[str, ...] | None = None) -> str:
    """Map 0..1 to a coarse band label a player could feel."""
    x = max(0.0, min(1.0, float(x)))
    if labels is None:
        labels = ("none", "light", "moderate", "heavy", "extreme")
    # 5 bins
    idx = min(len(labels) - 1, int(x * len(labels)))
    if x >= 0.999:
        idx = len(labels) - 1
    return labels[idx]


def _hero_tag(hp: float) -> str:
    if hp <= 0.05:
        return "down"
    if hp < 0.35:
        return "critical"
    if hp < 0.65:
        return "wounded"
    if hp < 0.9:
        return "bruised"
    return "ok"


@dataclass
class PlayerFacingCard:
    """What the pause-briefing / mission card shows."""

    id: str
    title: str
    kind: str
    map_name: str
    deploy_label: str
    objective_label: str
    extraction_label: str
    situation: str
    objective_text: str
    how_to_win: str
    threats: str
    allies: str
    plain_objective: str
    soft_clock_minutes: int = 10
    no_base_building: bool = True
    briefing_lines: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def briefing_block(self) -> str:
        lines = [
            f"MISSION {self.id}: {self.title}",
            f"Map: {self.map_name} | Type: {self.kind}",
            f"Deploy: {self.deploy_label}",
            f"Objective: {self.objective_label}",
            f"Extract: {self.extraction_label}",
            f"Soft clock: ~{self.soft_clock_minutes} min",
            f"Base building: {'NO' if self.no_base_building else 'yes'}",
            "",
            f"SITUATION: {self.situation}",
            f"OBJECTIVE: {self.objective_text}",
            f"HOW TO WIN: {self.how_to_win}",
            f"THREATS: {self.threats}",
            f"ALLIES: {self.allies}",
            f"PLAIN: {self.plain_objective}",
        ]
        if self.briefing_lines:
            lines.append("")
            lines.append("VOICE:")
            for b in self.briefing_lines:
                lines.append(f"  [{b.get('speaker', '?')}] {b.get('text', '')}")
        return "\n".join(lines)


@dataclass
class FairHUD:
    """Coarse player-readable combat HUD (no exact sim floats)."""

    tick: int
    phase: str  # APPROACH | FIGHT | HOLD | EXTRACT | CRITICAL
    clock_band: str  # early | mid | late | red
    clock_remaining_hint: str  # e.g. "~6 min left"
    objective_bar: str  # empty | started | half | nearly | done
    contact: str  # none | light | moderate | heavy | extreme
    under_fire: bool
    team_feeling: str  # fresh | steady | strained | breaking
    vane: str
    ketha: str
    last_flavor: str
    approach_feel: str  # far | closing | on_it | overextended
    notes: list[str] = field(default_factory=list)
    # Eco bands (player-visible when base building allowed)
    eco_feel: str = "n/a"  # dry | thin | steady | fat | n/a
    metal_feel: str = "n/a"
    energy_feel: str = "n/a"
    buildpower_feel: str = "n/a"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def text(self) -> str:
        fire = "UNDER FIRE" if self.under_fire else "quiet"
        lines = [
            f"HUD t={self.tick} PHASE={self.phase} clock={self.clock_band} ({self.clock_remaining_hint})",
            f"objective=[{self.objective_bar}] contact={self.contact} ({fire})",
            f"team={self.team_feeling} approach={self.approach_feel}",
            f"heroes: Vane={self.vane}  Ketha={self.ketha}",
            f"last: {self.last_flavor}",
        ]
        if self.eco_feel != "n/a":
            lines.append(
                f"eco={self.eco_feel} metal={self.metal_feel} "
                f"energy={self.energy_feel} bp={self.buildpower_feel}"
            )
        for n in self.notes:
            lines.append(f"note: {n}")
        return "\n".join(lines)


def build_fair_hud(
    *,
    tick: int,
    duration_ticks: int,
    progress: float,
    approach: float,
    threat: float,
    player_strength: float,
    enemy_strength: float,
    vane_hp: float,
    ketha_hp: float,
    extract: float,
    last_action: str,
    rng: random.Random | None = None,
    eco_bands: dict[str, str] | None = None,
    show_eco: bool = False,
) -> FairHUD:
    """Project hidden sim truth → noisy player HUD.

    Small observation noise so the agent cannot reverse-engineer exact floats.
    """
    rng = rng or random.Random(tick * 17 + 3)
    # jitter truth slightly before banding
    def j(v: float, s: float = 0.06) -> float:
        return max(0.0, min(1.0, v + rng.uniform(-s, s)))

    progress_j = j(progress, 0.04)
    threat_j = j(threat, 0.07)
    approach_j = j(approach, 0.05)
    p_j = j(player_strength, 0.05)
    clock_frac = tick / max(1, duration_ticks)

    if clock_frac < 0.25:
        clock_band = "early"
    elif clock_frac < 0.55:
        clock_band = "mid"
    elif clock_frac < 0.8:
        clock_band = "late"
    else:
        clock_band = "red"

    remain_min = max(0, int(round((1.0 - clock_frac) * (duration_ticks * 5 / 60))))
    clock_hint = f"~{remain_min} min left" if remain_min > 0 else "clock dying"

    # Bands must not cry "nearly done" at half progress — that made the proxy
    # EXTRACT forever while the true objective sat at ~0.7.
    if progress_j < 0.1:
        obj_bar = "empty"
    elif progress_j < 0.4:
        obj_bar = "started"
    elif progress_j < 0.75:
        obj_bar = "half"
    elif progress_j < 0.93:
        obj_bar = "nearly"
    else:
        obj_bar = "done"

    contact = _band(threat_j)
    under_fire = threat_j > 0.42 and approach_j > 0.2

    # team feeling from strength + heroes
    hero_min = min(vane_hp, ketha_hp)
    feel_score = 0.45 * p_j + 0.35 * hero_min + 0.2 * (1.0 - threat_j)
    if feel_score > 0.72:
        team = "fresh"
    elif feel_score > 0.52:
        team = "steady"
    elif feel_score > 0.32:
        team = "strained"
    else:
        team = "breaking"

    if approach_j < 0.2:
        approach_feel = "far"
    elif approach_j < 0.45:
        approach_feel = "closing"
    elif approach_j < 0.8:
        approach_feel = "on_it"
    else:
        approach_feel = "overextended"

    if extract > 0.45 and progress >= 0.92:
        phase = "EXTRACT"
    elif hero_min < 0.35 or team == "breaking":
        phase = "CRITICAL"
    elif progress >= 0.75 and approach > 0.4 and threat_j < 0.55:
        phase = "HOLD"
    elif approach > 0.25 or threat > 0.35:
        phase = "FIGHT"
    else:
        phase = "APPROACH"

    flavor = {
        "PUSH_OBJECTIVE": "squads lean into the objective",
        "PROBE": "scouts feel the edge of the zone",
        "FLANK": "element peels wide for a side angle",
        "HOLD_AND_HEAL": "lines dig in; rezbots crawl",
        "RALLY": "banner up — reforming the knot",
        "FALLBACK": "breaking contact, dragging wounded",
        "EXTRACT": "vector home — eyes on extract",
        "WAIT": "holding breath",
        "BUILD_MEX": "constructors plant metal extractors",
        "BUILD_ENERGY": "wind and solar rise on the shelf",
        "BUILD_CON": "another constructor rolls out",
        "EXPAND_FRONT": "footprint creeps toward the front",
        "RECLAIM": "wrecks feed the stockpile",
        "TECH_UP": "labs climb a tech rung",
        "DEFEND_BASE": "guns turn home to guard the plant",
        "": "deployment dust settling",
    }.get(last_action, f"did {last_action}")

    notes: list[str] = []
    if obj_bar == "done":
        notes.append("Objective complete — extract is legal. Get out.")
    elif obj_bar == "nearly":
        notes.append("Objective almost done — finish the job before extract.")
    if clock_band == "red" and obj_bar not in ("nearly", "done"):
        notes.append("Soft clock red — finish or live.")
    if under_fire and team in ("strained", "breaking"):
        notes.append("Incoming is chewing the roster.")
    if vane_hp < 0.35 or ketha_hp < 0.35:
        notes.append("A named hero is in bad shape.")

    eco = eco_bands or {}
    eco_feel = eco.get("eco", "n/a") if show_eco else "n/a"
    metal_feel = eco.get("metal", "n/a") if show_eco else "n/a"
    energy_feel = eco.get("energy", "n/a") if show_eco else "n/a"
    bp_feel = eco.get("buildpower", "n/a") if show_eco else "n/a"
    if show_eco and eco_feel in ("dry", "thin"):
        notes.append("Eco feels thin — plant income before pure push.")
    if show_eco and phase == "APPROACH" and energy_feel == "dry":
        notes.append("Energy stall risk — power first.")

    return FairHUD(
        tick=tick,
        phase=phase,
        clock_band=clock_band,
        clock_remaining_hint=clock_hint,
        objective_bar=obj_bar,
        contact=contact,
        under_fire=under_fire,
        team_feeling=team,
        vane=_hero_tag(vane_hp),
        ketha=_hero_tag(ketha_hp),
        last_flavor=flavor,
        approach_feel=approach_feel,
        notes=notes,
        eco_feel=eco_feel,
        metal_feel=metal_feel,
        energy_feel=energy_feel,
        buildpower_feel=bp_feel,
    )


def fair_hud_to_wall_sensors(hud: FairHUD) -> dict[str, float]:
    """Translate fair HUD bands into umwelt wall sensors (no raw truth).

    This is the only path from the world into the belief graph during play.
    """
    contact_map = {"none": 0.05, "light": 0.25, "moderate": 0.5, "heavy": 0.75, "extreme": 0.95}
    obj_map = {"empty": 0.05, "started": 0.25, "half": 0.55, "nearly": 0.85, "done": 0.98}
    clock_map = {"early": 0.15, "mid": 0.45, "late": 0.7, "red": 0.92}
    team_map = {"fresh": 0.85, "steady": 0.65, "strained": 0.4, "breaking": 0.15}
    approach_map = {"far": 0.1, "closing": 0.35, "on_it": 0.65, "overextended": 0.9}
    hero_map = {"ok": 1.0, "bruised": 0.75, "wounded": 0.5, "critical": 0.25, "down": 0.0}

    contact = contact_map.get(hud.contact, 0.4)
    obj = obj_map.get(hud.objective_bar, 0.2)
    clock = clock_map.get(hud.clock_band, 0.5)
    team = team_map.get(hud.team_feeling, 0.5)
    approach = approach_map.get(hud.approach_feel, 0.3)
    vane = hero_map.get(hud.vane, 0.5)
    ketha = hero_map.get(hud.ketha, 0.5)
    heroes = (vane + ketha) / 2.0

    # Signed mood evidence derived ONLY from fair bands
    aggression = (1.0 - contact) * 0.5 + (0.3 if hud.phase == "FIGHT" else 0.0) - (0.4 if hud.phase == "CRITICAL" else 0.0)
    caution = contact * 0.7 + (0.4 if hud.team_feeling in ("strained", "breaking") else 0.0) + (0.3 if min(vane, ketha) < 0.4 else 0.0)
    focus = 0.2 + obj * 0.5 + (0.2 if hud.phase in ("HOLD", "FIGHT") else 0.0)
    pressure = clock * 0.7 + (0.3 if hud.under_fire else 0.0)
    cohesion = team * 0.9 - (0.2 if hud.approach_feel == "overextended" else 0.0)
    momentum = (obj - 0.3) * 1.0 + (0.2 if hud.phase == "FIGHT" and contact < 0.6 else 0.0) - (0.3 if hud.team_feeling == "breaking" else 0.0)

    def clip_s(v: float) -> float:
        return max(-1.0, min(1.0, v))

    # advantage is UNKNOWN exactly — estimate from team vs contact only
    advantage_est = max(0.0, min(1.0, 0.5 + (team - 0.5) * 0.6 - (contact - 0.4) * 0.4))

    return {
        "proxy_aggression_wall": clip_s(aggression),
        "proxy_caution_wall": clip_s(caution - 0.3),
        "proxy_focus_wall": clip_s(focus - 0.2),
        "proxy_pressure_wall": clip_s(pressure - 0.2),
        "proxy_cohesion_wall": clip_s(cohesion - 0.2),
        "proxy_momentum_wall": clip_s(momentum),
        "mission_objective_wall": obj,
        "mission_threat_wall": contact,
        "mission_clock_wall": clock,
        "mission_progress_wall": obj,
        "force_player_strength_wall": team,
        "force_enemy_strength_wall": contact,  # player only feels contact, not true e_str
        "force_advantage_wall": advantage_est,
        "hero_vane_alive_wall": vane,
        "hero_vane_wounded_wall": max(0.0, 1.0 - vane),
        "hero_vane_near_objective_wall": approach,
        "hero_ketha_alive_wall": ketha,
        "hero_ketha_wounded_wall": max(0.0, 1.0 - ketha),
        "hero_ketha_near_objective_wall": approach,
    }
