# Outbound 40 — Cloud BAR compute for living-shell bakes

**Date:** 2026-07-27  
**Status:** Pipeline shipped — host path is **AWS** (see [41](41_AWS_CLOUD_SETUP.md)); yurt node `aws` stands in for Roc CPU work  
**Supersedes (for Phase B sim locus):** local-only `bake_living_shell.ps1` overnight  
**Extends:** [37](37_LIVING_SHELL_TEMPLATES.md), [39](39_SEVEN_MAP_GROW_RATES.md)  
**Next:** [41_AWS_CLOUD_SETUP.md](41_AWS_CLOUD_SETUP.md)

---

## Why cloud now

Local Windows headless **arms** the bake gadget (`VA_SHELL_BAKE_ARMED`) but often **stalls at IconsAtlas ~f=30**, so real strip dumps never land. Placeholders + BARb rate mixes are campaign-usable; **true AI-grown shells** need reliable multi-hour sims.

Cloud compute:

1. Frees the local play/dev machine.
2. Lets us run **all seven maps** with distinct grow rates without babysitting.
3. Keeps the same recipe/strip/membrane contract — only the **engine locus** moves.

---

## Architecture

```
LOCAL (author + strip + campaign)
  data/base_templates/*/bake_recipe.json
  grow_profiles.json  (SimpleAI sprawl / BARb easy|medium|hard|hard_aggressive)
  scripts/cloud/New-CloudBakeBundle.ps1   → startscripts + queue
  scripts/cloud/Sync-CloudBarRuntime.ps1  → engine + 7 maps + BAR.sdd + mod
  scripts/cloud/Invoke-CloudShellBake.ps1 → SSH run + harvest + apply_shell_strip
  tools/.../shell_character_membrane.py  → umwelt pack after harvest

CLOUD (Windows VM + OpenSSH)  [PRIMARY]
  bar_data/engine/recoil_*/spring-headless.exe
  bar_data/maps/<seven>.sd7
  bar_data/games/BAR.sdd + VerdanceAshes.sdd
  scripts/remote_worker_bake.ps1
  → infolog VA_SHELL_UNIT lines → scp home → living_shell_v1.json

CLOUD (Linux)  [OPTIONAL]
  Needs native Recoil spring-headless + content
  scripts/cloud/remote_worker_bake.sh
```

**Primary path = Windows cloud VM** so `spring-headless.exe` + BARb DLLs match local parity. Linux is secondary (native engine required).

---

## What syncs (size budget)

| Asset | ~Size | Frequency |
|-------|-------|-----------|
| Engine `recoil_2025.06.24` | ~95 MB | once / engine bump |
| Seven campaign maps | ~640 MB | once / map version |
| `BAR.sdd` | ~3.2 GB | once / game bump |
| `VerdanceAshes.sdd` | &lt;1 MB | every bake (gadgets) |
| Job startscripts | tiny | every bake |

Not synced: full 196-map catalog, music, screenshots, local campaign state.

---

## Operator steps

### 1. Provision a Windows cloud box

Recommended minimal:

- **Azure** Windows Server 2022 / Win11, 4–8 vCPU, 16 GB RAM, ~40 GB free disk  
- **AWS** Windows `t3.xlarge` / `c6i.xlarge` spot also fine  
- **Hetzner** / any VPS only if **Windows** is available for primary path

On the VM:

1. Enable **OpenSSH Server** (optional Features → OpenSSH Server).
2. Add your public key to `C:\ProgramData\ssh\administrators_authorized_keys` (Admin) or user `.ssh\authorized_keys`.
3. Open inbound TCP **22**.
4. PowerShell remoting not required — plain `ssh` + `scp` only.

### 2. Local config

```powershell
cd $ws
copy data\cloud\cloud_config.template.json data\cloud\cloud_config.json
# edit host, user, privateKeyPath, remoteRoot
```

### 3. Package (works offline — no host needed)

```powershell
powershell -File scripts/cloud/New-CloudBakeBundle.ps1
# or shortest first smoke:
powershell -File scripts/cloud/New-CloudBakeBundle.ps1 -MapIds the_rock_jungle
```

### 4. Full cloud bake (sync + run all + harvest + strip)

```powershell
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -RefreshMembrane
```

Smoke one map after sync:

```powershell
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -MapIds the_rock_jungle -SkipSync
```

Harvest-only if remote already finished:

```powershell
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -HarvestOnly -BundleName shell_bake_cloud_YYYYMMDD_HHMMSS
```

---

## Headless contract (unchanged)

```
spring-headless.exe --write-dir <barDataRoot> --isolation --only-local <startscript>
cwd = barDataRoot
modoptions: va_shell_bake=1, va_shell_bake_frames=N, va_shell_bake_mapid=...
settings: UnitIconsAsUI=0, LuaUI=0 (cloud worker patches)
living-shell gadget skips spawn when va_shell_bake
```

Wrong launch still loads stale My Games startscripts — cloud worker uses the same flags as local Phase B.

---

## Rate mixes stay on recipes

Cloud does **not** invent new AI names. Per-start `growProfile` from `bake_recipe.json` + `grow_profiles.json`:

| Profile | AI | After strip |
|---------|-----|-------------|
| sprawl / hold | SimpleAI | eco islands / rims |
| fortify_easy / fortify / fortify_hard | BARb | light → citadel teeth |
| scrap / thin | SimpleAI | Null foothold / glass |

Play with rates by editing recipes, re-package, re-submit cloud jobs. Membrane re-reads recipes + any new `living_shell_v1.json` counts.

---

## Umwelt / campaign compatibility

- Harvest writes `data/base_templates/<map>/living_shell_v1.json` (same schema as local bake).
- Compiler already prefers baked templates over placeholders.
- Membrane pack: `outbox/shell_character_membrane.latest.json`  
  - Fair rule unchanged: proxy only gets `fair_tags` + `raid_hint` + solution geometry.
- Cloud status packs:  
  - `outbox/cloud_bake_bundle.latest.json`  
  - `outbox/cloud_runtime_sync.latest.json`  
  - `outbox/cloud_bake_harvest.latest.json`

Learning baked into process: **sim locus = cloud**; authoring + strip + campaign stay local.

---

## Still local

| Task | Locus |
|------|--------|
| Playable campaign / headed play | Local BAR |
| **Headed GPU shell bake** (IconsAtlas unblock) | Local `spring.exe` — see below |
| Placeholder generation | Local |
| Strip filter apply | Local (after harvest) |
| Membrane / craft / story | Local |
| Phase C scars / D capture | Local (post-shell) |

---

## Local headed GPU path (no AWS seal)

When headless stalls at **IconsAtlas f≈30** (`atlasRendered=0`) and cloud host is not configured:

```powershell
# Shortest map first — real VA_SHELL_UNIT dump → living_shell_v1.json
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle

# Or all seven (babysit the window; gadget auto-quits after dump)
powershell -File scripts/bake_all_living_shells.ps1 -Headed

# Optional short smoke (still real engine units, thinner shell)
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle -GrowFrames 3600
```

Contract is identical to cloud: `va_shell_bake=1` gadget dumps → `apply_shell_strip.ps1` → `data/base_templates/<map>/living_shell_v1.json` with `source=bake`. AWS remains preferred for unattended multi-hour BARb grows.

---

## Success criteria

1. `the_rock_jungle` cloud bake produces `VA_SHELL_UNIT` lines (any density).  
2. All seven maps produce `living_shell_v1.json` with character-spread unit counts.  
3. `build_next_mission_v1.ps1` loads real shells for shell-capable kinds.  
4. Membrane pack reflects real unit densities where available.

---

## Commands cheat sheet

```powershell
# Offline package all seven
powershell -File scripts/cloud/New-CloudBakeBundle.ps1

# One-time runtime push (engine + maps + BAR.sdd + mod)
powershell -File scripts/cloud/Sync-CloudBarRuntime.ps1

# Full pipeline
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -RefreshMembrane

# Local headless (often IconsAtlas hang at f=30):
powershell -File scripts/bake_living_shell.ps1 -MapId the_rock_jungle

# Local headed GPU unblock (spring.exe):
powershell -File scripts/bake_living_shell_headed.ps1 -MapId the_rock_jungle
```
