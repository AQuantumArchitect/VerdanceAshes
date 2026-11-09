# Dev log: toward 0.16

One entry per working day: what changed, what was measured, what's next. The newest entry comes first. Run folders live under `autopilot_runs\` on the dev PC (fenrir); they're not in git.

## 2026-11-09: the hard-AI baseline

**Run:** `scripts\test\campaign_hard.bat` (BARb hard_aggressive, stock BAR, speed 10, beats on), `autopilot_runs\20261109_001446`. It ran on 0cfc556, so it predates the drop-limit rule of 1be6f78. It's a baseline for the proxy player, not for the drop limit.

**Outcome:** the campaign completed in 11 sorties and 2 h 20 min wall time, finishing with the Overthrow (finale A) won. That reads like a pass, but it isn't one.

| # | Map | Job | Verdict | Wall | Heroes home |
|---|---|---|---|---|---|
| 1 | Greenest Fields | seize lane (raid) | victory | 155 s | Verse, Halbard |
| 2 | Greenest Fields | take the Koom door | victory | 107 s | Verse, Halbard |
| 3 | Rock Jungle | fortify (founding) | **wiped** | 138 s | — |
| 4 | Koom Valley | road | partial | 178 s | — |
| 5 | Rock Jungle | door SE outer muster | **wiped** | 80 s | — |
| 6 | Rock Jungle | door NE rim | **wiped** | 62 s | — |
| 7 | Rock Jungle | door NE rim | victory (contested) | 209 s | Verse |
| 8 | Rock Jungle | door SE outer muster | **wiped** | 83 s | — |
| 9 | Rock Jungle | door SE outer muster | **wiped** | 65 s | — |
| 10 | Rock Jungle | door SE outer muster | **wiped** | 95 s | — |
| 11 | Ancient Bastion | the Overthrow | victory | 154 s | Verse |

**What it shows**

1. **The proxy throws heroes away.** By the end, 20 named heroes were dead. That includes Vane (sortie 1), Halbard (sortie 3), Ketha (almost every sortie; she keeps coming back) and every field recruit the company raised. Verse alone carried the finale, which went to the finale kit. BARb treats heroes as units. This is the first job for the proxy player: keep named heroes alive (pull back early, resurrect the fallen).
2. **The Rock Jungle is a death spiral.** Six wipes in seven visits, all on the same two door jobs. Two things feed it:
   - **The raptor pace climbs with every visit, won or lost.** Grace went from 600 s to 430, 308, 158, 113 and 81, and the raptors' head start from 0 to 950 s. A company that keeps failing at home keeps making home harder.
   - **The pull home never lets go.** The bag held 11 Tenebrium through the whole spiral, and a wipe doesn't spend it, so the pull curve sent the company home again and again. The "defeat raises the stock a visit wants" rule (f51e375) didn't break the loop.
   Both need an owner call: is home supposed to get harder per visit, or per time the raptors have had to grow?
3. **The finale is easy for a hollow company.** The Overthrow fell in 154 s to Verse and the finale kit.
4. **The reserve did fill:** 27 units at the end (6 Legion constructors, 7 Rezbots, 5 Javelins and others). The wallet ended at 24k metal and 11 Tenebrium.

**Next**
- Proxy player, hero caution: named heroes retreat toward the pad at low health or under a heavy threat, and a Rezbot or Ketha goes for a fallen hero's wreck. Measure it as hero deaths per sortie against this run (20 dead in 11 sorties).
- Proxy player, extraction: get the built army onto the pad before extracting.
- Owner call on the Rock Jungle spiral (visit-based escalation, a pull that ignores wipes).
