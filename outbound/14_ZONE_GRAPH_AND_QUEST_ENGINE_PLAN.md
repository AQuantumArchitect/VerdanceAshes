# WO-020 Plan — Zone ↔ Map Graph & Quest Generation

**Author:** Head Hancho  
**Date:** 2026-07-25  
**Status:** PLANNED (major work; not started implementation)  
**Driver:** Operator request — map all zones to maps, graph them, generate quests from the graph.

---

## 1. What already exists

| Asset | Location | State |
|---|---|---|
| 7-map pool | `data/map_pool/seven_maps.json` | Canonical |
| Authored zone maps (per map) | `data/zone_maps/authored/*.authored.zone_map.json` | **45 zones** total (6–7 per map) |
| **Within-map** adjacency | `data/zone_maps/authored/zone_adjacency.json` | Done (map → zone → neighbors[]) |
| Campaign zone control | `state/campaign_state.json` territory / zone flip | Partial (WO-007 flip works) |
| Sortie contracts | `VA-SORTIE/1` / `next_sortie_order.json` | Legal contracts on **one** zone |
| War map export | `outbox/war_map.json` | Snapshot-ish; not the quest brain |

**Gap:** there is no single **world graph** that:

1. Lists every zone with full metadata (mapId, bounds, roles, owner, front),  
2. Connects zones **across maps** (strategic edges),  
3. Lets the story engine walk the graph to **propose contracts / quest chains**.

Today contracts are hand-authored or lightly scripted (e.g. Koom seize_lane). The engine cannot yet say: “player holds A, adjacent contested B on same map, portal to map X zone Y — offer raid on B then push Y.”

---

## 2. Target architecture

```
┌─────────────────────────────────────────────────────────────┐
│  world_zone_graph.v1.json  (authoritative campaign atlas)   │
│  nodes: zoneId → { mapId, label, roles[], bounds, tags[] }  │
│  edges: { from, to, kind, cost, notes }                     │
│    kind ∈ same_map | strategic_link | sea_lane | story_gate │
└───────────────────────────┬─────────────────────────────────┘
                            │
            ┌───────────────┼────────────────┐
            ▼               ▼                ▼
   ownership overlay   front-band walk   quest generator
   (campaign_state)    (10min packs)     (VA-SORTIE/1 batch)
```

### 2.1 Node schema (draft)

```json
{
  "zoneId": "KOOM_CENTRAL_FLUID_SCAR",
  "mapId": "koom_valley",
  "label": "Central Fluid Scar",
  "roles": ["lane", "contested_default", "contract_seize"],
  "deployEligible": true,
  "extractEligible": true,
  "tags": ["river", "tempo"],
  "homeCharacters": ["grath"]
}
```

### 2.2 Edge schema (draft)

```json
{
  "from": "KOOM_NW_GREEN_SHELF",
  "to": "KOOM_CENTRAL_FLUID_SCAR",
  "kind": "same_map",
  "cost": 1
}
```

```json
{
  "from": "KOOM_SE_GREEN_SHELF",
  "to": "TAB_NW_PLATEAU",
  "kind": "strategic_link",
  "cost": 2,
  "notes": "South Koom → north Tabula plateau corridor"
}
```

Cross-map links are **authored narrative/strategic**, not geometric. They are the quest engine’s long-range moves.

---

## 3. Work breakdown

### Phase 0 — Inventory & unify (½ day)

- [ ] Script: dump all 45 zones → `reports/zone_atlas_inventory.json`  
  fields: mapId, zoneId, label, bounds, roles inferred from id/label  
- [ ] Validate every zoneId used in `campaign_state` / contracts exists in authored maps  
- [ ] Flatten `zone_adjacency.json` into edge list with `kind: same_map`

### Phase 1 — World graph artifact (1 day)

- [ ] Produce `data/zone_maps/world_zone_graph.v1.json`  
  - all nodes from authored zone maps  
  - all same_map edges from adjacency  
  - **empty** strategic_link list + checklist for operator/hancho fill  
- [ ] Schema validator `tools/validate_world_zone_graph.py`  
- [ ] Wire export into `outbox/war_map.json` (or replace it)

### Phase 2 — Cross-map strategic links (1–2 days, collaborative)

- [ ] Author 8–15 strategic edges that match the campaign arc  
  GF → EOH → KOOM → TAB → AB / RJ → ATS (see outbound 09)  
- [ ] Tag gates: reputation, pathSignal, missionNumber floors  
- [ ] Optional: link “character home” zones into personal quest hooks

### Phase 3 — Ownership & front on the graph (1 day)

- [ ] Overlay: for each node, owner faction from campaign_state  
- [ ] Front score: contested if owner≠player and neighbor owned by player  
- [ ] Front-band selector already used in build_next_mission — feed it graph front nodes only

### Phase 4 — Quest / contract generator (2–3 days)

- [ ] `tools/generate_sortie_candidates.py`  
  Input: world graph + ownership + reputation + characters  
  Output: ranked list of legal `VA-SORTIE/1` drafts  
- [ ] Contract kinds mapped to graph patterns:

  | kind | graph pattern |
  |---|---|
  | seize_lane | player-adjacent contested lane zone |
  | eco_raid | enemy eco role zone, path length ≤ 2 |
  | extract_vip | character home in contested zone |
  | hold_ground | player zone with enemy neighbors |
  | deep_strike | strategic_link hop into new map |

- [ ] Human pick or auto-pick top candidate → `next_sortie_order.json`  
- [ ] Keep legal contract validation as gate

### Phase 5 — Play loop glue (1 day)

- [ ] ADVANCE path: after result, recompute ownership, regenerate candidates  
- [ ] Companion console / play note shows “why this contract” (path on graph)  
- [ ] Measurement: log chosen edge path in result for tuning

---

## 4. What we will **not** do in this workstream

- Full RmlUi strategic map UI (still gated on WO-101)  
- Auto-drawing zone polygons from heightmaps (authored bounds stay source of truth)  
- 47-zone deck fiction — **45 zones only**

---

## 5. Immediate unlocks after Phase 1

Even before quest gen ships:

- Single atlas for Hancho + future GUI  
- Clean zoneId errors in contracts  
- Front-band packs only on real contested nodes  
- Character homes attach to real nodes for WO-006b enemy named spawn

---

## 6. Recommended first build slice (when you greenlight)

**WO-020a (execute next):** inventory script + `world_zone_graph.v1.json` with all nodes + same_map edges + validator.  
**WO-020b:** you + Hancho author strategic_link edges over one short session.  
**WO-020c:** candidate generator MVP (seize_lane + eco_raid only).

---

## 7. Success criteria

1. Every playable contract zoneId resolves in the world graph.  
2. Engine can list ≥3 legal next sorties without hand JSON.  
3. Cross-map progression is an explicit edge, not a hard-coded mission number.  
4. Operator can rant “push south” and Hancho maps rant → graph walk → contract.
