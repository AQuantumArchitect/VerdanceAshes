# Night Test — Multi-Rate World + Offscreen Clash + Tnb BP Cap (v0.8.4)

Abstract-first night harness. Real BAR is for play sorties; escalation between maps does **not** require spring-headless.

## Laws

### Multi-rate clock

| Band | Where | Rate × sortie elapsed |
|------|--------|------------------------|
| **live** | Focus map, measured zones | **0** abstract (BAR is truth) |
| **near** | Other zones on focus map | **0.5×** |
| **far** | Other theaters | **0.25×** |

Offline rest (`world_tick`) also advances far maps at 0.25× and runs clashes.

### Offscreen clash

`tools/offscreen_clash_v1.py` — rival adjacent zones skirmish using actor-shaped strength (SimpleAI / Defender / Null / Raptors / Ashwalkers). No spring.exe. Events land in `frontEvents` (`offscreen_clash`, `offscreen_zone_flip`). Flip cap: ≤2 per map per tick.

### Tenebrium BP cap

```
accessTnb = bank + invested living stakes
maxPlayerBuildPower = 150 * accessTnb
```

- Bank **0** and no invested → **no new** build-power units.
- Per-unit Tnb cost (`ceil(bp/150)`) still applies.
- Armada crisis bank 0 unchanged.
- Infolog: `VA_TENEBRIUM_BPCAP` · HUD chip `BP used/max`.

## Preflight (no BAR)

```bat
NIGHT_TEST.bat
```

Or:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\player\night_preflight.ps1
```

Writes `outbox/night_preflight.latest.json` and (via kernel sim) `outbox/night_world.latest.json`.

## Operator loop

1. Snapshot: `state\backups\pre_night_playtest\` (preflight can create).
2. `NIGHT_TEST.bat` → PASS.
3. Optional `RESET.bat` for rep 18/70 + Rock Jungle home.
4. `SETUP.bat` if mutator stale; `PLAY.bat` leave open.
5. Scorecard: [`NIGHT_PLAYTEST_SCORECARD.md`](NIGHT_PLAYTEST_SCORECARD.md).
6. 3–5 sorties: theater rim route → Drop → bring-home; watch Tnb/BP, offscreen events, Cortex crater grudge.

## Explicit non-goals this night

- Cloud multi-map BARb dumps / IconsAtlas overnight farms
- Live lane Lua gadget
- Full Path A/B/C victory graph

## Related

- Theater / home: [`THEATER_MAP_AND_HOME.md`](THEATER_MAP_AND_HOME.md)
- Tenebrium commerce: `outbound/43_COMMERCE_TENEBRIUM_AND_MERC_PACKS.md`
- Grow rates: `outbound/39_SEVEN_MAP_GROW_RATES.md`
