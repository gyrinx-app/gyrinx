import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { CampaignSchedule } from "./CampaignSchedule";
import type { Cycle, Phase, ScheduleProps } from "./types";

function phase(id: string, name: string): Phase {
    const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        id,
        name,
        description: `${name} rules.`,
        effects: "",
        count: 0,
        rewards: {
            win: reward,
            draw: reward,
            loss: reward,
            entry_credits: { fixed: 0, dice: null },
        },
        editHref: `/phase/${id}/edit/`,
        duplicateHref: `/phase/${id}/duplicate/`,
        deleteHref: "",
    };
}
function cycle(order: number, phaseId: string, state = "Past"): Cycle {
    return {
        key: `saved-${order}`,
        name: `Cycle ${order}`,
        order,
        phaseId,
        phaseName: phaseId,
        state,
        startsOn: "",
        endsOn: "",
        description: "",
        effects: "",
        editHref: `/cycle/${order}/edit/`,
        href: `/cycle/${order}/`,
        startedAt: "",
        endedAt: "",
    };
}
function props(): ScheduleProps {
    return {
        campaignName: "Ash Road",
        campaignHref: "/campaign/",
        scheduleHref: "/cycles/",
        canManage: true,
        configured: true,
        status: "In progress",
        currentName: "Cycle 3",
        currentPhase: "Occupation",
        currentPhaseId: "occupation",
        rows: [
            cycle(1, "occupation"),
            cycle(2, "downtime"),
            cycle(3, "occupation", "Current"),
            cycle(4, "occupation", "Projected"),
        ],
        phases: [
            phase("occupation", "Occupation"),
            phase("downtime", "Downtime"),
            phase("unused", "Unused phase"),
        ],
        plan: {
            mode: "repeating",
            steps: [{ id: "step", phase_id: "occupation", count: 2 }],
            startsAfter: "Cycle 3",
            nextPosition: 0,
        },
        actions: {
            plan: "/plan/",
            transition: "/advance/",
            transitionLabel: "Advance cycle",
            template: "/templates/",
            saveTemplate: "/templates/save/",
        },
        previousHref: "",
        nextHref: "",
        moreHref: "/cycles/?preview=24",
        focusId: "",
        editor: null,
    };
}

test("future previews describe a read-only repeating pattern without a shifting boundary", () => {
    render(<CampaignSchedule {...props()} />);
    expect(
        screen.getByText("This pattern repeats until the campaign finishes."),
    ).toBeTruthy();
    expect(screen.queryByText(/Continues after/)).toBeNull();
    expect(
        screen.getByText(/Previewing does not change your schedule/),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("link", { name: "Preview more cycles" })
            .getAttribute("href"),
    ).toBe("/cycles/?preview=24");
});

test("consecutive phase groups preserve repeated occurrences and the saved cycle order", () => {
    const { container } = render(<CampaignSchedule {...props()} />);
    expect(
        Array.from(container.querySelectorAll("tbody tr[id]")).map(
            (row) => row.id,
        ),
    ).toEqual([
        "cycle-saved-1",
        "cycle-saved-2",
        "cycle-saved-3",
        "cycle-saved-4",
    ]);
    const occupation = screen.getAllByRole("region", {
        name: "Phase 1: Occupation",
    });
    expect(occupation).toHaveLength(2);
    expect(within(occupation[0]).queryByText("Current phase")).toBeNull();
    expect(within(occupation[1]).getByText("Current phase")).not.toBeNull();
    expect(within(occupation[1]).getByText("2 cycles")).not.toBeNull();
    expect(
        within(occupation[1]).queryByText("Projected", { exact: true }),
    ).toBeNull();
    expect(container.querySelectorAll("#phase-occupation")).toHaveLength(1);
    expect(screen.queryByRole("region", { name: "Unused phase" })).toBeNull();
});

test("future saved cycles have no badge and previews retain their edit actions", () => {
    const value = props();
    value.rows.push(cycle(5, "occupation", "Saved future"));
    render(<CampaignSchedule {...value} />);
    expect(screen.queryByText("Saved future", { exact: true })).toBeNull();
    expect(screen.queryByText("Projected", { exact: true })).toBeNull();
    expect(
        screen.getByText("Preview, not saved yet. Edit this cycle to save it."),
    ).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Edit Cycle 4" }).getAttribute("href"),
    ).toBe("/cycle/4/edit/");
    expect(
        screen.getByRole("link", { name: "Edit Cycle 5" }).getAttribute("href"),
    ).toBe("/cycle/5/edit/");
    const lastCycle = screen.getByText("Cycle 5");
    expect(
        lastCycle.compareDocumentPosition(
            screen.getByText("Repeating pattern"),
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    for (const heading of screen.getAllByRole("heading", { level: 3 }))
        expect(heading.closest("table")).toBeNull();
});

test("phase rules and configured rewards sit above their cycle rows", () => {
    const value = props();
    value.phases[0].rewards = {
        ...value.phases[0].rewards,
        win: {
            credits: { fixed: 0, dice: { count: 2, sides: 3, multiplier: 10 } },
            reputation: 1,
        },
        entry_credits: { fixed: 250, dice: null },
    };
    render(<CampaignSchedule {...value} />);
    const group = screen.getAllByRole("region", {
        name: "Phase 1: Occupation",
    })[0];
    expect(within(group).getByText("Occupation rules.")).not.toBeNull();
    expect(
        within(group).getByText(
            "Win: 2D3 × 10¢, 1 reputation · Phase entry: 250¢",
        ),
    ).not.toBeNull();
    expect(
        within(group).getByRole("table", { name: "Occupation cycles" }),
    ).not.toBeNull();
});

test("cycle details expand in place beside phase action menus", async () => {
    const value = props();
    value.focusId = "saved-3";
    value.rows[2].effects = "Recover equipment after this cycle.";
    render(<CampaignSchedule {...value} />);
    expect(
        screen
            .getByText("Recover equipment after this cycle.")
            .closest("details")?.open,
    ).toBe(false);
    await userEvent.click(screen.getByText("More details"));
    expect(
        screen
            .getByText("Recover equipment after this cycle.")
            .closest("details")?.open,
    ).toBe(true);
    expect(
        screen.getByRole("button", { name: "More actions for Downtime" }),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit Downtime" })).toBeNull();
});

test("phase menus offer direct edit links and only the supplied management actions", async () => {
    const value = props();
    value.phases[0].deleteHref = "/phase/occupation/delete/";
    render(<CampaignSchedule {...value} />);
    const group = screen.getAllByRole("region", {
        name: "Phase 1: Occupation",
    })[0];
    await userEvent.click(
        within(group).getByRole("button", {
            name: "More actions for Occupation",
        }),
    );
    const menu = within(group).getByRole("menu");
    expect(
        within(menu)
            .getByRole("menuitem", { name: "Edit" })
            .getAttribute("href"),
    ).toBe("/phase/occupation/edit/");
    expect(
        within(menu)
            .getByRole("menuitem", { name: "Duplicate" })
            .getAttribute("href"),
    ).toBe("/phase/occupation/duplicate/");
    expect(
        within(menu)
            .getByRole("menuitem", { name: "Delete" })
            .getAttribute("href"),
    ).toBe("/phase/occupation/delete/");
    expect(within(menu).getByRole("separator")).toBeTruthy();
    await userEvent.keyboard("{Escape}");
    await userEvent.click(
        screen.getByRole("button", { name: "More actions for Downtime" }),
    );
    expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull();
});

test("phase numbers remain stable across repeated groups and use the full phase list", () => {
    const value = props();
    value.phases[0].number = 4;
    value.phases[1].number = 7;
    render(<CampaignSchedule {...value} />);
    expect(
        screen.getAllByRole("heading", { name: "Phase 4: Occupation" }),
    ).toHaveLength(2);
    expect(
        screen.getByRole("heading", { name: "Phase 7: Downtime" }),
    ).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Settings" }).getAttribute("href"),
    ).toBe("/plan/");
});

test("readers can open phase effects without receiving phase management actions", async () => {
    const value = props();
    value.canManage = false;
    value.rows = value.rows.map((row) => ({ ...row, editHref: "" }));
    value.phases[1].effects = "Recover equipment at the end of the phase.";
    render(<CampaignSchedule {...value} />);
    expect(
        screen.queryByRole("button", { name: /More actions for/ }),
    ).toBeNull();
    await userEvent.click(
        screen.getByRole("button", { name: "Effects for Downtime" }),
    );
    expect(
        screen.getByRole("dialog", { name: "Effects for Downtime" })
            .textContent,
    ).toContain(value.phases[1].effects);
});

test("readers retain the grouped rules without management controls", () => {
    const value = props();
    value.canManage = false;
    value.actions = {};
    value.rows = value.rows.map((row) => ({ ...row, editHref: "" }));
    render(<CampaignSchedule {...value} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("link", { name: /^Edit/ })).toBeNull();
    expect(screen.getAllByText("Occupation rules.")).toHaveLength(2);
    expect(
        screen
            .getByRole("link", { name: "Preview more cycles" })
            .getAttribute("href"),
    ).toBe("/cycles/?preview=24");
});

test("saved and projected cycles expose compact deletion actions", () => {
    const data = props();
    data.rows = data.rows.map((cycle) => ({
        ...cycle,
        deleteHref: `/delete/${cycle.order}/`,
    }));
    render(<CampaignSchedule {...data} />);
    for (const row of data.rows) {
        const action = screen.getByRole("link", { name: `Delete ${row.name}` });
        expect(action.getAttribute("href")).toBe(row.deleteHref);
        expect(action.className).toContain("size-6");
    }
});
