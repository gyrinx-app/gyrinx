const origin = process.env.CAMPAIGN_ORIGIN || "http://127.0.0.1:8768";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { defaults, storageKey } from "./src/campaign-model.js";

const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    headless: true,
});
const names = [
    "The Ash Road",
    "The Siege of Hive Primus: Ash Road Uprising",
    "The Last War for the Forgotten Settlements Beyond the Gates of Hive Primus",
    "Underhive".repeat(10),
];
const widths = [320, 390, 560, 640, 760, 769, 1024, 1199, 1200, 1512];
const errors = [];
let cases = 0;
mkdirSync("qa", { recursive: true });
try {
    const page = await browser.newPage();
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${origin}/campaign/`);
    for (const [index, name] of names.entries()) {
        for (const viewer of ["player", "arbitrator"]) {
            for (const width of widths) {
                const label = `${viewer}, ${width}px, ${name}`;
                const state = defaults();
                state.name = name;
                await page.evaluate(
                    ({ key, state }) =>
                        localStorage.setItem(key, JSON.stringify(state)),
                    { key: storageKey, state },
                );
                await page.setViewportSize({ width, height: 900 });
                await page.goto(
                    `${origin}/campaign/?view=dashboard&viewer=${viewer}`,
                );
                const root = page.locator("#campaign-root");
                const title = root.getByRole("heading", { name, exact: true });
                await title.waitFor();
                await page.evaluate(() => document.fonts.ready);
                const actions = await root
                    .getByLabel("Campaign actions", { exact: true })
                    .boundingBox();
                const heading = await title.boundingBox();
                assert.equal(
                    await page.evaluate(
                        () =>
                            document.documentElement.scrollWidth >
                            innerWidth + 1,
                    ),
                    false,
                    label,
                );
                assert.equal(
                    await title.evaluate(
                        (el) => el.scrollWidth > el.clientWidth + 1,
                    ),
                    false,
                    `Title overflow: ${label}`,
                );
                assert.ok(
                    actions.x >= 0 && actions.x + actions.width <= width + 1,
                    `Action overflow: ${label}`,
                );
                const beside =
                    (viewer === "player" ? width >= 640 : width >= 768) &&
                    width < 1200;
                if (beside) {
                    assert.ok(
                        actions.x >= heading.x + heading.width - 1,
                        `Actions beside title: ${label}`,
                    );
                    assert.ok(
                        actions.y < heading.y + heading.height,
                        `Actions share title row: ${label}`,
                    );
                }
                if (width >= 768 && width < 1200) {
                    const period = await root
                        .getByLabel("Current campaign period")
                        .boundingBox();
                    const metadata = await root
                        .locator(".cp-campaign-metadata")
                        .boundingBox();
                    assert.ok(
                        Math.abs(period.y - metadata.y) < 2,
                        `Metadata shares period row: ${label}`,
                    );
                }
                if (
                    (index === 1 &&
                        viewer === "player" &&
                        [390, 760, 769, 1512].includes(width)) ||
                    (index === 2 && viewer === "arbitrator" && width === 769)
                ) {
                    await page.screenshot({
                        path: `qa/campaign-long-name-${index}-${viewer}-${width}.png`,
                    });
                }
                cases++;
            }
        }
    }
    assert.deepEqual(errors, []);
    console.log(
        `Campaign long-name checks passed (${cases} cases across ${widths.length} widths and both views).`,
    );
} finally {
    await browser.close();
}
