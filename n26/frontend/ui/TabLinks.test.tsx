import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { TabLinks } from "./TabLinks";

const tabs = [
    { label: "Skills", href: "/skills/", current: true },
    { label: "Powers", href: "/powers/", current: false },
    {
        label: "Other",
        href: "/other/",
        current: false,
        title: "Other collections",
    },
];

test("narrow collection navigation keeps the current link and searches other destinations", async () => {
    const user = userEvent.setup();
    render(<TabLinks label="Which list" tabs={tabs} />);
    const nav = screen.getByRole("navigation", { name: "Which list" });
    const narrow = nav.children[1] as HTMLElement;
    expect(
        within(narrow)
            .getByRole("link", { name: "Skills" })
            .getAttribute("aria-current"),
    ).toBe("page");
    const trigger = within(narrow).getByRole("button", { name: "Other tabs" });
    expect(trigger.textContent).toContain("+2 more");
    await user.click(trigger);
    expect(document.activeElement).toBe(
        screen.getByRole("searchbox", { name: "Search tabs" }),
    );
    expect(screen.queryByRole("menuitem", { name: "Skills" })).toBeNull();
    expect(
        screen.getByRole("menuitem", { name: "Powers" }).getAttribute("href"),
    ).toBe("/powers/");
    await user.type(
        screen.getByRole("searchbox", { name: "Search tabs" }),
        "other",
    );
    expect(screen.queryByRole("menuitem", { name: "Powers" })).toBeNull();
    expect(
        screen.getByRole("menuitem", { name: "Other" }).getAttribute("href"),
    ).toBe("/other/");
    await user.keyboard("{Escape}");
    expect(
        (
            screen.getByRole("searchbox", {
                name: "Search tabs",
            }) as HTMLInputElement
        ).value,
    ).toBe("");
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(trigger);
});

test("two collections remain ordinary links in both responsive strips", () => {
    render(<TabLinks label="Which list" tabs={tabs.slice(0, 2)} />);
    const nav = screen.getByRole("navigation", { name: "Which list" });
    expect(within(nav).queryByRole("button")).toBeNull();
    for (const strip of [...nav.children] as HTMLElement[]) {
        expect(
            within(strip)
                .getByRole("link", { name: "Powers" })
                .getAttribute("href"),
        ).toBe("/powers/");
    }
});
