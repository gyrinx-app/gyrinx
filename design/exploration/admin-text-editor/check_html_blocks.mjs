import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
const baseURL = `http://127.0.0.1:${process.env.EDITOR_PORT || 8765}`;
const testPage = execFileSync(".venv/bin/python", [
    "-c",
    `import server
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
page=FlatPage.objects.create(url='/help/html-block-check/',title='HTML block checks',content='<p>Before marker After marker</p>')
page.sites.set(Site.objects.all())
print(page.pk,end='')`,
]).toString();
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_EXECUTABLE ||
        (process.platform === "darwin"
            ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            : undefined),
    headless: true,
});
const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    permissions: ["clipboard-read", "clipboard-write"],
});
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
mkdirSync("qa", { recursive: true });
try {
    await page.goto(
        `${baseURL}/enter/${readFileSync(".local-secret", "utf8").trim()}/`,
    );
    await page.goto(`${baseURL}/admin/flatpages/flatpage/${testPage}/change/`);
    const ui = page.locator("#id_content + [data-editor-host]");
    const editor = ui.getByRole("textbox", {
        name: "Page content",
        exact: true,
    });
    await editor.waitFor();
    await editor.evaluate((el) => {
        el.focus();
        const text = el.querySelector("p").firstChild;
        const offset = text.textContent.indexOf("After marker");
        const selection =
            el.getRootNode().getSelection?.() || window.getSelection();
        selection.setBaseAndExtent(text, offset, text, offset);
    });
    await page.waitForTimeout(100);
    const insert = ui.getByRole("button", {
        name: "Insert HTML block",
        exact: true,
    });
    assert.equal(await insert.locator("svg.lucide-square-code").count(), 1);
    await insert.click();
    const block = editor.locator("[data-html-block-editor]");
    await block.waitFor();
    assert.match(
        await block.evaluate(
            (el) => el.parentElement.previousElementSibling.textContent,
        ),
        /^Before marker $/,
    );
    assert.equal(
        await editor.locator(":scope > p").last().textContent(),
        "After marker",
    );
    const source =
        '<section>\n  <h2>Handmade HTML</h2>\n  <p>Some <strong>bold text</strong> &amp; a link to <a href="https://gyrinx.app/">Gyrinx</a>.</p>\n</section>\n<script>window.htmlBlockExecuted=true</script>\n<img src="invalid" onerror="window.htmlBlockExecuted=true">';
    await block
        .getByRole("textbox", { name: "HTML code", exact: true })
        .fill(source);
    assert.equal(
        await page.evaluate(() => window.htmlBlockExecuted),
        undefined,
    );
    const margin = await block.evaluate(
        (el) => getComputedStyle(el).marginBlockStart,
    );
    assert.equal(margin, "24px");
    await block
        .getByRole("button", {
            name: "Add paragraph below HTML block",
            exact: true,
        })
        .click();
    assert.equal(
        await block.evaluate(
            (el) => el.parentElement.nextElementSibling.tagName,
        ),
        "P",
    );
    assert.equal(
        await block.evaluate(
            (el) => el.parentElement.nextElementSibling.textContent,
        ),
        "",
    );
    await page.keyboard.type("Paragraph below HTML.");
    assert.equal(
        await block.evaluate(
            (el) => el.parentElement.nextElementSibling.textContent,
        ),
        "Paragraph below HTML.",
    );
    assert.equal(
        await block
            .getByRole("textbox", { name: "HTML code", exact: true })
            .inputValue(),
        source,
    );
    await block.screenshot({ path: "qa/html-block-edit.png" });
    await page.locator('[name="_continue"]').click();
    await block.waitFor();
    assert.equal(
        await block
            .getByRole("textbox", { name: "HTML code", exact: true })
            .inputValue(),
        source,
    );
    const stored = await page.locator("#id_content").inputValue();
    assert.match(stored, /data-html-block=/);
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    const preview = ui.getByLabel("Rendered preview");
    const rendered = preview.locator(".html-block-preview");
    await rendered
        .getByRole("heading", { name: "Handmade HTML", exact: true })
        .waitFor();
    assert.equal(
        (await preview.locator(":scope > p").first().textContent()).trim(),
        "Before marker",
    );
    assert.equal(
        await preview.locator(":scope > p").last().textContent(),
        "After marker",
    );
    assert.equal(await rendered.locator("strong").textContent(), "bold text");
    assert.equal(
        await rendered
            .getByRole("link", { name: "Gyrinx", exact: true })
            .getAttribute("href"),
        "https://gyrinx.app/",
    );
    assert.equal(await rendered.locator("script,[onerror]").count(), 0);
    assert.equal(
        await page.evaluate(() => window.htmlBlockExecuted),
        undefined,
    );
    assert.equal(
        await preview
            .getByRole("button", {
                name: "Add paragraph below HTML block",
                exact: true,
            })
            .count(),
        0,
    );
    await preview.screenshot({ path: "qa/html-block-preview.png" });
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    const colours = await block
        .getByRole("textbox", { name: "HTML code", exact: true })
        .evaluate((el) => ({
            text: getComputedStyle(el).color,
            background: getComputedStyle(el).backgroundColor,
        }));
    assert.notEqual(colours.text, colours.background);
    await block.screenshot({ path: "qa/html-block-dark.png" });
    await page.setViewportSize({ width: 390, height: 844 });
    await block.screenshot({ path: "qa/html-block-mobile.png" });
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await block
        .getByRole("button", { name: "Delete HTML block", exact: true })
        .click();
    assert.equal(await block.count(), 0);
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    await block.waitFor();
    assert.equal(
        await block
            .getByRole("textbox", { name: "HTML code", exact: true })
            .inputValue(),
        source,
    );
    // Copy both portable HTML and a plain-text fallback, preserving the entire source.
    await block
        .getByRole("button", { name: "Copy HTML block", exact: true })
        .click();
    await block
        .getByRole("status")
        .getByText("HTML block copied. Paste it into the editor.", {
            exact: true,
        })
        .waitFor();
    const clipboard = await page.evaluate(async () => {
        const items = await navigator.clipboard.read();
        const result = {};
        for (const item of items)
            for (const type of item.types)
                result[type] = await (await item.getType(type)).text();
        return result;
    });
    assert.equal(
        JSON.parse(clipboard["text/plain"].slice("Gyrinx HTML block\n".length)),
        source,
    );
    assert.ok(clipboard["text/html"].includes("data-html-block="));
    await block.screenshot({ path: "qa/html-block-copy.png" });
    await editor.locator(":scope > p").last().click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("ControlOrMeta+V");
    if ((await block.count()) === 1)
        await editor.evaluate((el, html) => {
            const data = new DataTransfer();
            data.setData("text/html", html);
            el.dispatchEvent(
                new ClipboardEvent("paste", {
                    clipboardData: data,
                    bubbles: true,
                    cancelable: true,
                }),
            );
        }, clipboard["text/html"]);
    assert.equal(await block.count(), 2);
    await editor.locator(":scope > p").last().click();
    await page.keyboard.press("ControlOrMeta+End");
    await editor.evaluate((el, text) => {
        const data = new DataTransfer();
        data.setData("text/plain", text);
        el.dispatchEvent(
            new ClipboardEvent("paste", {
                clipboardData: data,
                bubbles: true,
                cancelable: true,
            }),
        );
    }, clipboard["text/plain"]);
    assert.equal(await block.count(), 3);
    for (const field of await block
        .getByRole("textbox", { name: "HTML code", exact: true })
        .all())
        assert.equal(await field.inputValue(), source);
    assert.equal(
        await page.evaluate(() => window.htmlBlockExecuted),
        undefined,
    );
    await page.locator('[name="_continue"]').click();
    await block.first().waitFor();
    assert.equal(await block.count(), 3);
    for (const field of await block
        .getByRole("textbox", { name: "HTML code", exact: true })
        .all())
        assert.equal(await field.inputValue(), source);
    assert.deepEqual(errors, []);
    console.log(
        "Passed: HTML block icon, cursor insertion, source preservation, paragraph divider, save/reload, safe preview, dark/mobile layout, delete/undo and HTML/plain-text copy/paste.",
    );
} finally {
    await browser.close();
    execFileSync(".venv/bin/python", [
        "-c",
        "import sys,server; from django.contrib.flatpages.models import FlatPage; FlatPage.objects.filter(pk=sys.argv[1]).delete()",
        testPage,
    ]);
}
