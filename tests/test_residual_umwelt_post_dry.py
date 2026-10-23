#!/usr/bin/env python3
"""Dry tests for residual → umweltPost mapping (no umweltd required)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import hive_bar_residual_v1 as residual  # noqa: E402

WS = TOOLS.parent


def _fixture() -> dict:
    return {
        "schemaVersion": "verdance-proxy-campaign/1.0",
        "sorties": 2,
        "seeds": 1,
        "difficulty": 1.4,
        "byStyle": {
            "simple": {
                "runs": 1,
                "meanWinRate": 1.0,
                "meanFun": 0.37,
                "meanTnb": 0.0,
                "meanClashEvents": 20.0,
            },
            "barbarian": {
                "runs": 1,
                "meanWinRate": 0.5,
                "meanFun": 0.5,
                "meanTnb": 1.0,
                "meanClashEvents": 22.0,
            },
        },
        "headToHead": {"winRateDelta_barb_minus_simple": -0.5},
    }


def test_map_posts_include_saturation_wall():
    r = residual.build_residual(_fixture(), workspace=WS, ran_on="wargen")
    posts = residual.map_residual_to_project_posts(r)
    kinds = {p["kind"] for p in posts}
    assert "referee" in kinds
    assert any(p["kind"] == "wall" and p["polarity"] < 0 for p in posts)


def test_try_umwelt_post_dark_safe():
    r = residual.build_residual(_fixture(), workspace=WS, ran_on="wargen")
    out = residual.try_umwelt_post(r)
    assert "umweltd_dark" in out
    assert "posts_planned" in out
    assert len(out["posts_planned"]) >= 1
    # when dark, attempted posts should be 0
    if out["umweltd_dark"]:
        assert out["attempted"] == 0


def test_write_residual_embeds_umwelt_post():
    r = residual.build_residual(_fixture(), workspace=WS, ran_on="wargen", source="test")
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="va_residual_"))  # never the real outbox or a machine path
    (tmp / "outbox").mkdir()
    result = residual.write_residual(r, tmp, also_hive=False, umwelt_post=True)
    assert result["written"]
    op = residual.residual_write_paths(tmp)["operator"]
    disk = json.loads(op.read_text(encoding="utf-8"))
    assert "umweltPost" in disk
    assert "umweltd_dark" in disk["umweltPost"]
    assert disk["honesty"].get("barDensifyBanned") is True


if __name__ == "__main__":
    test_map_posts_include_saturation_wall()
    test_try_umwelt_post_dark_safe()
    test_write_residual_embeds_umwelt_post()
    print("test_residual_umwelt_post_dry OK")
