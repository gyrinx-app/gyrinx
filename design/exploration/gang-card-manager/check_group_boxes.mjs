import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import * as M from "./src/card-manager-model.js";
import { groupBoxShapes } from "./src/group-box-geometry.js";

const initial = M.defaults();
assert(initial.filter((n) => n.children).every((n) => !n.showBox));
const targets = M.groupActionIds(initial, ["special", "fallen"], "special");
assert.deepEqual(targets, ["special", "fallen"]);
assert.deepEqual(
    M.groupActionIds(
        initial,
        ["campaign", "actions", "stash", "violet", "crawler"],
        "special",
    ),
    targets,
);
assert.deepEqual(M.groupActionIds(initial, ["special"], "fallen"), ["fallen"]);
const shown = M.setGroupBox(initial, targets, true);
assert(shown.filter((n) => n.children).every((n) => n.showBox));
assert(
    initial.filter((n) => n.children).every((n) => !n.showBox),
    "Draft updates preserve saved state.",
);
assert(
    M.sortCards(shown, "name-asc")
        .filter((n) => n.children)
        .every((n) => n.showBox),
);
assert(M.validLayout(shown, ["ink"]));
assert(M.validLayout([{ ...initial[0], colour: "none" }], ["ink"]));
assert(
    M.validLayout(initial, ["ink"]),
    "Old layouts without showBox remain valid.",
);
for (const showBox of [1, "true", null, {}, []]) {
    assert.equal(M.validLayout([{ ...initial[0], showBox }], ["ink"]), false);
}
assert(M.ungroup(shown, targets).every((n) => !n.children));
const rect = (row, left, right) => ({
    row,
    left,
    right,
    top: row * 120,
    bottom: row * 120 + 100,
});
assert.equal(groupBoxShapes([rect(0, 0, 300), rect(1, 0, 300)])[0].rows, 2);
const split = groupBoxShapes([rect(0, 200, 300), rect(1, 0, 100)]);
assert.equal(split.length, 2);
assert.equal(split[0].openRight, true);
assert.equal(split[1].openLeft, true);
assert(split.every((shape) => shape.dottedPath.length > 0));
const stepped = groupBoxShapes([
    rect(0, 200, 300),
    rect(1, 0, 300),
    rect(2, 0, 100),
]);
assert.equal(stepped.length, 1);
assert.equal(stepped[0].rows, 3);
assert.equal(stepped[0].dottedPath, "");
assert(!stepped[0].path.includes("NaN"));

const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
const origin = process.env.BASE_URL || "http://127.0.0.1:8776";
const manager = page.getByRole("dialog", { name: "Card Manager", exact: true });
const header = (id) => manager.locator(`[data-group-id="${id}"]`);
const toggle = (id) =>
    header(id).getByRole("button", { name: "Show group box", exact: true });
const boxes = (id) => page.locator(`[data-roster-group="${id}"]`);
async function open() {
    await page
        .getByRole("button", { name: "Card Manager", exact: true })
        .click();
}
async function save() {
    await manager.getByRole("button", { name: "Save", exact: true }).click();
    await manager.waitFor({ state: "hidden" });
}
async function seed(layout) {
    await page.evaluate(
        ({ key, layout }) => localStorage.setItem(key, JSON.stringify(layout)),
        { key: M.STORAGE_KEY, layout },
    );
    await page.reload();
    await page
        .getByRole("button", { name: "Card Manager", exact: true })
        .waitFor();
    await page.evaluate(() => document.fonts.ready);
    // Let ResizeObserver measure the loaded fonts and React commit the outline.
    await page.evaluate(
        () =>
            new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)),
            ),
    );
}
const group = (ids, extra = {}) => ({
    id: "test-group",
    name: "Champions",
    colour: "violet",
    pin: null,
    showBox: true,
    children: ids.map((id) => ({ id, pin: null })),
    ...extra,
});
mkdirSync("qa", { recursive: true });
try {
    await page.goto(`${origin}/gang/?names=short`);
    assert.equal(await page.locator(".gang-group-box").count(), 0);
    await open();
    assert.equal(await toggle("special").getAttribute("aria-pressed"), "false");
    assert.equal(
        await toggle("special").locator("svg.lucide-square-dashed").count(),
        1,
    );
    const position = await header("special").evaluate((el) => {
        const buttons = [...el.children];
        return (
            buttons.indexOf(el.querySelector(".cm-header-box")) + 1 ===
            buttons.indexOf(el.querySelector(".cm-header-ungroup"))
        );
    });
    assert(position);
    await header("special").getByRole("checkbox").check();
    await header("fallen").getByRole("checkbox").check();
    await toggle("special").click();
    assert.equal(await toggle("fallen").getAttribute("aria-pressed"), "true");
    await toggle("fallen").click();
    assert.equal(await toggle("special").getAttribute("aria-pressed"), "false");
    await toggle("special").click();
    await save();
    await boxes("special").first().waitFor();
    await boxes("fallen").first().waitFor();
    await page.reload();
    await boxes("fallen").first().waitFor();
    await open();
    await toggle("special").click();
    await manager.getByRole("button", { name: "Cancel", exact: true }).click();
    await page
        .getByRole("dialog", { name: "Discard changes?", exact: true })
        .getByRole("button", { name: "Discard changes", exact: true })
        .click();
    await open();
    assert.equal(await toggle("special").getAttribute("aria-pressed"), "true");
    await header("special").getByRole("checkbox").check();
    await header("fallen").getByRole("checkbox").check();
    await header("fallen")
        .getByRole("button", { name: "Ungroup Dead / destroyed", exact: true })
        .click();
    assert.equal(await manager.locator("[data-group-id]").count(), 0);
    await save();
    assert.equal(await page.locator(".gang-group-box").count(), 0);

    // A short diagonal wrap keeps its continuation ends open.
    await seed([initial[0], group(["nyx", "ash"])]);
    await boxes("test-group").nth(1).waitFor();
    assert.equal(await boxes("test-group").count(), 2);
    assert.equal(
        await boxes("test-group").nth(0).getAttribute("data-open-right"),
        "true",
    );
    assert.equal(
        await boxes("test-group").nth(1).getAttribute("data-open-left"),
        "true",
    );
    assert.equal(
        await boxes("test-group").locator(".gang-group-box-label").count(),
        1,
    );
    const dots = boxes("test-group").locator(".gang-group-box-dots");
    assert.equal(await dots.count(), 2);
    for (const stroke of await dots.all()) {
        assert.equal(await stroke.getAttribute("stroke-dasharray"), "1 3");
        assert.equal(await stroke.getAttribute("stroke-linecap"), "round");
        assert(
            Math.abs(
                (await stroke.evaluate((path) => path.getTotalLength())) - 48,
            ) < 0.1,
        );
    }
    const bevel = await boxes("test-group")
        .nth(1)
        .evaluate((box) => {
            const path = box.querySelector(".gang-group-box-outline"),
                width = parseFloat(box.style.width);
            const card = box.getRootNode().querySelector(".callout-frame");
            const cut = card
                ? parseFloat(getComputedStyle(card).borderTopRightRadius)
                : 8;
            return {
                corner: path.isPointInStroke(new DOMPoint(width - 0.5, 0.5)),
                bevel: path.isPointInStroke(
                    new DOMPoint(width - 0.5 - cut / 2, 0.5 + cut / 2),
                ),
            };
        });
    assert.equal(bevel.corner, false);
    assert.equal(bevel.bevel, true);
    await page.screenshot({
        path: "qa/group-box-open-wrap.png",
        fullPage: true,
        animations: "disabled",
    });

    // Overlapping columns form one outline with no horizontal seam through the overlap.
    await seed([initial[0], group(["nyx", "ash", "sera", "jade", "rook"])]);
    await boxes("test-group").first().waitFor();
    assert.equal(await boxes("test-group").count(), 1);
    assert.equal(await boxes("test-group").getAttribute("data-rows"), "3");
    assert.equal(
        await boxes("test-group").locator(".gang-group-box-dots").count(),
        0,
    );
    const seam = await boxes("test-group").evaluate((box) => {
        const root = box.getRootNode(),
            path = box.querySelector(".gang-group-box-outline");
        const grid = root.querySelector(".gang-grid");
        const a = root.querySelector("#model-nyx"),
            b = root.querySelector("#model-jade");
        const left = parseFloat(box.style.left),
            top = parseFloat(box.style.top);
        const y = (a.offsetTop + a.offsetHeight + b.offsetTop) / 2 - top;
        const x = a.offsetLeft + a.offsetWidth / 2 - left;
        return {
            insideSeam: path.isPointInStroke(new DOMPoint(x, y)),
            connectedSide: path.isPointInStroke(
                new DOMPoint(grid.clientWidth + 6 - left, y),
            ),
            colour: getComputedStyle(box).color,
            labelCenterDelta: Math.abs(
                box
                    .querySelector(".gang-group-box-label")
                    .getBoundingClientRect().top +
                    box
                        .querySelector(".gang-group-box-label")
                        .getBoundingClientRect().height /
                        2 -
                    box.getBoundingClientRect().top -
                    0.5,
            ),
            labelColour: getComputedStyle(
                box.querySelector(".gang-group-box-label"),
            ).color,
            labelBorders: ["Top", "Right", "Bottom", "Left"].map(
                (side) =>
                    getComputedStyle(
                        box.querySelector(".gang-group-box-label"),
                    )[`border${side}Width`],
            ),
            labelBorderColour: getComputedStyle(
                box.querySelector(".gang-group-box-label"),
            ).borderTopColor,
            rosterGap:
                grid.getBoundingClientRect().top -
                root.querySelector(".gang-details-bar").getBoundingClientRect()
                    .bottom,
            topAtNormalLevel: path.isPointInStroke(
                new DOMPoint(
                    root.querySelector("#model-ash").offsetLeft +
                        root.querySelector("#model-ash").offsetWidth / 2 -
                        left,
                    b.offsetTop - 14 - top,
                ),
            ),
            bottomAtNormalLevel: path.isPointInStroke(
                new DOMPoint(
                    b.offsetLeft + b.offsetWidth / 2 - left,
                    Math.max(
                        ...[...grid.children]
                            .filter((cell) => cell.offsetTop === b.offsetTop)
                            .map((cell) => cell.offsetTop + cell.offsetHeight),
                    ) +
                        6 -
                        top,
                ),
            ),
            fillOpacity: getComputedStyle(
                box.querySelector(".gang-group-box-fill"),
            ).fillOpacity,
            fillClosed: box
                .querySelector(".gang-group-box-fill")
                .getAttribute("d")
                .endsWith("Z"),
        };
    });
    assert.equal(seam.insideSeam, false);
    assert.equal(seam.connectedSide, true);
    assert.equal(seam.colour, seam.labelColour);
    assert.equal(seam.labelBorderColour, seam.colour);
    assert(
        seam.labelCenterDelta < 0.01,
        "The box edge crosses the centre of the fully bordered label.",
    );
    assert.deepEqual(seam.labelBorders, ["1px", "1px", "1px", "1px"]);
    assert(seam.rosterGap >= 32);
    assert.equal(
        seam.topAtNormalLevel,
        true,
        "Joined top edges keep the normal card clearance.",
    );
    assert.equal(
        seam.bottomAtNormalLevel,
        true,
        "Joined bottom edges keep the normal card clearance.",
    );
    assert.equal(seam.fillOpacity, "0.05");
    assert.equal(seam.fillClosed, true);
    await page.screenshot({
        path: "qa/group-box-connected-desktop.png",
        fullPage: true,
        animations: "disabled",
    });
    const labelClearsCards = () =>
        page.locator(".gang-group-box-label").evaluateAll((labels) => {
            const cards = [
                ...document
                    .querySelector("#gang-root")
                    .shadowRoot.querySelectorAll(".gang-grid .gang-card"),
            ].map((card) => card.getBoundingClientRect());
            return labels.every((label) => {
                const box = label.getBoundingClientRect();
                return cards.every(
                    (card) =>
                        box.right <= card.left ||
                        box.left >= card.right ||
                        box.bottom <= card.top ||
                        box.top >= card.bottom,
                );
            });
        });
    for (const width of [1440, 1000, 390, 320]) {
        await page.setViewportSize({ width, height: 1050 });
        await page.waitForFunction(() => {
            const root = document.querySelector("#gang-root").shadowRoot;
            const box = root.querySelector(".gang-group-box");
            const grid = root.querySelector(".gang-grid");
            return parseFloat(box.style.width) <= grid.clientWidth + 14;
        });
        assert.equal(await boxes("test-group").count(), 1);
        assert.equal(
            await page.evaluate(
                () => document.documentElement.scrollWidth > innerWidth,
            ),
            false,
        );
        assert(
            await labelClearsCards(),
            `Group labels clear every card at ${width}px.`,
        );
        await page.locator("#model-nyx").hover();
        await page
            .locator("#model-nyx")
            .evaluate((el) =>
                Promise.all(
                    el.getAnimations().map((animation) => animation.finished),
                ),
            );
        assert(
            await labelClearsCards(),
            `Group labels clear hovered cards at ${width}px.`,
        );
        await page.mouse.move(0, 0);
        await open();
        const fits = await header("test-group").evaluate((el) =>
            [...el.children]
                .filter((n) => n.getClientRects().length)
                .every((n) => {
                    const a = el.getBoundingClientRect(),
                        b = n.getBoundingClientRect();
                    return b.left >= a.left && b.right <= a.right + 1;
                }),
        );
        assert(fits, `Group controls fit at ${width}px.`);
        await manager
            .getByRole("button", { name: "Cancel", exact: true })
            .click();
    }
    await page
        .getByRole("button", { name: "Toggle dark mode", exact: true })
        .click();
    await page.screenshot({
        path: "qa/group-box-connected-mobile-dark.png",
        fullPage: true,
        animations: "disabled",
    });

    // Toggling boxes preserves mounted cards, their tabs and attached pets.
    await page.setViewportSize({ width: 1440, height: 1050 });
    await seed([initial[0], group(["vesper", "nyx"], { showBox: false })]);
    const leader = page.locator("#model-vesper");
    await leader.getByRole("tab", { name: "Notes", exact: true }).click();
    const mounted = await leader.elementHandle();
    await open();
    await toggle("test-group").click();
    await save();
    await boxes("test-group").waitFor();
    assert(await mounted.evaluate((el) => el.isConnected));
    assert.equal(
        await leader
            .getByRole("tab", { name: "Notes", exact: true })
            .getAttribute("aria-selected"),
        "true",
    );
    assert.equal(await page.locator('.gang-grid > [id^="model-"]').count(), 4);
    assert.equal(await boxes("test-group").getAttribute("data-rows"), "2");
    await page.screenshot({
        path: "qa/group-box-pets.png",
        fullPage: true,
        animations: "disabled",
    });
    // The roster label opens a real editor and preserves mounted card state.
    const editor = page.getByRole("dialog", {
        name: "Edit group",
        exact: true,
    });
    await page
        .getByRole("button", { name: "Edit group Champions", exact: true })
        .click();
    assert.equal(
        await editor
            .getByRole("group", { name: "Group colour", exact: true })
            .getByRole("button")
            .count(),
        19,
    );
    assert.equal(await editor.getByRole("combobox").count(), 0);
    await editor.getByLabel("Group name", { exact: true }).fill("Forward team");
    await editor
        .getByRole("button", { name: "No colour", exact: true })
        .click();
    await editor.getByRole("button", { name: "Save", exact: true }).click();
    await editor.waitFor({ state: "hidden" });
    await page
        .getByRole("button", { name: "Edit group Forward team", exact: true })
        .waitFor();
    assert.equal(
        await boxes("test-group").locator(".gang-group-box-fill").count(),
        0,
    );
    assert.equal(
        await boxes("test-group").evaluate((box) =>
            box.style.getPropertyValue("--group-colour"),
        ),
        "var(--color-ink-400)",
    );
    assert(await mounted.evaluate((el) => el.isConnected));
    assert.equal(
        await leader
            .getByRole("tab", { name: "Notes", exact: true })
            .getAttribute("aria-selected"),
        "true",
    );
    await page.reload();
    await page
        .getByRole("button", { name: "Edit group Forward team", exact: true })
        .click();
    assert.equal(
        await editor
            .getByRole("button", { name: "No colour", exact: true })
            .getAttribute("aria-pressed"),
        "true",
    );
    await editor
        .getByLabel("Group name", { exact: true })
        .fill("Cancelled name");
    await editor.getByRole("button", { name: "Cancel", exact: true }).click();
    await page
        .getByRole("button", { name: "Edit group Forward team", exact: true })
        .click();
    await editor
        .getByRole("link", { name: "Card Manager", exact: true })
        .click();
    await manager.waitFor();
    await header("test-group")
        .getByRole("button", {
            name: "Group colour for Forward team",
            exact: true,
        })
        .click();
    assert.equal(
        await manager
            .getByRole("button", { name: "No colour", exact: true })
            .getAttribute("aria-pressed"),
        "true",
    );
    await manager
        .getByRole("button", { name: "Violet group colour", exact: true })
        .click();
    await save();
    await boxes("test-group").locator(".gang-group-box-fill").waitFor();
    await page
        .getByRole("button", { name: "Edit group Forward team", exact: true })
        .click();
    await editor.getByLabel("Group name", { exact: true }).fill("Night crew");
    await editor
        .getByRole("button", { name: "No colour", exact: true })
        .click();
    await editor.screenshot({ path: "qa/group-editor-desktop.png" });
    await editor
        .getByRole("link", { name: "Save and open Card Manager", exact: true })
        .click();
    await manager.waitFor();
    assert(
        await header("test-group")
            .getByRole("button", {
                name: "Rename group Night crew",
                exact: true,
            })
            .isVisible(),
    );
    await manager.getByRole("button", { name: "Cancel", exact: true }).click();
    await page.setViewportSize({ width: 320, height: 1050 });
    await page
        .getByRole("button", { name: "Edit group Night crew", exact: true })
        .click();
    await editor
        .getByLabel("Group name", { exact: true })
        .fill("Night crew — Forward team");
    assert.equal(
        await editor.evaluate((el) => el.scrollWidth > el.clientWidth),
        false,
    );
    await editor.screenshot({ path: "qa/group-editor-mobile.png" });
    await page.keyboard.press("Escape");
    await editor.waitFor({ state: "hidden" });
    await page.setViewportSize({ width: 1440, height: 1050 });
    // The shared palette also applies No colour to a multi-group selection.
    await seed(shown);
    await open();
    await header("special").getByRole("checkbox").check();
    await header("fallen").getByRole("checkbox").check();
    await manager
        .getByRole("button", { name: "Group colour", exact: true })
        .click();
    await manager
        .getByRole("button", { name: "No colour", exact: true })
        .click();
    await save();
    assert.equal(await page.locator(".gang-group-box-fill").count(), 0);
    await page.reload();
    await boxes("special").first().waitFor();
    assert.equal(await page.locator(".gang-group-box-fill").count(), 0);
    await seed([
        group(["nyx", "ash", "sera"], { id: "front", name: "Forward" }),
        group(["jade", "rook"], { id: "rear", name: "Reserve" }),
    ]);
    await boxes("rear").waitFor();
    const precedingBox = await boxes("front").boundingBox();
    const nextLabel = await boxes("rear")
        .locator(".gang-group-box-label")
        .boundingBox();
    assert(
        nextLabel.y >= precedingBox.y + precedingBox.height + 1,
        "Tighter rows retain clearance between a centred label and the preceding box.",
    );
    await page.screenshot({
        path: "qa/group-box-row-clearance.png",
        fullPage: true,
        animations: "disabled",
    });
    assert.deepEqual(errors, []);
    console.log(
        "Group boxes passed: bulk actions and persistence, dotted open wraps, continuous joins, outlined labels, 5% fill and no-colour mode, group editor and Card Manager link, tighter row clearance, responsive controls, pets and mounted card state.",
    );
} finally {
    await browser.close();
}
