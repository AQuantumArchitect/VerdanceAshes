# 29 — Dual Umwelt Manifolds + Lane AI (Koom line war)

**Date:** 2026-07-26  
**Status:** Phase A–B shipped offline (fair_sim + DomainSpecs + tests)

## What landed

### Two manifolds

| Manifold | DomainSpec | Code |
|----------|------------|------|
| **Proxy-player** (belief) | `verdance-player-proxy` | `proxy_manifold.py` + `world.py` |
| **Campaign-shape** (ρ / density membrane) | `verdance-campaign-shape` | `campaign_manifold.py` |
| **Lane war** (line membrane) | `verdance-lane-war` | `lane_war.py` + `lane_world.py` |

Yurt pointers:

- `ws-win/yurt/worlds/verdance_proxy/world.py` (promoted)
- `ws-win/yurt/worlds/verdance_campaign/world.py` (new)

### Campaign as density membrane

- Phase-1 ρ = **expectation vector** on Q0–Q7-style axes + path_space width  
- **Width curve:** early missions ~0.15–0.35 (clear action vectors); late ~0.70–0.95 (multipath)  
- `MissionSolutionSpace`: primary/viable vectors, win_predicates (any-of), decoys  
- `fair_sim` can clear on **any** declared predicate (diverging solutions)  
- Early `eco_raid` pure-build **does not** clear (vector stays clear)

### Lane AI (line war)

- Koom Valley interior: **3–5 columns** (default 4; width scales count)  
- All That Simmers / Tabula ramps also get geometry when seize/hold  
- Line orders: `HOLD_LINE`, `WEIGHT_LANE`, `REFUSE_LANE`, `REINFORCE_LANE`, `BREAKTHROUGH`, `REFUSE_FLANK`, `STAGGER_ADVANCE`  
- Fair bands only to proxy (`front` / per-lane feel) — no exact enemy mass

## Commands

```powershell
$ws = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
$env:PYTHONPATH = "$ws\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"

& $py -m unittest quantum_bar_ai.test_manifolds_lane -v
& $py -m unittest quantum_bar_ai.test_smoke -v

# Inspect
& $py -c "from quantum_bar_ai.campaign import build_full_campaign; m=build_full_campaign(); print([(x.id, round(x.solution_space.width,2), getattr(x.lane_geometry,'lane_count',None)) for x in m])"
```

## Fair rule (unchanged)

Proxy never reads full campaign ρ or lane referee ground truth.  
Luke/Dave human dams still never auto-cleared.

## Next (when you can play)

1. Retrain `bar_brain` with `width_band` + `lane_band` context keys  
2. Lua zone strips on Koom interior for real unit columns  
3. Optional umweltd register of both yurt worlds on :7073  
4. Mirror width curve into semantica-yurt sy_* cards if wanted  

## Acceptance

- [x] Two DomainSpecs loadable (proxy + campaign)  
- [x] Early narrow / late wide solution spaces  
- [x] Koom 3–5 lane geometry + line orders  
- [x] fair_sim multi-predicate + multi-lane  
- [x] Unit tests in `test_manifolds_lane.py`  
- [ ] In-BAR Lua lane strips (Phase D)  
- [ ] Live umweltd registration  
