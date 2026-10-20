#!/usr/bin/env python3
"""Heuristic Lua 5.1 structure check (no interpreter available): strips comments/strings,
then checks bracket balance and block balance (function/if/for/while/do/repeat ... end/until).
Reports the line of the first imbalance. Not a parser; catches the usual slips."""
import re, sys

KW_OPEN = {"function", "if", "for", "while", "do", "repeat"}

def strip(src):
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                close = "]" + m.group(1) + "]"
                j = src.find(close, i)
                j = n if j < 0 else j + len(close)
                out.append("\n" * src[i:j].count("\n")); i = j; continue
            j = src.find("\n", i); j = n if j < 0 else j
            i = j; continue
        if c in "\"'":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\": j += 1
                if src[j:j+1] == "\n": return None, f"unterminated string at line {src.count(chr(10),0,i)+1}"
                j += 1
            out.append('""'); i = j + 1; continue
        m = re.match(r"\[(=*)\[", src[i:])
        if m:
            close = "]" + m.group(1) + "]"
            j = src.find(close, i)
            j = n if j < 0 else j + len(close)
            out.append('""' + "\n" * src[i:j].count("\n")); i = j; continue
        out.append(c); i += 1
    return "".join(out), None

def check(path):
    src = open(path, encoding="utf-8").read()
    code, err = strip(src)
    if err: return err
    depth = 0; stack = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    for ln, line in enumerate(code.split("\n"), 1):
        for ch in line:
            if ch in pairs: stack.append((ch, ln))
            elif ch in ")]}":
                if not stack or pairs[stack[-1][0]] != ch: return f"bracket mismatch '{ch}' at line {ln}"
                stack.pop()
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", line)
        # 'for'/'while' use 'do' as part of the same block: count do only when not preceded by for/while on the line
        i = 0
        while i < len(toks):
            t = toks[i]
            if t in ("for", "while"):
                depth += 1
                # skip the matching 'do'
                try:
                    k = toks.index("do", i + 1); del toks[k]
                except ValueError:
                    pass
            elif t in ("function", "if", "do", "repeat"):
                depth += 1
            elif t in ("end", "until"):
                depth -= 1
                if depth < 0: return f"extra 'end' at line {ln}"
            i += 1
    if stack: return f"unclosed '{stack[-1][0]}' from line {stack[-1][1]}"
    if depth != 0: return f"block depth {depth} at EOF (missing 'end')"
    return None

if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        e = check(p)
        print(("FAIL " + e if e else "ok  ") + "  " + p)
        bad += bool(e)
    sys.exit(1 if bad else 0)
