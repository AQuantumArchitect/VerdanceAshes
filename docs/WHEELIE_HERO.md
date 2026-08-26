# Spoke — Wheelie Tech Specialist (scout mentor)

**Not a default ace.** Unlock via Null Merc standing.

## Fantasy

Spoke rides a **Wheelie** (`legscout`) and is a scout-tech specialist for the
Null Mercs. Every Wheelie that dies banked XP into Spoke; every new Wheelie
the company mints starts at that XP floor. Scout line snowballs without
making the base heroes (Vane / Ketha) depend on it.

## Unlock paths

| Path | Requirement |
|---|---|
| Broker contract | Listing `wheelie_tech_spoke` — 120 scrap, Null Mercs rep ≥ 55 |
| Soft auto | Null Mercs rep ≥ 55 on any roster ensure (intent / advance) |

Locked heroes never deploy (`status: locked` skipped in kit + intent).

## In-BAR behavior (`game_verdance_campaign.lua`)

- Hero trait `wheelie_mentor` / id `spoke` registers mentor
- Player `legscout` death → `VA_WHEELIE_HARVEST` raises bank
- Player `legscout` create → stamp `va_wheelie_xp_floor` experience
- Mentor own death still keeps bank (mints continue to get floor)

## Campaign fields

```json
{
  "heroId": "spoke",
  "name": "Spoke",
  "unitDef": "legscout",
  "trait": "wheelie_mentor",
  "traits": ["wheelie_mentor", "scout_tech"],
  "status": "active"
}
```

## Notes / future

- Could fold bank into `peakBarXp` on advance for persistence across sorties
  (today bank is sortie-local; campaign XP still grows via normal hero result path).
- Optional: name other wheelie chassis if Legion renames scouts.
