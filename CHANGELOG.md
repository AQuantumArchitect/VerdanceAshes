# Changelog

## Unreleased

- **The Overthrow is a soak** (owner call). The finale's castle used to be a 20-minute siege bake: four Armada seats against three Null Mercs besiegers. Now three balanced BARbs and five simple defender and constructor AIs raise the castle unopposed for a set time, and the soak time is the difficulty: 15 minutes easy, 20 medium (shipped), 35 hard. Then most of what built it goes: 85% of the constructors and nano turrets (fewer builders, less Tenebrium to reclaim from them), and every commander but the one in the Keep. Factories stay. In the mission only the Keep's commander is left (`keepOneCommander`); the company used to face nine. The medium bake has 957 units. `tools/war_bake_v1.py --map ancient_bastion --soak easy|medium|hard`.
- **No more debug lines in the console.** The mod writes hundreds of `VA_` lines a sortie for the kernel and the test tools: the result in 48 JSON chunks, field ticks, memory stats. Each one also scrolled through the player's chat console ("VA_OBJECTIVE_TARGET_DOWN force=living_shell_primary destroyed=61/72"). They now go out at the log level BAR's chat skips, and the infolog still records every one. A sortie came home with 499 such lines and none on screen. `va_echo=1` brings them back for debugging.
- **Heroes bring their mood from camp into the fight** (owner direction, first slice). Each hero on a drop gets a temper from the camp, as two numbers. Nerve rises with bonds to the people on the same drop (camp talks and fighting together add bond points) and falls with a rival aboard, a wound being carried, the times they've gone down, and bonded friends lost. Drive rises with bonds and experience and falls with grief. In the field the temper scales the hero's own doctrine: a shaken hero bails and kites sooner, a steady one holds, and drive leans into the push. `verdance.company.temper`, `mission.heroTemper`, and `VA_HERO_TEMPER` in the infolog.
- **Air heroes can be rescued.** A field recruit is seeded as a wreck by spawning its unit and killing it quietly, but an aircraft killed that way leaves no wreck. So Rookery and Stiletto were "lost" at frame 120 on every Rock Jungle visit (`cause=no_wreck`). An air hero is now seeded as a ground constructor of its faction, and raising it brings back the real hero, as already happened for building heroes.
- **Rock Jungle grace never falls below five minutes** (owner call). It eases from 600 s toward 300 with each visit; it used to fall toward zero (81 s by the tenth visit on the hard-AI run).
- **A rescue that fights you first is never folded away** (playtester note). The jobs rail lists hostile rescues first and marks them as a fight; only friendly ones fold into "and N more".
- **The debrief says where a new recruit is:** home at camp, or waiting at a zone for the company to fetch them.
- **A shorter jobs screen.** "What it pays" and "To win" are a third shorter.
- **Store blurbs no longer restate the price** ("for a fortune in metal", "priced like it", "Costs Tenebrium"); the price is on the badge.
- **Who goes: compact hero cards** (playtester note). Cards take the height of what they say instead of the whole screen, XP is a bar toward the next level ("23 / 100 to L3"), and Ketha is in full colour with an "always comes" lock instead of greyed out like someone who can't come.
- **Autopilot (testing rig): a more careful proxy player.** A named hero badly hurt, or hurt with a crowd near, walks back to the pad and stays there until it is mostly whole, and heroes are never nudged into the fight. On raptor ground the company plays BARb "hard" (balanced) instead of hard_aggressive and leaves a minute after the grace ends, done or not. Before each drop it spends most of the metal bag on mercenaries.

- **The drop limit grows with every sortie you play** (owner call). It is how much of the reserve a drop can start with, and it used to grow 1k metal per victory or extraction and nothing for a partial. On the 11-04 hard-AI run, nine partials left it near 1k while the reserve held about 100 units, so the company dropped as hero packs alone. Now every sortie fought grows it by 1k, whatever the verdict, with no ceiling. An abandoned sortie doesn't count. The reserve screen calls it the drop limit.
- **The field's starting metal is no longer banked as hauled.** The metal you lift off with is yours to spend, but every sortie also starts with a 1k allotment, and the result contract dropped the field that says so (`metalKFieldStart`). So each sortie banked its unspent 1k as if the company had hauled it home. The contract keeps it now, and the bag grows only with metal brought home beyond it.
- **Losing costs what is on the map** (owner call). A wiped company's stockpile used to be banked as if it had lifted off. It was on the map, so it's lost with the company.

- **CI runs locally.** GitHub Actions is manual only (Actions minutes are scarce). `scripts\test\ci.bat` is the gate before a push: the hub tests with the real Umwelt pin, the ship dry run and the staged-build check. The workflows use the Node 24 actions (checkout v5, setup-python v6, upload-artifact v5).
- **The test rig runs on Windows.** Lua 5.4 is found on Linux or Windows (`winget install DEVCOM.Lua`, or `VA_LIBLUA`), the hub tests start no detached belief workers, and the tests that assumed Linux (symlinks, BAR's install paths) work on a PC with BAR installed.

- **The test rig travels with the repo.** `scripts\test\` holds the autopilot bats (hard-AI campaign, tour, finale, resume, two-sortie rehearsal). They build their own venv and Umwelt at the pin, with no machine paths. `tools/test_rig/` holds the hub snapshot, the flow walk the playtester reads, and the Lua runner. `docs/TESTING.md` covers what each rig is for and what was open on 2026-11-08.


## 0.15.0 — 2026-11-04

The sortie flow. Choosing a job starts loading the field in Beyond All Reason; while it loads you answer up to two camp talks, pick who goes, and pick what comes. Then you drop. Missions are built in Python (no PowerShell needed to build), the pull home is a smooth curve on the Tenebrium you bring back, and the Rock Jungle's raptors pick up gradually with every visit.

- **BAR is never hidden while the field loads.** On a new laptop, BAR loaded behind the hub, said "battle started… battle paused", then showed only a transparent window that took no clicks. The kernel had minimized BAR while it loaded and restored it under the hub without focus. Now BAR loads in its own window, the hub gets the screen back once BAR has opened, and on Drop BAR comes to the front, restored and active.
- **The kings' showdown in four corners** (finale B, owner call). The company lands north-west, Armada starts north-east, Cortex south-east, and a raptor den with its hives holds the south-west. That makes three kings and the wild, with every corner occupied. The Null Mercs no longer sit a throne. The raptors fight everyone, at an easier pace than the Rock Jungle's (very easy, with a slower queen), so they harry the kings without deciding the throne. The throne is still the last commander standing. In Cortex's own suit, Cortex stays home and its corner stands empty.
- **The showdown keeps the map's own water** for the whole match: no sink and no tide. All That Simmers is flat, and the tide drowned whole seats mid-match.
- **No Tenebrium gate in the showdown.** It is a straight game of BAR: the company builds freely, as the rival kings always have. With the gate on and a walked bank of 12, the company was refused its T2 plant 251 times in one match and never fielded an army that could reach a corner.
- **The den holds its own corner.** In the showdown the raptor den grows every turret except the meteor turret, which shoots the whole map. In one test match a meteor turret in the south-west killed the company's king in the north-west at minute 68.
- **No field recruits in the showdown.** A hostile recruit loose on the board decided the throne: in one test match a Tsunami seaplane killed the Cortex king at minute 7.
- **Autopilot (testing rig):** a king's siege gathers 2,200 elmos short of the king and strikes together, or after three minutes with whatever has gathered.
- **The sortie flow** (owner calls). The hub asks one question per screen. **The jobs:** the board and the two or three jobs on offer, each naming whom you could rescue; the side column and the repeated job text are gone. **Choose this job** starts loading the field in Beyond All Reason, and while it loads you walk three screens. **Camp talks:** every pending story scene, the company's most pressing matter and one support talk, answered one at a time. **Who goes:** leave anyone at base. **What comes:** the reserve and the mercenary store on one screen. Then **Drop**. The debrief is now a full screen, with **Choose the next job** to move on.
- **A lost map can be retaken.** Holding no door on a map, the hub's take-the-door job had no place to land, and the campaign stalled on it. This happened to the hard AI after two Rock Jungle defeats. The job now lands on the door itself, as a road crossing does.
- **The briefing subtitle is in plain words.** It used to read "Contract for nullmercs against armada on tabula/T_NW_RESERVE". It now reads "For the Null Mercs, against Armada.", and a finale reads "The last fight: the Spire Jump."
- **Every talk can be declined.** Each scene, matter and support talk offers "No time for this.", which costs nothing and records no stance. A declined scene or matter is closed for good, and you can't put a talk off to later. A support talk you decline can come back, because supports build up.
- **The autopilot scouts.** The test rig sends its fastest fighter to each scout mark, then hands it back to the AI once the mark is done.
- **One primary, two kinds of secondary** (owner call). The primary is still taking the ground. Secondaries are now scouting ("scout Northwest Lane": done once the company has had a good look at the zone) and rescues (rez a wreck to bring them in). Both are always optional. The escalation ladder's extra enemy camps are gone; its secondaries are scouting now. Scouting pays in what the company learns, and a rescue pays a person, so neither adds Null Mercs standing. On the rail and the board, a scout mark is blue and a rescue is red.
- **The Home tab is gone.** With the camp level gone, it held only the clock: rest, wait, scout, post and recall. Scouting is now a secondary, and anyone not on the drop is at base.
- **No camp level** (owner call). The camp is whatever the company has built and left standing in the Rock Jungle. The hub no longer sells camp levels for Tenebrium and metal: Raise camp, the Founding sortie button and the camp status are gone from Home. Tenebrium to spend pulls the company home to build (see the next entry), and the clear-the-wilds job unlocks once something stands there. The "A Place to Stand" reading now counts the structures standing in the Rock Jungle.
- **The loop is raid, eat the Tenebrium, bring it home** (owner call). Losing in the Rock Jungle costs nothing extra: the stock a visit wants depends only on what the camp is worth. Builders don't build at base, and there is no camp growth while you are away. The camp is what the company builds there with the Tenebrium it brings home.
- **The pull home is a smooth curve** (owner call: "parametric and continuous"). There is no "3 Tenebrium" rule any more. Tenebrium in the bag pulls the company toward the Rock Jungle along a logistic curve. The point where the pull reaches one half is the stock worth going home for. With no camp it sits at 2 Tenebrium, and it rises with what the camp is already worth (0.6 Tenebrium per 1k metal while the camp is small, slowing as it grows). Every Rock Jungle job gains or loses up to 1.2 in the road score with the pull, so an empty bag sends the company out by the roads instead of home. Before this, Rock Jungle doors won 7 of 11 jobs on the hard-AI run. The clear job comes from the curve's midpoint, and Ketha says what a visit wants once the bag is worth the trip.
- **The Rock Jungle's raptors pick up smoothly.** Before, the second visit had no grace and the third started the raptors half an hour into their clock. On the hard-AI run, every Rock Jungle drop after the founding was wiped 80 to 200 seconds after landing. Now grace shrinks by e every three visits (600, 430, 308, 221 seconds…) and the raptors' head start climbs toward 30 minutes by e every eight visits (0, 212, 398, 562 seconds…). Home stays a place you can go back to.
- **What comes, in rows.** The reserve is one row per unit type with − and +, and a line explaining the lift limit. It replaces 22 identical kit tiles. Store listings show one line, with the rest on hover. A listing you can't afford says "needs 16k metal (you have 13k)", not "need 16×1km$ metal (have 13)".
- **Each rule once, where it matters.** The route is one line: land at the pad, then lift from the same pad, or from the door once it's yours. The pad rule (only what stands on the pad at extract comes home) sits on What comes. A job against a side shows your standing with that side, and "What it pays" is out of the fold. The repeated map-only notes are gone from the drop button, the status line and the store; the "Map only" badge stays. A hero card tells its pack once, on the meta line.
- **Playtest round two.** On the jobs rail, Ketha says what the bag is worth once it pulls home. "What it pays" is two short sentences. The pad rule says that what you built in the field becomes a holding. The store's intro no longer talks about loading.
- **Two talks a drop at most.** Story scenes come first, then the most pressing matter, then a support talk. The rest wait for the next drop.
- **The debrief says what moved:** standing with each side, before and after; which scout marks were seen and which rescues came in or were lost; and who is still out in the field.
- **Screen tour (tooling):** `autopilot_campaign_v1.py --tour` walks the campaign without BAR. Each sortie builds its real seed, fakes a clean extraction and keeps the hub before and after. `tools/screen_tour_v1.py` renders every hub tab and the briefing, field and extraction screens from that seed, with a word count for each, so the UI pass can cut from a measured inventory.
- **Testing only:** `autopilot_campaign_v1.py --rival-ai SimpleAI` plays every rival seat as SimpleAI, to check that a field can be won at all. The real game keeps BARb.
- **The Python mission builder runs on a Windows console.** Its first live build on the PC died printing "→" in the console's cp1252 code page. The builder now writes UTF-8, and the kernel reads every Python child as UTF-8.
- **The mission builder is Python** (`python -m verdance.mission_builder`). It writes the same scenario `build_next_mission_v1.ps1` did, value for value, checked against eleven sorties of a tour from the PC (`tests/test_mission_builder_parity.py`). The kernel builds with it; `install_playable_slice.ps1` still writes the seeds and the startscript, and is skipped (the build still succeeds) on a machine with no PowerShell. The PowerShell builder stays as the reference: `VERDANCE_BUILDER=ps1` runs it. The port found three faults in it. Two are fixed: Armada and Cortex war seats now carry their team colour, and a single visit-tier warden now takes the field (before, only two or more did). The third no longer matters: the Rock Jungle home's shorter raptor grace was never applied, but every Rock Jungle drop now sets its grace from the visit's raptor pace (next entry). The parity test reproduces the faults (`ps1_faults=True`) so it can still match the corpus exactly.

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
