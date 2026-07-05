# Verdance's Ashes — Procedural Campaign for Beyond All Reason (Alpha)

Verdance's Ashes is an experimental **procedural campaign** that runs on top of
[Beyond All Reason](https://www.beyondallreason.info). You play short sorties in BAR;
between missions, a local story engine measures what actually happened in your match
(zone control, army value, economy) and advances a persistent campaign world:

- a **campaign graph** tracks faction pressure, contested space, scarcity, and your path through the story
- **zones evolve offscreen** — enemies you ignored keep building while you fight elsewhere
- your **companion (Ketha)** gains experience, morale, and stress across missions
- every mission is **generated from campaign state**, not hand-scripted

## What's in this package

| Piece | What it does |
|---|---|
| `VerdanceAshes.sdd` | A BAR mutator (game archive). Spawns missions, detects objectives, ends the game, and reports results. Installed into your BAR `data\games\` folder. |
| `workspace\` | The campaign engine: builds the next mission, launches BAR, reads the result out of the match, advances the campaign, and generates the next mission. |

## Quick start

1. Install and launch Beyond All Reason at least once (so it downloads an engine).
2. Unzip this package anywhere (e.g. `Documents\VerdanceAshes`).
3. Run `workspace\SETUP.bat`. It finds your BAR install, installs the mutator, and creates a fresh campaign.
4. Run `workspace\PLAY_SESSION.bat`. It builds mission 1, launches BAR, and waits.
5. Play the mission. The objective panel at the top of the screen tells you what to do.
   Win/loss is detected automatically; when the game ends, the campaign advances itself
   and the next mission is built.
6. Run `PLAY_SESSION.bat` again for the next mission. That's the loop.

See `INSTALL.md` for troubleshooting and `PLAYTESTING.md` for how to send feedback.

## Status

This is an **alpha playtest build**. The campaign spine currently cycles seven maps
(Greenest Fields → Eye of Horus → Koom Valley → Tabula → Ancient Bastion →
The Rock Jungle → All That Simmers) with generated objectives, difficulty scaled by
campaign pressure, and persistent zone memory. Dialogue and story presentation are
minimal. Expect rough edges — that's what the playtest is for.
