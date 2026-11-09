"""The company's reserve: what lifts comes home (hero packs excepted), what boards leaves it,
the lift limit starts at nothing and grows with the value actually brought home."""
from verdance.company import reserve as R


def test_the_lift_grows_with_value_brought_home_not_with_verdicts():
    """Owner call 2026-11-09: a partial that lifts an army off the pad grows the lift; a victory that
    lifts nothing does not. The lift is LIFT_SHARE of everything ever brought home."""
    roster = {"reserve": {}, "cadre": {}}
    st = {"roster": roster, "history": []}
    assert R.lift_cap(st) == 0
    out = R.homecoming(roster, {"verdict": "partial", "manifest": {"going": {"units": {"armpw": 10}}}}, history=[])
    ten = 10 * R.unit_value("armpw")
    assert out["liftedValue"] == round(ten) and abs(R.lift_cap(st) - R.LIFT_SHARE * ten) < 0.5
    st["history"].append({"verdict": "partial"})
    R.homecoming(roster, {"verdict": "victory", "manifest": {"going": {"units": {}}}}, history=st["history"])
    st["history"].append({"verdict": "victory"})
    assert abs(R.lift_cap(st) - R.LIFT_SHARE * ten) < 0.5          # a victory lifting nothing adds nothing
    R.homecoming(roster, {"manifest": {"going": {"units": {"armpw": 4}, "packUnits": {"armpw": 4}}}}, history=st["history"])
    assert abs(R.lift_cap(st) - R.LIFT_SHARE * ten) < 0.5          # a hero's pack is not cargo


def test_an_old_save_keeps_its_lift_on_the_upgrade():
    """A save from before the ledger (0.15): its first homecoming seeds the ledger from the old rule,
    1k per victory or extraction before this sortie, then adds what this sortie lifted."""
    hist = [{"verdict": "victory"}, {"verdict": "partial"}, {"verdict": "extracted"}]
    roster = {"reserve": {}, "cadre": {}}
    st = {"roster": roster, "history": hist}
    assert R.lift_cap(st) == 2000
    R.homecoming(roster, {"manifest": {"going": {"units": {"armpw": 2}}}}, history=hist)
    assert abs(R.lift_cap(st) - (2000 + R.LIFT_SHARE * 2 * R.unit_value("armpw"))) < 0.5


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
    assert cap == 2 * R.LIFT_PER_SORTIE == 2000  # no ledger yet: the old rule's lift
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
