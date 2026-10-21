# Verdance's Ashes — the rules on one page

*What the game is, in the words the game uses. Everything else in `docs/` is how it is built.*

You run a small mercenary **company** on Verdance, a dying world that Armada, Cortex, the Null Mercs and the wild are already fighting over. Between fights you sit at the **hub** (the war-room). Fights are real **Beyond All Reason** sorties. Nothing is scripted: the map, the factions and your own company's picture of the world are one simulation that keeps running while you are home.

## 1. Belief, not truth

The hub board and the in-game minimap never show the map as it is. They show what the **company believes**:

| You see | It means |
|---|---|
| A zone filled in a faction's colour | We believe they hold it. Alpha = how sure we are. |
| Green fill | We believe it is ours. |
| An outline, no fill | We believe it is empty. |
| A hairline and a `?` | Nobody has looked. |
| A dashed border | Old word — the belief is stale. |
| Red diagonal hatch | How much of **us** they currently see (exposure). `◉` marks where they think we are. |
| `✗` / `○` | The ground contradicted the brief here: held when we thought ours or blank (`✗`); empty when we thought held (`○`). |

Belief comes from what the company has seen: the last sortie's line of sight, scouts posted from camp, patrols coming back, rumours. In the fight, your own line of sight **replaces** belief live, and when the ground disagrees with the brief, Yeva says so once and the mark stays.

Nothing on the player's side ever reads the truth frame or another faction's mind. That is a law of the code, not a style choice.

## 2. The pad

One point on the map is the **pad**: the company lands there and lifts from there, like raiders. The pad is the zone you chose on the hub (its anchor; radius 560). You may only choose a pad in a zone we believe is ours, or a rim zone we believe is empty, dark or unsure with low threat — the hub strikes out the rest and tells you why in the belief's own words ("believed held by Armada (88%)").

## 3. A sortie

1. **Infil.** The game loads paused on a card: who you brought, the belief board with the pad and the job marked, what Yeva thinks you are walking into. **Enter** begins.
2. **The job.** An objective (wreck, hold, fortify, seize…) and marks — required and optional. The sidebar shows the phase (▸ APPROACH ✦ FIGHT ◆ MARKS ⌂ EXTRACT ∞ OVERTIME), the objective's progress as one bar, and the marks as squares.
3. **The clock never ends a sortie.** When it runs out the phase is OVERTIME and the map wakes up. Nothing is decided for you.
4. **Extract.** Get what you want to keep onto the pad and press **EXTRACT**. The game pauses on the **manifest**: who is going, what is staying and where, where you are lifting to (home, or a linked zone). **Enter** confirms, **Esc** goes back to the field.
5. **What is off the pad stays.** A person left on Verdance becomes an obligation the company owes. Structures left behind become **holdings** the factions will fight over. Units left are gone.
6. **Wiped.** If the company is destroyed, nobody comes back and everything on Verdance is Verdance's now.

The enemy answers what you actually did — the lane you wrecked, the gate you held, the time you spent in their sight — not a script.

## 4. Home

Verdicts come from the manifest: **SECURED** (job done, nobody left), **HINGE** (lifted, but the job undone or someone left), **FIELD COSTS** (wiped), **LEFT THE FIELD** (abandoned), **RESULT NOT HOME** (the result never arrived — retry or abandon).

At camp, time passes. Heroes rest, scout, post to zones, come back changed. The company table raises matters; what you promise there is remembered. Rumours arrive; zones change hands you never saw. The next briefing is the company's best guess — and the gap between that guess and the ground is the game.

## 5. People

Heroes are named units with levels, ranks, wounds and histories. Critical heroes must come home. A downed hero is a wreck that can be recovered (`✚` on the board); a hero left off the pad is `⚑` in the field until you go back; a dead hero is `✗ lost`. Field recruits can join mid-sortie.

## 6. Tenebrium

The company's currency. Looted from wrecks in the field, spent on hires and gear at camp, tracked on the bar at the top of the fight. Bank · looted this sortie · still in the field.

## 7. What it is not

Not a new RTS, not a balance mod, not multiplayer. BAR's units, maps, AI and fight are BAR's. Verdance's Ashes decides where you fight, with whom, and what it costs.

---

*Vocabulary.* **Belief** (what a mind thinks), **observation** (what a mind saw, with a quality η), **surprise** (how far the ground was from the belief), **divergence** (how far two minds' beliefs are from each other; the player sees only their own side of it), **exposure** (how much of us they see). The engine that holds all of this is Umwelt — see `docs/UMWELT_IN_VERDANCE.md`.
