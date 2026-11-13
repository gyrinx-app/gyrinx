import assert from "node:assert/strict";
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import * as M from "./src/card-manager-model.js";

const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [],
    posts = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("request", (request) => {
    if (request.method() === "POST") posts.push(request.url());
});
const origin = process.env.BASE_URL || "http://127.0.0.1:8776";
const view = page.getByRole("button", { name: "View controls", exact: true });
const menu = page.getByRole("dialog", { name: "Roster view", exact: true });
const side = menu.getByRole("checkbox", { name: "Side-scroll mode" });
const separate = menu.getByRole("checkbox", { name: "Separate rows by group" });
const track = page.locator(".roster-carousel-track");
async function ready() {
    await page.locator("#model-nyx").waitFor();
    await page.waitForFunction(
        () =>
            document
                .querySelector("#gang-root")
                .shadowRoot.querySelector("link").sheet,
    );
    await page.evaluate(() => document.fonts.ready);
}
async function escape() {
    await page.keyboard.press("Escape");
    await menu.waitFor({ state: "hidden" });
}
async function settled() {
    await page.waitForTimeout(1000);
}
try {
    await page.goto(`${origin}/gang/?names=short`);
    await ready();
    const hireBox = await page
        .getByRole("button", { name: "Hire fighters", exact: true })
        .boundingBox();
    assert((await view.boundingBox()).x < hireBox.x);
    await view.click();
    assert(await separate.isDisabled());
    const widths = [];
    for (const size of ["Small", "Standard", "Large"]) {
        await menu.getByRole("radio", { name: size, exact: true }).check();
        widths.push((await page.locator("#model-nyx").boundingBox()).width);
    }
    assert(
        widths[0] < widths[1] && widths[1] < widths[2],
        JSON.stringify(widths),
    );
    if (await page.locator(".gang-standard").count()) {
        await menu.getByRole("radio", { name: "Small", exact: true }).check();
        assert(
            await page
                .locator(".gang-standard .gang-book-values > td:last-child")
                .evaluateAll((cells) =>
                    cells.every((cell) => cell.scrollWidth <= cell.clientWidth),
                ),
            "XP values fit the smallest cards.",
        );
    }
    await menu.getByRole("radio", { name: "Standard", exact: true }).check();
    await escape();
    assert(await view.evaluate((el) => el === el.getRootNode().activeElement));
    await page
        .locator("#model-nyx")
        .getByRole("tab", { name: "Lore", exact: true })
        .click();
    const rook = page.locator("#model-rook");
    let picture = null;
    if (
        await rook
            .getByRole("button", { name: "Add picture for Rook", exact: true })
            .count()
    ) {
        const chooser = page.waitForEvent("filechooser");
        await rook
            .getByRole("button", { name: "Add picture for Rook", exact: true })
            .click();
        await (await chooser).setFiles("public/static/cards/dog-golden.jpg");
        const crop = page.getByRole("dialog", {
            name: "Crop the picture",
            exact: true,
        });
        await crop
            .getByRole("button", { name: "Use this crop", exact: true })
            .click();
        await crop.waitFor({ state: "hidden" });
        picture = await rook.locator(".gang-portrait img").getAttribute("src");
    }
    await view.click();
    await side.check();
    await escape();
    assert.equal(await track.count(), 1);
    if (picture) {
        assert.equal(
            await rook.locator(".gang-portrait img").getAttribute("src"),
            picture,
        );
        assert(
            await rook.locator(".gang-portrait img").evaluate(async (img) => {
                await img.decode();
                return img.naturalWidth > 0;
            }),
        );
    }
    assert.equal(
        await page
            .locator("#model-nyx")
            .getByRole("tab", { name: "Lore", exact: true })
            .getAttribute("aria-selected"),
        "true",
    );
    assert.equal(await page.locator(".gang-special").count(), 3);
    const row = page.locator(".roster-carousel");
    assert.equal(
        await track
            .locator(":scope > .gang-card")
            .evaluateAll(
                (els) =>
                    new Set(
                        els.map((el) =>
                            Math.round(el.getBoundingClientRect().top),
                        ),
                    ).size,
            ),
        1,
    );
    await row
        .getByRole("button", { name: "Next card in Models", exact: true })
        .click();
    await settled();
    assert((await track.evaluate((el) => el.scrollLeft)) > 0);
    await track.focus();
    await page.keyboard.press("End");
    await page.waitForFunction(
        () =>
            document
                .querySelector("#gang-root")
                .shadowRoot.querySelector(
                    ".roster-carousel header button:last-child",
                ).disabled,
    );
    assert(
        await row
            .getByRole("button", { name: "Next card in Models", exact: true })
            .isDisabled(),
    );
    await page.keyboard.press("Home");
    await page.waitForFunction(
        () =>
            document
                .querySelector("#gang-root")
                .shadowRoot.querySelector(".roster-carousel-track").scrollLeft <
            2,
    );
    assert(
        await row
            .getByRole("button", {
                name: "Previous card in Models",
                exact: true,
            })
            .isDisabled(),
    );
    // Dragging a card surface moves the track without activating card controls.
    const rect = await track.boundingBox();
    await page.mouse.move(rect.x + 280, rect.y + 230);
    await page.mouse.down();
    await page.mouse.move(rect.x + 40, rect.y + 230, { steps: 10 });
    await page.mouse.up();
    await settled();
    assert((await track.evaluate((el) => el.scrollLeft)) > 0);
    // Releasing an unstarted drag outside the track must not arm the next hover.
    await track.evaluate((el) => el.scrollTo({ left: 0, behavior: "instant" }));
    await page.waitForTimeout(100);
    await track.dispatchEvent("pointerdown", {
        pointerId: 543,
        pointerType: "mouse",
        button: 0,
        clientX: 300,
    });
    await page.locator("body").dispatchEvent("pointerup", {
        pointerId: 543,
        pointerType: "mouse",
        button: 0,
    });
    await track.dispatchEvent("pointermove", {
        pointerId: 543,
        pointerType: "mouse",
        clientX: 40,
    });
    assert.equal(await track.evaluate((el) => el.scrollLeft), 0);
    // Group rows preserve visible roster order, pets, hidden state and saved colours.
    const layout = [
        M.defaults()[0],
        { id: "nyx", pin: null },
        {
            id: "forward",
            name: "Forward team",
            colour: "violet",
            pin: null,
            showBox: true,
            children: [
                { id: "vesper", pin: null },
                { id: "ash", pin: null, hidden: true },
            ],
        },
        { id: "sera", pin: null },
        { id: "jade", pin: null },
        {
            id: "rear",
            name: "Rear team",
            colour: "none",
            pin: null,
            children: [
                { id: "rook", pin: null },
                { id: "wren", pin: null },
            ],
        },
        { id: "crawler", pin: null },
    ];
    await page.evaluate(
        ({ key, layout }) => localStorage.setItem(key, JSON.stringify(layout)),
        { key: M.STORAGE_KEY, layout },
    );
    await page.reload();
    await ready();
    await view.click();
    await escape();
    await page.locator(".gang-group-box").first().waitFor();
    await view.click();
    await separate.check();
    await escape();
    assert.deepEqual(
        await page
            .locator("[data-carousel-row]")
            .evaluateAll((els) => els.map((el) => el.dataset.carouselRow)),
        [
            "ungrouped-nyx",
            "forward",
            "ungrouped-sera",
            "rear",
            "ungrouped-crawler",
        ],
    );
    assert.equal(
        await page
            .locator('[data-carousel-row="forward"] .gang-card:visible')
            .count(),
        3,
    );
    assert(!(await page.locator("#model-ash").isVisible()));
    assert.equal(await page.locator("#model-vesper-pet-1").count(), 1);
    await page.setViewportSize({ width: 1000, height: 1050 });
    await page
        .locator('[data-carousel-row="rear"]')
        .getByRole("button", { name: "Next card in Rear team", exact: true })
        .click();
    await settled();
    assert.equal(
        await page
            .locator('[data-carousel-row="forward"] .roster-carousel-track')
            .evaluate((el) => el.scrollLeft),
        0,
    );
    await page.setViewportSize({ width: 1440, height: 1050 });
    mkdirSync("qa", { recursive: true });
    await page.screenshot({
        path: "qa/roster-view-desktop.png",
        fullPage: true,
    });
    await page.reload();
    await ready();
    assert.equal(await track.count(), 5);
    // The phone carousel fills its viewport with one card at a time.
    for (const width of [768, 390, 320]) {
        await page.setViewportSize({ width, height: 900 });
        await view.click();
        const bounds = await menu.boundingBox();
        assert(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
        if (width < 768) assert.equal(await menu.getByRole("radio").count(), 0);
        await escape();
        assert(
            !(await page.evaluate(
                () => document.documentElement.scrollWidth > innerWidth,
            )),
        );
        if (width < 768) {
            const first = page.locator(
                '[data-carousel-row="forward"] .roster-carousel-track',
            );
            await first.evaluate((el) =>
                el.scrollTo({ left: 0, behavior: "instant" }),
            );
            await page.waitForFunction(
                () =>
                    document
                        .querySelector("#gang-root")
                        .shadowRoot.querySelector(
                            '[data-carousel-row="forward"] .roster-carousel-track',
                        ).scrollLeft < 2,
            );
            assert(
                await first.evaluate((el) => {
                    const cards = [...el.children].filter(
                        (card) => !card.hidden,
                    );
                    const trackBox = el.getBoundingClientRect(),
                        a = cards[0].getBoundingClientRect(),
                        b = cards[1].getBoundingClientRect();
                    return (
                        Math.abs(a.width - (trackBox.width - 16)) < 2 &&
                        b.left >= trackBox.right
                    );
                }),
            );
            await first.focus();
            await page.keyboard.press("ArrowRight");
            await settled();
            assert((await first.evaluate((el) => el.scrollLeft)) > 0);
        }
        if (width === 390) {
            await page
                .getByRole("button", { name: "Toggle dark mode", exact: true })
                .click();
            await page.screenshot({
                path: "qa/roster-view-mobile-dark.png",
                fullPage: true,
            });
            await view.click();
            await page.screenshot({ path: "qa/roster-view-menu-mobile.png" });
            await escape();
        }
    }
    await page.setViewportSize({ width: 1440, height: 1050 });
    await view.click();
    await side.uncheck();
    await escape();
    assert.equal(await track.count(), 0);
    assert.equal(await page.locator(".gang-grid").count(), 1);
    await view.click();
    await menu.getByRole("radio", { name: "Small", exact: true }).check();
    await page.screenshot({ path: "qa/roster-view-menu-desktop.png" });
    await page.locator("h1").click();
    assert(!(await menu.isVisible()));
    await page.evaluate(
        ({ key, layout }) =>
            localStorage.setItem(
                key,
                JSON.stringify(
                    layout.map((node) => ({ ...node, hidden: true })),
                ),
            ),
        { key: M.STORAGE_KEY, layout },
    );
    await page.reload();
    await page.locator("h1").waitFor();
    await view.click();
    await side.check();
    await escape();
    assert.equal(
        await page.locator(".roster-carousel").count(),
        0,
        "Hidden models leave no empty carousel.",
    );
    assert(
        !(await page.locator(".gang-panel-roster").isVisible()),
        "Hidden panels leave no extra section.",
    );
    assert.deepEqual(errors, []);
    assert.deepEqual(posts, []);
    console.log(
        "Roster view passed: sizes, menu focus, carousel arrows/keyboard/drag, independent groups, ordered ungrouped runs, pets, hidden cards, persistence, mobile sizing and both themes. No network writes.",
    );
} finally {
    await browser.close();
}
