import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
const baseURL = `http://127.0.0.1:${process.env.EDITOR_PORT || 8765}`;
const snapshot = execFileSync(".venv/bin/python", [
    "-c",
    'import json,server; from django.contrib.flatpages.models import FlatPage; from lab.models import FlatPageOptions; print(json.dumps({"content":FlatPage.objects.get(pk=1).content,"options":list(FlatPageOptions.objects.filter(page_id=1).values())}))',
]).toString();
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_EXECUTABLE ||
        (process.platform === "darwin"
            ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            : undefined),
    headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
mkdirSync("qa", { recursive: true });
async function selectText(editor, text) {
    // Wait for modal focus restoration before asserting a synthetic selection.
    for (let attempt = 0; attempt < 5; attempt++) {
        await editor.evaluate((el, text) => {
            el.focus();
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const start = node.textContent.indexOf(text);
                if (start >= 0) {
                    const selection =
                        el.getRootNode().getSelection?.() ||
                        window.getSelection();
                    selection.setBaseAndExtent(
                        node,
                        start,
                        node,
                        start + text.length,
                    );
                    return;
                }
            }
            throw Error("Anchor text missing");
        }, text);
        await page.waitForTimeout(100);
        if (
            (await editor.evaluate((el) =>
                (
                    el.getRootNode().getSelection?.() || window.getSelection()
                ).toString(),
            )) === text
        )
            return;
    }
    assert.fail("DOM selection must contain the complete anchor");
}
try {
    await page.goto(
        `${baseURL}/enter/${readFileSync(".local-secret", "utf8").trim()}/`,
    );
    const ui = page.locator("#id_content + [data-editor-host]");
    const editor = ui.getByRole("textbox", { name: "Page content" });
    await editor.waitFor();
    await editor.click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("Enter");
    const anchor = `Colour sample ${Date.now()}`;
    await page.keyboard.type(anchor);
    await selectText(editor, anchor);
    await ui.getByRole("button", { name: "Text colour", exact: true }).click();
    const palette = JSON.parse(readFileSync("src/cotton.json", "utf8")).colours;
    assert.deepEqual(
        await ui.locator(".editor-colours button").allTextContents(),
        palette.map((colour) => colour.name),
    );
    assert.equal(
        await ui
            .locator(".editor-colours button")
            .first()
            .evaluate((el) => getComputedStyle(el).justifyContent),
        "flex-start",
    );
    assert.equal(
        await ui
            .locator(".editor-colours button")
            .first()
            .evaluate((el) => getComputedStyle(el).textAlign),
        "left",
    );
    await ui.getByRole("button", { name: "Red", exact: true }).click();
    const redHex = await ui.getByLabel("Custom colour").inputValue();
    const redRGB =
        "rgb(" +
        redHex
            .slice(1)
            .match(/../g)
            .map((channel) => parseInt(channel, 16))
            .join(", ") +
        ")";
    const galleryRed = await ui.getByRole("dialog").evaluate((el) => {
        const canvas = document.createElement("canvas");
        canvas.width = canvas.height = 1;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = getComputedStyle(el)
            .getPropertyValue("--color-red-500")
            .trim();
        ctx.fillRect(0, 0, 1, 1);
        return (
            "#" +
            [...ctx.getImageData(0, 0, 1, 1).data]
                .slice(0, 3)
                .map((channel) => channel.toString(16).padStart(2, "0"))
                .join("")
        );
    });
    assert.equal(
        redHex,
        galleryRed,
        "Red must match the actual N26 gallery shade",
    );
    await ui.getByRole("button", { name: "Apply colour", exact: true }).click();
    assert.equal(
        await editor
            .getByText(anchor, { exact: true })
            .evaluate((el) => getComputedStyle(el).color),
        redRGB,
    );
    await page.locator('[name="_continue"]').click();
    await editor.waitFor();
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    await ui
        .getByLabel("Rendered preview")
        .getByText(anchor, { exact: true })
        .waitFor();
    assert.equal(
        await ui
            .getByLabel("Rendered preview")
            .getByText(anchor, { exact: true })
            .evaluate((el) => getComputedStyle(el).color),
        redRGB,
    );
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    await selectText(editor, anchor);
    await ui.getByRole("button", { name: "Text colour", exact: true }).click();
    await ui.getByLabel("Custom colour").fill("#7e22ce");
    await page.screenshot({ path: "qa/admin-colour-dark.png", fullPage: true });
    await ui.getByRole("button", { name: "Apply colour", exact: true }).click();
    await page.waitForTimeout(150);
    const colourHTML = await page.locator("#id_content").inputValue();
    assert.equal(
        await editor
            .getByText(anchor, { exact: true })
            .evaluate((el) => getComputedStyle(el).color),
        "rgb(126, 34, 206)",
        colourHTML,
    );
    await selectText(editor, anchor);
    await ui.getByRole("button", { name: "Text colour", exact: true }).click();
    await ui
        .getByRole("button", { name: "Default colour", exact: true })
        .click();
    assert.equal(
        await editor.locator("span[style]").filter({ hasText: anchor }).count(),
        0,
    );
    assert.ok(
        (await editor.textContent()).includes(anchor),
        "Resetting colour preserves the text",
    );
    // Neither editor or its Django form exposes the removed feature.
    assert.equal(
        await page
            .getByRole("button", { name: "Add comment", exact: true })
            .count(),
        0,
    );
    assert.equal(
        await page.locator("[name*=editor_notes],[data-notes-input]").count(),
        0,
    );
    assert.equal(await editor.locator("[data-comment-id]").count(), 0);
    await page.setViewportSize({ width: 390, height: 844 });
    await selectText(editor, anchor);
    await ui.getByRole("button", { name: "Text colour", exact: true }).click();
    await page.screenshot({
        path: "qa/admin-colour-mobile.png",
        fullPage: true,
    });
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await ui.getByRole("button", { name: "Cancel", exact: true }).click();
    assert.deepEqual(errors, []);
    console.log(
        "Passed: colour/default/custom formatting, save/reload, mobile dialogs and removal of comment controls.",
    );
} finally {
    await browser.close();
    execFileSync(
        ".venv/bin/python",
        [
            "-c",
            'import json,sys,server; from django.db import transaction; from django.contrib.flatpages.models import FlatPage; from lab.models import FlatPageOptions; s=json.load(sys.stdin);\nwith transaction.atomic():\n FlatPage.objects.filter(pk=1).update(content=s["content"]); FlatPageOptions.objects.filter(page_id=1).delete();\n for row in s["options"]: FlatPageOptions.objects.create(**row)',
        ],
        { input: snapshot },
    );
}
