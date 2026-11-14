"""Exercise the diagnostic helper in an isolated real browser.

Run with .codex/run.sh python
.agents/skills/design-refinement/scripts/test_browser_review.py.
"""

import unittest
from pathlib import Path

from playwright.sync_api import Error, sync_playwright

SOURCE = Path(__file__).with_name("browser-review.js").read_text()


class BrowserReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(
                channel="chrome", headless=True
            )
        except Error:
            cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 800, "height": 600})
        self.page.set_content("""
            <style>
              body { margin:0; background:rgb(24,24,24); color:rgb(240,240,240) }
              main { position:relative; width:400px; height:1200px; margin:16px }
              h1, p { margin:0; position:absolute; width:120px; height:24px }
              h1 { left:12px; top:8px; font-size:20px; font-weight:700 }
              p { left:20px; top:48px; font-size:16px; font-weight:400 }
            </style>
            <main><h1>Heading</h1><p>Content</p>
              <span hidden>Hidden content</span><button>Action</button>
            </main>
        """)
        self.assertTrue(self.page.evaluate(SOURCE)["ready"])

    def tearDown(self):
        self.page.close()

    def test_measured_edges_and_resolved_type(self):
        items = self.page.evaluate("gyrinxDesignReview.compare(['h1', 'p'])")
        self.assertEqual(items[1]["deltaFromFirst"]["left"], 8)
        self.assertEqual(items[1]["deltaFromFirst"]["top"], 40)
        self.assertEqual(items[0]["styles"]["fontWeight"], "700")
        self.assertEqual(
            self.page.evaluate("gyrinxDesignReview.inspect('[hidden]')"), []
        )

    def test_modes_replace_each_other_and_clear_without_changing_content(self):
        original = self.page.locator("main").inner_html()
        for mode in ("grid", "anchors", "blocks", "zones"):
            self.page.evaluate(
                """mode => gyrinxDesignReview.overlay({
                  root:'main', mode, selectors:['h1', 'p'],
                  regions:[{selector:'h1', priority:1}, {selector:'p', priority:3}]
                })""",
                mode,
            )
            overlay = self.page.locator("[data-gyrinx-design-review]")
            self.assertEqual(overlay.count(), 1)
            self.assertEqual(
                overlay.evaluate("el => getComputedStyle(el).pointerEvents"), "none"
            )
            self.assertEqual(self.page.locator("main").inner_html(), original)
            self.assertEqual(self.page.get_by_role("button", name="Action").count(), 1)
        self.page.evaluate("gyrinxDesignReview.clear()")
        self.assertEqual(self.page.locator("[data-gyrinx-design-review]").count(), 0)
        self.page.evaluate("window.dispatchEvent(new Event('resize'))")
        self.assertEqual(self.page.locator("[data-gyrinx-design-review]").count(), 0)

    def test_blocks_retain_inherited_dark_background_and_text_bars(self):
        self.page.evaluate("gyrinxDesignReview.overlay({mode:'blocks'})")
        overlay = self.page.locator("[data-gyrinx-design-review]")
        self.assertEqual(
            overlay.locator("rect").first.get_attribute("fill"), "rgb(24, 24, 24)"
        )
        self.assertGreater(
            overlay.locator('rect[fill="rgb(240, 240, 240)"]').count(), 0
        )

    def test_inline_svg_becomes_a_media_placeholder(self):
        self.page.locator("main").evaluate(
            """el => el.insertAdjacentHTML('beforeend',
              '<svg width="24" height="24" viewBox="0 0 24 24"><path d="M2 2L22 22"/></svg>')"""
        )
        self.page.evaluate("gyrinxDesignReview.overlay({mode:'blocks'})")
        self.assertEqual(
            self.page.locator(
                '[data-gyrinx-design-review] rect[fill="#aaa"][width="24"][height="24"]'
            ).count(),
            1,
        )

    def test_grid_tracks_root_after_scroll_and_resize(self):
        self.page.evaluate("gyrinxDesignReview.overlay({mode:'grid', columns:2})")
        self.page.evaluate("window.scrollTo(0, 100)")
        self.page.wait_for_function(
            "document.querySelector('[data-gyrinx-design-review] line').getAttribute('y1') === '0'"
        )
        self.page.set_viewport_size({"width": 600, "height": 400})
        self.page.wait_for_function(
            "document.querySelector('[data-gyrinx-design-review]').getAttribute('width') === '600'"
        )
        self.assertEqual(self.page.locator("[data-gyrinx-design-review]").count(), 1)

    def test_rejects_ambiguous_elements_and_invalid_options(self):
        for expression in (
            "gyrinxDesignReview.compare(['missing'])",
            "gyrinxDesignReview.compare(['main *'])",
            "gyrinxDesignReview.overlay({root:'missing'})",
            "gyrinxDesignReview.overlay({step:0})",
            "gyrinxDesignReview.overlay({columns:0})",
            "gyrinxDesignReview.overlay({gutter:1000})",
            "gyrinxDesignReview.overlay({mode:'unknown'})",
            "gyrinxDesignReview.overlay({mode:'zones', regions:[{selector:'h1', priority:0}]})",
        ):
            with self.subTest(expression=expression):
                self.assertTrue(
                    self.page.evaluate(
                        f"() => {{ try {{ {expression}; return false; }} catch {{ return true; }} }}"
                    )
                )
        self.assertEqual(self.page.locator("[data-gyrinx-design-review]").count(), 0)


if __name__ == "__main__":
    unittest.main()
