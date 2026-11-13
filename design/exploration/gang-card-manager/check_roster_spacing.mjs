import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import * as M from "./src/card-manager-model.js";

const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1355, height: 1256 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const group = (id, name, ids) => ({
    id,
    name,
    colour: "violet",
    showBox: true,
    pin: null,
    children: ids.map((id) => ({ id, pin: null })),
});
const layout = [
    group("panels", "Gang panels", ["campaign", "actions", "stash"]),
    group("forward", "Forward team", ["vesper", "nyx"]),
    group("rear", "Rear team", ["echo", "ash", "rook"]),
];
const menu = page.getByRole("dialog", { name: "Roster view", exact: true });
async function toggle(value) {
    await page
        .getByRole("button", { name: "View controls", exact: true })
        .click();
    await menu
        .getByRole("checkbox", { name: "Separate rows by group" })
        .setChecked(value);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(250);
}
async function dimensions() {
    await page.locator('[data-roster-group="forward"]').waitFor();
    return page.evaluate(() => {
        const root = document.querySelector("#gang-root").shadowRoot;
        const rect = (selector) => {
            const r = root.querySelector(selector).getBoundingClientRect();
            return {
                x: r.x,
                y: r.y + scrollY,
                width: r.width,
                height: r.height,
            };
        };
        return {
            panel: rect('.gang-panel-roster [data-roster-group="panels"]'),
            box: rect('[data-roster-group="forward"]'),
            card: rect("#model-vesper"),
            second: rect("#model-nyx"),
            heading: rect(".roster-carousel > header > :first-child"),
            panelCard: rect('[data-flip="card-campaign"]'),
        };
    });
}
function closeEnough(a, b, label) {
    for (const key of Object.keys(a).filter(
        (key) => !label.endsWith("heading") || key !== "width",
    ))
        assert(
            Math.abs(a[key] - b[key]) < 1.1,
            `${label}.${key}: ${a[key]} versus ${b[key]}`,
        );
}
try {
    await page.goto(`${process.env.BASE_URL || "http://127.0.0.1:8776"}/gang/`);
    await page.evaluate(
        ({ layout, key }) => {
            localStorage.setItem(key, JSON.stringify(layout));
            localStorage.setItem(
                "gyrinx-roster-view-v1",
                JSON.stringify({
                    size: "small",
                    sideScroll: true,
                    separateGroups: false,
                }),
            );
        },
        { layout, key: M.STORAGE_KEY },
    );
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    mkdirSync("qa", { recursive: true });
    for (const width of [1355, 390, 320]) {
        await page.setViewportSize({ width, height: 1256 });
        await page.waitForTimeout(250);
        const before = await dimensions();
        assert(
            Math.abs(before.card.y - before.box.y - 14) < 1.1,
            "The usual 14px group-box clearance is retained.",
        );
        assert(
            await page
                .locator(".roster-carousel .gang-group-box-label")
                .first()
                .evaluate((label) => {
                    const track = label
                        .closest(".roster-carousel-track")
                        .getBoundingClientRect();
                    const rect = label.getBoundingClientRect();
                    return (
                        rect.top >= track.top + 1 && rect.bottom <= track.bottom
                    );
                }),
            "The complete label fits inside the scrolling viewport.",
        );
        await page
            .getByRole("button", { name: "View controls", exact: true })
            .click();
        assert.equal(
            await menu.locator(".roster-view-choice small").count(),
            0,
        );
        await page.keyboard.press("Escape");
        await toggle(true);
        const after = await dimensions();
        assert(
            await page
                .locator(".roster-carousel")
                .first()
                .evaluate(
                    (row) =>
                        getComputedStyle(
                            row.querySelector(".roster-carousel-title"),
                        ).color ===
                        getComputedStyle(row.querySelector(".gang-group-box"))
                            .color,
                ),
            "Group headings use the outline colour.",
        );
        for (const key of [
            "panel",
            "panelCard",
            "box",
            "card",
            "second",
            "heading",
        ])
            closeEnough(before[key], after[key], `${width}px ${key}`);
        const metrics = await page
            .locator(".roster-carousel-track")
            .first()
            .evaluate((el) => ({
                top: parseFloat(getComputedStyle(el).paddingTop),
                bottom: parseFloat(getComputedStyle(el).paddingBottom),
            }));
        assert.equal(metrics.top, 22);
        assert.equal(metrics.bottom, 10);
        assert.equal(
            await page
                .locator(".roster-carousel > header")
                .first()
                .getByRole("button", {
                    name: "Edit group Forward team",
                    exact: true,
                })
                .count(),
            1,
        );
        assert.equal(
            await page
                .locator(
                    '.roster-carousel [data-roster-group="forward"] .gang-group-box-label',
                )
                .count(),
            0,
        );
        assert(
            !(await page.evaluate(
                () => document.documentElement.scrollWidth > innerWidth,
            )),
        );
        await page.screenshot({
            path: `qa/roster-spacing-${width}-separate.png`,
            fullPage: true,
        });
        await toggle(false);
        const restored = await dimensions();
        for (const key of Object.keys(before))
            closeEnough(
                before[key],
                restored[key],
                `${width}px restored ${key}`,
            );
        if (width === 1355)
            await page.screenshot({
                path: "qa/roster-spacing-desktop-continuous.png",
                fullPage: true,
            });
    }
    await page
        .getByRole("button", { name: "Toggle dark mode", exact: true })
        .click();
    await toggle(true);
    await page.screenshot({
        path: "qa/roster-spacing-mobile-dark.png",
        fullPage: true,
    });
    assert.deepEqual(errors, []);
    console.log(
        "Roster spacing passed: panel outlines persist, first heading/box/card coordinates and sizes stay fixed across grouping toggles at desktop, 390px and 320px; tighter padding and removed helper copy verified.",
    );
} finally {
    await browser.close();
}
