"""The company's reserve: what lifts comes home (hero packs excepted), what boards leaves it, and
the drop limit, which starts at nothing and grows 1k with every sortie played, with no ceiling."""
from pathlib import Path

from verdance.company import reserve as R

ROOT = Path(__file__).resolve().parents[1]


def test_lifted_units_join_the_reserve_and_escorts_do_not():
    roster = {"reserve": {"armsh": 2}, "cadre": {"armsh": 2}}
    result = {"manifest": {"going": {"units": {"armsh": 5, "armart": 3, "legrezbot": 4}, "packUnits": {"legrezbot": 3}}}}
    R.homecoming(roster, result)
    assert roster["reserve"] == {"armsh": 5, "armart": 3, "legrezbot": 1}
    assert roster["cadre"] == {}


def test_brought_units_that_did_not_lift_are_gone():
    roster = {"reserve": {"armart": 6}, "cadre": {"armart": 6}}
    R.homecoming(roster, {"manifest": {"going": {"units": {"armart": 2}}}})
    assert roster["reserve"] == {"armart": 2}


def test_the_drop_limit_grows_with_every_sortie_played_whatever_the_verdict():
    """Owner call 2026-11-09: the drop grows 1k per mission, no cap; the longer you play, the more of
    the reserve you can start a drop with. A partial or a defeat counts; an abandoned sortie does not."""
    reserve = {"armart": 40, "armsh": 40}
    st = {"history": []}
    assert R.lift_cap(st) == 0 and R.default_bring(reserve, 0) == {}
    st["history"] = [{"verdict": "victory"}, {"verdict": "partial"}, {"verdict": "defeat"},
                     {"verdict": "abandon"}, {"verdict": "extracted"}]
    cap = R.lift_cap(st)
    assert R.missions_played(st) == 4 and cap == 4 * R.DROP_PER_MISSION == 4000
    st["history"] += [{"verdict": "partial"}] * 46
    assert R.lift_cap(st) == 50_000                     # no ceiling
    bring = R.default_bring(reserve, cap)
    assert 0 < R.bring_value(bring) <= cap
    assert R.clamp_bring({"armart": 99}, {"armart": 3}, 1e9) == {"armart": 3}


def test_the_veteran_perk_is_one_more_missions_worth():
    st = {"history": [{"verdict": "partial"}], "roster": {"commander": {"perks": ["veteran_cadre"]}}}
    assert R.lift_cap(st) == 2000


def test_an_old_save_starts_its_reserve_from_the_cadre():
    roster = {"cadre": {"armsh": 3}}
    assert R.ensure_reserve(roster) == {"armsh": 3}


def _settle(result, metal_k=5):
    from verdance.campaign import commerce
    from verdance.hub.contract import normalize_result, result_v2_to_v1_fields
    state = {"missionNumber": 3, "commerce": {"tenebrium": 0, "metalK": metal_k, "owned": {}}}
    flat = result_v2_to_v1_fields(normalize_result(dict(result, schemaVersion="verdance-match-result/2.0")))
    commerce.settle_commerce_after_sortie(state, flat, False, False, False, workspace=ROOT)
    return state["commerce"]["metalK"]


def test_the_wallet_banks_what_lifts_off_beyond_the_field_allotment():
    """The metal you lift off with is yours to spend (floor to 1k), net of the 1k the field handed
    you. Until 2026-11-09 the result contract dropped metalKFieldStart, so every sortie banked its
    unspent allotment as hauled metal (the 11-08 rehearsal lifted off with exactly that 1000)."""
    lifted = {"status": "extracted", "metalKFieldStart": 1, "metalKBrought": 0,
              "manifest": {"going": {"heroes": [{"heroId": "ketha"}], "units": {}}}}
    assert _settle(dict(lifted, metalStored=1000.0, metalKExtracted=1)) == 5      # the allotment, unspent
    assert _settle(dict(lifted, metalStored=6400.0, metalKExtracted=6)) == 10     # 6k off the pad, 1k of it handed out


def test_a_wiped_company_banks_none_of_its_stockpile():
    """Owner call 2026-11-09: losing costs what is on the map, and the stockpile was on the map."""
    wiped = {"status": "wiped", "metalStored": 9000.0, "metalKExtracted": 9, "metalKFieldStart": 1, "metalKBrought": 0,
             "manifest": {"going": {"heroes": [], "units": {}}}}
    assert _settle(wiped) == 5


def test_presence_is_defensive_value():
    from verdance.campaign.measure import apply_zone_dv
    state = {"zoneMemory": {"tabula": {"T_C_SPILLWAY": {"controllingFaction": "neutral", "abstract": {"control": "neutral"}}}}}
    result = {"deploymentMapId": "tabula", "zoneDv": {"T_C_SPILLWAY": {"ashwalkers": 1900, "armada": 300},
                                                      "T_C_INNER_SPILLWAY": {"armada": 1600}}}
    changed = apply_zone_dv(state, result)
    zm = state["zoneMemory"]["tabula"]
    assert zm["T_C_SPILLWAY"]["controllingFaction"] == "ashwalkers"
    assert zm["T_C_INNER_SPILLWAY"]["controllingFaction"] == "armada"
    assert set(changed) == {"T_C_SPILLWAY", "T_C_INNER_SPILLWAY"}
