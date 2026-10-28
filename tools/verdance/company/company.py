"""Company preamble + field pool (Fire Emblem loop).

Fresh run: pick 3 band packs from the unlock pool → seal company.
Unpicked heroes go into fieldPool (wild) for mid-run wreck/rez or sortie joins.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from verdance.common import WORKSPACE_ROOT, utc_now

# Default homes for wild heroes (must match authored zone_map ids).
# Spread pads — never pile every missing catalog hero onto GF_C_GATE.
DEFAULT_HOMES: Dict[str, List[str]] = {
    "rumor": ["ancient_bastion", "AB_NE_CRATERS"],
    "mask": ["greenest_fields", "GF_SE_PLATEAU"],
    "gale": ["tabula", "T_C_SPILLWAY"],
    "mason": ["ancient_bastion", "AB_NW_TOR"],
    "loom": ["tabula", "T_NE_CAUSEWAY"],
    "hundred": ["tabula", "T_E_CAUSEWAY"],
    "gorgon": ["koom_valley", "KV_E_LOWER_LANE"],
    "rookery": ["koom_valley", "KV_NE_SPILLWAY"],
    "dam": ["the_rock_jungle", "TRJ_NE_SHALLOWS"],
    "arc": ["ancient_bastion", "AB_SE_HEIGHTS"],
    "mammoth": ["eye_of_horus", "EOH_SE_MUSTER"],
    "gladius": ["koom_valley", "KV_W_UPPER_LANE"],
    "triton": ["tabula", "T_SW_CAUSEWAY"],
    "starlight": ["ancient_bastion", "AB_E_RIDGE"],
    "banisher": ["koom_valley", "KV_E_UPPER_LANE"],
    "arrow": ["tabula", "T_NW_RESERVE"],
    "hornet": ["all_that_simmers", "ATS_SW_PLATEAU"],
    "charybdis": ["eye_of_horus", "EOH_SW_CAUSEWAY"],
    "shiva": ["koom_valley", "KV_W_OUTER_LANE"],
    "tremor": ["ancient_bastion", "AB_C_WALL"],
    "stiletto": ["the_rock_jungle", "TRJ_NE_RIM"],
    "lunkhead": ["eye_of_horus", "EOH_C_INNER_GATE"],
    "stronghold": ["all_that_simmers", "ATS_NE_OUTER_PLATEAU"],
    "possum": ["tabula", "T_SE_RESERVE"],
    "phoenix": ["eye_of_horus", "EOH_NW_BASTION"],
    "scylla": ["the_rock_jungle", "TRJ_SW_SHALLOWS"],
    "tsunami": ["all_that_simmers", "ATS_NW_SHORE"],
    "thresh": ["all_that_simmers", "ATS_NE_PLATEAU"],
    "rusk": ["koom_valley", "KV_W_LANE"],
    "verse": ["the_rock_jungle", "TRJ_SE_GATE"],
    "odessa": ["greenest_fields", "GF_C_GATE"],
    "brakhov": ["ancient_bastion", "AB_W_KEEP"],
    "yeva": ["eye_of_horus", "EOH_E_LANE"],
    "cauter": ["greenest_fields", "GF_NW_BASTION"],
    "grath": ["koom_valley", "KV_E_LANE"],
    "halq": ["the_rock_jungle", "TRJ_SE_GATE"],
    "auditor": ["ancient_bastion", "AB_W_GATEHOUSES"],
    "twitch": ["eye_of_horus", "EOH_SE_BASTION"],
    "consul": ["the_rock_jungle", "TRJ_NW_GATE"],
    "spoke": ["greenest_fields", "GF_C_INNER_GATE"],
    "veil": ["the_rock_jungle", "TRJ_NW_GATE"],
    "commando": ["the_rock_jungle", "TRJ_SW_LANE"],
    "rascal": ["greenest_fields", "GF_SE_PLATEAU"],
    "tick": ["greenest_fields", "GF_SW_MUSTER"],
    "fatboy": ["greenest_fields", "GF_NE_PLATEAU"],
    "bro": ["eye_of_horus", "EOH_SE_BASTION"],
    "stride": ["koom_valley", "KV_W_LANE"],
    "mira": ["the_rock_jungle", "TRJ_C_SPILLWAY"],
    "kettle": ["greenest_fields", "GF_SW_BASTION"],
    "infestor": ["eye_of_horus", "EOH_E_LANE"],
    "quill": ["koom_valley", "KV_E_LANE"],
    "kit": ["the_rock_jungle", "TRJ_C_SPILLWAY"],
    "vale": ["ancient_bastion", "AB_NE_CRATERS"],
    "nox": ["greenest_fields", "GF_N_PLATEAU"],
    "lumen": ["greenest_fields", "GF_S_PLATEAU"],
    "anvil": ["greenest_fields", "GF_C_GATE"],
    "volt": ["koom_valley", "KV_W_LANE"],
    # Catalog fills that used to fall through to GF_C_GATE (haunted pile-up).
    "hearth": ["greenest_fields", "GF_NW_CITADEL"],
    "solarium": ["greenest_fields", "GF_SW_CITADEL"],
    "warder": ["the_rock_jungle", "TRJ_NW_MUSTER"],
    "noctua": ["the_rock_jungle", "TRJ_E_MUSTER"],
}

# Building / pad chassis that often fail Gaia CreateUnit+kill wreck seeds.
# Seed a mobile proxy corpse; keep real unitDef on the hero row for identity.
WRECK_SEED_PROXY: Dict[str, str] = {
    "armageo": "armck",
    "armfus": "armck",
    "armnanotc": "armck",
    "armestor": "armck",
    "armwin": "armck",
    "armsolar": "armck",
    "armmoho": "armck",
    "armmex": "armck",
    # Noctua Bay is legap (drone plant). Never proxy as legcen — that reads as Phobos.
    "legap": "legfig",
    "corfus": "corck",
    "corageo": "corck",
    "cormex": "corck",
    # Building heroes met in the field (2026-10-28): the bays, the cloaked fusion, the Bulwark.
    "armckfus": "armck",
    "armlab": "armck",
    "legvp": "legck",
    "cordoom": "corck",
}

CORE_DEFAULT = ["ketha"]
SEAT_CAP_DEFAULT = 3


def _workspace(ws: Optional[Path] = None) -> Path:
    if ws is not None:
        return Path(ws)
    return WORKSPACE_ROOT


def load_crew_packs(workspace: Optional[Path] = None) -> Dict[str, Any]:
    path = _workspace(workspace) / "data" / "story" / "crew_packs.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:  # noqa: BLE001
        return {}


PROFILE_REL = Path("state") / "profile.json"


def load_profile(workspace: Optional[Path] = None) -> Dict[str, Any]:
    """The player's record across campaigns (survives a campaign reset): heroes unlocked by rescue."""
    path = _workspace(workspace) / PROFILE_REL
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    except Exception:  # noqa: BLE001
        data = {}
    data.setdefault("unlocked", [])
    return data


def unlock_rescued_survivors(state: Dict[str, Any], workspace: Optional[Path] = None) -> List[str]:
    """At the end of a campaign: every hero rescued in the field (joined after the seal) who is
    still alive becomes a starting option for every campaign after this one."""
    company = state.get("company") or {}
    rescued = {str(h) for h in (company.get("joinedLater") or [])}
    field = state.get("fieldPool") or {}
    rescued |= {str(h) for h, e in field.items() if isinstance(e, dict) and str(e.get("status")) == "recruited"}
    alive = {str(h.get("heroId")) for h in ((state.get("roster") or {}).get("heroes") or [])
             if isinstance(h, dict) and str(h.get("status") or "") in ("active", "wounded")}
    # A hero rented for the drop that won the campaign, home alive, is kept (verdance.company.rentals).
    last = {str(h) for h in (company.get("rentedLastDrop") or [])}
    rescued |= last
    alive |= last
    new = sorted(rescued & alive)
    profile = load_profile(workspace)
    gained = [h for h in new if h not in profile["unlocked"]]
    if gained:
        from datetime import datetime, timezone
        profile["unlocked"] = sorted(set(profile["unlocked"]) | set(gained))
        profile.setdefault("history", []).append({"campaignId": state.get("campaignId"), "unlocked": gained,
                                                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        path = _workspace(workspace) / PROFILE_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return gained


def load_hero_roster_map(workspace: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    path = _workspace(workspace) / "data" / "story" / "hero_roster.json"
    out: Dict[str, Dict[str, Any]] = {}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        for h in data.get("heroes") or []:
            if isinstance(h, dict) and h.get("heroId"):
                out[str(h["heroId"])] = h
    except Exception:  # noqa: BLE001
        pass
    return out


def band_hero_ids(packs: Optional[Dict[str, Any]] = None) -> List[str]:
    packs = packs or {}
    heroes = packs.get("heroes") or {}
    ids = []
    for hid, row in heroes.items():
        if isinstance(row, dict) and str(row.get("role") or "") == "band":
            ids.append(str(hid))
    return ids


def core_hero_ids(packs: Optional[Dict[str, Any]] = None) -> List[str]:
    packs = packs or {}
    core = packs.get("core")
    if isinstance(core, list) and core:
        return [str(x) for x in core]
    return list(CORE_DEFAULT)


def hero_can_lead(hid: str, packs: Optional[Dict[str, Any]] = None) -> bool:
    """The first pick is you, and you walk: a hero on a building chassis (canLead: false) cannot lead."""
    packs = packs if packs is not None else load_crew_packs()
    pack = (packs.get("heroes") or {}).get(str(hid)) or {}
    return pack.get("canLead", True) is not False


def seat_cap(packs: Optional[Dict[str, Any]] = None) -> int:
    packs = packs or {}
    return int(packs.get("seatCap") or SEAT_CAP_DEFAULT)


def starter_unlock_ids(packs: Optional[Dict[str, Any]] = None, workspace: Optional[Path] = None) -> List[str]:
    """Who you may start a campaign with: the authored starters plus every hero this player has
    unlocked by rescuing them and bringing them through a campaign alive (state/profile.json)."""
    packs = packs if packs is not None else load_crew_packs(workspace)
    band = band_hero_ids(packs)
    raw = packs.get("starterUnlocks") or packs.get("starterUnlockPool") or []
    if not isinstance(raw, list):
        raw = []
    allowed = {str(x) for x in raw} | {str(x) for x in load_profile(workspace).get("unlocked") or []}
    return [h for h in band if h in allowed]


def unlock_pool_ids(state: Dict[str, Any], packs: Optional[Dict[str, Any]] = None) -> List[str]:
    """Who may appear on the preamble board."""
    packs = packs if packs is not None else load_crew_packs()
    band = band_hero_ids(packs)
    explicit = state.get("unlockPool")
    if isinstance(explicit, list) and explicit:
        if "*" in explicit or "all" in explicit:
            return band
        allowed = {str(x) for x in explicit}
        return [h for h in band if h in allowed]
    # Dev dump: full catalog on the hire board.
    if packs.get("playtestAllUnlocked", False):
        return band
    starter = starter_unlock_ids(packs)
    if starter:
        return starter
    # Conservative fallback: nothing unlocked yet (core still free)
    return []


def empty_company(packs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    packs = packs or {}
    return {
        "sealed": False,
        "core": core_hero_ids(packs),
        "band": [],
        "you": None,
        "joinedLater": [],
        "sealedAt": None,
        "seatCap": seat_cap(packs),
    }


def _hero_home(hid: str, state: Dict[str, Any], roster_row: Optional[Dict[str, Any]]) -> List[str]:
    # Prefer authored defaults (zone ids stay current). Legacy character.home
    # often still has RJ_/KOOM_ prefixes from older maps.
    if hid in DEFAULT_HOMES:
        return list(DEFAULT_HOMES[hid])
    if isinstance(roster_row, dict):
        recruit = roster_row.get("recruit") or {}
        if isinstance(recruit, dict) and recruit.get("mapId"):
            zone = recruit.get("zoneId")
            return [str(recruit["mapId"])] + ([str(zone)] if zone else [])
    chars = state.get("characters") or {}
    sheet = chars.get(hid) if isinstance(chars, dict) else None
    if isinstance(sheet, dict) and sheet.get("home"):
        home = sheet["home"]
        if isinstance(home, list) and home:
            return [str(x) for x in home]
        if isinstance(home, str) and home:
            return [home]
    return ["greenest_fields", "GF_C_GATE"]


def _recruit_spec(
    hid: str,
    roster_row: Optional[Dict[str, Any]],
    home: List[str],
    *,
    pack: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize toward field recruit; keep authored type when already field-ish."""
    base: Dict[str, Any] = {"type": "wreck_rez"}
    if isinstance(roster_row, dict) and isinstance(roster_row.get("recruit"), dict):
        authored = dict(roster_row["recruit"])
        kind = str(authored.get("type") or "")
        # Premium / slow-burn: keep sortie/map gates; convert calendar beats to wreck_rez.
        # Factory / builder heroes: capture or rez (stock BAR). retrieve_stash stays.
        if kind in (
            "wreck_rez",
            "sortie",
            "map_state",
            "objective_kind",
            "retrieve_stash",
            "capture",
        ):
            base = authored
        elif kind == "assist_fortify":
            # No special fortify join — convert via capture or rez like everyone else.
            base = {"type": "wreck_rez", "legacy": authored}
        elif kind in ("mission_victory", "rep", "act_reached"):
            # Soft migrate: wreck_rez on home map; keep old gate as hint for Phase 3.
            base = {
                "type": "wreck_rez",
                "legacy": authored,
            }
            # Auditor / kiln stay a bit special
            if hid in ("auditor", "brakhov"):
                base["type"] = "sortie"
                base["requiresVictory"] = True
    if isinstance(pack, dict) and pack.get("factory"):
        base.setdefault("factory", pack.get("factory"))
        if str(base.get("type") or "") == "assist_fortify":
            base["type"] = "wreck_rez"
    if home:
        base.setdefault("mapId", home[0])
        if len(home) > 1:
            base.setdefault("zoneId", home[1])
    return base


def build_field_entry(
    hid: str,
    state: Dict[str, Any],
    *,
    packs: Optional[Dict[str, Any]] = None,
    roster_map: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    packs = packs or load_crew_packs()
    roster_map = roster_map if roster_map is not None else load_hero_roster_map()
    row = roster_map.get(hid) or {}
    pack = (packs.get("heroes") or {}).get(hid) or {}
    home = _hero_home(hid, state, row if row else None)
    name = (
        (row.get("name") if isinstance(row, dict) else None)
        or pack.get("name")
        or hid
    )
    return {
        "heroId": hid,
        "name": name,
        "unitDef": pack.get("unitDef") or (row.get("unitDef") if isinstance(row, dict) else None) or "legcen",
        "status": "wild",
        "home": home,
        "recruit": _recruit_spec(hid, row if row else None, home, pack=pack if isinstance(pack, dict) else None),
    }


def ensure_company(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Ensure company + unlockPool + fieldPool scaffolding on campaign state."""
    packs = load_crew_packs(workspace)
    company = state.get("company")
    if not isinstance(company, dict):
        company = empty_company(packs)
        state["company"] = company
    else:
        company.setdefault("sealed", False)
        company.setdefault("core", core_hero_ids(packs))
        company.setdefault("band", [])
        company.setdefault("joinedLater", [])
        company.setdefault("sealedAt", None)
        company.setdefault("seatCap", seat_cap(packs))

    sealed_now = bool((state.get("company") or {}).get("sealed"))
    if packs.get("playtestAllUnlocked", False) and not sealed_now:
        # Playtest / early meta: every band pack is unlocked for the intro pick.
        state["unlockPool"] = ["*"]
    elif "unlockPool" not in state:
        state["unlockPool"] = starter_unlock_ids(packs)
    elif (
        not packs.get("playtestAllUnlocked", False)
        and isinstance(state.get("unlockPool"), list)
        and ("*" in state["unlockPool"] or "all" in state["unlockPool"])
        and not sealed_now
    ):
        # Fresh / unsealed runs should not inherit a playtest dump of every hero.
        state["unlockPool"] = starter_unlock_ids(packs)

    field = state.get("fieldPool")
    if not isinstance(field, dict):
        field = {}
        state["fieldPool"] = field

    # Mid-run legacy saves: already fighting without a preamble — infer a seal
    # from active roster heroes so Drop is not soft-locked.
    if not company.get("sealed"):
        hist = state.get("history") or []
        mission_n = int(state.get("missionNumber") or 1)
        mid_run = bool(hist) or mission_n > 1 or bool(state.get("lastResult"))
        if mid_run:
            _legacy_auto_seal(state, packs, workspace)

    # Catalog grew after seal: park brand-new band packs in the wild field pool.
    # Also scrub owned seats out of "wild" so the hub teasers stay honest.
    if company.get("sealed"):
        roster_map = load_hero_roster_map(workspace)
        owned = set(str(x) for x in (company.get("core") or []))
        owned.update(str(x) for x in (company.get("band") or []))
        owned.update(str(x) for x in (company.get("joinedLater") or []))
        owned.update(str(x) for x in (company.get("rented") or []))   # rented for this drop: theirs until homecoming
        for hid in list(field.keys()):
            if hid in owned and isinstance(field.get(hid), dict):
                if str(field[hid].get("status") or "") == "wild":
                    field[hid]["status"] = "recruited"
        for hid in band_hero_ids(packs):
            if hid in owned:
                continue
            if hid in field and isinstance(field.get(hid), dict):
                # Still wild: refresh home / recruit / chassis from catalog so
                # mission-join modes (assist_fortify, retrieve_stash) stick.
                if str(field[hid].get("status") or "") == "wild":
                    fresh = build_field_entry(hid, state, packs=packs, roster_map=roster_map)
                    for key in ("name", "unitDef", "home", "recruit"):
                        if key in fresh:
                            field[hid][key] = fresh[key]
                continue
            field[hid] = build_field_entry(hid, state, packs=packs, roster_map=roster_map)
            _set_roster_status(state, hid, "locked", player=False)
        state["fieldPool"] = field

    return state["company"]


def _legacy_auto_seal(
    state: Dict[str, Any],
    packs: Dict[str, Any],
    workspace: Optional[Path],
) -> None:
    """Best-effort seal for campaigns that predate company preamble."""
    core = core_hero_ids(packs)
    cap = seat_cap(packs)
    roster_map = load_hero_roster_map(workspace)
    active_band: List[str] = []
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if not isinstance(h, dict):
            continue
        hid = str(h.get("heroId") or "")
        if not hid or hid in core:
            continue
        if str(h.get("status") or "") != "active":
            continue
        pack = (packs.get("heroes") or {}).get(hid)
        if not isinstance(pack, dict) or str(pack.get("role")) != "band":
            continue
        active_band.append(hid)
    picks = active_band[:cap]
    # If somehow empty mid-run, leave unsealed (player must preamble).
    if not picks and not active_band:
        # Still seal core-only so Drop works; full field pool wild.
        picks = []
    company = state["company"]
    for hid in core:
        _set_roster_status(state, hid, "active", player=True)
    for hid in picks:
        _set_roster_status(state, hid, "active", player=True)
    field: Dict[str, Any] = {}
    for hid in band_hero_ids(packs):
        if hid in picks:
            continue
        field[hid] = build_field_entry(hid, state, packs=packs, roster_map=roster_map)
        if hid not in picks:
            # Keep already-active extras as joinedLater rather than wild.
            if hid in active_band[cap:]:
                continue
            _set_roster_status(state, hid, "locked", player=False)
    later = [h for h in active_band[cap:] if h not in picks]
    for hid in later:
        _set_roster_status(state, hid, "active", player=True)
        if hid in field:
            field[hid]["status"] = "recruited"
    company["sealed"] = True
    company["core"] = core
    company["band"] = picks
    if not company.get("you"):
        company["you"] = picks[0] if picks else None
    company["joinedLater"] = later
    company["sealedAt"] = company.get("sealedAt") or utc_now()
    company["legacyAutoSeal"] = True
    state["company"] = company
    state["fieldPool"] = field


def hero_status(state: Dict[str, Any], hid: str) -> str:
    """Roster status wins; characters sheet is the fallback."""
    hid = str(hid or "")
    if not hid:
        return "active"
    roster = (state.get("roster") or {}).get("heroes") or []
    for h in roster:
        if isinstance(h, dict) and str(h.get("heroId")) == hid:
            return str(h.get("status") or "active").lower()
    chars = state.get("characters") or {}
    sheet = chars.get(hid) if isinstance(chars, dict) else None
    if isinstance(sheet, dict):
        return str(sheet.get("status") or "active").lower()
    return "active"


def hero_is_deployable(state: Dict[str, Any], hid: str) -> bool:
    """Dead / lost heroes stay on the company roll but do not drop."""
    st = hero_status(state, hid)
    return st not in ("dead", "lost")


def company_deploy_band(state: Dict[str, Any]) -> List[str]:
    """Band seats for drop packet: living starting picks + mid-run joins.

    Fallen company members remain on company.band for the Fallen UI, but are
    excluded here so deploy scripts / confirmation only list who is dropping.
    """
    company = state.get("company") or {}
    if not company.get("sealed"):
        return []
    band = [str(x) for x in (company.get("band") or [])]
    later = [str(x) for x in (company.get("joinedLater") or [])]
    rented = [str(x) for x in (company.get("rented") or [])]     # verdance.company.rentals: this drop only
    seen = set()
    out: List[str] = []
    for hid in band + later + rented:
        if not hid or hid in seen:
            continue
        if not hero_is_deployable(state, hid):
            continue
        seen.add(hid)
        out.append(hid)
    return out


def company_deploy_aces(state: Dict[str, Any], packs: Optional[Dict[str, Any]] = None) -> List[str]:
    packs = packs or load_crew_packs()
    company = state.get("company") or {}
    core = [str(x) for x in (company.get("core") or core_hero_ids(packs))]
    living_core = [hid for hid in core if hero_is_deployable(state, hid)]
    return living_core + company_deploy_band(state)


def sortie_roster(
    state: Dict[str, Any],
    requested_band: Optional[List[str]] = None,
    packs: Optional[Dict[str, Any]] = None,
) -> tuple:
    """Who this Drop actually ships.

    Core always comes. ``requested_band`` is the hub Dropping list (non-core).
    None means every living pack in the company. An empty list means core only.
    Ids that are not in the sealed living company are ignored.
    """
    packs = packs or load_crew_packs()
    company = state.get("company") or {}
    core = [str(x) for x in (company.get("core") or core_hero_ids(packs))]
    living_core = [hid for hid in core if hid and hero_is_deployable(state, hid)]
    allowed = company_deploy_band(state)
    allowed_set = set(allowed)
    core_set = set(living_core)
    if requested_band is None:
        band = list(allowed)
    else:
        band = []
        seen = set()
        for raw in requested_band:
            hid = str(raw or "")
            if not hid or hid in seen or hid in core_set:
                continue
            if hid not in allowed_set:
                continue
            seen.add(hid)
            band.append(hid)
    return band, living_core + band


def _set_roster_status(state: Dict[str, Any], hid: str, status: str, *, player: Optional[bool] = None) -> None:
    roster = state.setdefault("roster", {})
    heroes = roster.setdefault("heroes", [])
    found = None
    for h in heroes:
        if isinstance(h, dict) and str(h.get("heroId")) == hid:
            found = h
            break
    packs = load_crew_packs()
    pack = (packs.get("heroes") or {}).get(hid) or {}
    roster_map = load_hero_roster_map()
    row = roster_map.get(hid) or {}
    name = (row.get("name") if row else None) or pack.get("name") or hid
    unit_def = pack.get("unitDef") or (row.get("unitDef") if row else None) or "legcen"
    if found is None:
        found = {
            "heroId": hid,
            "name": name,
            "unitDef": unit_def,
            "missionCritical": bool(pack.get("missionCritical") or (row.get("missionCritical") if row else False)),
            "status": status,
            "xp": float((row.get("xp") if row else 0) or 0.0),
            "timesWounded": 0,
            "campaignXp": 0.0,
        }
        heroes.append(found)
    else:
        found["status"] = status
        found.setdefault("name", name)
        found.setdefault("unitDef", unit_def)
    if player is not None:
        found["player"] = bool(player)
    elif status == "active":
        found["player"] = True
    elif status == "locked":
        found["player"] = False

    chars = state.setdefault("characters", {})
    sheet = chars.get(hid)
    if not isinstance(sheet, dict):
        sheet = {
            "id": hid,
            "name": name,
            "faction": "ashwalkers",
            "unitDef": unit_def,
            "xp": 0,
            "player": bool(player) if player is not None else status == "active",
            "home": _hero_home(hid, state, row if row else None),
            "status": "active" if status == "active" else "active",
            "wounds": 0,
            "scars": [],
        }
        chars[hid] = sheet
    if player is not None:
        sheet["player"] = bool(player)
    if status == "active":
        sheet["status"] = "active"
        sheet["player"] = True if player is None else bool(player)
    elif status == "locked":
        sheet["player"] = False if player is None else bool(player)


def seal_company(
    state: Dict[str, Any],
    band_ids: List[str],
    *,
    workspace: Optional[Path] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Seal the run company. Returns (ok, error, company)."""
    packs = load_crew_packs(workspace)
    ensure_company(state, workspace)
    company = state["company"]
    if company.get("sealed"):
        return False, "company already sealed", company

    cap = int(company.get("seatCap") or seat_cap(packs))
    core = [str(x) for x in (company.get("core") or core_hero_ids(packs))]
    unlocked = set(unlock_pool_ids(state, packs))
    picks: List[str] = []
    seen = set()
    for raw in band_ids:
        hid = str(raw or "").strip()
        if not hid or hid in seen:
            continue
        if hid in core:
            return False, f"{hid} is core — not a band seat", company
        if hid not in unlocked:
            return False, f"{hid} is not unlocked", company
        pack = (packs.get("heroes") or {}).get(hid)
        if not isinstance(pack, dict) or str(pack.get("role")) != "band":
            return False, f"{hid} is not a band pack", company
        seen.add(hid)
        picks.append(hid)

    if len(picks) != cap:
        return False, f"pick exactly {cap} packs (got {len(picks)})", company
    # The first pick is you: the hero the player is. You lead on foot.
    you = picks[0]
    if not hero_can_lead(you, packs):
        name = ((packs.get("heroes") or {}).get(you) or {}).get("name") or you
        return False, f"{name} cannot lead (a building cannot walk); pick someone who can as yourself", company

    # Builders spend Tnb; Cortex packs spend km$ (1km$ = 1000 BAR metal bag).
    commerce = state.setdefault("commerce", {})
    if "tenebrium" not in commerce:
        commerce["tenebrium"] = int(packs.get("startWalletTnb") or 0)
    if "metalK" not in commerce:
        commerce["metalK"] = int(packs.get("startWalletKm") or commerce.get("credits") or 7)
    wallet = int(commerce.get("tenebrium") or 0)
    metal_k = int(commerce.get("metalK") or 0)
    spent_tnb = 0
    spent_km = 0
    for hid in picks:
        pack = (packs.get("heroes") or {}).get(hid) or {}
        spent_tnb += int(pack.get("hireTnb") or 0)
        spent_km += int(pack.get("hireKm") or pack.get("hireKm$") or 0)
    if spent_tnb > wallet:
        return False, f"need {spent_tnb} Tnb for builders (have {wallet})", company
    if spent_km > metal_k:
        return False, f"need {spent_km} km$ for Cortex packs (have {metal_k})", company

    roster_map = load_hero_roster_map(workspace)
    all_band = band_hero_ids(packs)

    # Preserve field rescues / mid-run joins across a fresh preamble seal.
    # Old behavior rebuilt every non-pick as wild+locked and wiped joinedLater,
    # so Hearth/Cauter rescues vanished from muster on the next Drop.
    prior_owned = set()
    for hid in (company.get("joinedLater") or []):
        if hid:
            prior_owned.add(str(hid))
    old_field = state.get("fieldPool") or {}
    if isinstance(old_field, dict):
        for hid, entry in old_field.items():
            if isinstance(entry, dict) and str(entry.get("status")) == "recruited":
                prior_owned.add(str(hid))
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if not isinstance(h, dict):
            continue
        hid = str(h.get("heroId") or h.get("id") or "")
        if not hid or hid in core or hid in picks:
            continue
        if str(h.get("status") or "") == "active" and h.get("player") is True:
            prior_owned.add(hid)

    # Activate core + picks
    for hid in core:
        _set_roster_status(state, hid, "active", player=True)
    for hid in picks:
        _set_roster_status(state, hid, "active", player=True)
    # You are mission-critical: if you go down in the field, the company must bring you back.
    for h in ((state.get("roster") or {}).get("heroes") or []):
        if isinstance(h, dict) and str(h.get("heroId") or h.get("id") or "") == you:
            h["missionCritical"] = True
            h["you"] = True

    # Wild pool = unpicked band who are not already company-owned rescues.
    field: Dict[str, Any] = {}
    later: List[str] = []
    for hid in all_band:
        if hid in picks or hid in core:
            continue
        if hid in prior_owned:
            later.append(hid)
            _set_roster_status(state, hid, "active", player=True)
            # Keep a recruited field marker so later seals still see ownership.
            prev = old_field.get(hid) if isinstance(old_field, dict) else None
            if isinstance(prev, dict):
                kept = dict(prev)
                kept["status"] = "recruited"
                field[hid] = kept
            else:
                kept = build_field_entry(hid, state, packs=packs, roster_map=roster_map)
                kept["status"] = "recruited"
                field[hid] = kept
            continue
        entry = build_field_entry(hid, state, packs=packs, roster_map=roster_map)
        field[hid] = entry
        _set_roster_status(state, hid, "locked", player=False)

    ledger = commerce.setdefault("ledger", [])
    if spent_tnb > 0:
        commerce["tenebrium"] = wallet - spent_tnb
        if isinstance(ledger, list):
            ledger.append({
                "op": "formation_hire_tnb",
                "spent": spent_tnb,
                "tenebriumLeft": commerce["tenebrium"],
                "band": list(picks),
                "at": utc_now(),
            })
    if spent_km > 0:
        commerce["metalK"] = metal_k - spent_km
        if isinstance(ledger, list):
            ledger.append({
                "op": "formation_hire_km",
                "spent": spent_km,
                "metalKLeft": commerce["metalK"],
                "band": list(picks),
                "at": utc_now(),
            })

    company["sealed"] = True
    company["core"] = core
    company["band"] = picks
    company["you"] = you
    company["joinedLater"] = later
    company["sealedAt"] = utc_now()
    company["formationTnbSpent"] = spent_tnb
    company["formationKmSpent"] = spent_km
    state["company"] = company
    state["fieldPool"] = field
    state["commerce"] = commerce
    return True, "", company


def join_from_field(
    state: Dict[str, Any],
    hero_id: str,
    *,
    workspace: Optional[Path] = None,
    reason: str = "wreck_rez",
) -> Tuple[bool, str]:
    """Move a wild hero into company.joinedLater (mid-run recruit)."""
    ensure_company(state, workspace)
    company = state["company"]
    if not company.get("sealed"):
        return False, "company not sealed"
    hid = str(hero_id)
    field = state.get("fieldPool") or {}
    entry = field.get(hid)
    if not isinstance(entry, dict):
        return False, f"{hid} not in field pool"
    if str(entry.get("status")) != "wild":
        return False, f"{hid} status is {entry.get('status')}"

    entry["status"] = "recruited"
    entry["recruitedAt"] = utc_now()
    entry["recruitReason"] = reason
    later = company.setdefault("joinedLater", [])
    if hid not in later and hid not in (company.get("band") or []):
        later.append(hid)
    _set_roster_status(state, hid, "active", player=True)
    return True, ""


def sealed_now_for_surface(state: Dict[str, Any]) -> bool:
    return bool((state.get("company") or {}).get("sealed"))


def _zone_belief_stack(state: Dict[str, Any], map_id: str, zone_id: str) -> Dict[str, float]:
    zm = ((state.get("zoneMemory") or {}).get(map_id) or {}).get(zone_id) or {}
    if not isinstance(zm, dict):
        return {}
    presence = zm.get("factionPresence")
    if isinstance(presence, dict):
        out: Dict[str, float] = {}
        for k, v in presence.items():
            try:
                out[str(k)] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    return {}


def score_field_recruit_belief(
    state: Dict[str, Any],
    entry: Dict[str, Any],
    *,
    map_id: str,
    marked_zone_ids: Optional[List[str]] = None,
) -> float:
    """Belief-field weight: player attention (marks) collapses the recruit onto that pad.

    Parametric axes (not magic lists):
      - marked zone match (hub target / infil attention)
      - enemy presence on the hero's home pad (contested attractor)
      - shellScar (scars pull salvage / wreck-rez fiction)
      - campaign q2 cohesion soft prior (cohesive company → easier joins)
    """
    recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
    home = entry.get("home") if isinstance(entry.get("home"), list) else []
    zone = str(recruit.get("zoneId") or (home[1] if len(home) > 1 else "") or "")
    marked = {str(z) for z in (marked_zone_ids or []) if z}
    score = 0.15  # baseline so unmarked wild can still fill a seat
    if zone and zone in marked:
        score += 10.0  # attention collapse — this is the sortie→character link
    stack = _zone_belief_stack(state, map_id, zone) if zone else {}
    enemy = float(stack.get("armada") or 0) + float(stack.get("cortex") or 0) + float(stack.get("wild") or 0)
    score += min(2.5, enemy * 2.0)
    zm = ((state.get("zoneMemory") or {}).get(map_id) or {}).get(zone) or {}
    absr = zm.get("abstract") if isinstance(zm, dict) else {}
    if isinstance(absr, dict):
        score += min(1.5, float(absr.get("shellScar") or 0.0) * 2.0)
    graph = state.get("graph") or {}
    try:
        q2 = float(graph.get("q2_cohesion") or 0.5)
    except (TypeError, ValueError):
        q2 = 0.5
    score += (q2 - 0.5) * 0.6
    mode = str(recruit.get("type") or "wreck_rez")
    if mode in ("wreck_rez", "retrieve_stash", "capture"):
        score += 0.2
    return round(score, 4)


def _encounter_per_sortie(workspace: Optional[Path]) -> int:
    from verdance.company import encounters as _enc
    return _enc.per_sortie(workspace)


def field_recruits_for_map(
    state: Dict[str, Any],
    map_id: str,
    *,
    workspace: Optional[Path] = None,
    limit: Optional[int] = None,
    marked_zone_ids: Optional[List[str]] = None,
    objective_archetype: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Wild fieldPool heroes for this sortie: the encounter field's seeded draw, by the weights in
    data/story/encounter_rules.json (how many a sortie meets, how much a marked zone draws, how hard a
    home pulls). Nothing is guaranteed but the builder at the Rock Jungle's entrance.

    Dual-ledger law: on eco_raid / seize / etc., wild recruits default to
    **optional** (bonus). Destroying them must not fail the primary board.
    Hard-link only when recruit.optionalJoin is explicitly false, or
    requiresVictory / contracted is set, or archetype is a rescue contract.
    """
    ensure_company(state, workspace)
    mid = str(map_id or "")
    if not mid:
        return []
    arch = str(objective_archetype or "").strip().lower()
    field = state.get("fieldPool") or {}

    def _row(hid: str, entry: Dict[str, Any], rmap: str, zone: str, belief: float) -> Dict[str, Any]:
        recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
        seed_xp = recruit.get("seedXp")
        if seed_xp is None and isinstance(entry.get("xp"), (int, float)):
            seed_xp = entry.get("xp")
        mode = str(recruit.get("type") or "wreck_rez")
        # Default optional on raid archetypes (and when unset). Explicit false keeps contract.
        raw_opt = recruit.get("optionalJoin")
        optional = True if raw_opt is None else bool(raw_opt)
        if recruit.get("requiresVictory") or recruit.get("contracted") is True:
            optional = False
        if str(recruit.get("type") or "") in ("rescue_contract", "retrieve_stash") and raw_opt is False:
            optional = False
        unit_def = str(entry.get("unitDef") or "legcen")
        wreck_proxy = WRECK_SEED_PROXY.get(unit_def)
        row = {
            "heroId": str(entry.get("heroId") or hid),
            "name": str(entry.get("name") or hid),
            "unitDef": unit_def,
            "mapId": rmap,
            "zoneId": zone or None,
            "recruitMode": mode,
            "requiresVictory": bool(recruit.get("requiresVictory")),
            "optionalJoin": optional,
            # Explicit contract stamp for the gadget (optionalJoin=false → linked).
            "sortieLinked": not optional,
            "seedXp": float(seed_xp) if seed_xp is not None else None,
            "blurb": str(recruit.get("blurb") or "") or None,
            "beliefScore": belief,
            # Engine death wreck (rez) or live unit (capture) — stock BAR convert.
            "spawnAsWreck": mode in ("wreck_rez", "retrieve_stash"),
        }
        # Buildings/pads often fail Gaia CreateUnit wreck seeds — stamp a mobile
        # proxy corpse def while keeping unitDef as the hero chassis identity.
        if wreck_proxy:
            row["wreckUnitDef"] = wreck_proxy
        fab = recruit.get("factory")
        if fab:
            row["factory"] = str(fab)
        return row

    # The encounter field (umwelt.foresight.encounter): who the company meets here is drawn by the
    # bond web, the company's draw belief and the ground, not by a fixed home. Marked zones are the
    # company's attention. Falls through to the fixed homes when Umwelt lacks the module.
    from verdance.company import encounters as _enc
    if limit is None:
        limit = _enc.per_sortie(workspace)
    try:
        met = _enc.encounters_for_map(state, mid, workspace=workspace, limit=limit, marked_zone_ids=marked_zone_ids)
    except Exception as exc:  # noqa: BLE001 - never block a sortie on the encounter field
        print(f"VA_ENCOUNTER_FAIL {type(exc).__name__}: {exc}")
        met = None
    if met is not None:
        rows = []
        for m in met:
            entry = field.get(m["heroId"])
            if not isinstance(entry, dict):
                continue
            row = _row(m["heroId"], entry, mid, str(m["zoneId"]), round(float(m["score"]), 4))
            row["encounter"] = {"p": m["p"], "anchored": m["anchored"], "reasons": m["reasons"], "label": m["label"]}
            if m["reasons"] and "builder waits" in str(m["reasons"][0]):
                row["entrance"] = True
            rows.append(row)
        return _enc.apply_meeting_stance(rows, state, workspace, mid)

    candidates: List[Dict[str, Any]] = []
    for hid, entry in field.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "") != "wild":
            continue
        recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
        home = entry.get("home") if isinstance(entry.get("home"), list) else []
        rmap = str(recruit.get("mapId") or (home[0] if home else "") or "")
        if rmap != mid:
            continue
        zone = str(recruit.get("zoneId") or (home[1] if len(home) > 1 else "") or "")
        belief = score_field_recruit_belief(
            state, entry, map_id=mid, marked_zone_ids=marked_zone_ids
        )
        candidates.append(_row(hid, entry, rmap, zone, belief))
    # Without the encounter field: the fixed homes, ranked by belief, a marked zone weighting its
    # hero by the same drawBoost; the entrance builder rule holds here too.
    boost = float((_enc.rules(workspace).get("markedGround") or {}).get("drawBoost", 1.0))
    marked = {str(z) for z in (marked_zone_ids or []) if z}
    for c in candidates:
        if str(c.get("zoneId") or "") in marked:
            c["beliefScore"] = round(float(c.get("beliefScore") or 0) * boost, 4)
    out: List[Dict[str, Any]] = []
    gate = _enc.entrance_builder(state, mid, workspace) if int(limit) > 0 else None
    if gate:
        entry = field.get(gate[0])
        if isinstance(entry, dict):
            out.append(dict(_row(gate[0], entry, mid, gate[1], 99.0), entrance=True))
    candidates = [c for c in candidates if c["heroId"] not in {o["heroId"] for o in out}]
    candidates.sort(key=lambda r: (-float(r.get("beliefScore") or 0), str(r.get("heroId") or "")))
    return _enc.apply_meeting_stance(out + candidates[: max(0, int(limit) - len(out))], state, workspace, mid)


def _collect_lost_field_recruit_ids(result: Dict[str, Any]) -> List[str]:
    """Hero ids whose rescue wreck was destroyed (not recruited)."""
    ids: List[str] = []
    for key in ("objectiveFailHero", "rescueFailHero", "rescueContractFailHero"):
        hid = result.get(key)
        if isinstance(hid, str) and hid.strip():
            ids.append(hid.strip())
    hrs = result.get("heroResults") if isinstance(result.get("heroResults"), dict) else {}
    for hid, hr in hrs.items():
        if not isinstance(hr, dict):
            continue
        if not (hr.get("fieldRecruit") or hr.get("wasFieldRecruit")):
            continue
        if hr.get("recruited"):
            continue
        if str(hr.get("status") or "") == "dead":
            ids.append(str(hid))
    for s in result.get("secondaryResults") or []:
        if not isinstance(s, dict):
            continue
        if not (s.get("failed") or str(s.get("outcome") or "") == "lost"):
            continue
        sid = str(s.get("id") or s.get("objectiveId") or "")
        if sid.startswith("hero_down_"):
            ids.append(sid.replace("hero_down_", "", 1))
        hid = s.get("heroId")
        if isinstance(hid, str) and hid.strip():
            ids.append(hid.strip())
    # Stable unique
    seen: set[str] = set()
    out: List[str] = []
    for hid in ids:
        if hid and hid not in seen:
            seen.add(hid)
            out.append(hid)
    return out


def apply_field_recruit_losses_from_result(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    workspace: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Mark wild fieldPool heroes lost when the rescue contract is destroyed.

    Without this, a blasted Fatboy pad stays wild and re-seeds next Drop.
    """
    ensure_company(state, workspace)
    ids = _collect_lost_field_recruit_ids(result)
    if not ids:
        return []
    field = state.get("fieldPool") or {}
    if not isinstance(field, dict):
        return []
    reason = str(
        result.get("objectiveFailReason")
        or result.get("terminalReason")
        or "wreck_destroyed"
    )
    lost: List[Dict[str, Any]] = []
    for hid in ids:
        entry = field.get(hid)
        if not isinstance(entry, dict):
            continue
        st = str(entry.get("status") or "")
        if st not in ("wild", ""):
            continue
        entry["status"] = "lost"
        entry["lostAt"] = utc_now()
        entry["lostReason"] = reason
        lost.append({
            "heroId": hid,
            "name": str(entry.get("name") or hid),
            "unitDef": str(entry.get("unitDef") or ""),
            "reason": reason,
        })
    return lost


def _recruited_ids_from_result(result: Dict[str, Any]) -> List[str]:
    """Union of explicit recruit id lists and heroResults.recruited flags.

    Soft-terminal / /vawin / gadget-reload paths sometimes drop the id list while
    heroResults still stamps recruited=true (or the reverse). Take both.
    """
    ids: List[str] = []
    seen = set()

    def add(hid: str) -> None:
        hid = str(hid or "").strip()
        if not hid or hid in seen:
            return
        seen.add(hid)
        ids.append(hid)

    raw = result.get("recruitedHeroIds") or result.get("recruitedHeroes") or []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                add(str(item.get("heroId") or item.get("id") or ""))

    hero_results = result.get("heroResults")
    if isinstance(hero_results, dict):
        for hid, row in hero_results.items():
            if isinstance(row, dict) and row.get("recruited") is True:
                add(str(hid))
    return ids


def apply_field_recruits_from_result(
    state: Dict[str, Any],
    result: Dict[str, Any],
    *,
    workspace: Optional[Path] = None,
    full_success: bool = False,
) -> List[Dict[str, Any]]:
    """Join wild heroes listed in result.recruitedHeroIds into the company.

    Call apply_field_recruit_losses_from_result first when processing a result so
    a destroyed rescue wreck cannot also join from a stale id list.
    """
    ensure_company(state, workspace)
    ids = _recruited_ids_from_result(result)
    joined: List[Dict[str, Any]] = []
    field = state.get("fieldPool") or {}
    for hid in ids:
        entry = field.get(hid) if isinstance(field, dict) else None
        # Already company — still ensure roster active / joinedLater membership.
        if isinstance(entry, dict) and str(entry.get("status")) == "recruited":
            later = (state.get("company") or {}).setdefault("joinedLater", [])
            if hid not in later and hid not in ((state.get("company") or {}).get("band") or []):
                later.append(hid)
            _set_roster_status(state, hid, "active", player=True)
            continue
        recruit = (entry or {}).get("recruit") if isinstance(entry, dict) else {}
        if isinstance(recruit, dict) and recruit.get("requiresVictory") and not full_success:
            continue
        reason = "wreck_rez"
        if isinstance(entry, dict) and isinstance(entry.get("recruit"), dict):
            reason = str(entry["recruit"].get("type") or "wreck_rez")
        # Capture / assist / stash all land in joinedLater the same way.
        ok, err = join_from_field(state, hid, workspace=workspace, reason=reason)
        if not ok:
            # Missing field-pool row (stale seed): still activate so muster owns them.
            if err and "not in field pool" in err:
                ensure_company(state, workspace)
                company = state["company"]
                if company.get("sealed"):
                    packs = load_crew_packs(workspace)
                    roster_map = load_hero_roster_map(workspace)
                    field = state.setdefault("fieldPool", {})
                    if hid not in field:
                        field[hid] = build_field_entry(
                            hid, state, packs=packs, roster_map=roster_map
                        )
                    ok, err = join_from_field(state, hid, workspace=workspace, reason=reason)
            if not ok:
                continue
        name = ""
        unit_def = ""
        entry = (state.get("fieldPool") or {}).get(hid) if isinstance(state.get("fieldPool"), dict) else entry
        if isinstance(entry, dict):
            name = str(entry.get("name") or hid)
            unit_def = str(entry.get("unitDef") or "")
            # Stash pilots unlock banked campaign XP on join.
            recruit = entry.get("recruit") if isinstance(entry.get("recruit"), dict) else {}
            unlock_xp = recruit.get("campaignXpUnlock")
            if unlock_xp is not None:
                roster = state.get("heroRoster") or state.get("heroes") or {}
                if isinstance(roster, dict) and isinstance(roster.get(hid), dict):
                    roster[hid]["campaignXp"] = max(
                        float(roster[hid].get("campaignXp") or 0),
                        float(unlock_xp),
                    )
                    if recruit.get("seedXp") is not None:
                        roster[hid]["xp"] = max(
                            float(roster[hid].get("xp") or 0),
                            float(recruit["seedXp"]),
                        )
        else:
            name = hid
        joined.append({"heroId": hid, "name": name, "unitDef": unit_def, "source": reason})
    if joined:
        recent = state.get("recentHeroJoins")
        if not isinstance(recent, dict):
            recent = {"missionNumber": int(state.get("missionNumber") or 1), "heroIds": [], "names": []}
            state["recentHeroJoins"] = recent
        for j in joined:
            if j["heroId"] not in (recent.get("heroIds") or []):
                recent.setdefault("heroIds", []).append(j["heroId"])
                recent.setdefault("names", []).append(j["name"])
    return joined


def hub_company_surface(state: Dict[str, Any], workspace: Optional[Path] = None) -> Dict[str, Any]:
    """Slice for hub_state.json / portal."""
    packs = load_crew_packs(workspace)
    ensure_company(state, workspace)
    company = state["company"]
    roster_map = load_hero_roster_map(workspace)
    unlocked = unlock_pool_ids(state, packs)

    def card(hid: str) -> Dict[str, Any]:
        pack = (packs.get("heroes") or {}).get(hid) or {}
        row = roster_map.get(hid) or {}
        chassis = (packs.get("chassis") or {}).get(pack.get("unitDef") or "") or {}
        escorts = pack.get("escorts") if isinstance(pack.get("escorts"), list) else []
        escort_labels = []
        for esc in escorts:
            if not isinstance(esc, dict):
                continue
            edef = str(esc.get("unitDef") or "")
            elab = ((packs.get("chassis") or {}).get(edef) or {}).get("label") or edef
            escort_labels.append({"unitDef": edef, "label": elab, "count": int(esc.get("count") or 0)})
        return {
            "id": hid,
            "name": pack.get("name") or row.get("name") or hid,
            "unitDef": pack.get("unitDef"),
            "chassisLabel": chassis.get("label") or pack.get("unitDef") or "?",
            "packTotal": pack.get("packTotal") or 1,
            "hireTnb": int(pack.get("hireTnb") or 0),
            "hireKm": int(pack.get("hireKm") or pack.get("hireKm$") or 0),
            "blurb": pack.get("blurb") or row.get("fiction") or "",
            "role": pack.get("role") or "band",
            "premium": bool(pack.get("premium")),
            "canLead": pack.get("canLead", True) is not False,
            "escorts": escort_labels,
        }

    field = state.get("fieldPool") or {}
    if any(isinstance(e, dict) and str(e.get("status")) == "wild" and "roam" not in e for e in field.values()):
        try:   # an older save, or a fresh seal: place the wild before showing them
            from verdance.company import encounters as _enc
            _enc.refresh_whereabouts(state, workspace)
        except Exception as exc:  # noqa: BLE001
            print(f"VA_ENCOUNTER_FAIL {type(exc).__name__}: {exc}")
    wild = []
    for hid, entry in field.items():
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status")) != "wild":
            continue
        home = entry.get("home") or []
        roam = entry.get("roam") if isinstance(entry.get("roam"), dict) else None
        wild.append({
            "id": hid,
            "name": entry.get("name") or hid,
            "unitDef": entry.get("unitDef"),
            # where the company believes they are (the encounter field), else their authored home
            "mapId": (roam or {}).get("mapId") or (home[0] if home else None),
            "zoneId": (roam or {}).get("zoneId") or (home[1] if len(home) > 1 else None),
            "recruit": entry.get("recruit") or {"type": "wreck_rez"},
            "whereabouts": roam,
        })
    # How each would turn up if met now: tension with the party = alive and against us (encounters).
    try:
        from verdance.company import encounters as _enc_st
        for w in wild:
            rec = w["recruit"] if isinstance(w["recruit"], dict) else {}
            if str(rec.get("type") or "wreck_rez") in _enc_st.KEEP_MEETING or rec.get("requiresVictory"):
                continue
            w["stance"] = _enc_st.meeting(str(w["id"]), state, workspace, w.get("mapId") or "")
    except Exception as exc:  # noqa: BLE001
        print(f"VA_STANCE_FAIL {type(exc).__name__}: {exc}")
    try:
        from verdance.company import encounters as _enc
        encounter_draw = _enc.draws_by_map(state, workspace) if sealed_now_for_surface(state) else None
    except Exception as exc:  # noqa: BLE001
        print(f"VA_ENCOUNTER_FAIL {type(exc).__name__}: {exc}")
        encounter_draw = None

    sealed = bool(company.get("sealed"))
    commerce = state.get("commerce") or {}
    if "tenebrium" in commerce:
        formation_wallet = int(commerce.get("tenebrium") or 0)
    else:
        formation_wallet = int(packs.get("startWalletTnb") or 0)
    if "metalK" in commerce:
        formation_km = int(commerce.get("metalK") or 0)
    else:
        formation_km = int(packs.get("startWalletKm") or 7)

    deploy_band = company_deploy_band(state) if sealed else []

    return {
        "sealed": sealed,
        "preambleNeeded": not sealed,
        "core": [card(h) for h in (company.get("core") or core_hero_ids(packs))],
        "band": list(company.get("band") or []),
        "you": company.get("you"),
        "joinedLater": list(company.get("joinedLater") or []),
        # heroes rented from the Cortex mercenary store for the next drop (verdance.company.rentals)
        "rented": list(company.get("rented") or []),
        "seatCap": int(company.get("seatCap") or seat_cap(packs)),
        # Preamble wallets: Tnb for build-power / reactor seats only.
        "formationWalletTnb": formation_wallet,
        "formationWalletKm": formation_km,
        "unlockedIds": unlocked,
        "pool": [card(h) for h in unlocked],
        "wild": wild,
        # the seeded draw per map (who the company would meet there, unmarked); None = fixed homes
        "encounterDraw": encounter_draw,
        "encounterPerSortie": _encounter_per_sortie(workspace),
        "deployAces": company_deploy_aces(state, packs) if sealed else core_hero_ids(packs),
        "deployBand": deploy_band,
    }
