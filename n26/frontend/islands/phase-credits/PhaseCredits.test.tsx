import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi, afterEach } from "vitest";
import { PhaseCredits, type PhaseCreditsProps } from "./PhaseCredits";

const props: PhaseCreditsProps = {
    gang: "Ash Choir",
    campaign: "Cinder Road",
    campaignHref: "/campaign/",
    action: "/phase-credits/",
    csrfToken: "csrf",
    arbitrator: true,
    payments: [{ id: "adjustment", label: "250¢ · Downtime" }],
    awards: [
        {
            entry: "entry",
            name: "Downtime",
            cycle: "Cycle 4",
            terms: "250¢",
            eligible: false,
            receipt: null,
        },
    ],
};
afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
});
test("an arbitrator links a previous adjustment with a note", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(
            Response.json(
                { error: "Select an unused credit adjustment." },
                { status: 422 },
            ),
        );
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<PhaseCredits {...props} />);
    expect(
        screen.getByRole("button", { name: "Grant Downtime credits" }),
    ).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("Action"), "paid");
    await user.selectOptions(
        screen.getByLabelText("Credit adjustment"),
        "adjustment",
    );
    await user.type(screen.getByLabelText("Note"), "Paid at the table");
    await user.click(
        screen.getByRole("button", { name: "Mark as already paid" }),
    );
    expect((await screen.findByRole("alert")).textContent).toContain(
        "Select an unused credit adjustment",
    );
    expect(Object.fromEntries(fetch.mock.calls[0]![1].body)).toMatchObject({
        entry: "entry",
        method: "paid",
        payment: "adjustment",
        note: "Paid at the table",
    });
});
