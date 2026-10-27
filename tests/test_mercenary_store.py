"""The Cortex mercenary store in the drop window (owner call, 2026-10-27): a pruned shelf, a Grunt
Stream that keeps coming, the Punch recommended on the first drop, and heroes rented for one drop
who are kept by winning the campaign with them."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.campaign import engine  # noqa: E402
from verdance.campaign.commerce import build_commerce_intent, load_commerce_catalog, purchase_listing  # noqa: E402
from verdance.company import company as C, rentals  # noqa: E402


def _state():
    s = engine.default_v1_state()
    engine.ensure_zone_memory(s, ROOT)
    C.ensure_company(s, ROOT)
    ok, err, _ = C.seal_company(s, ["pavise", "halbard", "solarium"], workspace=ROOT)
    assert ok, err
    s.setdefault("commerce", {}).update(tenebrium=5, metalK=30)
    s["reputation"]["cortex"] = 45
    return s


def test_the_cortex_shelf_is_pruned():
    L = load_commerce_catalog(ROOT)["listings"]
    assert "crash_of_brutes" not in L
    cortex = [k for k, v in L.items() if v.get("shelf") == "cortex"]
    assert len(cortex) <= 7
    assert L["punch_of_thugs"]["recommend"]["firstDrop"] == 2


def test_the_grunt_stream_comes_in_waves():
    s = _state()
    assert purchase_listing(s, "grunt_stream", ROOT)["ok"]
    waves = [p for p in build_commerce_intent(s, ROOT)["pendingDeliveries"] if p["listingId"] == "grunt_stream"]
    assert len(waves) == 4 and sum(p["count"] for p in waves) == 20
    etas = [p["etaSeconds"] for p in waves]
    assert etas == sorted(etas) and etas[-1] - etas[0] == 3 * 45


def test_a_bought_suit_or_rental_is_never_a_free_package():
    s = _state()
    s["commerce"]["tenebrium"] = 20
    assert purchase_listing(s, "cortex_commander_suit", ROOT)["ok"]
    assert purchase_listing(s, "rent_bro", ROOT)["ok"]
    deploy = {d["unitDef"] for d in build_commerce_intent(s, ROOT)["deploy"]}
    assert "corcom" not in deploy and "corgol" not in deploy


def test_a_rented_hero_drops_once_and_goes_back():
    s = _state()
    assert purchase_listing(s, "rent_gale", ROOT)["ok"]
    assert "gale" in C.company_deploy_band(s)
    assert C.hero_status(s, "gale") == "active"
    C.ensure_company(s, ROOT)                                  # the hub rebuild must not re-lock her
    assert C.hero_status(s, "gale") == "active"
    assert not purchase_listing(s, "rent_gale", ROOT)["ok"]    # once per drop
    home = rentals.settle(s, {"status": "victory"})
    assert home == ["gale"] and "gale" not in C.company_deploy_band(s)
    assert not any(h.get("heroId") == "gale" and h.get("rented") for h in s["roster"]["heroes"])


def test_rent_on_the_last_drop_and_win_keeps_the_hero(tmp_path=None):
    import tempfile
    s = _state()
    s["company"]["rentedLastDrop"] = ["bro"]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "state").mkdir()
        gained = C.unlock_rescued_survivors(s, Path(tmp))
        assert "bro" in gained
        prof = json.loads((Path(tmp) / "state" / "profile.json").read_text())
        assert "bro" in prof["unlocked"]
