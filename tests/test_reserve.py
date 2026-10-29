"""The company's reserve: what lifts comes home (hero packs excepted), what boards leaves it,
the lift limit starts at nothing and grows with each successful sortie."""
from verdance.company import reserve as R


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


def test_lift_limit_holds_and_grows():
    reserve = {"armart": 40, "armsh": 40}
    st = {"history": []}
    assert R.lift_cap(st) == 0 and R.default_bring(reserve, 0) == {}
    st["history"] = [{"verdict": "victory"}, {"verdict": "partial"}, {"verdict": "defeat"}, {"verdict": "extracted"}]
    cap = R.lift_cap(st)
    assert cap == 2 * R.LIFT_PER_SORTIE == 2000
    bring = R.default_bring(reserve, cap)
    assert 0 < R.bring_value(bring) <= cap
    assert R.clamp_bring({"armart": 99}, {"armart": 3}, 1e9) == {"armart": 3}


def test_an_old_save_starts_its_reserve_from_the_cadre():
    roster = {"cadre": {"armsh": 3}}
    assert R.ensure_reserve(roster) == {"armsh": 3}


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
