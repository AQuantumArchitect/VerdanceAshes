# Outbound 44 — Kernel locks: world graph + occupation + no UI seat

**Date:** 2026-07-28  
**Status:** SHIPPED (kernel wiring)  
**Seat:** game/kernel (player rig / hub UI = other bot)

## Operator review incorporated

| Comment | Resolution |
|---------|------------|
| Occupation “one model” — unsure if correct | **Locked:** living shell + decoy plant + scars. Hand camps = deprecated fallback only. |
| “only 1 map” | Means **one occupation model** and **same-map session chains** (Mode A), **not** deleting the seven-map pool. |
| yay world zone graph | Graph is authoritative; validators + story engine load it first. |
| don’t worry about UI | No hub/shop/Deploy work this seat. |

## World zone graph (kernel)

| Piece | Path |
|-------|------|
| Atlas | `data/zone_maps/world_zone_graph.v1.json` (45 nodes, 83 edges) |
| Loader | `tools/world_zone_graph.py` |
| Validate structure | `tools/validate_world_zone_graph.py` |
| Sortie legality | `tools/validate_sortie_contract.py` → `wzg.load_full_adjacency(..., kinds=("same_map",))` |
| Story extract / walks | `verdance_story_engine_v1._load_map_adjacency` → same helper |
| Tests | `tests/test_world_zone_graph.py` |

**Rule:** same_map edges = legal in-session contracts / promote / extract neighbors.  
**strategic_link** edges = Mode B later; ignored by same-session walks.

```powershell
python tools\world_zone_graph.py --workspace .
python tools\world_zone_graph.py --workspace . --map koom_valley
python -m unittest tests.test_world_zone_graph tests.test_sortie_contract -v
```

## Occupation model (one)

```
OFFLINE: bake → strip → decoy plant → template JSON
MATCH:   spawn living shell → primary pocket objective → promote / scar
WRATH:   ephemeral only (never scarred)
```

Compiler already prefers shell for shell-capable kinds (`build_next_mission_v1.ps1`).  
Hand eco sprawl runs only when `Try-ApplyLivingShell` fails (missing template).

## Session model (kernel)

- **Mode A (focus):** same map, promote pockets / next same-map contract via graph neighbors.  
- **Mode B:** map travel via strategic_link — deferred.  
- **Seven-map pool remains** for campaign spine and offline craft.

## Explicit non-goals (this seat)

- Hub HTML, shop panel, Deploy button, RmlUi, Electron  
- Pretty zone border drawing (rig may consume progress *values* later)

## Sortie / Result contract direction (next kernel rock)

Still multi-schema today (`mission-intent`, `sortie-order`, seed tables, match result markers).  
Next doc pass: map fields → `sortie_contract.v2` + `va_result.v2` without UI.

## Related

- WO-020 plan: `outbound/14_ZONE_GRAPH_AND_QUEST_ENGINE_PLAN.md`  
- Shells: `outbound/37_LIVING_SHELL_TEMPLATES.md`  
- Tnb: `outbound/43_COMMERCE_TENEBRIUM_AND_MERC_PACKS.md`
