import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test } from "vitest";
import { CampaignSetup } from "./CampaignSetup";

afterEach(() => localStorage.clear());
test("dismissal stays with its campaign and completion preserves management links", async () => {
    const props = {
        storageKey: "actor:campaign-a",
        items: [
            { label: "Invite players", href: "/invite/", complete: true },
            {
                label: "Set up phases & cycles",
                href: "/cycles/",
                complete: false,
            },
        ],
    };
    const view = render(<CampaignSetup {...props} />);
    expect(
        screen
            .getByRole("link", { name: "Set up phases & cycles" })
            .getAttribute("href"),
    ).toBe("/cycles/");
    expect(screen.getByLabelText("Complete")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Dismiss setup checklist" }),
    );
    expect(view.container.childElementCount).toBe(0);
    view.unmount();
    const second = render(
        <CampaignSetup
            {...props}
            items={props.items.map((item) => ({ ...item, complete: true }))}
        />,
    );
    expect(second.container.childElementCount).toBe(0);
    second.rerender(
        <CampaignSetup {...props} key="other" storageKey="actor:campaign-b" />,
    );
    expect(
        screen.getByRole("region", { name: "Set up your campaign" }),
    ).toBeTruthy();
});
