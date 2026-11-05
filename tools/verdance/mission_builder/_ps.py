"""Windows PowerShell 5.1 semantics the mission builder's port has to keep.

scripts/build_next_mission_v1.ps1 ran under Windows PowerShell 5.1 on .NET Framework (the kernel calls
``powershell``, and the parity corpus is 5.1's ConvertTo-Json). Its output depends on how 5.1 treats
truthiness, casts, rounding and strings, so the port spells those rules out once, here, instead of
leaning on Python's own (which differ: an empty dict is false in Python and true in PowerShell; a
float prints as ``1.0`` in Python and ``1`` in PowerShell; string ``-eq`` ignores case).

Data read from JSON stands for PowerShell's PSCustomObject (a dict); output objects are dicts too.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


def T(v: Any) -> bool:
    """LanguagePrimitives.IsTrue: what ``if ($v)`` and ``-not $v`` decide."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return len(v) > 0
    if isinstance(v, (list, tuple)):
        if len(v) == 0:
            return False
        if len(v) == 1:
            first = v[0]
            if isinstance(first, (list, tuple)):
                return len(first) > 0
            return T(first)
        return True
    # PSCustomObject, hashtable, anything else: an object is true, even an empty one.
    return True


def has(obj: Any, name: str) -> bool:
    """``$obj.PSObject.Properties[$name]`` is non-null: the property exists (its value may be null)."""
    return isinstance(obj, dict) and name in obj


def g(obj: Any, name: str) -> Any:
    """``$obj.name``: null on a null object or a missing property."""
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def arr(v: Any) -> List[Any]:
    """``@($v)`` over a value (not a command's output): null is one null element, a list is copied."""
    if isinstance(v, list):
        return list(v)
    if isinstance(v, tuple):
        return list(v)
    return [v]


def dotnet_double_str(x: float) -> str:
    """double.ToString() on .NET Framework: the "G" format, 15 significant digits."""
    if x != x:
        return "NaN"
    if x == math.inf:
        return "Infinity"
    if x == -math.inf:
        return "-Infinity"
    if x == 0:
        return "0"
    return "%.15G" % x


def S(v: Any) -> str:
    """``[string]$v`` (and ``"$v"`` inside a string)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return dotnet_double_str(v)
    if isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)):
        # An array joins on $OFS, a single space.
        return " ".join(S(x) for x in v)
    if isinstance(v, dict):
        # A PSCustomObject prints as @{a=1; b=2}.
        return "@{" + "; ".join(f"{k}={S(x)}" for k, x in v.items()) + "}"
    return str(v)


def round_even(x: float) -> float:
    """[Math]::Round(double): round half to even on the exact binary value."""
    return float(round(x))


def R(x: Any, digits: int = 0) -> float:
    """[Math]::Round(double, digits) as .NET Framework does it: scale, round half to even, unscale.

    That is not Python's round(x, digits), which rounds the exact decimal value; the two disagree on
    values whose scaled product lands on .5 by floating-point error.
    """
    v = float(x)
    if digits == 0:
        return round_even(v)
    if abs(v) < 1e16:
        p = 10.0 ** digits
        v = v * p
        v = float(round(v))
        v = v / p
    return v


def I(v: Any) -> int:
    """``[int]$v``: a double rounds half to even (Convert.ToInt32), null is 0."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(round(v))
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0
        try:
            return int(s)
        except ValueError:
            return int(round(float(s)))
    if isinstance(v, list) and len(v) == 1:
        return I(v[0])
    raise TypeError(f"Cannot convert {type(v).__name__} to System.Int32")


def D(v: Any) -> float:
    """``[double]$v``: null is 0, a string parses (empty is 0)."""
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return 0.0
        return float(s)
    if isinstance(v, list) and len(v) == 1:
        return D(v[0])
    raise TypeError(f"Cannot convert {type(v).__name__} to System.Double")


def B(v: Any) -> bool:
    """``[bool]$v``: the same rule as ``if``."""
    return T(v)


def ieq(a: Any, b: Any) -> bool:
    """``-eq`` between two strings: case-insensitive."""
    if a is None or b is None:
        return a is None and b is None
    return S(a).lower() == S(b).lower()


def eq(a: Any, b: Any) -> bool:
    """``$a -eq $b`` for scalars: the right side converts to the left side's type."""
    if a is None:
        return b is None
    if b is None:
        return False
    if isinstance(a, bool):
        return a == T(b)
    if isinstance(a, (int, float)):
        if isinstance(b, bool):
            return a == (1 if b else 0)
        if isinstance(b, (int, float)):
            return a == b
        if isinstance(b, str):
            try:
                return a == float(b.strip()) if b.strip() else a == 0
            except ValueError:
                return False
        return False
    if isinstance(a, str):
        return a.lower() == S(b).lower()
    return a is b


def iin(v: Any, options: Iterable[str]) -> bool:
    """``$v -in @(...)`` against string literals: case-insensitive."""
    s = S(v).lower()
    return any(s == o.lower() for o in options)


def imatch(v: Any, pattern: str) -> bool:
    """``$v -match 'pattern'``: case-insensitive regex search."""
    return re.search(pattern, S(v), re.IGNORECASE) is not None


def ilike(v: Any, pattern: str) -> bool:
    """``$v -like 'pat*'``: case-insensitive wildcard match of the whole string."""
    rx = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in pattern)
    return re.fullmatch(rx, S(v), re.IGNORECASE | re.DOTALL) is not None


def sign(x: float) -> int:
    """[Math]::Sign."""
    return (x > 0) - (x < 0)


def fmt(template: str, *args: Any) -> str:
    """``"template" -f args`` for the {N} and {N:n2} placeholders the builder uses."""

    def one(m: "re.Match[str]") -> str:
        idx = int(m.group(1))
        spec = m.group(2)
        v = args[idx] if idx < len(args) else None
        if spec and spec.lower().startswith("n"):
            places = int(spec[1:] or 2)
            return f"{D(v):,.{places}f}"
        if spec and spec.lower().startswith("d"):
            width = int(spec[1:] or 0)
            return str(I(v)).zfill(width)
        return S(v)

    return re.sub(r"\{(\d+)(?::([A-Za-z]\d*))?\}", one, template)


class CIDict:
    """A PowerShell ``@{}`` hashtable used as a map: string keys compare without case."""

    def __init__(self) -> None:
        self._d: Dict[str, Tuple[str, Any]] = {}

    @staticmethod
    def _k(key: Any) -> str:
        return S(key).lower()

    def __contains__(self, key: Any) -> bool:
        return self._k(key) in self._d

    def __getitem__(self, key: Any) -> Any:
        return self._d[self._k(key)][1]

    def __setitem__(self, key: Any, value: Any) -> None:
        k = self._k(key)
        if k in self._d:
            self._d[k] = (self._d[k][0], value)
        else:
            self._d[k] = (S(key), value)

    def get(self, key: Any, default: Any = None) -> Any:
        hit = self._d.get(self._k(key))
        return default if hit is None else hit[1]

    def __len__(self) -> int:
        return len(self._d)

    def keys(self) -> List[str]:
        return [k for k, _ in self._d.values()]

    def items(self) -> List[Tuple[str, Any]]:
        return list(self._d.values())

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())


# A ``@{}`` hashtable on .NET Framework enumerates its keys by bucket, which follows the string's
# culture hash, not insertion order. The one place that order reaches the scenario is the standing
# war's same-side pacts (``foreach ($f in $sideAllies.Keys)``). The corpus from Luke's PC
# (tour 2026-11-04, commit 9ce74de) shows "nullmercs" enumerated before "armada" whichever was
# inserted first (tour 03 and tour 08). Cortex never seats in that corpus, so its place is a guess:
# after the two that were seen.
_HASHTABLE_ORDER = ("nullmercs", "armada")


def hashtable_key_order(keys: Iterable[str]) -> List[str]:
    keys = list(keys)

    def rank(item: Tuple[int, str]) -> Tuple[int, int]:
        i, k = item
        low = k.lower()
        if low in _HASHTABLE_ORDER:
            return (0, _HASHTABLE_ORDER.index(low))
        return (1, i)

    return [k for _, k in sorted(enumerate(keys), key=rank)]


def sort_unique_ints(values: Iterable[Any]) -> List[int]:
    """``$values | Sort-Object -Unique`` over integers."""
    return sorted({I(v) for v in values})


def first(items: Iterable[Any], pred) -> Optional[Any]:
    """``... | Where-Object { pred } | Select-Object -First 1``."""
    for it in items:
        if pred(it):
            return it
    return None
