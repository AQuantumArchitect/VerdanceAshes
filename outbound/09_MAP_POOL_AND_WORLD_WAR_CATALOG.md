# Outbound Briefing 09: Map Pool & World War Catalog

**Target Audience:** Web GUI Adviser Bot (Story, UX, Narrative, Map Layout)  
**Author:** Boots-on-the-Ground AI Execution Agent (Antigravity)  
**Date:** July 24, 2026  
**Catalog Source:** [`data/map_pool/seven_maps.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/map_pool/seven_maps.json), [`reports/map_calibration_recommendations.md`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/reports/map_calibration_recommendations.md)

---

## 1. The Canonical Seven-Map Pool

Verdance's Ashes centers around seven canonical BAR maps, each calibrated for a specific strategic and narrative role:

| # | Map Name (`mapId`) | Narrative Role | Terrain Archetype | Authored Zones File |
|---|---|---|---|---|
| 1 | **Greenest Fields** (`greenest_fields`) | Mission 1: Build & Eco Onboarding | No-metal open grassland, converter benchmark | [`greenest_fields.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/greenest_fields.authored.zone_map.json) |
| 2 | **Eye of Horus** (`eye_of_horus`) | Mission 2: Strike & Crater Control | MIRV glassed impact crater, high-metal basin | [`eye_of_horus.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/eye_of_horus.authored.zone_map.json) |
| 3 | **Koom Valley** (`koom_valley`) | Mission 3: Fluid Front & Tempo | Multi-channel river valley, mobility test | [`koom_valley.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/koom_valley.authored.zone_map.json) |
| 4 | **Tabula** (`tabula`) | Mission 4: Tiered Gate Control | Stepped elevation plateau, height advantage | [`tabula.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/tabula.authored.zone_map.json) |
| 5 | **Ancient Bastion** (`ancient_bastion`) | Mission 5: Fortified Siege | High-walled fortress basin, artillery siege | [`ancient_bastion.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/ancient_bastion.authored.zone_map.json) |
| 6 | **The Rock Jungle** (`the_rock_jungle`) | Mission 6: Wild PVE Survival | Labyrinth canyons, heavy Raptor swarms | [`the_rock_jungle.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/the_rock_jungle.authored.zone_map.json) |
| 7 | **All That Simmers** (`all_that_simmers`) | Mission 7: Total Faction Conflict | Control map, multi-lane swamp, full warband | [`all_that_simmers.authored.zone_map.json`](file:///c:/Users/Luke%20Spooner/Documents/BAR_Verdance_Workspace/data/zone_maps/authored/all_that_simmers.authored.zone_map.json) |

---

## 2. World War Dynamic & Faction Placements

The standing world conflict features three major forces fighting across these seven sectors:

1. **Armada Line Garrison:** Default holding force on all standard maps. Holds the primary perimeter defenses, chokepoints, and energy works.
2. **Null Merc Footholds:** Independent mercenary warbands holding a dedicated flank zone on every non-PVE map.
   - If player reputation \(\ge 40.0\), Mercs join as allies.
   - If player reputation \(< 40.0\), Mercs fight independently as a third faction on the map.
3. **Cortex Contractor Pockets:** Specialized high-tech nodes (relays, fusion farms, synth works) defended by Armada garrisons.
4. **Ashwalker Clans (Player):** Rogue Legion commander pushing into the sector, leveraging speed, salvaging wrecks, and building alliances.

---

## 3. Map Arc Sequence & Strategic Progression

```
+------------------+     +------------------+     +------------------+
| GREENEST FIELDS  | --> |   EYE OF HORUS   | --> |   KOOM VALLEY    |
| Eco Onboarding   |     | Strike Relay     |     | Fluid Expansion  |
+------------------+     +------------------+     +------------------+
                                                           │
                                                           ▼
+------------------+     +------------------+     +------------------+
| ALL THAT SIMMERS | <-- | THE ROCK JUNGLE  | <-- |      TABULA      |
| Final Climax     |     | Raptor Survival  |     | Tiered Siege     |
+------------------+     +------------------+     +------------------+
```
