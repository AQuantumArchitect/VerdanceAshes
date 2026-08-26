"""Lane AI — umwelt-shaped line-war brain for shoulder-to-shoulder fights.

Maps like Koom Valley interior and All That Simmers are not free-roam blobs:
armies fight in parallel columns. This module owns:

  - LaneGeometry (3–5 across Koom; up to 8 elsewhere)
  - per-lane state + line orders
  - classical "quantum membrane" coherence (high = solid front)
  - policy that assigns mass across lanes

Phase 0: fair_sim + offline tests. Lua gadget wiring is Phase D.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any  # LaneDensity attached as density: Any
import random


LINE_ORDERS = (
    "HOLD_LINE",
    "WEIGHT_LANE",       # extras["lane"]
    "REFUSE_LANE",       # extras["lane"]
    "REINFORCE_LANE",    # extras["lane"]
    "BREAKTHROUGH",      # extras["lane"]
    "REFUSE_FLANK",
    "STAGGER_ADVANCE",
)


@dataclass
class LaneGeometry:
    map_id: str
    lane_count: int
    labels: list[str]
    primary_index: int = 0
    adjacency: list[tuple[int, int]] = field(default_factory=list)
    refuse_cost: float = 0.15
    # optional world AABB hints for future Lua (normalized 0..1 map space)
    strips: list[dict[str, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        n = max(1, min(8, int(self.lane_count)))
        self.lane_count = n
        if len(self.labels) < n:
            self.labels = list(self.labels) + [f"Lane {i}" for i in range(len(self.labels), n)]
        self.labels = self.labels[:n]
        self.primary_index = max(0, min(n - 1, int(self.primary_index)))
        if not self.adjacency:
            self.adjacency = [(i, i + 1) for i in range(n - 1)]
        if not self.strips:
            w = 1.0 / n
            self.strips = [
                {"x0": i * w, "x1": (i + 1) * w, "y0": 0.15, "y1": 0.85} for i in range(n)
            ]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LaneGeometry":
        adj = d.get("adjacency") or []
        adjacency = [tuple(x) for x in adj]  # type: ignore[misc]
        return cls(
            map_id=str(d.get("map_id") or ""),
            lane_count=int(d.get("lane_count") or 3),
            labels=list(d.get("labels") or []),
            primary_index=int(d.get("primary_index") or 0),
            adjacency=adjacency,  # type: ignore[arg-type]
            refuse_cost=float(d.get("refuse_cost") or 0.15),
            strips=list(d.get("strips") or []),
        )


@dataclass
class LaneState:
    """Per-column combat membrane cell."""

    pressure: float = 0.3       # contact intensity 0..1
    hold: float = 0.0           # ownership progress 0..1
    push: float = 0.0           # our forward effort
    bleed: float = 0.0          # losses leaking to neighbors
    friendly_mass: float = 0.25
    enemy_mass: float = 0.25
    contested: float = 0.5

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LineOrder:
    order: str
    lane: int | None = None
    reason: str = ""
    confidence: float = 0.6

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LineFront:
    geometry: LaneGeometry
    lanes: list[LaneState] = field(default_factory=list)
    coherence: float = 0.7
    tempo: float = 0.4
    panic: float = 0.1
    commit: float = 0.5
    last_order: LineOrder | None = None
    # optional quantum membrane (n×n density); kept in sync on orders/combat
    density: Any = None  # LaneDensity | None

    def __post_init__(self) -> None:
        n = self.geometry.lane_count
        if len(self.lanes) < n:
            # slight center bias toward primary
            prim = self.geometry.primary_index
            base = 1.0 / n
            self.lanes = []
            for i in range(n):
                boost = 0.08 if i == prim else 0.0
                self.lanes.append(
                    LaneState(
                        friendly_mass=base + boost,
                        enemy_mass=base,
                        contested=0.55 if i == prim else 0.4,
                        pressure=0.35 if i == prim else 0.25,
                    )
                )
            self._normalize_mass("friendly_mass")
            self._normalize_mass("enemy_mass")
        if self.density is None:
            try:
                from .quantum_membrane import LaneDensity

                self.density = LaneDensity(n=n)
                # seed from classical masses
                self.density.diag = [L.friendly_mass for L in self.lanes]
                self.density.enemy_diag = [L.enemy_mass for L in self.lanes]
                self.density._renorm()
            except Exception:
                self.density = None

    def _normalize_mass(self, attr: str) -> None:
        total = sum(getattr(L, attr) for L in self.lanes) or 1.0
        for L in self.lanes:
            setattr(L, attr, max(0.02, getattr(L, attr) / total))

    def as_dict(self) -> dict[str, Any]:
        return {
            "geometry": self.geometry.as_dict(),
            "lanes": [L.as_dict() for L in self.lanes],
            "coherence": self.coherence,
            "tempo": self.tempo,
            "panic": self.panic,
            "commit": self.commit,
            "last_order": self.last_order.as_dict() if self.last_order else None,
        }

    def fair_bands(self) -> dict[str, Any]:
        """What a human/proxy might feel — no exact enemy mass."""
        labels = self.geometry.labels
        return {
            "front": "solid" if self.coherence > 0.65 else ("ragged" if self.coherence > 0.4 else "broken"),
            "tempo": "pushing" if self.tempo > 0.55 else ("held" if self.tempo > 0.35 else "falling"),
            "lanes": [
                {
                    "name": labels[i],
                    "feel": (
                        "ours" if L.hold > 0.65 else
                        ("contested" if L.contested > 0.45 else "theirs")
                    ),
                    "pressure": (
                        "heavy" if L.pressure > 0.7 else
                        ("moderate" if L.pressure > 0.4 else "light")
                    ),
                }
                for i, L in enumerate(self.lanes)
            ],
        }

    def primary_hold(self) -> float:
        return self.lanes[self.geometry.primary_index].hold

    def held_count(self, thr: float = 0.6) -> int:
        return sum(1 for L in self.lanes if L.hold >= thr)

    def mean_hold(self) -> float:
        return sum(L.hold for L in self.lanes) / max(1, len(self.lanes))


# ---------------------------------------------------------------------------
# Presets — Koom Valley interior 3–5; simmer; generic
# ---------------------------------------------------------------------------

def koom_geometry(lane_count: int = 4) -> LaneGeometry:
    lane_count = max(3, min(5, int(lane_count)))
    packs = {
        3: (
            ["West Green", "Fluid Scar", "East Scar"],
            1,
        ),
        4: (
            ["West Green", "Fluid Scar", "East Scar", "Ridge Path"],
            1,
        ),
        5: (
            ["NW Shelf", "West Green", "Fluid Scar", "East Scar", "Ridge Path"],
            2,
        ),
    }
    labels, prim = packs[lane_count]
    return LaneGeometry(
        map_id="koom_valley",
        lane_count=lane_count,
        labels=list(labels),
        primary_index=prim,
        refuse_cost=0.14,
    )


def simmer_geometry(lane_count: int = 3) -> LaneGeometry:
    lane_count = max(3, min(5, int(lane_count)))
    labels = ["West Simmer", "Central Lane", "East Simmer"]
    if lane_count >= 4:
        labels.append("North Mouth")
    if lane_count >= 5:
        labels.insert(0, "South Staging")
    prim = labels.index("Central Lane") if "Central Lane" in labels else lane_count // 2
    return LaneGeometry(
        map_id="all_that_simmers",
        lane_count=lane_count,
        labels=labels[:lane_count],
        primary_index=prim,
        refuse_cost=0.12,
    )


def geometry_for_map(map_id: str, *, lane_count: int | None = None, width: float = 0.3) -> LaneGeometry | None:
    """Pick geometry; lane_count scales slightly with mission width."""
    mid = (map_id or "").lower()
    if lane_count is None:
        # Early narrow → 3; mid → 4; late wide → 5 on Koom
        if width < 0.35:
            lane_count = 3
        elif width < 0.7:
            lane_count = 4
        else:
            lane_count = 5
    if "koom" in mid:
        return koom_geometry(lane_count)
    if "simmer" in mid:
        return simmer_geometry(min(5, max(3, lane_count - 0)))  # type: ignore[arg-type]
    if mid in ("tabula",):
        # plateau "lanes" as ramp columns
        n = max(3, min(5, int(lane_count)))
        return LaneGeometry(
            map_id=mid,
            lane_count=n,
            labels=[f"Ramp {i+1}" for i in range(n)],
            primary_index=n // 2,
            refuse_cost=0.16,
        )
    return None


# ---------------------------------------------------------------------------
# Policy — line orders from front + mood-ish knobs
# ---------------------------------------------------------------------------

def decide_line(
    front: LineFront,
    *,
    aggression: float = 0.0,
    caution: float = 0.0,
    cohesion: float = 0.5,
    width: float = 0.3,
    enemy: bool = False,
    rng: random.Random | None = None,
) -> LineOrder:
    """Pick a line order. Early width → weight primary; late → more options."""
    rng = rng or random.Random(0)
    geo = front.geometry
    prim = geo.primary_index
    lanes = front.lanes

    # Find weakest / strongest
    holds = [L.hold for L in lanes]
    masses_f = [L.friendly_mass for L in lanes]
    masses_e = [L.enemy_mass for L in lanes]
    weakest = min(range(len(lanes)), key=lambda i: holds[i] - 0.3 * masses_e[i])
    hottest = max(range(len(lanes)), key=lambda i: masses_e[i] * lanes[i].pressure)

    # Coherence crisis
    if front.coherence < 0.35 or front.panic > 0.65:
        return LineOrder("HOLD_LINE", reason="front ragged — dress the line", confidence=0.75)

    # Early / narrow: clear vector on primary
    if width < 0.4 and not enemy:
        if lanes[prim].hold < 0.7:
            if aggression > 0.35:
                return LineOrder("BREAKTHROUGH", lane=prim, reason="narrow card — break primary", confidence=0.8)
            return LineOrder("WEIGHT_LANE", lane=prim, reason="narrow card — weight primary", confidence=0.85)
        return LineOrder("HOLD_LINE", reason="primary owned — hold line", confidence=0.7)

    # Refuse a bleeding outer lane when caution high
    if caution > 0.25 and (weakest == 0 or weakest == len(lanes) - 1):
        if masses_e[weakest] > masses_f[weakest] * 1.35 and lanes[weakest].hold < 0.35:
            return LineOrder(
                "REFUSE_LANE",
                lane=weakest,
                reason=f"refuse bleeding {'west' if weakest == 0 else 'east'}",
                confidence=0.7,
            )

    if front.coherence > 0.55 and aggression > 0.2:
        target = prim if width < 0.55 else hottest
        if width >= 0.7 and rng.random() < 0.35:
            return LineOrder("STAGGER_ADVANCE", reason="wide card — stagger advance", confidence=0.65)
        if aggression > 0.55 and lanes[target].enemy_mass < 0.35:
            return LineOrder("BREAKTHROUGH", lane=target, reason="breakthrough soft lane", confidence=0.7)
        return LineOrder("WEIGHT_LANE", lane=target, reason="weight pressure lane", confidence=0.68)

    if cohesion > 0.3 and lanes[prim].hold > 0.4:
        return LineOrder("REINFORCE_LANE", lane=prim, reason="reinforce primary hold", confidence=0.65)

    if caution > 0.4:
        return LineOrder("REFUSE_FLANK", reason="collapse flanks inward", confidence=0.6)

    return LineOrder("HOLD_LINE", reason="default dress", confidence=0.55)


def apply_line_order(front: LineFront, order: LineOrder, *, dt: float = 1.0) -> LineFront:
    """Redistribute mass / push according to order (mutates and returns front)."""
    front.last_order = order
    n = len(front.lanes)
    if n == 0:
        return front
    o = order.order
    lane = order.lane if order.lane is not None else front.geometry.primary_index
    lane = max(0, min(n - 1, lane))
    # Quantum membrane channel (rephase / dephase / collapse)
    if front.density is not None:
        try:
            front.density.apply_order(o, lane)
        except Exception:
            pass

    def shift_to(target: int, amount: float) -> None:
        donors = [i for i in range(n) if i != target]
        if not donors:
            return
        take = amount / len(donors)
        for i in donors:
            moved = min(take, front.lanes[i].friendly_mass * 0.5)
            front.lanes[i].friendly_mass -= moved
            front.lanes[target].friendly_mass += moved

    if o == "HOLD_LINE":
        avg = sum(L.friendly_mass for L in front.lanes) / n
        for L in front.lanes:
            L.friendly_mass = 0.7 * L.friendly_mass + 0.3 * avg
            L.push = max(0.0, L.push * 0.9)
        front.coherence = min(1.0, front.coherence + 0.04 * dt)
    elif o == "WEIGHT_LANE":
        shift_to(lane, 0.12 * dt)
        front.lanes[lane].push = min(1.0, front.lanes[lane].push + 0.12 * dt)
        front.coherence = max(0.15, front.coherence - 0.02 * dt)
        front.commit = min(1.0, front.commit + 0.05)
    elif o == "REINFORCE_LANE":
        shift_to(lane, 0.1 * dt)
        front.lanes[lane].hold = min(1.0, front.lanes[lane].hold + 0.03 * dt)
        front.coherence = min(1.0, front.coherence + 0.02 * dt)
    elif o == "REFUSE_LANE":
        # pull mass out of lane into neighbors
        pull = front.lanes[lane].friendly_mass * (0.35 + front.geometry.refuse_cost)
        front.lanes[lane].friendly_mass -= pull
        neigh = [j for a, b in front.geometry.adjacency for j in (a, b) if lane in (a, b) and j != lane]
        if not neigh:
            neigh = [i for i in range(n) if i != lane]
        for j in neigh:
            front.lanes[j].friendly_mass += pull / len(neigh)
        front.lanes[lane].push = 0.0
        front.lanes[lane].bleed = min(1.0, front.lanes[lane].bleed + 0.1)
        front.coherence = max(0.1, front.coherence - 0.03 * dt)
    elif o == "BREAKTHROUGH":
        shift_to(lane, 0.2 * dt)
        front.lanes[lane].push = min(1.0, front.lanes[lane].push + 0.22 * dt)
        # bleed neighbors
        for a, b in front.geometry.adjacency:
            if lane in (a, b):
                other = b if a == lane else a
                front.lanes[other].bleed = min(1.0, front.lanes[other].bleed + 0.08 * dt)
                front.lanes[other].friendly_mass = max(0.04, front.lanes[other].friendly_mass - 0.03 * dt)
        front.coherence = max(0.1, front.coherence - 0.06 * dt)
        front.tempo = min(1.0, front.tempo + 0.08 * dt)
        front.commit = min(1.0, front.commit + 0.1)
    elif o == "REFUSE_FLANK":
        if n >= 3:
            for edge in (0, n - 1):
                pull = front.lanes[edge].friendly_mass * 0.25
                front.lanes[edge].friendly_mass -= pull
                mid = n // 2
                front.lanes[mid].friendly_mass += pull * 0.6
                # rest to near-mid
                near = mid - 1 if edge == 0 else mid + 1
                near = max(0, min(n - 1, near))
                front.lanes[near].friendly_mass += pull * 0.4
        front.coherence = min(1.0, front.coherence + 0.03 * dt)
    elif o == "STAGGER_ADVANCE":
        for i, L in enumerate(front.lanes):
            if i % 2 == front.last_order.lane if False else (i % 2 == 0):
                L.push = min(1.0, L.push + 0.1 * dt)
            else:
                L.push = max(0.0, L.push * 0.85)
        front.tempo = min(1.0, front.tempo + 0.05 * dt)
        front.coherence = max(0.2, front.coherence - 0.015 * dt)

    front._normalize_mass("friendly_mass")
    # sync classical masses from density if present (quantum → classical)
    if front.density is not None and len(front.density.diag) == n:
        for i, L in enumerate(front.lanes):
            # blend so classical push state still matters
            L.friendly_mass = 0.55 * L.friendly_mass + 0.45 * front.density.diag[i]
        front._normalize_mass("friendly_mass")
        try:
            front.coherence = max(
                0.05,
                min(1.0, 0.5 * front.coherence + 0.5 * (0.3 + 2.0 * front.density.mean_coherence())),
            )
        except Exception:
            pass
    return front


def tick_lane_combat(
    front: LineFront,
    *,
    player_strength: float,
    enemy_strength: float,
    fortified: bool = False,
    rng: random.Random | None = None,
    dt: float = 1.0,
) -> LineFront:
    """Resolve one abstract combat tick across lanes after orders applied."""
    rng = rng or random.Random(0)
    fort = 1.15 if fortified else 1.0
    # Quantum combat channel first (coherence bonus on solid fronts)
    dens_holds: list[float] | None = None
    if front.density is not None:
        try:
            dens_holds = front.density.combat_tick(
                player_strength=player_strength,
                enemy_strength=enemy_strength,
                primary=front.geometry.primary_index,
                fortified=fortified,
                rng=rng,
            )
            # pull enemy mass from density
            if len(front.density.enemy_diag) == len(front.lanes):
                for i, L in enumerate(front.lanes):
                    L.enemy_mass = 0.6 * L.enemy_mass + 0.4 * front.density.enemy_diag[i]
        except Exception:
            dens_holds = None

    for i, L in enumerate(front.lanes):
        # enemy slightly prefers primary + high friendly mass
        bias = 1.1 if i == front.geometry.primary_index else 1.0
        # coherence bonus from quantum membrane
        coh_bonus = 1.0
        if front.density is not None:
            coh_bonus = 1.0 + 0.2 * front.density.mean_coherence() / 0.2
        # local fight score
        f = L.friendly_mass * player_strength * (1.0 + 0.5 * L.push) * coh_bonus
        e = L.enemy_mass * enemy_strength * fort * bias
        ratio = f / max(0.05, f + e)
        if dens_holds is not None and i < len(dens_holds):
            ratio = 0.65 * ratio + 0.35 * dens_holds[i]
        L.pressure = max(0.05, min(0.98, 0.55 * (1.0 - ratio) + 0.3 * L.enemy_mass + rng.uniform(-0.03, 0.03)))
        L.contested = max(0.0, min(1.0, 1.0 - abs(ratio - 0.5) * 2.0))
        # hold progress
        if ratio > 0.50:
            gain = 0.05 * dt * (ratio - 0.42) * (1.0 + 0.45 * L.push)
            L.hold = min(1.0, L.hold + gain)
        else:
            L.hold = max(0.0, L.hold - 0.025 * dt * (0.52 - ratio))
        # bleed from low mass
        if L.friendly_mass < 0.12:
            L.bleed = min(1.0, L.bleed + 0.05 * dt)
        else:
            L.bleed = max(0.0, L.bleed - 0.02 * dt)
        # enemy mass drifts toward contested
        L.enemy_mass = max(0.05, min(0.6, L.enemy_mass + rng.uniform(-0.02, 0.02) + 0.01 * (0.5 - ratio)))
    front._normalize_mass("enemy_mass")

    # front coherence from hold variance + bleed (+ density purity)
    holds = [L.hold for L in front.lanes]
    mean_h = sum(holds) / len(holds)
    var = sum((h - mean_h) ** 2 for h in holds) / len(holds)
    bleed = sum(L.bleed for L in front.lanes) / len(front.lanes)
    front.coherence = max(0.05, min(1.0, 0.75 - 1.2 * var - 0.35 * bleed + 0.1 * mean_h))
    if front.density is not None:
        front.coherence = max(
            0.05,
            min(1.0, 0.55 * front.coherence + 0.45 * front.density.purity),
        )
    front.tempo = max(0.0, min(1.0, 0.4 * mean_h + 0.4 * (sum(L.push for L in front.lanes) / len(front.lanes))))
    front.panic = max(0.0, min(1.0, 0.5 * (1.0 - front.coherence) + 0.3 * (1.0 - player_strength)))
    return front


def lane_objective_progress(front: LineFront, *, width: float = 0.3) -> float:
    """Scalar progress for fair_sim: primary-heavy early; multipath late."""
    prim = front.primary_hold()
    mean = front.mean_hold()
    held = front.held_count(0.55) / max(1, front.geometry.lane_count)
    if width < 0.4:
        return 0.75 * prim + 0.25 * mean
    if width < 0.7:
        return 0.5 * prim + 0.3 * mean + 0.2 * held
    # wide: any solid multi-lane control counts
    return 0.3 * prim + 0.35 * mean + 0.35 * held
