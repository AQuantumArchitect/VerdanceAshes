"""Sturdiness checks for rescue-wreck fail → EXTRACT (one path).

We cannot run the Spring gadget in pytest; these tests lock the Lua contracts
by reading the shipped sources so a regression cannot silently drop the path.

Canonical path:
  blast wreck → short grace → heroLost → failRescueContract (latch) → the extract loop opens;
  the verdict word is the campaign's to derive (pass nine: the gadget reports facts).
(The gadget-terminal and HUD-prompt string checks went with the debrief widget in pass seven.)
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKS = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "include" / "va_marks_registry.lua"
CAMPAIGN = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets" / "game_verdance_campaign.lua"


def _live_lines(src: str, needle: str) -> list[str]:
    return [
        ln for ln in src.splitlines()
        if needle in ln and not ln.strip().startswith("--")
    ]


def test_marks_fail_does_not_credit_required_left(marks_src: str | None = None):
    marks_src = marks_src or MARKS.read_text(encoding="utf-8")
    assert "function M.fail(" in marks_src
    assert "Do NOT decrement requiredLeft" in marks_src or "must never unlock victory" in marks_src.lower()
    assert 'outcome == "lost"' in marks_src
    assert "M.fail(reg, sid, label)" in marks_src
    assert "va_sec" in marks_src and "_failed" in marks_src


def test_blast_uses_short_rez_grace(campaign_src: str | None = None):
    campaign_src = campaign_src or CAMPAIGN.read_text(encoding="utf-8")
    assert "rezBuilderWorkingFeature" in campaign_src
    assert "wreck_gone" in campaign_src
    assert "math.min(HERO_REZ_GRACE, 15)" in campaign_src


def test_sortie_link_is_optional_only(campaign_src: str | None = None):
    """Contracted unless optionalJoin — no belief/zone side paths."""
    campaign_src = campaign_src or CAMPAIGN.read_text(encoding="utf-8")
    block = campaign_src.split("function fieldRecruitIsSortieLinked", 1)[1].split("\nend", 1)[0]
    assert "optionalJoin" in block
    assert "beliefScore" not in block
    assert "targetZone" not in block


def test_eco_raid_field_recruits_default_optional():
    """Tnb/eco raid must not hard-fail the board when a wild recruit wreck dies."""
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from verdance.company.company import WRECK_SEED_PROXY, field_recruits_for_map

    assert WRECK_SEED_PROXY.get("legap") != "legcen"
    state = {
        "company": {"sealed": True, "core": ["vane", "ketha"], "band": [], "joinedLater": [], "seatCap": 3},
        "fieldPool": {
            "fatboy": {
                "heroId": "fatboy",
                "name": "Fatboy Contract",
                "unitDef": "armfboy",
                "status": "wild",
                "home": ["greenest_fields", "GF_NE_PLATEAU"],
                "recruit": {"type": "wreck_rez", "mapId": "greenest_fields", "zoneId": "GF_NE_PLATEAU"},
            },
            "noctua": {
                "heroId": "noctua",
                "name": "Noctua Bay",
                "unitDef": "legap",
                "status": "wild",
                "home": ["greenest_fields", "GF_SE_PLATEAU"],
                "recruit": {
                    "type": "wreck_rez",
                    "mapId": "greenest_fields",
                    "zoneId": "GF_SE_PLATEAU",
                    "factory": "legion_drone_bay",
                },
            },
        },
    }
    rows = field_recruits_for_map(
        state,
        "greenest_fields",
        limit=2,
        marked_zone_ids=["GF_SE_PLATEAU", "GF_NE_PLATEAU"],
        objective_archetype="eco_raid",
    )
    assert rows
    for r in rows:
        assert r["optionalJoin"] is True
        assert r["sortieLinked"] is False
    noctua = next(r for r in rows if r["heroId"] == "noctua")
    assert noctua.get("wreckUnitDef") == "legfig"


def test_credit_and_contract_know_recruit_lost():
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from verdance.belief import match_credit as mc
    from verdance.hub.contract import normalize_result

    assert "extracted_recruit_lost" in mc._REASON_HINTS
    raw = {
        "campaignId": "verdance_ashes",
        "missionId": "va_test",
        "missionNumber": 1,
        "chapterIndex": 1,
        "mapId": "greenest_fields",
        "status": "partial",
        "terminalReason": "extracted_recruit_lost",
        "objectiveFailed": True,
        "objectiveFailReason": "wreck_destroyed",
        "objectiveFailHero": "fatboy",
        "frame": 1200,
    }
    c = mc.credit_from_result(raw)
    assert c["verdict"] == "partial"
    assert c["objectiveFailed"] is True
    assert "rescue" in c["reasonHint"].lower() or "wreck" in c["reasonHint"].lower()
    assert "rescue contract failed" in c["changed"]

    n = normalize_result(raw)
    assert n["verdict"] == "partial"
    assert n["objectiveFailed"] is True
    assert n["objectiveFailReason"] == "wreck_destroyed"
    assert n["objectiveFailHero"] == "fatboy"
    assert n["rescueContractFailed"] is True
    flat = __import__("contract_v2", fromlist=["result_v2_to_v1_fields"]).result_v2_to_v1_fields(n)
    assert flat["objectiveFailed"] is True
    assert flat["objectiveFailHero"] == "fatboy"


def test_company_seeds_sortie_linked():
    src = (ROOT / "tools" / "verdance" / "company" / "company.py").read_text(encoding="utf-8")
    assert "sortieLinked" in src
    assert "not optional" in src


def test_field_pool_marks_lost_recruit():
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    from verdance.company.company import apply_field_recruit_losses_from_result

    state = {
        "company": {
            "sealed": True,
            "core": ["vane", "ketha"],
            "band": [],
            "joinedLater": [],
            "seatCap": 3,
        },
        "fieldPool": {
            "fatboy": {
                "heroId": "fatboy",
                "name": "Fatboy",
                "unitDef": "armfatboy",
                "status": "wild",
                "home": ["greenest_fields", "GF_NE_PLATEAU"],
                "recruit": {"type": "wreck_rez", "optionalJoin": False},
            }
        },
        "unlockPool": [],
    }
    lost = apply_field_recruit_losses_from_result(
        state,
        {
            "objectiveFailed": True,
            "objectiveFailHero": "fatboy",
            "objectiveFailReason": "wreck_destroyed",
            "terminalReason": "extracted_recruit_lost",
        },
    )
    assert len(lost) == 1
    assert lost[0]["heroId"] == "fatboy"
    assert state["fieldPool"]["fatboy"]["status"] == "lost"
    # Idempotent
    lost2 = apply_field_recruit_losses_from_result(
        state, {"objectiveFailHero": "fatboy", "objectiveFailed": True}
    )
    assert lost2 == []


def test_campaign_emits_fail_hero(campaign_src: str | None = None):
    campaign_src = campaign_src or CAMPAIGN.read_text(encoding="utf-8")
    assert "objectiveFailHero" in campaign_src
    assert "rescueContractFailHero" in campaign_src
    marks = MARKS.read_text(encoding="utf-8")
    assert '"heroId":' in marks


if __name__ == "__main__":
    test_marks_fail_does_not_credit_required_left()
    test_campaign_one_fail_path()
    test_soft_clock_respects_rescue_fail()
    test_blast_uses_short_rez_grace()
    test_hud_fail_and_extract_prompts()
    test_voluntary_exfil_and_bail_gates()
    test_result_json_includes_objective_failed()
    test_sortie_link_is_optional_only()
    test_credit_and_contract_know_recruit_lost()
    test_company_seeds_sortie_linked()
    test_field_pool_marks_lost_recruit()
    test_campaign_emits_fail_hero()
    print("ALL_OK")
