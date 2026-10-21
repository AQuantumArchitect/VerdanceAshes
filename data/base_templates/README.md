# Living shell templates

Frozen base shells for Verdance occupation maps.

- Rate catalog: `grow_profiles.json` (SimpleAI sprawl vs BARb easy/medium/hard/hard_aggressive)
- Cloud bake notes: `scripts/forge/cloud/README.md`
- Design briefs for shells / grow rates / decoy farm: git history under `outbound/` (see `docs/ARCHIVE.md`)
- Sims use **normal commanders**; occupation plants **decoy coms** (`armdecom` / `cordecom` / `legdecom`) after strip

## Layout

```
base_templates/
  grow_profiles.json
  strip_filter.json
  strip_filter_t2_battle.json   # richer keep set for war-mid claims
  wrath/
    armada_gunslinger_response_v1.json
    cortex_qrf_v1.json
    bastion_heavy_v1.json
    wild_thin_v1.json
  greenest_fields/   bake_recipe + armada_placeholder_v1 (+ armada_t15 after bake)
  eye_of_horus/
  koom_valley/
  tabula/
  ancient_bastion/
  the_rock_jungle/
  all_that_simmers/
```

Each map folder: `bake_recipe.json` (with per-start `growProfile`) + rate-tuned placeholder.

## Grow profiles (character, not new lore)

| Profile | AI | Use |
|---------|-----|-----|
| sprawl | SimpleAI | Converter utopia / energy islands |
| hold | SimpleAI | Ridges, rims, quiet shelves |
| fortify_easy | BARb easy | Light teeth among sprawl |
| fortify | BARb medium | Lane teeth, gates |
| fortify_hard | BARb hard | Citadel, Cortex dealer, plateau fort |
| scrap / thin | SimpleAI | Null scrap, glass edge, killfield |
| aggressive_core | BARb hard_aggressive | Battle-farm cores (Koom 1v1 T2 mid) |

**Commanders:** sim = normal coms · occupation shell = decoy com swarm (less metal, less danger).

## Commands

```powershell
# One map placeholder (applies growProfile multipliers + decoy nodes)
powershell -File scripts/generate_placeholder_shell.ps1 -MapId koom_valley

# All seven placeholders
powershell -File scripts/bake_all_living_shells.ps1 -PlaceholderOnly

# Preferred: cloud BAR sims (all seven, BARb rate mixes)
# 1) copy data/cloud/cloud_config.template.json -> cloud_config.json and set host
# 2) package offline, then sync+run+harvest
powershell -File scripts/cloud/New-CloudBakeBundle.ps1
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -RefreshMembrane

# Koom 1v1 BARb hard_agg → T2 mid claim package (battle farm, not peaceful co-grow)
powershell -File scripts/package_battle_farm.ps1

# Local headed GPU when headless IconsAtlas hangs (spring.exe, shortest map first)
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle
powershell -File scripts/bake_all_living_shells.ps1 -Headed

# Local headless fallback when IconsAtlas is not broken
powershell -File scripts/bake_living_shell.ps1 -MapId the_rock_jungle
powershell -File scripts/bake_all_living_shells.ps1
```

Headless launch must use `--write-dir <barDataRoot> --isolation --only-local <script>` (local + cloud workers).

## Compiler

Prefers baked `living_shell_v1.json` / `armada_t15_v1.json` over placeholders.
Shell-capable kinds: eco_raid, eco_expand, seize_lane, strike_relay, siege, multipressure, hold_plateau, gate_control, survive_wilds, economy_disrupt.

## Membrane

```powershell
$env:PYTHONPATH = "$ws\tools;$env:UMWELT_SRC"   # UMWELT_SRC = <umwelt clone>\src
& python -m quantum_bar_ai.shell_character_membrane $ws
# -> outbox/shell_character_membrane.latest.json
```
