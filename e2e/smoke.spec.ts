import { test, expect } from "@playwright/test";

const TEST_USER_PASSWORD = process.env.TEST_USER_PASSWORD;

if (!TEST_USER_PASSWORD) {
    throw new Error("TEST_USER_PASSWORD is not set");
}

test("test", async ({ page }) => {
    await page.goto("https://gyrinx.app/");

    // Load the lists page
    await page.getByRole("link", { name: "Lists" }).click();

    // Log in as test user
    await page.getByRole("link", { name: "Sign In" }).click();
    await page.getByRole("textbox", { name: "Username:" }).click();
    await page.getByRole("textbox", { name: "Username:" }).fill("test");
    await page.getByRole("textbox", { name: "Password:" }).click();
    await page
        .getByRole("textbox", { name: "Password:" })
        .fill(TEST_USER_PASSWORD);
    await page.getByRole("button", { name: "Sign In" }).click();

    // Create a new list
    await page.getByRole("link", { name: "Create a new List" }).click();
    await page.getByRole("textbox", { name: "Name:" }).click();
    await page.getByRole("textbox", { name: "Name:" }).fill("Test");
    await page
        .getByLabel("House:")
        .selectOption("9647fe15-019d-4968-aaf3-85b064d3de39");
    await page.getByRole("checkbox", { name: "Public:" }).uncheck();
    await expect(page.getByRole("button", { name: "Create" })).toBeVisible();
    await page.getByRole("button", { name: "Create" }).click();

    // Verify the list was created
    await expect(page.locator("h2")).toContainText("Test");

    // Add a fighter to the list
    await page.getByText("Add fighter").click();
    await page.getByRole("textbox", { name: "Name:" }).fill("T-1");
    await page
        .getByLabel("Fighter:")
        .selectOption("ba216a78-19c1-4de7-8e17-7a279b453c11");
    await expect(page.getByRole("button", { name: "Add" })).toBeVisible();
    await page.getByRole("button", { name: "Add" }).click();

    // Verify the fighter was added
    await expect(page.getByText("T-1 115¢")).toBeVisible();
    await expect(page.getByText("Charter Master (Leader)")).toBeVisible();
    await expect(page.locator("#content")).toContainText(
        "Charter Master (Leader)",
    );
    await expect(page.locator("#content")).toContainText(
        "Gang Hierarchy (Leader)",
    );
    await expect(page.locator("#content")).toContainText(
        "This fighter has no weapons.",
    );

    // Add a weapon to the fighter
    await page.getByRole("link", { name: "Add or edit weapons" }).click();
    await expect(page.locator("#content")).toContainText(
        "This fighter has no weapons.",
    );
    await page.getByRole("button", { name: "Add Ironhead autogun" }).click();

    // Verify the weapon was added
    await expect(page.locator("#content")).toContainText(
        "Ironhead autogun (25¢)",
    );
    await expect(page.locator("#content")).toContainText("4+");
    await expect(page.locator("#content")).toContainText("Rapid Fire (2)");

    // Add gear to the fighter
    await page.getByRole("link", { name: "Test", exact: true }).click();
    await page.getByRole("link", { name: "Add gear" }).click();
    await expect(page.locator("#content")).toContainText(
        "This fighter has no gear.",
    );
    await page.getByRole("button", { name: "Add Mesh armour (15¢)" }).click();

    // Verify the gear was added
    await expect(page.locator("#content")).toContainText("Mesh armour (15¢)");
    await page.getByRole("link", { name: "Test", exact: true }).click();
    await expect(page.locator("#content")).toContainText("Mesh armour (15¢)");

    // Add skills to the fighter
    await page.getByRole("link", { name: "Add skills" }).click();
    await page.getByRole("checkbox", { name: "Crushing Blow" }).check();
    await page.getByRole("button", { name: "Save" }).click();

    // Verify the skills were added
    await expect(page.locator("#content")).toContainText("Crushing Blow");
});
