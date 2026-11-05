"""The Rock Jungle pulls along the bag's curve (owner call, 2026-11-04): with nothing to spend its jobs
lose ground to the roads out; with a camp's worth of Tenebrium they gain it. No step anywhere."""
import copy
from pathlib import Path

from verdance.common import WORKSPACE_ROOT
from verdance.campaign import engine
from verdance.world import roads


def _home_scores(tnb):
    st = engine.default_v1_state()
    st["commerce"]["tenebrium"] = tnb
    return {j["id"]: j["score"] for j in roads.legal_jobs(copy.deepcopy(st), Path(WORKSPACE_ROOT))
            if j["mapId"] == roads.HOME_MAP_ID}


def test_home_jobs_move_with_the_bag_smoothly():
    rows = [_home_scores(t) for t in range(0, 8)]
    assert rows[0], "a fresh state has Rock Jungle jobs"
    for jid in rows[0]:
        series = [r[jid] for r in rows]
        assert all(b > a for a, b in zip(series, series[1:])), series
        assert series[-1] - series[0] > roads.HOME_PULL_WEIGHT          # the whole swing is used
        assert all(b - a < 0.8 for a, b in zip(series, series[1:]))   # and no single Tnb is a cliff


def test_the_debrief_says_what_moved():
    before = {"reputation": {"armada": 20.0, "cortex": 50.0}, "growthPending": 2}
    st = {"reputation": {"armada": 17.0, "cortex": 50.2}, "homeCamp": {"growthPending": 6}}
    res = {"secondaryResults": [{"kind": "scout", "label": "the ford", "completed": True},
                                {"kind": "vault", "label": "x", "completed": True}]}
    mv = engine.what_moved(before, st, res, "tabula", [{"name": "Vane"}], [])
    assert mv["standing"] == [{"side": "armada", "name": "Armada", "before": 20, "after": 17, "delta": -3.0}]
    assert mv["marks"] == [{"kind": "scout", "label": "the ford", "done": True}]
    assert mv["rescued"] == ["Vane"] and mv["camp"] == {"grew": 4, "waiting": 6}
    home = engine.what_moved(before, st, res, "the_rock_jungle", [], [])
    assert home["camp"]["placed"] == 2


def test_a_beating_at_home_raises_the_bar_and_fades():
    from verdance.campaign.home import home_pull
    st = {"commerce": {"tenebrium": 2}, "history": []}
    calm = home_pull(st)["pull"]
    st["history"] = [{"mapId": "the_rock_jungle", "verdict": "defeat"}]
    beaten = home_pull(st)["pull"]
    assert beaten < calm - 0.2
    later = []
    for _ in range(6):
        st["history"].append({"mapId": "tabula", "verdict": "victory"})
        later.append(home_pull(st)["pull"])
    assert all(b > a for a, b in zip([beaten] + later, later)) and later[-1] > calm - 0.1
