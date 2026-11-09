#!/usr/bin/env python3
"""The safety field (va_safety_field.lua, owner call 2026-11-09: no leashes, no magic numbers): fire
from what the company knows, shared over its crowd; the unknown as danger in proportion to the enemy
not yet found; and a hero's choice of where to be. Run in real Lua
(tools/hud_harness/safety_field_test.lua); skipped without Lua 5.4."""
from __future__ import annotations

import unittest

import lua_harness


class SafetyField(unittest.TestCase):
    def test_fire_unknown_and_choice(self):
        self.assertIsNone(lua_harness.run("tools/hud_harness/safety_field_test.lua"))
