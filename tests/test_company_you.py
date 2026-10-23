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


def test_rezzed_hero_on_the_pad_comes_home_healthy():
    """Pavise went down, was rezzed, extracted with everyone: she is active, not wounded."""
    from verdance.campaign.roster import update_roster
    st = default_v1_state()
    for h in st["roster"]["heroes"]:
        h["status"] = "active"
    result = {"status": "extracted", "namedOutcomes": [{"charId": "pavise", "outcome": "recovered"}],
              "heroResults": {"pavise": {"status": "survived", "wasDown": True, "xp": 0.5}}}
    update_roster(st, result, True, True)
    pav = next(h for h in st["roster"]["heroes"] if h["heroId"] == "pavise")
    assert pav["status"] == "active", pav


def test_builder_scripts_parse():
    """Every game-path PowerShell script parses (PowerShell 7 if installed; skipped otherwise)."""
    import shutil, subprocess
    pwsh = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if Path("/opt/pwsh/pwsh").exists() else None)
    if not pwsh:
        return
    import tempfile
    files = [str(p) for p in (ROOT / "scripts").glob("*.ps1")]
    check = Path(tempfile.mkdtemp()) / "parse.ps1"
    check.write_text("$bad=0; foreach($f in $args){$t=$null;$e=$null;"
                     "[System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$t,[ref]$e)|Out-Null;"
                     "if($e.Count){$bad++; Write-Output ($f + ': ' + $e[0].Message)}}; exit $bad", encoding="utf-8")
    r = subprocess.run([pwsh, "-NoProfile", "-File", str(check)] + files, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr


def test_vivarium_cleared_ground_gets_no_template_base():
    """The world remembers: zones nobody holds get no enemy base; Armada's still do."""
    import shutil, subprocess, tempfile
    pwsh = shutil.which("pwsh") or ("/opt/pwsh/pwsh" if Path("/opt/pwsh/pwsh").exists() else None)
    if not pwsh:
        return
    tpl = ROOT / "data" / "base_templates" / "greenest_fields" / "armada_placeholder_v1.json"
    zones = {u.get("zoneId") for u in json.loads(tpl.read_text(encoding="utf-8-sig")).get("units") or [] if u.get("zoneId")}
    def run(ctrl):
        st = {"zoneMemory": {"greenest_fields": {z: {"controllingFaction": ctrl(z)} for z in zones}}}
        sp = Path(tempfile.mkdtemp()) / "state.json"
        sp.write_text(json.dumps(st), encoding="utf-8")
        r = subprocess.run([pwsh, "-NoProfile", "-File", str(ROOT / "tools" / "hud_harness" / "shell_probe.ps1"),
                            "-Script", str(ROOT / "scripts" / "build_next_mission_v1.ps1"), "-StatePath", str(sp),
                            "-TemplatePath", str(tpl)], capture_output=True, text=True, timeout=300)
        line = next((l for l in r.stdout.splitlines() if "kept=" in l), "")
        assert line, r.stdout + r.stderr
        return int(line.split("kept=")[1].split()[0])
    assert run(lambda z: "neutral") == 0
    one = sorted(zones)[0]
    assert run(lambda z: "armada" if z == one else "neutral") > 0
