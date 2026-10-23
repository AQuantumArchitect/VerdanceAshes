"""The company: Ketha always; three picks, the first is you (must walk, mission-critical);
heroes rescued and alive at a campaign's end unlock as starters (state/profile.json)."""
import json, shutil, tempfile
from pathlib import Path

from verdance.campaign.schema import default_v1_state
from verdance.company import company as C

ROOT = Path(__file__).resolve().parents[1]


def _ws():
    ws = Path(tempfile.mkdtemp(prefix="va_you_"))
    (ws / "data" / "story").mkdir(parents=True)
    for f in ("crew_packs.json", "hero_roster.json"):
        shutil.copy(ROOT / "data" / "story" / f, ws / "data" / "story" / f)
    return ws


def test_first_pick_is_you_and_must_walk():
    ws = _ws(); st = default_v1_state()
    packs = C.load_crew_packs(ws)
    assert not C.hero_can_lead("warder", packs) and not C.hero_can_lead("hearth", packs) and C.hero_can_lead("pavise", packs)
    assert set(C.starter_unlock_ids(packs, ws)) == {"pavise", "solarium", "halbard", "vane", "spoke"}
    ok, err, comp = C.seal_company(st, ["pavise", "solarium", "halbard"], workspace=ws)
    assert ok, err
    assert comp["you"] == "pavise" and comp["core"] == ["ketha"]
    row = next(h for h in st["roster"]["heroes"] if h["heroId"] == "pavise")
    assert row["missionCritical"] is True


def test_anvil_is_not_a_starter():
    ws = _ws(); st = default_v1_state()
    C.ensure_company(st, ws)
    assert "anvil" not in C.unlock_pool_ids(st, C.load_crew_packs(ws))
    ok, err, _ = C.seal_company(st, ["pavise", "anvil", "solarium"], workspace=ws)
    assert not ok and "not unlocked" in err


def test_rescued_survivor_unlocks_for_next_campaign():
    ws = _ws(); st = default_v1_state()
    st["company"] = {"sealed": True, "core": ["ketha"], "band": ["pavise"], "you": "pavise", "joinedLater": ["anvil"]}
    st["roster"]["heroes"].append({"heroId": "anvil", "status": "active"})
    assert C.unlock_rescued_survivors(st, ws) == ["anvil"]
    assert "anvil" in json.loads((ws / "state" / "profile.json").read_text())["unlocked"]
    assert "anvil" in C.starter_unlock_ids(C.load_crew_packs(ws), ws)
