# Outbound Briefing 05: Density Matrix & Zone Telemetry

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Implementation:** `measure_graph_from_world()` in [`tools/verdance_story_engine_v1.py`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/tools/verdance_story_engine_v1.py)

---

## 1. What is the Density Matrix?

The **Density Matrix** is a mathematical formulation that bridges real-time tactical BAR match events with abstract macro campaign graph scalars (`q0`, `q2`, `q6`, `q7`).

Rather than scripting arbitrary campaign progress, the engine constructs a **Hermitian Battlefield Matrix** \(H\) of dimension \((N+1) \times (N+1)\), where \(N\) is the number of authored map zones:

- **Diagonal Elements \(H_{ii}\):** Zone Feature Density (Metal extractors, solar/wind generators, defense turret counts, unit build mass in zone \(i\)).
- **Off-Diagonal Elements \(H_{ij}\):** Entanglement Couplings (combat pressure, unit transfers, and line-of-fire intensity crossing the boundary between zone \(i\) and zone \(j\)).
- **Hydrology & Anchor Element \(H_{N+1, N+1}\):** Environmental terrain factor (water presence, wind volatility).

---

## 2. Spectral Eigensolver (`jacobi_eigen`)

When a match ends, the extracted translation packet (`inbox/latest_va_translation.json`) is processed by a pure-Python Jacobi eigensolver embedded in `verdance_story_engine_v1.py`:

```python
# Pure stdlib Jacobi eigenvalue decomposition
evals, evecs = jacobi_eigen(hermitian_matrix)
```

### Derived Spectral Observables:
1. **Dominant Eigenvalue (\(\lambda_{\max}\)):** Total concentrated energy/mass of the primary battle theater.
2. **Participation Ratio (\(P\)):** Measures entanglement breadth across zones:
   \[
   P = \frac{1}{\sum_{k} v_k^4}
   \]
   High participation indicates a multi-lane, widespread war; low participation indicates a localized choke-point duel.
3. **Spectral Spread (\(\Delta \lambda\)):** Variance across eigenvalues representing frontier disorder.
4. **Dominant Faction Weight:** Faction distribution (Armada vs Cortex vs Ashwalkers) within the principal eigenvector mode.

---

## 3. Spectral-to-Graph Mapping

The spectral observables directly ease the graph scalars using a low-pass filter (\(\text{EASE} = 0.25\)):

- **`q0_armada_cortex` \(\leftarrow\)** Measured Cortex-vs-Armada mass ratio in the principal eigenvector mode. Beating Cortex structures directly shrinks Cortex spectral weight, decaying `q0` toward Armada stability.
- **`q2_void_structure` \(\leftarrow\)** Derived directly from Spectral Spread (\(\Delta \lambda\)) and hazard zone density. High spatial disorder increases `q2`.
- **`q7_resource_scarcity` \(\leftarrow\)** Derived from \(1.0 - \text{mean(EconomyMomentum)}\). Heavy building loss and eco destruction increase scarcity.
- **`q6_independent` \(\leftarrow\)** Floored by surviving Ashwalker cadre unit count (warband power projection).

---

## 4. Authored Map Zones vs. Generic Grids

Each map in the canonical pool uses an authored zone map in [`data/zone_maps/authored/*.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/).

### Sample Zone Breakdown: Eye of Horus (`eye_of_horus`)
1. `EOH_NW_CRATER_CAMP` (Northwest Rim - Default Player Deployment Zone)
2. `EOH_WESTERN_DEBRIS_LANE` (Western Choke & Extraction Lane)
3. `EOH_CENTRAL_CRATER_BASIN` (High-metal central impact crater)
4. `EOH_SE_CORTEX_POCKET` (Southeast fortified valley - Objective Relay Zone)
5. `EOH_EASTERN_FLANK` (Eastern ridge - Null Merc Foothold)

Authored zones ensure that telemetry speaks in human narrative terms (e.g. "Cortex dealer relay in Southeast Pocket destroyed") rather than arbitrary grid coordinates.
