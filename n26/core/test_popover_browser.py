"""Browser behaviour for the popover.

Run with ``GYRINX_BROWSER_TESTS=1 pytest -n0 n26/core/test_popover_browser.py``.
The ordinary suite skips this module because CI does not install Playwright browsers.
"""

import os
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles import finders
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler
from playwright.sync_api import expect, sync_playwright

pytestmark = pytest.mark.skipif(
    os.environ.get("GYRINX_BROWSER_TESTS") != "1",
    reason="set GYRINX_BROWSER_TESTS=1 to run Playwright interaction tests",
)


def render(source: str) -> str:
    return Template(CottonCompiler().process(source)).render(Context())


def test_keyboard_and_link_selection_manage_focus():
    component = render(
        '<c-ui.popover trigger_text="Contents" panel_label="On this page">'
        '<a href="#chosen">First section</a></c-ui.popover>'
        '<c-ui.popover trigger_text="Help" panel_label="Help topics">'
        '<a href="#chosen">Help topic</a></c-ui.popover>'
    )
    alpine_path = finders.find("designsystem/vendor/alpine.min.js")
    kit_path = finders.find("django_cotton_ui/cotton-ui.min.js")
    assert alpine_path and kit_path
    alpine = Path(alpine_path).read_text()
    kit = Path(kit_path).read_text()
    page_html = f"""
        <style>[x-cloak] {{ display: none !important; }}</style>
        <script>{kit}</script>
        {component}
        <button id="outside">Outside</button>
        <div style="height: 1600px"></div>
        <h2 id="chosen">Chosen section</h2>
        <script>{alpine}</script>
    """

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(page_html)

        trigger = page.get_by_role("button", name="Contents")
        panel = page.locator('[role="dialog"][aria-label="On this page"]')
        first_link = page.get_by_role("link", name="First section")
        help_trigger = page.get_by_role("button", name="Help")
        help_panel = page.locator('[role="dialog"][aria-label="Help topics"]')

        expect(trigger).to_have_attribute("aria-controls", re.compile(r".+"))
        expect(help_trigger).to_have_attribute("aria-controls", re.compile(r".+"))
        controls = trigger.get_attribute("aria-controls")
        help_controls = help_trigger.get_attribute("aria-controls")
        assert controls != help_controls
        assert panel.get_attribute("id") == controls
        assert help_panel.get_attribute("id") == help_controls

        expect(trigger).to_have_attribute("aria-expanded", "false")
        trigger.focus()
        trigger.press("Enter")
        panel.wait_for(state="visible")
        assert trigger.get_attribute("aria-expanded") == "true"
        assert first_link.evaluate("element => element === document.activeElement")
        trigger_box = trigger.bounding_box()
        panel_box = panel.bounding_box()
        assert trigger_box and panel_box
        assert panel_box["y"] >= trigger_box["y"] + trigger_box["height"]

        page.keyboard.press("Escape")
        panel.wait_for(state="hidden")
        assert trigger.get_attribute("aria-expanded") == "false"
        assert trigger.evaluate("element => element === document.activeElement")

        trigger.click()
        panel.wait_for(state="visible")
        page.locator("#outside").click()
        panel.wait_for(state="hidden")
        assert trigger.get_attribute("aria-expanded") == "false"

        trigger.press("Enter")
        panel.wait_for(state="visible")
        expect(first_link).to_be_focused()
        first_link.press("Enter")
        panel.wait_for(state="hidden")
        assert trigger.evaluate("element => element === document.activeElement")
        page.wait_for_function("location.hash === '#chosen'")
        target_top = page.locator("#chosen").evaluate(
            "element => element.getBoundingClientRect().top"
        )
        assert page.evaluate("window.scrollY") > 1000
        assert 0 <= target_top < page.evaluate("window.innerHeight")

        browser.close()
