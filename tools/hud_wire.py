#!/usr/bin/env python3
"""The wire between the gadgets (luarules) and the HUD (luaui): does every signal have both ends?

Four kinds of signal cross it:

  rules params    the gadgets publish (Set{Game,Unit,Feature}RulesParam); widgets read (Get...).
  events          a synced gadget calls SendToUnsynced("NAME", ...); an unsynced half catches it
                  (AddSyncAction "NAME") and calls Script.LuaUI.Fn; a widget registers Fn
                  (widgetHandler:RegisterGlobal). A widget that only defines widget:Fn never hears
                  it: BAR links its own call-in names, not ours.
  commands        a widget sends SendLuaRulesMsg("VA_CMD:<cmd>"); a gadget handles <cmd>.
  WG              one widget sets WG.x; another reads it.

    python3 tools/hud_wire.py            # exit 1 when a HUD signal has only one end
    python3 tools/hud_wire.py --orphans  # also list params a gadget writes that nothing reads
    python3 tools/hud_wire.py --all      # also list every rules param with its ends

A param read by a widget (or a gadget) that nothing writes is a reader reading nothing; an event
or a command with one end is a wire cut. Those fail. A param a gadget writes that nothing reads is
listed with --orphans only: many are kept for a person reading the infolog or a debugger. Names
built at run time ("va_seen_" .. zone) are matched by prefix.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "mod" / "VerdanceAshes.sdd"
GADGETS = MOD / "luarules" / "gadgets"
LUAUI = MOD / "luaui"
# BAR's own gadget files that live in our tree (copied in, not ours to wire).
FOREIGN = {"raptor_spawner_defense.lua", "unit_footprint_clearance.lua"}
KINDS = ("Game", "Unit", "Feature", "Team")
# Ends that are meant to be open: the HUD harness's redirect for the live report.
SEAMS = {"WG.vaLivePath"}


def strip_comments(src: str) -> str:
    """Blank Lua comments, keep strings and line numbers."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1; continue
        m = re.match(r"\[(=*)\[", src[i:i + 8])
        if m:
            close = "]" + m.group(1) + "]"
            j = src.find(close, i); j = n if j < 0 else j + len(close)
            out.append(src[i:j]); i = j; continue
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:i + 10])
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, i); j = n if j < 0 else j + len(close)
            else:
                j = src.find("\n", i); j = n if j < 0 else j
            out.append(re.sub(r"[^\n]", " ", src[i:j])); i = j; continue
        out.append(c); i += 1
    return "".join(out)


def lua_files():
    for p in sorted(GADGETS.rglob("*.lua")):
        yield ("foreign" if p.name in FOREIGN else "gadget"), p
    for p in sorted(LUAUI.rglob("*.lua")):
        yield "widget", p


# A key argument: "lit", or "prefix" .. expr (a run-time name, matched by prefix).
KEY = r"""\s*(?:"([^"\n]*)"|'([^'\n]*)')(\s*\.\.)?"""


def key_of(m, base):
    lit = m.group(base) if m.group(base) is not None else m.group(base + 1)
    return lit + ("*" if m.group(base + 2) else "")


def wrappers(src: str):
    """Local helpers that pass their first parameter on as a rules-param key:
    `local function num(name, d) return tonumber(Spring.GetGameRulesParam(name)) ... end`."""
    found = {}
    for m in re.finditer(r"(?:local\s+)?function\s+([\w.:]+)\s*\(\s*(\w+)", src):
        fn, p = m.group(1).split(".")[-1].split(":")[-1], m.group(2)
        body = src[m.end():m.end() + 400]
        body = body[:body.find("\nend") if "\nend" in body else len(body)]
        w = re.search(r"Spring\.(Get|Set)(%s)RulesParam\s*\(\s*(?:\w+\s*,\s*)?%s\b" % ("|".join(KINDS), p), body)
        if w:
            found[fn] = (w.group(1), w.group(2))
    return found


def scan():
    params = collections.defaultdict(lambda: {"w": set(), "r": set()})   # (kind, key) -> ends
    events = collections.defaultdict(lambda: {"send": set(), "catch": set()})
    luaui_fns = collections.defaultdict(lambda: {"call": set(), "reg": set(), "def": set()})
    cmds = collections.defaultdict(lambda: {"send": set(), "handle": set()})
    wg = collections.defaultdict(lambda: {"set": set(), "get": set()})
    shared = {}   # the HUD library's readers (luaui/Include/va_hud.lua: Hud.num, Hud.str, ...)
    for p in sorted((LUAUI / "Include").glob("*.lua")):
        shared.update(wrappers(strip_comments(p.read_text(errors="replace"))))
    for side, p in lua_files():
        src = strip_comments(p.read_text(errors="replace"))
        where = f"{p.relative_to(MOD)}"
        def line(pos):
            return f"{where}:{src.count(chr(10), 0, pos) + 1}"
        # direct rules-param calls
        for m in re.finditer(r"Spring\.(Get|Set)(%s)RulesParam\s*\(\s*(?:[^,()\"']+(?:\([^()]*\))?\s*,\s*)?%s" % ("|".join(KINDS), KEY), src):
            k = key_of(m, 3)
            params[(m.group(2), k)]["w" if m.group(1) == "Set" else "r"].add(line(m.start()))
        for m in re.finditer(r"pcall\s*\(\s*Spring\.(Get|Set)(%s)RulesParam\s*,\s*(?:[^,()\"']+\s*,\s*)?%s" % ("|".join(KINDS), KEY), src):
            params[(m.group(2), key_of(m, 3))]["w" if m.group(1) == "Set" else "r"].add(line(m.start()))
        if side == "foreign":
            # BAR's file with our one line in it: count what it writes for us, nothing else
            for m in re.finditer(r"SetGameRulesParam\s*\(%s" % KEY, src):
                if key_of(m, 1).startswith("va_"):
                    params[("Game", key_of(m, 1))]["w"].add(line(m.start()))
            continue
        # through a wrapper: this file's own, or the HUD library's (Hud.num, or num = Hud.num)
        own = wrappers(src)
        for fn, (gs, kind) in list(own.items()) + list(shared.items()):
            if fn in own:
                pat = r"(?<![\w.:])%s\s*\(%s" % (re.escape(fn), KEY)
            elif re.search(r"\bHud\.%s\b" % re.escape(fn), src):
                # Hud.num("k") always; a bare num("k") only when the file took num from Hud
                bare = re.search(r"(?m)^local\s+[\w\s,]*\b%s\b[\w\s,]*=.*\bHud\.%s\b" % (re.escape(fn), re.escape(fn)), src)
                pat = r"(?:\bHud\.%s|%s)\s*\(%s" % (re.escape(fn), (r"(?<![\w.:])" + re.escape(fn)) if bare else r"(?!)", KEY)
            else:
                continue
            for m in re.finditer(pat, src):
                k = key_of(m, 1)
                params[(kind, k)]["w" if gs == "Set" else "r"].add(line(m.start()))
        for m in re.finditer(r"SendToUnsynced\s*\(%s" % KEY, src):
            events[key_of(m, 1)]["send"].add(line(m.start()))
        for m in re.finditer(r"AddSyncAction\s*\(%s" % KEY, src):
            events[key_of(m, 1)]["catch"].add(line(m.start()))
        for m in re.finditer(r"Script\.LuaUI\.(\w+)\s*\(", src):
            luaui_fns[m.group(1)]["call"].add(line(m.start()))
        for m in re.finditer(r"RegisterGlobal\s*\(\s*(?:widget\s*,\s*)?%s" % KEY, src):
            luaui_fns[key_of(m, 1)]["reg"].add(line(m.start()))
        if side == "widget":
            for m in re.finditer(r"function\s+widget:(\w+)\s*\(", src):
                luaui_fns[m.group(1)]["def"].add(line(m.start()))
            for m in re.finditer(r"SendLuaRulesMsg\s*\(%s" % KEY, src):
                k = key_of(m, 1)
                if k.startswith("VA_CMD:"):
                    cmds[re.split(r"[ :*]", k[7:])[0] or "*"]["send"].add(line(m.start()))
        for m in re.finditer(r"\bWG\.(\w+)\s*=(?!=)", src):
            wg[m.group(1)]["set"].add(line(m.start()))
        for m in re.finditer(r"\bWG\.(\w+)\b(?!\s*=(?!=))", src):
            wg[m.group(1)]["get"].add(line(m.start()))
    # VA_CMD handlers: a gadget names the command in a string literal it matches against
    # ("^vahotdrop ", "VA_CMD:manifest", "extract:", or a table key / == compare).
    gsrc = "\n".join(strip_comments(p.read_text(errors="replace")) for side, p in lua_files() if side == "gadget")
    for c, e in cmds.items():
        pat = r"""["'](?:\^|VA_CMD:)?%s(?:["' :%%]|\b)|\b%s\s*=\s*(?:true|function)""" % (re.escape(c), re.escape(c))
        if c == "*" or re.search(pat, gsrc):
            e["handle"].add("gadgets")
    return params, events, luaui_fns, cmds, wg, vocab()


# Events that carry a kind as their first argument: which kinds are sent, which the HUD tells apart.
# Senders: SendToUnsynced(CHANNEL, "kind") and the gadgets' own relays (name("kind")).
CHANNELS = {
    "VERDANCE_MISSION_EVENT": ("VerdanceMissionEvent", ("marksCommit",)),
    "VERDANCE_HERO_EVENT": ("VerdanceHeroEvent", ("broadcastHeroEvent",)),
    "VERDANCE_BEAT": ("VerdanceBeat", ()),
}


def vocab():
    out = {}
    gad = [(p, strip_comments(p.read_text(errors="replace"))) for side, p in lua_files() if side == "gadget"]
    wid = [(p, strip_comments(p.read_text(errors="replace"))) for side, p in lua_files() if side == "widget"]
    for ch, (fn, relays) in CHANNELS.items():
        sent, heard = collections.defaultdict(set), collections.defaultdict(set)
        for p, src in gad:
            pats = [r"SendToUnsynced\s*\(\s*\"%s\"\s*,\s*\"(\w+)\"" % ch]
            pats += [r"(?<![\w.:])%s\s*\(\s*\"(\w+)\"" % r for r in relays]
            for pat in pats:
                for m in re.finditer(pat, src):
                    sent[m.group(1)].add(f"{p.relative_to(MOD)}:{src.count(chr(10), 0, m.start()) + 1}")
        for p, src in wid:
            reg = re.search(r"RegisterGlobal\s*\(\s*(?:widget\s*,\s*)?[\"']%s[\"']\s*,\s*function\s*\([^)]*\)\s*([\w:.]+)\s*\(" % fn, src)
            if not reg:
                continue
            # the handler the global calls: its body, up to the next top-level `end`
            name = re.escape(reg.group(1))
            h = re.search(r"(?m)^(?:local\s+)?function\s+%s\s*\(" % name, src)
            if not h:
                continue
            body_end = re.search(r"(?m)^end\b", src[h.end():])
            body = src[h.start():h.end() + (body_end.end() if body_end else len(src))]
            for m in re.finditer(r"\b(?:ev|event|kind)\s*==\s*\"(\w+)\"", body):
                heard[m.group(1)].add(f"{p.relative_to(MOD)}:{src.count(chr(10), 0, h.start() + m.start()) + 1}")
            # or a table of handlers looked up by kind: ON_MISSION[ev]
            for t in re.finditer(r"\b(\w+)\[(?:ev|event|kind)\]", body):
                tbl = re.search(r"(?m)^local\s+%s\s*=\s*\{(.*?)^\}" % re.escape(t.group(1)), src, re.S)
                if not tbl:
                    continue
                for k in re.finditer(r"(?m)^  (\w+)\s*=", tbl.group(1)):
                    heard[k.group(1)].add(f"{p.relative_to(MOD)}:{src.count(chr(10), 0, tbl.start(1) + k.start()) + 1}")
        out[ch] = (sent, heard)
    return out


def matches(key, keys):
    """Ends of a param: exact name, or a prefix (va_seen_*) on either side."""
    if key.endswith("*"):
        pre = key[:-1]
        return [k for k in keys if k.rstrip("*").startswith(pre) or pre.startswith(k.rstrip("*"))]
    return [k for k in keys if k == key or (k.endswith("*") and key.startswith(k[:-1]))]


def problems(params, events, luaui_fns, cmds, wg, vocab):
    out = []
    for ch, (sent, heard) in sorted(vocab.items()):
        for k in sorted(set(sent) - set(heard)):
            out.append(("sent, HUD ignores it", f"{ch} {k}", sorted(sent[k])))
        for k in sorted(set(heard) - set(sent)):
            out.append(("handled, never sent", f"{ch} {k}", sorted(heard[k])))
    by_kind = collections.defaultdict(dict)
    for (kind, key), ends in params.items():
        by_kind[kind][key] = ends
    for kind, keys in by_kind.items():
        written = {k for k, e in keys.items() if e["w"]}
        read = {k for k, e in keys.items() if e["r"]}
        for k in sorted(read):
            if k.startswith("va_") or k.startswith("va"):
                if not matches(k, written):
                    out.append(("read, never written", f"{kind} param {k}", sorted(keys[k]["r"])))
        for k in sorted(written):
            if not matches(k, read):
                out.append(("orphan: written, never read", f"{kind} param {k}", sorted(keys[k]["w"])))
    for ev, e in sorted(events.items()):
        if e["send"] and not e["catch"]:
            out.append(("sent, never caught", f"event {ev}", sorted(e["send"])))
        if e["catch"] and not e["send"]:
            out.append(("caught, never sent", f"event {ev}", sorted(e["catch"])))
    for fn, e in sorted(luaui_fns.items()):
        if e["call"] and not e["reg"]:
            how = "defined as widget:%s but never registered" % fn if e["def"] else "no widget registers it"
            out.append(("forwarded, never heard", f"Script.LuaUI.{fn} ({how})", sorted(e["call"] | e["def"])))
    for c, e in sorted(cmds.items()):
        if e["send"] and not e["handle"]:
            out.append(("sent, never handled", f"VA_CMD:{c}", sorted(e["send"])))
    for k, e in sorted(wg.items()):
        if e["get"] and not e["set"] and f"WG.{k}" not in SEAMS:
            out.append(("read, never set", f"WG.{k}", sorted(e["get"])))
    return out


def hud_problems():
    return [p for p in problems(*scan()) if not p[0].startswith("orphan")]


def main(argv):
    wire = scan()
    probs = problems(*wire)
    if "--all" in argv:
        for (kind, key), e in sorted(wire[0].items()):
            print(f"{kind:7} {key:40} w={len(e['w'])} r={len(e['r'])}")
    cut = [p for p in probs if not p[0].startswith("orphan")]
    shown = probs if "--orphans" in argv else cut
    for what, name, where in shown:
        print(f"{what:28} {name}\n{'':28} {', '.join(where[:4])}{' ...' if len(where) > 4 else ''}")
    orphans = len(probs) - len(cut)
    print(f"hud wire: {len(cut)} cut signal(s); {orphans} orphan param(s) (--orphans lists them)")
    return 1 if cut else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
