# Changelog

## Unreleased

- **The kings' showdown in four corners** (finale B, owner call). The company lands north-west, Armada starts north-east, Cortex south-east, and a raptor den with its hives holds the south-west. That makes three kings and the wild, with every corner occupied. The Null Mercs no longer sit a throne. The raptors fight everyone, at an easier pace than the Rock Jungle's (very easy, with a slower queen), so they harry the kings without deciding the throne. The throne is still the last commander standing. In Cortex's own suit, Cortex stays home and its corner stands empty.
- **The showdown keeps the map's own water** for the whole match: no sink and no tide. All That Simmers is flat, and the tide drowned whole seats mid-match.
- **No Tenebrium gate in the showdown.** It is a straight game of BAR: the company builds freely, as the rival kings always have. With the gate on and a walked bank of 12, the company was refused its T2 plant 251 times in one match and never fielded an army that could reach a corner.
- **The den holds its own corner.** In the showdown the raptor den grows every turret except the meteor turret, which shoots the whole map. In one test match a meteor turret in the south-west killed the company's king in the north-west at minute 68.
- **No field recruits in the showdown.** A hostile recruit loose on the board decided the throne: in one test match a Tsunami seaplane killed the Cortex king at minute 7.
- **Autopilot (testing rig):** a king's siege gathers 2,200 elmos short of the king and strikes together, or after three minutes with whatever has gathered.
- **Testing only:** `autopilot_campaign_v1.py --rival-ai SimpleAI` plays every rival seat as SimpleAI, to check that a field can be won at all. The real game keeps BARb.

## 0.14.6 — 2026-11-03

Every ending can be reached and won. On a stock BAR install, a hard AI (BARb, hard_aggressive) beat the whole campaign and each of the three finales.

- **Raptors on current BAR.** BAR moved its utilities from `Spring.Utilities` to `BAR.Utilities`. Verdance's raptor spawner read the old name on its first line, so on a current install it failed to load: the Rock Jungle had no raptor waves, no rage and no queen. It now reads whichever this BAR has.
- **The finale's massive start lands again.** Since 0.14.0, a sealed hub crew also dropped the act-3 kit: the base, lab and army the finale is built around. They land beside the company again; the heroes still come in their packs.
- **The Spire Jump (finale C) can be powered.** The gate wanted four advanced fusions, which only a T2 constructor builds, and the company raises T2 labs only on All That Simmers. It now charges from 1,500 energy a second of the company's own generators near it (solars, winds, geothermals, fusions, Hearth's reactor). The rail reads `power 640 / 1500 energy`. The gate's frame now stands where a constructor can walk to it; it used to stand on rock the company could not climb.
- **The Overthrow (finale A) is the Keep.** The Keep's war seat is the target, and its 18 guns and factories are what you break, not its 66 windmills and extractors. A finale is won by its own objective, not by holding ground next to the pad.
- **The kings' showdown (finale B) can be won.** Each king now starts on its seat; BAR used to put them on the map's own start points in random order. A king whose ground lies under the sea, or under the tide still to come in the match, walks inland in the first seconds. The Armada king used to start under water, where no land army could reach it.
- **Armed means it has weapons.** Presence, contested holds and the Overthrow's booking counted windmills and extractors as fighters (BAR leaves them able to attack).
- **A build refused for want of Tenebrium** says so once every 30 seconds per builder. It used to say so every frame: a factory left with a constructor queued and an empty bank wrote 1.6 million lines in one finale, until the game ran out of memory and the sortie came home without a result.
- **Rehearsals:** `autopilot_campaign_v1.py --finale A|B|C` starts at the ending with a walked campaign's bank (12 Tenebrium). The autopilot breaks the Overthrow's targets, builds and powers the Spire Gate and walks the heroes through, and in the kings' showdown leaves the war to BARb for half an hour, then attacks the kings' commanders.

## 0.14.5 — 2026-11-02

The Null Mercs fight Armada, not you.

- **One side.** The company and the Null Mercs, allied in the match, no longer contest each other's ground. Each still needs more than 1,500 of its own strength in a zone and three times its enemies'. Neither lends strength to the other, and when both qualify the zone is the company's. A zone the mercs hold beside you (mercs 4,000, you 1,400, Armada 500) is now theirs instead of nobody's. The game and the hub use the same rule; a test runs both on the same zones.
- **No clashes between allies between sorties.** The campaign's between-mission fights paired a mercs zone with the company's next door and handed it to the company. Now only Armada (and the others) fight either of you.

## 0.14.4 — 2026-11-02

Mission 1 gets a designed opening, and the door you take stays taken.

- **Mission 1's opening** (#10, `docs/MISSION1_OPENING.md`):
  - The briefing is three of Ketha's lines.
  - The job arrives in two stages: first "Off the pad. Eyes on their farm." with a gold ring on the ground, then the real job once the farm is in sight.
  - Select, move, attack and build are each prompted only if you haven't done them yet. A prompt clears the moment you do.
  - Minute five ends on an intercepted Armada dispatch and a column on its way.
  - Every timing is tunable in `data/escalation/mission1_opening.json` (`pacing`).
- **A door taken stays taken.** The result the hub reads at home dropped the list of the company's allies. So a door the company lifted from with the Null Mercs beside it was not held at home, and the next sortie offered the same door again.
- **Fixed on the way:**
  - The briefing card printed "table: 0x…" for its line.
  - Mission 1's objective mark sat at the Bastion's box centre instead of on the farm.
  - The generic "hero down" bark fired at the first second about field recruits nobody had met.
- **Autopilot `--beats`** keeps the authored beats on in a headless rehearsal.

## 0.14.3 — 2026-11-02

A fix release: on 0.14.2, the first mission could not be won once the Null Mercs followed the company in.

- **Allies don't contest the company's ground.** In mission 1, the Null Mercs (allied in the match) walked into the Northwest Bastion behind the company. Their presence counted as "everyone else", so the hold's need climbed from 3,871 to 27,751 and the hold never started. The company's allies now count neither for it nor against it: in the objective's hold, in the live extraction points and when the campaign moves zones at home. On a stock BAR the opening now completes in about three minutes.
- **The opening's card names the real target.** It said "the southeast plateau" and promised the Koom Valley road; the target is the Northwest Bastion next door. "To win" says what the game checks (wreck most of the zone, then hold it with more than 1,500 of your own army there and three times the enemy's), not the contract's name.
- **A stopped hold says why**: `hold 0s / 30s · waiting for presence`.
- **A failed Drop says why**: `mod sync failed:` and the installer's first error line.
- **Heat ray**: no more GameFrame error every 10 frames for a Halberd with no veterancy yet.
- **The first drop on a new BAR install** loads for several minutes while BAR scans its files once; START_HERE says so.
- **Autopilot** holds a capture's zone when the company is short of presence there, so rehearsals can finish a capture; `docs/FIRST_MATCH.md` walks the first match minute by minute.

## 0.14.2 — 2026-11-02

A fix release: 0.14.1 started on a stock BAR install but a friend's first match still did not.

- **SETUP accepts a stock BAR data folder.** A fresh install has no `games\` folder; SETUP now makes it instead of refusing.
- **Fresh installs get the campaign maps.** SETUP fetches all seven, PLAY re-checks before a drop, and a drop that is missing one says which. The map service answers with a single object for some names, which 0.14.1 read as "no such map" (Greenest Fields 1.3 never downloaded).
- **Another installed version of a pinned map is named.** BAR's own download may give 1.3.1 where the campaign is pinned to 1.3; the message now says so rather than reporting the map missing.
- **Autopilot `--stock`** rehearses a fresh BAR install (engine and rapid game only), and dev checkouts find the pinned Umwelt clone. A run capped with `--sorties N` passes (exit 0, `REHEARSAL OK`) when every sortie came home.
- **Umwelt moves to `7ee6d08`** (its `main` on 2026-11-02). The 0.14.1 pin (`8154c13`) had no `foresight.encounter`, so wild heroes never roamed in a shipped build; the hub now speaks the newer encounter vocabulary (`arrival` where it said `presence`).

## 0.14.1 — 2026-11-01

A fix release: 0.14.0 needs it to start on a normal BAR install.

- **Plays on a stock Beyond All Reason.** The campaign mutator depended on `Beyond All Reason $VERSION`, which only a developer checkout of BAR is called. A BAR installed from beyondallreason.info stopped at load with `Dependent archive "Beyond All Reason $VERSION" not found`. SETUP and every drop now set the installed copy to depend on the BAR the launcher downloaded (`Beyond All Reason test-N-hash`), and pick up BAR updates.
- **Setup instructions** (START_HERE.txt, docs/INSTALL.md) follow the current drop: Ready the drop, confirm the party and the reserve, hire, Lock drop. They also cover Windows' "protected your PC" prompt and the new load error.
- **Umwelt** is the pinned commit (`tools/umwelt_pin.json`), and its Apache-2.0 LICENSE ships beside it. 0.14.0 had picked up a stale copy and shipped none.
- **No machine paths in the build.** `release_manifest.json` records commits, not the builder's folder, and the launcher has no developer-only hooks.
- **Release tooling** runs on Windows PowerShell 5.1.

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
