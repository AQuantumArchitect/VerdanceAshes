"""UniversalLearner pilot on bar_brain action families.

One-law learning over ScalarParams:
  - width_action: (width_band, action)  — front geometry
  - eco_action:   (eco_feel, action)    — economy feel (v0.8.6+)
  - accrue while chosen on the fair tape
  - reinforce at mission end with signed surprise from fair outcome only
  - project param values back into BarBrainWeights tables for overlay

Fair-room only: surprise uses won / progress / heroes — never SimTruth tables.
BAR densify is not involved (n_obs wall stays honest elsewhere).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .bar_brain import (
    BarBrainWeights,
    _width_band_from_card,
    load_weights,
    save_weights,
    weights_path,
)
from .policy import ACTIONS
from .suite import _workspace_root

# Primary family name stays width_action for residual faces; eco is additive.
UL_FAMILY = "width_action+eco_action"
UL_FAMILY_LEGACY = "width_action"
WIDTH_BANDS = ("narrow", "open", "wide")
ECO_BANDS = ("dry", "thin", "steady", "fat")
DEFAULT_UL_STATE_PATH = Path("app") / "brain" / "bar_brain_ul_state.json"

# Soft clamps so UL cannot explode preferences overnight
PARAM_LO = 0.05
PARAM_HI = 12.0
DEFAULT_SIGMA = 1.5


def _ensure_umwelt_params():
    try:
        from umwelt.substrate.params import ScalarParam
        from umwelt.learning.universal_learner import UniversalLearner

        return ScalarParam, UniversalLearner
    except ImportError as e:
        raise ImportError(
            "bar_brain_ul requires umwelt on PYTHONPATH (ws-win\\umwelt\\src)"
        ) from e


def ul_state_path(workspace: Path | None = None) -> Path:
    ws = workspace or _workspace_root()
    return ws / DEFAULT_UL_STATE_PATH


def _param_key(band: str, action: str) -> str:
    return f"{band}|{action}"


def _seed_value_width(weights: BarBrainWeights, band: str, action: str) -> float:
    table = weights.width_action.get(band) or {}
    v = float(table.get(action, 0.0))
    if v <= 0:
        # mild global prior so every cell is learnable
        v = float(weights.action_counts.get(action, 0.1)) * 0.15 + 0.2
    return max(PARAM_LO, min(PARAM_HI, v))


def _seed_value_eco(weights: BarBrainWeights, eco: str, action: str) -> float:
    table = weights.eco_action.get(eco) or {}
    v = float(table.get(action, 0.0))
    if v <= 0:
        v = float(weights.action_counts.get(action, 0.1)) * 0.12 + 0.2
    return max(PARAM_LO, min(PARAM_HI, v))


# backward-compat alias
def _seed_value(weights: BarBrainWeights, band: str, action: str) -> float:
    if band in ECO_BANDS:
        return _seed_value_eco(weights, band, action)
    return _seed_value_width(weights, band, action)


@dataclass
class WidthActionUL:
    """Pilot learner: eligibility-trace UL over width_action + eco_action cells."""

    family: str = UL_FAMILY
    params: dict[str, Any] = field(default_factory=dict)
    total_accruals: int = 0
    total_reinforces: int = 0
    missions: int = 0
    updated_at: str = ""
    _learner: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        ScalarParam, UniversalLearner = _ensure_umwelt_params()
        if self._learner is None:
            self._learner = UniversalLearner(lam=0.9, lr=0.35, obs_sigma=0.2)

    @classmethod
    def from_weights(cls, weights: BarBrainWeights | None = None) -> "WidthActionUL":
        ScalarParam, _ = _ensure_umwelt_params()
        w = weights or load_weights()
        params: dict[str, Any] = {}
        for band in WIDTH_BANDS:
            for action in ACTIONS:
                key = _param_key(band, action)
                val = _seed_value_width(w, band, action)
                params[key] = ScalarParam(
                    name=key,
                    value=val,
                    sigma=DEFAULT_SIGMA,
                    lo=PARAM_LO,
                    hi=PARAM_HI,
                )
        for eco in ECO_BANDS:
            for action in ACTIONS:
                key = _param_key(eco, action)
                val = _seed_value_eco(w, eco, action)
                params[key] = ScalarParam(
                    name=key,
                    value=val,
                    sigma=DEFAULT_SIGMA,
                    lo=PARAM_LO,
                    hi=PARAM_HI,
                )
        return cls(params=params)

    @classmethod
    def from_dict(cls, d: dict[str, Any], weights: BarBrainWeights | None = None) -> "WidthActionUL":
        ScalarParam, _ = _ensure_umwelt_params()
        base = cls.from_weights(weights)
        for key, row in (d.get("params") or {}).items():
            if key not in base.params:
                continue
            p = base.params[key]
            p.value = float(row.get("value", p.value))
            p.sigma = float(row.get("sigma", p.sigma))
            p.update_count = int(row.get("update_count", 0))
            if p.lo is not None:
                p.value = max(p.lo, p.value)
            if p.hi is not None:
                p.value = min(p.hi, p.value)
        base.total_accruals = int(d.get("total_accruals") or 0)
        base.total_reinforces = int(d.get("total_reinforces") or 0)
        base.missions = int(d.get("missions") or 0)
        base.updated_at = str(d.get("updated_at") or "")
        return base

    def as_dict(self) -> dict[str, Any]:
        params_out: dict[str, Any] = {}
        for key, p in self.params.items():
            params_out[key] = {
                "value": round(float(p.value), 6),
                "sigma": round(float(p.sigma), 6),
                "update_count": int(p.update_count),
            }
        n_width = sum(1 for k in params_out if k.split("|", 1)[0] in WIDTH_BANDS)
        n_eco = sum(1 for k in params_out if k.split("|", 1)[0] in ECO_BANDS)
        return {
            "schema": "bar-brain-ul/1.1",
            "family": self.family if self.family else UL_FAMILY,
            "families": ["width_action", "eco_action"],
            "total_accruals": self.total_accruals,
            "total_reinforces": self.total_reinforces,
            "missions": self.missions,
            "updated_at": self.updated_at,
            "params": params_out,
            "nWidthParams": n_width,
            "nEcoParams": n_eco,
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        sigmas = [float(p.sigma) for p in self.params.values()]
        updates = [int(p.update_count) for p in self.params.values()]
        width_updates = sum(
            int(p.update_count)
            for k, p in self.params.items()
            if k.split("|", 1)[0] in WIDTH_BANDS
        )
        eco_updates = sum(
            int(p.update_count)
            for k, p in self.params.items()
            if k.split("|", 1)[0] in ECO_BANDS
        )
        return {
            "ulFamily": self.family or UL_FAMILY,
            "ulUpdateCount": int(sum(updates)),
            "ulMeanSigma": round(sum(sigmas) / max(1, len(sigmas)), 4),
            "ulMissions": self.missions,
            "ulTotalAccruals": self.total_accruals,
            "ulTotalReinforces": self.total_reinforces,
            "nParams": len(self.params),
            "ulWidthUpdates": int(width_updates),
            "ulEcoUpdates": int(eco_updates),
        }

    def accrue_tape_row(
        self,
        row: dict[str, Any],
        width_band: str,
        *,
        eco_feel: str | None = None,
    ) -> None:
        action = row.get("action") or "WAIT"
        if action not in ACTIONS:
            return
        # width family
        if width_band in WIDTH_BANDS:
            key = _param_key(width_band, action)
            p = self.params.get(key)
            if p is not None:
                self._learner.accrue(p, 1.0)
                self.total_accruals += 1
        # eco family (fair HUD eco_feel only)
        eco = eco_feel
        if eco is None:
            eco = (row.get("hud") or {}).get("eco_feel")
        if eco in ECO_BANDS:
            key = _param_key(str(eco), action)
            p = self.params.get(key)
            if p is not None:
                self._learner.accrue(p, 1.0)
                self.total_accruals += 1

    def surprise_from_result(self, *, won: bool, progress: float, heroes: float = 1.0) -> float:
        """Signed residual: positive = worse than hoped (push preferences down via reinforce).

        UniversalLearner.reinforce: target = value - lr * surprise * e_hat
        So positive surprise lowers the param (discourage); negative raises (encourage).
        """
        prog = max(0.0, min(1.0, float(progress)))
        # expected progress band ~0.7 for a fair clear; miss is positive surprise
        progress_miss = 0.7 - prog
        if won:
            # reward: negative surprise scaled by how clean
            clean = 0.5 * prog + 0.5 * max(0.0, min(1.0, heroes))
            return -0.35 * (0.4 + clean)  # about -0.14 .. -0.35
        # loss / fail
        return 0.45 + 0.4 * max(0.0, progress_miss)  # about 0.45 .. 0.85

    def reinforce_mission(self, surprise: float) -> dict[str, float]:
        """Consume eligibility traces for all params that accrued this mission."""
        touched: dict[str, float] = {}
        for key, p in self.params.items():
            if self._learner.eligibility(p) == 0.0:
                continue
            before = float(p.value)
            self._learner.reinforce(p, surprise)
            touched[key] = float(p.value) - before
            self.total_reinforces += 1
        self.missions += 1
        return touched

    def learn_from_result(
        self,
        result: dict[str, Any],
        *,
        default_width: str = "open",
    ) -> dict[str, Any]:
        """Learn from one fair-campaign result (player_card + tape + won)."""
        won = bool(result.get("won"))
        card = result.get("player_card") or {}
        width_band = _width_band_from_card(card)
        if width_band not in WIDTH_BANDS:
            width_band = default_width if default_width in WIDTH_BANDS else "open"

        tape = result.get("tape") or []
        for row in tape:
            # per-row width if tape carries it; else mission card band
            wb = width_band
            hud = row.get("hud") or {}
            if hud.get("width_band") in WIDTH_BANDS:
                wb = str(hud.get("width_band"))
            elif (row.get("_truth") or {}).get("width_band") in WIDTH_BANDS:
                # operator tape may carry width for training; agent never saw this live
                # but width_band on card is fair; _truth width is craft geometry (ok for credit)
                wb = str((row.get("_truth") or {}).get("width_band"))
            eco = hud.get("eco_feel")
            if eco not in ECO_BANDS:
                # soft map from numeric eco if present
                eco_num = (row.get("_truth") or {}).get("eco")
                if isinstance(eco_num, (int, float)):
                    e = float(eco_num)
                    if e < 0.25:
                        eco = "dry"
                    elif e < 0.45:
                        eco = "thin"
                    elif e < 0.7:
                        eco = "steady"
                    else:
                        eco = "fat"
                else:
                    eco = None
            self.accrue_tape_row(row, wb, eco_feel=eco if eco in ECO_BANDS else None)

        progress = 0.0
        heroes = 1.0
        if tape:
            last = tape[-1]
            truth = last.get("_truth") or {}
            progress = float(truth.get("progress") or result.get("progress") or (1.0 if won else 0.3))
            heroes = float(
                truth.get("heroes_alive_frac")
                or result.get("heroes_alive_frac")
                or 1.0
            )
        else:
            progress = float(result.get("progress") or (0.9 if won else 0.25))
            heroes = float(result.get("heroes_alive_frac") or (0.8 if won else 0.3))

        surprise = self.surprise_from_result(won=won, progress=progress, heroes=heroes)
        deltas = self.reinforce_mission(surprise)
        return {
            "won": won,
            "width_band": width_band,
            "surprise": round(surprise, 4),
            "progress": round(progress, 4),
            "nTouched": len(deltas),
            "deltas": {k: round(v, 4) for k, v in list(deltas.items())[:12]},
        }

    def learn_from_report(self, report: dict[str, Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for res in report.get("results") or []:
            out.append(self.learn_from_result(res))
        return out

    def project_to_weights(self, weights: BarBrainWeights) -> BarBrainWeights:
        """Write learned param values into width_action + eco_action tables."""
        for band in WIDTH_BANDS:
            table = weights.width_action.setdefault(band, {})
            for action in ACTIONS:
                key = _param_key(band, action)
                p = self.params.get(key)
                if p is None:
                    continue
                table[action] = round(float(p.value), 4)
        for eco in ECO_BANDS:
            table = weights.eco_action.setdefault(eco, {})
            for action in ACTIONS:
                key = _param_key(eco, action)
                p = self.params.get(key)
                if p is None:
                    continue
                table[action] = round(float(p.value), 4)
        return weights

    def apply_doctrine_prior(self, posture: str, *, boost: float = 0.35) -> dict[str, float]:
        """Soft one-shot hive RTS doctrine prior. Never commands the fair agent."""
        posture = (posture or "rest").lower().strip()
        bumps: dict[str, float] = {}
        if posture in ("farm_patrol", "patrol", "farm"):
            targets = [
                ("narrow", "PROBE"),
                ("narrow", "HOLD_AND_HEAL"),
                ("narrow", "BUILD_ENERGY"),
                ("open", "BUILD_MEX"),
            ]
        elif posture in ("support_push", "push", "support"):
            targets = [
                ("open", "PUSH_OBJECTIVE"),
                ("open", "FLANK"),
                ("wide", "EXPAND_FRONT"),
                ("wide", "PUSH_OBJECTIVE"),
            ]
        else:
            # rest / dam-pressure: mild diversity, no thrash
            targets = [
                ("open", "HOLD_AND_HEAL"),
                ("open", "RALLY"),
                ("narrow", "WAIT"),
            ]
        cap = min(0.6, max(0.05, float(boost)))
        for band, action in targets:
            key = _param_key(band, action)
            p = self.params.get(key)
            if p is None:
                continue
            before = float(p.value)
            p.value = min(PARAM_HI, before + cap)
            bumps[key] = float(p.value) - before
        return bumps


def load_ul_state(
    path: Path | None = None,
    *,
    weights: BarBrainWeights | None = None,
    workspace: Path | None = None,
) -> WidthActionUL:
    p = path or ul_state_path(workspace)
    w = weights or load_weights(weights_path(workspace) if workspace else None)
    if not p.is_file():
        return WidthActionUL.from_weights(w)
    try:
        return WidthActionUL.from_dict(json.loads(p.read_text(encoding="utf-8")), w)
    except Exception:
        return WidthActionUL.from_weights(w)


def save_ul_state(ul: WidthActionUL, path: Path | None = None, workspace: Path | None = None) -> Path:
    p = path or ul_state_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    ul.updated_at = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(ul.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def train_report_with_ul(
    report: dict[str, Any],
    *,
    workspace: Path | None = None,
    save: bool = True,
    doctrine_posture: str | None = None,
) -> dict[str, Any]:
    """Histogram ingest + UL pilot on width+eco action families; optional doctrine prior."""
    from .bar_brain import ingest_campaign_report

    ws = workspace or _workspace_root()
    w = load_weights(weights_path(ws))
    w = ingest_campaign_report(report, w)
    ul = load_ul_state(workspace=ws, weights=w)
    # migrate legacy family label on next save
    if ul.family in (None, "", UL_FAMILY_LEGACY):
        ul.family = UL_FAMILY
    if doctrine_posture:
        ul.apply_doctrine_prior(doctrine_posture)
    mission_logs = ul.learn_from_report(report)
    w = ul.project_to_weights(w)
    if save:
        save_weights(w, weights_path(ws))
        save_ul_state(ul, workspace=ws)
    return {
        "histogramSamples": w.samples,
        "wins": w.wins,
        "losses": w.losses,
        "ul": ul.summary(),
        "missionLogs": mission_logs,
        "doctrinePosture": doctrine_posture,
    }


def fair_results_to_report(fair_dicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build bar_brain ingest report from FairMissionResult.as_dict() list."""
    results = []
    for d in fair_dicts:
        results.append(
            {
                "won": bool(d.get("won") or d.get("verdict") in ("extracted", "objective_complete")),
                "player_card": d.get("player_card") or {},
                "tape": d.get("tape") or [],
                "progress": d.get("progress"),
                "heroes_alive_frac": d.get("heroes_alive_frac"),
                "verdict": d.get("verdict"),
                "mission_id": d.get("mission_id"),
            }
        )
    return {"results": results, "source": "proxy_fair_tapes"}


def read_hive_doctrine_posture(workspace: Path | None = None) -> str | None:
    """Best-effort soft prior from hive RTS vitals (missing = None)."""
    candidates = [
        Path(r"C:\Users\Luke Spooner\ws-win\yurt-sync\commons\vitals\hive_rts_state.json"),
        Path.home() / "ws-win" / "yurt-sync" / "commons" / "vitals" / "hive_rts_state.json",
    ]
    if workspace:
        candidates.append(workspace.parent.parent / "ws-win" / "yurt-sync" / "commons" / "vitals" / "hive_rts_state.json")
    for p in candidates:
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        # tolerate several shapes
        posture = (
            data.get("posture")
            or data.get("missionPosture")
            or (data.get("mission") or {}).get("posture")
            or data.get("mode")
            or data.get("lastBeat")
        )
        if isinstance(posture, str) and posture.strip():
            return posture.strip().lower()
        # XP caste levels as weak signal
        castes = data.get("castes") or data.get("casteXp") or {}
        if isinstance(castes, dict) and castes:
            # if revenue/butler elevated → support_push else farm
            try:
                rev = float((castes.get("revenue") or castes.get("revenue_ant") or {}).get("level") or 0)
                but = float((castes.get("butler") or castes.get("butler_ant") or {}).get("level") or 0)
                if rev >= 2 or but >= 2:
                    return "support_push"
            except Exception:
                pass
            return "farm_patrol"
    return None
