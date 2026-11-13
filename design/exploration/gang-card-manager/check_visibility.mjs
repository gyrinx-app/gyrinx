import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import * as M from "./src/card-manager-model.js";

const initial = M.defaults();
assert(initial.every((node) => !M.isHidden(initial, node.id)));
const childHidden = M.setHidden(initial, "campaign", true);
const groupHidden = M.setHidden(childHidden, "special", true);
assert(M.isHidden(groupHidden, "actions"));
assert(!M.find(groupHidden, "actions").hidden);
assert(M.isHidden(M.setHidden(groupHidden, "special", false), "campaign"));
assert(!M.isHidden(M.setHidden(groupHidden, "special", false), "actions"));
assert(!M.find(initial, "campaign").hidden);
for (const hidden of [null, 1, "true", {}, []]) {
    assert(!M.validLayout([{ ...initial[0], hidden }], ["ink"]));
    assert(!M.validLayout([{ id: "nyx", pin: null, hidden }], ["ink"]));
    assert(
        !M.validLayout(
            [
                {
                    ...initial[0],
                    children: [{ id: "campaign", pin: null, hidden }],
                },
            ],
            ["ink"],
        ),
    );
}
assert(M.validLayout(groupHidden, ["ink"]));
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_PATH ||
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: true,
});
try {
    const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
    });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const manager = page.getByRole("dialog", {
        name: "Card Manager",
        exact: true,
    });
    const open = () =>
        page.getByRole("button", { name: "Card Manager", exact: true }).click();
    const save = async () => {
        await manager
            .getByRole("button", { name: "Save", exact: true })
            .click();
        await manager.waitFor({ state: "hidden" });
    };
    const row = (id) => manager.locator(`[data-card-id="${id}"] .cm-row`);
    const header = (id) => manager.locator(`[data-group-id="${id}"]`);
    const card = (id) => page.locator(`[data-flip="card-${id}"]`);
    await page.goto(
        `${process.env.BASE_URL || "http://127.0.0.1:8776"}/gang/?names=short`,
    );
    await card("vesper")
        .getByRole("tab", { name: "Lore", exact: true })
        .click();
    await open();
    assert(
        await row("vesper").locator(".cm-visibility svg.lucide-eye").count(),
    );
    assert(
        await row("vesper").evaluate((el) =>
            el
                .querySelector(".cm-visibility")
                .nextElementSibling.matches(".cm-grip"),
        ),
    );
    assert(
        await header("special").evaluate((el) =>
            el
                .querySelector(".cm-visibility")
                .nextElementSibling.matches(".cm-grip"),
        ),
    );
    await row("vesper")
        .getByRole("button", { name: "Hide card Vesper Krail", exact: true })
        .click();
    assert(
        await row("vesper")
            .locator(".cm-visibility svg.lucide-eye-closed")
            .count(),
    );
    assert.equal(
        await row("vesper").locator(".cm-visibility-note").innerText(),
        "Hidden",
    );
    await save();
    for (const id of ["vesper", "vesper-pet-0", "vesper-pet-1"]) {
        assert.equal(await card(id).count(), 1, "Hidden cards stay mounted.");
        assert.equal(await card(id).isVisible(), false);
    }
    await open();
    await row("vesper")
        .getByRole("button", { name: "Show card Vesper Krail", exact: true })
        .click();
    await save();
    assert(await card("vesper").isVisible());
    assert.equal(
        await card("vesper")
            .getByRole("tab", { name: "Lore", exact: true })
            .getAttribute("aria-selected"),
        "true",
    );
    await open();
    await row("campaign")
        .getByRole("button", {
            name: "Hide card Campaign attributes",
            exact: true,
        })
        .click();
    await header("special")
        .getByRole("button", { name: "Hide group Gang panels", exact: true })
        .click();
    assert(
        await row("actions")
            .getByRole("button", {
                name: "Show card Available actions",
                exact: true,
            })
            .isDisabled(),
    );
    assert.equal(
        await row("actions").locator(".cm-visibility-note").innerText(),
        "Hidden with group",
    );
    await save();
    for (const id of ["campaign", "actions", "stash"])
        assert(!(await card(id).isVisible()));
    assert.equal(await page.locator(".gang-panel-stack:visible").count(), 0);
    await page.reload();
    await open();
    assert(
        await header("special")
            .locator(".cm-visibility svg.lucide-eye-closed")
            .count(),
    );
    await header("special")
        .getByRole("button", { name: "Show group Gang panels", exact: true })
        .click();
    await save();
    assert(!(await card("campaign").isVisible()));
    assert(await card("actions").isVisible());
    assert(await card("stash").isVisible());
    // Cancelling a visibility draft leaves the roster unchanged.
    await open();
    await row("nyx")
        .getByRole("button", { name: "Hide card Nyx", exact: true })
        .click();
    await manager.getByRole("button", { name: "Cancel", exact: true }).click();
    await page
        .getByRole("dialog", { name: "Discard changes?", exact: true })
        .getByRole("button", { name: "Discard changes", exact: true })
        .click();
    assert(await card("nyx").isVisible());
    // Hidden cards do not leave holes or contribute to group outlines.
    const group = {
        id: "forward",
        name: "Forward team",
        colour: "violet",
        pin: null,
        showBox: true,
        children: [
            { id: "nyx", pin: null },
            { id: "ash", pin: null, hidden: true },
        ],
    };
    await page.evaluate(
        ({ key, group }) => localStorage.setItem(key, JSON.stringify([group])),
        { key: M.STORAGE_KEY, group },
    );
    await page.reload();
    await page.locator('[data-roster-group="forward"]').waitFor();
    assert(!(await card("ash").isVisible()));
    const bounds = await page
        .locator('[data-roster-group="forward"]')
        .boundingBox();
    const nyx = await card("nyx").boundingBox();
    assert(bounds.width < nyx.width + 20);
    assert(bounds.x <= nyx.x && bounds.x > nyx.x - 10);
    await open();
    mkdirSync("qa", { recursive: true });
    for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        const sizes = await manager.evaluate((el) => {
            const group = el.querySelector(".cm-group-name"),
                model = el.querySelector(".cm-model-name");
            const controls = el.querySelector('[data-group-id="forward"]');
            const rect = controls.getBoundingClientRect();
            return {
                group: getComputedStyle(group).fontSize,
                model: getComputedStyle(model).fontSize,
                weight: getComputedStyle(group).fontWeight,
                modelWeight: getComputedStyle(model).fontWeight,
                fits: [...controls.children].every((n) => {
                    const r = n.getBoundingClientRect();
                    return r.left >= rect.left - 1 && r.right <= rect.right + 1;
                }),
                grip: controls
                    .querySelector(".cm-grip svg")
                    .getAttribute("width"),
                rowGrip: el
                    .querySelector(".cm-row .cm-grip svg")
                    .getAttribute("width"),
                eye: controls
                    .querySelector(".cm-visibility svg")
                    .getAttribute("width"),
            };
        });
        assert.equal(sizes.group, sizes.model);
        assert.equal(sizes.weight, sizes.modelWeight);
        assert.equal(sizes.grip, sizes.rowGrip);
        assert.equal(sizes.eye, "16");
        assert(sizes.fits, `Group controls fit at ${width}px.`);
        if (width !== 320)
            await manager.screenshot({
                path: `qa/card-visibility-${width}.png`,
            });
    }
    await header("forward")
        .getByRole("button", { name: "Hide group Forward team", exact: true })
        .click();
    assert(
        await row("nyx")
            .getByRole("button", { name: "Show card Nyx", exact: true })
            .isDisabled(),
    );
    assert(
        await header("forward").evaluate((el) => {
            const rect = el.getBoundingClientRect();
            return [...el.children].every((child) => {
                const box = child.getBoundingClientRect();
                return box.left >= rect.left - 1 && box.right <= rect.right + 1;
            });
        }),
        "Hidden group controls fit at 320px.",
    );
    await save();
    assert.equal(await page.locator(".gang-group-box").count(), 0);
    assert.equal(
        await page.locator(".gang-grid").evaluate((el) => el.offsetHeight),
        0,
    );
    await page.reload();
    assert(!(await card("nyx").isVisible()));
    await open();
    await header("forward")
        .getByRole("button", { name: "Show group Forward team", exact: true })
        .click();
    await save();
    assert(await card("nyx").isVisible());
    assert(!(await card("ash").isVisible()));
    assert.deepEqual(errors, []);
    console.log(
        "Visibility passed: card/group persistence, inherited state, pets, mounted tab state, cancellation, hidden-panel flow, outline bounds, matching row sizes and narrow layouts.",
    );
} finally {
    await browser.close();
}
