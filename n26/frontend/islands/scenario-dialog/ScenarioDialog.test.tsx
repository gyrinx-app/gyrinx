import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import {
    ScenarioDialog,
    scenarioNavigation,
    type ScenarioDialogProps,
} from "./ScenarioDialog";

const props: ScenarioDialogProps = {
    mode: "save",
    action: "/n26/scenario/save/",
    cancelUrl: "/n26/scenario/?crew=2",
    selectionUrl: "/n26/scenario/?crew=2&dialog=save",
    csrfToken: "token",
    rolls: { crew: 2 },
    campaigns: [
        { value: "one", label: "Ash Road" },
        { value: "two", label: "Dust Falls" },
    ],
    campaign: "one",
    battles: [
        {
            value: "first",
            label: "Sump clash",
            revision: 3,
            hasScenario: false,
        },
        {
            value: "second",
            label: "Tunnel fight",
            revision: 5,
            hasScenario: true,
        },
    ],
    battle: "",
    revision: null,
    errors: {},
};
beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.setAttribute("open", "");
    });
    HTMLDialogElement.prototype.close = vi.fn(function (
        this: HTMLDialogElement,
    ) {
        this.removeAttribute("open");
    });
});
afterEach(() => vi.restoreAllMocks());
it("changes campaign through its URL while retaining the result", () => {
    const go = vi
        .spyOn(scenarioNavigation, "assign")
        .mockImplementation(() => {});
    render(<ScenarioDialog {...props} />);
    fireEvent.change(screen.getByLabelText("Campaign *"), {
        target: { value: "two" },
    });
    const target = new URL(go.mock.calls[0][0]);
    expect(target.searchParams.get("campaign")).toBe("two");
    expect(target.searchParams.get("crew")).toBe("2");
    expect(target.searchParams.get("dialog")).toBe("save");
});
it("chooses a battle and submits its revision without a name field", () => {
    const { container } = render(<ScenarioDialog {...props} />);
    expect(
        screen.getByRole("button", { name: "Connect scenario" }),
    ).toHaveProperty("disabled", true);
    fireEvent.change(screen.getByLabelText("Battle *"), {
        target: { value: "second" },
    });
    expect(
        container.querySelector<HTMLInputElement>('[name="revision"]')?.value,
    ).toBe("5");
    expect(
        screen.getByText(
            "Connecting replaces this battle’s generated scenario.",
        ),
    ).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Connect scenario" }),
    ).toHaveProperty("disabled", false);
    expect(container.querySelector('[name="name"]')).toBeNull();
});
it("has an explicit empty state when the campaign has no battles", () => {
    render(<ScenarioDialog {...props} battles={[]} />);
    expect(screen.getByText(/No battles in this campaign/)).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Connect scenario" }),
    ).toHaveProperty("disabled", true);
});
it("asks only for a campaign when creating a battle", () => {
    render(<ScenarioDialog {...props} mode="record" />);
    expect(
        screen.getByText(
            "Select a campaign to create a battle using this scenario.",
        ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Battle *")).toBeNull();
    expect(screen.getByRole("button", { name: "Continue" })).toHaveProperty(
        "disabled",
        false,
    );
});
