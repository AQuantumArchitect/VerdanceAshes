# Outbound 43 — Commerce, Tenebrium, merc packs, local battle farm

**Date:** 2026-07-28  
**Status:** **SHIPPED (data + engine + compile + gadget hooks)** — broker economy playable in intent/compiler; full shop UI still thin

## Fantasy

Ashwalkers / Null Mercs are a **mercenary band**, not a full faction eco. They buy chaff streams, loan packs, and (with reputation) stolen constructors. The galaxy's build-metal is **Tenebrium** — black-hole distillate from BAR lore, scarce since the **Generic Disaster**. Anything that *builds* costs **≥ 1 Tenebrium**. You start with **none**.

## Pieces

| Piece | What |
|-------|------|
| **Punch of Thugs** | Starter **loan**: 6× `corthud`, spawn **smoking** (~32–52% HP). Return them in better shape (alive count ≥ loaned on a win) or the broker docks rep/credits. |
| **Crash of Brutes** | Buy 4× `corraid` for scrap credits (no Tenebrium — they do not build). |
| **Cortex Grunt Fab** | Buy a little `corlab` **locked** to print `corak` forever. Arc 1 chaff stream. Costs **1 Tenebrium**. |
| **Grunt Fab Build Power** | Arc 2+: nanos + thicker metal/energy trickle. Costs **1 Tenebrium**. |
| **Armada / Cortex constructors** | `armck` / `corck` at **rep ≥ 60** + **1 Tenebrium** each. |
| **Scrap credits** | Broker scrip for pure combat packs. |

## Data / code

| Path | Role |
|------|------|
| `data/commerce/commerce_catalog.json` | Listings, costs, loan policy, sortie rewards |
| `tools/verdance_story_engine_v1.py` | `ensure_commerce`, `purchase_listing`, `build_commerce_intent`, `settle_commerce_after_sortie` |
| `scripts/build_next_mission_v1.ps1` | `Add-CommerceDeployToKit` → player force |
| `mod/.../game_verdance_campaign.lua` | `healthFrac` / loan tags on spawn |
| `scripts/run_local_battle_farm.ps1` | Local Koom 1v1 BARb T2 mid bake (no AWS) |

## State shape

```json
"commerce": {
  "tenebrium": 0,
  "credits": 40,
  "owned": { "punch_of_thugs": { "loan": true, "loanCount": 6, ... } },
  "upgrades": {},
  "ledger": []
}
```

Intent exposes `commerce.shop` (shelf + availability) and `commerce.deploy` (compiler kit inject).

## Sortie rewards (deterministic from resultKey)

- Victory → chance of +0–1 Tenebrium, +scrap credits  
- Zone flip → higher Tenebrium chance  
- Clean extract → small extra chance  
- Loan return OK → credit tip + Null Merc rep; small Tenebrium tip chance  
- Loan breach → credit debt + rep hit  

## Local sims (coward's-road deferred)

Cloud can wait. On this box:

```powershell
# Package + run Koom 1v1 BARb hard_agg ~22 min sim (~T2 mid)
.\scripts\run_local_battle_farm.ps1

# Package only (no engine)
.\scripts\run_local_battle_farm.ps1 -PackageOnly
```

After dump: `apply_shell_strip.ps1` with `strip_filter_t2_battle.json` + decoy occupation (see outbound 42).

**Risk / reality check (2026-07-28 local run):**  
`run_local_battle_farm.ps1` launches correctly (quoted paths, isolation, settings patch) but headless still **spins forever on IconsAtlas at f=30** (`atlasRendered=0`, multi-GB RAM). Process killed; springsettings restored. **Real BARb dumps still want cloud (or a headed/GPU path)** until that engine hang is cracked. Placeholders + strip/decoy pipeline remain usable offline.

## Full Tenebrium resource (WO-043c) — **SHIPPED**

**Not an engine change.** Verdance campaign gadget + story graph.

### Rules

| Rule | Behavior |
|------|----------|
| **Build-power cost** | Any unit with `buildSpeed > 0` costs **≥1 Tnb** (`ceil(bp/150)`). Charged when the player starts the nanoframe; refunded if cancelled incomplete. |
| **Reclaim stake** | That cost is stamped on the unit (`va_tenebrium_invested`). On death it lives on the wreck/heap/debris. |
| **Durable wrecks** | Tnb survives wreck → heap transfer. **Truly gone** (vaporized, no debris) → `tenebriumLost`. |
| **Reclaim** | Reclaim steps pull Tnb into the **bank** proportionally; infinite storage (display number only). |
| **Decoy farms** | Enemy decoy coms still drop shards (≥1 Tnb) — Armada’s spent investment. |
| **Armada crisis** | Armada bank **0**; cannot create new build-power units. Pre-placed occupation stays. |
| **Q7** | `q7_resource_scarcity` is the Tenebrium scarcity qubit — eases from bank/commerce stock + crisis floor. |

### HUD / params

- `va_tenebrium_bank` / `_looted` / `_spent` / `_lost` / `_storage=-1` (∞)
- `va_armada_tenebrium_crisis`
- Objectives strip: **Tenebrium: N (∞ storage)** + crisis line

### Result → campaign

`tenebriumBank` end-of-sortie becomes the commerce bag carry; spent/lost/reclaimed noted in ledger.

Infolog: `VA_TENEBRIUM_INIT` · `SPEND` · `REFUND` · `PENDING` · `SHARD` · `HEAP_TRANSFER` · `LOOT` · `LOST` · `BLOCKED`

## Still open

- [ ] In-client shop panel (console / overmind) calling `purchase_listing`
- [ ] Track loan HP quality beyond survivor count (true “better shape”)
- [ ] Optional in-mission Tenebrium spend for placing new build structures
- [ ] 3v3 denser Koom mid once 1v1 density is known
- [ ] AWS cloud later for overnight multi-map farms

## Operator play notes

1. Fresh campaign: **Punch of Thugs** is free and already owned — expect damaged Thugs and busy rez bots.  
2. You **cannot** buy the grunt fab until you scavenge **1 Tenebrium** (win/flip sorties).  
3. Constructors stay locked until faction rep is high **and** you have Tenebrium.  
4. Crash of Brutes is the expensive hammer when you have scrap but not build rights.
