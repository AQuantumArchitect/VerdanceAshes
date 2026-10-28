"""The campaign gadget's parts stay consistent (tools/campaign_parts.py).

Every global a part reads is defined by some part (or is the engine's), and each part's
"Provides:" / "Uses:" header says what the code does.
"""
from __future__ import annotations

import campaign_lua
import campaign_parts


def test_every_part_exists_and_the_core_includes_it():
    names = [n for n, _ in campaign_lua.parts()]
    assert names[0] == "core" and len(names) > 10
    for name, path in campaign_lua.parts():
        assert path.is_file(), f"{name}: {path}"
    listed = {p.stem for p in campaign_lua.PARTS.glob("*.lua")}
    assert listed == set(names[1:]), f"parts not included by the core: {listed - set(names[1:])}"


def test_no_part_reads_a_name_nobody_defines():
    _files, _prov, _uses, undefined = campaign_parts.analyse()
    assert not undefined, "\n".join(f"{p}.lua:{l} {n}" for p, l, n in undefined)


def test_headers_match_the_code():
    files, provides, uses, _ = campaign_parts.analyse()
    for part, path in files.items():
        if part == "core":
            continue
        _head, cur, _rest = campaign_parts._split_header(path.read_text(encoding="utf-8"))
        assert cur == campaign_parts.header_lines(part, provides, uses), \
            f"{part}.lua header is stale: python3 tools/campaign_parts.py --fix"
