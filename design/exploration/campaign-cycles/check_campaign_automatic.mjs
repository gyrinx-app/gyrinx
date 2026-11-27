import assert from "node:assert/strict";
import { chromium } from "playwright";
import * as M from "./src/campaign-model.js";
const origin = process.env.CAMPAIGN_ORIGIN || "http://127.0.0.1:8768";
const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    headless: true,
});
const context = await browser.newContext();
const page = await context.newPage(),
    other = await context.newPage();
const errors = [];
for (const tab of [page, other])
    tab.on("pageerror", (error) => errors.push(error.message));
const ui = (tab) => tab.locator("#campaign-root");
const state = () =>
    page.evaluate((key) => JSON.parse(localStorage.getItem(key)), M.storageKey);
async function until(test) {
    const deadline = Date.now() + 10000;
    while (!(await test())) {
        if (Date.now() > deadline)
            throw new Error("Campaign state did not settle.");
        await new Promise((resolve) => setTimeout(resolve, 30));
    }
}
try {
    await page.goto(`${origin}/campaign/`);
    await ui(page)
        .getByRole("heading", { name: "The Ash Road", exact: true })
        .waitFor();
    const seed = M.defaults();
    M.saveSettings(seed, {
        limit: null,
        repeat: true,
        steps: [
            { phase: "downtime", cycles: 1 },
            { phase: "occupation", cycles: 1 },
        ],
        days: 7,
        start: "",
        autoChange: true,
        autoCycles: M.defaultAutoCycles(),
    });
    seed.autoCycles.nextAt = new Date(Date.now() + 4500).toISOString();
    await page.evaluate(
        ({ key, seed }) => localStorage.setItem(key, JSON.stringify(seed)),
        { key: M.storageKey, seed },
    );
    await page.reload();
    await other.goto(`${origin}/campaign/`);
    // Leave a destructive form open while another tab and the timer change state.
    await ui(page)
        .getByRole("button", { name: "End cycle", exact: true })
        .click();
    await until(async () => (await state()).cycles.length === 4);
    const after = await state();
    assert.equal(after.currentPhase, "downtime");
    assert.equal(after.grants.length, 3, "Two tabs apply a boundary once.");
    assert.equal(M.currentCycle(after).startedAt, seed.autoCycles.nextAt);
    await until(async () =>
        (await ui(other).locator(".cp-period-facts").textContent()).includes(
            "Cycle 4",
        ),
    );
    const dialog = ui(page).getByRole("dialog");
    await dialog
        .getByRole("button", { name: "Confirm and end cycle", exact: true })
        .click();
    await dialog
        .getByRole("alert")
        .filter({ hasText: "current cycle changed" })
        .waitFor();
    assert.equal(
        (await state()).cycles.length,
        4,
        "A stale form cannot end the new cycle.",
    );
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    // An unrelated edit in another tab must survive the next manual transaction.
    await ui(other).getByRole("link", { name: "Cycle 4", exact: true }).click();
    await ui(other)
        .getByRole("button", { name: "Edit Downtime", exact: true })
        .click();
    const edit = ui(other).getByRole("dialog");
    await edit
        .getByLabel("Description", { exact: true })
        .fill("Edited in another tab.");
    await edit.getByRole("button", { name: "Save", exact: true }).click();
    await edit.waitFor({ state: "hidden" });
    await ui(page)
        .getByRole("button", { name: "End cycle", exact: true })
        .click();
    await dialog
        .getByLabel("Skip next automatic change", { exact: false })
        .check();
    await dialog
        .getByRole("button", { name: "Confirm and end cycle", exact: true })
        .click();
    await dialog.waitFor({ state: "hidden" });
    const final = await state();
    assert.equal(final.cycles.length, 5);
    assert.equal(final.grants.length, 3);
    assert.equal(
        final.phases.find((phase) => phase.id === "downtime").description,
        "Edited in another tab.",
    );
    assert.ok(
        Date.parse(final.autoCycles.nextAt) >
            Date.parse(after.autoCycles.nextAt),
    );
    await page.evaluate(() => {
        Storage.prototype.setItem = () => {
            throw new DOMException("Storage is full", "QuotaExceededError");
        };
    });
    for (const number of [6, 7]) {
        await ui(page)
            .getByRole("button", { name: "End cycle", exact: true })
            .click();
        await dialog
            .getByRole("button", { name: "Confirm and end cycle", exact: true })
            .click();
        await dialog.waitFor({ state: "hidden" });
        await ui(page)
            .locator(".cp-period-facts")
            .getByRole("link", { name: `Cycle ${number}`, exact: true })
            .waitFor();
    }
    assert.equal(
        (await state()).cycles.length,
        5,
        "Quota errors preserve the stored copy and allow successive in-memory edits.",
    );
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log("Campaign automatic and cross-tab checks passed.");
} finally {
    await browser.close();
}
