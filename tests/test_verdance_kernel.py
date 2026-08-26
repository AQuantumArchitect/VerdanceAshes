"""Kernel surface tests (Phases 1–4 stubs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from verdance_kernel import CampaignKernel, phase_status  # noqa: E402
from verdance_kernel import steam as steam_mod  # noqa: E402
from verdance_kernel import surface as surface_mod  # noqa: E402
from verdance_kernel.phases import PHASES  # noqa: E402


def test_phase_registry():
    st = phase_status()
    assert st["schemaVersion"].startswith("verdance-ship-phases")
    assert "1" in PHASES and PHASES["1"]["status"] == "live"
    assert "2" in PHASES and PHASES["2"]["status"] == "live"


def test_kernel_status_and_hub():
    k = CampaignKernel(ROOT)
    st = k.status()
    assert st["schemaVersion"].startswith("verdance-campaign-kernel")
    assert st["capabilities"]["stamp"] is True
    assert st["capabilities"]["autoApply"] is True
    hub = k.get_hub_surface()
    # hub may need rebuild in clean trees; rebuild if missing
    if not hub.get("ok"):
        rep = k.rebuild_hub()
        assert rep.get("ok")
        hub = k.get_hub_surface()
    assert hub.get("ok")
    assert "missionNumber" in hub["hub"]


def test_steam_mirror_and_achievement():
    k = CampaignKernel(ROOT)
    m = steam_mod.cloud_mirror(ROOT)
    # ok only if campaign_state exists
    if (ROOT / "state" / "campaign_state.json").is_file():
        assert m.get("ok")
        assert (ROOT / "state" / "steam" / "cloud" / "campaign_state.json").is_file()
    u = steam_mod.unlock_achievement(ROOT, "FIRST_SORTIE", detail="unit-test")
    assert u.get("ok")
    st = steam_mod.status(ROOT)
    assert "FIRST_SORTIE" in st.get("unlocked", [])


def test_campaign_surface_write():
    surf = surface_mod.write_surface(ROOT)
    assert surf["schemaVersion"].startswith("verdance-campaign-surface")
    path = Path(surf["path"])
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "choices" in data
    assert "ketha" in data


def test_purchase_missing_listing():
    k = CampaignKernel(ROOT)
    r = k.purchase("")
    assert r.get("ok") is False
