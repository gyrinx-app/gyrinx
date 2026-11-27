const origin = process.env.CAMPAIGN_ORIGIN || "http://127.0.0.1:8768";
import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { chromium } from "playwright";
import * as M from "./src/campaign-model.js";
const templateBase = JSON.parse(readFileSync("src/campaign-base.json", "utf8"));
assert.ok(
    Object.keys(templateBase.provenance).some((path) =>
        path.endsWith("/view/campaign_sheet.html"),
    ),
);
for (const [path, hash] of Object.entries(templateBase.provenance))
    assert.equal(
        createHash("sha256").update(readFileSync(path)).digest("hex"),
        hash,
        "Rebuild when an upstream campaign template changes.",
    );
await import("./check_campaign_model.mjs");
mkdirSync("qa", { recursive: true });
const browser = await chromium.launch({
    executablePath: process.env.CHROME_PATH || undefined,
    headless: true,
});
const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
});
const page = await context.newPage();
const errors = [];
let acceptConfirm = true;
const confirms = [];
page.on("dialog", async (d) => {
    confirms.push(d.message());
    if (acceptConfirm) await d.accept();
    else await d.dismiss();
});
page.on("pageerror", (e) => errors.push(e.message));
const ui = page.locator("#campaign-root");
const dialog = ui.getByRole("dialog");
const btn = (name, root = ui) =>
    root.getByRole("button", { name, exact: true });
async function campaignAction(name) {
    await ui.locator('summary[aria-label="More actions"]').click();
    await btn(name).click();
}
async function editCurrentCycle() {
    await campaignAction("Manage phases & cycles");
    const snapshot = await stored();
    await btn(
        `Edit ${snapshot.cycles.find((c) => c.id === snapshot.currentCycle).name}`,
    ).click();
}
const stored = () =>
    page.evaluate(async (k) => {
        const read = () => JSON.parse(localStorage.getItem(k));
        return navigator.locks ? navigator.locks.request(k, read) : read();
    }, M.storageKey);
async function screenshot(name) {
    await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
    await ui.locator(".cp-page").evaluate((el) =>
        Promise.allSettled(
            el
                .getAnimations({ subtree: true })
                .filter(
                    (animation) =>
                        animation.effect?.getTiming().iterations !== Infinity,
                )
                .map((animation) => animation.finished),
        ),
    );
    await page.screenshot({ path: `qa/campaign-${name}.png`, fullPage: true });
}
try {
    await page.goto(`${origin}/campaign/`);
    await ui
        .getByRole("heading", { name: "The Ash Road", exact: true })
        .waitFor();
    for (const name of ["Type", "Arbitrator", "Founding budget", "Settlement"])
        assert.ok(await ui.getByText(name, { exact: true }).count());
    for (const name of ["Wealth", "Reputation", "Income"])
        assert.ok(
            await ui.getByRole("columnheader", { name, exact: true }).count(),
        );
    assert.equal(await ui.locator("#campaign-overview").count(), 1);
    assert.equal(
        await ui.getByText("Campaign duration", { exact: true }).count(),
        1,
    );
    assert.equal(
        await ui
            .getByText("Fixed · 7 scheduled cycles", { exact: true })
            .count(),
        1,
    );
    assert.equal(await ui.getByText("Phase", { exact: true }).count(), 1);
    assert.equal(await ui.locator("#campaign-sections > #gangs").count(), 1);
    assert.equal(await ui.locator("#campaign-sections > #battles").count(), 1);
    assert.equal(
        await ui.locator("#campaign-sections > #n26-campaign-assets").count(),
        1,
    );
    assert.equal(await ui.locator("#campaign-sections > #log").count(), 1);
    assert.equal(await ui.locator("#campaign-sections > #players").count(), 1);
    assert.equal(
        await ui.locator(".cp-tabs,.cp-current,.cp-header-figures").count(),
        0,
    );
    assert.match(await ui.locator("#gangs h2").textContent(), /3 gangs/);
    assert.equal(
        await ui
            .getByRole("heading", { name: "Phase & cycle", exact: true })
            .count(),
        0,
    );
    assert.equal(
        await ui
            .getByText("Effects and battle rewards", { exact: true })
            .count(),
        1,
    );
    const periodBox = await ui
            .getByLabel("Current campaign period")
            .boundingBox(),
        actionsBox = await ui
            .getByLabel("Campaign actions", { exact: true })
            .boundingBox();
    assert.ok(
        Math.abs(periodBox.y - actionsBox.y) < 4,
        "Period information shares the action row.",
    );
    assert.ok(
        periodBox.width < 700,
        "The period information stays compact on desktop.",
    );

    await btn("Read full description").click();
    assert.equal(await btn("Hide description").isVisible(), true);
    await btn("Hide description").click();
    await ui
        .getByRole("link", { name: "The old pump station", exact: true })
        .click();
    await dialog
        .getByRole("heading", { name: "The old pump station", exact: true })
        .waitFor();
    await page.keyboard.press("Escape");
    await screenshot("dashboard-desktop");
    await btn("End cycle").click();
    await dialog
        .locator(".cp-transition")
        .getByText("Downtime", { exact: true })
        .waitFor();
    assert.equal(await dialog.locator(".cp-inline-note").count(), 0);
    await screenshot("advance-downtime");
    await btn("Confirm and end cycle", dialog).click();
    assert.equal((await stored()).currentPhase, "downtime");
    assert.equal((await stored()).grants.length, 3);
    await ui.getByText("Effects and battle rewards", { exact: true }).click();
    await ui
        .getByText("Each gang receives 250 credits when Downtime begins.", {
            exact: false,
        })
        .waitFor();
    assert.deepEqual(
        (await stored()).gangs.map((g) => g.credits),
        [435, 370, 490],
    );
    await screenshot("downtime");
    await page.reload();
    await ui.getByRole("heading", { name: "Downtime", exact: true }).waitFor();
    assert.equal((await stored()).grants.length, 3);
    await campaignAction("Manage phases & cycles");
    await screenshot("schedule-desktop");
    assert.equal(
        await ui
            .getByLabel("Occupation phase", { exact: true })
            .getByText("Completed", { exact: true })
            .count(),
        4,
    );
    assert.equal(await btn("Add cycle to Occupation").count(), 1);
    assert.equal(await btn("Add cycle to Occupation").isEnabled(), true);
    const endedOccupation = (await stored()).cycles.find(
        (c) => c.id === "c3",
    ).endedAt;
    assert.equal(
        await ui
            .getByLabel("Occupation phase", { exact: true })
            .getByText(M.endedDate(endedOccupation), { exact: true })
            .count(),
        2,
    );

    await btn("Schedule settings").click();
    assert.equal(
        await dialog.getByText("Real-world dates", { exact: true }).count(),
        1,
    );
    assert.equal(
        await dialog
            .getByLabel("Show rough dates for cycles", { exact: true })
            .isChecked(),
        false,
    );
    assert.equal(
        await dialog.getByLabel("Campaign start date", { exact: true }).count(),
        0,
    );
    await dialog
        .getByLabel("Show rough dates for cycles", { exact: true })
        .check();
    await dialog
        .getByLabel("Campaign start date", { exact: true })
        .fill("2026-10-05");
    await dialog.getByLabel("Days per cycle", { exact: true }).fill("7");
    assert.equal(await dialog.locator('option[value="lengths"]').count(), 0);
    assert.equal(await dialog.locator('option[value="manual"]').count(), 0);
    await dialog
        .getByLabel("Campaign length", { exact: true })
        .selectOption("unlimited");
    assert.equal(
        await dialog.getByText("Real-world dates", { exact: true }).count(),
        0,
    );
    assert.equal(
        await dialog.getByLabel("How phases change", { exact: true }).count(),
        0,
    );
    await btn("Save", dialog).click();
    assert.equal((await stored()).limit, null);
    assert.equal((await stored()).start, "2026-10-05");
    await btn("Back to campaign").click();
    assert.equal(
        await ui.getByText("26 Oct – 1 Nov", { exact: true }).count(),
        0,
    );
    await editCurrentCycle();
    await dialog.getByLabel("Phase", { exact: true }).selectOption("takeover");
    await btn("Save", dialog).click();
    await btn("Back to campaign").click();
    assert.equal((await stored()).currentCycle, "c4");
    assert.equal((await stored()).currentPhase, "takeover");
    await campaignAction("Manage phases & cycles");
    await btn("Edit Takeover").click();
    await dialog.screenshot({ path: "qa/campaign-edit-phase.png" });
    await dialog.getByLabel("Win credits", { exact: true }).fill("70");
    await dialog.getByLabel("Win reputation", { exact: true }).fill("4");
    await btn("Save", dialog).click();
    await dialog.waitFor({ state: "hidden" });
    await page.goto(`${origin}/campaign/?view=battles&viewer=arbitrator`);
    await btn("Record a battle").click();
    await dialog
        .getByLabel("Battle name", { exact: true })
        .fill("The disputed crossing");
    await dialog
        .getByLabel("Battle result", { exact: true })
        .selectOption("nightshade");
    await screenshot("record-battle");
    await btn("Record battle", dialog).click();
    const after = await stored();
    assert.equal(after.battles[0].phase, "takeover");
    assert.equal(after.battles[0].cycle, "c4");
    assert.equal(after.battles[0].payouts[0].credits, 70);
    await btn("Back to campaign").click();
    await editCurrentCycle();
    await dialog
        .getByLabel("Phase", { exact: true })
        .selectOption("occupation");
    await btn("Save", dialog).click();
    await btn("Back to campaign").click();
    assert.equal((await stored()).battles[0].phase, "takeover");
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot("dashboard-mobile");
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await btn("Toggle theme").click();
    await screenshot("dashboard-dark-mobile");
    await page.setViewportSize({ width: 1440, height: 1100 });
    await screenshot("dashboard-dark");
    await btn("Record a battle").click();
    await screenshot("dialog-dark");
    await page.keyboard.press("Escape");
    assert.equal(await dialog.count(), 0);
    // Fresh finite schedule: spacing, controls, deletion and active-cycle movement.
    const fixedFixture = M.defaults();
    fixedFixture.battles = fixedFixture.battles.filter((b) => b.cycle !== "c1");
    await page.evaluate(
        ({ key, state }) => localStorage.setItem(key, JSON.stringify(state)),
        { key: M.storageKey, state: fixedFixture },
    );
    await page.goto(`${origin}/campaign/?view=schedule`);
    await btn("Schedule settings").waitFor();
    assert.equal(await btn("Add phase").count(), 0);
    assert.equal(
        await ui
            .getByRole("heading", { name: "Phases & cycles", exact: true })
            .count(),
        1,
    );
    const row = await ui.locator('[data-cycle-id="c1"]').boundingBox();
    assert.ok(row.height >= 38 && row.height <= 46);
    assert.equal(
        await ui.locator('[data-cycle-id="c3"]').getAttribute("draggable"),
        "true",
    );
    await btn("Move Cycle 3 to next phase").click();
    assert.equal((await stored()).currentPhase, "downtime");
    await btn("Move Cycle 3 to previous phase").click();
    assert.equal((await stored()).currentPhase, "occupation");
    const dataTransfer = await page.evaluateHandle(() => new DataTransfer());
    await ui
        .locator('[data-cycle-id="c3"]')
        .dispatchEvent("dragstart", { dataTransfer });
    const target = ui.getByLabel("Takeover phase", { exact: true });
    await target
        .locator(".cp-phase-item")
        .dispatchEvent("dragover", { dataTransfer, clientY: 0 });
    assert.equal(await ui.locator(".cp-drop-available").count(), 3);
    await target.locator(".cp-drag-preview").waitFor({ state: "visible" });
    assert.equal(await target.locator(".cp-drag-preview").count(), 1);
    assert.equal(
        await target.locator(".cp-drag-preview").getAttribute("aria-label"),
        "Drop Cycle 3 in Takeover",
    );
    assert.equal(
        await target.evaluate((el) => el.classList.contains("cp-drop-active")),
        true,
    );
    await screenshot("drag-preview");
    await ui
        .locator('[data-cycle-id="c3"]')
        .dispatchEvent("dragend", { dataTransfer });
    assert.equal(await ui.locator(".cp-drag-preview").count(), 0);
    await ui
        .locator('[data-cycle-id="c3"]')
        .dragTo(
            ui
                .getByLabel("Takeover phase", { exact: true })
                .locator(".cp-phase-item"),
        );
    assert.equal((await stored()).currentPhase, "takeover");
    assert.equal((await stored()).battles[0].phase, "occupation");
    await btn("Delete Cycle 1").click();
    await btn("Delete cycle", dialog).click();
    assert.equal((await stored()).cycles.length, 6);
    await btn("Move Takeover earlier").click();
    assert.deepEqual(
        (await stored()).phases.map((p) => p.id),
        ["occupation", "takeover", "downtime"],
    );
    await btn("Move Takeover later").click();
    assert.equal(await btn("End cycle").count(), 1);
    await btn("Schedule settings").click();
    acceptConfirm = false;
    await dialog
        .getByLabel("Campaign length", { exact: true })
        .selectOption("unlimited")
        .catch(() => {});
    assert.equal(
        await dialog
            .getByLabel("Campaign length", { exact: true })
            .inputValue(),
        "fixed",
    );
    assert.match(confirms.at(-1), /clear .* scheduled cycles/);
    acceptConfirm = true;
    await btn("Cancel", dialog).click();
    await btn("Schedule settings").click();
    assert.equal(
        await dialog.getByLabel("How phases change", { exact: true }).count(),
        0,
    );
    await dialog
        .getByLabel("Campaign length", { exact: true })
        .selectOption("unlimited");
    assert.equal(
        await dialog.getByText("Real-world dates", { exact: true }).count(),
        0,
    );
    assert.equal(
        await dialog.getByLabel("How phases change", { exact: true }).count(),
        0,
    );
    await btn("Save", dialog).click();
    let live = await stored();
    assert.equal(
        live.cycles.length,
        2,
        "Unlimited campaigns keep past and active cycles only.",
    );
    assert.equal(live.cycles.at(-1).id, live.currentCycle);
    assert.equal(
        await ui
            .locator(".cp-phase-summary")
            .getByText("Completed", { exact: true })
            .count(),
        0,
    );
    for (const name of ["Occupation", "Downtime", "Takeover"])
        assert.equal(await btn(`Add cycle to ${name}`).count(), 0);
    assert.equal(await btn("Change phase").count(), 0);
    await btn("End cycle").click();
    await dialog
        .getByLabel("Phase for the new cycle", { exact: true })
        .selectOption("downtime");
    assert.equal(
        await dialog
            .getByLabel("Phase for the new cycle", { exact: true })
            .inputValue(),
        "downtime",
    );
    await dialog
        .getByLabel("Next cycle name", { exact: true })
        .fill("Respite on the road");
    await btn("End cycle", dialog).click();
    assert.equal((await stored()).cycles.at(-1).name, "Respite on the road");
    live = await stored();
    assert.equal(live.currentPhase, "downtime");
    assert.equal(live.cycles.length, 3);
    await btn("Schedule settings").click();
    await dialog.getByLabel("Use a repeating pattern", { exact: true }).check();
    await screenshot("pattern-settings");
    acceptConfirm = false;
    await btn("Cancel", dialog).click();
    assert.equal(await dialog.count(), 1);
    assert.match(confirms.at(-1), /unsaved pattern/);
    await page.keyboard.press("Escape");
    assert.equal(await dialog.count(), 1);
    await btn("Close", dialog).click();
    assert.equal(await dialog.count(), 1);
    await page.goBack({ waitUntil: "commit", timeout: 3000 }).catch(() => {});
    assert.equal(await dialog.count(), 1);
    assert.match(page.url(), /view=schedule/);
    acceptConfirm = true;

    assert.equal(
        await dialog
            .getByLabel("Phase in step 4", { exact: true })
            .inputValue(),
        "downtime",
    );
    await btn("Save", dialog).click();
    assert.equal(await btn("End cycle").count(), 1);
    assert.equal(await btn("New cycle").count(), 0);
    const grantsBeforePattern = (await stored()).grants.length;
    for (const expected of [
        "occupation",
        "occupation",
        "downtime",
        "takeover",
        "takeover",
        "downtime",
        "occupation",
    ]) {
        const before = await stored();
        await btn("End cycle").click();
        if (expected === "occupation" && before.pattern.cursor === 0)
            await dialog
                .getByLabel("Next cycle name", { exact: true })
                .fill("Opening round");
        await btn("Confirm and end cycle", dialog).click();
        const after = await stored();
        assert.equal(after.currentPhase, expected);
        assert.ok(
            after.cycles.find((c) => c.id === before.currentCycle).endedAt,
        );
        assert.equal(
            (await ui
                .getByText(
                    M.endedDate(
                        after.cycles.find((c) => c.id === before.currentCycle)
                            .endedAt,
                    ),
                    { exact: true },
                )
                .count()) > 0,
            true,
        );
        assert.equal(after.cycles.length, before.cycles.length + 1);
        assert.equal(after.cycles.at(-1).id, after.currentCycle);
    }
    assert.equal(
        (await stored()).grants.length,
        grantsBeforePattern + 6,
        "Each Downtime re-entry repeats its entry grant.",
    );
    const cursor = (await stored()).pattern.cursor;
    const active = (await stored()).cycles.at(-1).name;
    await btn(`Move ${active} to next phase`).click();
    assert.equal((await stored()).currentPhase, "downtime");
    assert.equal((await stored()).pattern.cursor, cursor);
    await page.reload();
    await btn("Schedule settings").waitFor();
    assert.equal((await stored()).pattern.cursor, cursor);
    const beforeOverride = await stored();
    const scheduledPhase = M.nextPatternPhase(beforeOverride);
    const overridePhase = beforeOverride.phases.find(
        (p) => p.id !== scheduledPhase,
    ).id;
    await btn("End cycle").click();
    const phaseSelect = dialog.getByLabel("Phase for the new cycle", {
        exact: true,
    });
    assert.equal(await phaseSelect.inputValue(), scheduledPhase);
    await phaseSelect.selectOption(overridePhase);
    assert.equal(
        await dialog
            .locator(".cp-transition > div")
            .last()
            .getByText(M.getPhase(beforeOverride, overridePhase).name, {
                exact: true,
            })
            .count(),
        1,
    );
    assert.equal(await dialog.locator(".cp-inline-note").count(), 0);
    await screenshot("pattern-phase-override");
    await btn("Confirm and end cycle", dialog).click();
    const overridden = await stored();
    assert.equal(overridden.currentPhase, overridePhase);
    assert.equal(overridden.pattern.cursor, cursor + 1);
    await btn("End cycle").click();
    assert.equal(
        await phaseSelect.inputValue(),
        M.nextPatternPhase(overridden),
    );
    await btn("Confirm and end cycle", dialog).click();
    assert.equal((await stored()).currentPhase, M.nextPatternPhase(overridden));
    await btn("Switch to player view").click();
    assert.equal(await btn("End cycle").count(), 0);
    assert.equal(await btn("Schedule settings").count(), 0);
    assert.equal(await ui.getByText(/Drag upcoming/).count(), 0);
    assert.equal(await ui.getByText(/Moving the active cycle/).count(), 0);
    assert.equal(await ui.locator('[draggable="true"]').count(), 0);
    await btn("Switch to arbitrator view").click();
    await page.setViewportSize({ width: 1440, height: 1100 });
    await screenshot("schedule-desktop");
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot("schedule-mobile");
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await btn("Schedule settings").click();
    await screenshot("pattern-settings-mobile");
    await dialog
        .getByLabel("Use a repeating pattern", { exact: true })
        .uncheck();
    await btn("Save", dialog).click();
    assert.equal(await btn("End cycle").count(), 1);
    await btn("Schedule settings").click();
    await dialog.getByLabel("Use a repeating pattern", { exact: true }).check();
    acceptConfirm = true;
    await btn("Cancel", dialog).click();
    assert.equal(await dialog.count(), 0);
    assert.equal((await stored()).pattern, null);
    await btn("Duplicate Downtime").click();
    const duplicate = (await stored()).phases.find(
        (p) => p.name === "Downtime (copy)",
    );
    assert.ok(duplicate && duplicate.id !== "downtime");
    await btn("Edit Downtime (copy)").click();
    assert.equal(
        await dialog
            .getByLabel("Credits per gang", { exact: true })
            .inputValue(),
        "250",
    );
    await btn("Cancel", dialog).click();
    await btn("Schedule settings").click();
    assert.equal(
        await dialog
            .getByLabel("Total campaign cycles", { exact: true })
            .count(),
        0,
    );
    await dialog
        .getByLabel("Campaign length", { exact: true })
        .selectOption("fixed");
    await btn("Save", dialog).click();
    assert.equal((await stored()).limit, (await stored()).cycles.length);
    await btn("Schedule settings").click();
    assert.equal(
        await dialog
            .getByLabel("Show rough dates for cycles", { exact: true })
            .count(),
        1,
    );
    await screenshot("settings-fixed");
    await btn("Cancel", dialog).click();
    await btn("Back to campaign").click();
    assert.equal(await btn("End campaign").count(), 1);
    await campaignAction("Manage phases & cycles");
    const beforeInsert = await stored();
    await btn("Add cycle to Occupation").click();
    const afterInsert = await stored();
    assert.equal(afterInsert.cycles.length, beforeInsert.cycles.length + 1);
    assert.equal(afterInsert.limit, afterInsert.cycles.length);
    assert.equal(afterInsert.currentCycle, beforeInsert.currentCycle);
    assert.equal(afterInsert.cycles.at(-1).phase, "occupation");
    assert.equal(afterInsert.grants.length, beforeInsert.grants.length);
    // Reopening must expose a truly active cycle, including its drag handle.
    const ended = M.defaults();
    while (!ended.ended) M.advance(ended);
    await page.evaluate(
        ({ key, state }) => localStorage.setItem(key, JSON.stringify(state)),
        { key: M.storageKey, state: ended },
    );
    await page.goto(`${origin}/campaign/`);
    await btn("Reopen campaign").click();
    const reopened = await stored();
    assert.ok(!reopened.closedCycles.includes(reopened.currentCycle));
    await campaignAction("Manage phases & cycles");
    assert.equal(
        await ui
            .locator(`[data-cycle-id="${reopened.currentCycle}"]`)
            .getAttribute("draggable"),
        "true",
    );
    await btn("Back to campaign").click();
    await btn("Record a battle").click();
    const beforeBadBattle = await stored();
    await dialog
        .getByLabel("Battle name", { exact: true })
        .fill("Invalid participants");
    await dialog
        .getByLabel("Gang 2", { exact: true })
        .selectOption(beforeBadBattle.gangs[0].id);
    await btn("Record battle", dialog).click();
    assert.match(
        await dialog.getByRole("alert").textContent(),
        /two different gangs/,
    );
    assert.deepEqual((await stored()).gangs, beforeBadBattle.gangs);
    await btn("Cancel", dialog).click();
    // Unreadable or future-version storage is preserved until an explicit reset.
    const malformed = M.defaults();
    malformed.phases[0].rewards = null;
    for (const raw of [
        "{bad json",
        JSON.stringify({ ...M.defaults(), version: 99 }),
        JSON.stringify(malformed),
    ]) {
        await page.evaluate(({ key, raw }) => localStorage.setItem(key, raw), {
            key: M.storageKey,
            raw,
        });
        await page.reload();
        await ui.getByText(/Saved campaign data could not be read/).waitFor();
        assert.equal(
            await page.evaluate(
                (key) => localStorage.getItem(key),
                M.storageKey,
            ),
            raw,
        );
        await btn("End cycle").click();
        await btn("Confirm and end cycle", dialog).click();
        assert.equal(
            await page.evaluate(
                (key) => localStorage.getItem(key),
                M.storageKey,
            ),
            raw,
        );
    }
    await btn("Reset demo").click();
    await btn("Reset demo", dialog).click();
    assert.equal((await stored()).cycles.length, 7);
    assert.equal(
        await ui.getByText(/Saved campaign data could not be read/).count(),
        0,
    );
    const unavailable = await browser.newContext();
    await unavailable.addInitScript(() => {
        Object.defineProperty(Storage.prototype, "getItem", {
            value() {
                throw new DOMException("Unavailable", "SecurityError");
            },
        });
        Object.defineProperty(Storage.prototype, "setItem", {
            value() {
                throw new DOMException("Unavailable", "SecurityError");
            },
        });
    });
    const unavailablePage = await unavailable.newPage();
    unavailablePage.on("pageerror", (e) => errors.push(e.message));
    await unavailablePage.goto(`${origin}/campaign/`);
    const unavailableUi = unavailablePage.locator("#campaign-root");
    await unavailableUi
        .getByRole("heading", { name: "The Ash Road", exact: true })
        .waitFor();
    await unavailableUi
        .getByRole("button", { name: "Toggle theme", exact: true })
        .click();
    assert.equal(
        await unavailableUi
            .getByText(/Saved campaign data could not be read/)
            .count(),
        1,
    );
    await unavailable.close();
    assert.deepEqual(errors, []);
    console.log(
        "Campaign browser checks passed: schedules, patterns, drag previews, forms, storage recovery, player view, keyboard and responsive layouts.",
    );
} finally {
    await browser.close();
}
