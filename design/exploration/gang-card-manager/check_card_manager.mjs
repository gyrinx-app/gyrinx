const baseURL = process.env.BASE_URL || "http://127.0.0.1:8776";
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import assert from "node:assert/strict";
import * as M from "./src/card-manager-model.js";

const initial = M.defaults();
assert.deepEqual(
    M.move(initial, ["vesper", "nyx"], 1)
        .slice(1, 4)
        .map((n) => n.id),
    ["ash", "vesper", "nyx"],
);
assert.deepEqual(M.move(initial, ["echo"], 1), initial);
assert.deepEqual(
    M.relocate(initial, ["vesper"], "stash", "merge"),
    initial,
    "Explicit pins constrain root cards.",
);
const withinGroup = M.setPin(initial, ["stash"], "top");
assert.deepEqual(
    M.find(withinGroup, "special").children.map((c) => c.id),
    ["stash", "campaign", "actions"],
);
assert.equal(
    withinGroup.some((n) => n.id === "stash"),
    false,
);
assert.deepEqual(
    M.move(withinGroup, ["stash"], 1),
    withinGroup,
    "Internal pins constrain arrow movement.",
);
const bottomInGroup = M.setPin(withinGroup, ["campaign"], "bottom");
assert.deepEqual(
    M.find(bottomInGroup, "special").children.map((c) => c.id),
    ["stash", "actions", "campaign"],
);
assert.equal(
    M.find(M.setPin(bottomInGroup, ["stash"], null), "stash").pin,
    null,
);
assert.equal(
    M.find(M.sortCards(bottomInGroup, "default"), "special").children.at(-1).id,
    "campaign",
);
const extracted = M.relocate(initial, ["violet"], "nyx", "after");
assert.equal(
    extracted.findIndex((n) => n.id === "violet"),
    extracted.findIndex((n) => n.id === "nyx") + 1,
);
assert.equal(
    M.find(extracted, "violet").pin,
    null,
    "A card taken out of a pinned group becomes unpinned.",
);
assert.equal(M.find(extracted, "fallen").pin, "bottom");
const grouped = M.groupSelection(initial, ["nyx", "ash"]),
    group = grouped.find((n) => n.name === "Card group");
assert.deepEqual(
    group.children.map((n) => n.id),
    ["nyx", "ash"],
);
assert.deepEqual(
    M.find(M.sortCards(grouped, "name-asc"), group.id).children.map(
        (n) => n.id,
    ),
    ["ash", "nyx"],
);
const typed = M.groupByType(
    grouped,
    grouped.map((n) => n.id),
);
assert.equal(typed[0].name, "Gang panels");
assert.equal(typed[0].pin, "top");
assert.equal(typed.at(-1).name, "Dead / destroyed");
assert.equal(typed.at(-1).pin, "bottom");
assert.deepEqual(
    typed.find((n) => n.name === "Champion").children.map((n) => n.id),
    ["nyx", "ash"],
);
assert.ok(!typed.some((n) => n.id === group.id));
assert.ok(M.models.vesper.subtypes.includes("Leader"));
assert.ok(M.models.crawler.subtypes.includes("Vehicle"));
assert.notEqual(M.models.crawler.type, "Vehicle");
const partialType = M.groupByType(initial, ["campaign"]);
assert.equal(
    M.find(partialType, "actions").pin,
    "top",
    "Untouched cards retain inherited pins when their group dissolves.",
);
assert.equal(M.find(partialType, "stash").pin, "top");
for (const layout of [initial, grouped, M.setPin(grouped, [group.id], "top")]) {
    const everyId = layout.flatMap((n) => [
        n.id,
        ...(n.children || []).map((c) => c.id),
    ]);
    for (const source of everyId)
        for (const target of everyId)
            for (const mode of ["before", "after", "merge"]) {
                const result = M.relocate(layout, [source], target, mode);
                assert.deepEqual(
                    M.flatten(result)
                        .map((n) => n.id)
                        .sort(),
                    M.flatten(layout)
                        .map((n) => n.id)
                        .sort(),
                    `${source} ${mode} ${target} preserves every card exactly once.`,
                );
                assert.ok(
                    result.every(
                        (n) =>
                            !n.children || n.children.every((c) => !c.children),
                    ),
                );
            }
}
// Storage values must not crash the manager or overwrite unreadable drafts.
const colours = ["ink", "violet"];
assert.equal(M.validLayout(initial, colours), true);
assert.equal(M.validLayout([], colours), true);
for (const value of [
    null,
    {},
    [null],
    [initial[1], initial[1]],
    [{ ...initial[0], children: [] }],
    [{ ...initial[0], colour: "unknown" }],
    [{ ...initial[0], children: [initial[0]] }],
    [{ id: "__proto__", pin: null }],
    [{ ...initial[0], id: "vesper" }],
    [{ ...initial[0], pin: "sideways" }],
])
    assert.equal(M.validLayout(value, colours), false);
const unreadable = M.loadLayout(
    () => ({ getItem: () => "{bad json" }),
    colours,
);
assert.equal(unreadable.writable, false);
let writes = 0;
const store = () => ({
    setItem: () => {
        writes++;
    },
});
assert.equal(M.storeLayout(store, initial, false), false);
assert.equal(writes, 0);
assert.equal(M.storeLayout(store, initial, true), true);
assert.equal(writes, 1);
assert.equal(
    M.storeLayout(
        () => {
            throw new Error("Storage disabled");
        },
        initial,
        true,
    ),
    false,
);
assert.equal(
    M.loadLayout(() => {
        throw new Error("Storage disabled");
    }, colours).writable,
    false,
);
const mixed = [
    {
        id: "mixed",
        name: "Mixed",
        colour: "ink",
        pin: null,
        children: [
            { id: "nyx", pin: null },
            { id: "stash", pin: null },
            { id: "ash", pin: null },
        ],
    },
];
for (const mode of [
    "name-asc",
    "name-desc",
    "rating-asc",
    "rating-desc",
    "profile",
    "default",
])
    assert.deepEqual(
        M.sortCards(M.sortCards(mixed, mode), mode),
        M.sortCards(mixed, mode),
    );
assert.deepEqual(
    M.sortCards(mixed, "name-asc")[0].children.map((n) => n.id),
    ["stash", "ash", "nyx"],
);
const originalStatus = M.models.ash.status;
M.models.ash.status = "In recovery";
assert.equal(M.profileCategory("ash"), "Champion");
if (originalStatus === undefined) delete M.models.ash.status;
else M.models.ash.status = originalStatus;
mkdirSync("qa", { recursive: true });
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } }),
    errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const manager = page.getByRole("dialog", { name: "Card Manager", exact: true });
const open = () =>
    page.getByRole("button", { name: "Card Manager", exact: true }).click();
const select = (name) =>
    manager.getByRole("checkbox", { name: `Select ${name}`, exact: true });
const row = (id) => manager.locator(`[data-card-id="${id}"]`);
const names = () => manager.locator(".cm-name-text").allTextContents();
const more = () =>
    manager.getByRole("button", { name: "More options", exact: true }).click();
const action = async (name) => {
    await more();
    await manager
        .locator(".cm-actions")
        .getByRole("button", { name, exact: true })
        .click();
};
const confirm = async (title, button) =>
    page
        .getByRole("dialog", { name: title, exact: true })
        .getByRole("button", { name: button, exact: true })
        .click();
const reset = async () => {
    if (
        await manager
            .getByRole("button", { name: "None", exact: true })
            .isEnabled()
    )
        await manager
            .getByRole("button", { name: "None", exact: true })
            .click();
    await action("Reset order");
    await confirm("Reset card order?", "Reset order");
};
const drag = async (from, to, { hold = 0, position = 0.8 } = {}) => {
    await page.waitForTimeout(240);
    const a = await manager
        .getByRole("button", { name: `Drag ${from}`, exact: true })
        .boundingBox();
    const b = await row(to).locator(".cm-row").boundingBox();
    await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
    await page.mouse.down();
    await page.mouse.move(b.x + b.width / 2, b.y + b.height * position, {
        steps: 10,
    });
    if (hold) await page.waitForTimeout(hold);
    await page.mouse.up();
    await page.waitForTimeout(240);
};
try {
    await page.goto(`${baseURL}/gang/?names=short`);
    await page.evaluate(() => document.fonts.ready);
    assert.equal(await page.locator(".gang-material").count(), 0);
    assert.equal(await page.locator(".gang-standard").count(), 13);
    assert.equal(await page.locator(".gang-special").count(), 3);
    await page.screenshot({
        path: "qa/card-manager-standard-cards.png",
        fullPage: true,
    });
    await open();
    await manager.waitFor();
    const dragStart = await manager
        .getByRole("button", { name: "Drag Nyx", exact: true })
        .boundingBox();
    const dragEnd = await row("ash").boundingBox();
    await page.mouse.move(
        dragStart.x + dragStart.width / 2,
        dragStart.y + dragStart.height / 2,
    );
    await page.mouse.down();
    await page.mouse.move(
        dragEnd.x + dragEnd.width / 2,
        dragEnd.y + dragEnd.height / 2,
        { steps: 5 },
    );
    await page.keyboard.press("Escape");
    await page.mouse.up();
    assert.equal(
        await manager.isVisible(),
        true,
        "Escape cancels a drag without closing the manager.",
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "Save", exact: true })
            .isDisabled(),
        true,
    );

    assert.equal(
        await manager
            .getByRole("button", { name: "Save", exact: true })
            .isDisabled(),
        true,
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "None", exact: true })
            .isDisabled(),
        true,
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "All", exact: true })
            .isVisible(),
        true,
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "Group by type", exact: true })
            .isVisible(),
        true,
        "Group controls are on the desktop strip.",
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "Move selected down" })
            .evaluate((el) => getComputedStyle(el).borderTopWidth),
        "0px",
    );
    assert.equal(
        await row("vesper")
            .getByRole("img", { name: "Leader", exact: true })
            .count(),
        1,
    );
    assert.equal(
        await row("crawler")
            .getByRole("img", { name: "Vehicle", exact: true })
            .count(),
        1,
    );
    assert.equal(
        await row("crawler").locator(".cm-type").innerText(),
        "Cargo-8 Ridgehauler",
    );
    assert.equal(
        await row("violet").locator(".cm-name-line .cm-status").innerText(),
        "Dead",
    );
    assert.ok(
        !(await row("violet")
            .locator(".cm-type")
            .innerText()
            .then((t) => t.includes("Dead"))),
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "All", exact: true })
            .locator("svg")
            .count(),
        0,
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "None", exact: true })
            .locator("svg")
            .count(),
        0,
    );
    await manager
        .getByRole("button", {
            name: "Group colour for Gang panels",
            exact: true,
        })
        .click();
    await manager
        .getByRole("button", { name: "Violet group colour", exact: true })
        .click();
    await page.keyboard.press("Escape");
    await select("Gang stash").check();
    await manager
        .getByRole("button", { name: "Pin to top", exact: true })
        .click();
    assert.equal(
        await manager
            .locator('[data-group-id="special"] + [data-card-id]')
            .getAttribute("data-card-id"),
        "stash",
    );
    await manager
        .getByRole("button", { name: "Pin to bottom", exact: true })
        .click();
    assert.equal(await row("stash").getAttribute("data-group-id"), null);
    assert.equal(
        await row("stash").evaluate((el) =>
            el.classList.contains("cm-group-child"),
        ),
        true,
    );
    await manager.getByRole("button", { name: "Unpin", exact: true }).click();
    await manager.getByRole("button", { name: "None", exact: true }).click();
    await manager
        .getByRole("button", { name: "Ungroup Gang panels", exact: true })
        .click();
    assert.equal(await manager.locator('[data-group-id="special"]').count(), 0);
    await reset();
    await manager.evaluate((el) => {
        window.cmRows = new Map(
            [...el.querySelectorAll("[data-card-id]")].map((n) => [
                n.dataset.cardId,
                n,
            ]),
        );
    });
    await select("Nyx").check();
    assert.equal(
        await manager
            .getByRole("button", { name: "None", exact: true })
            .isEnabled(),
        true,
    );
    await manager
        .getByRole("button", { name: "Move selected down", exact: true })
        .click();
    const animated = await manager.locator("[data-flip]").evaluateAll((els) =>
        els
            .filter((el) =>
                el
                    .getAnimations()
                    .some((a) =>
                        a.effect
                            .getKeyframes()
                            .some((frame) => frame.transform),
                    ),
            )
            .map((el) => el.dataset.flip)
            .sort(),
    );
    assert.deepEqual(
        animated,
        ["ash", "nyx"],
        "Only rows whose positions changed animate.",
    );
    for (let i = 0; i < 4; i++) {
        await manager
            .getByRole("button", { name: "Move selected up", exact: true })
            .click();
        await manager
            .getByRole("button", { name: "Move selected down", exact: true })
            .click();
    }
    assert.equal(
        await manager.evaluate((el) =>
            [...el.querySelectorAll("[data-card-id]")].every(
                (n) => window.cmRows.get(n.dataset.cardId) === n,
            ),
        ),
        true,
        "Rapid movement preserves every row node.",
    );
    await select("Ash").check();
    await manager.getByRole("button", { name: "Group", exact: true }).click();
    assert.equal(
        await manager.evaluate((el) =>
            [...el.querySelectorAll("[data-card-id]")].every(
                (n) => window.cmRows.get(n.dataset.cardId) === n,
            ),
        ),
        true,
        "Grouping also preserves every row node.",
    );
    await manager
        .getByRole("button", { name: "Rename group Card group", exact: true })
        .click();
    await page
        .getByRole("textbox", { name: "Group name", exact: true })
        .fill("Champions");
    await confirm("Group name", "Set name");
    await select("group Champions").check();
    await action("Group name");
    await page
        .getByRole("textbox", { name: "Group name", exact: true })
        .fill("Strike team");
    await confirm("Group name", "Set name");
    await manager
        .getByRole("button", { name: "Group colour", exact: true })
        .click();
    assert.equal(
        await manager
            .getByRole("group", { name: "Group colour", exact: true })
            .getByRole("button")
            .count(),
        19,
    );
    await manager
        .getByRole("button", { name: "Violet group colour", exact: true })
        .click();
    assert.equal(
        await manager
            .getByRole("button", { name: "Violet group colour", exact: true })
            .getAttribute("aria-pressed"),
        "true",
    );
    await page.screenshot({ path: "qa/card-manager-colour-panel.png" });
    await page.keyboard.press("Escape");
    await manager
        .getByRole("button", { name: "Group by type", exact: true })
        .click();
    const replace = page.getByRole("dialog", {
        name: "Replace existing groups?",
        exact: true,
    });
    assert.ok((await replace.innerText()).includes("Strike team"));
    await replace.getByRole("button", { name: "Cancel", exact: true }).click();
    assert.equal(
        await manager
            .getByRole("button", {
                name: "Rename group Strike team",
                exact: true,
            })
            .count(),
        1,
    );
    await manager
        .getByRole("button", { name: "Group by type", exact: true })
        .click();
    await confirm("Replace existing groups?", "Ungroup and group by type");
    assert.equal(
        await manager
            .getByRole("button", { name: "Rename group Champion", exact: true })
            .count(),
        1,
    );
    assert.equal(
        await manager
            .getByRole("button", { name: "None", exact: true })
            .isDisabled(),
        true,
    );
    await manager
        .getByRole("button", { name: "Group by type", exact: true })
        .click();
    await confirm("Replace existing groups?", "Ungroup and group by type");
    const headers = await manager.locator("[data-group-id]").allTextContents();
    assert.ok(headers[0].includes("Gang panels"));
    assert.ok(headers.at(-1).includes("Dead / destroyed"));
    await reset();
    await drag("Violet", "nyx");
    assert.equal(
        await row("violet").evaluate((el) =>
            el.classList.contains("cm-group-child"),
        ),
        false,
    );
    assert.equal(
        await manager.evaluate((el) =>
            [...el.querySelectorAll("[data-card-id]")].every(
                (n) => window.cmRows.get(n.dataset.cardId) === n,
            ),
        ),
        true,
        "Extracting from a pinned group preserves row nodes.",
    );
    await manager.getByRole("button", { name: "Save", exact: true }).click();
    await page.reload();
    await open();
    assert.equal(
        await row("violet").evaluate((el) =>
            el.classList.contains("cm-group-child"),
        ),
        false,
    );
    await reset();
    await drag("Nyx", "ash", { hold: 800, position: 0.5 });
    assert.equal(
        await manager
            .getByRole("button", {
                name: "Rename group Card group",
                exact: true,
            })
            .count(),
        1,
    );
    await select("Sera Vex").check();
    await select("Jade").check();
    await drag("Sera Vex", "echo");
    assert.deepEqual((await names()).slice(-4, -2), ["Sera Vex", "Jade"]);
    await manager.getByRole("button", { name: "None", exact: true }).click();
    await select("Sera Vex").check();
    await action("Archive models");
    assert.ok(
        (
            await page
                .getByRole("dialog", { name: "Archive 1 model?", exact: true })
                .innerText()
        ).includes("only take effect when you save"),
    );
    await confirm("Archive 1 model?", "Confirm archive");
    assert.equal(
        await row("sera").getByText("To be archived", { exact: true }).count(),
        1,
    );
    assert.equal(
        await row("sera")
            .locator(".cm-name-text")
            .evaluate((el) => getComputedStyle(el).textDecorationLine),
        "line-through",
    );
    await select("Jade").check();
    await action("Delete models");
    await confirm("Delete 1 model?", "Confirm delete");
    await select("Vesper Krail").check();
    await action("Refund models");
    await confirm("Refund 1 model?", "Confirm refund");
    assert.equal(
        await row("vesper")
            .getByText("To be refunded", { exact: true })
            .count(),
        1,
    );
    await manager.getByRole("button", { name: "Save", exact: true }).click();
    const final = page.getByRole("dialog", {
        name: "Save and apply model actions?",
        exact: true,
    });
    const summary = await final.innerText();
    for (const text of [
        "Archive 1 model",
        "Sera Vex",
        "Delete 1 model",
        "Jade",
        "Refund 1 model",
        "Vesper Krail",
        "2 attached pets",
    ])
        assert.ok(summary.includes(text), text);
    await page.screenshot({ path: "qa/card-manager-save-confirmation.png" });
    await final.getByRole("button", { name: "Cancel", exact: true }).click();
    assert.equal(await row("sera").count(), 1);
    await row("jade")
        .getByRole("button", {
            name: "Undo pending delete for Jade",
            exact: true,
        })
        .click();
    assert.equal(
        await row("jade").getByText("To be deleted", { exact: true }).count(),
        0,
    );
    await page.screenshot({ path: "qa/card-manager-pending-actions.png" });
    await manager.getByRole("button", { name: "Save", exact: true }).click();
    await confirm("Save and apply model actions?", "Save and apply");
    await open();
    assert.equal(await row("sera").count(), 0);
    assert.equal(await row("vesper").count(), 0);
    assert.equal(await row("jade").count(), 1);
    await manager.getByRole("button", { name: "Cancel", exact: true }).click();
    // A separate context keeps the long-name fixtures and screenshots independent of saved actions.
    const long = await browser.newPage({
        viewport: { width: 1440, height: 1050 },
    });
    long.on("pageerror", (e) => errors.push(e.message));
    await long.goto(`${baseURL}/gang/`);
    await long.evaluate(() => document.fonts.ready);
    await long
        .getByRole("button", { name: "Card Manager", exact: true })
        .click();
    const lm = long.getByRole("dialog", { name: "Card Manager", exact: true });
    assert.ok(
        (await lm.locator('[data-card-id="vesper"] .cm-name-text').innerText())
            .length > 90,
    );
    assert.equal(
        await lm
            .locator('[data-card-id="vesper"] .cm-name-text')
            .evaluate((el) => el.scrollWidth > el.clientWidth),
        true,
    );
    assert.equal(
        await lm
            .locator(".cm-list")
            .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
        true,
    );
    const headerOrder = await lm
        .locator('[data-group-id="special"]')
        .evaluate((el) => {
            const controls = [...el.children];
            return [
                ".cm-group-name",
                ".cm-count",
                ".cm-colour-dot",
                ".cm-header-box",
                ".cm-header-ungroup",
                ".cm-pin-label",
                ".cm-grip",
            ].map((selector) => controls.indexOf(el.querySelector(selector)));
        });
    assert.deepEqual(
        [...headerOrder].sort((a, b) => a - b),
        headerOrder,
    );
    assert.equal(
        (await lm.locator(".cm-header-ungroup svg.lucide-unlink").count()) > 0,
        true,
    );
    for (const width of [
        320, 360, 390, 440, 499, 520, 540, 580, 600, 620, 660, 680, 700, 720,
        744, 800, 1000,
    ]) {
        await long.setViewportSize({ width, height: 1000 });
        await lm
            .getByRole("button", { name: "More options", exact: true })
            .click();
        const bounds = await lm.evaluate((el) => {
            const dialog = el.getBoundingClientRect();
            const elements = [
                ...el.querySelectorAll(
                    ".cm-toolbar button, .cm-actions, .cm-sortbar select",
                ),
            ]
                .filter((n) => n.getClientRects().length)
                .map((n) => n.getBoundingClientRect());
            return elements.every(
                (r) => r.left >= dialog.left && r.right <= dialog.right,
            );
        });
        assert.equal(
            bounds,
            true,
            `Toolbar, dropdown and sort selector stay inside the dialog at ${width}px.`,
        );
        if ([520, 620, 720].includes(width))
            await lm.screenshot({
                path: `qa/card-manager-toolbar-${width}.png`,
            });
        await lm
            .getByRole("button", { name: "More options", exact: true })
            .click();
    }
    await long.setViewportSize({ width: 1440, height: 1050 });
    await lm.screenshot({ path: "qa/card-manager-long-names-desktop.png" });
    await long.getByRole("button", { name: "Cancel", exact: true }).click();
    await long
        .getByRole("button", { name: "Toggle dark mode", exact: true })
        .click();
    await long
        .getByRole("button", { name: "Card Manager", exact: true })
        .click();
    await lm.screenshot({ path: "qa/card-manager-long-names-dark.png" });
    await lm.getByRole("button", { name: "Cancel", exact: true }).click();
    await long.setViewportSize({ width: 390, height: 844 });
    await long
        .getByRole("button", { name: "Card Manager", exact: true })
        .click();
    assert.equal(
        await lm.getByRole("button", { name: "All", exact: true }).isVisible(),
        true,
    );
    assert.equal(
        await lm.getByRole("button", { name: "None", exact: true }).isVisible(),
        true,
    );
    assert.equal(
        await lm
            .getByRole("button", { name: "Group by type", exact: true })
            .count(),
        0,
    );
    await lm.getByRole("button", { name: "More options", exact: true }).click();
    assert.equal(
        await lm
            .getByRole("button", { name: "Group by type", exact: true })
            .isVisible(),
        true,
    );
    await lm.getByRole("button", { name: "More options", exact: true }).click();
    assert.equal(
        await lm
            .locator(".cm-list")
            .evaluate((el) => el.scrollWidth <= el.clientWidth + 1),
        true,
    );
    await lm.screenshot({ path: "qa/card-manager-long-names-mobile.png" });
    await long.emulateMedia({ reducedMotion: "reduce" });
    await lm.getByRole("checkbox", { name: /Select Nyx the Unbroken/ }).check();
    await lm
        .getByRole("button", { name: "Move selected down", exact: true })
        .click();
    assert.equal(
        await lm
            .locator("[data-flip]")
            .evaluateAll(
                (els) =>
                    els
                        .flatMap((el) => el.getAnimations())
                        .filter((a) =>
                            a.effect.getKeyframes().some((f) => f.transform),
                        ).length,
            ),
        0,
    );
    await lm
        .getByRole("button", { name: "Exit Card Manager", exact: true })
        .click();
    await long
        .getByRole("dialog", { name: "Discard changes?", exact: true })
        .getByRole("button", { name: "Discard changes", exact: true })
        .click();
    await long.close();
    for (const blocked of [false, true]) {
        const context = await browser.newContext();
        await context.addInitScript((blocked) => {
            if (blocked)
                Object.defineProperty(window, "localStorage", {
                    get() {
                        throw new Error("Storage blocked");
                    },
                });
            else localStorage.setItem("gyrinx-card-manager-v1", "{bad json");
        }, blocked);
        const broken = await context.newPage();
        await broken.goto(`${baseURL}/gang/?names=short`);
        await broken
            .getByRole("status")
            .getByText(/saved layout could not be read/)
            .waitFor();
        await broken
            .getByRole("button", { name: "Card Manager", exact: true })
            .click();
        const modal = broken.getByRole("dialog", {
            name: "Card Manager",
            exact: true,
        });
        await modal
            .getByRole("checkbox", { name: "Select Nyx", exact: true })
            .check();
        await modal
            .getByRole("button", { name: "Move selected down", exact: true })
            .click();
        await modal.getByRole("button", { name: "Save", exact: true }).click();
        await broken
            .getByRole("status")
            .getByText(/could not be saved/)
            .waitFor();
        if (!blocked)
            assert.equal(
                await broken.evaluate(() =>
                    localStorage.getItem("gyrinx-card-manager-v1"),
                ),
                "{bad json",
            );
        await context.close();
    }
    assert.deepEqual(errors, []);
    console.log(
        "Card Manager passed: stable row identity and targeted animation, All/None, regroup warnings and type pins, extraction from pinned groups, rename, palette, responsive controls, subtype icons, long names, staged actions and final save summary, keyboard and reduced motion.",
    );
} finally {
    await browser.close();
}
