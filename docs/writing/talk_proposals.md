# Camp talks: proposals for the writing pass (2026-11-09)

These are proposals, not changes. The talk data hasn't been edited, apart from removing the role ids (below). Accept, edit or reject them; once a pair's lines are settled, they go in that pair's `*_bonds.json` and `tools/author_bonds_v1.py` merges them.

## What makes the generated talks read cluttered

- **One middle for 60 talks.** These four beats appear, word for word, in 60 rank-A and rank-B talks:
  > Still hearing you in the kit after the Drop. / Then keep hearing it. The ash does not edit us clean. / If the next wall takes one of us, the other finishes the work. / That's not a promise. That's logistics.

  After the second pair, a player knows the talk before reading it, so the talk says nothing about the two people in it.
- **The close is mechanical.** "Support locks. X and Y leave the hearth different." reads like a game message, not a scene.
- **Narration carries 43% of all talk words** (`talk_audit.md`). The voices are short and good ("Pack is one thought." "Wrecks are unfinished sentences."); the narration around them is what reads heavy.
- **Fixed already:** 93 narrator lines opened with internal role ids ("core_skirm seat beside core_rez."). They're gone (9319cf9).

## Three drafts

Each keeps the pair's own opening (their hooks) and replaces the shared middle and the mechanical close with lines only these two could say.

### `ketha__vane:A` Pack memory (bond)

| Now | Proposed |
|---|---|
| *Captain and unfinished sentences. Ash-Captain Vane keeps the quiet. Ketha fills it.* | *Vane keeps the quiet. Ketha fills it.* |
| **Vane** Pack is one thought. | **Vane** Pack is one thought. |
| **Ketha** Wrecks are unfinished sentences. | **Ketha** Wrecks are unfinished sentences. |
| *core_skirm seat beside core_rez. You two keep finding the same fire.* | **Vane** If I go down mid-stride, don't finish it for me. Raise me and let me. |
| **Vane** Still hearing you in the kit after the Drop. | **Ketha** I raise what I can carry. You, I'd carry twice. |
| **Ketha** Then keep hearing it. The ash does not edit us clean. | *Neither says more. The fire does the rest.* |
| **Vane** If the next wall takes one of us, the other finishes the work. | |
| **Ketha** That's not a promise. That's logistics. | |
| *Support locks. Ash-Captain Vane and Ketha leave the hearth different.* | |

Before: 82 words. Proposed: 46.

### `quill__vane:A` Who gives the order (tension)

| Now | Proposed |
|---|---|
| *Flock captain vs tread marshal. The room gets smaller when both of you stand in it.* | *The room gets smaller with both of them in it.* |
| **Vane** Pack is one thought. | **Vane** Pack is one thought. |
| **Quill** Orders walk on treads. | **Quill** Orders walk on treads. |
| (the shared middle) | **Quill** Your pack breaks my line every time it runs. |
| | **Vane** Your line stands still while mine dies in front of it. |
| | **Quill** Then call it before you run, and I'll move the treads. |
| *Support locks. …* | *Not friends. Not easy. Better.* |

### `grath__nox:A` Two debts (mirror)

| Now | Proposed |
|---|---|
| *Wages and weather arrears. Same ledger, different ink.* | *Same ledger, different ink.* |
| **Grath** Three wars unpaid. | **Grath** Three wars unpaid. |
| **Nox** Still paying for the last sky. | **Nox** Still paying for the last sky. |
| (the shared middle) | **Grath** Who holds your note? |
| | **Nox** Whoever's left. Same as yours. |
| | **Grath** Then we stand where the collector has to come through both of us. |
| *Support locks. …* | *Neither debt feels lighter. Both feel answered.* |

## The 60 talks with the shared middle

`anvil__auditor:B`, `anvil__brakhov:A`, `anvil__brakhov:B`, `anvil__volt:B`, `anvil__yeva:B`, `auditor__halq:B`, `auditor__odessa:B`, `auditor__rusk:B`, `brakhov__fatboy:B`, `brakhov__hearth:B`, `brakhov__vale:A`, `bro__fatboy:B`, `bro__hearth:B`, `bro__volt:B`, `commando__nox:B`, `fatboy__hearth:B`, `fatboy__lumen:B`, `grath__nox:A`, `grath__nox:B`, `grath__spoke:B`, `grath__veil:B`, `grath__yeva:B`, `halq__kit:B`, `halq__spoke:B`, `halq__veil:B`, `halq__yeva:B`, `hearth__lumen:A`, `hearth__lumen:B`, `hearth__odessa:B`, `infestor__volt:B`, `ketha__vane:A`, `kettle__mira:A`, `kettle__mira:B`, `kit__mira:A`, `kit__mira:B`, `kit__quill:B`, `kit__twitch:B`, `lumen__noctua:B`, `lumen__spoke:B`, `lumen__tick:B`, `mira__twitch:B`, `noctua__solarium:B`, `nox__spoke:B`, `nox__vale:B`, `nox__veil:B`, `odessa__rusk:B`, `odessa__vane:B`, `odessa__yeva:B`, `quill__stride:B`, `quill__vane:A`, `quill__vane:B`, `quill__verse:B`, `rusk__vane:B`, `rusk__yeva:B`, `solarium__tick:B`, `spoke__tick:B`, `twitch__vale:B`, `twitch__veil:B`, `veil__volt:A`, `veil__volt:B`

A suggested order: start with the pairs players meet first (Ketha and Vane, Quill and Vane, Rusk and Vane, Odessa and Vane), then the rest by how often their heroes drop together.
