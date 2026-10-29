"""Real Playwright/Chromium DOM smoke for the owner's screenshot-like WoS export.

No WoS URL, login, licensed content, credentials, or network requests.
Run with WOS_MODAL_BROWSER_TEST=1 and a locally installed Chromium.
The screenshot-style fixture intentionally has NO role=dialog and NO
class names containing modal, which caused the real 2026-10-29 failure.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "wos_ui_export", ROOT / "scripts" / "stage2" / "wos_ui_export.py")
wos = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wos)

HTML = """
<!DOCTYPE html><html lang="en"><body>
<button id="mainExport" onclick="document.querySelector('#menu').style.display='block'">
  Export</button>
<div id="menu" style="display:none">
  <button onclick="setTimeout(() => {document.querySelector('#panel').style.display='block';this.parentNode.style.display='none'},80)">Plain text file</button>
</div>
<div id="panel" style="display:none;background:white;padding:24px">
 <div><h1>Export Records to Plain Text File</h1></div>
 <section>
  <div>Record Options</div>
  <p><label><input type="radio" name="part" checked>All records on page</label></p>
  <p><label><input type="radio" name="part">Records from:</label>
   <input type="number" min="1" value="1"> to
   <input type="number" min="1" value="1000"></p>
  <p>No more than 500 records at a time</p>
  <div>Record Content:</div>
  <select aria-label="Record Content">
   <option>Author, Title, Source</option>
   <option selected>Full Record and Cited References</option>
  </select>
  <p><button id="confirmExport">Export</button><button>Cancel</button></p>
 </section>
</div>
</body></html>
"""


# Reproduces the owner's actual Playwright trace:
# #onetrust-consent-sdk .onetrust-pc-dark-filter intercepts Export clicks.
ONETRUST_OVERLAY = """
<div id="onetrust-consent-sdk">
 <div class="onetrust-pc-dark-filter" style="
  position:fixed;inset:0;z-index:998;background:rgba(0,0,0,.5)"></div>
 <div id="onetrust-pc-sdk" style="
  position:fixed;left:10%;top:20%;width:80%;padding:30px;
  z-index:999;background:white">
   <h2>Cookie Preferences</h2>
   <button id="onetrust-reject-all-handler" onclick="
     document.querySelector('#onetrust-consent-sdk').remove()">
      Reject All</button>
 </div>
</div>
"""

ONETRUST_OWNER_CHOICE = """
<div id="onetrust-consent-sdk">
 <div class="onetrust-pc-dark-filter" style="
  position:fixed;inset:0;z-index:998;background:rgba(0,0,0,.5)"></div>
 <div id="onetrust-pc-sdk" style="
  position:fixed;left:10%;top:20%;z-index:999;background:white;padding:20px">
  <h2>Cookie Preferences</h2>
  <button id="onetrust-accept-btn-handler" onclick="
    document.querySelector('#onetrust-consent-sdk').remove()">Accept All</button>
 </div>
</div>
"""


@unittest.skipUnless(os.environ.get("WOS_MODAL_BROWSER_TEST") == "1",
                     "Set WOS_MODAL_BROWSER_TEST=1 for real Chromium smoke")
class TestWosModalLiveDom(unittest.TestCase):
    def test_screenshot_reconstruction_full_sequence(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(HTML)
                modal = wos.open_modal(page)
                self.assertEqual(modal.get_attribute("id"), "panel")
                wos.fill_range(modal, 501, 1000)
                wos.select_record_content(page, modal)
                self.assertTrue(modal.locator('input[type="radio"]').nth(1).is_checked())
                self.assertEqual(modal.locator('input[type="number"]').nth(0).input_value(), "501")
                self.assertEqual(modal.locator('input[type="number"]').nth(1).input_value(), "1000")
                self.assertEqual(modal.locator("select").input_value(),
                                 "Full Record and Cited References")
                self.assertTrue(modal.get_by_role("button", name="Export").is_visible())
            finally:
                browser.close()

    def test_real_onetrust_dark_filter_is_resolved_before_export(self):
        from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(HTML.replace('<button id="mainExport"', ONETRUST_OVERLAY
                                              + '<button id="mainExport"'))
                # Reproduce the owner's exact blocking symptom before fix.
                with self.assertRaises(BrowserTimeout):
                    page.locator("#mainExport").click(timeout=750)
                modal = wos.open_modal(page)
                self.assertEqual(modal.get_attribute("id"), "panel")
                self.assertEqual(page.locator("#onetrust-consent-sdk").count(), 0)
                wos.fill_range(modal, 501, 1000)
                wos.select_record_content(page, modal)
                self.assertEqual(modal.locator('input[type="number"]').nth(0).input_value(), "501")
                self.assertEqual(modal.locator('input[type="number"]').nth(1).input_value(), "1000")
                self.assertTrue(modal.get_by_role("button", name="Export").is_visible())
            finally:
                browser.close()

    def test_owner_choice_when_onetrust_does_not_offer_reject(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(HTML.replace('<button id="mainExport"', ONETRUST_OWNER_CHOICE
                                              + '<button id="mainExport"'))
                prompts = []
                def owner_choice(question):
                    prompts.append(question)
                    self.assertTrue(page.locator(
                        "#onetrust-consent-sdk .onetrust-pc-dark-filter").is_visible())
                    # Only the owner chooses this visible site option.
                    page.locator("#onetrust-accept-btn-handler").click()
                    return ""
                wos.resolve_cookie_consent(page, input_fn=owner_choice,
                                           output_fn=lambda _: None)
                self.assertEqual(len(prompts), 1)
                self.assertEqual(page.locator("#onetrust-consent-sdk").count(), 0)
                modal = wos.open_modal(page)
                self.assertEqual(modal.get_attribute("id"), "panel")
            finally:
                browser.close()

    def test_owner_can_stop_without_cookie_consent(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(HTML.replace('<button id="mainExport"', ONETRUST_OWNER_CHOICE
                                              + '<button id="mainExport"'))
                with self.assertRaisesRegex(wos.ExportError, "cookie choice still pending"):
                    wos.resolve_cookie_consent(page, input_fn=lambda _: "Q",
                                               output_fn=lambda _: None)
                self.assertFalse(page.locator("#panel").is_visible())
            finally:
                browser.close()

    def test_no_modal_without_required_controls(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as driver:
            browser = driver.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_content(
                    "<h1>Export Records to Plain Text File</h1>"
                    "<p>Missing range controls and export button</p>")
                with self.assertRaisesRegex(wos.ExportError, "not in one visible panel"):
                    wos.locate_export_panel(page)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
