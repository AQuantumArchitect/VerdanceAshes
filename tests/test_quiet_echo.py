#!/usr/bin/env python3
"""The mod's VA_ debug lines stay out of the player's console (2026-11-09): va_active.lua sends a
single-string Spring.Echo starting VA_ to Spring.Log at L_DEPRECATED, which BAR's chat drops and the
infolog keeps. Run in real Lua (tools/hud_harness/quiet_echo_test.lua); skipped without Lua 5.4."""
from __future__ import annotations

import unittest

import lua_harness


class QuietEcho(unittest.TestCase):
    def test_va_lines_go_to_the_log_not_the_console(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/quiet_echo_test.lua"))
