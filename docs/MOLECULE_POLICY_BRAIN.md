# Molecule as Policy Brain Space

**Status:** Stages **0–4 shipped**. Soft merge **default on** (kept live for v0.12.0). Rollback: `va_molecule_policy=off`.  
**Role in recalibration:** **combat temperament lens only** — not world SSOT. Mainline: [`GRAPH_COLLAPSE_SSOT.md`](GRAPH_COLLAPSE_SSOT.md) (Phases 0–4 done). Stages **5–9 frozen**.  
**SSOT molecules:** `data/story/hero_umwelt.json`  
**Hand doctrine (cache/override):** `data/story/hero_codex.json` → `va_hero_doctrine.lua` + `va_intent_resolver.lua` `DOCTRINE`  
**φ features:** `data/story/phi_features.json` · `tools/phi_projector_v1.py` · Lua stub `va_phi_projector.lua` (**not** think-wired)  
**D(u):** `tools/molecule_doctrine_v1.py apply --shadow` → JSON face + `va_molecule_doctrine.lua`  
**Policy:** `va_molecule_policy.lua` · wired in `game_verdance_unit_behavior.lua`  
**Shadow resolver:** `tools/shadow_intent_v1.py` → `outbox/shadow_intent.latest.json`  
**Seal:** `docs/MOLECULE_POLICY_SCORECARD.md`

---

## North star

The hero **umwelt molecule** \(u_h \in \mathbb{R}^{10}\) is the shared **policy temperament space**. A hero’s vector vaguely describes battlefield behavior as an eigen-temperament in that basis. **BeliefField** stays situational evidence. **IntentResolver** stays the decoder. Relationships (FE web) soft-augment the decoder — they do not densify a second god-brain.

### Law (every stage)

- Dark banner > silent fake-live
- η / human seal sacred before combat feel retune
- Soft bias only until an explicit stage unlock
- Do **not** replace BeliefField or player orders with cognifold/LLM
- Hand voice (Vane↔Ketha, Warder↔Commando, Knock cadence) stays sacred overrides

### Already shipped (do not rebuild)

- L0 molecules · L1 support web + spot-meets-siege cultivation · L2 mapPressure · L3 observe tape
- Authored hearth talks · `support_ai_augments.json` wishlist
- Codex · doctrine profiles · BeliefField · IntentResolver

---

## Architecture (target)

```
u_h     molecule (SSOT)           temperament / care axes          SLOW
D(u_h)  doctrine readout          kiteBias, pushBias, allow*       DERIVED
m_z     mapPressure               theater in same 10 axes          SLOW
b_t     BeliefField leaves        orders, threat, pain, craft…     FAST + η
φ_t     world features→10 axes    sparse projector                 FAST
A(bond) FE augments               knock dodge, mark bias, …        GATED
        ↓
score(intent) ≈ ⟨u_h, φ_t⟩ · g(b_t,η) · D(u_h) · A(pairBonds)
        ↓
IntentResolver (decoder) → bail | kite | craft | push | hold
```

Eco rhyme: `fit(h,z)=⟨u_h,m_z⟩` ranks aces for theaters; `⟨u_h,φ_t⟩` colors tick intent.

### Ten axes (shared basis)

`energy · offense · mobility · sight · pad · craft · heat · fog · sky · ledger`

### `D(u)` mapping (Stage 1 shadow)

| Molecule cue | Doctrine readout |
|--------------|------------------|
| `+mobility −pad` | ↑`kiteBias`, ↓`preferDefenses` |
| `+pad −mobility` | ↓`kiteBias`, ↑hold / `preferDefenses` |
| `+offense +heat −energy` | ↑`pushBias`, kiln-ish gates |
| `+craft +energy` | ↑`craftBias` |
| `+sight +fog` | scout/mark bias flags (**data only** until Stage 5) |
| Codex hard gates | `allowBail` / `allowKite` / Kiln no-bail stay overrides |

Hand doctrine becomes a **cache/override**, not a second brain. Shadow never flips live combat.

### Stage 2 — φ projector (shipped shadow)

```bash
python tools/phi_projector_v1.py features
python tools/phi_projector_v1.py fit --map eye_of_horus --cue heat_ash --cue statics_nearby
python tools/phi_projector_v1.py face --map eye_of_horus --cue heat_ash
python tools/phi_projector_v1.py smoke
```

`fit(h,φ)=⟨u_h,φ_t⟩` ranks who “pays” on this tick’s theater cues (+ optional mapPressure blend).

### Stage 3 — shadow IntentResolver (shipped parallel brain)

```bash
python tools/shadow_intent_v1.py run
python tools/shadow_intent_v1.py smoke
```

Formula: `score(intent) ≈ ⟨u,φ⟩ · g(b,η) · D(u)` with `A=1`. Compares to Python port of live `Intent.resolve` under hand doctrine. Seal card: `docs/MOLECULE_POLICY_SCORECARD.md`.

### Stage 4 — soft live merge (opt-in)

| Mode | Effect |
|------|--------|
| `soft` (**default**) | Blend biases toward `D(u)` at α≈0.28; **hard gates stay hand** (Kiln no-bail) |
| `shadow` | Live = hand; stamps `va_shadow_intent` under soft blend for compare |
| `off` | Hand doctrine only — no molecule blend |

Set via modoption `va_molecule_policy` or GameRulesParam of the same name (rules param wins).  
Play path: `Documents\My Games\VerdanceAshes\PLAY.bat` (BAR games junctions to that mod).  
Regen D(u) cache after molecule edits: `python tools/molecule_doctrine_v1.py apply --shadow` then redeploy mod.  
Rollback: `va_molecule_policy=off`. BeliefField + player orders untouched.

Cartoonish umwelt disagreements are **feature, not bug** — they are how character shows up in micro.

---

## Stage gate summary

| Stage | Name | Live combat? | Unlock condition |
|------:|------|:------------:|------------------|
| 0 | Freeze & faces | No | Always |
| 1 | D(u) shadow | No | Stage 0 done |
| 2 | φ projector shadow | No | Stage 1 sane |
| 3 | Shadow resolver | No | Stage 2 logging |
| 4 | Soft live merge | **Soft** | Human seal on Stage 3 |
| 5a | Knock cadence | **One augment** | Stage 4 stable or parallel soft-only flag |
| 5b–d | More augments | Gated | 5a sealed |
| 6 | Talk templates | No (hub) | Anytime after 0; parallel |
| 7 | Company cognifold | No (hub) | After 1–2; parallel OK |
| 8 | Tensor | No (hub) | Observe volume |
| 9 | Eigen / disposition | Soft | Stage 8 + seals |

**This slice:** Stages 0–4. Soft is opt-in. Next unlock when wanted: Stage 5a Knock cadence (still gated).

---

## Doctrine vs molecule (Stage 0 snapshot)

Hand knobs = IntentResolver profile for codex `doctrine` kind, with per-hero `preferDefenses` / `allowBail` / `allowKite` / `verb` from codex.  
Naive `D(u)` = molecule readout **without** sacred gates.  
Gated `D(u)` = naive + codex hard gates (what Stage 4 soft-merge would respect).

Regenerate the live table anytime:

```bash
python tools/molecule_doctrine_v1.py table
python tools/molecule_doctrine_v1.py apply --shadow
python tools/molecule_doctrine_v1.py diff
```

### Sanity pins (expect after Stage 1)

| Hero | Hand story | Molecule should imply |
|------|------------|------------------------|
| **Brakhov (Kiln)** | no bail, no kite, high push, preferDefenses | `+heat +off −ene −mob` → kilnish gates preserved |
| **Mira (arty)** | kite, soft push, preferDefenses | `+heat +off` with kite room → **artyish**, not kiln |
| **Vane (Phobos)** | high kite, flock | `+mob −pad +off` → high kiteBias |
| **Hearth** | hold, no kite, low push | `+ene −mob +pad −off` → low kite/push, craft up |
| **Phobos pack / skirm** | kite-forward | mobility-led readout |
| **Warder / Anvil** | pad / plod | pad-led, preferDefenses |

Full per-hero hand vs derived vs delta: `outbox/molecule_doctrine_shadow.json`.

### Honest disagreements to glance (not bugs)

Largest |hand − D(u)| after Stage 1 smoke: **line pad-plods** (Cauter/Quill/Anvil/Rusk/Odessa — molecule wants less kite / more preferDefenses than hand line profile), **Vale fog_siege** (molecule still push-heavy vs hand soft-push), **constructor/hivish** (Solarium/Lumen bail clamp). These are the cache/override candidates for Stage 4 soft-merge — do not retune combat from them yet.

---

## Explicit non-goals

- Replacing BeliefField with molecule argmax
- LLM planner / densified cognifold god-brain
- Auto-demoting sacred hand talks
- Shipping umweltd / SpaceWheat engine inside Steam G0 depot
- Multi-augment combat flip in one PR
- `--live` doctrine apply (not until Stage 4 seal)

---

## Pointers

- Layer cake / observe / tensor: `docs/HERO_GRAPH_UMWELT_FOUNDATION.md`
- Molecules: `docs/HERO_UMWELT.md`
- Support web + FE augments wishlist: `docs/SUPPORT_WEB.md`
- Cognifold / dual-gym pathway: `docs/UMWELT_GYM_PATHWAY.md`
- Observe smoke: `python tools/hero_observe_v1.py smoke`
- Map fit: `python tools/map_umwelt_v1.py fit --map eye_of_horus`
