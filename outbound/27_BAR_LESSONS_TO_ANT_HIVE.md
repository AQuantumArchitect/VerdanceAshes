# Outbound 27 — BAR lessons exported to the ant hive

While you are offline from games (~3–4h), the Verdance RTS doctrine was
ported into the **general ant hive** (yurt-sync / wargen-grok).

## Idea

An ant hive bootstrap fails the same way a bad BAR player fails: thrash every
unit every frame, stack expensive cycles, zero progress on death, hide the
difficulty behind fog. An RTS master does the opposite.

## Shipped (hive)

| Piece | Path |
|-------|------|
| Commander | `ws-win/yurt-sync/work/_wargen/coral/hive_rts_commander.py` |
| Launcher | `.../hive_rts.ps1` |
| Doctrine | `.../plans/BAR_LESSONS_TO_HIVE.md` |
| Mission card | `commons/vitals/hive_rts_mission_card.md` |
| Sticky XP | `commons/vitals/hive_rts_state.json` |

## Live beats already run

1. **Farm patrol** — quantum fungus dance ×3 + free dispatch → OK  
2. **Support push** — butler + revenue on Dave dam pressure → dispatch OK  
3. Caste XP banked: butler + revenue **L2 Runner** (sticky; death would not wipe)

## Fair HUD (what the commander sees)

- Hearth up/sick · hive grade · mesh honesty  
- Axes as **bands** (low/mid/high/critical), not a blended fake score  
- Dam count + top Luke dam (never fake-cleared)  
- Fungus allow_cycle / farm vs full push  

## When you get back

```powershell
cd C:\Users\Luke Spooner\ws-win\yurt-sync\work\_wargen\coral
python hive_rts_commander.py status
python hive_rts_commander.py card
```

BAR campaign XP farm work remains in Verdance; this is the **same doctrine**
on the swarm so the hive stops bootstrapping blind and starts campaigning.
