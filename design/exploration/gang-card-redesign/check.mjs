import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { nameplateEdge } from "./src/nameplate-edge.js";

assert.equal(nameplateEdge("Nyx"), nameplateEdge("Nyx"));
assert.notEqual(nameplateEdge("Nyx"), nameplateEdge("Ash"));
assert.equal(nameplateEdge("Encañada"), nameplateEdge("Encan\u0303ada"));
const origin = process.env.CARDS_ORIGIN || "http://127.0.0.1:8768";
const browser = await chromium.launch({
    ...(process.env.CHROME_PATH
        ? { executablePath: process.env.CHROME_PATH }
        : {}),
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1512, height: 1050 } });
const errors = [],
    posts = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("request", (request) => {
    if (request.method() === "POST") posts.push(request.url());
});
mkdirSync("qa", { recursive: true });
const card = page.locator("#model-wren"),
    rook = page.locator("#model-rook");
const camera = rook.getByRole("button", {
    name: "Add picture for Rook",
    exact: true,
});
const dialog = page.getByRole("dialog", {
    name: "Crop the picture",
    exact: true,
});
const confirm = dialog.getByRole("button", {
    name: "Use this crop",
    exact: true,
});
async function open() {
    await page.goto(origin);
    await card.waitFor();
    await page.waitForFunction(
        () =>
            document
                .querySelector("#gang-root")
                .shadowRoot.querySelector("link").sheet,
    );
    await page.evaluate(() => document.fonts.ready);
}
try {
    await open();
    assert.equal(
        await page.locator(".gang-special,.callout-card,.cm-dialog").count(),
        0,
        "Only model cards are submitted.",
    );
    assert.equal(
        await page
            .locator("#model-crawler .gang-book-values > td:nth-last-child(2)")
            .textContent(),
        "Vehicle",
    );
    const picker = page.getByRole("combobox", { name: "Gang colour" });
    const colours = await picker
        .locator("option")
        .evaluateAll((els) => els.map((el) => el.value));
    assert.equal(colours.length, 18);
    for (const dark of [false, true]) {
        if (dark)
            await page
                .getByRole("button", { name: "Toggle dark mode" })
                .click();
        for (const colour of colours) {
            await picker.selectOption(colour);
            await page.waitForFunction(
                () =>
                    !document
                        .querySelector("#gang-root")
                        .shadowRoot.querySelector(".gang-page")
                        .style.getPropertyValue("--gang-rating-ink")
                        .includes("var("),
            );
            const style = await card.evaluate((el) => {
                const rating = el.querySelector(".gang-rating"),
                    fill = getComputedStyle(rating);
                const canvas = document.createElement("canvas");
                canvas.width = canvas.height = 1;
                const ctx = canvas.getContext("2d");
                const luminance = (colour) => {
                    ctx.fillStyle = colour;
                    ctx.fillRect(0, 0, 1, 1);
                    const c = [...ctx.getImageData(0, 0, 1, 1).data]
                        .slice(0, 3)
                        .map((n) => {
                            const x = n / 255;
                            return x <= 0.04045
                                ? x / 12.92
                                : ((x + 0.055) / 1.055) ** 2.4;
                        });
                    return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
                };
                const back = luminance(fill.backgroundColor),
                    ink = luminance(fill.color);
                return {
                    labels: [
                        ...el.querySelectorAll(
                            ".gang-statline th,.gang-model-details dt,.gang-weapons th",
                        ),
                    ].map((label) => getComputedStyle(label).color),
                    ink: getComputedStyle(el).color,
                    stat: getComputedStyle(
                        el.querySelector(".gang-book-header"),
                    ).backgroundColor,
                    header: getComputedStyle(
                        el.querySelector("header"),
                        "::before",
                    ).backgroundColor,
                    contrast:
                        (Math.max(back, ink) + 0.05) /
                        (Math.min(back, ink) + 0.05),
                    ratingHeight: rating.offsetHeight,
                    band: parseFloat(getComputedStyle(el).paddingTop),
                };
            });
            assert(style.labels.every((ink) => ink === style.ink));
            if (dark) assert.equal(style.stat, style.header);
            assert(
                style.contrast >= 4.5,
                `${colour} rating contrast in ${dark ? "dark" : "light"} mode`,
            );
            assert.equal(style.ratingHeight, style.band);
            assert.equal(
                new URL(page.url()).searchParams.get("colour"),
                colour,
            );
        }
        await picker.selectOption("sky");
        for (const name of ["Card", "Lore", "Notes"]) {
            await card.getByRole("tab", { name, exact: true }).click();
            const alignment = await card.evaluate((el) => {
                const panel = el.querySelector('[role="tabpanel"]'),
                    tab = el.querySelector('[aria-selected="true"]');
                const body = panel.getBoundingClientRect(),
                    bounds = tab.getBoundingClientRect();
                const scale =
                    el.getBoundingClientRect().width /
                    parseFloat(getComputedStyle(el).width);
                return {
                    bottom: bounds.bottom - body.top,
                    x:
                        bounds.left +
                        parseFloat(tab.style.getPropertyValue("--paper-x")) *
                            scale -
                        body.left,
                    y:
                        body.top +
                        parseFloat(panel.style.getPropertyValue("--paper-y")) *
                            scale -
                        bounds.top,
                    panelImage: getComputedStyle(panel).backgroundImage,
                    tabImage: getComputedStyle(tab).backgroundImage,
                    size: getComputedStyle(panel).backgroundSize,
                    tabSize: getComputedStyle(tab).backgroundSize,
                    line: getComputedStyle(
                        el.querySelector(".gang-card-controls"),
                    ).borderBottomColor,
                    outline: getComputedStyle(tab).borderTopColor,
                };
            });
            assert(
                Math.abs(alignment.bottom) < 0.5 &&
                    Math.abs(alignment.x) < 0.5 &&
                    Math.abs(alignment.y) < 0.5,
            );
            assert.equal(alignment.panelImage, alignment.tabImage);
            assert.equal(alignment.size, alignment.tabSize);
            assert.equal(alignment.line, alignment.outline);
            assert(
                dark
                    ? alignment.panelImage === "none"
                    : alignment.panelImage.includes("classic-blank.jpg"),
            );
        }
        await card.getByRole("tab", { name: "Card", exact: true }).focus();
        await page.keyboard.press("End");
        assert.equal(
            await card
                .getByRole("tab", { name: "Notes", exact: true })
                .getAttribute("aria-selected"),
            "true",
        );
        await page.keyboard.press("Home");
        const menu = card.locator(".gang-model-menu");
        await menu.locator("summary").click();
        for (const option of await menu.locator("button").all()) {
            await option.hover();
            assert.notEqual(
                await option.evaluate(
                    (el) => getComputedStyle(el).backgroundColor,
                ),
                "rgba(0, 0, 0, 0)",
            );
        }
        await menu.locator("summary").focus();
        await page.keyboard.press("Escape");
        assert.equal(await menu.getAttribute("open"), null);
        await card
            .getByRole("button", {
                name: "Equip Wren, Last Daughter of the Thirteen Ashen Spires",
                exact: true,
            })
            .click();
        await page
            .getByRole("dialog")
            .getByRole("button", { name: "Close", exact: true })
            .last()
            .click();
        for (const width of [1512, 390, 320]) {
            await page.setViewportSize({ width, height: 1050 });
            await card.hover();
            await card.evaluate((el) =>
                Promise.all(el.getAnimations().map((a) => a.finished)),
            );
            assert.equal(
                await page.evaluate(
                    () => document.documentElement.scrollWidth > innerWidth,
                ),
                false,
            );
            assert(
                await page
                    .locator(
                        ".gang-new .gang-weapons tr > :nth-child(n + 2):nth-child(-n + 6)",
                    )
                    .evaluateAll((cells) =>
                        cells.every((cell) => {
                            if (cell.colSpan > 1) return true;
                            const range = document.createRange();
                            range.selectNodeContents(cell);
                            return (
                                range.getBoundingClientRect().width <=
                                    cell.getBoundingClientRect().width + 0.5 &&
                                range.getClientRects().length <= 1
                            );
                        }),
                    ),
            );
            await page.mouse.move(0, 0);
            await card.screenshot({
                path: `qa/card-${width}-${dark ? "dark" : "light"}.png`,
                animations: "disabled",
            });
        }
        await page.setViewportSize({ width: 1512, height: 1050 });
    }
    await open();
    const chooser = page.waitForEvent("filechooser");
    await camera.click();
    await (
        await chooser
    ).setFiles(resolve("public/static/cards/dog-golden.jpg"));
    await dialog.waitFor();
    await confirm.waitFor();
    await page.waitForFunction(
        () =>
            !document
                .querySelector("#gang-root")
                .shadowRoot.querySelector(
                    ".gang-picture-crop button[aria-busy]",
                ).disabled,
    );
    const box = dialog.locator(".cropper-crop-box"),
        before = await box.boundingBox();
    const point = await dialog.locator(".cropper-point.point-se").boundingBox();
    await page.mouse.move(
        point.x + point.width / 2,
        point.y + point.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(point.x - 25, point.y - 30, { steps: 8 });
    await page.mouse.up();
    assert((await box.boundingBox()).width < before.width - 5);
    await confirm.click();
    await dialog.waitFor({ state: "hidden" });
    assert(
        await rook
            .locator(".gang-portrait")
            .evaluate((el) => el.matches(":focus")),
    );
    const dimensions = await rook
        .locator(".gang-portrait img")
        .evaluate(async (img) => {
            await img.decode();
            return [img.naturalWidth, img.naturalHeight];
        });
    assert(
        Math.abs(dimensions[0] / dimensions[1] - 4 / 5) < 0.01 &&
            Math.max(...dimensions) <= 1600,
    );
    for (const file of [
        {
            name: "broken.png",
            mimeType: "image/png",
            buffer: Buffer.from("broken"),
        },
        {
            name: "large.png",
            mimeType: "image/png",
            buffer: Buffer.alloc(10 * 1024 * 1024 + 1),
        },
    ]) {
        await open();
        await rook.locator('input[type="file"]').setInputFiles(file);
        await dialog.getByRole("alert").waitFor();
        assert(await confirm.isDisabled());
        await page.keyboard.press("Escape");
        await dialog.waitFor({ state: "hidden" });
        assert(await camera.isVisible());
    }
    assert.deepEqual(errors, []);
    assert.deepEqual(posts, []);
    console.log(
        "Model cards passed: 18 colours, both themes, responsive layouts, texture joins, keyboard tabs and menus, simulated actions, image crop/focus and invalid/oversized images. No gang boxes, manager or network writes.",
    );
} finally {
    await browser.close();
}
