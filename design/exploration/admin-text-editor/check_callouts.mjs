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
page=FlatPage.objects.create(url='/help/callout-check/',title='Callout checks',content='<p>Callout checks.</p>')
page.sites.set(Site.objects.all())
print(page.pk,end='')`,
]).toString();
let uploadToken = null;
const relatedUploadTokens = [];
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_EXECUTABLE ||
        (process.platform === "darwin"
            ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            : undefined),
    headless: true,
});
const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    reducedMotion: "reduce",
    permissions: ["clipboard-read", "clipboard-write"],
});
const page = await context.newPage();
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
    await editor.locator(":scope > p").last().click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("Enter");
    await page.keyboard.type("Before marker After marker");
    for (let i = 0; i < "After marker".length; i++)
        await page.keyboard.press("ArrowLeft");
    await ui
        .getByRole("button", { name: "Insert callout", exact: true })
        .click();
    assert.equal(
        await ui
            .getByRole("button", { name: "Insert callout", exact: true })
            .locator("svg.lucide-square-dashed-top-solid")
            .count(),
        1,
    );
    const names = [
        "Information",
        "Expanding information",
        "FAQ carousel",
        "Download",
        "Related links",
        "Email",
        "Expandable example",
    ];
    for (const name of names)
        assert.equal(
            await ui
                .getByRole("dialog")
                .getByRole("button", { name, exact: true })
                .count(),
            1,
        );
    await ui
        .getByRole("dialog")
        .getByRole("button", { name: "Information", exact: true })
        .click();
    const block = editor.locator('[data-callout-editor="info"]').first();
    await block.waitFor();
    let html = await page.locator("#id_content").inputValue();
    assert.ok(html.indexOf("Before marker") < html.indexOf("data-callout"));
    assert.ok(html.indexOf("data-callout") < html.indexOf("After marker"));
    await block.getByText("Callout settings and text", { exact: true }).click();
    assert.equal(
        await block.evaluate((el) =>
            el.getRootNode().getSelection().toString().includes("Eyebrow text"),
        ),
        false,
    );
    assert.equal(
        await block
            .locator(".callout-input-border")
            .first()
            .evaluate((el) => getComputedStyle(el).borderTopWidth),
        "1px",
    );
    assert.equal(await block.getByLabel("Striped header").isChecked(), false);
    assert.equal(await block.getByLabel("Dark-mode glow").isChecked(), false);
    await block.getByLabel("Dark-mode glow").check();
    for (const label of [
        "Colour",
        "Lucide icon",
        "Label",
        "Eyebrow text",
        "Body text",
    ])
        assert.equal(
            await block
                .getByLabel(label, { exact: true })
                .evaluate((el) => getComputedStyle(el).fontWeight),
            "400",
        );
    await block.getByRole("combobox", { name: "Colour", exact: true }).click();
    assert.equal(
        await block.getByRole("listbox").getByRole("option").count(),
        19,
    );
    await block
        .getByRole("listbox")
        .screenshot({ path: "qa/callout-colours-light.png" });
    const violet = block.getByRole("option", { name: "Violet", exact: true });
    assert.equal(
        await violet.evaluate((el) => getComputedStyle(el).color),
        await violet.evaluate((el) => {
            const probe = document.createElement("span");
            probe.style.color = "var(--color-violet-500)";
            el.appendChild(probe);
            const result = getComputedStyle(probe).color;
            probe.remove();
            return result;
        }),
    );
    await block
        .getByRole("option", { name: "Gyrinx default", exact: true })
        .press("Escape");
    await block
        .getByRole("combobox", { name: "Colour", exact: true })
        .press("ArrowDown");
    await block
        .getByRole("option", { name: "Gyrinx default", exact: true })
        .press("End");
    await block
        .getByRole("option", { name: "Rose", exact: true })
        .press("Escape");
    await block.getByRole("combobox", { name: "Colour", exact: true }).click();
    await block.getByRole("option", { name: "Violet", exact: true }).click();
    await block
        .getByLabel("Lucide icon", { exact: true })
        .selectOption("other");
    await block
        .getByLabel("Lucide icon name", { exact: true })
        .fill("not-an-icon");
    assert.equal(
        await block
            .getByLabel("Lucide icon name", { exact: true })
            .getAttribute("aria-invalid"),
        "true",
    );
    await block.getByLabel("Lucide icon name", { exact: true }).fill("compass");
    assert.equal(await block.locator("svg.lucide-compass").count(), 1);
    await block.getByLabel("Label", { exact: true }).fill("Design note");
    await block
        .getByLabel("Eyebrow text", { exact: true })
        .fill("Important context");
    await block
        .getByLabel("Body text", { exact: true })
        .fill("First callout paragraph.\n\nSecond callout paragraph.");
    await block.getByLabel("Striped header").uncheck();
    const body = block.getByRole("textbox", { name: "Body text", exact: true });
    await body.click();
    await page.keyboard.press("ControlOrMeta+A");
    for (const name of ["Bold", "Italic", "Underline"])
        await block
            .getByRole("toolbar", { name: "Body text formatting", exact: true })
            .getByRole("button", { name, exact: true })
            .click();
    assert.equal(
        (await body
            .locator(
                "strong em u, strong u em, em strong u, u strong em, em u strong, u em strong",
            )
            .count()) > 0,
        true,
    );
    assert.ok(
        (await page.locator("#id_content").inputValue()).includes(
            "Before marker",
        ),
    );
    assert.equal(
        await body.evaluate((el) => el.editor.view.root === el.getRootNode()),
        true,
    );
    // Clicking formatted text should collapse the selection inside this body.
    await body.locator("p").last().click();
    assert.notEqual(
        await body.evaluate((el) => el.editor.state.selection.toJSON().type),
        "all",
    );
    await body.scrollIntoViewIfNeeded();
    const lineBox = await body.locator("p").last().boundingBox();
    await page.mouse.move(lineBox.x + 3, lineBox.y + lineBox.height / 2);
    await page.mouse.down();
    await page.mouse.move(lineBox.x + 110, lineBox.y + lineBox.height / 2, {
        steps: 8,
    });
    await page.mouse.up();
    await page.waitForTimeout(100);
    const selectedText = await body.evaluate((el) => ({
        from: el.editor.state.selection.from,
        to: el.editor.state.selection.to,
    }));
    assert.ok(
        selectedText.to > selectedText.from,
        "Dragging must select a text range",
    );
    // Select All followed by an arrow must also preserve the body and its caret.
    await page.keyboard.press("ControlOrMeta+A");
    await body.focus();
    await body.evaluate(
        () =>
            new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)),
            ),
    );
    await page.keyboard.press("ArrowRight");
    await page.keyboard.type(" Typing check.");
    assert.match(
        await body.innerText(),
        /Second callout paragraph\. Typing check\.$/,
    );
    for (let i = 0; i < " Typing check.".length; i++)
        await page.keyboard.press("Backspace");
    await page.screenshot({ path: "qa/callout-settings.png", fullPage: true });
    await block
        .getByRole("button", { name: "Copy callout", exact: true })
        .click();
    await block
        .getByRole("status")
        .getByText("Callout copied. Paste it into the editor.", { exact: true })
        .waitFor();
    const clipboard = await page.evaluate(async () => {
        const items = await navigator.clipboard.read();
        return items[0].getType("text/html").then((blob) => blob.text());
    });
    assert.match(clipboard, /data-callout/);
    assert.match(clipboard, /Design note/);
    await editor.locator(":scope > p").last().click();
    await page.keyboard.press("ControlOrMeta+End");
    await page.keyboard.press("ControlOrMeta+V");
    await page.waitForTimeout(200);
    if ((await editor.locator('[data-callout-editor="info"]').count()) === 1)
        await page.keyboard.press("Control+V");
    await page.waitForTimeout(200);
    if ((await editor.locator('[data-callout-editor="info"]').count()) === 1) {
        // Headless Chrome may not dispatch the OS paste shortcut. Use the actual
        // browser clipboard payload through the editor's standard paste event.
        const plain = await page.evaluate(() => navigator.clipboard.readText());
        await editor.evaluate(
            (el, payload) => {
                const data = new DataTransfer();
                data.setData("text/html", payload.html);
                data.setData("text/plain", payload.text);
                el.dispatchEvent(
                    new ClipboardEvent("paste", {
                        clipboardData: data,
                        bubbles: true,
                        cancelable: true,
                        composed: true,
                    }),
                );
            },
            { html: clipboard, text: plain },
        );
    }
    await editor.locator('[data-callout-editor="info"]').nth(1).waitFor();
    for (const name of names.slice(1)) {
        await editor.locator(":scope > p").last().click();
        await page.keyboard.press("ControlOrMeta+End");
        await ui
            .getByRole("button", { name: "Insert callout", exact: true })
            .click();
        await ui
            .getByRole("dialog")
            .getByRole("button", { name, exact: true })
            .click();
    }
    // Exercise the last callout at the end of the document, with no trailing paragraph.
    await editor.evaluate((el) => {
        let end = 0;
        const instance = el.editor;
        instance.state.doc.forEach((node, pos) => {
            if (node.type.name === "callout") end = pos + node.nodeSize;
        });
        instance.commands.deleteRange({
            from: end,
            to: instance.state.doc.content.size,
        });
    });
    // Each authoring block offers a reliable paragraph insertion point.
    for (const kind of [
        "info",
        "expanding-info",
        "carousel",
        "download",
        "link-cluster",
        "mail-link",
        "example",
    ]) {
        const item = editor.locator(`[data-callout-editor="${kind}"]`).first();
        const count = await editor.locator(":scope > p").count();
        await item
            .getByRole("button", {
                name: "Add paragraph below callout",
                exact: true,
            })
            .click();
        assert.equal(await editor.locator(":scope > p").count(), count + 1);
        assert.equal(
            await item.evaluate(
                (el) => el.parentElement.nextElementSibling?.tagName,
            ),
            "P",
        );
        const selected = await editor.evaluate((el) => {
            const state = el.editor.state;
            return {
                type: state.selection.$from.parent.type.name,
                text: state.selection.$from.parent.textContent,
                empty: state.selection.empty,
                marks: state.storedMarks?.length || 0,
            };
        });
        assert.deepEqual(selected, {
            type: "paragraph",
            text: "",
            empty: true,
            marks: 0,
        });
        await page.keyboard.type(`Paragraph after ${kind}.`);
        assert.equal(
            await item.evaluate(
                (el) => el.parentElement.nextElementSibling?.textContent,
            ),
            `Paragraph after ${kind}.`,
        );
        // Include keyboard activation, repeated clicks, and insertion before an existing paragraph.
        if (kind === "example") {
            await item
                .getByRole("button", {
                    name: "Add paragraph below callout",
                    exact: true,
                })
                .focus();
            await page.keyboard.press("Enter");
            assert.equal(await editor.locator(":scope > p").count(), count + 2);
            assert.equal(
                await item.evaluate(
                    (el) => el.parentElement.nextElementSibling?.textContent,
                ),
                "",
            );
        }
    }
    const expanding = editor.locator('[data-callout-editor="expanding-info"]');
    await expanding
        .getByText("Callout settings and text", { exact: true })
        .click();
    assert.equal(
        await expanding.locator("svg.lucide-arrow-down-wide-narrow").count(),
        1,
    );
    await expanding.getByLabel("Striped header").check();
    await expanding
        .getByLabel("Body text", { exact: true })
        .fill("Collapsed summary.");
    await expanding
        .getByLabel("Expanded body text", { exact: true })
        .fill("Additional detail revealed.");
    const detail = expanding.getByRole("textbox", {
        name: "Expanded body text",
        exact: true,
    });
    await detail.click();
    await page.keyboard.press("ControlOrMeta+A");
    await expanding
        .getByRole("toolbar", {
            name: "Expanded body text formatting",
            exact: true,
        })
        .getByRole("button", { name: "Bulleted list", exact: true })
        .click();
    assert.equal(await detail.locator("ul").count(), 1);
    const download = editor.locator('[data-callout-editor="download"]');
    await download
        .getByText("Callout settings and text", { exact: true })
        .click();
    await download
        .getByLabel("Upload download file", { exact: true })
        .setInputFiles({
            name: "callout-test-notes.txt",
            mimeType: "text/plain",
            buffer: Buffer.from("Download callout test content"),
        });
    await download
        .getByRole("status")
        .getByText(/callout-test-notes.txt uploaded/)
        .waitFor();
    const uploaded = await download
        .getByLabel("Download address", { exact: true })
        .inputValue();
    assert.match(uploaded, /\/uploads\//);
    uploadToken = new URL(uploaded).pathname.split("/")[2];
    const downloadResponse = await context.request.get(uploaded);
    assert.equal(
        await downloadResponse.text(),
        "Download callout test content",
    );
    const links = editor.locator('[data-callout-editor="link-cluster"]');
    await links.getByText("Callout settings and text", { exact: true }).click();
    await links
        .getByLabel("Link address", { exact: true })
        .fill("https://gyrinx.app/help/n26/handbook/");
    await links.getByRole("button", { name: "Add link", exact: true }).click();
    const attachment = links.locator("fieldset").nth(1);
    await attachment
        .getByLabel("Link text", { exact: true })
        .fill("Campaign reference file");
    await attachment
        .getByLabel("Upload file for this link", { exact: true })
        .setInputFiles({
            name: "unsupported.exe",
            mimeType: "application/octet-stream",
            buffer: Buffer.from("unsupported"),
        });
    await attachment
        .getByRole("alert")
        .getByText("That file type is not supported.", { exact: true })
        .waitFor();
    assert.equal(
        await attachment
            .getByLabel("Link address", { exact: true })
            .inputValue(),
        "",
    );
    await attachment
        .getByLabel("Upload file for this link", { exact: true })
        .setInputFiles({
            name: "related-notes.txt",
            mimeType: "text/plain",
            buffer: Buffer.from("Related link upload content"),
        });
    await attachment
        .getByRole("status")
        .getByText(/related-notes.txt uploaded/)
        .waitFor();
    const relatedFile = await attachment
        .getByLabel("Link address", { exact: true })
        .inputValue();
    assert.match(relatedFile, /\/uploads\//);
    relatedUploadTokens.push(new URL(relatedFile).pathname.split("/")[2]);
    assert.equal(
        await attachment.getByLabel("Link text", { exact: true }).inputValue(),
        "Campaign reference file",
    );
    assert.equal(
        await (await context.request.get(relatedFile)).text(),
        "Related link upload content",
    );
    await links.screenshot({ path: "qa/callout-related-upload.png" });

    // A removed link's pending upload must never update a surviving link.
    await page.waitForTimeout(650);
    await links.getByRole("button", { name: "Add link", exact: true }).click();
    const pendingLink = links.locator("fieldset").nth(2);
    let releaseUpload, uploadStarted;
    const uploadGate = new Promise((resolve) => (releaseUpload = resolve));
    const uploadArrival = new Promise((resolve) => (uploadStarted = resolve));
    await page.route("**/tinymce/upload/", async (route) => {
        uploadStarted();
        await uploadGate;
        await route
            .fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify({
                    location: "https://example.com/obsolete-upload.txt",
                    filename: "obsolete-upload.txt",
                }),
            })
            .catch(() => {});
    });
    await pendingLink
        .getByLabel("Upload file for this link", { exact: true })
        .setInputFiles({
            name: "obsolete-upload.txt",
            mimeType: "text/plain",
            buffer: Buffer.from("Cancelled upload"),
        });
    await uploadArrival;
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(await links.locator("fieldset").count(), 2);
    releaseUpload();
    await page.waitForTimeout(150);
    await page.unroute("**/tinymce/upload/");
    assert.equal(
        await attachment
            .getByLabel("Link address", { exact: true })
            .inputValue(),
        relatedFile,
    );
    assert.equal(
        await links
            .getByRole("button", { name: "Add link", exact: true })
            .isEnabled(),
        true,
    );

    const email = editor.locator('[data-callout-editor="mail-link"]');
    await email.getByText("Callout settings and text", { exact: true }).click();
    await email
        .getByLabel("Email recipient", { exact: true })
        .fill("author@example.com");
    const faq = editor.locator('[data-callout-editor="carousel"]');
    await faq.getByText("Callout settings and text", { exact: true }).click();
    await faq.getByRole("button", { name: "Add card", exact: true }).click();
    await faq
        .getByLabel("Card body text", { exact: true })
        .fill("Temporary fifth card.");
    await faq.getByRole("button", { name: "Remove card", exact: true }).click();
    assert.equal(
        await faq.getByLabel("Card", { exact: true }).locator("option").count(),
        4,
    );
    await faq.getByRole("button", { name: "Add card", exact: true }).click();
    await faq
        .getByLabel("Card body text", { exact: true })
        .fill("Fifth FAQ card.");
    const cardBody = faq.getByRole("textbox", {
        name: "Card body text",
        exact: true,
    });
    await cardBody.click();
    await page.keyboard.press("ControlOrMeta+A");
    await faq
        .getByRole("toolbar", {
            name: "Card body text formatting",
            exact: true,
        })
        .getByRole("button", { name: "Numbered list", exact: true })
        .click();
    assert.equal(await cardBody.locator("ol").count(), 1);
    await page.waitForTimeout(650); // Separate the added card from the prior typing history.
    // Regression: Undo can remove the selected final card without changing the local card index.
    await faq.getByRole("button", { name: "Add card", exact: true }).click();
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(
        await faq.getByLabel("Card", { exact: true }).inputValue(),
        "4",
    );
    await faq
        .getByLabel("Card eyebrow", { exact: true })
        .fill("Undo recovered card");
    const draftConfigs = await page.locator("#id_content").evaluate((el) => {
        const template = document.createElement("template");
        template.innerHTML = el.value;
        return [...template.content.querySelectorAll("[data-callout]")].map(
            (el) => JSON.parse(el.getAttribute("data-callout")),
        );
    });
    assert.equal(
        draftConfigs.find((c) => c.type === "carousel").slides[4].eyebrow,
        "Undo recovered card",
    );
    assert.equal(
        await faq
            .getByRole("textbox", { name: "Card body text", exact: true })
            .locator("ol")
            .count(),
        1,
    );
    // Labels must target a single control, rather than containing an entire menu.
    assert.equal(await editor.locator("label button").count(), 0);
    await block
        .locator("label")
        .filter({ hasText: /^Label$/ })
        .click();
    assert.equal(
        await block
            .getByLabel("Label", { exact: true })
            .evaluate((el) => el.getRootNode().activeElement === el),
        true,
    );
    await faq.screenshot({ path: "qa/callout-carousel-settings.png" });
    await page.locator('[name="_continue"]').click();
    await editor.waitFor();
    assert.equal(await editor.locator("[data-callout-editor]").count(), 8);
    const configs = await page.locator("#id_content").evaluate((el) => {
        const template = document.createElement("template");
        template.innerHTML = el.value;
        return [...template.content.querySelectorAll("[data-callout]")].map(
            (el) => JSON.parse(el.getAttribute("data-callout")),
        );
    });
    assert.equal(Object.hasOwn(configs[0], "slides"), false);
    assert.equal(Object.hasOwn(configs[0], "links"), false);
    assert.equal(
        Object.hasOwn(
            configs.find((c) => c.type === "carousel"),
            "detail",
        ),
        false,
    );
    assert.deepEqual(configs[0], configs[1]);
    assert.equal(configs[0].glow, true);
    assert.equal(configs.find((c) => c.type === "carousel").glow, false);
    assert.equal(configs.find((c) => c.type === "carousel").slides.length, 5);
    assert.equal(configs[0].icon, "compass");
    for (const config of configs.slice(2))
        assert.equal(config.colour, "default");
    await block.getByText("Callout settings and text", { exact: true }).click();
    assert.equal(
        await block.getByLabel("Lucide icon", { exact: true }).inputValue(),
        "other",
    );
    assert.equal(
        await block
            .getByLabel("Lucide icon name", { exact: true })
            .inputValue(),
        "compass",
    );
    await ui.getByRole("button", { name: "HTML", exact: true }).click();
    assert.match(await ui.getByLabel("HTML output").textContent(), /\n  <p>/);
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    const preview = ui.getByLabel("Rendered preview");
    await preview.locator(".callout-card").first().waitFor();
    assert.equal(
        await preview
            .getByRole("button", { name: "Copy callout", exact: true })
            .count(),
        0,
    );
    assert.equal(
        await preview
            .getByRole("button", {
                name: "Add paragraph below callout",
                exact: true,
            })
            .count(),
        0,
    );
    assert.equal(
        await preview
            .getByText("Callout settings and text", { exact: true })
            .count(),
        0,
    );
    const info = preview
        .locator('.callout-card[data-card-type="info"]')
        .first();
    assert.equal(
        await info.locator(".callout-card__label").textContent(),
        "Design note",
    );
    assert.equal(await info.getAttribute("data-striped"), null);
    assert.equal(await info.locator("svg.lucide-compass").count(), 1);
    assert.equal(
        await info.evaluate((el) => getComputedStyle(el).fontFamily),
        await preview.evaluate((el) => getComputedStyle(el).fontFamily),
    );
    assert.equal(
        await info.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--theme").trim(),
        ),
        await preview.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--color-violet-500").trim(),
        ),
    );
    assert.equal(
        await info.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--glow").trim(),
        ),
        "transparent",
    );
    const exp = preview.locator(
        '.callout-card[data-card-type="expanding-info"]',
    );
    assert.equal(await exp.getAttribute("data-striped"), "");
    assert.equal(
        await exp.locator("svg.lucide-arrow-down-wide-narrow").count(),
        1,
    );
    assert.equal(
        await exp.evaluate((el) => getComputedStyle(el).borderTopColor),
        await exp.evaluate((el) => {
            const probe = document.createElement("span");
            probe.style.color = "var(--color-box-border)";
            el.appendChild(probe);
            const colour = getComputedStyle(probe).color;
            probe.remove();
            return colour;
        }),
    );
    assert.equal(
        await exp
            .getByText("Additional detail revealed.", { exact: true })
            .count(),
        0,
    );
    await exp.getByRole("button", { name: "Expand", exact: true }).click();
    await exp
        .getByText("Additional detail revealed.", { exact: true })
        .waitFor();
    assert.equal(await exp.locator(".disclosure__detail ul").count(), 1);
    await exp.getByRole("button", { name: "Collapse", exact: true }).click();
    const example = preview.locator('.callout-card[data-card-type="example"]');
    assert.equal(await example.locator("svg.lucide-lighthouse").count(), 1);
    await example
        .getByRole("button", { name: "Show me an example", exact: true })
        .click();
    await example.getByText(/Here is a concise worked example/).waitFor();
    const carousel = preview.locator(".callout-carousel");
    const bottomGap = await carousel.evaluate(
        (el) =>
            el.getBoundingClientRect().bottom -
            el.querySelector(".callout-card").getBoundingClientRect().bottom,
    );
    assert.ok(
        Math.abs(bottomGap) < 2,
        `Carousel has extra space below its card: ${bottomGap}`,
    );
    await carousel
        .getByRole("button", { name: "Show card 5", exact: true })
        .click();
    await page.waitForTimeout(150);
    assert.equal(
        await carousel
            .getByRole("button", { name: "Show card 5", exact: true })
            .getAttribute("aria-current"),
        "true",
    );
    assert.equal(
        await carousel.locator('[aria-label="Next card"]').isDisabled(),
        true,
    );
    assert.equal(
        await carousel.locator(".callout-card").nth(4).locator("ol").count(),
        1,
    );
    assert.equal(
        await preview.locator("a[download]").getAttribute("href"),
        uploaded,
    );
    assert.equal(
        await preview
            .getByRole("link", { name: "Campaign reference file", exact: true })
            .getAttribute("href"),
        relatedFile,
    );
    assert.equal((await info.locator("strong").count()) > 0, true);
    assert.equal((await info.locator("em").count()) > 0, true);
    assert.equal((await info.locator("u").count()) > 0, true);
    const widths = await preview.evaluate((el) => [
        el.querySelector('[data-card-type="info"]').getBoundingClientRect()
            .width,
        el.querySelector('[data-card-type="carousel"]').getBoundingClientRect()
            .width,
    ]);
    assert.ok(
        Math.abs(widths[0] - widths[1]) < 2,
        `Callout widths differ: ${widths}`,
    );
    assert.match(
        await preview.locator('a[href^="mailto:"]').getAttribute("href"),
        /author@example.com/,
    );
    await page.evaluate(() => document.fonts.ready);
    await carousel
        .getByRole("button", { name: "Show card 5", exact: true })
        .click();
    await page.waitForTimeout(150);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(200);
    assert.equal(
        await carousel
            .getByRole("button", { name: "Show card 5", exact: true })
            .getAttribute("aria-current"),
        "true",
    );
    await carousel
        .getByRole("button", { name: "Show card 1", exact: true })
        .click();
    await page.waitForTimeout(150);
    await page.screenshot({ path: "qa/callout-mobile.png", fullPage: true });
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.waitForTimeout(200);
    await carousel
        .getByRole("button", { name: "Show card 1", exact: true })
        .click();
    await page.waitForTimeout(150);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: "qa/callout-preview.png", fullPage: true });
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(
        await exp.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--glow").trim(),
        ),
        "transparent",
    );
    assert.notEqual(
        await info.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--glow").trim(),
        ),
        "transparent",
    );
    assert.equal(
        await carousel.evaluate((el) =>
            getComputedStyle(el).getPropertyValue("--glow").trim(),
        ),
        "transparent",
    );
    assert.equal(
        await exp
            .locator(".callout-card__label")
            .evaluate((el) => getComputedStyle(el).color),
        await exp.evaluate((el) => {
            const probe = document.createElement("span");
            probe.style.color = "var(--color-ink-200)";
            el.appendChild(probe);
            const colour = getComputedStyle(probe).color;
            probe.remove();
            return colour;
        }),
    );
    await page.screenshot({
        path: "qa/callout-preview-dark.png",
        fullPage: true,
    });
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    const glowBlock = editor.locator('[data-callout-editor="info"]').first();
    if ((await glowBlock.locator("details").getAttribute("open")) === null)
        await glowBlock
            .getByText("Callout settings and text", { exact: true })
            .click();
    assert.equal(
        await glowBlock.getByLabel("Dark-mode glow").isChecked(),
        true,
    );
    await glowBlock.getByLabel("Dark-mode glow").uncheck();
    assert.equal(
        await glowBlock
            .locator(".callout-card")
            .evaluate((el) =>
                getComputedStyle(el).getPropertyValue("--glow").trim(),
            ),
        "transparent",
    );
    await glowBlock
        .getByRole("combobox", { name: "Colour", exact: true })
        .click();
    await glowBlock
        .getByRole("listbox")
        .screenshot({ path: "qa/callout-colours-dark.png" });
    await glowBlock
        .getByRole("option", { name: "Violet", exact: true })
        .press("Escape");
    await editor
        .locator('[data-callout-editor="info"]')
        .first()
        .getByRole("button", { name: "Delete callout", exact: true })
        .click();
    assert.equal(await editor.locator("[data-callout-editor]").count(), 7);
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.equal(await editor.locator("[data-callout-editor]").count(), 8);
    assert.deepEqual(errors, []);
    console.log(
        "Passed: all seven callout types, cursor insertion, settings, clipboard copy/paste, save/reload, font/theme inheritance, reader interactions, delete/undo and mobile layout.",
    );
} finally {
    await browser.close();
    execFileSync(".venv/bin/python", [
        "-c",
        "import sys,server; from django.contrib.flatpages.models import FlatPage; FlatPage.objects.filter(pk=sys.argv[1]).delete()",
        testPage,
    ]);
    for (const token of relatedUploadTokens)
        if (/^[a-f0-9]{32}$/.test(token))
            execFileSync(".venv/bin/python", [
                "-c",
                "import sys,shutil,server; shutil.rmtree(server.UPLOAD_ROOT / sys.argv[1])",
                token,
            ]);
    if (uploadToken && /^[a-f0-9]{32}$/.test(uploadToken))
        execFileSync(".venv/bin/python", [
            "-c",
            "import sys,shutil,server; shutil.rmtree(server.UPLOAD_ROOT / sys.argv[1])",
            uploadToken,
        ]);
}
