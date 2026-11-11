import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { chromium } from "playwright";
import { entries, searchEntries } from "./src/database-data.js";
const presentation = JSON.parse(readFileSync("src/presentation.json", "utf8"));
for (const [path, hash] of Object.entries(presentation.provenance))
    assert.equal(
        createHash("sha256").update(readFileSync(path)).digest("hex"),
        hash,
        "Regenerate Database presentation after Cotton changes",
    );
assert.equal(searchEntries("agility").length, 6);
assert(searchEntries("strength").some((e) => e.category === "gear"));
assert(searchEntries("strength").some((e) => e.category === "injuries"));
assert.equal(new Set(entries.map((e) => e.id)).size, entries.length);
mkdirSync("qa", { recursive: true });
const origin = process.env.DATABASE_ORIGIN || "http://127.0.0.1:8772";
const browser = await chromium.launch({
    ...(process.env.CHROME_PATH
        ? { executablePath: process.env.CHROME_PATH }
        : {}),
    headless: true,
});
try {
    const page = await browser.newPage({
        viewport: { width: 1512, height: 1100 },
        reducedMotion: "reduce",
    });
    async function screenshot(options) {
        await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
        await page.screenshot(options);
    }
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    await page.goto(`${origin}/database/`);
    const search = page.getByRole("combobox", { name: "Search database" });
    const browse = page.getByRole("navigation", {
        name: "Database categories",
    });
    await page
        .getByRole("heading", { name: "What are you looking for?" })
        .waitFor();
    assert.equal(await page.locator(".db-results article").count(), 0);
    await screenshot({ path: "qa/database-preview.png", fullPage: false });
    await screenshot({ path: "qa/database-desktop.png", fullPage: true });
    await search.fill("plasma");
    await search.press("Escape");
    assert.equal(await page.locator(".db-results article").count(), 2);
    await search.press("ArrowDown");
    await search.press("Enter");
    assert.match(page.url(), /entry=weapons/);
    await page.goBack();
    assert.equal(await search.inputValue(), "plasma");
    await search.fill("shotgun");
    await search.press("Escape");
    const shotgun = page.locator("article").filter({
        has: page.getByRole("table", { name: "Shotgun weapon profiles" }),
    });
    await shotgun
        .getByRole("rowheader", { name: "Executioner shells" })
        .waitFor();
    assert.equal(await shotgun.locator(".db-nested-profile").count(), 3);
    const rows = await shotgun.getByRole("rowheader").allTextContents();
    assert.equal(rows[0], "Shotgun");
    assert(rows[1].includes("Solid shot"));
    assert.equal(
        await page
            .locator("article.gang-new.callout-frame[data-striped]")
            .count(),
        1,
    );
    await screenshot({ path: "qa/database-weapon.png", fullPage: true });
    await page
        .getByRole("button", { name: "Clear search", exact: true })
        .click();
    await search.press("Escape");
    await browse.getByRole("link", { name: /Skills/ }).click();
    assert.equal(
        await page
            .getByRole("heading", { name: "Skills", exact: true })
            .count(),
        1,
    );
    await page.getByLabel("Filter by set").selectOption("Agility");
    assert.equal(await page.locator(".db-results article").count(), 6);
    const spring = page.locator("article").filter({
        has: page.getByRole("heading", { name: "Spring Up", exact: true }),
    });
    assert.equal(
        await spring
            .getByRole("img", { name: "D6 result 6" })
            .locator(".lucide-dice-6")
            .count(),
        1,
    );
    await spring.getByText("Built into profiles (1)", { exact: true }).click();
    await spring
        .getByRole("button", { name: "Escher Queen", exact: true })
        .click();
    assert.match(page.url(), /category=profiles/);
    await screenshot({ path: "qa/database-models.png", fullPage: true });
    await page
        .locator(".db-selected")
        .getByRole("button", { name: "Spring Up", exact: true })
        .click();
    assert.match(page.url(), /category=skills/);
    await screenshot({ path: "qa/database-skill.png", fullPage: true });
    await browse.getByRole("link", { name: /Injuries/ }).click();
    assert.equal(await page.locator(".db-results article").count(), 6);
    const hobbled = page.locator("article").filter({
        has: page.getByRole("heading", { name: "Hobbled", exact: true }),
    });
    await hobbled
        .getByText("Reduces Movement by 1.", { exact: true })
        .waitFor();
    assert.equal(
        await hobbled
            .getByRole("img", { name: "D66 result 42" })
            .locator("svg")
            .count(),
        2,
    );
    await screenshot({ path: "qa/database-injuries.png", fullPage: true });
    await browse.getByRole("link", { name: /^Gear/ }).click();
    await page.getByText("Improves Save by 1.", { exact: true }).waitFor();
    await search.fill("doesnotexist");
    await search.press("Escape");
    await page.getByRole("heading", { name: "No entries found" }).waitFor();
    await page.getByRole("button", { name: "Clear filters" }).click();
    await page
        .getByRole("heading", { name: "What are you looking for?" })
        .waitFor();
    for (const category of ["profiles", "weapons", "injuries"]) {
        await browse
            .getByRole("link", { name: new RegExp(category, "i") })
            .click();
        for (const width of [320, 390, 768, 1100, 1512]) {
            await page.setViewportSize({ width, height: 1000 });
            assert.equal(
                await page
                    .locator(".db-page")
                    .evaluate((el) => el.scrollWidth > innerWidth),
                false,
                `${category} page overflows at ${width}`,
            );
            const clipped = await page
                .locator("article .gang-card-panel")
                .evaluateAll((nodes) =>
                    nodes.some((el) => el.scrollWidth > el.clientWidth + 1),
                );
            assert.equal(
                clipped,
                false,
                `${category} body overflows at ${width}`,
            );
        }
    }
    await browse.getByRole("link", { name: /Weapons/ }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    const light = await page
        .locator("article .gang-card-panel")
        .first()
        .evaluate((el) => getComputedStyle(el).backgroundColor);
    await screenshot({ path: "qa/database-mobile.png", fullPage: true });
    await page.getByRole("button", { name: "Switch colour theme" }).click();
    const dark = await page
        .locator("article .gang-card-panel")
        .first()
        .evaluate((el) => getComputedStyle(el).backgroundColor);
    assert.notEqual(light, dark);
    await screenshot({
        path: "qa/database-mobile-dark.png",
        fullPage: true,
    });
    await page.setViewportSize({ width: 1512, height: 1100 });
    await screenshot({ path: "qa/database-dark.png", fullPage: true });
    await page.goto(`${origin}/database/?category=powers`);
    await page.reload();
    assert.equal(await page.locator(".db-results article").count(), 6);
    assert.doesNotMatch(
        await page.locator(".db-main").innerText(),
        /__[A-Z_0-9]+__/,
    );
    assert.deepEqual(errors, []);
    console.log(
        "Database: search-first landing, category headings, nested weapon profiles, shared new-style frames, dice faces, injuries, gear modifiers, search, keyboard, relationships, URL navigation, responsive and dark layouts passed.",
    );
} finally {
    await browser.close();
}
