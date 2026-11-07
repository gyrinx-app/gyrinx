import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { Hire } from "./Hire";
import type { HireProps } from "./types";

const props: HireProps = {
    scope: "gang",
    scopeLabel: "Gang list",
    scopeTabs: [
        { key: "gang", label: "Gang list", href: "/hire/" },
        {
            key: "supplementary",
            label: "Supplementary",
            href: "/hire/?list=supplementary",
        },
        { key: "all", label: "All profiles", href: "/hire/?list=all" },
    ],
    section: "",
    listingHref: "/hire/",
    priceFloor: 0,
    priceCeiling: 0,
    categories: [],
    categoryOptions: [],
    sections: [],
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    owner: { name: "Keeper" },
    figures: {
        items: [],
        roster: { count: 0, rating: 0, groups: [], models: [] },
    },
    values: {
        list: "gang",
        section: "",
        profile: "",
        selection: "[]",
        name: "",
        paid: "",
        rate: "paid",
        request_key: "key",
        profile_name: "",
        choice_names: "[]",
        quoted: "0",
    },
    errors: {},
    confirmation: false,
    notice: "",
    messages: [
        { text: "Hired Vex.", tone: "success" },
        { text: "Not enough credits.", tone: "error" },
        { text: "Review the updated collection.", tone: "warning" },
    ],
    csrfToken: "csrf",
    action: "/hire/",
    commandHref: "/hire/command/",
    recoveryKey: "hire-test",
    back: "/hire/",
    signInHref: "/login/",
};

afterEach(() => vi.unstubAllGlobals());

test("queued Hire outcomes retain their tone and can be dismissed independently", async () => {
    render(<Hire {...props} />);
    const alerts = screen.getAllByRole("alert");
    expect(alerts.map((alert) => alert.getAttribute("data-message"))).toEqual([
        "success",
        "error",
        "warning",
    ]);
    await userEvent.click(
        within(alerts[1]).getByRole("button", { name: "Dismiss" }),
    );
    expect(screen.queryByText("Not enough credits.")).toBeNull();
    expect(screen.getByText("Hired Vex.")).toBeTruthy();
    expect(screen.getByText("Review the updated collection.")).toBeTruthy();
});

test("Enter in search cannot start a hire and all scope links stay available", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    render(<Hire {...props} messages={[]} />);
    expect(
        screen.getByRole("heading", { name: "Hire fighters", level: 1 }),
    ).toBeTruthy();
    const navigation = screen.getByRole("navigation", {
        name: "Who can be hired",
    });
    expect(
        within(navigation)
            .getAllByRole("link")
            .map((link) => link.textContent),
    ).toEqual(["Gang list", "Supplementary", "All profiles"]);
    await userEvent.type(screen.getByRole("searchbox"), "Ganger{Enter}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
});
