import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import * as M from "./src/history-model.js";
import * as D from "./src/history-demo.js";
import { graphLayout } from "./src/history-graph.js";
let nestedFixture = M.undo(M.seed());
nestedFixture = M.addActivity(nestedFixture, "income");
nestedFixture = M.restore(nestedFixture, "v4");
let nestedGroups = M.timelineGroups(nestedFixture);
assert.equal(nestedGroups.length, 1);
assert.deepEqual(nestedGroups[0].children[0].ids, ["v9"]);
assert.equal(nestedGroups[0].anchor, "v4");
const resetFixture = D.resetExampleGang(nestedFixture);
assert.equal(resetFixture.versions.length, 1);
assert.equal(M.current(resetFixture).credits, 1000);
assert.equal(resetFixture.journal.length, 0);
assert.deepEqual(resetFixture.otherHistories, nestedFixture.otherHistories);
const populatedFixture = D.populateExampleGang(D.resetExampleGang(M.seed()));
assert.ok(
    new Set(populatedFixture.versions.map((e) => e.when.slice(0, 10))).size >=
        6,
);
assert.ok(
    M.timelineGroups(populatedFixture).some((g) => g.children.length),
    "Sample includes nested undo sequences.",
);
const sampleDates = populatedFixture.versions.map((e) =>
    new Date(e.when).toLocaleDateString("en-CA", {
        timeZone: "America/Mexico_City",
    }),
);
assert.equal(sampleDates.at(-1), "2026-10-22");
assert.ok(sampleDates.every((day) => day <= "2026-10-22"));
const futureFixture = structuredClone(populatedFixture);
for (const event of [...futureFixture.versions, ...futureFixture.journal])
    event.when = new Date(Date.parse(event.when) + 7 * 86400000).toISOString();
delete futureFixture.demoSampleStartId;
delete futureFixture.demoSampleEndId;
const migratedDates = D.dateExampleHistory(futureFixture);
assert.deepEqual(
    migratedDates.versions.map((e) => e.id),
    futureFixture.versions.map((e) => e.id),
);
assert.equal(
    migratedDates.versions.at(-1).when,
    populatedFixture.versions.at(-1).when,
);
assert.deepEqual(M.current(migratedDates), M.current(populatedFixture));
const graphFixture = graphLayout(nestedFixture, M.entries(nestedFixture));
assert.equal(graphFixture.points.length, nestedFixture.versions.length);
assert.ok(
    graphFixture.edges.some(
        (e) => e.return && e.from.entry.type === "restore" && e.to.y < e.from.y,
    ),
);
assert.ok(graphFixture.edges.some((e) => e.inactive && e.to.y > e.from.y));
const undoneRestoreFixture = M.undo(nestedFixture);
const undoneRestoreGraph = graphLayout(
    undoneRestoreFixture,
    M.entries(undoneRestoreFixture),
);
assert.ok(
    undoneRestoreGraph.points.some(
        (p) => p.entry.id === nestedFixture.head && p.inactive,
    ),
    "Undone restore node remains in its branch.",
);
assert.ok(
    !undoneRestoreGraph.edges.some(
        (e) => e.return && e.from.entry.id === nestedFixture.head,
    ),
    "Undone restores have no canonical return connector.",
);
const movedJunction = undoneRestoreGraph.junctions.find(
    (p) => p.entry.id === nestedFixture.head,
);
assert.ok(
    movedJunction.inactive && movedJunction.y > graphFixture.junctions[0].y,
    "Undone restore junction moves below canonical history.",
);
assert.ok(
    undoneRestoreGraph.edges.some(
        (e) =>
            e.undoneRestore &&
            e.from.entry.id === nestedFixture.head &&
            e.to === movedJunction &&
            e.from.y !== e.to.y,
    ),
    "A dotted connection joins the restore symbol and relocated junction.",
);
const redoneRestoreFixture = M.redo(undoneRestoreFixture, nestedFixture.head);
assert.ok(
    graphLayout(
        redoneRestoreFixture,
        M.entries(redoneRestoreFixture),
    ).edges.some((e) => e.return && e.from.entry.id === nestedFixture.head),
    "Redo reinstates the canonical return connector.",
);
const redoneGraph = graphLayout(
    redoneRestoreFixture,
    M.entries(redoneRestoreFixture),
);
assert.ok(
    !redoneGraph.junctions.find((p) => p.entry.id === nestedFixture.head)
        .inactive,
);
assert.ok(
    !redoneGraph.edges.some(
        (e) => e.undoneRestore && e.from.entry.id === nestedFixture.head,
    ),
);
const mainPoints = graphFixture.points.filter(
    (p) => !p.inactive && p.entry.type !== "restore",
);
assert.equal(
    new Set([...mainPoints, ...graphFixture.junctions].map((p) => p.y)).size,
    1,
    "Canonical route stays horizontal.",
);
let reuseFixture = M.undo(M.seed());
reuseFixture = M.addActivity(reuseFixture, "income");
reuseFixture = M.addActivity(reuseFixture, "income");
reuseFixture = M.undo(reuseFixture);
reuseFixture = M.addActivity(reuseFixture, "income");
const reuseGraph = graphLayout(reuseFixture, M.entries(reuseFixture));
assert.equal(
    reuseGraph.points.find((p) => p.entry.id === "v9").y,
    reuseGraph.points.find((p) => p.entry.id === "v11").y,
    "Disjoint branch intervals reuse a lane.",
);
const fixtureCount = nestedFixture.versions.length;
nestedFixture = M.generateDemoActions(nestedFixture);
assert.equal(nestedFixture.versions.length, fixtureCount + 10);
assert.equal(M.timelineGroups(nestedFixture)[0].children.length, 1);
const initial = M.seed(),
    original = structuredClone(initial);
let state = M.undo(initial);
assert.equal(state.head, "v8");
assert.equal(M.entries(state).length, 9, "Undo does not add a public action.");
assert.equal(M.status(state, "v9").actor, "louis");
assert.equal(M.current(state).models[1].skills.length, 0);
state = M.redo(state);
assert.equal(M.entries(state).length, 9, "Redo does not add a public action.");
assert.equal(M.current(state).models[1].skills[0], "Spring Up");
state = M.addActivity(M.undo(state), "armour");
const branch = state.head;
assert.equal(M.current(state).rating, 835);
state = M.undo(state);
assert.equal(M.children(state).length, 2);
state = M.redo(state, "v9");
const beforeRestore = structuredClone(M.current(state));
const beforeRestoreHead = state.head;
state = M.restore(state, "v4");
const restoreId = state.head;
assert.equal(M.version(state).type, "restore");
assert.equal(M.version(state).parent, beforeRestoreHead);
assert.equal(M.version(state).restoreTarget, "v4");
let reversed = M.undo(state);
assert.deepEqual(
    M.current(reversed),
    beforeRestore,
    "Undo restores the exact state before a restore.",
);
assert.equal(reversed.head, beforeRestoreHead);
assert.equal(M.status(reversed, restoreId).type, "undo");
assert.equal(M.status(reversed, "v5"), null);
reversed = M.redo(reversed, restoreId);
assert.equal(reversed.head, restoreId);
assert.equal(
    M.status(reversed, "v5").type,
    "restore",
    "Redoing a restore reinstates its undo annotations.",
);
assert.equal(M.current(reversed).rating, 770);
const extra = M.addActivity(state, "armour");
assert.equal(M.undo(extra).head, restoreId);
assert.deepEqual(M.current(M.undo(M.undo(extra))), beforeRestore);
assert.equal(M.current(state).rating, 770);
assert.equal(M.current(state).credits, 230);
assert.deepEqual(M.current(state).models[0].equipment, [
    "Lasgun",
    "Mesh armour",
]);
assert.equal(M.current(state).models[2].status, "Active");
assert.equal(M.status(state, "v5").type, "restore");
assert.equal(M.status(state, branch).type, "undo");
assert.match(M.entries(state)[0].description, /18 October 2026/);
assert.ok(!M.entries(state).some((e) => /version v\d/i.test(e.description)));
state = M.highlight(state, "v4", "louis");
assert.ok(M.isHighlighted(state, "v4", "louis"));
assert.equal(
    M.isHighlighted(state, "v4", "mira"),
    false,
    "Highlights are private to the owner.",
);
assert.throws(() => M.highlight(state, "v4", "mira"));
assert.throws(() => M.restore(state, "v5", "mira"));
const journalBeforeClone = state.journal.length,
    entriesBeforeClone = M.entries(state).length;
state = M.cloneVersion(state, "v7", "Recovery copy");
assert.equal(
    state.journal.length,
    journalBeforeClone,
    "Cloning adds no journal event.",
);
assert.equal(
    M.entries(state).length,
    entriesBeforeClone,
    "Cloning adds no activity row.",
);
assert.equal(state.head, restoreId);
state.clones[0].snapshot.models[0].equipment.push("Clone only");
assert.equal(
    M.version(state, "v7").snapshot.models[0].equipment.includes("Clone only"),
    false,
);
assert.deepEqual(
    state.versions.slice(0, 9),
    original.versions,
    "All original actions remain unchanged.",
);
const ownIron = M.historyFor(state, "iron");
assert.throws(() => M.undo(ownIron, "louis"));
assert.equal(M.undo(ownIron, "mira").head, "iron-purchase");
assert.deepEqual(initial, original);
const legacy = structuredClone(initial);
delete legacy.highlightsByOwner;
delete legacy.otherHistories;
legacy.highlights = ["v6"];
const migrated = M.hydrate(legacy);
assert.ok(M.isHighlighted(migrated, "v6", "louis"));
assert.equal(M.isHighlighted(migrated, "v6", "mira"), false);
assert.deepEqual(migrated.versions, initial.versions);
const oldRestoreState = M.seed();
oldRestoreState.journal.push({
    id: "old-restore",
    type: "restore",
    when: "2026-10-21T12:00:00-06:00",
    actor: "louis",
    gang: "nightshade",
    category: "history",
    from: "v9",
    to: "v4",
    before: structuredClone(M.current(initial)),
    snapshot: structuredClone(M.version(initial, "v4").snapshot),
    affected: ["v5", "v6", "v7", "v8", "v9"],
    restored: [],
});
oldRestoreState.head = "v4";
const upgraded = M.hydrate(oldRestoreState);
assert.equal(upgraded.head, "old-restore");
assert.deepEqual(
    M.current(M.undo(upgraded)),
    M.current(initial),
    "Existing stored restores are undoable after upgrade.",
);
assert.equal(M.entries(upgraded).filter((e) => e.type === "restore").length, 1);
assert.deepEqual(
    upgraded.versions.slice(0, 9).map((e) => e.snapshot),
    initial.versions.map((e) => e.snapshot),
);
const oldAfter = structuredClone(oldRestoreState);
oldAfter.versions.push({
    id: "legacy-later",
    parent: "v4",
    when: "2026-10-21T13:00:00-06:00",
    actor: "louis",
    gang: "nightshade",
    category: "gang",
    description: "Notes edited.",
    snapshot: {
        ...structuredClone(M.current(oldRestoreState)),
        notes: "Retained note.",
    },
});
oldAfter.head = "legacy-later";
const upgradedAfter = M.hydrate(oldAfter);
assert.equal(M.version(upgradedAfter, "legacy-later").parent, "old-restore");
assert.deepEqual(M.current(M.undo(M.undo(upgradedAfter))), M.current(initial));

const sameStateRestore = M.restore(initial, initial.head);
assert.equal(
    M.entries(sameStateRestore).length,
    10,
    "An explicit restore remains recorded even if its state is already current.",
);
assert.throws(() =>
    M.addRoll(initial, { reason: "Test", count: 2, results: [0, 7] }),
);
const rolled = M.addRoll(initial, {
    reason: "Rare trade availability",
    count: 2,
    results: [4, 2],
    outcome: "Rare trade available.",
});
assert.deepEqual(M.version(rolled).dice, [4, 2]);
assert.deepEqual(
    M.current(rolled),
    M.current(initial),
    "Logging a roll does not change gang figures.",
);
console.log(
    "History model: retained branches, private highlights, owner checks, exact restoration, independent clones, hidden undo/redo and dice passed.",
);
mkdirSync("qa", { recursive: true });
const origin = process.env.HISTORY_ORIGIN || "http://127.0.0.1:8766";
const browser = await chromium.launch({
    ...(process.env.CHROME_PATH
        ? { executablePath: process.env.CHROME_PATH }
        : {}),
    headless: true,
});
const resetPage = await browser.newPage();
await resetPage.goto(`${origin}/history/?page=2`);
await resetPage.locator("#history-root .history-entry").first().waitFor();
const populatedCount = await resetPage
    .locator("#history-root .history-entry")
    .count();
assert.ok(
    populatedCount > 15,
    "Example gang is populated with retained sample activity.",
);
await resetPage
    .locator("#history-root")
    .getByRole("button", { name: "Generate demo actions", exact: true })
    .click();
await resetPage.reload();
await resetPage.locator("#history-root .history-entry").first().waitFor();
assert.equal(
    await resetPage.locator("#history-root .history-entry").count(),
    populatedCount + 10,
    "New actions survive the one-time population.",
);
await resetPage.close();
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
await page.addInitScript(
    ({ key, reset, fixture }) => {
        if (!localStorage.getItem(key))
            localStorage.setItem(key, JSON.stringify(fixture));
        localStorage.setItem(reset, "done");
        localStorage.setItem("gyrinx-history-sample-week-2026-10-22", "done");
    },
    { key: M.STORAGE_KEY, reset: D.DEMO_RESET_KEY, fixture: M.seed() },
);
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const ui = page.locator("#history-root");
const entry = (id) => ui.locator(`[data-entry-id="${id}"]`);
async function actions(id) {
    await entry(id).getByLabel("Entry actions", { exact: true }).click();
}
async function screenshot(name) {
    await page.evaluate(
        () =>
            new Promise((resolve) => {
                window.scrollTo(0, 0);
                requestAnimationFrame(() => requestAnimationFrame(resolve));
            }),
    );
    await page.screenshot({
        path: `qa/history-${name}.png`,
        fullPage: true,
        animations: "disabled",
    });
}
async function goto(path = "") {
    await page.goto(`${origin}/history/${path}`);
    await ui.locator("h1").waitFor();
}
async function apply() {
    await ui.getByRole("button", { name: /^(Apply filters|Filter)$/ }).click();
}
try {
    await goto();
    assert.equal(await ui.locator("h1").innerText(), "History");
    assert.equal(await ui.locator(".history-entry").count(), 9);
    assert.equal(
        await ui
            .locator(".history-column")
            .evaluate((e) => Math.round(e.getBoundingClientRect().width)),
        672,
        "N26 log column is max-w-2xl.",
    );
    assert.equal(
        await ui
            .locator(".history-day h2")
            .first()
            .evaluate((e) => getComputedStyle(e).color),
        await ui
            .locator(".entry-figures time")
            .first()
            .evaluate((e) => getComputedStyle(e).color),
    );
    assert.equal(await ui.locator(".entry-meta .identity-user img").count(), 9);
    assert.equal(await ui.locator(".entry-meta .house-icon").count(), 9);
    assert.ok(
        !/\bversion v\d/i.test(await ui.locator(".history-column").innerText()),
    );
    const toolbarBounds = await ui
        .locator(".history-top-controls")
        .boundingBox();
    const filtersBounds = await ui
        .locator('form[aria-label="History filters"]')
        .boundingBox();
    assert.ok(
        toolbarBounds.y < filtersBounds.y,
        "Undo/redo appear above the filters.",
    );
    assert.equal(await ui.locator(".timeline-node.latest").count(), 1);
    assert.equal(await ui.locator(".timeline-node circle").count(), 8);
    assert.equal(
        await ui.locator(".timeline-node circle").first().getAttribute("fill"),
        "none",
    );
    await screenshot("gang-desktop");
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(await ui.locator(".history-entry").count(), 9);
    assert.match(await entry("v9").innerText(), /Undone by user ·\s*louis/);
    assert.equal(
        await entry("v9").evaluate((e) => getComputedStyle(e).opacity),
        "1",
    );
    assert.equal(
        await entry("v9")
            .locator(".entry-record")
            .evaluate((e) => getComputedStyle(e).opacity),
        "0.5",
        "Action content fades independently of the menu.",
    );
    for (const selector of [".entry-meta", ".entry-figures", ".entry-state"]) {
        assert.equal(
            await entry("v9")
                .locator(selector)
                .evaluate((e) => {
                    let opacity = 1;
                    for (
                        let node = e;
                        node?.nodeType === 1;
                        node = node.parentElement
                    )
                        opacity *= Number(getComputedStyle(node).opacity);
                    return opacity;
                }),
            0.5,
            `${selector} fades with the whole row.`,
        );
    }
    assert.equal(
        await entry("v9")
            .locator(".entry-tools")
            .evaluate((e) => getComputedStyle(e).opacity),
        "1",
    );
    assert.equal(
        await ui
            .locator(".timeline-rail.branch")
            .first()
            .evaluate((e) => getComputedStyle(e).borderLeftStyle),
        "dashed",
    );
    assert.equal(
        await ui
            .locator(".timeline-rail.branch")
            .first()
            .evaluate((e) => getComputedStyle(e).opacity),
        "0.5",
    );
    assert.equal(
        await entry("v8").evaluate((e) => getComputedStyle(e).zIndex),
        "1",
    );
    const terminal = await ui
        .locator(".timeline-rail.branch")
        .first()
        .boundingBox();
    const noteBounds = await entry("v9").locator(".undone-note").boundingBox();
    assert.ok(
        Math.abs(
            terminal.y + terminal.height - noteBounds.y - noteBounds.height / 2,
        ) < 1,
    );
    assert.equal(await ui.locator(".undo-terminal").count(), 1);
    async function assertUndoArrowCentres() {
        const offsets = await ui
            .locator(".undo-terminal")
            .evaluateAll((arrows) =>
                arrows.map((arrow) => {
                    const a = arrow.getBoundingClientRect(),
                        rail = arrow.parentElement,
                        r = rail.getBoundingClientRect();
                    return (
                        a.left +
                        a.width / 2 -
                        (r.left +
                            parseFloat(getComputedStyle(rail).borderLeftWidth) /
                                2)
                    );
                }),
            );
        assert.ok(
            offsets.length &&
                offsets.every((offset) => Math.abs(offset) < 0.05),
            "Every undo arrowhead is centred on the rail stroke.",
        );
    }
    await assertUndoArrowCentres();
    assert.equal(
        await entry("v9")
            .locator(".timeline-node")
            .evaluate((e) => getComputedStyle(e).opacity),
        "1",
        "Node background stays opaque to break the rail.",
    );
    const indent = await entry("v9").evaluate((e) => {
        const row = e.getBoundingClientRect(),
            list = e.parentElement.getBoundingClientRect();
        return {
            actual: row.x - list.x,
            expected: Math.max(16, Math.min(32, list.width * 0.05)),
        };
    });
    assert.ok(
        Math.abs(indent.actual - indent.expected) < 1,
        "Undone lanes use compact spacing around 5%.",
    );
    assert.equal(
        await ui
            .locator(".history-day h2")
            .first()
            .evaluate((e) => getComputedStyle(e).textAlign),
        "right",
    );
    await ui.getByRole("button", { name: "Redo", exact: true }).click();
    assert.equal(await ui.locator(".history-entry").count(), 9);
    assert.ok(!(await entry("v9").innerText()).includes("Undone"));
    await actions("v4");
    assert.equal(
        (
            await entry("v4")
                .locator(".history-menu-panel > :nth-child(2)")
                .innerText()
        ).trim(),
        "Highlight",
    );
    await ui.getByRole("button", { name: "Highlight", exact: true }).click();
    assert.ok(await entry("v4").locator(".highlight-mark").count());
    await ui
        .getByRole("combobox", { name: "Show", exact: true })
        .selectOption("highlighted");
    await apply();
    assert.equal(await ui.locator(".history-entry").count(), 2);
    await page.reload();
    await entry("v4").waitFor();
    assert.equal(await ui.locator(".history-entry").count(), 2);
    await goto("?viewer=mira");
    assert.equal(await ui.locator(".highlight-mark").count(), 0);
    assert.equal(await ui.locator(".highlighted").count(), 0);
    assert.equal(
        await ui
            .getByRole("combobox", { name: "Show", exact: true })
            .locator('option[value="highlighted"]')
            .count(),
        0,
    );
    assert.equal(
        await ui.getByRole("button", { name: "Undo", exact: true }).count(),
        0,
    );
    await entry("v4").locator(".identity-gang").click();
    await ui.locator("h1").waitFor();
    assert.match(page.url(), /viewer=mira/);
    assert.equal(await ui.locator(".highlight-mark").count(), 0);
    await goto("campaign/?view=timeline");
    assert.ok(!new URL(page.url()).searchParams.has("view"));
    assert.equal(
        await ui.getByRole("button", { name: "Timeline", exact: true }).count(),
        0,
    );
    assert.equal(
        await ui
            .locator(
                ".branch-timeline,.timeline-rails,.timeline-node,.nested-branch",
            )
            .count(),
        0,
        "Campaign activity is a flat feed.",
    );
    assert.ok(await ui.locator(".campaign-history").count());
    assert.equal(await ui.locator("h1").innerText(), "Log");
    assert.equal(
        await ui
            .getByRole("combobox", {
                name: "Player or arbitrator",
                exact: true,
            })
            .count(),
        1,
    );
    assert.equal(
        await ui.getByRole("combobox", { name: "Gang", exact: true }).count(),
        1,
    );
    assert.equal(await ui.getByLabel("From date", { exact: true }).count(), 1);
    await actions("v5");
    const restore = ui.getByRole("button", {
        name: "Restore this version",
        exact: true,
    });
    assert.equal(
        await restore.count(),
        1,
        "Own actions are controllable in the campaign log.",
    );
    assert.equal(
        await restore.locator("svg.lucide-rotate-cw-fading-clock").count(),
        1,
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Clone from version", exact: true })
            .locator("svg.lucide-git-fork")
            .count(),
        1,
    );
    await page.keyboard.press("Escape");
    await actions("iron-purchase");
    assert.equal(
        await ui
            .getByRole("button", { name: "Restore this version", exact: true })
            .count(),
        0,
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Highlight", exact: true })
            .count(),
        0,
    );
    await page.keyboard.press("Escape");
    await screenshot("campaign-desktop");
    await actions("v5");
    const href = await ui
        .getByRole("link", { name: "Link to this entry", exact: true })
        .getAttribute("href");
    assert.match(href, /gang\/nightshade\/\?entry=v5/);
    await ui
        .getByRole("link", { name: "Link to this entry", exact: true })
        .click();
    await entry("v5").waitFor();
    assert.ok(
        await entry("v5").evaluate((e) => e === e.getRootNode().activeElement),
    );
    await actions("v5");
    await ui.getByRole("link", { name: "View snapshot", exact: true }).click();
    await ui
        .getByRole("heading", {
            name: "Nightshade Coven",
            level: 1,
            exact: true,
        })
        .waitFor();
    assert.match(
        await ui.locator(".snapshot-banner").innerText(),
        /Static snapshot/,
    );
    assert.match(
        await ui.locator(".snapshot-details").innerText(),
        /Plasma pistol/,
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Restore this version", exact: true })
            .count(),
        1,
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Clone this version", exact: true })
            .count(),
        1,
    );
    await screenshot("snapshot-desktop");
    await ui
        .getByRole("button", { name: "Clone this version", exact: true })
        .click();
    await ui
        .getByRole("dialog")
        .getByRole("textbox", { name: "Gang name", exact: true })
        .fill("Snapshot copy");
    await ui
        .getByRole("dialog")
        .getByRole("button", { name: "Clone this version", exact: true })
        .click();
    await ui
        .getByRole("heading", { name: "Snapshot copy", exact: true, level: 1 })
        .waitFor();
    assert.match(page.url(), /\/history\/gang\/[\w-]+\//);
    assert.equal(
        await ui.locator('[data-testid="snapshot-rating"]').innerText(),
        "820",
    );
    assert.match(
        await ui.locator(".snapshot-details").innerText(),
        /Plasma pistol/,
    );
    await screenshot("cloned-gang");
    await goto("gang/nightshade/snapshots/v4/");
    await ui
        .getByRole("button", { name: "Restore this version", exact: true })
        .click();
    await ui
        .getByRole("dialog")
        .getByRole("button", { name: "Restore this version", exact: true })
        .click();
    await ui.getByText("Gang restored.", { exact: true }).waitFor();
    assert.match(
        page.url(),
        /gang\/nightshade\/snapshots\/v4\//,
        "Restoring stays on the current page.",
    );
    await goto();
    assert.equal(
        await ui.locator('[data-testid="current-rating"]').innerText(),
        "770",
    );
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(
        await ui.locator('[data-testid="current-rating"]').innerText(),
        "820",
    );
    await ui.getByRole("button", { name: "Redo", exact: true }).click();
    assert.equal(
        await ui.locator('[data-testid="current-rating"]').innerText(),
        "770",
    );
    await goto();
    assert.match(
        await ui.locator(".history-timeline").innerText(),
        /Restored their gang to the 18 October 2026/,
    );
    assert.match(await entry("v5").innerText(), /Undone by a restore/);
    const restoredRow = ui
        .locator(".history-entry")
        .filter({ hasText: "Restored their gang to the" });
    const restoredId = await restoredRow.getAttribute("data-entry-id");
    assert.equal(
        await restoredRow.locator(".entry-tools").count(),
        0,
        "Restore records have no row actions.",
    );
    const restoreLine = await ui.locator(".restore-rail").first().boundingBox();
    const restoredPoint = await entry("v4").boundingBox();
    assert.ok(
        Math.abs(restoreLine.y + restoreLine.height - restoredPoint.y - 18) < 1,
        "Restore line reaches the restored action node.",
    );
    const targetLink = restoredRow.locator(".entry-description a");
    assert.equal(await targetLink.getAttribute("href"), "#entry-v4");
    await targetLink.click();
    assert.match(page.url(), /entry=v4#entry-v4/);
    assert.ok(
        await entry("v4").evaluate((e) => e === e.getRootNode().activeElement),
    );
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(
        await ui.locator('[data-testid="current-rating"]').innerText(),
        "820",
    );
    assert.match(await entry(restoredId).innerText(), /Undone by user/);
    assert.equal(
        await entry(restoredId).evaluate((e) => getComputedStyle(e).opacity),
        "1",
    );
    assert.ok(!(await entry("v5").innerText()).includes("Undone"));
    await ui.getByRole("button", { name: "Redo", exact: true }).click();
    assert.equal(
        await ui.locator('[data-testid="current-rating"]').innerText(),
        "770",
    );
    assert.match(await entry("v5").innerText(), /Undone by a restore/);
    assert.equal(
        await ui
            .locator(".history-entry")
            .filter({ hasText: "Restored their gang to the" })
            .count(),
        1,
        "Undo and redo retain the original restore action.",
    );
    assert.equal(
        await entry("v7").evaluate(
            (e) => getComputedStyle(e).borderBottomWidth,
        ),
        "1px",
        "The inset row retains its divider.",
    );
    await screenshot("gang-restored");
    await goto("campaign/?viewer=mira");
    assert.equal(
        await ui.locator(".highlight-mark").count(),
        1,
        "Only mira’s private highlight is shown.",
    );
    assert.equal(await entry("v4").locator(".highlight-mark").count(), 0);
    await actions("iron-purchase");
    assert.equal(
        await ui
            .getByRole("button", { name: "Restore this version", exact: true })
            .count(),
        1,
        "mira can control her gang from the campaign log.",
    );
    await page.keyboard.press("Escape");
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(
        await entry("iron-income").evaluate(
            (e) => getComputedStyle(e).marginLeft,
        ),
        "0px",
        "Undone campaign entries remain aligned.",
    );
    assert.equal(
        await ui
            .locator(".timeline-rails,.timeline-node,.nested-branch")
            .count(),
        0,
    );
    assert.match(
        await entry("iron-income").innerText(),
        /Undone by user ·\s*mira/,
    );
    await ui.getByRole("button", { name: "Redo", exact: true }).click();
    await goto("campaign/roll/");
    await ui
        .getByRole("textbox", { name: "Reason *", exact: true })
        .fill("Rare trade availability");
    await ui
        .getByRole("combobox", { name: "Roll source", exact: true })
        .selectOption("record");
    await ui
        .getByRole("textbox", { name: "Dice results *", exact: true })
        .fill("4, 2");
    await ui
        .getByRole("textbox", { name: "Outcome", exact: true })
        .fill("Rare trade available.");
    await ui.getByRole("button", { name: "Record roll", exact: true }).click();
    await ui.locator(".history-timeline").waitFor();
    assert.match(page.url(), /campaign\/\?entry=/);
    assert.match(
        await ui.locator(".entry-targeted").innerText(),
        /Rare trade available/,
    );
    assert.equal(
        await ui.locator(".entry-targeted .history-dice svg").count(),
        2,
    );
    assert.equal(await ui.locator(".linked-mark").innerText(), "Linked");
    assert.equal(await ui.locator(".linked-mark svg").count(), 1);
    assert.equal(
        await ui
            .locator(".entry-targeted")
            .evaluate((e) => getComputedStyle(e).outlineStyle),
        "none",
    );
    await ui.getByRole("button", { name: "Toggle theme", exact: true }).click();
    assert.ok(!new URL(page.url()).searchParams.has("entry"));
    assert.equal(new URL(page.url()).hash, "");
    assert.equal(await ui.locator(".linked-mark").count(), 0);
    await ui.locator(".history-page.dark").waitFor();
    await screenshot("campaign-dark");
    await page.setViewportSize({ width: 390, height: 844 });
    await screenshot("campaign-mobile-dark");
    await ui.getByRole("button", { name: "Toggle theme", exact: true }).click();
    await ui.locator(".history-page:not(.dark)").waitFor();
    await screenshot("campaign-mobile");
    assert.ok(
        await ui
            .locator(".history-page")
            .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
    );
    await goto("gang/nightshade/snapshots/v5/");
    assert.equal(
        await ui.locator('[data-testid="snapshot-rating"]').innerText(),
        "820",
    );
    assert.match(
        await ui.locator(".snapshot-details").innerText(),
        /Plasma pistol/,
    );
    await goto("gang/nightshade/snapshots/v4/");
    await screenshot("snapshot-mobile");
    assert.ok(
        await ui
            .locator(".history-page")
            .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
    );
    await goto();
    await screenshot("gang-mobile");
    await page.setViewportSize({ width: 320, height: 740 });
    assert.ok(
        await ui
            .locator(".history-page")
            .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
        "320px gang page has no overflow.",
    );
    await actions("v5");
    const menu = await entry("v5").locator(".history-menu-panel").boundingBox();
    assert.ok(menu.x >= 0 && menu.x + menu.width <= 320);
    await page.keyboard.press("Escape");
    let longHistory = M.seed();
    for (let i = 0; i < 60; i++)
        longHistory = M.addActivity(longHistory, "income");
    await page.evaluate(
        ({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
        { key: M.STORAGE_KEY, value: longHistory },
    );
    await goto("?entry=v2#entry-v2");
    assert.equal(await ui.locator(".history-entry").count(), 69);
    assert.ok(
        await entry("v2").evaluate((e) => e === e.getRootNode().activeElement),
        "Deep links locate entries throughout the unpaginated log.",
    );
    assert.equal(await ui.locator(".history-pagination").count(), 0);
    await goto("?page=2");
    assert.equal(await ui.locator(".history-entry").count(), 69);
    assert.ok(!new URL(page.url()).searchParams.has("page"));
    await ui.getByLabel("From date", { exact: true }).fill("2026-10-18");
    await ui.getByLabel("To date", { exact: true }).fill("2026-10-18");
    await apply();
    assert.equal(
        await ui.locator(".history-entry").count(),
        4,
        "Date filters include the selected day.",
    );
    await goto();
    await page.evaluate(
        ({ key }) => {
            const root = JSON.parse(localStorage.getItem(key));
            root.versions.push({
                id: "long-log-restore",
                parent: root.head,
                restoreTarget: "v2",
                targetEntryId: "v2",
                type: "restore",
                actor: "louis",
                gang: "nightshade",
                when: new Date().toISOString(),
                sourceWhen: root.versions.find((v) => v.id === "v2").when,
                category: "history",
                snapshot: structuredClone(
                    root.versions.find((v) => v.id === "v2").snapshot,
                ),
                before: structuredClone(
                    root.versions.find((v) => v.id === root.head).snapshot,
                ),
                affected: root.versions
                    .filter((v) => !["v1", "v2"].includes(v.id))
                    .map((v) => v.id),
            });
            root.head = "long-log-restore";
            localStorage.setItem(key, JSON.stringify(root));
        },
        { key: M.STORAGE_KEY },
    );
    await goto("?kind=history");
    await page.evaluate(() => (window.historyLinkCheck = "retained"));
    await entry("long-log-restore").locator(".entry-description a").click();
    await entry("v2").waitFor();
    assert.equal(
        await page.evaluate(() => window.historyLinkCheck),
        "retained",
        "Restore links navigate within the page without reloading.",
    );
    assert.ok(
        !new URL(page.url()).searchParams.has("kind"),
        "A restore link clears a filter that hides its target.",
    );
    assert.ok(
        await entry("v2").evaluate((e) => e === e.getRootNode().activeElement),
    );
    // Repeated restores retain the previous abandoned branches as nested timelines.
    let deep = M.undo(M.seed());
    deep = M.addActivity(deep, "income");
    deep = M.restore(deep, "v4");
    for (let i = 0; i < 5; i++) {
        deep = M.addActivity(deep, "income");
        deep = M.restore(deep, "v4");
    }
    assert.equal(M.timelineGroups(deep).length, 1);
    await page.evaluate(
        ({ key, value }) => localStorage.setItem(key, JSON.stringify(value)),
        { key: M.STORAGE_KEY, value: deep },
    );
    await goto();
    assert.equal(
        await entry("v9").count(),
        0,
        "Nested undone actions start collapsed.",
    );
    assert.ok(await ui.locator(".nested-branch").count());
    assert.equal(await ui.locator(".timeline-rail.canonical").count(), 1);
    assert.ok(
        await ui.locator('[data-level="2"]').count(),
        "Three timeline levels are visible together.",
    );
    await screenshot("three-level-timeline");
    for (let i = 0; i < 2; i++) {
        await ui.locator(".nested-branch button").first().click();
        await page.waitForTimeout(260);
    }
    assert.equal(await ui.locator(".timeline-rail.ancestor").count(), 3);
    assert.equal(await ui.locator(".timeline-truncated").count(), 1);
    assert.ok(await ui.locator(".undo-terminal").count());
    await screenshot("nested-timelines");
    await page.setViewportSize({ width: 320, height: 900 });
    await page.waitForTimeout(100);
    assert.ok(
        await ui
            .locator(".history-page")
            .evaluate((e) => e.scrollWidth <= e.clientWidth + 1),
        "Deep nesting fits a narrow phone.",
    );
    await assertUndoArrowCentres();
    await screenshot("nested-mobile");
    await ui
        .getByRole("button", { name: "Full timeline", exact: true })
        .click();
    await goto("?entry=v9#entry-v9");
    await entry("v9").waitFor();
    await actions("v9");
    assert.equal(
        await entry("v9")
            .locator(".entry-tools")
            .evaluate((e) => {
                let opacity = 1;
                for (let n = e; n?.nodeType === 1; n = n.parentElement)
                    opacity *= Number(getComputedStyle(n).opacity);
                return opacity;
            }),
        1,
        "Undone action options remain fully opaque.",
    );
    await page.keyboard.press("Escape");
    await goto();
    const countBefore = await ui.locator(".history-entry").count();
    await ui
        .getByRole("button", { name: "Generate demo actions", exact: true })
        .click();
    assert.equal(await ui.locator(".history-entry").count(), countBefore + 10);
    await screenshot("generated-actions");
    await ui.getByRole("button", { name: "Timeline", exact: true }).click();
    await ui.locator(".branch-timeline").waitFor();
    assert.equal(
        await ui.locator(".graph-node").count(),
        M.entries(M.generateDemoActions(deep)).length +
            graphLayout(deep, M.entries(deep)).junctions.length,
    );
    assert.ok(await ui.locator(".route-undone").count());
    assert.ok(await ui.locator(".route-restore").count());
    assert.ok(await ui.locator(".graph-junction-node.graph-undone").count());
    assert.ok(await ui.locator(".route-restore-undone").count());
    assert.equal(
        await ui
            .locator(".route-restore-undone")
            .first()
            .evaluate((e) => getComputedStyle(e).strokeDasharray),
        "0px, 5px",
    );
    const canonicalRestore = ui.locator(".graph-junction-node").first();
    await canonicalRestore.hover();
    await ui.locator(".graph-detail .restoration-node").waitFor();
    assert.equal(await ui.locator(".graph-detail .entry-tools").count(), 0);
    const canonicalBox = await canonicalRestore.boundingBox(),
        cardBox = await ui.locator(".graph-detail").boundingBox();
    assert.ok(
        cardBox.y >= canonicalBox.y + canonicalBox.height + 4 ||
            cardBox.y + cardBox.height <= canonicalBox.y - 4,
        "Canonical restore card anchors to the top junction.",
    );
    await page.mouse.move(0, 0);
    await ui.locator(".graph-detail").waitFor({ state: "hidden" });
    await canonicalRestore.click();
    await ui.locator(".graph-detail .restoration-node").waitFor();
    await ui
        .getByRole("button", { name: "Close action details", exact: true })
        .click();
    const graphRestore = ui.locator(".graph-node.graph-restore").first();
    await graphRestore.scrollIntoViewIfNeeded();
    await graphRestore.hover();
    await ui
        .getByRole("region", { name: "Action details", exact: true })
        .waitFor();
    await page.mouse.move(0, 0);
    await ui
        .getByRole("region", { name: "Action details", exact: true })
        .waitFor({ state: "hidden" });
    await graphRestore.click();
    await ui.locator("h1").click();
    await ui
        .getByRole("region", { name: "Action details", exact: true })
        .waitFor({ state: "hidden" });
    await graphRestore.hover();
    assert.equal(
        await ui
            .locator(".graph-routes")
            .evaluate((e) => getComputedStyle(e).strokeWidth),
        "2px",
    );
    assert.ok(await ui.locator(".route-return[marker-end]").count());
    await ui
        .getByRole("region", { name: "Action details", exact: true })
        .waitFor();
    assert.ok(
        await ui
            .locator(".graph-detail .restoration-node.lucide-rotate-ccw-clock")
            .count(),
    );
    assert.equal(
        await ui.locator(".graph-detail .entry-tools").count(),
        0,
        "Restore cards have no actions.",
    );
    const cardBounds = await ui.locator(".graph-detail").boundingBox(),
        nodeBounds = await graphRestore.boundingBox();
    assert.ok(
        cardBounds.y >= nodeBounds.y + nodeBounds.height + 4 ||
            cardBounds.y + cardBounds.height <= nodeBounds.y - 4,
        "Action card is offset from its node.",
    );
    await ui
        .getByRole("button", { name: "Close action details", exact: true })
        .click();
    const regularNode = ui.locator(".graph-node:not(.graph-restore)").last();
    await regularNode.click();
    await ui
        .locator(".graph-detail")
        .getByLabel("Entry actions", { exact: true })
        .click();
    assert.equal(
        await ui
            .getByRole("button", { name: "Clone from version", exact: true })
            .count(),
        1,
    );
    await ui.getByRole("button", { name: "Highlight", exact: true }).click();
    assert.ok(await ui.locator(".graph-detail .highlight-mark").count());
    assert.ok(await ui.locator(".graph-date-axis time").count());
    assert.equal(
        await ui.locator(".graph-date-divider").count(),
        (await ui.locator(".graph-date-axis time").count()) - 1,
    );
    await ui
        .locator(".graph-detail")
        .getByLabel("Entry actions", { exact: true })
        .click();
    assert.equal(
        await ui
            .locator(".graph-detail .history-menu-panel")
            .evaluate((e) => getComputedStyle(e).position),
        "fixed",
        "Timeline menus escape the card scroll area.",
    );
    const menuBounds = await ui
        .locator(".graph-detail .history-menu-panel")
        .boundingBox();
    assert.ok(
        menuBounds.y >= 0 &&
            menuBounds.y + menuBounds.height <= page.viewportSize().height,
        "Timeline menu stays inside the viewport.",
    );
    const dateTops = await ui
        .locator(".graph-date-axis time")
        .evaluateAll((es) => es.map((e) => e.getBoundingClientRect().top));
    assert.equal(new Set(dateTops).size, 1, "Date labels share a single row.");
    const graphDeepLink = await ui
        .locator(".graph-detail")
        .getByRole("link", { name: "Link to this entry", exact: true })
        .getAttribute("href");
    assert.ok(graphDeepLink.includes("view=timeline"));
    await page.mouse.move(0, 0);
    await page.goto(`${origin}${graphDeepLink}`);
    await ui.locator(".graph-node.graph-selected").waitFor();
    assert.equal(
        await ui.locator(".graph-detail").count(),
        0,
        "Deep links scroll without opening a card.",
    );
    assert.ok(
        await ui.locator(".graph-scroll").evaluate((e) => e.scrollLeft > 0),
        "Linked nodes are brought into view.",
    );
    await ui.locator(".graph-node.graph-selected").click();
    await screenshot("timeline-graph-mobile");
    await page.setViewportSize({ width: 1440, height: 1100 });
    await ui
        .getByRole("button", { name: "Close action details", exact: true })
        .click();
    await ui.locator(".graph-scroll").evaluate((e) => e.scrollTo(0, 0));
    await screenshot("timeline-graph-desktop");
    await ui.locator(".graph-node:not(.graph-restore)").first().click();
    await ui
        .locator(".graph-detail")
        .getByLabel("Entry actions", { exact: true })
        .click();
    await ui
        .getByRole("button", { name: "Restore this version", exact: true })
        .click();
    const beforeRestoreUrl = page.url();
    await ui
        .getByRole("dialog")
        .getByRole("button", { name: "Restore this version", exact: true })
        .click();
    await ui.getByText("Gang restored.", { exact: true }).waitFor();
    assert.equal(
        page.url(),
        beforeRestoreUrl,
        "Timeline restoration stays on the same route and view.",
    );
    assert.equal(await ui.locator(".branch-timeline").count(), 1);
    await ui.getByRole("button", { name: "History", exact: true }).click();
    assert.ok(await ui.locator(".history-timeline").count());
    assert.deepEqual(errors, []);
    console.log(
        "History browser: N26 header/filter layout, owner-only highlights and campaign controls, dated restore/clone navigation, static snapshots, deep links throughout the log, dice form, hidden undo/redo, responsive and dark layouts passed.",
    );
} finally {
    await browser.close();
}
