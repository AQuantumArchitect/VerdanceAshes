"""The campaign lane: one story engine, split by seam.

- ``schema`` — Campaign state schema: constants, the crafted map pool, the default save and its migration, zone memory.
- ``zones`` — Zone id canonicalisation: legacy ids migrate onto the current zone maps.
- ``acts`` — Act structure (story pacing only, never a build lock) and the finale plans.
- ``progression`` — Reputation, companion mood and the XP/level ladders shared by roster and heroes.
- ``hydrology`` — Planet hydrology: one body of water shared by seven maps; waterlines, storms, tides and their beats.
- ``measure`` — Measurement: BAR telemetry collapses into zone memory; offscreen ticks, front decay, the player's regression arc, graph deltas and the spectral read of the battlefield.
- ``voice`` — Ketha's voice: deterministic, data-driven briefing, debrief and beat lines.
- ``roster`` — The hero roster arc: cadre XP, recruitment beats, act rewards, the commander and the roster half of the intent.
- ``commerce`` — Commerce: the catalogue, army budget, purchases, deliveries, faction banks, and settling the shop after a sortie.
- ``home`` — The Rock Jungle home camp: clearing it, building in it.
- ``living_shell`` — The living shell: scars, the player's footprint, surviving installs and abstract regrowth between sorties.
- ``objectives`` — Objectives, the front summary, the war map and where the next sortie lands.
- ``sorties`` — Sortie orders: the hub stamp, the opening sortie, Mode A quests, the escalation plan.
- ``intent`` — Intent dressing: landable zones and pads, enemy scale, economy, difficulty presentation and story events.
- ``engine`` — The story engine proper: ``process_result`` folds a sortie into the campaign, ``materialize_next_intent`` writes what the next Drop carries, and the CLI (``init-state`` / ``intent`` / ``advance``).

Every public name of every module is re-exported here, so callers and tests keep
``from verdance.campaign import process_result`` (and the ``tools/verdance/campaign/engine.py`` shim keeps
``import verdance_story_engine_v1 as engine``).
"""
from __future__ import annotations

from verdance.common import canonical_map_id, clamp, load_json, save_json, utc_now  # noqa: F401

from .schema import *  # noqa: F401,F403
from .zones import *  # noqa: F401,F403
from .acts import *  # noqa: F401,F403
from .progression import *  # noqa: F401,F403
from .hydrology import *  # noqa: F401,F403
from .measure import *  # noqa: F401,F403
from .voice import *  # noqa: F401,F403
from .roster import *  # noqa: F401,F403
from .commerce import *  # noqa: F401,F403
from .home import *  # noqa: F401,F403
from .living_shell import *  # noqa: F401,F403
from .objectives import *  # noqa: F401,F403
from .sorties import *  # noqa: F401,F403
from .intent import *  # noqa: F401,F403
from .engine import *  # noqa: F401,F403
from .engine import main  # noqa: F401
