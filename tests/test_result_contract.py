"""The sortie result's top-level fields, by section (include/campaign/result*.lua).

resultJson writes the sections in RESULT_SECTIONS order; each section is a function in the part that
knows its facts. Python (verdance.hub.contract.normalize_result, match_credit, manifest) reads these
keys, so adding, dropping or moving one is a contract change: update SECTIONS here on purpose.
"""
from __future__ import annotations

import re

import campaign_lua

SECTIONS = {
    "resultSortieFields": "schemaVersion campaignId missionId missionNumber playerTeamId chapterIndex pathSignal "
                          "resultKey sortieId status terminalReason manifest frame elapsedMinutes holdFrames "
                          "requiredFrames debugAutoProgress sessionMode occupationModel deploymentMapId mapId "
                          "deploymentZoneId targetZoneId extractionZoneId patron map zoneMap",
    "resultObjectiveFields": "objectiveKind objectiveMode objectiveComplete objectiveCompleteHow objectiveCompleteFrame "
                             "objectiveTargetsTotal objectiveTargetsDestroyed destroyedObjectiveIds "
                             "objectiveResults requiredMarksLeft allObjectivesDone secondaryResults purge "
                             "objectiveFailed objectiveFailReason objectiveFailHero rescueContractFailed shellScars "
                             "survivingInstalls",
    "resultCaptureFields": "nodeClaimed nodeClaimedFrame pocketCleared capturePhase captureMode regrowWaves zoneHoldFrames",
    "resultCompanyFields": "armyValue metrics playerSurvivors playerSurvivorXp loanUnitHp playerFootprint",
    "resultHeroFields": "heroResults recruitedHeroIds namedOutcomes companionsAlive companionsTotal primaryCompanion "
                        "commanderSuit",
    "resultMetalFields": "metalStored metalStorage metalKExtracted metalKBrought metalKFieldStart metalExportMode",
    "resultTenebriumFields": "tenebriumLooted tenebriumBank tenebriumInvested tenebriumLivingStakes "
                             "tenebriumLivingStakeUnits tenebriumSpent tenebriumLost tenebriumLootEvents "
                             "tenebriumWrecksCreated tenebriumWrecksClaimed tenebriumWrecksLost "
                             "tenebriumUnclaimedOnExtraction tenebriumClaimEvents tenebriumTeamBanks "
                             "tenebriumFactionBanks armadaTenebriumCrisis",
    "resultWorldFields": "economy graph reputation zoneDv observedZones beliefExport kings",
}


def _section_keys(src: str, fn: str) -> list[str]:
    m = re.search(r"(?ms)^(?:local )?function " + fn + r"\(.*?^end$", src)
    assert m, f"{fn} is not defined"
    return re.findall(r"""(?m)^    '"([A-Za-z]+)":""", m.group(0))


def test_each_section_writes_its_fields():
    src = campaign_lua.source()
    for fn, keys in SECTIONS.items():
        assert _section_keys(src, fn) == keys.split(), fn


def test_result_sections_run_in_order_and_no_key_is_written_twice():
    src = campaign_lua.source()
    block = re.search(r"(?s)local RESULT_SECTIONS = \{(.*?)\n\}", src).group(1)
    assert re.findall(r"return (result\w+Fields)\(c\)", block) == list(SECTIONS)
    every = [k for keys in SECTIONS.values() for k in keys.split()]
    assert len(every) == len(set(every)) == 95
