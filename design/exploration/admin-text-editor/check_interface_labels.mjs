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
page=FlatPage.objects.create(url='/help/interface-label-check/',title='Interface label design',content='<p>To keep your changes, choose Save and continue editing.</p><p>Open Settings to adjust the page options, or choose Add link to include a reference.</p>')
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
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
mkdirSync("qa", { recursive: true });
async function selectText(editor, text) {
    await editor.evaluate((el, text) => {
        el.focus();
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const start = node.textContent.indexOf(text);
            if (start !== -1) {
                const selection =
                    el.getRootNode().getSelection?.() || window.getSelection();
                selection.setBaseAndExtent(
                    node,
                    start,
                    node,
                    start + text.length,
                );
                return;
            }
        }
        throw Error("Text to format missing");
    }, text);
    await page.waitForTimeout(100);
}
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
    const scriptURL = await page
        .locator('script[src*="/static/editor.js"]')
        .getAttribute("src");
    assert.match(scriptURL, /editor\.js\?v=\d+/);
    const themeURL = await ui
        .locator('link[rel="stylesheet"]')
        .getAttribute("href");
    assert.match(themeURL, /theme\.css\?v=\d+/);
    const button = ui.getByRole("button", {
        name: "Interface label",
        exact: true,
    });
    assert.equal(await button.locator("svg.lucide-usb-c-port").count(), 1);
    for (const text of ["Save and continue editing", "Settings", "Add link"]) {
        await selectText(editor, text);
        await button.click();
    }
    assert.equal(await editor.locator(".interface-label").count(), 3);
    assert.deepEqual(
        await editor.locator(".interface-label").allTextContents(),
        ["Save and continue editing", "Settings", "Add link"],
    );
    const geometry = await editor
        .locator(".interface-label")
        .first()
        .evaluate((el) => {
            const style = getComputedStyle(el);
            return {
                display: style.display,
                padding: parseFloat(style.paddingInlineStart),
                fontSize: parseFloat(style.fontSize),
                background: style.backgroundColor,
                cursor: style.cursor,
                role: el.getAttribute("role"),
                tabindex: el.getAttribute("tabindex"),
            };
        });
    assert.equal(geometry.display, "inline");
    assert.ok(geometry.padding < 8);
    assert.notEqual(geometry.background, "rgba(0, 0, 0, 0)");
    assert.equal(geometry.cursor, "text");
    assert.equal(geometry.role, null);
    assert.equal(geometry.tabindex, null);
    // Toggling removes only the selected label, and Clear formatting removes it too.
    await selectText(editor, "Settings");
    await button.click();
    assert.equal(await editor.locator(".interface-label").count(), 2);
    await selectText(editor, "Settings");
    await button.click();
    await selectText(editor, "Settings");
    await ui
        .getByRole("button", { name: "Clear formatting", exact: true })
        .click();
    assert.equal(await editor.locator(".interface-label").count(), 2);
    await selectText(editor, "Settings");
    await button.click();
    await page.locator('[name="_continue"]').click();
    await editor.waitFor();
    assert.equal(await editor.locator(".interface-label").count(), 3);
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    const preview = ui.getByLabel("Rendered preview");
    await preview.locator(".interface-label").first().waitFor();
    assert.equal(await preview.locator(".interface-label").count(), 3);
    const previewBackground = await preview
        .locator(".interface-label")
        .first()
        .evaluate((el) => getComputedStyle(el).backgroundColor);
    assert.equal(previewBackground, geometry.background);
    await preview.screenshot({ path: "qa/interface-label-light.png" });
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    const darkBackground = await preview
        .locator(".interface-label")
        .first()
        .evaluate((el) => getComputedStyle(el).backgroundColor);
    assert.notEqual(darkBackground, previewBackground);
    await preview.screenshot({ path: "qa/interface-label-dark.png" });
    await page.setViewportSize({ width: 390, height: 844 });
    await preview.screenshot({ path: "qa/interface-label-mobile.png" });
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await ui.getByRole("button", { name: "HTML", exact: true }).click();
    assert.match(
        await ui.getByLabel("HTML output").textContent(),
        /interface-label/,
    );
    assert.deepEqual(errors, []);
    console.log(
        "Passed: interface label selection/toggle/reset, Cotton inline styling, save/reload, sanitised preview and dark/mobile layout.",
    );
} finally {
    await browser.close();
    execFileSync(".venv/bin/python", [
        "-c",
        "import sys,server; from django.contrib.flatpages.models import FlatPage; FlatPage.objects.filter(pk=sys.argv[1]).delete()",
        testPage,
    ]);
}
