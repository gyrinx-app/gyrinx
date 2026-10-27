import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import assert from "node:assert/strict";
const baseURL = `http://127.0.0.1:${process.env.EDITOR_PORT || 8765}`;
const original =
    '<h2 id="legacy-anchor" class="legacy-class">TinyMCE compatibility</h2><p>Before callouts.</p><p>After callouts.</p>';
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_EXECUTABLE ||
        (process.platform === "darwin"
            ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            : undefined),
    headless: true,
});
const pk = execFileSync(
    ".venv/bin/python",
    [
        "-c",
        `import sys,server
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
p=FlatPage.objects.create(url='/help/tinymce-check/',title='TinyMCE callout checks',content=sys.stdin.read())
p.sites.set(Site.objects.all())
print(p.pk,end='')`,
    ],
    { input: original },
).toString();
const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
    permissions: ["clipboard-read", "clipboard-write"],
});
const uploadTokens = [];
const errors = [];
page.on("pageerror", (error) => {
    errors.push(error.message);
    console.log("PAGE ERROR", error.message);
});
mkdirSync("qa", { recursive: true });
const url = `${baseURL}/admin/flatpages/flatpage/${pk}/change/?editor=tinymce`;
try {
    await page.goto(
        `${baseURL}/enter/${readFileSync(".local-secret", "utf8").trim()}/`,
    );
    await page.goto(url);
    const ui = page.locator("#id_content + [data-editor-host]");
    const tiny = ui.frameLocator("iframe.tiny-editor-frame");
    await tiny
        .getByRole("button", { name: "Insert callout", exact: true })
        .waitFor({ timeout: 20000 });
    await ui
        .getByRole("status")
        .getByText("Ready to edit", { exact: true })
        .waitFor({ timeout: 30000 });
    const body = tiny
        .frameLocator("iframe.tox-edit-area__iframe")
        .locator("body");
    await body.waitFor();

    const palette = JSON.parse(readFileSync("src/cotton.json", "utf8")).colours;
    const expectedColours = await ui.evaluate((host, palette) => {
        const theme = getComputedStyle(
            host.shadowRoot.querySelector(".gyrinx-editor"),
        );
        const context = document.createElement("canvas").getContext("2d");
        return palette.flatMap(({ name, token }) => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = theme.getPropertyValue(token).trim();
            context.fillRect(0, 0, 1, 1);
            const hex =
                "#" +
                [...context.getImageData(0, 0, 1, 1).data]
                    .slice(0, 3)
                    .map((value) => value.toString(16).padStart(2, "0"))
                    .join("");
            return [hex, name];
        });
    }, palette);
    assert.deepEqual(
        await tiny.locator("#tiny-document").evaluate(() =>
            window.tinymce
                .get("tiny-document")
                .options.get("color_map")
                .flatMap(({ value, text }) => [value.toLowerCase(), text]),
        ),
        expectedColours,
    );

    assert.equal(await body.locator("#legacy-anchor.legacy-class").count(), 1);
    await tiny.locator("#tiny-document").evaluate(() => {
        const editor = window.tinymce.get("tiny-document");
        editor.selection.setCursorLocation(
            editor.getBody(),
            editor.getBody().childNodes.length,
        );
    });
    await tiny
        .getByRole("button", { name: "Insert callout", exact: true })
        .click();
    await tiny
        .getByRole("menuitem", { name: "Information", exact: true })
        .click();
    const dialog = tiny.getByRole("dialog");
    await dialog
        .getByRole("button", { name: "Save callout", exact: true })
        .waitFor();
    await dialog.getByLabel("Label", { exact: true }).fill("Design note");
    await dialog
        .getByLabel("Lucide icon name", { exact: true })
        .fill("compass");
    const rich = dialog.locator("[data-callout-body]");
    await rich.waitFor();
    await rich.fill("Information callout body.");
    await dialog
        .getByRole("button", { name: "Save callout", exact: true })
        .click();
    await body.locator(":scope > aside[data-callout]").waitFor();
    assert.equal(
        await body
            .locator(":scope > aside[data-callout]")
            .getAttribute("contenteditable"),
        "false",
    );
    assert.match(
        await page.locator("#id_content").inputValue(),
        /Information callout body/,
    );

    const information = body.locator(":scope > aside[data-callout]").first();
    await information
        .getByRole("button", { name: "Add paragraph below block", exact: true })
        .click();
    await page.keyboard.type("Paragraph after information.");
    assert.equal(
        await information.evaluate((el) => el.nextElementSibling.textContent),
        "Paragraph after information.",
    );
    await information
        .getByRole("button", { name: "Edit block", exact: true })
        .click();
    await dialog
        .getByLabel("Label", { exact: true })
        .fill("Edited design note");
    const editBody = dialog.locator("[data-callout-body]");
    await editBody.waitFor();
    assert.match(await editBody.textContent(), /Information callout body/);
    await editBody.click();
    await page.keyboard.press("ControlOrMeta+A");
    await dialog.getByRole("button", { name: /^Bold/ }).click();
    await dialog
        .getByRole("button", { name: "Save callout", exact: true })
        .click();
    assert.match(await information.textContent(), /Edited design note/);
    assert.equal(
        await body.locator(":scope > aside[data-callout]").count(),
        1,
        "Editing a callout must replace its block",
    );
    await information
        .getByRole("button", { name: "Copy block", exact: true })
        .click();
    const clip = await tiny.locator("#tiny-document").evaluate(async () => {
        const items = await navigator.clipboard.read();
        const result = {};
        for (const item of items)
            for (const type of item.types)
                result[type] = await (await item.getType(type)).text();
        return result;
    });
    assert.match(clip["text/plain"], /^Gyrinx callout\n/);
    await tiny.locator("#tiny-document").evaluate((el, html) => {
        const editor = window.tinymce.get(el.id);
        editor.selection.setCursorLocation(
            editor.getBody(),
            editor.getBody().childNodes.length,
        );
        editor.insertContent(html);
    }, clip["text/html"]);
    await body
        .locator(":scope > aside[data-callout]")
        .nth(1)
        .getByRole("button", { name: "Copy block", exact: true })
        .waitFor();
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 2);
    await body
        .locator(":scope > aside[data-callout]")
        .nth(1)
        .getByRole("button", { name: "Delete block", exact: true })
        .click();
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 1);
    await tiny.getByRole("button", { name: "Undo", exact: true }).click();
    await body.locator(":scope > aside[data-callout]").nth(1).waitFor();
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 2);
    // Native dialog redial must preserve each card and its rich body independently.
    await tiny.locator("#tiny-document").evaluate((el) => {
        const editor = window.tinymce.get(el.id);
        editor.selection.setCursorLocation(
            editor.getBody(),
            editor.getBody().childNodes.length,
        );
    });
    await tiny
        .getByRole("button", { name: "Insert callout", exact: true })
        .click();
    await tiny
        .getByRole("menuitem", { name: "FAQ carousel", exact: true })
        .click();
    await dialog
        .getByLabel("Label", { exact: true })
        .fill("Frequently asked questions");
    const cardBody = dialog.locator("[data-callout-body]");
    await cardBody.waitFor();
    await cardBody.fill("First FAQ answer.");
    await dialog.getByRole("button", { name: "Add card", exact: true }).click();
    await cardBody.waitFor();
    await cardBody.fill("Fifth FAQ answer.");
    await dialog
        .getByLabel("Card eyebrow", { exact: true })
        .fill("Fifth question");
    await dialog.getByLabel("Card", { exact: true }).selectOption("0");
    await cardBody.waitFor();
    assert.match(await cardBody.textContent(), /First FAQ answer/);
    await dialog.getByLabel("Card", { exact: true }).selectOption("4");
    await cardBody.waitFor();
    assert.match(await cardBody.textContent(), /Fifth FAQ answer/);
    await dialog
        .getByRole("button", { name: "Remove card", exact: true })
        .click();
    assert.equal(
        await dialog
            .getByLabel("Card", { exact: true })
            .locator("option")
            .count(),
        4,
    );
    await dialog.getByRole("button", { name: "Add card", exact: true }).click();
    await cardBody.waitFor();
    await cardBody.fill("Final fifth FAQ answer.");
    await dialog.screenshot({ path: "qa/tinymce-faq-dialog.png" });
    await dialog
        .getByRole("button", { name: "Save callout", exact: true })
        .click();
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 3);
    for (const [kind, title] of [
        ["expanding-info", "Expanding information"],
        ["download", "Download"],
        ["link-cluster", "Related links"],
        ["mail-link", "Email"],
        ["example", "Expandable example"],
    ]) {
        await tiny.locator("#tiny-document").evaluate((el) => {
            const editor = window.tinymce.get(el.id);
            editor.selection.setCursorLocation(
                editor.getBody(),
                editor.getBody().childNodes.length,
            );
        });
        await tiny
            .getByRole("button", { name: "Insert callout", exact: true })
            .click();
        await tiny.getByRole("menuitem", { name: title, exact: true }).click();
        await dialog.locator("[data-callout-body]").first().waitFor();
        await dialog
            .locator("[data-callout-body]")
            .first()
            .fill(`${title} body text.`);
        if (kind === "expanding-info")
            await dialog
                .locator("[data-callout-body]")
                .nth(1)
                .fill("Expanded information detail.");
        if (kind === "download") {
            const [chooser] = await Promise.all([
                page.waitForEvent("filechooser"),
                dialog
                    .getByRole("button", {
                        name: "Download address",
                        exact: true,
                    })
                    .click(),
            ]);
            await chooser.setFiles({
                name: "tiny-native-check.txt",
                mimeType: "text/plain",
                buffer: Buffer.from("TinyMCE callout upload check"),
            });
            const address = await dialog
                .getByRole("combobox", {
                    name: "Download address",
                    exact: true,
                })
                .evaluate(
                    (el) =>
                        new Promise((resolve, reject) => {
                            const deadline = Date.now() + 10000;
                            const timer = setInterval(() => {
                                if (el.value.includes("/uploads/")) {
                                    clearInterval(timer);
                                    resolve(el.value);
                                } else if (Date.now() > deadline) {
                                    clearInterval(timer);
                                    reject(
                                        Error(
                                            "Upload did not fill the download field",
                                        ),
                                    );
                                }
                            }, 50);
                        }),
                );
            uploadTokens.push(new URL(address).pathname.split("/")[2]);
            assert.equal(
                await (await page.context().request.get(address)).text(),
                "TinyMCE callout upload check",
            );
        }
        if (kind === "mail-link")
            await dialog
                .getByLabel("Email recipient", { exact: true })
                .fill("author@example.com");
        if (kind === "link-cluster") {
            await dialog
                .getByLabel("Link text", { exact: true })
                .fill("Handbook reference");
            await dialog
                .getByRole("combobox", { name: "Link address", exact: true })
                .fill("https://gyrinx.app/help/n26/handbook/");
            await dialog
                .getByRole("button", { name: "Add link", exact: true })
                .click();
            await dialog.locator("[data-callout-body]").waitFor();
            await dialog
                .getByLabel("Link text", { exact: true })
                .nth(1)
                .fill("Another reference");
            await dialog
                .getByRole("combobox", { name: "Link address", exact: true })
                .nth(1)
                .fill("https://example.com/reference");
        }
        await dialog
            .getByRole("button", { name: "Save callout", exact: true })
            .click();
        assert.equal(
            await body
                .locator(`:scope > aside[data-callout]`)
                .last()
                .evaluate(
                    (el) => JSON.parse(el.getAttribute("data-callout")).type,
                ),
            kind,
        );
    }
    // HTML-source blocks stay inert during authoring and use the same block controls.
    await tiny.locator("#tiny-document").evaluate((el) => {
        const editor = window.tinymce.get(el.id);
        editor.selection.setCursorLocation(
            editor.getBody(),
            editor.getBody().childNodes.length,
        );
    });
    await tiny
        .getByRole("button", { name: "Insert HTML block", exact: true })
        .click();
    const code =
        "<h3>HTML source heading</h3><p>HTML source body.</p><script>window.tinyUnsafe=true</script>";
    await dialog.getByLabel("HTML code", { exact: true }).fill(code);
    await dialog
        .getByRole("button", { name: "Save HTML block", exact: true })
        .click();
    assert.equal(
        await body.locator(":scope > div[data-html-block]").count(),
        1,
    );
    assert.equal(
        await tiny.locator("#tiny-document").evaluate(() => window.tinyUnsafe),
        undefined,
    );
    // The text-only clipboard fallback restores the same editable callout.
    await tiny.locator("#tiny-document").evaluate((el, text) => {
        const editor = window.tinymce.get(el.id);
        editor.selection.setCursorLocation(
            editor.getBody(),
            editor.getBody().childNodes.length,
        );
        const data = new DataTransfer();
        data.setData("text/plain", text);
        editor.getBody().dispatchEvent(
            new ClipboardEvent("paste", {
                clipboardData: data,
                bubbles: true,
                cancelable: true,
            }),
        );
    }, clip["text/plain"]);
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 9);
    const raw = await page.locator("#id_content").inputValue();
    assert.doesNotMatch(
        raw,
        /data-block-action|contenteditable=|data-mce-gyrinx-rendered/,
    );
    assert.match(raw, /<strong>Information callout body/);
    const configs = await page.locator("#id_content").evaluate((el) => {
        const template = document.createElement("template");
        template.innerHTML = el.value;
        return [
            ...template.content.querySelectorAll("aside[data-callout]"),
        ].map((node) => JSON.parse(node.getAttribute("data-callout")));
    });
    assert.deepEqual(configs[0], configs[1]);
    assert.equal(configs[2].slides.length, 5);
    assert.equal(configs.length, 9);
    assert.deepEqual(configs[0], configs[8]);
    assert.match(configs[2].slides[4].body, /Final fifth FAQ answer/);
    await page.locator('[name="_continue"]').click();
    assert.equal(
        new URL(page.url()).searchParams.get("editor"),
        "tinymce",
        "Save and continue keeps the chosen editor",
    );
    await ui
        .getByRole("status")
        .getByText("Ready to edit", { exact: true })
        .waitFor();
    assert.equal(await body.locator(":scope > aside[data-callout]").count(), 9);
    assert.equal(
        await body.locator(":scope > div[data-html-block]").count(),
        1,
    );
    assert.equal(await body.locator("#legacy-anchor.legacy-class").count(), 1);
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    const preview = ui.getByLabel("Rendered preview");
    await preview.locator(".callout-carousel").waitFor();
    await preview
        .getByRole("button", { name: "Show card 5", exact: true })
        .click();
    assert.match(
        await preview
            .locator(".callout-carousel .callout-card")
            .last()
            .textContent(),
        /Final fifth FAQ answer/,
    );
    assert.equal(
        await preview.locator(".html-block-preview h3").textContent(),
        "HTML source heading",
    );
    assert.equal(
        await preview.locator("script,[data-block-action]").count(),
        0,
    );
    await preview.screenshot({ path: "qa/tinymce-preview.png" });
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    await preview.screenshot({ path: "qa/tinymce-preview-dark.png" });
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await body
        .locator(":scope > aside[data-callout]")
        .first()
        .getByRole("button", { name: "Edit block", exact: true })
        .click();
    await dialog.locator("[data-callout-body]").first().waitFor();
    const dialogBackground = await dialog.evaluate(
        (el) => getComputedStyle(el).backgroundColor,
    );
    assert.notEqual(dialogBackground, "rgb(255, 255, 255)");
    await dialog.screenshot({ path: "qa/tinymce-dialog-dark.png" });
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(
        await page.evaluate(
            () => document.documentElement.scrollWidth > innerWidth + 1,
        ),
        false,
    );
    console.log(
        "Passed: TinyMCE callout types, legacy HTML, rich editing, FAQ/link changes, uploads, HTML blocks, clipboard fallback, paragraph insertion, Undo, saving and preview.",
    );
    assert.deepEqual(errors, []);
} finally {
    await browser.close();
    execFileSync(
        ".venv/bin/python",
        [
            "-c",
            "import json,sys,re,shutil,server; [shutil.rmtree(server.UPLOAD_ROOT/token,ignore_errors=True) for token in json.load(sys.stdin) if re.fullmatch(r'[a-f0-9]{32}',token)]",
        ],
        { input: JSON.stringify(uploadTokens) },
    );
    execFileSync(".venv/bin/python", [
        "-c",
        "import sys,server;from django.contrib.flatpages.models import FlatPage;FlatPage.objects.filter(pk=sys.argv[1]).delete()",
        pk,
    ]);
}
