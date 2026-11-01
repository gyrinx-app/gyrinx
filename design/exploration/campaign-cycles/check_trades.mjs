const origin = process.env.CAMPAIGN_ORIGIN || "http://127.0.0.1:8768";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";
import { defaults } from "./src/campaign-data.js";
import * as T from "./src/trade-model.js";
const sample = () => T.initialiseTrades(defaults());
const s = sample();
assert.equal(s.tradingEnabled, false);
assert.throws(() =>
    T.openTrade(s, "louis", "nightshade", "iron", T.emptyOffer(), ""),
);
s.tradingEnabled = true;
const id = T.openTrade(
    s,
    "louis",
    "nightshade",
    "iron",
    { credits: 50, holdings: ["nightshade-gear-0", "territory-0"] },
    "Meet at the crossing.",
);
assert.equal(s.tradeNotifications[0].owner, "mira");
assert.throws(() => T.actOnTrade(s, id, "tom", "accept"));
assert.throws(() =>
    T.actOnTrade(s, id, "mira", "offer", {
        credits: 0,
        holdings: ["nightshade-gear-0"],
    }),
);
T.actOnTrade(s, id, "mira", "offer", {
    credits: 20,
    holdings: ["iron-resource"],
});
T.actOnTrade(s, id, "louis", "accept");
assert.throws(() => T.actOnTrade(s, id, "mira", "withdraw"));
T.actOnTrade(s, id, "louis", "withdraw");
assert.deepEqual(s.trades[0].accepted, []);
assert.equal(T.availableCredits(s, "nightshade"), 185);
T.actOnTrade(s, id, "louis", "accept");
assert.throws(() => T.actOnTrade(s, id, "louis", "note", "Unagreed terms"));
assert.equal(T.availableCredits(s, "nightshade"), 135);
assert.throws(() => T.actOnTrade(s, id, "mira", "offer", T.emptyOffer()));
assert.throws(() =>
    T.openTrade(
        s,
        "louis",
        "nightshade",
        "sump",
        { credits: 136, holdings: [] },
        "",
    ),
);
assert.throws(() =>
    T.openTrade(
        s,
        "louis",
        "nightshade",
        "sump",
        { credits: 0, holdings: ["nightshade-gear-0"] },
        "",
    ),
);
T.actOnTrade(s, id, "mira", "counter");
assert.deepEqual(s.trades[0].accepted, []);
T.actOnTrade(s, id, "mira", "offer", {
    credits: 30,
    holdings: ["iron-resource"],
});
T.actOnTrade(s, id, "mira", "accept");
T.actOnTrade(s, id, "louis", "accept");
assert.equal(s.trades[0].status, "completed");
assert.equal(s.gangs[0].credits, 165);
assert.equal(s.gangs[1].credits, 140);
assert.equal(s.tradeHoldings.find((h) => h.id === "territory-0").owner, "iron");
assert.equal(
    s.tradeHoldings.find((h) => h.id === "iron-resource").owner,
    "nightshade",
);
assert.throws(() => T.actOnTrade(s, id, "louis", "accept"));
assert.equal(s.trades[0].offers.nightshade.note, "Meet at the crossing.");
assert.equal(s.trades[0].transfers[0].note, "Meet at the crossing.");
assert.equal(s.entries.filter((e) => e.trade === id).length, 2);
assert.ok(s.trades[0].events.length > 2);
assert.throws(() => T.actOnTrade(s, id, "louis", "withdraw"));
const netState = structuredClone(s);
netState.gangs[0].credits = 0;
netState.gangs[1].credits = 20;
T.actOnTrade(netState, id, "louis", "undo-request");
T.actOnTrade(netState, id, "mira", "undo-accept", netState.trades[0].undo.id);
assert.equal(netState.gangs[0].credits, 20);
assert.equal(netState.gangs[1].credits, 0);
const undoState = structuredClone(s),
    undoTrade = undoState.trades[0];
const originalOfferEvent = undoTrade.events.find((e) => e.kind === "opened");
assert.equal(originalOfferEvent.details.credits, 50);
assert.equal(originalOfferEvent.details.holdings[0].name, "Lasgun");
assert.equal(originalOfferEvent.details.note, "Meet at the crossing.");
assert.ok(undoTrade.openedAt);
assert.ok(undoTrade.closedAt);
assert.throws(() => T.actOnTrade(undoState, id, "tom", "undo-request"));
T.actOnTrade(undoState, id, "louis", "undo-request");
assert.equal(undoState.entries[0].tradeEvent, "undo-requested");
assert.equal(undoState.entries[0].trade, id);
assert.ok(T.isCampaignEntry(undoState.entries[0]));
const legacyRequest = structuredClone(undoState);
legacyRequest.entries = legacyRequest.entries.filter(
    (e) => e.tradeEvent !== "undo-requested",
);
delete legacyRequest.trades[0].campaignUndoRequestsVersion;
T.initialiseTrades(legacyRequest);
T.initialiseTrades(legacyRequest);
assert.equal(
    legacyRequest.entries.filter((e) => e.tradeEvent === "undo-requested")
        .length,
    1,
);
assert.equal(undoState.gangs[0].credits, 165);
let request = undoTrade.undo.id;
assert.throws(() =>
    T.actOnTrade(undoState, id, "louis", "undo-accept", request),
);
T.actOnTrade(undoState, id, "mira", "undo-decline", request);
assert.equal(undoTrade.status, "completed");
T.actOnTrade(undoState, id, "louis", "undo-request");
assert.throws(() =>
    T.actOnTrade(undoState, id, "mira", "undo-accept", request),
);
request = undoTrade.undo.id;
T.actOnTrade(undoState, id, "louis", "undo-cancel", request);
T.actOnTrade(undoState, id, "louis", "undo-request");
request = undoTrade.undo.id;
const returnedGear = undoState.tradeHoldings.find(
    (h) => h.id === "nightshade-gear-0",
);
returnedGear.location = "fighter";
returnedGear.assignedTo = "leader";
let before = JSON.stringify(undoState);
assert.throws(() =>
    T.actOnTrade(undoState, id, "mira", "undo-accept", request),
);
assert.equal(JSON.stringify(undoState), before);
returnedGear.location = "stash";
returnedGear.assignedTo = null;
undoState.gangs[1].credits = 0;
before = JSON.stringify(undoState);
assert.throws(() =>
    T.actOnTrade(undoState, id, "mira", "undo-accept", request),
);
assert.equal(JSON.stringify(undoState), before);
undoState.gangs[1].credits = 140;
const reservedTrade = T.openTrade(undoState, "mira", "iron", "sump", {
    credits: 0,
    holdings: ["nightshade-gear-0"],
    note: "",
});
T.actOnTrade(undoState, reservedTrade, "mira", "accept");
before = JSON.stringify(undoState);
assert.throws(() =>
    T.actOnTrade(undoState, id, "mira", "undo-accept", request),
);
assert.equal(JSON.stringify(undoState), before);
T.actOnTrade(undoState, reservedTrade, "tom", "decline");
T.actOnTrade(undoState, id, "mira", "undo-accept", request);
assert.equal(undoTrade.status, "undone");
assert.equal(undoState.gangs[0].credits, 185);
assert.equal(undoState.gangs[1].credits, 120);
assert.equal(returnedGear.owner, "nightshade");
assert.equal(
    undoState.tradeHoldings.find((h) => h.id === "territory-0").owner,
    "nightshade",
);
assert.equal(
    undoState.tradeHoldings.find((h) => h.id === "iron-resource").owner,
    "iron",
);
assert.ok(
    undoState.entries.some((e) => e.trade === id && e.tradeEvent === "undone"),
);
assert.throws(() =>
    T.actOnTrade(undoState, id, "mira", "undo-accept", request),
);
assert.equal(undoTrade.transfers[0].holdings[0].name, "Lasgun");
const declined = T.openTrade(
    s,
    "louis",
    "nightshade",
    "iron",
    T.emptyOffer(),
    "",
);
s.tradingEnabled = false;
T.actOnTrade(s, declined, "mira", "decline");
assert.equal(s.trades[0].status, "declined");
const stash = sample();
stash.tradingEnabled = true;
stash.tradeHoldings.push(
    {
        id: "carried",
        owner: "nightshade",
        name: "Carried boltgun",
        kind: "Equipment",
        location: "fighter",
        assignedTo: "leader",
    },
    {
        id: "assigned",
        owner: "nightshade",
        name: "Assigned armour",
        kind: "Equipment",
        location: "stash",
        assignedTo: "champion",
    },
);
for (const holding of ["carried", "assigned"])
    assert.throws(() =>
        T.openTrade(stash, "louis", "nightshade", "iron", {
            credits: 0,
            holdings: [holding],
            note: "",
        }),
    );
const pending = T.openTrade(
    stash,
    "louis",
    "nightshade",
    "iron",
    T.emptyOffer(),
);
const old = stash.trades[0];
delete old.offerNotesVersion;
old.notes = [
    { actor: "louis", text: "Owes one favour.", at: new Date().toISOString() },
];
old.accepted = ["nightshade"];
T.initialiseTrades(stash);
assert.equal(old.offers.nightshade.note, "Owes one favour.");
assert.deepEqual(old.accepted, []);
assert.ok(
    T.isCampaignEntry({
        trade: pending,
        text: "Nightshade Coven opened a trade with Iron Vultures.",
    }),
);
assert.ok(
    !T.isCampaignEntry({
        trade: pending,
        text: "Nightshade Coven accepted the trade.",
    }),
);
old.status = "completed";
delete old.offerNotesVersion;
old.notes = [{ actor: "mira", text: "An earlier note." }];
T.initialiseTrades(stash);
assert.equal(old.offers.iron.note, "");
assert.equal(old.notes[0].text, "An earlier note.");
console.log(
    "Trade model: permissions, reservations, counter-offers, completion and decline passed.",
);
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
async function screenshot(path, fullPage = true) {
    await page.evaluate(async () => {
        scrollTo({ top: 0, behavior: "instant" });
        await document.fonts.ready;
        const root = document.querySelector("#campaign-root").shadowRoot;
        await Promise.allSettled(
            root
                .getAnimations()
                .filter((a) => a.effect?.getTiming().iterations !== Infinity)
                .map((a) => a.finished),
        );
    });
    await page.screenshot({ path, fullPage });
}
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(`${origin}/campaign/`);
const ui = page.locator("#campaign-root");
const button = (name) => ui.getByRole("button", { name, exact: true });
await ui.locator('summary[aria-label="More actions"]').click();
assert.equal(await button("Trades").isDisabled(), true);
await button("Edit campaign").click();
await ui.getByLabel("Allow trades between campaign gangs").check();
await button("Save").click();
await button("Back to campaign").click();
await ui.locator('summary[aria-label="More actions"]').click();
await button("Trades").click();
await button("Start a trade").click();
await ui.getByLabel("Credits", { exact: true }).fill("50");
await ui.getByLabel("Lasgun", { exact: true }).check();
await ui.getByLabel("Toll Crossing", { exact: true }).check();
await ui
    .getByLabel("Offer note (optional)", { exact: true })
    .fill("Meet at Toll Crossing after the next battle.");
await button("Open trade").click();
await button("Accept").waitFor();
const tradeUrl = page.url();
await ui.getByLabel("Demo account").selectOption("mira");
await ui.locator('summary[aria-label="Notifications"]').click();
await ui
    .getByRole("button", { name: /Unread · Nightshade Coven has begun/ })
    .click();
await button("Edit offer").click();
await ui.getByLabel("Credits", { exact: true }).fill("20");
await ui.getByLabel("Promethium cache", { exact: true }).check();
await ui
    .getByLabel("Offer note (optional)", { exact: true })
    .fill("IOU: one favour at the next battle.");
await button("Save offer").click();
await button("Accept").click();
await button("Cancel acceptance").click();
await button("Save offer").waitFor();
assert.equal(
    await ui.getByLabel("Offer note (optional)", { exact: true }).inputValue(),
    "IOU: one favour at the next battle.",
);
await ui
    .getByLabel("Offer note (optional)", { exact: true })
    .fill("IOU: two favours at the next battle.");
await button("Save offer").click();
await button("Accept").click();
await ui.getByLabel("Demo account").selectOption("louis");
await button("Counter-offer").click();
await button("Save offer").waitFor();
await button("Save offer").click();
await button("Accept").click();
await button("Cancel acceptance").waitFor();
assert.equal(await ui.locator(".tr-offer-accepted").count(), 1);
assert.equal((await ui.innerText()).includes("[object Object]"), false);
await screenshot("qa/trade-preview.png", false);
await screenshot("qa/trade-desktop.png");
await ui.getByLabel("Demo account").selectOption("mira");
await button("Accept").click();
await ui.getByText("Trade completed", { exact: true }).waitFor();
await page.reload();
await ui.getByText("Trade completed", { exact: true }).waitFor();
assert.equal(await button("Accept").count(), 0);
assert.equal(await button("Cancel acceptance").count(), 0);
assert.equal(await ui.locator(".tr-banner.tr-completed").count(), 1);
assert.equal(
    await ui
        .locator(".tr-transfer-summary")
        .getByText("IOU: two favours at the next battle.", { exact: true })
        .count(),
    1,
);
assert.equal(await ui.locator(".tr-offer-accepted").count(), 2);
assert.equal(
    await ui
        .locator(".tr-heading")
        .getByText("Completed", { exact: true })
        .count(),
    1,
);
assert.equal(await ui.locator(".tr-dates time").count(), 2);
assert.match(
    await ui.locator(".tr-events li").first().innerText(),
    /completed their trade/,
);
assert.equal(
    (await ui
        .locator(".tr-event-offer")
        .getByText("Lasgun × 1", { exact: true })
        .count()) > 0,
    true,
);
assert.equal(
    await ui.locator(".tr-transfer-summary .tr-gang-icon img").count(),
    4,
);
await screenshot("qa/trade-completed.png");
await page.setViewportSize({ width: 390, height: 844 });
await screenshot("qa/trade-mobile.png");
assert.equal(
    await ui
        .locator(".tr-workspace")
        .evaluate((el) => el.scrollWidth > el.clientWidth),
    false,
);
await button("Toggle theme").click();
await screenshot("qa/trade-mobile-dark.png");
await button("Back to campaign").click();
await button("Full log").click();
assert.equal((await ui.innerText()).includes("updated their offer"), false);
assert.equal((await ui.innerText()).includes("accepted the trade"), false);
assert.equal(await button("View trade record").count(), 2);
await ui
    .getByRole("button", { name: "View trade record", exact: true })
    .first()
    .click();
await ui.getByText("Trade completed", { exact: true }).waitFor();
await button("Request undo").click();
await button("Back to campaign").click();
await button("Full log").click();
await ui.getByText(/requested an undo\. The other gang must accept/).waitFor();
await button("View trade record").first().click();

await button("Cancel undo request").waitFor();
assert.equal(await button("Accept undo").count(), 0);
await ui.getByLabel("Demo account").selectOption("louis");
await button("Decline undo").click();
await button("Request undo").waitFor();
await button("Request undo").click();
await ui.getByLabel("Demo account").selectOption("mira");
await button("Accept undo").click();
await ui.getByText("Trade undone", { exact: true }).waitFor();
assert.match(
    await ui.locator(".tr-events li").first().innerText(),
    /trade was undone/,
);
assert.equal(await ui.locator(".tr-dates time").count(), 3);
await page.reload();
await ui.getByText("Trade undone", { exact: true }).waitFor();
assert.equal(await button("Request undo").count(), 0);
await screenshot("qa/trade-undone.png");
await page.goto(tradeUrl.replace("account=louis", "account=visitor"));
await ui
    .getByText(
        "Only the owners of these two gangs can interact with the trade.",
    )
    .waitFor();
await page.goto(`${origin}/campaign/?view=trade&account=louis`);
await ui.getByLabel("Trade with").selectOption("sump");
const cawdor = ui.locator(
    '.tr-gang-icon img[src="/static/history/cawdor.svg"]',
);
await cawdor.waitFor();
assert.equal(
    await cawdor.evaluate(async (img) => {
        await img.decode();
        return img.naturalWidth > 0;
    }),
    true,
);
await page.evaluate(() => {
    const key = "gyrinx-campaign-periods-v1";
    const s = JSON.parse(localStorage.getItem(key));
    s.tradeHoldings.push({
        id: "carried-test",
        name: "Carried boltgun",
        owner: "nightshade",
        kind: "Equipment",
        location: "fighter",
        assignedTo: "leader",
    });
    localStorage.setItem(key, JSON.stringify(s));
});
await page.reload();
assert.equal(
    await ui.getByLabel("Carried boltgun", { exact: true }).count(),
    0,
);
assert.deepEqual(errors, []);
await browser.close();
console.log(
    "Trade browser: disabled setting, opening, notification, editing, counter, acceptance, records, responsive and dark layouts passed.",
);
