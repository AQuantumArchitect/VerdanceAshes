"""The company's reserve: what lifts comes home (hero packs excepted), what boards leaves it,
the lift limit starts at nothing and grows with the value actually brought home."""
from verdance.company import reserve as R


def test_the_lift_grows_with_the_metal_lifted_home_not_the_units():
    """Owner calls 2026-11-09: the lift grows with the stored metal the company lifts off with (reclaim
    the field, build storage), net of the field's starting allotment. Units that lift go into the
    reserve and do not count; a wiped company lifts nothing; verdicts do not matter."""
    roster = {"reserve": {}, "cadre": {}}
    st = {"roster": roster, "history": []}
    assert R.lift_cap(st) == 0
    partial = {"status": "extracted", "metalStored": 6400.0, "metalKFieldStart": 1,
               "manifest": {"going": {"units": {"armpw": 10}}}}
    out = R.homecoming(roster, partial, history=[])
    assert out["metalLifted"] == 5400 and roster["reserve"] == {"armpw": 10}
    assert R.lift_cap(st) == R.LIFT_SHARE * 5400                    # the ten Peewees are reserve, not lift
    st["history"].append({"verdict": "partial"})
    R.homecoming(roster, {"status": "wiped", "metalStored": 9000.0, "manifest": {"going": {"units": {}}}},
                 history=st["history"])
    st["history"].append({"verdict": "defeat"})
    assert R.lift_cap(st) == R.LIFT_SHARE * 5400                    # nobody lifted: the stockpile stayed
    R.homecoming(roster, {"status": "extracted", "metalStored": 300.0, "metalKFieldStart": 1,
                          "manifest": {"going": {"units": {}}}}, history=st["history"])
    assert R.lift_cap(st) == R.LIFT_SHARE * 5400                    # spent below the allotment: nothing gained


def test_the_contract_keeps_the_field_allotment_so_it_is_not_counted_as_hauled():
    """The gadget's result goes through hub.contract before commerce and the roster read it. Until
    2026-11-09 the contract dropped metalKFieldStart: every sortie banked its free 1k allotment as
    hauled metal (the 11-08 rehearsal lifted off with exactly that 1000, unspent)."""
    from verdance.hub.contract import normalize_result, result_v2_to_v1_fields
    raw = {"schemaVersion": "verdance-match-result/2.0", "status": "extracted", "metalStored": 1000.0,
           "metalKExtracted": 1, "metalKFieldStart": 1, "metalKBrought": 0,
           "manifest": {"going": {"heroes": [{"heroId": "ketha"}], "units": {}}}}
    flat = result_v2_to_v1_fields(normalize_result(raw))
    assert flat["metalKFieldStart"] == 1 and flat["metalKBrought"] == 0 and flat["terminalKind"] == "extracted"
    assert R.metal_lifted(flat) == 0.0
    flat["metalStored"] = 7500.0
    assert R.metal_lifted(flat) == 6500.0


def test_an_old_save_keeps_its_lift_on_the_upgrade():
    """A save from before the ledger (0.15): its first homecoming seeds the ledger from the old rule,
    1k per victory or extraction before this sortie, then adds what this sortie lifted."""
    hist = [{"verdict": "victory"}, {"verdict": "partial"}, {"verdict": "extracted"}]
    roster = {"reserve": {}, "cadre": {}}
    st = {"roster": roster, "history": hist}
    assert R.lift_cap(st) == 2000
    R.homecoming(roster, {"status": "extracted", "metalStored": 2000.0, "manifest": {"going": {"units": {"armpw": 2}}}},
                 history=hist)
    assert R.lift_cap(st) == 2000 + R.LIFT_SHARE * 2000


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
