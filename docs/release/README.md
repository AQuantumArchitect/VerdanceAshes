# Verdance's Ashes — Campaign for Beyond All Reason (Alpha)

**The green is dying. Ashwalkers hold the line.**

A single-player **campaign shell** on top of
[Beyond All Reason](https://www.beyondallreason.info).

You plan the war from a map. You fight short sorties in BAR.
Between missions the planet digs in — aces gain XP and wounds,
and the next fight is grown from that living world.

## How to play

1. Install Beyond All Reason and launch it once.
2. Run **`app\bin\PLAY.bat`** (leave the window open).
3. On the war map:
   - choose a green **sortie**
   - mark the ground (defaults are fine)
   - **Drop into battle**
4. Play the BAR mission (briefing → objective → extract).
5. The kernel **BAR bridge** usually brings the result home automatically.
   If not: **After the fight — bring it home**.
6. Repeat: hire mercs, rest, talk, or take the next drop.

Architecture: `docs/SHIP_ARCHITECTURE.md` (kernel phases 0–4).

Same-map continues: after a win, click a debrief contract or press **1 / 2 / 3 / 4**
and **Enter** to keep fighting without leaving the map (heroes and warband carry
forward). Arrow keys move the focus.

## Package pieces

| Piece | Role |
|---|---|
| War map (`PLAY.bat` → :8770) | Aces, broker, theaters, drop → launch |
| `VerdanceAshes.sdd` | BAR mutator: mission seed, objectives, debrief |
| Campaign engine | Builds the next sortie from `campaign_state` |

A copy in `Documents\My Games\VerdanceAshes` can be installed with
`scripts\ship.ps1 -InstallToMyGames` (see `docs/DEPLOY_TRUTH.md`).

## Status

Alpha playtest. Seven theaters (Greenest Fields → … → All That Simmers),
generated objectives, living occupation, Null Mercs vs Armada world war.
Expect rough edges — that's the point of the playtest.

See `START_HERE.txt` for the 30-second path and `PLAYTESTING.md` for feedback.
