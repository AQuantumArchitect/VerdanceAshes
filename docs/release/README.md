# Verdance's Ashes — Campaign for Beyond All Reason (Public Alpha)

**The green is dying. Ashwalkers hold the line.**

A single-player **campaign shell** on top of
[Beyond All Reason](https://www.beyondallreason.info).

You plan the war from a map. You fight short sorties in BAR.
Between missions the planet digs in — aces gain XP and wounds,
and the next fight is grown from that living world.

## How to play

One path, from the folder you unzipped (or cloned):

1. Install Beyond All Reason and launch it once (so it installs an engine).
2. Run **`SETUP.bat`** once. It finds your BAR install (and asks for the
   `data` folder path if it cannot), copies the mutator into BAR, and writes
   mission 1.
3. Run **`PLAY.bat`** every session and leave the window open.
4. On the war map:
   - choose a green **sortie**
   - confirm the objective on the briefing table (defaults are fine)
   - **Launch** (the field loads behind the hub), pick who goes, then **Drop**
5. Play the BAR mission (briefing → objective → extract).
6. The kernel's BAR bridge brings the result home automatically.
   If the map does not move: **After the fight — bring it home**.
7. Repeat: hire mercs, rest, talk, or take the next drop.

**`RESET.bat`** starts the campaign over (your old save is kept in `state\backups\`).

Python: the zip embeds its own runtime under `runtime\`, nothing to install.
A git clone needs Python 3.10+ on PATH; `SETUP.bat` says so if it finds none.

Same-map continues: after a win, click a debrief contract or press **1 / 2 / 3 / 4**
and **Enter** to keep fighting without leaving the map (heroes and warband carry
forward). Arrow keys move the focus.

## Sending feedback

In the hub: **System menu → Export feedback bundle** writes
`export\feedback_<stamp>.zip` (your campaign state plus the logs the kernel
needs to reproduce the problem). Attach it to an issue at
<https://github.com/AQuantumArchitect/VerdanceAshes/issues> with what you did,
what you expected, and what happened. `PLAYTESTING.md` has a short template.

## Package pieces

| Piece | Role |
|---|---|
| War map (`PLAY.bat` → :8770) | Aces, broker, theaters, drop → launch. The minimap paints what the company **believes**, not the ground truth. |
| `VerdanceAshes.sdd` | BAR mutator: mission seed, objectives, debrief |
| Campaign engine | Builds the next sortie from `campaign_state` |

Architecture: `docs/SHIP_ARCHITECTURE.md`. Deploy truth: `docs/DEPLOY_TRUTH.md`.

## Status

Public alpha playtest. Seven theaters (Greenest Fields → … → All That Simmers),
generated objectives, living occupation, Null Mercs vs Armada world war.
Expect rough edges — that's the point of the playtest.

See `START_HERE.txt` for the 30-second path and `INSTALL.md` for troubleshooting.
