import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { ProfileSort } from "./ProfileSort";

it("shows only the current label and keeps server-provided sort destinations", async () => {
    render(
        <ProfileSort
            choices={[
                {
                    label: "Name",
                    href: "?tab=n23&category=campaign-gangs&sort=name",
                    current: false,
                },
                {
                    label: "Last modified",
                    href: "?tab=n23&category=campaign-gangs&sort=modified",
                    current: true,
                },
                {
                    label: "Wealth",
                    href: "?tab=n23&category=campaign-gangs&sort=wealth",
                    current: false,
                },
            ]}
        />,
    );
    const trigger = screen.getByRole("button", { name: "Sort gangs" });
    expect(trigger.textContent).toBe("Last modified");
    expect(screen.queryByRole("menu")).toBeNull();
    const user = userEvent.setup();
    await user.click(trigger);
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(
        screen.getByRole("menuitem", { name: "Wealth" }).getAttribute("href"),
    ).toBe("?tab=n23&category=campaign-gangs&sort=wealth");
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(trigger);
    expect(screen.queryByRole("menu")).toBeNull();
});
