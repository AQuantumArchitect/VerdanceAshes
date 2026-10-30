# Changelog

## 0.14.0 — 2026-10-29

The second test line. Everything since the first test export (0.13.0, 2026-10-26).

### Heroes
- **64 heroes.** The roster recast gives one named hero per unit type where it counts, mixed utility in the packs, and Legion detachments supporting Armada heroes.
  - New faces include Loom, Hundred, Gorgon and Choir (Arc).
  - Also new: the Marsh sisters, Rookery, the Damwrights, Old Mother Brandt, Gladius, Triton and Mason.
  - Ceil, the Marauders and Tarn retired.
- **Scout heroes are their bays.** They land with a metal storage and 1k metal, and print scouts on repeat.
- **Builders are base-seeders:** heroes who can raise an economy, factories and constructors.
- **Field effects v2:**
  - A self effect (20–40%, many conditional: moving, still, hurt, enemy near, unseen, on water, allies close).
  - Auras that reach the company members who match them (at most +15% per stat).
  - Income, veterancy and repair auras.
  - Bonded heroes take auras ×1.5; rivals feel friction.
  - Home ground strengthens the self effect.
  - Effects now stack on veterancy and craft XP instead of being overwritten.
- **Bonds:** 153 written ties with camp talks. Every hero has a friend, a rival and a tie across factions.
- **Hero Ledger** (`tools/hero_ledger`): one dataset and page for the whole roster, with a card draft and a Markdown/JSON export.

### Meeting heroes
- Wild heroes roam by the bond web (the Umwelt encounter field).
- Bonds are the default meeting, rivals the accent, strangers uncommon. Field fit decides which strangers come.
- Hostility is continuous: a logistic in the party's stance that rises over the campaign. Tension heroes come in alive and against you; raise the wreck to recruit.
- Encounter weights live in `data/story/encounter_rules.json`. The one hard rule is a builder at the Rock Jungle's entrance.

### The war
- **Every job is territory.** Rescues are bonus objectives.
- **Ownership** is `1500 < (AV+DV)self > 3 × others`. Every owned zone is an extraction point, and lifted units go to the one reserve.
- **The Drop sheet** walks party → reserve → mercenaries → Lock drop. The field loads behind it, and a hire never reloads the field.
- **The first sortie on an open map** founds a base there.
- **Commander suits** are a one-fight loan; a raised commander comes home as a suit.
- **New ground:**
  - Spire Jump finale at the Spire Gate.
  - The Eye of Horus: a glassed crater with a Cortex camp and Armada scouts.
  - Visit tiers.
  - Tabula entrenched.
- **The store:** Cortex mercenaries, with hires for one drop.

### Under the hood
- **Performance:** the belief board paints row runs into display lists, and belief nodes leave with their units. HUD garbage went from ~17 MB/s to 0.08 MB/s, ending the 1.2 GB LuaRAM emergency collections.
- **The campaign gadget** is a core plus parts with checked headers.
- **HUD:** every gadget-HUD signal has both ends (`tools/hud_wire.py`), and the loop runs headless.
- **Clean-up:** dead modes, flags, code and slop are removed; the mission builder is 414 lines shorter.

## 0.13.0 — 2026-10-26
First test export: SHIP -Dev, fresh-tree tests, shell-only occupation, graph fallback objectives.
