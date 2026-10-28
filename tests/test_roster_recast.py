"""The roster recast of 2026-10-28 (owner's line-by-line calls on the sameness review).

Every pack below is exactly what was asked for; the people retired are gone from every file; the
two new heroes and Choir's new ties are woven in; the Lua roster is generated from the JSON."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "data" / "story"
MOD = ROOT / "mod" / "VerdanceAshes.sdd"


def _j(p):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


PACKS = _j(S / "crew_packs.json")
H = PACKS["heroes"]


def _esc(h):
    return {e["unitDef"]: e["count"] for e in H[h].get("escorts") or []}


WANT = {  # hero: (lead unit, packTotal, escorts)
    "twitch": ("corfast", 1, {"va_printer": 1}),
    "consul": ("armconsul", 1, {"armfark": 2}),
    "mason": ("legck", 1, {"legmlv": 2, "legdrag": 10, "legforti": 4}),
    "mask": ("va_mask", 1, {"armpw": 10, "armfify": 3}),
    "rookery": ("armca", 3, {"armfig": 4, "corveng": 2, "legionnaire": 2, "legvenator": 2}),
    "dam": ("armbeaver", 4, {}),
    "lumen": ("va_lumen", 1, {"armseer": 1, "armjam": 1}),   # builds only Prudes and Pulsars; a radar and a jammer
    "gorgon": ("legmed", 1, {"armyork": 2}),
    "pavise": ("armwar", 1, {"leglob": 5}),
    "yeva": ("armsnipe", 1, {"armflea": 6}),
    "spoke": ("legvp", 1, {"legmstor": 1}),
    "tick": ("armlab", 1, {"armmstor": 1}),
    "noctua": ("legap", 1, {"legmstor": 1}),
    "fatboy": ("armfboy", 1, {"legrail": 2}),
    "stride": ("va_mav_stride", 3, {}),
    "hearth": ("armckfus", 1, {}),
    "warder": ("cordoom", 1, {}),
    "kettle": ("va_kettle", 1, {"legatrans": 2}),
    "vale": ("armmerl", 1, {"corvroc": 1, "legavroc": 1}),
    "loom": ("armspid", 6, {"legbal": 6}),
    "anvil": ("armcroc", 2, {}),
    "volt": ("armlatnk", 1, {"armflash": 6}),
    "rumor": ("va_ghost", 1, {"legaspy": 2, "armgremlin": 2}),
    "tsunami": ("armsb", 1, {"legspbomber": 2, "armpeep": 5}),
    "starlight": ("armmanni", 1, {"armfast": 4}),
    "hornet": ("armblade", 2, {}),
    "stiletto": ("armstil", 3, {"legwhisper": 1}),
    "hundred": ("legspcarrier", 1, {"legamcluster": 2}),
    "lunkhead": ("armlun", 1, {"legcar": 2}),
    "possum": ("armmh", 1, {"legsh": 4, "legmh": 5, "legah": 2}),
    "arc": ("armzeus", 1, {"armsam": 6}),
    "vane": ("legstr", 1, {"legcen": 10}),
    "ketha": ("legrezbot", 5, {}),
    "odessa": ("legamph", 1, {"armpincer": 5}),
    "cauter": ("legshot", 1, {"legkark": 3}),
    "rusk": ("leggat", 5, {}),
    "grath": ("legaheattank", 1, {"leghelios": 3}),
    "halq": ("legaradk", 1, {"armrock": 8}),
    "mira": ("armmart", 5, {"legavrad": 1}),
    "kit": ("legbart", 1, {"legbar": 1, "legamcluster": 1, "legrail": 1, "legsrail": 1, "leghrk": 1}),
    "infestor": ("va_infestor", 4, {"armsptk": 2}),
    "scylla": ("leganavybattleship", 1, {}),
    "charybdis": ("legehovertank", 1, {}),
    "gladius": ("legaskirmtank", 6, {}),
    "triton": ("legfloat", 1, {"armanac": 8}),
    "commando": ("va_cormando", 1, {"va_cormlv_fast": 4, "corvalk": 1}),
    "bro": ("corgol", 1, {}),
    "halbard": ("va_halberd", 1, {"legah": 3, "legner": 4}),
    "gale": ("corcut", 6, {}),
    "banisher": ("corban", 3, {}),
    "arrow": ("corparrow", 1, {"corsala": 6}),
    "shiva": ("corshiva", 1, {}),
    "tremor": ("cortrem", 1, {"corspec": 1, "corfav": 5}),
    "mammoth": ("corsumo", 1, {}),
}
RETIRED = ("ceil", "marauder", "tarn")


def test_every_pack_is_as_called():
    costs = _j(S / "unit_costs.json")["units"]
    for h, (unit, total, esc) in WANT.items():
        p = H[h]
        assert (p["unitDef"], p["packTotal"], p["extras"], _esc(h)) == (unit, total, total - 1, esc), h
        for u in [unit, *esc]:
            assert u.startswith("va_") or (u in PACKS["chassis"] and u in costs), (h, u)


def test_the_retired_are_gone_everywhere():
    for f in list(S.glob("*.json")) + [MOD / "luarules/gadgets/include/va_crew_roster.lua",
                                       MOD / "luarules/gadgets/include/va_hero_tags.lua", ROOT / "tools/verdance/company/company.py"]:
        txt = f.read_text(encoding="utf-8-sig")
        for r in RETIRED:
            assert not re.search(r'"' + r + r'"|\b' + r + r' = \{|"' + r + r'__|__' + r + r'"', txt), (f.name, r)


def test_the_new_people_have_a_voice_and_ties():
    codex = {h["heroId"]: h for h in _j(S / "hero_codex.json")["heroes"]}
    web = _j(S / "support_web.json")
    for h, name in (("loom", "Orla 'Loom' Vey"), ("hundred", "Thessaly 'Hundred' Orne"), ("arc", "Ambrose 'Choir' Halloran"),
                    ("hornet", "Teague & Saffi Marsh"), ("gorgon", "Ivra 'Gorgon' Maelis")):
        assert codex[h]["name"] == name and codex[h]["voice"]["hook"] and codex[h]["voice"]["fiction"], h
        assert H[h]["name"] == name, h
    for h in ("loom", "hundred", "arc", "gorgon"):
        ties = {e["polarity"] for e in web["edges"] if h in (e["a"], e["b"]) and e.get("authored")}
        assert ties & {"bond", "attract", "sibling", "mentor", "mirror"} and ties & {"rivalry", "tension", "friction"}, h


def test_the_lua_roster_is_generated_from_the_json():
    out = subprocess.run([sys.executable, str(ROOT / "tools/sync_crew_roster.py"), "--check"], capture_output=True)
    assert out.returncode == 0, "va_crew_roster.lua is out of date: run tools/sync_crew_roster.py"
    lua = (MOD / "luarules/gadgets/include/va_crew_roster.lua").read_text(encoding="utf-8")
    assert all(f"\n  {h} = {{" in lua for h in WANT)
    assert all(H[h].get("packMind") for h in H), "packMind lives in the JSON now"


def test_nox_keeps_its_umbrella():
    # The Traveler is BAR's Umbrella mobile anti-nuke: it builds nothing, so no fighters and no Storks.
    assert H["nox"]["unitDef"] == "armscab" and _esc("nox") == {"armferret": 1}


def test_lumen_raises_only_prudes_and_pulsars():
    src = (MOD / "units/va_lumen.lua").read_text(encoding="utf-8")
    assert 'def.buildoptions = { "armgmm", "armanni" }' in src


def test_every_hero_has_a_friend_a_rival_and_a_tie_across_factions():
    """The enrichment round (2026-10-28 evening): nobody's web is one-sided or one-faction."""
    web = _j(S / "support_web.json")
    codex = {h["heroId"]: h for h in _j(S / "hero_codex.json")["heroes"]}
    ally = {"bond", "attract", "sibling", "mentor", "mirror"}
    for h in H:
        ties = [e for e in web["edges"] if e.get("authored") and h in (e["a"], e["b"])]
        assert len(ties) >= 4, (h, len(ties))
        assert any(e["polarity"] in ally for e in ties) and any(e["polarity"] not in ally for e in ties), h
        assert any(codex[e["a"]]["faction"] != codex[e["b"]]["faction"] for e in ties), h
    stale = [e for e in web["edges"] if {e["a"], e["b"]} == {"consul", "shiva"}]
    assert stale and not any("Grunts need paperwork" in m for m in stale[0]["motifs"])
