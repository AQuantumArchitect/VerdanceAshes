"""The sortie flow in the hub page (owner calls, 2026-11-03/04): Choose this job opens the camp talks,
every talk can be answered or declined and must be before Who goes, then What comes. Walked in a real
browser on the repo's own hub state, map only. Skipped where Playwright is not installed."""
import http.server
import re
import threading
import unittest
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    from playwright.sync_api import sync_playwright
except Exception:  # noqa: BLE001
    sync_playwright = None


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@unittest.skipIf(sync_playwright is None, "playwright is not installed")
class SortieFlow(unittest.TestCase):
    def test_choose_talk_who_goes_what_comes(self):
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(ROOT / "app" / "showoff")))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        errors = []
        try:
            with sync_playwright() as pw:
                b = pw.chromium.launch()
                pg = b.new_page(viewport={"width": 1500, "height": 950})
                pg.on("pageerror", lambda e: errors.append(str(e)))
                pg.goto(f"http://127.0.0.1:{httpd.server_address[1]}/index.html")
                pg.wait_for_timeout(2000)
                if pg.locator("#coach-skip").is_visible():
                    pg.click("#coach-skip")
                self.assertFalse(pg.locator('button[data-workspace="home"]').count(), "the Home tab is gone")
                self.assertFalse(pg.locator("#col-right").is_visible(), "no side column on the jobs screen")
                if pg.locator("#company-intro").is_visible():
                    pg.click("#recommend-company"); pg.click("#btn-seal-company-intro"); pg.wait_for_timeout(500)
                if pg.locator("#company-intro").is_visible():
                    # Sealing goes through the kernel (PLAY.bat); this static page has none, so a fresh
                    # campaign (company not sealed yet) cannot get past the formation screen here.
                    b.close()
                    self.skipTest("needs a save with the company sealed (fresh campaign: sealing needs the kernel)")
                self.assertEqual(pg.locator("#btn-deploy").inner_text().strip(), "Choose this job")
                pg.click("#btn-deploy"); pg.wait_for_timeout(700)
                self.assertTrue(pg.locator('#drop-confirm .drop-tab.on[data-drop-tab="talks"]').count(), "the flow opens on the talks")
                go = pg.locator("#drop-confirm-go")
                talks = 0
                while pg.locator("[data-talk-answer]").count() and talks < 12:
                    self.assertTrue(go.is_disabled(), "no skipping a talk")
                    nulls = pg.locator("[data-talk-answer]", has_text="No time for this.")
                    self.assertTrue(nulls.count(), "every talk can be declined")
                    nulls.first.click(); pg.wait_for_timeout(300); talks += 1
                self.assertIn("who goes", go.inner_text().lower())
                go.click(); pg.wait_for_timeout(400)
                self.assertTrue(pg.locator('#drop-confirm .drop-tab.on[data-drop-tab="party"]').count())
                self.assertIn("what comes", go.inner_text().lower())
                go.click(); pg.wait_for_timeout(400)
                self.assertTrue(pg.locator('#drop-confirm .drop-tab.on[data-drop-tab="reserve"]').count())
                self.assertTrue(pg.locator("#shop-list").is_visible() and pg.locator("#drop-reserve").is_visible(),
                                "the reserve and the store on one screen")
                b.close()
        finally:
            httpd.shutdown()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
