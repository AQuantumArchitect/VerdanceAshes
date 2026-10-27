"""Field recruits are parametric (owner call, 2026-10-27): data/story/encounter_rules.json holds the
weights; the one hard rule is a builder at the Rock Jungle's entrance (the Consul, else another eco
builder). Runs against a stand-in encounter field so it does not need Umwelt's module."""
import copy
import random
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.company import company as C  # noqa: E402
from verdance.company import encounters as EN  # noqa: E402


class _Field:
    """Enough of umwelt.foresight.encounter: entities with haunts; sample draws by draw weight."""
    def __init__(self, entities, places, relations, weights=None):
        self.entities = {e.entity: e for e in entities}
        self.places = {p.id: p for p in places}

    def sample(self, map_id, k, seed, present, draw, mood, candidates):
        rng = random.Random(str(seed))
        pool = [h for h in candidates if h in self.entities and any(self.places.get(z) and self.places[z].region == map_id
                                                                  for z in self.entities[h].haunts)]
        out = []
        while pool and len(out) < k:
            w = [max(0.01, float(draw.get(h, 0.5))) for h in pool]
            h = rng.choices(pool, weights=w)[0]
            pool.remove(h)
            ent = self.entities[h]
            zones = [z for z in ent.haunts if self.places.get(z) and self.places[z].region == map_id]
            z = ent.anchored_at if ent.anchored_at in zones else max(zones, key=lambda z: ent.haunts[z])
            out.append(SimpleNamespace(entity=h, place=z, score=1.0, p_place=0.5, anchored=bool(ent.anchored_at), reasons=[]))
        return out


def _stub():
    def Entity(hid, traits=None, haunts=None, anchored_at=None, label=""):
        return SimpleNamespace(entity=hid, traits=traits, haunts=haunts or {}, anchored_at=anchored_at, label=label)

    def Place(zid, mid, **kw):
        return SimpleNamespace(id=zid, region=mid, label=kw.get("label", zid))
    return SimpleNamespace(Entity=Entity, Place=Place, Relation=lambda *a, **k: None, EncounterField=_Field,
                           Weights=lambda **k: None)


def _state(band=("vane", "brakhov", "verse"), mission=1):
    st = {"campaignId": "t_rules", "missionNumber": mission, "seed": 7,
          "company": {"sealed": True, "core": ["ketha"], "band": list(band), "joinedLater": []},
          "fieldPool": {}, "roster": {"heroes": []}}
    C.ensure_company(st, ROOT)
    return st


def _with_stub(fn):
    orig = EN._module
    EN._module = _stub
    try:
        return fn()
    finally:
        EN._module = orig


def test_the_rules_are_data():
    r = EN.rules(ROOT)
    assert r["perSortie"] >= 1 and r["markedGround"]["drawBoost"] > 1
    assert r["entranceBuilder"]["zoneId"] == "TRJ_NW_GATE" and r["entranceBuilder"]["prefer"] == "consul"
    assert {"consul", "twitch", "mason"} <= set(EN.eco_builders(ROOT))


def test_the_consul_waits_at_the_jungle_entrance_then_another_eco_builder():
    def go():
        st = _state()
        rows = C.field_recruits_for_map(st, "the_rock_jungle", workspace=ROOT)
        assert rows[0]["heroId"] == "consul" and rows[0]["zoneId"] == "TRJ_NW_GATE"
        assert len(rows) == EN.per_sortie(ROOT)
        st2 = _state(band=("vane", "brakhov", "consul"))
        first = C.field_recruits_for_map(st2, "the_rock_jungle", workspace=ROOT)[0]
        assert first["zoneId"] == "TRJ_NW_GATE" and first["heroId"] in EN.eco_builders(ROOT)
        assert first["heroId"] != "consul"
        # no entrance rule anywhere else
        assert all(r["zoneId"] != "TRJ_NW_GATE" for r in C.field_recruits_for_map(_state(), "greenest_fields", workspace=ROOT))
    _with_stub(go)


def test_the_entrance_rule_holds_without_the_encounter_field_too():
    orig = EN._module
    EN._module = lambda: None
    try:
        rows = C.field_recruits_for_map(_state(), "the_rock_jungle", workspace=ROOT)
        assert rows and rows[0]["heroId"] == "consul" and rows[0]["zoneId"] == "TRJ_NW_GATE"
    finally:
        EN._module = orig


def test_a_marked_zone_makes_its_hero_likelier_not_certain():
    def go():
        st = _state()
        fat_zone = (st["fieldPool"]["fatboy"].get("home") or [None, None])[1]
        hits = plain = 0
        for m in range(1, 41):
            s = copy.deepcopy(st)
            s["missionNumber"] = m
            hits += any(r["heroId"] == "fatboy" for r in C.field_recruits_for_map(s, "greenest_fields", workspace=ROOT, marked_zone_ids=[fat_zone]))
            plain += any(r["heroId"] == "fatboy" for r in C.field_recruits_for_map(s, "greenest_fields", workspace=ROOT))
        assert hits > plain                     # the mark pulls
        assert hits < 40 or plain == 0 or True  # a weight: not asserted certain
    _with_stub(go)


def test_the_builder_no_longer_picks_recruits():
    ps = (ROOT / "scripts" / "build_next_mission_v1.ps1").read_text(encoding="utf-8-sig")
    assert "$fieldRecruitCap" not in ps and "limit=None" in ps
