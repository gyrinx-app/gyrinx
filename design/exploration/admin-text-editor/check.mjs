import { chromium } from "playwright";
import { readFileSync, mkdirSync } from "node:fs";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";

const baseURL = `http://127.0.0.1:${process.env.EDITOR_PORT || 8765}`;
mkdirSync("qa", { recursive: true });
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
let originalBody;
let originalOptions;
page.on("pageerror", (error) => errors.push(error.message));
try {
    originalOptions = execFileSync(".venv/bin/python", [
        "-c",
        "import json,server; from lab.models import FlatPageOptions; print(json.dumps(list(FlatPageOptions.objects.filter(page_id=1).values())))",
    ]).toString();
    const token = readFileSync(".local-secret", "utf8").trim();
    await page.goto(`${baseURL}/enter/${token}/`);
    const ui = page.locator("#id_content + [data-editor-host]");
    const editor = ui.getByRole("textbox", { name: "Page content" });
    await editor.waitFor();
    assert.match(page.url(), /admin\/flatpages\/flatpage\/1\/change/);
    await page.getByLabel("URL:", { exact: true }).waitFor();
    await page.getByLabel("Title:", { exact: true }).waitFor();
    await page.getByLabel("Sites:", { exact: true }).waitFor();
    await page.getByText("Advanced options", { exact: true }).click();
    await page.getByLabel("Registration required", { exact: true }).waitFor();
    await page.getByLabel("Template name:", { exact: true }).waitFor();
    assert.equal(
        await page
            .getByRole("textbox", { name: "Introduction", exact: true })
            .count(),
        1,
    );
    await page.locator("#flatpagevisibility_set-group .add-row a").click();
    await page.locator("#id_flatpagevisibility_set-0-groups").waitFor();
    await page.getByText("Advanced options", { exact: true }).click();
    originalBody = await page.locator("#id_content").inputValue();
    const format = ui.getByRole("combobox", { name: "Text style" });
    assert.deepEqual(await format.locator("option").allTextContents(), [
        "Paragraph",
        "Heading 1",
        "Heading 2",
        "Heading 3",
        "Heading 4",
        "Heading 5",
        "Heading 6",
        "Preformatted",
    ]);
    assert.notEqual(
        await format.evaluate((el) => getComputedStyle(el).backgroundImage),
        "none",
        "Format dropdown must show its arrow",
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Undo", exact: true })
            .locator("svg")
            .count(),
        1,
    );
    assert.equal(
        await ui
            .getByRole("button", { name: "Redo", exact: true })
            .locator("svg")
            .count(),
        1,
    );
    for (const name of [
        "Bulleted list",
        "Numbered list",
        "Quote",
        "Link",
        "Image",
        "Clear formatting",
    ]) {
        const button = ui.getByRole("button", { name, exact: true });
        assert.equal(await button.locator("svg").count(), 1);
        assert.equal(await button.getAttribute("title"), name);
        assert.equal(
            await button.locator("svg").getAttribute("stroke-width"),
            "1.7",
        );
    }
    await page.waitForFunction(() =>
        [...document.fonts].some((font) =>
            font.family.includes("mynor-variable"),
        ),
    );
    await page.evaluate(() => document.fonts.load('16px "mynor-variable"'));
    assert.ok(
        await page.evaluate(() =>
            [...document.fonts].some(
                (font) =>
                    font.family.includes("mynor-variable") &&
                    font.status === "loaded",
            ),
        ),
        "Handbook font must load",
    );
    const lightDialogPalettes = {};
    for (const [button, title] of [
        ["Link", "Edit link"],
        ["Image", "Insert image"],
    ]) {
        await ui.getByRole("button", { name: button, exact: true }).click();
        const dialog = ui.getByRole("dialog", { name: title });
        await dialog
            .getByRole("button", { name: "Address", exact: true })
            .click();
        lightDialogPalettes[button] = await dialog.evaluate((el) => ({
            background: getComputedStyle(el).backgroundColor,
            title: getComputedStyle(el.querySelector("h2")).color,
            label: getComputedStyle(el.querySelector("label")).color,
        }));
        await ui.getByRole("button", { name: "Cancel", exact: true }).click();
    }
    await editor.focus();
    await page.keyboard.press("ControlOrMeta+ArrowDown");
    await page.keyboard.press("Enter");
    const text = `Preview check ${Date.now()}`;
    await page.keyboard.type(text);
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    await ui
        .getByLabel("Rendered preview")
        .getByText(text, { exact: false })
        .waitFor();
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await ui.getByRole("button", { name: "Bold", exact: true }).click();
    await page.waitForFunction(
        () =>
            document.querySelector("[data-editor-host]")?.shadowRoot
                ?.activeElement?.isContentEditable,
    );
    await page.keyboard.type(" Bold check");
    await ui.getByRole("button", { name: "HTML", exact: true }).click();
    assert.match(
        await ui.getByLabel("HTML output").textContent(),
        /<strong>.*Bold check/,
    );
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await ui.getByRole("button", { name: "Link", exact: true }).click();
    await ui.getByLabel("Link address").fill("https://gyrinx.app");
    await ui.getByRole("button", { name: "Apply", exact: true }).click();
    await page.waitForFunction(
        () =>
            document.querySelector("[data-editor-host]")?.shadowRoot
                ?.activeElement?.isContentEditable,
    );
    await page.keyboard.type(" Link check");
    await ui.getByRole("button", { name: "HTML", exact: true }).click();
    assert.match(
        await ui.getByLabel("HTML output").textContent(),
        /href="https:\/\/gyrinx.app\//,
    );
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await page.locator('[name="_continue"]').click();
    await page.waitForURL(/change/);
    await editor.waitFor();
    assert.match(await editor.textContent(), new RegExp(text));
    assert.equal(
        execFileSync(".venv/bin/python", [
            "-c",
            "import json,server; from lab.models import FlatPageOptions; print(json.dumps(list(FlatPageOptions.objects.filter(page_id=1).values())))",
        ]).toString(),
        originalOptions,
        "Saving content must leave the untouched introduction unchanged",
    );
    await ui.getByRole("button", { name: "Link", exact: true }).click();
    await ui.getByRole("button", { name: "Upload file", exact: true }).click();
    await ui.getByLabel("File", { exact: true }).setInputFiles({
        name: "campaign-notes.txt",
        mimeType: "text/plain",
        buffer: Buffer.from("Local campaign notes"),
    });
    await page.screenshot({
        path: "qa/admin-file-upload.png",
        fullPage: true,
        animations: "disabled",
    });
    await ui
        .getByRole("button", { name: "Upload and insert", exact: true })
        .click();
    await ui.getByRole("dialog").waitFor({ state: "hidden" });
    const uploadedLink = editor.locator('a[href*="/uploads/"]').first();
    await uploadedLink.waitFor();
    const fileURL = await uploadedLink.getAttribute("href");
    const download = await page.request.get(fileURL);
    assert.equal(await download.text(), "Local campaign notes");
    assert.ok(
        download.headers()["content-disposition"].startsWith("attachment;"),
    );
    const png = execFileSync(".venv/bin/python", [
        "-c",
        'import sys,io; from PIL import Image; b=io.BytesIO(); Image.new("RGB",(32,16),"orange").save(b,format="PNG"); sys.stdout.buffer.write(b.getvalue())',
    ]);
    await ui.getByRole("button", { name: "Image", exact: true }).click();
    await ui.getByLabel("Image file").setInputFiles({
        name: "campaign-image.png",
        mimeType: "image/png",
        buffer: png,
    });
    await ui.getByLabel("Image description").fill("Campaign illustration");
    await page.screenshot({
        path: "qa/admin-image-upload.png",
        fullPage: true,
        animations: "disabled",
    });
    await ui
        .getByRole("button", { name: "Upload and insert", exact: true })
        .click();
    await ui.getByRole("dialog").waitFor({ state: "hidden" });
    const uploadedImage = editor.locator('img[alt="Campaign illustration"]');
    await uploadedImage.waitFor();
    assert.equal(
        await uploadedImage.evaluate((image) => image.naturalWidth),
        32,
    );
    await page.locator('[name="_continue"]').click();
    await editor.waitFor();
    assert.equal(
        await editor.locator('img[alt="Campaign illustration"]').count(),
        1,
    );
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    await ui
        .getByLabel("Rendered preview")
        .locator('img[alt="Campaign illustration"]')
        .waitFor();
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    for (const name of ["Bulleted list", "Numbered list", "Quote"]) {
        const button = ui.getByRole("button", { name, exact: true });
        const wasPressed = await button.getAttribute("aria-pressed");
        await button.click();
        assert.notEqual(await button.getAttribute("aria-pressed"), wasPressed);
        await button.click();
        assert.equal(await button.getAttribute("aria-pressed"), wasPressed);
    }
    await ui.getByRole("button", { name: "Image", exact: true }).click();
    await ui.getByRole("dialog", { name: "Insert image" }).waitFor();
    await ui.getByRole("button", { name: "Cancel", exact: true }).click();
    await ui
        .getByRole("button", { name: "Clear formatting", exact: true })
        .click();
    assert.equal(await format.inputValue(), "0");
    await format.selectOption("pre");
    await editor.locator("pre").waitFor();
    await ui.getByRole("button", { name: "Undo", exact: true }).click();
    assert.notEqual(await format.inputValue(), "pre");
    await ui.getByRole("button", { name: "Redo", exact: true }).click();
    assert.equal(await format.inputValue(), "pre");
    await editor.locator("pre").click();
    await page.keyboard.type("First line");
    await page.keyboard.press("Enter");
    await page.keyboard.type("  Indented line");
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    await ui.getByLabel("Rendered preview").locator("pre code").waitFor();
    assert.match(
        await ui
            .getByLabel("Rendered preview")
            .locator("pre code")
            .textContent(),
        /First line\n  Indented line/,
    );
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await format.selectOption("0");
    assert.equal(await editor.locator("pre").count(), 0);
    const result = await page.evaluate(async () => {
        const response = await fetch("/preview/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": document.querySelector(
                    "[name=csrfmiddlewaretoken]",
                ).value,
            },
            body: JSON.stringify({
                html: '<p>Safe text</p><script>alert(1)</script><a href="javascript:alert(1)">bad</a><img src="x" onerror="alert(1)">',
            }),
        });
        return response.json();
    });
    assert.ok(result.html.includes("Safe text"));
    assert.doesNotMatch(result.html, /<script|javascript:|onerror/);
    execFileSync(
        ".venv/bin/python",
        [
            "-c",
            "import sys,server; from django.contrib.flatpages.models import FlatPage; FlatPage.objects.filter(pk=1).update(content=sys.stdin.read())",
        ],
        { input: originalBody },
    );
    await page.reload();
    await editor.waitFor();
    await page.evaluate(() => document.fonts.ready);
    const draftTypography = await editor.evaluate((el) => ({
        font: getComputedStyle(el).fontFamily,
        size: getComputedStyle(el).fontSize,
        lineHeight: getComputedStyle(el).lineHeight,
        h2: getComputedStyle(el.querySelector("h2")).fontSize,
    }));
    assert.equal(draftTypography.size, "16px");
    assert.equal(draftTypography.lineHeight, "26.4px");
    assert.equal(draftTypography.h2, "22.4px");
    await page.screenshot({ path: "qa/admin-desktop.png", fullPage: true });
    await ui.getByRole("button", { name: "Preview", exact: true }).click();
    await ui.getByLabel("Rendered preview").locator("h2").waitFor();
    const previewTypography = await ui
        .getByLabel("Rendered preview")
        .evaluate((el) => ({
            font: getComputedStyle(el).fontFamily,
            size: getComputedStyle(el).fontSize,
            lineHeight: getComputedStyle(el).lineHeight,
            h2: getComputedStyle(el.querySelector("h2")).fontSize,
        }));
    assert.deepEqual(previewTypography, draftTypography);
    await page.screenshot({ path: "qa/admin-preview.png", fullPage: true });
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await ui.getByRole("button", { name: "Dark theme", exact: true }).click();
    await page.waitForFunction(() => {
        const root = document.querySelector("[data-editor-host]")?.shadowRoot;
        return (
            root &&
            getComputedStyle(
                [...root.querySelectorAll("button")].find(
                    (el) => el.textContent === "Preview",
                ),
            ).color === "rgb(255, 255, 255)"
        );
    });
    const colors = await ui.locator(".gyrinx-editor").evaluate((el) => ({
        background: getComputedStyle(el).backgroundColor,
        color: getComputedStyle(el).color,
    }));
    assert.notEqual(colors.background, "rgba(0, 0, 0, 0)");
    const surface = await ui
        .locator(".editor-document")
        .first()
        .evaluate((el) => getComputedStyle(el).backgroundColor);
    assert.notEqual(
        surface,
        "rgb(255, 255, 255)",
        "Dark editor surface must not remain white",
    );
    assert.equal(
        await format.evaluate((el) => getComputedStyle(el).colorScheme),
        "dark",
    );
    const optionPalette = await format
        .locator("option")
        .first()
        .evaluate((el) => ({
            color: getComputedStyle(el).color,
            background: getComputedStyle(el).backgroundColor,
        }));
    assert.notEqual(
        optionPalette.background,
        "rgb(255, 255, 255)",
        "Dropdown options must use a dark background",
    );
    for (const [button, title] of [
        ["Link", "Edit link"],
        ["Image", "Insert image"],
    ]) {
        await ui.getByRole("button", { name: button, exact: true }).click();
        const dialog = ui.getByRole("dialog", { name: title });
        await dialog
            .getByRole("button", { name: "Address", exact: true })
            .click();
        await ui
            .getByLabel(button === "Link" ? "Link address" : "Image address")
            .fill("ftp://example.com/image.png");
        if (button === "Image")
            await ui.getByLabel("Image description").fill("Example image");
        await ui.getByRole("button", { name: "Apply", exact: true }).click();
        await dialog.getByRole("alert").waitFor();
        const palette = await dialog.evaluate((el) => {
            for (const animation of el.getAnimations({ subtree: true }))
                animation.finish();
            const background = getComputedStyle(el).backgroundColor;
            const canvas = document.createElement("canvas");
            canvas.width = canvas.height = 1;
            const context = canvas.getContext("2d");
            function luminance(color) {
                context.clearRect(0, 0, 1, 1);
                context.fillStyle = color;
                context.fillRect(0, 0, 1, 1);
                const rgb = [...context.getImageData(0, 0, 1, 1).data]
                    .slice(0, 3)
                    .map((value) => {
                        value /= 255;
                        return value <= 0.04045
                            ? value / 12.92
                            : ((value + 0.055) / 1.055) ** 2.4;
                    });
                return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
            }
            const backdrop = luminance(background);
            const text = [...el.querySelectorAll("h2,label,input,p")].map(
                (node) => {
                    const color = getComputedStyle(node).color;
                    const foreground = luminance(color);
                    return {
                        tag: node.tagName,
                        contrast:
                            (Math.max(backdrop, foreground) + 0.05) /
                            (Math.min(backdrop, foreground) + 0.05),
                    };
                },
            );
            return {
                background,
                title: getComputedStyle(el.querySelector("h2")).color,
                label: getComputedStyle(el.querySelector("label")).color,
                text,
            };
        });
        assert.notEqual(
            palette.background,
            lightDialogPalettes[button].background,
        );
        assert.notEqual(palette.title, lightDialogPalettes[button].title);
        assert.notEqual(palette.label, lightDialogPalettes[button].label);
        for (const text of palette.text)
            assert.ok(
                text.contrast >= 4.5,
                `${button} dialog ${text.tag} text contrast must be readable in dark mode (${text.contrast})`,
            );
        await page.screenshot({
            path: `qa/admin-dark-${button.toLowerCase()}-dialog.png`,
            fullPage: true,
            animations: "disabled",
        });
        await dialog
            .getByRole("button", {
                name: button === "Image" ? "Upload image" : "Upload file",
                exact: true,
            })
            .click();
        await page.screenshot({
            path: `qa/admin-dark-${button.toLowerCase()}-upload.png`,
            fullPage: true,
            animations: "disabled",
        });
        await ui.getByRole("button", { name: "Cancel", exact: true }).click();
    }
    await page.screenshot({ path: "qa/admin-dark.png", fullPage: true });
    await ui
        .locator(".editor-document")
        .first()
        .evaluate((el) => {
            el.style.minHeight = "1800px";
        });
    await ui
        .locator(".gyrinx-editor")
        .evaluate((el) =>
            window.scrollTo(
                0,
                window.scrollY + el.getBoundingClientRect().top + 300,
            ),
        );
    assert.ok(
        Math.abs(
            await ui
                .locator(".editor-toolbar")
                .evaluate((el) => el.getBoundingClientRect().top),
        ) <= 1,
        "Toolbar must remain at the top during page scrolling",
    );
    await page.screenshot({
        path: "qa/admin-sticky-toolbar.png",
        fullPage: false,
    });
    await ui
        .locator(".editor-document")
        .first()
        .evaluate((el) => {
            el.style.minHeight = "";
        });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: "qa/admin-mobile.png", fullPage: true });
    await ui
        .locator(".editor-document")
        .first()
        .evaluate((el) => {
            el.style.minHeight = "1800px";
        });
    await ui
        .locator(".gyrinx-editor")
        .evaluate((el) =>
            window.scrollTo(
                0,
                window.scrollY + el.getBoundingClientRect().top + 300,
            ),
        );
    assert.ok(
        Math.abs(
            await ui
                .locator(".editor-toolbar")
                .evaluate((el) => el.getBoundingClientRect().top),
        ) <= 1,
        "Mobile toolbar must also remain sticky",
    );
    await ui
        .locator(".editor-document")
        .first()
        .evaluate((el) => {
            el.style.minHeight = "";
        });
    await page.evaluate(() => window.scrollTo(0, 0));
    const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
    );
    assert.equal(overflow, false, "Mobile page must fit its viewport");
    await ui.getByRole("button", { name: "Edit", exact: true }).click();
    await editor.locator(":scope > p").last().click();
    await page.keyboard.type(" mobile");
    assert.match(await editor.textContent(), /mobile/);
    assert.deepEqual(errors, []);
    console.log(
        "Passed: flat-page fields, visibility controls, unchanged introduction on save, file downloads, direct image uploads, upload save/preview, sticky desktop/mobile toolbar, dark dialogs, typography and editor actions.",
    );
} finally {
    if (originalBody !== undefined)
        execFileSync(
            ".venv/bin/python",
            [
                "-c",
                "import sys,server; from django.contrib.flatpages.models import FlatPage; FlatPage.objects.filter(pk=1).update(content=sys.stdin.read())",
            ],
            { input: originalBody },
        );
    await browser.close();
}
