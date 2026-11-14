import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { PhaseSettings } from "./PhaseSettings";
import type { Phase, Rewards } from "./types";

function emptyRewards(): Rewards {
    const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        win: reward,
        draw: reward,
        loss: reward,
        entry_credits: { fixed: 0, dice: null },
    };
}

function phase(overrides: Partial<Phase> = {}): Phase {
    return {
        id: "occupation",
        name: "Occupation",
        description: "Build influence in the underhive.",
        effects: "Gangs can claim a territory.",
        rewards: {
            ...emptyRewards(),
            win: { credits: { fixed: 25, dice: null }, reputation: 1 },
            entry_credits: { fixed: 50, dice: null },
        },
        count: 3,
        editHref: "/phases/occupation/edit/",
        duplicateHref: "/phases/occupation/duplicate/",
        deleteHref: "/phases/occupation/delete/",
        ...overrides,
    };
}

test("settings shows authored phase summaries and server phase numbers", async () => {
    render(
        <PhaseSettings
            phases={[phase({ number: 4 })]}
            addHref="/phases/add/"
            disabled={false}
        />,
    );
    expect(
        screen.getByRole("heading", { name: "Phase 4: Occupation" }),
    ).toBeTruthy();
    expect(screen.getByText("Build influence in the underhive.")).toBeTruthy();
    expect(
        screen.getByText(/Win: 25¢, 1 reputation · Phase entry: 50¢/),
    ).toBeTruthy();
    expect(screen.getByText(/3 saved cycles/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Effects for Occupation" }),
    );
    expect(
        within(
            screen.getByRole("dialog", { name: "Effects for Occupation" }),
        ).getByText("Gangs can claim a territory."),
    ).toBeTruthy();
    for (const [action, path] of [
        ["Edit", "edit"],
        ["Duplicate", "duplicate"],
        ["Delete", "delete"],
    ]) {
        const link = screen.getByRole("link", { name: `${action} Occupation` });
        expect(link.getAttribute("href")).toBe(`/phases/occupation/${path}/`);
        expect(link.getAttribute("aria-disabled")).toBe("false");
    }
    expect(
        screen.getByRole("link", { name: "Add phase" }).getAttribute("href"),
    ).toBe("/phases/add/");
});

test("older phase data falls back to the provided order and keeps empty summaries quiet", () => {
    render(
        <PhaseSettings
            phases={[
                phase({
                    id: "z",
                    name: "Takeover",
                    description: "",
                    effects: "",
                    rewards: emptyRewards(),
                    count: 1,
                }),
                phase({
                    id: "a",
                    name: "Downtime",
                    description: "",
                    effects: "",
                    rewards: emptyRewards(),
                    count: 0,
                }),
            ]}
            disabled={false}
        />,
    );
    expect(
        screen.getByRole("heading", { name: "Phase 1: Takeover" }),
    ).toBeTruthy();
    expect(
        screen.getByRole("heading", { name: "Phase 2: Downtime" }),
    ).toBeTruthy();
    expect(screen.getByText("1 saved cycle")).toBeTruthy();
    expect(screen.getByText("0 saved cycles")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Effects for/ })).toBeNull();
    expect(screen.queryByText(/Win:|Phase entry:/)).toBeNull();
    expect(screen.queryByRole("link", { name: "Add phase" })).toBeNull();
});

test("disabled settings preserves phase action links while preventing navigation", () => {
    render(
        <PhaseSettings phases={[phase()]} addHref="/phases/add/" disabled />,
    );
    for (const name of [
        "Edit Occupation",
        "Duplicate Occupation",
        "Delete Occupation",
        "Add phase",
    ]) {
        const link = screen.getByRole("link", { name });
        expect(link.getAttribute("aria-disabled")).toBe("true");
        expect(link.getAttribute("tabindex")).toBe("-1");
        expect(fireEvent.click(link)).toBe(false);
    }
});

test("empty settings keeps the add-phase path without inventing phase actions", () => {
    render(
        <PhaseSettings phases={[]} addHref="/phases/add/" disabled={false} />,
    );
    expect(
        screen.getByText("No phases yet. Add a phase to plan cycles."),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Add phase" })).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();
    expect(
        screen.queryByRole("link", { name: /Edit|Duplicate|Delete/ }),
    ).toBeNull();
});
