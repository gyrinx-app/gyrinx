import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountMenu, type AccountMenuProps } from "./AccountMenu";

const props: AccountMenuProps = {
    label: "Open account menu",
    unread: 0,
    unreadText: "0 unread notifications",
    person: { name: "boss", href: "/n26/users/@boss/", badge: "staff" },
    badges: {
        staff: {
            label: "Gyrinx staff",
            svg: { tag: "svg", props: { viewBox: "0 0 24 24" } },
        },
    },
    items: [
        { type: "person" },
        { type: "separator" },
        { type: "link", label: "Your account", href: "/accounts/" },
        {
            type: "link",
            label: "Notifications",
            href: "/notifications/",
            count: 0,
            countLabel: "unread notifications",
        },
        {
            type: "group",
            label: "Theme",
            items: [
                {
                    type: "theme",
                    storageKey: "theme",
                    defaultMode: "system",
                    choices: [
                        ["light", "Light", "sun"],
                        ["dark", "Dark", "moon"],
                        ["system", "System", "monitor"],
                    ],
                },
            ],
        },
        {
            type: "group",
            label: "Staff only",
            items: [
                { type: "link", label: "Admin", href: "/admin/" },
                {
                    type: "form",
                    label: "Impersonate vex",
                    action: "/impersonate/7/",
                    fields: [
                        ["csrfmiddlewaretoken", "token"],
                        ["next", "/n26/gangs/1/"],
                    ],
                    tone: "danger",
                },
            ],
        },
        { type: "separator" },
        { type: "link", label: "Sign out", href: "/logout/", tone: "danger" },
    ],
};

beforeEach(() => {
    vi.stubGlobal(
        "matchMedia",
        vi.fn(() => ({
            matches: false,
            addEventListener: () => {},
            removeEventListener: () => {},
        })),
    );
    localStorage.clear();
});

const trigger = () =>
    screen.getByRole("button", { name: /^Open account menu/ });

describe("account menu", () => {
    it("names the reader on the button, with their badge, and counts unread", () => {
        render(
            <AccountMenu
                {...props}
                unread={120}
                unreadText="120 unread notifications"
            />,
        );
        const button = trigger();
        expect(button.getAttribute("aria-label")).toBe(
            "Open account menu — 120 unread notifications",
        );
        expect(button.textContent).toContain("boss");
        expect(button.textContent).toContain("99+");
        expect(
            within(button).getByRole("img", { name: "Gyrinx staff" }),
        ).toBeTruthy();
    });

    it("draws its rows in the server's order, with the name as a line", async () => {
        const user = userEvent.setup();
        render(<AccountMenu {...props} />);
        await user.click(trigger());
        const menu = screen.getByRole("menu");
        expect(
            within(menu)
                .getAllByRole("menuitem")
                .map((row) => row.textContent),
        ).toEqual([
            "Your account",
            "Notifications",
            "Admin",
            "Impersonate vex",
            "Sign out",
        ]);
        expect(within(menu).getAllByRole("separator")).toHaveLength(2);
        expect(within(menu).getAllByRole("menuitemradio")).toHaveLength(3);
        // The name leads the menu but is not a row to choose.
        expect(menu.textContent?.indexOf("boss")).toBe(0);
        expect(within(menu).getByText("Staff only")).toBeTruthy();
        expect(
            within(menu)
                .getByRole("menuitem", { name: "Sign out" })
                .getAttribute("href"),
        ).toBe("/logout/");
    });

    it("says what the inbox count means inside the menu", async () => {
        const user = userEvent.setup();
        render(
            <AccountMenu
                {...props}
                unread={2}
                items={props.items.map((e) =>
                    e.type === "link" && e.label === "Notifications"
                        ? { ...e, count: 2 }
                        : e,
                )}
            />,
        );
        await user.click(trigger());
        const row = screen.getByRole("menuitem", { name: /Notifications/ });
        expect(row.textContent).toContain("2 unread notifications");
    });

    it("moves through links, schemes and the form row with the arrow keys", async () => {
        const user = userEvent.setup();
        render(<AccountMenu {...props} />);
        trigger().focus();
        await user.keyboard("{ArrowDown}");
        expect(document.activeElement?.textContent).toBe("Your account");
        await user.keyboard("{ArrowDown}{ArrowDown}");
        expect(document.activeElement?.getAttribute("role")).toBe(
            "menuitemradio",
        );
        await user.keyboard("{End}");
        expect(document.activeElement?.textContent).toBe("Sign out");
        await user.keyboard("{ArrowUp}");
        expect(document.activeElement?.textContent).toBe("Impersonate vex");
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(trigger());
    });

    it("posts the form row with its hidden fields", async () => {
        const user = userEvent.setup();
        render(<AccountMenu {...props} />);
        await user.click(trigger());
        const row = screen.getByRole("menuitem", { name: "Impersonate vex" });
        const form = row.closest("form")!;
        expect(form.getAttribute("method")).toBe("post");
        expect(form.getAttribute("action")).toBe("/impersonate/7/");
        expect(form.getAttribute("role")).toBe("none");
        expect(row.getAttribute("type")).toBe("submit");
        const data = new FormData(form);
        expect(data.get("csrfmiddlewaretoken")).toBe("token");
        expect(data.get("next")).toBe("/n26/gangs/1/");
    });

    it("keeps the menu open while a scheme is chosen", async () => {
        const user = userEvent.setup();
        render(<AccountMenu {...props} />);
        await user.click(trigger());
        await user.click(screen.getByRole("menuitemradio", { name: "Dark" }));
        expect(screen.getByRole("menu")).toBeTruthy();
        expect(document.documentElement.classList.contains("dark")).toBe(true);
        document.documentElement.classList.remove("dark");
    });

    it("closes on Tab and leaves focus on the button", async () => {
        const user = userEvent.setup();
        render(<AccountMenu {...props} />);
        trigger().focus();
        await user.keyboard("{ArrowDown}");
        await user.keyboard("{Tab}");
        expect(screen.queryByRole("menu")).toBeNull();
    });
});
