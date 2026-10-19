import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import assert from "node:assert/strict";

mkdirSync("qa", { recursive: true });
const browser = await chromium.launch({
    executablePath:
        process.env.CHROME_EXECUTABLE ||
        (process.platform === "darwin"
            ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            : undefined),
    headless: true,
});
const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    colorScheme: "light",
    reducedMotion: "reduce",
});
const errors = [];
const requests = [];
page.on("request", (request) => requests.push(request.url()));
page.on("pageerror", (error) => errors.push(error.message));
try {
    const response = await page.goto(
        process.env.HOMEPAGE_URL || "http://127.0.0.1:8766/homepage/",
    );
    assert.match(response.headers()["cache-control"], /no-store/);
    await page.getByRole("heading", { level: 1 }).waitFor();
    const assetUrls = await page.evaluate(() => ({
        script: document.querySelector('script[type="module"]').src,
        style: document
            .querySelector("[data-homepage-host]")
            .shadowRoot.querySelector('link[rel="stylesheet"]').href,
    }));
    assert.ok(new URL(assetUrls.script).searchParams.get("v"));
    assert.equal(
        new URL(assetUrls.script).search,
        new URL(assetUrls.style).search,
    );
    assert.equal(new URL(assetUrls.style).pathname, "/static/homepage.css");
    assert.ok(
        !requests.some((url) =>
            /\/static\/(editor\.js|tiny-editor\.js|theme\.css)/.test(url),
        ),
    );
    await page.evaluate(() => document.fonts.ready);
    assert.equal(
        await page.getByRole("heading", { level: 1 }).innerText(),
        "Gyrinx: open-source tools for the Necromunda community.",
    );
    assert.equal(await page.locator(".home-feature").count(), 3);
    assert.equal(
        await page.locator(".home-feature .callout-card__chrome").count(),
        0,
    );
    assert.equal(
        await page
            .locator(".home-hero")
            .evaluate((el) => el.getBoundingClientRect().height),
        182,
    );
    await page.getByLabel("Username", { exact: true }).waitFor();
    await page.getByLabel("Password", { exact: true }).waitFor();
    await page.getByLabel("Remember me", { exact: true }).waitFor();
    const footer = page.getByRole("contentinfo");
    assert.equal(
        await footer.locator(".n26-site-footer-grid > div").count(),
        3,
    );
    await footer
        .getByText("Designed and built in the UK.", { exact: true })
        .waitFor();
    assert.equal(await footer.getByRole("link").count(), 12);
    await footer
        .getByRole("img", { name: "Support Gyrinx on Patreon" })
        .scrollIntoViewIfNeeded();
    await page.waitForFunction(() => {
        const image = document
            .querySelector("[data-homepage-host]")
            .shadowRoot.querySelector('img[alt="Support Gyrinx on Patreon"]');
        return image.complete && image.naturalWidth > 0;
    });
    assert.equal(
        await footer
            .getByRole("img", { name: "Support Gyrinx on Patreon" })
            .evaluate((el) => el.complete && el.naturalWidth > 0),
        true,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    assert.equal(
        await page
            .getByRole("link", { name: "Create an account", exact: true })
            .getAttribute("href"),
        "https://gyrinx.app/accounts/signup/",
    );
    assert.equal(await page.locator('[id^="site-banner"]').count(), 0);
    assert.equal(
        await page
            .getByRole("heading", { name: "Sign in", exact: true })
            .count(),
        0,
    );
    assert.equal(await page.locator(".home-feature[data-striped]").count(), 3);
    assert.equal(
        await page
            .locator(".home-register-options")
            .getByRole("link", { name: "About Gyrinx", exact: true })
            .getAttribute("href"),
        "https://gyrinx.app/about/",
    );
    assert.equal(
        await page.locator(".home-feature").nth(1).locator("p").innerText(),
        "Gyrinx is kept up to date with the latest Necromunda rules as they drop. We offer full support for both Necromunda Skirmish (N26) and N23.",
    );
    const loginLayout = await page.locator(".home-login").evaluate((el) => ({
        left: el.getBoundingClientRect().left,
        inset: parseFloat(
            getComputedStyle(el.closest(".home-content-grid")).paddingLeft,
        ),
        containerLeft: el.closest(".home-content-grid").getBoundingClientRect()
            .left,
        gap:
            el.getBoundingClientRect().top -
            el
                .closest("main")
                .querySelector(".home-hero")
                .getBoundingClientRect().bottom,
    }));
    assert.equal(
        loginLayout.left,
        loginLayout.containerLeft + loginLayout.inset,
    );
    assert.ok(loginLayout.gap >= 16 && loginLayout.gap <= 24);
    assert.equal(await page.locator(".home-updates h3").count(), 3);
    const borders = await page
        .locator(".home-updates .divide-y")
        .evaluate((el) => ({
            top: parseFloat(getComputedStyle(el).borderTopWidth),
            bottom: parseFloat(getComputedStyle(el).borderBottomWidth),
            dividers: [...el.children]
                .slice(0, -1)
                .map((entry) =>
                    parseFloat(getComputedStyle(entry).borderBottomWidth),
                ),
        }));
    assert.equal(borders.top, 1);
    assert.equal(borders.bottom, 1);
    assert.deepEqual(borders.dividers, [1, 1]);
    assert.equal(
        await page
            .locator(".home-updates")
            .getByRole("link", { name: "View all" })
            .getAttribute("href"),
        "https://gyrinx.app/changelog/?tag=N26",
    );
    assert.equal(
        await page
            .locator(".home-hero-image")
            .evaluate((el) => el.complete && el.naturalWidth > 0),
        true,
    );
    assert.equal(
        await page.locator(".home-carousel-controls").isVisible(),
        false,
    );
    const positions = await page.locator(".home-feature").evaluateAll((els) =>
        els.map((el) => ({
            x: el.getBoundingClientRect().x,
            y: el.getBoundingClientRect().y,
        })),
    );
    assert.equal(new Set(positions.map(({ y }) => y)).size, 1);
    assert.ok(
        positions[0].x < positions[1].x && positions[1].x < positions[2].x,
    );
    await page.locator(".home-feature").first().hover();
    assert.equal(
        await page
            .locator(".home-feature")
            .first()
            .evaluate((el) => new DOMMatrix(getComputedStyle(el).transform).a),
        1.025,
    );
    await page.mouse.move(0, 0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: "qa/homepage-desktop.png", fullPage: true });
    await page.getByRole("button", { name: "Use dark theme" }).click();
    await page.screenshot({
        path: "qa/homepage-desktop-dark.png",
        animations: "disabled",
        fullPage: true,
    });
    await page.reload();
    await page.getByRole("button", { name: "Use light theme" }).click();
    await page.getByRole("button", { name: "Open navigation menu" }).click();
    assert.equal(await page.getByRole("dialog").isVisible(), true);
    await page.keyboard.press("Escape");
    assert.equal(await page.getByRole("dialog").isVisible(), false);
    assert.equal(
        await page
            .getByRole("button", { name: "Open navigation menu" })
            .evaluate((el) => el.getRootNode().activeElement === el),
        true,
    );
    for (const width of [320, 390, 674, 767, 768, 926, 1024, 1440, 1920]) {
        await page.setViewportSize({ width, height: 900 });
        assert.equal(
            await page.evaluate(
                () => document.documentElement.scrollWidth <= window.innerWidth,
            ),
            true,
            `Overflow at ${width}px`,
        );
        assert.equal(
            await page.locator(".home-carousel-controls").isVisible(),
            width < 768,
        );
        const layout = await page
            .locator(".home-content-grid")
            .evaluate((el) => {
                const login = el
                    .querySelector(".home-invitation")
                    .getBoundingClientRect();
                const features = el
                    .querySelector(".home-features")
                    .getBoundingClientRect();
                const updates = el
                    .querySelector(".home-updates")
                    .getBoundingClientRect();
                const baseline = (element) => {
                    const marker = document.createElement("span");
                    marker.style.cssText =
                        "display:inline-block;width:0;height:0;padding:0;margin:0;vertical-align:baseline";
                    element.append(marker);
                    const y = marker.getBoundingClientRect().top;
                    marker.remove();
                    return y;
                };
                const updatesElement = el.querySelector(".home-updates");
                return {
                    usernameBaseline: baseline(
                        el.querySelector('label[for="home-username"]'),
                    ),
                    updatesBaseline: baseline(
                        updatesElement.querySelector("h2"),
                    ),
                    updatesClientHeight: updatesElement.clientHeight,
                    updatesScrollHeight: updatesElement.scrollHeight,
                    lastEntryBottom: updatesElement
                        .querySelector(".divide-y")
                        .lastElementChild.getBoundingClientRect().bottom,
                    updatesBottom: updates.bottom,
                    loginHeight: login.height,
                    updatesHeight: updates.height,
                    width: el.getBoundingClientRect().width,
                    loginTop: login.top,
                    loginRight: login.right,
                    updatesLeft: updates.left,
                    updatesTop: updates.top,
                    featuresBottom: features.bottom,
                };
            });
        assert.ok(layout.width <= (width >= 1400 ? 1320 : 1200));
        if (width < 768) assert.ok(layout.updatesTop >= layout.featuresBottom);
        else {
            assert.ok(
                Math.abs(layout.usernameBaseline - layout.updatesBaseline) <= 1,
            );
            assert.ok(layout.updatesLeft > layout.loginRight);
            assert.equal(
                layout.updatesScrollHeight,
                layout.updatesClientHeight,
            );
            assert.ok(layout.lastEntryBottom <= layout.updatesBottom + 1);
        }
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(
        () =>
            new Promise((resolve) =>
                requestAnimationFrame(() => requestAnimationFrame(resolve)),
            ),
    );
    await page.locator(".home-feature-track").focus();
    await page.keyboard.press("ArrowRight");
    await page.waitForFunction(
        () =>
            document
                .querySelector("[data-homepage-host]")
                .shadowRoot.querySelector('[aria-label="Show content card"]')
                .getAttribute("aria-current") === "true",
    );
    await page.getByRole("button", { name: "Next card", exact: true }).click();
    await page.waitForFunction(
        () =>
            document
                .querySelector("[data-homepage-host]")
                .shadowRoot.querySelector('[aria-label="Show campaigns card"]')
                .getAttribute("aria-current") === "true",
    );
    assert.equal(
        await page
            .getByRole("button", { name: "Next card", exact: true })
            .isDisabled(),
        true,
    );
    await page.screenshot({
        path: "qa/homepage-mobile-campaigns.png",
        fullPage: true,
    });
    await page.getByRole("button", { name: "Show gangs card" }).click();
    await page.waitForFunction(
        () =>
            document
                .querySelector("[data-homepage-host]")
                .shadowRoot.querySelector('[aria-label="Show gangs card"]')
                .getAttribute("aria-current") === "true",
    );
    // Native scrolling follows the same state path as a touch swipe.
    await page.locator(".home-feature-track").evaluate((el) => {
        el.scrollLeft = el.children[1].offsetLeft - el.children[0].offsetLeft;
    });
    await page.waitForFunction(
        () =>
            document
                .querySelector("[data-homepage-host]")
                .shadowRoot.querySelector('[aria-label="Show content card"]')
                .getAttribute("aria-current") === "true",
    );
    await page.getByRole("button", { name: "Show gangs card" }).click();
    await page.waitForFunction(
        () =>
            document
                .querySelector("[data-homepage-host]")
                .shadowRoot.querySelector('[aria-label="Show gangs card"]')
                .getAttribute("aria-current") === "true",
    );
    await page.evaluate(() => {
        document
            .querySelector("[data-homepage-host]")
            .shadowRoot.activeElement?.blur();
        window.scrollTo(0, 0);
    });
    await page.screenshot({ path: "qa/homepage-mobile.png", fullPage: true });
    await page.locator(".home-feature").first().hover();
    const mobileHover = await page
        .locator(".home-feature")
        .first()
        .evaluate((el) => {
            const card = el.getBoundingClientRect();
            const track = el.parentElement.getBoundingClientRect();
            return {
                scale: new DOMMatrix(getComputedStyle(el).transform).a,
                fits:
                    card.left >= track.left &&
                    card.right <= track.right &&
                    card.top >= track.top &&
                    card.bottom <= track.bottom,
            };
        });
    assert.equal(mobileHover.scale, 1.025);
    assert.equal(mobileHover.fits, true);
    await page.mouse.move(0, 0);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.getByRole("button", { name: "Use dark theme" }).click();
    await page.screenshot({
        path: "qa/homepage-mobile-dark.png",
        animations: "disabled",
        fullPage: true,
    });
    assert.equal(
        await page
            .getByRole("link", { name: "Sign up", exact: true })
            .first()
            .getAttribute("href"),
        "https://gyrinx.app/accounts/signup/",
    );
    assert.deepEqual(errors, []);
    await page
        .getByLabel("Username", { exact: true })
        .fill("preview@example.com");
    await page
        .getByText("Use your username to sign in.", { exact: true })
        .waitFor();
    await page.getByLabel("Username", { exact: true }).fill("preview-user");
    await page
        .getByLabel("Password", { exact: true })
        .fill("preview-only-password");
    await page.getByLabel("Remember me", { exact: true }).check();
    const outgoing = [];
    page.on("request", (request) => {
        if (request.method() === "POST") outgoing.push(request.url());
    });
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page
        .getByText("This is a design preview.", { exact: false })
        .waitFor();
    assert.equal(
        await page.getByLabel("Password", { exact: true }).inputValue(),
        "",
    );
    assert.deepEqual(outgoing, []);
    assert.equal(
        page.url(),
        process.env.HOMEPAGE_URL || "http://127.0.0.1:8766/homepage/",
    );
    console.log(
        "Homepage: desktop grid, mobile carousel, keyboard and scroll navigation, themes, menu, responsive widths and images passed.",
    );
} finally {
    await browser.close();
}
