import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Hire } from "./Hire";
import type { HireProps } from "./types";

test("queued Hire outcomes retain their tone and can be dismissed independently", async () => {
    const props: HireProps = {
        scope: "gang",
        scopeLabel: "Gang list",
        scopeTabs: [],
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
