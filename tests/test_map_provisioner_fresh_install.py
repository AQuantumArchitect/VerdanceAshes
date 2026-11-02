#!/usr/bin/env python3
"""A fresh BAR has none of the campaign maps (2026-11-01: a friend's first drop stopped at "map
'Greenest Fields 1.3' could not be provisioned"). The provisioner takes the content service's answer
as a list or as one object, tries every mirror, falls back on the engine's pr-downloader, and SETUP,
PLAY and every Drop all fetch what is missing."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from verdance.world import map_provisioner as mp  # noqa: E402

BODY = b"fake sd7 bytes"
MD5 = hashlib.md5(BODY).hexdigest()
ENTRY = {"filename": "greenest_fields_1.3.sd7", "md5": MD5, "size": len(BODY),
         "mirrors": ["https://files-cdn.beyondallreason.dev/file/x/greenest_fields_1.3.sd7"]}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen(answer, fail_downloads=0):
    calls = {"n": 0}

    def fake(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "/find?" in url:
            return _Resp(json.dumps(answer).encode())
        calls["n"] += 1
        if calls["n"] <= fail_downloads:
            raise OSError("mirror down")
        return _Resp(BODY)
    return fake


def test_the_service_answer_as_an_object_or_a_list():
    for answer in (ENTRY, [ENTRY]):
        with mock.patch.object(mp.urllib.request, "urlopen", _urlopen(dict(answer) if isinstance(answer, dict) else [dict(ENTRY)])):
            e = mp.resolve("Greenest Fields 1.3")
        assert e["filename"] == "greenest_fields_1.3.sd7" and len(e["mirrors"]) == 2   # + the md5 URL


def test_a_fresh_install_downloads_the_map_trying_every_mirror():
    with tempfile.TemporaryDirectory() as d:
        bar = Path(d)
        with mock.patch.object(mp.urllib.request, "urlopen", _urlopen(dict(ENTRY), fail_downloads=1)):
            res = mp.ensure("Greenest Fields 1.3", bar, workspace=ROOT, quiet=True)
        assert res["status"] == "downloaded"
        assert (bar / "maps" / "greenest_fields_1.3.sd7").read_bytes() == BODY


def test_when_the_service_fails_the_engines_downloader_fetches_it():
    with tempfile.TemporaryDirectory() as d:
        bar = Path(d)
        exe = bar / "engine" / "2025.06.1" / "pr-downloader.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("")

        def fake_run(cmd, **kw):
            assert cmd[0] == str(exe) and "--download-map" in cmd and "Greenest Fields 1.3" in cmd
            (bar / "maps").mkdir(exist_ok=True)
            (bar / "maps" / "greenest_fields_1.3.sd7").write_bytes(BODY)
        with mock.patch.object(mp.urllib.request, "urlopen", side_effect=OSError("403 Forbidden")), \
                mock.patch.object(mp.subprocess, "run", fake_run):
            res = mp.ensure("Greenest Fields 1.3", bar, workspace=ROOT, quiet=True)
        assert res["status"] == "downloaded" and res["via"] == "pr-downloader"


def test_setup_play_and_every_drop_fetch_missing_maps():
    setup = (ROOT / "scripts" / "player" / "setup_play.ps1").read_text(encoding="utf-8-sig")
    assert "-m verdance.world.map_provisioner --workspace $Workspace --check-all" in setup
    launcher = (ROOT / "tools" / "verdance_kernel" / "launcher.py").read_text(encoding="utf-8")
    assert "_ensure_campaign_maps(Path(kernel.ws))" in launcher
    sortie = (ROOT / "tools" / "verdance_kernel" / "sortie.py").read_text(encoding="utf-8")
    assert "prov = provision_map(ws, cfg, map_name" in sortie and "could not be downloaded" in sortie


def test_another_version_of_the_map_is_named_but_does_not_count():
    """2026-11-01: BAR downloaded Greenest Fields 1.3.1; the campaign is pinned to 1.3."""
    with tempfile.TemporaryDirectory() as d:
        bar = Path(d)
        (bar / "maps").mkdir()
        (bar / "maps" / "greenest_fields_1.3.1.sd7").write_bytes(b"x")
        assert mp.other_versions(bar / "maps", "greenest_fields_1.3.sd7") == ["greenest_fields_1.3.1.sd7"]
        with mock.patch.object(mp.urllib.request, "urlopen", side_effect=OSError("offline")):
            try:
                mp.ensure("Greenest Fields 1.3", bar, workspace=ROOT, quiet=True)
                raise AssertionError("1.3.1 must not stand in for 1.3")
            except mp.MapProvisionError as exc:
                assert "greenest_fields_1.3.1.sd7" in str(exc) and "needs exactly greenest_fields_1.3.sd7" in str(exc)
