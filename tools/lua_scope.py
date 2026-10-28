"""A small Lua reader for the campaign gadget's tooling: tokens, top-level items, scope-resolved names.

    lex(src)                 -> [(type, value, line)]       type: name | kw | str | num | op
    items(src)               -> [{start, end, kind, names, uses}]   top-level statements
                                kind: local_fn | local_var | global_fn | global_var | stmt
    Resolver(src).run().refs -> {(line, ordinal): (name, binding)}
                                binding: ('L', decl_line, name) for a local, ('G', name) for a global

Not a full parser: enough to say, for every name in a file, which declaration it means. Used by
tools/campaign_parts.py (and the split of game_verdance_campaign.lua into include/campaign/).
"""
from __future__ import annotations

import re

KW = set("and break do else elseif end false for function goto if in local nil not or repeat return then true until while".split())

def lex(src):
    i, n, line = 0, len(src), 1
    toks = []
    while i < n:
        c = src[i]
        if c == '\n':
            line += 1; i += 1; continue
        if c in ' \t\r':
            i += 1; continue
        if src.startswith('--', i):
            m = re.match(r'--\[(=*)\[', src[i:])
            if m:
                close = ']' + m.group(1) + ']'
                j = src.find(close, i + len(m.group(0)))
                j = n if j < 0 else j + len(close)
                line += src.count('\n', i, j); i = j; continue
            j = src.find('\n', i)
            i = n if j < 0 else j
            continue
        m = re.match(r'\[(=*)\[', src[i:])
        if m:
            close = ']' + m.group(1) + ']'
            j = src.find(close, i + len(m.group(0)))
            j = n if j < 0 else j + len(close)
            toks.append(('str', '', line)); line += src.count('\n', i, j); i = j; continue
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\': j += 1
                if j < n and src[j] == '\n': line += 1
                j += 1
            toks.append(('str', '', line)); i = j + 1; continue
        m = re.match(r'[A-Za-z_][A-Za-z0-9_]*', src[i:])
        if m:
            w = m.group(0)
            toks.append(('kw' if w in KW else 'name', w, line)); i += len(w); continue
        m = re.match(r'0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?', src[i:])
        if m:
            toks.append(('num', m.group(0), line)); i += len(m.group(0)); continue
        m = re.match(r'\.\.\.|\.\.|==|~=|<=|>=|::|[-+*/%^#<>=(){}\[\];:,.]', src[i:])
        if m:
            toks.append(('op', m.group(0), line)); i += len(m.group(0)); continue
        i += 1
    return toks


def items(src):
    toks = lex(src)
    out = []
    depth = 0
    paren = 0
    cur = None
    k = 0
    def flush(end_line):
        nonlocal cur
        if cur:
            cur['end'] = end_line
            out.append(cur)
        cur = None
    while k < len(toks):
        t, v, ln = toks[k]
        if depth == 0 and paren == 0:
            starts = False
            prevt = toks[k - 1] if k else None
            after_decl = prevt is not None and prevt[0] == 'kw' and prevt[1] in ('local', 'function')
            if after_decl:
                starts = False
            elif t == 'kw' and v in ('local', 'function', 'if', 'for', 'while', 'do', 'repeat', 'return'):
                # `x = function() ... end` is one statement: a function after `=` or `,` is a value
                starts = not (v == 'function' and prevt is not None and prevt[1] in ('=', ',', '(', '{', 'return', 'and', 'or'))
            elif t == 'name' and not after_decl:
                prev = toks[k - 1] if k else None
                if not prev or not (prev[0] == 'op' and prev[1] in ('.', ':', ',', '=', '(', '[', '..', '+', '-', '*', '/', 'and', 'or')) and not (prev[0] in ('name', 'str', 'num') or (prev[0] == 'op' and prev[1] in (')', ']', '}'))):
                    starts = True
                elif prev and (prev[0] in ('name', 'str', 'num') or (prev[0] == 'kw' and prev[1] in ('end', 'true', 'false', 'nil')) or (prev[0] == 'op' and prev[1] in (')', ']', '}'))) :
                    starts = True
            if starts:
                flush(toks[k - 1][2] if k else ln)
                cur = {'start': ln, 'kind': 'stmt', 'names': [], 'uses': set()}
                if t == 'kw' and v == 'local':
                    if toks[k + 1][1] == 'function':
                        cur['kind'] = 'local_fn'; cur['names'] = [toks[k + 2][1]]
                    else:
                        cur['kind'] = 'local_var'
                        j = k + 1
                        while j < len(toks) and toks[j][0] == 'name':
                            cur['names'].append(toks[j][1])
                            if toks[j + 1][1] == ',': j += 2
                            else: break
                elif t == 'kw' and v == 'function':
                    j = k + 1; parts = []
                    while toks[j][0] == 'name' or toks[j][1] in ('.', ':'):
                        parts.append(toks[j][1]); j += 1
                    cur['kind'] = 'global_fn'; cur['names'] = [''.join(parts)]
                elif t == 'name':
                    j = k; parts = []
                    while toks[j][0] == 'name' or toks[j][1] == '.':
                        parts.append(toks[j][1]); j += 1
                    if toks[j][1] in ('=', ','):
                        cur['kind'] = 'global_var'; cur['names'] = [''.join(parts)]
        if cur is not None and t == 'name':
            prev = toks[k - 1] if k else None
            if not (prev and prev[0] == 'op' and prev[1] in ('.', ':')):
                cur['uses'].add(v)
        if t == 'kw':
            if v in ('function', 'if', 'do', 'repeat'):
                depth += 1
            elif v in ('end', 'until'):
                depth -= 1
        elif t == 'op':
            if v in ('(', '{', '['): paren += 1
            elif v in (')', '}', ']'): paren -= 1
        k += 1
    flush(toks[-1][2])
    return out


STMT_KW = {'local', 'if', 'for', 'while', 'repeat', 'return', 'break', 'do', 'end', 'else', 'elseif',
           'until', 'goto'}
OPERAND_END_KW = {'nil', 'true', 'false', 'end'}


class Resolver:
    def __init__(self, src, lmap=None):
        self.t = lex(src)
        self.n = len(self.t)
        self.lmap = lmap
        self.scopes = [{}]
        self.blocks = ['chunk']
        self.pending = []          # (activate_at, scope_dict, [(name, id)])
        self.next_do = None        # for-loop variables waiting for their `do`
        self.refs = {}             # (orig_line, ordinal) -> (name, binding)
        self.ordinal = {}
        self.brack = []
        self.toplevel = set()      # decl ids declared in the chunk scope

    def L(self, line):
        return self.lmap[line - 1] if self.lmap else line

    def ordn(self, line):
        o = self.ordinal.get(line, 0)
        self.ordinal[line] = o + 1
        return o

    def lookup(self, name):
        for sc in reversed(self.scopes):
            if name in sc:
                return ('L',) + sc[name]
        return ('G', name)

    def declare(self, scope, name, line):
        d = (self.L(line), name)
        scope[name] = d
        if scope is self.scopes[0]:
            self.toplevel.add(d)

    def ref(self, k):
        _, v, ln = self.t[k]
        o = self.ordn(ln)
        self.refs[(self.L(ln), o)] = (v, self.lookup(v))

    def skip_name(self, k):
        self.ordn(self.t[k][2])

    def stmt_end(self, k):
        depth = fdepth = 0
        prev = None
        j = k
        while j < self.n:
            t, v, _ = self.t[j]
            if depth == 0 and fdepth == 0 and prev is not None:
                prev_end = prev[0] in ('name', 'num', 'str') or (prev[0] == 'op' and prev[1] in (')', ']', '}', '...')) \
                    or (prev[0] == 'kw' and prev[1] in OPERAND_END_KW)
                if t == 'kw' and v in STMT_KW:
                    return j
                if prev_end and (t == 'name' or (t == 'kw' and v == 'function')):
                    return j
                if t == 'op' and v == ';':
                    return j
            if t == 'op' and v in ('(', '{', '['):
                depth += 1
            elif t == 'op' and v in (')', '}', ']'):
                depth -= 1
            elif t == 'kw' and v == 'function':
                fdepth += 1
            elif t == 'kw' and fdepth and v in ('if', 'do', 'repeat'):
                fdepth += 1
            elif t == 'kw' and fdepth and v in ('end', 'until'):
                fdepth -= 1
            prev = (t, v)
            j += 1
        return self.n

    def open_function(self, j, method):
        """j at '(' of the parameter list. Returns index after ')'."""
        assert self.t[j][1] == '(', self.t[j]
        sc = {}
        if method:
            sc['self'] = (self.L(self.t[j][2]), 'self')
        j += 1
        while self.t[j][1] != ')':
            if self.t[j][0] == 'name':
                self.skip_name(j)
                sc[self.t[j][1]] = (self.L(self.t[j][2]), self.t[j][1])
            j += 1
        self.scopes.append(sc)
        self.blocks.append('func')
        return j + 1

    def close(self):
        self.scopes.pop()
        self.blocks.pop()

    def run(self):
        t = self.t
        k = 0
        while k < self.n:
            while self.pending and self.pending[0][0] <= k:
                _, sc, names = self.pending.pop(0)
                for nm, line in names:
                    self.declare(sc, nm, line)
            typ, v, ln = t[k]
            if typ == 'kw' and v == 'local':
                if t[k + 1][1] == 'function':
                    self.skip_name(k + 2)
                    self.declare(self.scopes[-1], t[k + 2][1], t[k + 2][2])
                    k = self.open_function(k + 3, False)
                    continue
                names, j = [], k + 1
                while j < self.n and t[j][0] == 'name':
                    self.skip_name(j)
                    names.append((t[j][1], t[j][2]))
                    j += 1
                    if j < self.n and t[j][1] == ',':
                        j += 1
                    else:
                        break
                end = self.stmt_end(j + 1) if (j < self.n and t[j][1] == '=') else j
                self.pending.append((end, self.scopes[-1], names))
                self.pending.sort(key=lambda p: p[0])
                k = j
                continue
            if typ == 'kw' and v == 'function':
                j = k + 1
                method = False
                first = True
                while t[j][0] == 'name' or t[j][1] in ('.', ':'):
                    if t[j][0] == 'name':
                        if first:
                            self.ref(j)
                            first = False
                        else:
                            self.skip_name(j)
                    elif t[j][1] == ':':
                        method = True
                    j += 1
                k = self.open_function(j, method)
                continue
            if typ == 'kw' and v == 'for':
                j = k + 1
                names = []
                while t[j][0] == 'name':
                    self.skip_name(j)
                    names.append((t[j][1], t[j][2]))
                    j += 1
                    if t[j][1] == ',':
                        j += 1
                    else:
                        break
                self.next_do = names
                k = j
                continue
            if typ == 'kw' and v == 'do':
                sc = {}
                if self.next_do is not None:
                    for nm, line in self.next_do:
                        sc[nm] = (self.L(line), nm)
                    self.next_do = None
                self.scopes.append(sc)
                self.blocks.append('block')
                k += 1
                continue
            if typ == 'kw' and v in ('then', 'repeat'):
                self.scopes.append({})
                self.blocks.append('block')
                k += 1
                continue
            if typ == 'kw' and v == 'elseif':
                self.close()
                k += 1
                continue
            if typ == 'kw' and v == 'else':
                self.close()
                self.scopes.append({})
                self.blocks.append('block')
                k += 1
                continue
            if typ == 'kw' and v in ('end', 'until'):
                self.close()
                k += 1
                continue
            if typ == 'name':
                prev = t[k - 1] if k else ('', '', 0)
                nxt = t[k + 1] if k + 1 < self.n else ('', '', 0)
                if prev[0] == 'op' and prev[1] in ('.', ':'):
                    self.skip_name(k)
                elif nxt[0] == 'op' and nxt[1] == '=' and self.brack and self.brack[-1] == '{' \
                        and prev[0] == 'op' and prev[1] in ('{', ',', ';'):
                    self.skip_name(k)
                elif (prev[0] == 'kw' and prev[1] == 'goto') or (prev[0] == 'op' and prev[1] == '::'):
                    self.skip_name(k)
                else:
                    self.ref(k)
                k += 1
                continue
            if typ == 'op':
                if v in ('(', '{', '['):
                    self.brack.append(v)
                elif v in (')', '}', ']') and self.brack:
                    self.brack.pop()
            k += 1
        return self


