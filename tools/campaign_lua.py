"""The campaign gadget's Lua source, whole: game_verdance_campaign.lua plus the parts it includes.

The gadget is split into luarules/gadgets/include/campaign/*.lua, loaded into the gadget's own
environment in the order the core file includes them. Tests and harnesses that read or lift code
from the gadget use this instead of opening the core file.

    from campaign_lua import source, parts, part_path
    source()            # every part, in load order, as one string
    parts()             # [(name, path)] in load order, the core first
    part_path("heroes") # path of one part
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GADGETS = ROOT / "mod" / "VerdanceAshes.sdd" / "luarules" / "gadgets"
CORE = GADGETS / "game_verdance_campaign.lua"
PARTS = GADGETS / "include" / "campaign"
_INCLUDE = re.compile(r'VFS\.Include\("luarules/gadgets/include/campaign/(\w+)\.lua", gadget\)')


def part_path(name: str) -> Path:
    return CORE if name == "core" else PARTS / f"{name}.lua"


def parts() -> list[tuple[str, Path]]:
    core = CORE.read_text(encoding="utf-8")
    return [("core", CORE)] + [(n, part_path(n)) for n in _INCLUDE.findall(core)]


def source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for _, p in parts())


__all__ = ["CORE", "PARTS", "part_path", "parts", "source"]
