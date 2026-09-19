#!/usr/bin/env python3
"""Exercise a running Help page in Chromium.

Run through .codex/run.sh against the worktree server. Optional screenshots are
saved locally; this command neither seeds data nor changes application records.
"""

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def check(page, url, width, screenshot_dir=None, theme="light", with_toc=True):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_function("window.Alpine !== undefined")
    page.locator(".flatpage-prose").wait_for()
    # The toolbar is a developer control, not part of the application layout.
    page.add_style_tag(content="#djDebugRoot { display: none !important; }")
    assert page.locator("main").count() == 1
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth"), width

    if width < 1024:
        expect(page.locator(".flatpage-help-nav")).not_to_be_visible()
        browse = page.get_by_role("button", name="Help & documentation", exact=True)
        expect(browse).to_be_visible()
        assert (
            abs(
                browse.bounding_box()["x"]
                - page.locator(".flatpage-main").bounding_box()["x"]
            )
            < 2
        ), "The menu stays at the left edge, including pages without a ToC."
        browse.focus()
        browse.press("Enter")
        drawer = page.get_by_role("dialog", name="Help & documentation", exact=True)
        expect(drawer).to_be_visible()
        expect(drawer.locator('a[aria-current="page"]')).to_be_visible()
        expect(drawer.get_by_role("button", name="Close", exact=True)).to_be_focused()
        page.keyboard.press("Tab")
        assert drawer.evaluate("element => element.contains(document.activeElement)")
        if screenshot_dir and width == 375:
            page.wait_for_timeout(350)  # Finish the drawer transition before capture.
            page.screenshot(path=str(screenshot_dir / f"help-drawer-{theme}.png"))
        page.keyboard.press("Escape")
        expect(drawer).not_to_be_visible()
        expect(browse).to_be_focused()
    else:
        expect(page.locator(".flatpage-help-nav")).to_be_visible()
        expect(page.locator(".flatpage-layout")).to_have_css("display", "grid")

    if not with_toc:
        expect(
            page.get_by_role("button", name="On this page", exact=True)
        ).to_have_count(0)
        expect(page.locator(".flatpage-toc")).to_have_count(0)
    elif width < 1280:
        trigger = page.get_by_role("button", name="On this page", exact=True)
        expect(trigger).to_be_visible()
        trigger.focus()
        trigger.press("Enter")
        panel = page.get_by_role("dialog", name="On this page", exact=True)
        expect(panel).to_be_visible()
        first_link = panel.locator('a[href^="#"]').first
        expect(first_link).to_be_focused()
        bounds = panel.bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width + 1
        assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 951
        if screenshot_dir and width == 375:
            expect(panel).to_have_css("opacity", "1")
            page.screenshot(path=str(screenshot_dir / f"help-toc-{theme}.png"))
        page.keyboard.press("Escape")
        expect(panel).not_to_be_visible()
        expect(trigger).to_be_focused()
        trigger.press("Enter")
        last_link = panel.locator('a[href^="#"]').last
        target = last_link.get_attribute("href")
        last_link.click()
        expect(panel).not_to_be_visible()
        expect(trigger).to_be_focused()
        assert page.evaluate("location.hash") == target
        assert page.evaluate(
            "document.getElementById(decodeURIComponent(location.hash.slice(1)))"
            ".getBoundingClientRect().top < innerHeight"
        ), "Returning focus must not scroll away from the selected section."
    else:
        expect(
            page.get_by_role("button", name="On this page", exact=True)
        ).not_to_be_visible()
        toc = page.locator(".flatpage-toc")
        expect(toc).to_be_visible()
        link = toc.locator('a[href^="#"]').last
        target = link.get_attribute("href")
        link.click()
        assert page.evaluate("location.hash") == target
        expect(link).to_have_attribute("aria-current", "location")

    page.evaluate("window.scrollTo(0, 0)")
    if screenshot_dir:
        page.screenshot(path=str(screenshot_dir / f"help-{width}-{theme}.png"))
    assert not errors, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Local Help page with at least two h2/h3 headings.")
    parser.add_argument("--screenshots", type=Path)
    parser.add_argument(
        "--no-toc",
        action="store_true",
        help="Check a page with fewer than two h2/h3 headings.",
    )
    args = parser.parse_args()
    if args.screenshots:
        args.screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for theme in ("light", "dark"):
            for width in (375, 768, 1024, 1440):
                context = browser.new_context(
                    viewport={"width": width, "height": 950}, color_scheme=theme
                )
                page = context.new_page()
                check(
                    page,
                    args.url,
                    width,
                    args.screenshots,
                    theme,
                    with_toc=not args.no_toc,
                )
                context.close()
                print(f"PASS {width}px {theme}")
        context = browser.new_context(
            viewport={"width": 375, "height": 950}, java_script_enabled=False
        )
        page = context.new_page()
        page.goto(args.url)
        labels = (
            ("Help & documentation",)
            if args.no_toc
            else ("Help & documentation", "On this page")
        )
        for label in labels:
            disclosure = page.locator(".flatpage-noscript-nav").filter(
                has=page.locator("summary", has_text=label)
            )
            disclosure.locator("summary").click()
            expect(disclosure.locator("a").first).to_be_visible()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        context.close()
        browser.close()
        print("PASS JavaScript disabled")


if __name__ == "__main__":
    main()
