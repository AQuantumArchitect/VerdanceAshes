"""Compact BAR eco manifold — ROI priors from bar-eco-manifold-five.

Source inspiration: https://bar-eco-manifold-five.vercel.app/
(structure cost m/e/l, mex xm, energy o, buildpower bp)

Used by:
  - fair_sim eco_expand / siege income curves
  - bar_brain training priors (what to build when metal/energy starved)
  - FairHUD eco bands

Not a full economy sim — a decision-shaped prior so the proxy learns
"energy first on no-metal maps", "mex payback", "con before tech".
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class StructurePrior:
    key: str
    name: str
    metal: float
    energy: float
    buildtime: float
    tags: tuple[str, ...]
    # outputs
    metal_income: float = 0.0  # mex xm-like
    energy_income: float = 0.0  # solar o / wind avg
    buildpower: float = 0.0
    e_store: float = 0.0
    m_store: float = 0.0

    def payback_frames_metal(self, metal_rate: float = 1.0) -> float:
        """Rough metal payback if this is a mex-like producer."""
        if self.metal_income <= 0:
            return float("inf")
        return self.metal / max(1e-6, self.metal_income * metal_rate)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# Legion-leaning priors (Verdance player roster is Legion-coded in many cards).
# Numbers distilled from the public ROI manifold pack (t1 land focus).
STRUCTURES: dict[str, StructurePrior] = {
    "t1_mex": StructurePrior(
        "t1_mex", "Leg. T1 Mex", metal=50, energy=500, buildtime=1880,
        tags=("t1", "mex", "land"), metal_income=0.8,
    ),
    "t1_wind": StructurePrior(
        "t1_wind", "Leg. Wind Turbine", metal=45, energy=175, buildtime=1680,
        tags=("t1", "energy", "variable", "land"), energy_income=11.0,
    ),
    "t1_solar": StructurePrior(
        "t1_solar", "Leg. Solar Collector", metal=155, energy=0, buildtime=2800,
        tags=("t1", "energy", "land"), energy_income=20.0,
    ),
    "t1_estor": StructurePrior(
        "t1_estor", "Leg. Energy Storage", metal=175, energy=1800, buildtime=4260,
        tags=("t1", "estor", "land"), e_store=6000,
    ),
    "t1_mstor": StructurePrior(
        "t1_mstor", "Leg. Metal Storage", metal=340, energy=590, buildtime=2920,
        tags=("t1", "mstor", "land"), m_store=3000,
    ),
    "t1_con": StructurePrior(
        "t1_con", "Leg. Con. Kbot", metal=100, energy=1600, buildtime=3250,
        tags=("t1", "constructor", "land"), buildpower=75,
    ),
    "t1_nano": StructurePrior(
        "t1_nano", "Leg. Nano Turret", metal=230, energy=3200, buildtime=5300,
        tags=("t1", "nanolathe", "land"), buildpower=200,
    ),
    "moho": StructurePrior(
        "moho", "Leg. Moho Mex", metal=640, energy=8100, buildtime=14100,
        tags=("t2", "mex", "land"), metal_income=4.0, m_store=600,
    ),
}


@dataclass
class EcoState:
    """Abstract eco for fair_sim / bar_brain (0..1 scales + soft counts)."""

    metal: float = 0.15  # stockpile feel 0..1
    energy: float = 0.2
    metal_income: float = 0.15  # 0..1
    energy_income: float = 0.2
    buildpower: float = 0.15
    mex_count: float = 0.0
    energy_count: float = 0.0
    con_count: float = 0.0
    tech: float = 0.0  # 0 t1 .. 1 t2-ish
    stall_metal: bool = False
    stall_energy: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def eco_level(self) -> float:
        """Combined eco fatness for objective progress on eco_expand."""
        return max(
            0.0,
            min(
                1.0,
                0.35 * self.metal_income
                + 0.35 * self.energy_income
                + 0.2 * self.buildpower
                + 0.1 * self.tech,
            ),
        )

    def bands(self) -> dict[str, str]:
        def b(x: float) -> str:
            if x < 0.2:
                return "dry"
            if x < 0.4:
                return "thin"
            if x < 0.7:
                return "steady"
            return "fat"

        return {
            "metal": b(self.metal_income),
            "energy": b(self.energy_income),
            "buildpower": b(self.buildpower),
            "eco": b(self.eco_level()),
        }


def recommend_build(eco: EcoState, *, no_metal_map: bool = False) -> str:
    """Prior action key from manifold ROI logic (player-legal heuristic)."""
    if eco.energy_income < 0.35 or eco.stall_energy:
        return "BUILD_ENERGY"
    if (not no_metal_map) and (eco.metal_income < 0.35 or eco.stall_metal):
        return "BUILD_MEX"
    if no_metal_map and eco.energy_income < 0.55:
        return "BUILD_ENERGY"
    if eco.buildpower < 0.4 and eco.con_count < 3:
        return "BUILD_CON"
    if eco.eco_level() > 0.55 and eco.tech < 0.4:
        return "TECH_UP"
    return "EXPAND_FRONT"


def apply_build_action(eco: EcoState, action: str, *, no_metal_map: bool = False, noise: float = 1.0) -> EcoState:
    """Mutate a copy of eco state from a build/expand action."""
    e = EcoState(**eco.as_dict())
    n = max(0.5, float(noise))

    if action == "BUILD_MEX":
        if no_metal_map:
            # pretend converter-fed metal bump via energy spend
            e.metal_income = min(1.0, e.metal_income + 0.04 * n)
            e.energy_income = max(0.05, e.energy_income - 0.02)
        else:
            e.mex_count += 1
            e.metal_income = min(1.0, e.metal_income + 0.08 * n)
        e.metal = min(1.0, e.metal + 0.03)
    elif action == "BUILD_ENERGY":
        e.energy_count += 1
        e.energy_income = min(1.0, e.energy_income + 0.1 * n)
        e.energy = min(1.0, e.energy + 0.05)
        if no_metal_map:
            e.metal_income = min(1.0, e.metal_income + 0.05 * n)  # converters
    elif action == "BUILD_CON":
        e.con_count += 1
        e.buildpower = min(1.0, e.buildpower + 0.1 * n)
    elif action == "TECH_UP":
        if e.eco_level() >= 0.45:
            e.tech = min(1.0, e.tech + 0.12 * n)
            e.metal_income = min(1.0, e.metal_income + 0.04)
            e.energy_income = min(1.0, e.energy_income + 0.03)
    elif action == "EXPAND_FRONT":
        e.metal_income = min(1.0, e.metal_income + 0.03 * n)
        e.energy_income = min(1.0, e.energy_income + 0.02 * n)
        e.buildpower = min(1.0, e.buildpower + 0.02)
    elif action == "RECLAIM":
        e.metal = min(1.0, e.metal + 0.06 * n)
        e.energy = min(1.0, e.energy + 0.03)

    # passive income tick
    e.metal = min(1.0, e.metal + 0.02 * e.metal_income)
    e.energy = min(1.0, e.energy + 0.02 * e.energy_income)
    e.stall_metal = e.metal < 0.12 and e.metal_income < 0.25
    e.stall_energy = e.energy < 0.12 and e.energy_income < 0.25
    return e


def eco_wall_sensors(eco: EcoState) -> dict[str, float]:
    """Optional eco walls for bar_brain DomainSpec (fair bands only)."""
    bands = eco.bands()
    bmap = {"dry": 0.1, "thin": 0.35, "steady": 0.6, "fat": 0.9}
    return {
        "eco_metal_wall": bmap[bands["metal"]],
        "eco_energy_wall": bmap[bands["energy"]],
        "eco_buildpower_wall": bmap[bands["buildpower"]],
        "eco_level_wall": bmap[bands["eco"]],
        "eco_tech_wall": max(0.0, min(1.0, eco.tech)),
    }


MANIFOLD_NOTES = (
    "bar-eco-manifold-five.vercel.app — industrial structure ROI. "
    "T1 mex ~50m/500e payback via xm; wind cheap energy; solar steady o; "
    "con bp before tech; no-metal maps force energy→converter path."
)
