"""Where the Lua 5.4 shared library is, for the ctypes harnesses and the tests that run them.

paths() lists the candidates that exist, best first (empty when Lua 5.4 is not installed):
  1. VA_LIBLUA, an explicit path to the library;
  2. Linux: /usr/lib/x86_64-linux-gnu/liblua5.4.so* (apt install liblua5.4-0);
  3. Windows: lua54.dll from `winget install DEVCOM.Lua` (%LOCALAPPDATA%\\Programs\\Lua\\bin or
     %ProgramFiles%\\Lua\\bin), else any lua54.dll on PATH.
"""
import glob
import os


def paths():
    found = []
    env = os.environ.get("VA_LIBLUA")
    if env and os.path.isfile(env):
        found.append(env)
    found += sorted(glob.glob("/usr/lib/x86_64-linux-gnu/liblua5.4.so*"))
    if os.name == "nt":
        dirs = [os.path.join(os.environ.get(v, ""), "Programs" if v == "LOCALAPPDATA" else "", "Lua", "bin")
                for v in ("LOCALAPPDATA", "ProgramFiles") if os.environ.get(v)]
        dirs += [d for d in os.environ.get("PATH", "").split(os.pathsep) if d]
        for d in dirs:
            p = os.path.join(d, "lua54.dll")
            if os.path.isfile(p) and p not in found:
                found.append(p)
    return found
