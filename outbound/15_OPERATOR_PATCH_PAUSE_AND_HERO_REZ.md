# Operator patch note — pause + named rez (2026-07-25)

## Your four requests

| # | Request | Action |
|---|---|---|
| 1 | Start paused | **Shipped** — unsynced gadget pauses on GameStart (and frame 0–2 backup). Unpause with normal BAR pause key. |
| 2 | Pause when sortie ends | **Shipped** — pause on terminal `victory` / `defeat` / `partial` before/with debrief. |
| 3 | Rezzed named units came back unnamed | **Fixed** — rez race: wreck FeatureDestroyed often runs before UnitCreated, so hero was marked dead and the new unit never re-tagged. Now: rez grace window + def/position match + worker-task path. |
| 4 | Map zones + graph for quest gen | **Planned** — `outbound/14_ZONE_GRAPH_AND_QUEST_ENGINE_PLAN.md` (WO-020). Not built yet; greenlight when ready. |

## Side effect cleaned up

Because of the rez race, **Vane and Ketha were written dead** in `campaign_state.json` after your session (wreck counted as destroyed when rezzed).  

**Restored for next play:**

- Vane → `active`  
- Ketha → `wounded` (kept her scar; deploys a bit softer)  
- Mission seed rebuilt: **va_004** with both heroes in the kit  

Backup: `state/backups/campaign_state.pre_hero_restore_*.json`

## How to verify next session

1. Run `PLAY_SESSION_V1.bat` — game should open **paused** with briefing.  
2. Unpause, fight, kill a named (Vane/Ketha floating tag), rez the wreck.  
3. Name tag + HUD should return (`VA_NAMED_RECOVERED` in infolog).  
4. Finish sortie — game should **pause** at terminal.  

## Infolog greps

- `VA_PAUSE sortie_start`  
- `VA_HERO_SPAWNED id=vane` / `ketha`  
- `VA_HERO_REZ_GRACE` (normal on rez; not a failure)  
- `VA_NAMED_RECOVERED`  
- `VA_PAUSE sortie_end:`
