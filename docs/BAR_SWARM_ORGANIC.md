# BAR player-proxy ↔ yurt-swarm organic fill (node-agnostic)

**Audience:** Luke (read-only) + bots/seats (implementation).  
**Luke never runs CLI for this.** Pulse, cascade, Task Scheduler, cultivate, and detached loops own it.

---

## Law (v0.8.7 pathway + muscle)

| Do | Don't |
|----|-------|
| Run **player proxy** on any **free capable muscle** (wargen, roc, …) | Hard-code “must be wargen” |
| Publish free/capability faces every tick | Let hive/oa2it77 execute BAR units |
| Hose residual with **`ran_on`** | God-brain merge / densify |
| Keep human seal freeable=false | Bot-clear `pkt-bar-playtest-s6-retune` |

**Player proxy** = quantum-BAR-AI in the **player seat** (fair room + story engine) vs simple/barb styles — not human PLAY.

---

## For Luke (what exists / what to glance at)

When **some** muscle machine has spare CPU (and GPU is not pegged), the swarm automatically:

1. Publishes `muscle/<node>_player_proxy.json` + mesh auction  
2. Seeds freeable packet `pkt-bar-proxy-ul-idle` (`kind=player_proxy`, muscle-claim only)  
3. Runs a proxy unit on a **free capable** node  
4. Trains `bar_brain` + UniversalLearner (`width_action+eco_action`) on **every** mission  
5. Hoses residual (`ran_on` tagged) + harvests **campaign fruit**  
6. Curriculum slots (C0–C4) + adaptive difficulty on open CPU  
7. **Rests** when spring is up, proxy already running, CPU hot, or this seat is orchestration-only  

**Not densify. Not spring required. Not a god-brain merge.**

### Faces (read if curious; bots write them)

| Face | Meaning |
|------|---------|
| `yurt-sync/commons/vitals/muscle/wargen_player_proxy.json` | Wargen free/capable |
| `yurt-sync/commons/vitals/muscle/roc_player_proxy.json` | Roc free/capable (stub until live) |
| `yurt-sync/commons/vitals/player_proxy_mesh.json` | auction: who is free now |
| `yurt-sync/commons/vitals/bar_swarm_organ.json` | last probe / rest / unit |
| `yurt-sync/commons/vitals/bar_proxy_residual.latest.json` | residual hose (`ran_on`) |
| `yurt-sync/commons/vitals/bar_swarm_tape.jsonl` | event tape |
| `BAR…/outbox/proxy_campaign.latest.json` | latest A/B summary |
| `BAR…/app/brain/bar_brain_ul_state.json` | UL purity / updates |

### What you do

**Nothing** for farms. Play real BAR with `PLAY.bat` when you want.  
Human seal `pkt-bar-playtest-s6-retune` waits on **your** playtest scorecard — bots do not fake that seal.

---

## Bot ownership map

| Bot surface | Role |
|-------------|------|
| `player_proxy_muscle` | capability faces + claim gate + mesh auction |
| `bar_swarm_bridge` | seed / tick / loop on free capable muscle |
| `superconduct_pulse` free FLOPs | seed + tick every pulse |
| `cascade_fungus.crawl` | seed; tick if claim ok |
| AFK cultivate loop | seed/tick when freeable thin |
| Task `Wargen-BarSwarmOrganic` | ~15 min tick (muscle local) |
| `launch_bar_swarm_detached.ps1` | multi-hour loop (bot-launched) |
| Packet `pkt-bar-proxy-ul-idle` | freeable mechanical waist food |

### Resource gate (per muscle node)

CPU ≤ 55% · mem ≤ 90% · GPU ≤ 70% (if present) · no spring.exe · ≤1 concurrent proxy  
**Plus:** `can_run_player_proxy` (workspace present, not orchestration-only)

Busy / wrong seat → rest; packet stays open for a free muscle.

### Code paths (bots only)

- `yurt-sync/work/_wargen/coral/player_proxy_muscle.py`
- `yurt-sync/work/_wargen/coral/bar_swarm_bridge.py`
- `tools/bar_swarm_unit_v1.py`
- `tools/hive_bar_residual_v1.py` (`ran_on`, `kind=player_proxy`)

### Roc (and future muscle)

Eligible in principle when that host publishes a **live** muscle face with workspace + free=true.  
Until then face is a stub (`stub_awaiting_live_muscle`). Bridge jobs optional; local worker loop preferred.

Seats may re-arm loops if dead. **Do not hand Luke a command list.**
