# Graph SSOT · Drop as Collapse

**Status:** Phases **0–4 done** (v0.12.0). Soft molecule kept **live**.  
**Repo:** BAR Verdance Workspace · play via My Games `PLAY.bat` / `RESET.bat` after ship.  
**Supersedes as mainline epic:** molecule policy Stages 5–9 (combat lens stays optional / live soft).

---

## North star

**One BAR Drop / match = one observation that collapses the quantum world graph into a classical update.**

| When | Who owns truth | What it is |
|------|----------------|------------|
| Between Drops | Hub + `state/campaign_state.json` | Superposition: sparse unresolved zones, open Q-axes |
| During Drop | BAR mutator (local only) | Measurement apparatus: BeliefField / IntentResolver |
| On homecoming | `bring_home` → `process_result` | Collapse: MatchResult → ΔG (+ XP / bonds / zones) |

Design rhyme: [`BAR_verdant_ashes_campaign/quantum_graph_framework.md`](../BAR_verdant_ashes_campaign/quantum_graph_framework.md) — *battles are measurements; between battles the world is uncertain.*  
Protocol rhyme: [`CAMPAIGN_BAR_PROTOCOL.md`](CAMPAIGN_BAR_PROTOCOL.md) — Sortie → Match → `bring_home`.

```
HUB holds G (world) + H (characters)
        │ Sortie stamp
        ▼
BAR Drop  (local ρ / BeliefField — ephemeral)
        │ MatchResult v2
        ▼
bring_home → process_result → M(G, result) → G′
        │
        ▼
Hub debrief shows which axes moved
```

---

## Source of truth law

| Layer | Artifact | Writers | Readers |
|-------|----------|---------|---------|
| **World graph G** | `state/campaign_state.json` → `graph` (+ `zoneMemory`) | **`process_result` only** (via `bring_home`) | Hub, stamp, briefs |
| **Character graph H** | `data/story/hero_umwelt.json`, `support_web.json`, live bonds/XP in campaign_state | Authored data + homecoming deltas | Hub talks, FE, deploy hints |
| **Measurement** | `inbox/latest_va_result.json` (MatchResult v2) | BAR gadget → extract | `process_result` only |
| **Combat local** | BeliefField / IntentResolver (+ optional molecule soft) | BAR tick | BAR tick — **not** world SSOT |
| **Derived faces** | `outbox/*` | Projectors | Eyes / bots — **never** write G |

**Hard rules**

1. No outbox face is world truth.
2. Molecules / doctrine / residual hose do not mutate `graph` except through `process_result`.
3. In-Drop Lua may keep a **scratch** quantum snapshot; if `persist_exported` succeeds (`quantum_authoritative`), Python skips its own graph deltas and trusts the exported fold. Hub remains campaign file authority after save.
4. Dark banner > fake-live.

---

## Live collapse operators (already in code)

These **are** `M(G, result)` today — thin, not the full fractal dictionary.

| Function | File | Role |
|----------|------|------|
| `apply_graph_deltas` | `tools/verdance_story_engine_v1.py` | Verdict / path → additive Δ on contested, independent, void, pathSignal* |
| `measure_graph_from_world` | same | Low-pass ease (`GRAPH_MEASURE_EASE = 0.25`) of axes toward masses / spectral / Tnb scarcity |
| `persist_exported` | `tools/quantum_campaign_state_v1.py` | Optional Lua-authoritative fold; when true, skips Python Δ |

Called from `process_result` after credit normalize. Saved to `state/campaign_state.json`.

### Current G axes (live keys)

| Key | Role |
|-----|------|
| `q0_armada_cortex` | Faction polarity (measured from zone masses / spectral) |
| `q2_void_structure` | Hazard / spread pressure |
| `q6_contested` | Flux / contested |
| `q6_independent` | Clan / Ashwalker sovereignty floor |
| `q7_resource_scarcity` | Eco + Tnb scarcity |
| `pathSignalA` / `B` / `C` | Path mixture (reinforced by mission path + verdict) |

Full Q dictionary in the quantum framework doc remains **design aspiration** — grow only what Drop can measure.

### Character graph H

- Molecules: `data/story/hero_umwelt.json` (temperament; combat coloring only)
- Edges: `data/story/support_web.json`
- Live: `campaign_state.characters[*].xp|bonds|wounds` via homecoming

---

## Phase 1 inventory — who writes campaign state / graph

| Writer | Mutates `graph`? | Mutates campaign_state? | Class |
|--------|------------------|-------------------------|-------|
| `verdance_story_engine_v1.process_result` | **Yes** (Δ + measure, unless quantum_authoritative) | **Yes** (canonical) | **KEEP — sole ingest** |
| `CampaignKernel.bring_home` | via process_result | via apply_result_to_hub | **KEEP — sole player entry** |
| `quantum_campaign_state_v1.persist_exported` | Yes (pathSignals + fold) when authoritative | Yes | **KEEP — optional Lua fold** |
| `build_hub_state_v1` | defaults / ensure keys | may write state | **KEEP — ensure/defaults; audit** |
| `capture_node_claims` | No (zones/claims) | Yes (CLI) | **KEEP — capture path; must stay credit-aligned** |
| `continuity_store_v1` | No | Yes (CLI restore) | **OPS — not live Drop** |
| `migrate_zone_ids_v1` | No | Yes (migration) | **OPS — one-shot** |
| `stamp_deploy_plan_v1` | No | **No** (reads only) | **KEEP — outbound** |
| `campaign_flow_matrix_v1` | No | **No** (reads only) | DERIVE |
| Molecule / phi / shadow tools | No | No | Combat lens / DERIVE |
| Hive residual / proxy / overnight | No (own faces) | Should not | **BOT-ONLY** |

**Gap to close in Phase 2:** hub debrief should surface **which G axes moved** (`graph_delta` + `graph_measured`) so collapse is visible, not vibes-only.

---

## Outbox face classes (Luke eyes vs bots)

### KEEP — player / homecoming

| Face | Role |
|------|------|
| `hub_result.latest.json` | Debrief after bring_home |
| `hub_deploy_plan.latest.json` / `hub_deploy_stamp.latest.json` | Outbound sortie |
| `next_sortie_order.json` | Seed for Drop |
| `bridge.latest.json` | Play session bridge |
| `play_session.status.json` | Session health |
| `result_harvest_fail.latest.json` | Honest failure |
| `war_map.json` | Hub map projection |
| `campaign_surface.latest.json` | Hub surface |
| `advance_report.v1.json` | process_result report |
| `story_events.latest.json` | Story events from advance |
| Human playthrough faces | Luke seal tape |

### DERIVE — useful projectors (not SSOT)

| Face | Role |
|------|------|
| `hero_observe.latest.json` / tape | Combat observe |
| `hero_graph_analysis.json` | Cast geometry glance |
| `molecule_doctrine_shadow.json` / `shadow_intent*` / `phi_shadow*` | Combat lens shadows |
| `campaign_flow.latest.*` | Flow matrix |
| `escalation_map.latest.md` | Escalation read |
| `zone_scorecard.latest.*` | Zone scores |
| `next_mission_intent.json` | Next intent projection |

### BOT-ONLY — demote from player HOME

| Face | Role |
|------|------|
| `proxy_campaign.latest.json` | AI proxy farm |
| `hive_bar_residual.latest.json` / `hive_gym_arena.latest.json` | Residual hose |
| `overnight_hive_bar.latest.json` / `training_pathway_morning.json` | Overnight |
| `campaign_fruit.latest.json` | Swarm ideas |
| `bar_swarm_*` / `battle_farm_*` / `manifold_gym.*` | Bot muscle |
| `quantum_bar_ai_*.latest.json` | Quantum-BAR AI suite |
| `continuity_audit_*.json` | Audit dumps |
| Dual-gym / cognifold vitals (hive) | Post-G0 wishlist faces |

### INTERSTITIAL NOISE (mental model)

- Soft molecule policy as a “second world brain” — treat as **combat coloring**; flag rollback `va_molecule_policy=off`
- Molecule Stages 5–9 epic — **frozen** until Drop→collapse is legible on hub
- Full cognifold / SpaceWheat live membrane — not Verdance SSOT

---

## Phases (execution)

| Phase | Goal | Status |
|------:|------|--------|
| 0 | This doc + HOME eye-demotion + cross-links | **done** |
| 1 | Writer inventory + outbox classes (above) | **done** |
| 2 | Expose `M` on hub debrief (collapse chips + payload) | **done** — `tools/graph_collapse_v1.py`; wired in `process_result` → debrief → `hub_result` |
| 3 | Hub reads G for briefings; sortie stamp carries full `graphSnapshot` | **done** — `graphPressure` on hub + stamp; BAR still writes MatchResult only |
| 4 | Character H under same homecoming law | **done** — see § Character collapse (H) below |
| 5 | Soft molecule prune | **kept live** (player choice) — soft default stays on; bot faces stay demoted in HOME |

### Character collapse (H)

Same homecoming path as G. `process_result` updates XP / wounds / bonds / joins; debrief tokens already list XP and wounds. Joins emit `H: … joined` chips. Support-web cultivation stays offline (`support_web_v1`); no live densify. Molecules remain combat temperament only.

### Soft molecule (Phase 5 decision)

`va_molecule_policy` default remains **soft** for this build (live combat coloring). Rollback still `off`. Not world SSOT.

---

## Explicit non-goals

- Replacing BeliefField with graph argmax
- Shipping full fractal Q dictionary in one pass
- Live cognifold as Verdance SSOT
- Deleting bot tooling (demote from eyes only)
- Molecule Stages 5–9 as mainline

---

## Success check

- Point at `state/campaign_state.json` → `graph` and say: **that is the world between fights.**
- After PLAY → Drop → home: hub shows **axes that moved**.
- Support web answers **who these people are**, not who owns the zone.
- HOME no longer trains your eyes on bot farm faces.
