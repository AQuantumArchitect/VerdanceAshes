"""Novel quantum-brain mechanisms for Verdance dual manifolds.

These are *classical simulations of quantum structure* suitable for offline
fair_sim / bar_brain / campaign craft — not a claim of physical qubits.

Mechanisms
----------
1. **PathKet** — complex amplitudes over campaign paths A/B/C (superposition
   of winning futures). Mission outcomes apply unitary-ish rotations;
   soft measurement nudges without full collapse until endgame.

2. **CampaignDensity** — Hermitian expectation + off-diagonal path coherence.
   Phase-1 upgrade of CampaignRho packed form.

3. **ProxyBelief** — reduced density / partial-trace stand-in: only fair axes.
   HUD observation weakly collapses belief, never campaign ρ (fair rule).

4. **LaneDensity** — n×n membrane for shoulder-to-shoulder war.
   Diagonal = mass; off-diagonal = line coherence. Orders rephase / dephase.

5. **PredicateInterference** — multipath win predicates as amplitudes.
   Constructive when vectors cohere; destructive when proxy thrash-switches.

6. **SolutionEntropy** — von Neumann / Shannon width of viable vector mix.

7. **DecoyPOVM** — choosing a decoy injects dephasing on belief + path_space.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, asdict
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def shannon_entropy(ps: list[float]) -> float:
    s = 0.0
    for p in ps:
        if p > 1e-12:
            s -= p * math.log(p + 1e-15)
    return s


def von_neumann_diag(diag: list[float]) -> float:
    """Entropy of a classical mixture (diag of ρ)."""
    tot = sum(max(0.0, d) for d in diag) or 1.0
    ps = [max(0.0, d) / tot for d in diag]
    return shannon_entropy(ps)


# ---------------------------------------------------------------------------
# 1. PathKet — path superposition
# ---------------------------------------------------------------------------

PATH_LABELS = ("A", "B", "C")  # Armada / Free-ashes / Void-exit


@dataclass
class PathKet:
    """Complex amplitudes α|A⟩+β|B⟩+γ|C⟩ stored as (re, im) triples."""

    re: list[float] = field(default_factory=lambda: [1 / math.sqrt(3)] * 3)
    im: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> None:
        n2 = sum(r * r + i * i for r, i in zip(self.re, self.im)) or 1.0
        n = math.sqrt(n2)
        self.re = [r / n for r in self.re]
        self.im = [i / n for i in self.im]

    def probs(self) -> dict[str, float]:
        return {
            PATH_LABELS[k]: self.re[k] * self.re[k] + self.im[k] * self.im[k]
            for k in range(3)
        }

    def purity(self) -> float:
        """Tr(ρ²) for pure ket = 1; after decoherence we track separately."""
        p = self.probs()
        return sum(v * v for v in p.values())  # lower bound if mixed

    def rotate(self, axis: int, theta: float) -> None:
        """SU(2)-like rotation in the plane of axis and next path."""
        j = (axis + 1) % 3
        c, s = math.cos(theta), math.sin(theta)
        r0, i0 = self.re[axis], self.im[axis]
        r1, i1 = self.re[j], self.im[j]
        self.re[axis] = c * r0 - s * r1
        self.im[axis] = c * i0 - s * i1
        self.re[j] = s * r0 + c * r1
        self.im[j] = s * i0 + c * i1
        self.normalize()

    def soft_measure(self, outcome: str, strength: float = 0.35) -> str:
        """POVM-style nudge toward `outcome` without full collapse.

        Uses a soft mix with the target basis state so repeated measures
        cannot drive other amplitudes to numerical zero overnight.
        """
        idx = PATH_LABELS.index(outcome) if outcome in PATH_LABELS else 0
        s = _clamp01(strength)
        # mix: |ψ⟩ ← √(1-s)|ψ⟩ + √s |outcome⟩  (approx on real/imag)
        keep = math.sqrt(max(0.0, 1.0 - s))
        add = math.sqrt(s)
        self.re = [keep * r for r in self.re]
        self.im = [keep * i for i in self.im]
        self.re[idx] += add
        self.normalize()
        # floor so no path fully dies
        for k in range(3):
            p = self.re[k] * self.re[k] + self.im[k] * self.im[k]
            if p < 0.02:
                self.re[k] += 0.12
        self.normalize()
        return outcome

    def hard_measure(self, rng: random.Random | None = None) -> str:
        rng = rng or random.Random(0)
        ps = self.probs()
        r = rng.random()
        acc = 0.0
        for lab in PATH_LABELS:
            acc += ps[lab]
            if r <= acc:
                # collapse
                self.re = [1.0 if lab == L else 0.0 for L in PATH_LABELS]
                self.im = [0.0, 0.0, 0.0]
                return lab
        return "C"

    def phase_kick(self, k: int, phi: float) -> None:
        """Relative phase on path k (interference control)."""
        c, s = math.cos(phi), math.sin(phi)
        r, i = self.re[k], self.im[k]
        self.re[k] = c * r - s * i
        self.im[k] = s * r + c * i

    def as_dict(self) -> dict[str, Any]:
        return {"re": list(self.re), "im": list(self.im), "probs": self.probs()}

    @classmethod
    def from_weights(cls, a: float, b: float, c: float) -> "PathKet":
        raw = [max(0.0, a), max(0.0, b), max(0.0, c)]
        s = sum(raw) or 1.0
        amps = [math.sqrt(x / s) for x in raw]
        return cls(re=amps, im=[0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# 2. CampaignDensity — path coherence membrane
# ---------------------------------------------------------------------------

@dataclass
class CampaignDensity:
    """Path-space density membrane: 3×3 Hermitian (stored upper triangle).

    diag[i] = path weight; off[i] = Re(ρ_{i,i+1}); phase tracked lightly.
    """

    diag: list[float] = field(default_factory=lambda: [1 / 3, 1 / 3, 1 / 3])
    off_re: list[float] = field(default_factory=lambda: [0.15, 0.15, 0.1])  # 01,12,20
    off_im: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    phi: float = 0.0  # campaign progress 0..1
    purity: float = 0.85

    def __post_init__(self) -> None:
        self._renorm_diag()

    def _renorm_diag(self) -> None:
        s = sum(max(0.0, d) for d in self.diag) or 1.0
        self.diag = [max(0.0, d) / s for d in self.diag]

    def path_weights(self) -> dict[str, float]:
        return {PATH_LABELS[i]: self.diag[i] for i in range(3)}

    def coherence(self) -> float:
        return _clamp01(sum(abs(x) for x in self.off_re) / 0.45)

    def entropy(self) -> float:
        return von_neumann_diag(self.diag)

    def max_entropy(self) -> float:
        return math.log(3.0)

    def width_from_entropy(self) -> float:
        """Map path entropy → campaign path-space width feel 0..1."""
        return _clamp01(self.entropy() / self.max_entropy())

    def dephase(self, amount: float = 0.1) -> None:
        a = _clamp01(amount)
        self.off_re = [x * (1.0 - a) for x in self.off_re]
        self.off_im = [x * (1.0 - a) for x in self.off_im]
        self.purity = max(0.2, self.purity * (1.0 - 0.5 * a))

    def rephase(self, amount: float = 0.05) -> None:
        a = _clamp01(amount)
        # pull off-diagonals toward geometric mean of diags (pure-state-ish)
        targets = [
            math.sqrt(max(0.0, self.diag[0] * self.diag[1])),
            math.sqrt(max(0.0, self.diag[1] * self.diag[2])),
            math.sqrt(max(0.0, self.diag[2] * self.diag[0])),
        ]
        self.off_re = [
            (1 - a) * o + a * 0.5 * t for o, t in zip(self.off_re, targets)
        ]
        self.purity = min(1.0, self.purity + 0.3 * a)

    def apply_path_nudge(self, path: str, strength: float = 0.08) -> None:
        idx = PATH_LABELS.index(path) if path in PATH_LABELS else 0
        self.diag[idx] += strength
        for i in range(3):
            if i != idx:
                self.diag[i] = max(0.02, self.diag[i] - strength / 2)
        self._renorm_diag()
        # winning a path slightly dephases others
        self.dephase(0.04 * strength / 0.08)

    def evolve_after_mission(
        self,
        *,
        won: bool,
        mission_index: int,
        path_hint: str | None = None,
        n_missions: int = 15,
        vector_diversity: float = 0.3,
    ) -> None:
        self.phi = max(self.phi, (mission_index + (1.0 if won else 0.4)) / max(1, n_missions))
        if won:
            if path_hint in PATH_LABELS:
                self.apply_path_nudge(path_hint, 0.1)
            else:
                # win without path commit → mild rephase (still multipath)
                self.rephase(0.04)
            # diversity of play keeps purity mid
            if vector_diversity > 0.5:
                self.dephase(0.03)
        else:
            self.dephase(0.08)
            # loss spreads probability (confusion)
            self.diag = [0.7 * d + 0.1 for d in self.diag]
            self._renorm_diag()

    def as_dict(self) -> dict[str, Any]:
        return {
            "diag": list(self.diag),
            "off_re": list(self.off_re),
            "off_im": list(self.off_im),
            "phi": self.phi,
            "purity": self.purity,
            "path_weights": self.path_weights(),
            "coherence": round(self.coherence(), 4),
            "entropy": round(self.entropy(), 4),
            "width_entropy": round(self.width_from_entropy(), 4),
        }

    @classmethod
    def from_path_weights(cls, a: float, b: float, c: float, purity: float = 0.85) -> "CampaignDensity":
        s = max(1e-9, a + b + c)
        d = [a / s, b / s, c / s]
        off = [
            0.5 * purity * math.sqrt(d[0] * d[1]),
            0.5 * purity * math.sqrt(d[1] * d[2]),
            0.4 * purity * math.sqrt(d[2] * d[0]),
        ]
        return cls(diag=d, off_re=off, purity=purity)


# ---------------------------------------------------------------------------
# 3. ProxyBelief — fair reduced density
# ---------------------------------------------------------------------------

FAIR_BELIEF_AXES = (
    "aggression",
    "caution",
    "focus",
    "pressure",
    "cohesion",
    "momentum",
    "objective",
    "threat",
)


@dataclass
class ProxyBelief:
    """What the proxy *thinks* — partial trace stand-in over fair axes only.

    Never stores campaign ρ, win_predicates, or enemy exact mass.
    """

    expect: dict[str, float] = field(default_factory=dict)
    # "off-diagonal" belief coherence between related pairs
    coherence: float = 0.6
    confusion: float = 0.1  # raised by decoy POVMs
    width_band: str = "narrow"
    samples: int = 0

    def __post_init__(self) -> None:
        if not self.expect:
            self.expect = {a: 0.0 for a in FAIR_BELIEF_AXES}

    def observe_hud(self, hud: dict[str, Any], mood_signed: dict[str, float] | None = None) -> None:
        """Weak collapse from fair HUD / mood only."""
        self.samples += 1
        eta = 0.35  # wall-tier-ish
        ms = mood_signed or {}
        for k in FAIR_BELIEF_AXES:
            if k in ms:
                prev = self.expect.get(k, 0.0)
                self.expect[k] = (1 - eta) * prev + eta * float(ms[k])
        # HUD bands → soft axes
        contact = str(hud.get("contact") or "none")
        if contact in ("heavy", "brutal"):
            self.expect["threat"] = (1 - eta) * self.expect.get("threat", 0) + eta * 0.7
            self.expect["pressure"] = (1 - eta) * self.expect.get("pressure", 0) + eta * 0.6
        elif contact in ("none", "light"):
            self.expect["threat"] = (1 - eta) * self.expect.get("threat", 0) + eta * (-0.2)
        obj = str(hud.get("objective_bar") or "empty")
        obj_map = {"empty": -0.6, "thin": -0.2, "half": 0.2, "full": 0.7, "done": 0.95}
        if obj in obj_map:
            self.expect["objective"] = (1 - eta) * self.expect.get("objective", 0) + eta * obj_map[obj]
        # observation mildly reduces confusion if HUD consistent
        self.confusion = max(0.0, self.confusion - 0.01)
        self.coherence = min(1.0, self.coherence + 0.01)

    def apply_decoy_povm(self, strength: float = 0.15) -> None:
        """Decoy action: inject confusion / dephase belief."""
        self.confusion = _clamp01(self.confusion + strength)
        self.coherence = max(0.05, self.coherence * (1.0 - strength))
        # scramble mild
        for k in self.expect:
            self.expect[k] *= 1.0 - 0.3 * strength

    def fair_dict(self) -> dict[str, Any]:
        return {
            "expect": {k: round(v, 4) for k, v in self.expect.items()},
            "coherence": round(self.coherence, 4),
            "confusion": round(self.confusion, 4),
            "width_band": self.width_band,
            "samples": self.samples,
            # never include rho / predicates
        }

    def action_bias(self) -> dict[str, float]:
        """Translate belief → soft action preferences (for bar_brain overlay)."""
        e = self.expect
        conf = 1.0 - 0.5 * self.confusion
        return {
            "PUSH_OBJECTIVE": conf * max(0.0, 0.4 + 0.4 * e.get("aggression", 0) + 0.2 * e.get("objective", 0)),
            "FLANK": conf * max(0.0, 0.3 + 0.3 * e.get("aggression", 0) - 0.2 * e.get("caution", 0)),
            "HOLD_AND_HEAL": conf * max(0.0, 0.3 + 0.4 * e.get("caution", 0) + 0.2 * e.get("cohesion", 0)),
            "PROBE": conf * max(0.0, 0.25 + 0.2 * e.get("focus", 0) - 0.1 * e.get("pressure", 0)),
            "RALLY": conf * max(0.0, 0.2 + 0.4 * e.get("cohesion", 0)),
            "FALLBACK": conf * max(0.0, 0.15 + 0.5 * e.get("threat", 0) + 0.3 * e.get("caution", 0)),
            "EXTRACT": conf * max(0.0, 0.1 + 0.6 * e.get("objective", 0)),
        }


# ---------------------------------------------------------------------------
# 4. LaneDensity — line-war quantum membrane
# ---------------------------------------------------------------------------

@dataclass
class LaneDensity:
    """n-lane density membrane for Koom-style fights.

    ``diag[i]`` = friendly mass fraction.
    ``coh[i]`` = Re(ρ_{i,i+1}) adjacency coherence (length n-1).
    """

    n: int = 4
    diag: list[float] = field(default_factory=list)
    coh: list[float] = field(default_factory=list)
    enemy_diag: list[float] = field(default_factory=list)
    purity: float = 0.75

    def __post_init__(self) -> None:
        n = max(2, min(8, int(self.n)))
        self.n = n
        if len(self.diag) != n:
            self.diag = [1.0 / n] * n
        if len(self.enemy_diag) != n:
            self.enemy_diag = [1.0 / n] * n
        if len(self.coh) != n - 1:
            # high coherence = solid front
            self.coh = [0.2 * self.purity] * (n - 1)
        self._renorm()

    def _renorm(self) -> None:
        s = sum(max(0.02, d) for d in self.diag) or 1.0
        self.diag = [max(0.02, d) / s for d in self.diag]
        s2 = sum(max(0.02, d) for d in self.enemy_diag) or 1.0
        self.enemy_diag = [max(0.02, d) / s2 for d in self.enemy_diag]

    def mean_coherence(self) -> float:
        if not self.coh:
            return 0.0
        return sum(abs(c) for c in self.coh) / len(self.coh)

    def entropy(self) -> float:
        return von_neumann_diag(self.diag)

    def apply_order(self, order: str, lane: int | None = None) -> None:
        """Map line order → rephase / dephase / weight channels."""
        lane = 0 if lane is None else max(0, min(self.n - 1, lane))
        if order == "HOLD_LINE":
            # rephase: restore off-diagonals
            target = 0.22 * self.purity
            self.coh = [0.7 * c + 0.3 * target for c in self.coh]
            avg = sum(self.diag) / self.n
            self.diag = [0.75 * d + 0.25 * avg for d in self.diag]
            self.purity = min(1.0, self.purity + 0.03)
        elif order == "WEIGHT_LANE":
            self._shift_mass(lane, 0.12)
            self._dephase_around(lane, 0.08)
        elif order == "REINFORCE_LANE":
            self._shift_mass(lane, 0.1)
            # local rephase with neighbors
            if lane > 0:
                self.coh[lane - 1] = min(0.4, self.coh[lane - 1] + 0.04)
            if lane < self.n - 1:
                self.coh[lane] = min(0.4, self.coh[lane] + 0.04)
        elif order == "REFUSE_LANE":
            pull = self.diag[lane] * 0.4
            self.diag[lane] -= pull
            neigh = []
            if lane > 0:
                neigh.append(lane - 1)
            if lane < self.n - 1:
                neigh.append(lane + 1)
            for j in neigh:
                self.diag[j] += pull / max(1, len(neigh))
            self._dephase_around(lane, 0.15)
        elif order == "BREAKTHROUGH":
            self._shift_mass(lane, 0.2)
            # collapse coherence involving breakthrough lane (measurement)
            self._collapse_lane(lane)
            self.purity = max(0.25, self.purity - 0.08)
        elif order == "REFUSE_FLANK":
            if self.n >= 3:
                for edge in (0, self.n - 1):
                    pull = self.diag[edge] * 0.25
                    self.diag[edge] -= pull
                    mid = self.n // 2
                    self.diag[mid] += pull * 0.6
                    near = mid - 1 if edge == 0 else mid + 1
                    near = max(0, min(self.n - 1, near))
                    self.diag[near] += pull * 0.4
            self.coh = [min(0.4, c + 0.03) for c in self.coh]
        elif order == "STAGGER_ADVANCE":
            # alternate phase: odd/even dephase differently
            for i in range(len(self.coh)):
                if i % 2 == 0:
                    self.coh[i] *= 0.85
                else:
                    self.coh[i] = min(0.4, self.coh[i] + 0.02)
            self.purity = max(0.3, self.purity - 0.02)
        self._renorm()

    def _shift_mass(self, target: int, amount: float) -> None:
        donors = [i for i in range(self.n) if i != target]
        if not donors:
            return
        take = amount / len(donors)
        for i in donors:
            moved = min(take, self.diag[i] * 0.5)
            self.diag[i] -= moved
            self.diag[target] += moved

    def _dephase_around(self, lane: int, amount: float) -> None:
        if lane > 0:
            self.coh[lane - 1] *= 1.0 - amount
        if lane < self.n - 1:
            self.coh[lane] *= 1.0 - amount

    def _collapse_lane(self, lane: int) -> None:
        """Measurement on lane: zero adjacent off-diagonals."""
        if lane > 0:
            self.coh[lane - 1] *= 0.15
        if lane < self.n - 1:
            self.coh[lane] *= 0.15

    def combat_tick(
        self,
        *,
        player_strength: float,
        enemy_strength: float,
        primary: int = 0,
        fortified: bool = False,
        rng: random.Random | None = None,
    ) -> list[float]:
        """Return per-lane hold deltas; update enemy_diag slightly."""
        rng = rng or random.Random(0)
        fort = 1.15 if fortified else 1.0
        holds: list[float] = []
        for i in range(self.n):
            bias = 1.1 if i == primary else 1.0
            # coherence bonus: solid front fights better
            coh_bonus = 1.0 + 0.25 * self.mean_coherence()
            f = self.diag[i] * player_strength * coh_bonus
            e = self.enemy_diag[i] * enemy_strength * fort * bias
            ratio = f / max(0.05, f + e)
            holds.append(ratio)
            self.enemy_diag[i] = max(
                0.05,
                min(0.6, self.enemy_diag[i] + rng.uniform(-0.02, 0.02) + 0.01 * (0.5 - ratio)),
            )
        s2 = sum(self.enemy_diag) or 1.0
        self.enemy_diag = [d / s2 for d in self.enemy_diag]
        # purity drifts with variance of mass — floor 0.28 so membrane never dies
        mean_d = sum(self.diag) / self.n
        var = sum((d - mean_d) ** 2 for d in self.diag) / self.n
        self.purity = max(0.28, min(1.0, self.purity - 0.35 * var + 0.03 * self.mean_coherence()))
        return holds

    def fair_bands(self, labels: list[str] | None = None) -> dict[str, Any]:
        labels = labels or [f"Lane {i}" for i in range(self.n)]
        front = (
            "solid"
            if self.mean_coherence() > 0.18 and self.purity > 0.6
            else ("ragged" if self.mean_coherence() > 0.08 else "broken")
        )
        return {
            "front": front,
            "purity_band": "high" if self.purity > 0.7 else ("mid" if self.purity > 0.45 else "low"),
            "lanes": [
                {
                    "name": labels[i] if i < len(labels) else f"L{i}",
                    "mass_feel": (
                        "heavy" if self.diag[i] > 0.35 else ("thin" if self.diag[i] < 0.15 else "balanced")
                    ),
                }
                for i in range(self.n)
            ],
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "diag": [round(x, 4) for x in self.diag],
            "coh": [round(x, 4) for x in self.coh],
            "enemy_diag": [round(x, 4) for x in self.enemy_diag],
            "purity": round(self.purity, 4),
            "mean_coherence": round(self.mean_coherence(), 4),
            "entropy": round(self.entropy(), 4),
        }


# ---------------------------------------------------------------------------
# 5. PredicateInterference
# ---------------------------------------------------------------------------

@dataclass
class PredicateAmplitudes:
    """Win predicates as complex amplitudes; interference on joint clear score."""

    names: list[str] = field(default_factory=list)
    re: list[float] = field(default_factory=list)
    im: list[float] = field(default_factory=list)
    phases: list[float] = field(default_factory=list)

    @classmethod
    def from_scores(cls, scores: dict[str, float], predicates: list[str]) -> "PredicateAmplitudes":
        names = list(predicates) if predicates else list(scores.keys())
        re, im, phases = [], [], []
        for i, n in enumerate(names):
            amp = math.sqrt(max(0.0, min(1.0, float(scores.get(n, 0.0)))))
            # phase from index + slight score coupling
            phi = 0.4 * i + 0.3 * amp
            re.append(amp * math.cos(phi))
            im.append(amp * math.sin(phi))
            phases.append(phi)
        return cls(names=names, re=re, im=im, phases=phases)

    def classical_any(self, thr: float = 0.72) -> bool:
        for n, r, i in zip(self.names, self.re, self.im):
            if r * r + i * i >= thr * thr:  # amp^2 >= thr roughly when thr~amp
                pass
        # better: use amplitude squared
        for r, i in zip(self.re, self.im):
            if r * r + i * i >= thr:
                return True
        return False

    def interference_score(self) -> float:
        """|Σ amp_k|² / n — constructive multipath bonus when phases align."""
        if not self.re:
            return 0.0
        sr = sum(self.re)
        si = sum(self.im)
        n = len(self.re)
        # normalize by n so thrashing many weak preds doesn't auto-win
        raw = (sr * sr + si * si) / max(1, n)
        classical = sum(r * r + i * i for r, i in zip(self.re, self.im)) / max(1, n)
        # blend: interference can help or hurt vs pure classical max
        return _clamp01(0.55 * classical + 0.45 * raw)

    def thrash_penalty(self, action_switches: int) -> float:
        """Dephase when proxy switch-thrashes strategies."""
        pen = min(0.4, 0.04 * max(0, action_switches - 3))
        return max(0.0, self.interference_score() - pen)

    def as_dict(self) -> dict[str, Any]:
        probs = [round(r * r + i * i, 4) for r, i in zip(self.re, self.im)]
        return {
            "names": list(self.names),
            "probs": probs,
            "interference": round(self.interference_score(), 4),
        }


# ---------------------------------------------------------------------------
# 6. Solution entropy width
# ---------------------------------------------------------------------------

def solution_entropy_width(viable_vectors: list[str], primary: list[str] | None = None) -> float:
    """Shannon width of solution mix: primary weighted higher."""
    if not viable_vectors:
        return 0.15
    primary = primary or []
    weights = []
    for v in viable_vectors:
        weights.append(2.0 if v in primary else 1.0)
    s = sum(weights) or 1.0
    ps = [w / s for w in weights]
    h = shannon_entropy(ps)
    h_max = math.log(max(2, len(ps)))
    return _clamp01(0.12 + 0.88 * (h / h_max if h_max > 0 else 0.5))


# ---------------------------------------------------------------------------
# 7. Path hint from actions (for campaign density nudge)
# ---------------------------------------------------------------------------

def path_hint_from_actions(actions: list[str], kind: str | None = None) -> str | None:
    """Soft-classify playstyle → path A/B/C for density evolution.

    Optional ``kind`` biases classification so pure-push on eco_expand still
    can register as B when footprint grew, keeping multipath alive overnight.
    """
    if not actions:
        return None
    c = {a: actions.count(a) for a in set(actions)}
    push = c.get("PUSH_OBJECTIVE", 0) + c.get("FLANK", 0)
    expand = c.get("EXPAND_FRONT", 0)
    eco = c.get("BUILD_MEX", 0) + c.get("BUILD_ENERGY", 0) + c.get("BUILD_CON", 0) + expand
    hold = c.get("HOLD_AND_HEAL", 0) + c.get("DEFEND_BASE", 0) + c.get("RALLY", 0)
    extract = c.get("EXTRACT", 0) + c.get("FALLBACK", 0)
    kind = (kind or "").lower()
    # kind priors
    if kind in ("eco_expand",) and eco + expand >= 2:
        return "B"
    if kind in ("survive_wilds",) and hold + extract >= push:
        return "C"
    if kind in ("siege", "multipressure") and eco >= 3 and eco >= push * 0.6:
        return "B"
    if eco > push and eco >= hold:
        return "B"  # free-space / ashes-hold eco
    if extract > len(actions) * 0.12 or (hold > push + expand and hold > eco):
        return "C"  # void / exit / survival
    if push + expand >= eco:
        return "A"  # Armada-style pressure
    return "B"


def vector_diversity(actions: list[str]) -> float:
    if not actions:
        return 0.0
    counts = {}
    for a in actions:
        counts[a] = counts.get(a, 0) + 1
    tot = len(actions)
    ps = [c / tot for c in counts.values()]
    return _clamp01(shannon_entropy(ps) / math.log(max(2, len(ps))))


# ---------------------------------------------------------------------------
# Dual-manifold tick helper (for gym / fair_sim integration)
# ---------------------------------------------------------------------------

@dataclass
class DualMembraneState:
    """Paired campaign density + proxy belief — never cross-leak fields."""

    campaign: CampaignDensity = field(default_factory=CampaignDensity)
    path_ket: PathKet = field(default_factory=PathKet)
    belief: ProxyBelief = field(default_factory=ProxyBelief)
    lane: LaneDensity | None = None

    def fair_export(self) -> dict[str, Any]:
        """Only what proxy may see."""
        return {
            "belief": self.belief.fair_dict(),
            "lane_bands": self.lane.fair_bands() if self.lane else None,
            "path_coherence_band": (
                "aligned"
                if self.campaign.coherence() > 0.5
                else ("split" if self.campaign.coherence() > 0.25 else "scattered")
            ),
            # NO campaign.diag exact, NO purity number raw if too informative —
            # band only
            "campaign_phi_band": (
                "opening"
                if self.campaign.phi < 0.33
                else ("midwar" if self.campaign.phi < 0.66 else "endgame")
            ),
        }

    def operator_export(self) -> dict[str, Any]:
        """Full dual state for gym / operator room."""
        return {
            "campaign": self.campaign.as_dict(),
            "path_ket": self.path_ket.as_dict(),
            "belief": self.belief.fair_dict(),
            "lane": self.lane.as_dict() if self.lane else None,
        }


def partial_trace_proxy(campaign: CampaignDensity, mood_signed: dict[str, float] | None = None) -> ProxyBelief:
    """Build initial proxy belief as 'reduced' view of campaign (lossy)."""
    b = ProxyBelief()
    # only derived fair-ish signals from path entropy — not path labels
    w = campaign.width_from_entropy()
    b.width_band = "narrow" if w < 0.4 else ("open" if w < 0.7 else "wide")
    b.coherence = campaign.coherence() * 0.5 + 0.3
    b.confusion = 0.05 + 0.1 * (1.0 - campaign.purity)
    if mood_signed:
        for k, v in mood_signed.items():
            if k in FAIR_BELIEF_AXES:
                b.expect[k] = float(v) * 0.5
    return b
