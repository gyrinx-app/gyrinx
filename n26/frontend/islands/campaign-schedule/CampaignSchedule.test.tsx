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
            transitionLabel: "End cycle",
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

test("future saved cycles stay editable while generated previews are read-only", () => {
    const value = props();
    value.rows.push(cycle(5, "occupation", "Saved future"));
    render(<CampaignSchedule {...value} />);
    expect(screen.queryByText("Saved future", { exact: true })).toBeNull();
    expect(screen.queryByText("Projected", { exact: true })).toBeNull();
    expect(screen.getByText("Generated preview, not saved yet.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit Cycle 4" })).toBeNull();
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

test("cycle details open a dismissible popover beside phase action menus", async () => {
    const value = props();
    value.focusId = "saved-3";
    value.rows[2].description = "A visible cycle description.";
    value.rows[2].effects =
        "<strong>Recover equipment after this cycle.</strong>";
    render(<CampaignSchedule {...value} />);
    expect(screen.getByText("A visible cycle description.")).toBeTruthy();
    expect(screen.queryByText(value.rows[2].effects)).toBeNull();
    const trigger = screen.getByRole("button", {
        name: "More details: effects for Cycle 3",
    });
    trigger.focus();
    await userEvent.keyboard("{Enter}");
    const panel = screen.getByRole("dialog", {
        name: "More details: effects for Cycle 3",
    });
    expect(panel.textContent).toContain(value.rows[2].effects);
    expect(panel.querySelector("strong")).toBeNull();
    expect(panel.className).toContain("fixed");
    expect(document.activeElement).toBe(panel);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
    await userEvent.click(trigger);
    await userEvent.click(screen.getByText("A visible cycle description."));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
        screen.getByRole("button", { name: "More actions for Downtime" }),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit Downtime" })).toBeNull();
});

test.each([
    ["", "2026-11-01T10:00:00Z", "", "cycle history"],
    ["", "", "2026-11-03T10:00:00Z", "cycle history"],
    [
        "Recover equipment.",
        "2026-11-01T10:00:00Z",
        "2026-11-03T10:00:00Z",
        "effects and cycle history",
    ],
])(
    "cycle details name only their available contents",
    async (effects, startedAt, endedAt, contents) => {
        const value = props();
        Object.assign(value.rows[2], { effects, startedAt, endedAt });
        render(<CampaignSchedule {...value} />);
        await userEvent.click(
            screen.getByRole("button", {
                name: `More details: ${contents} for Cycle 3`,
            }),
        );
        const panel = screen.getByRole("dialog");
        if (effects) expect(panel.textContent).toContain(effects);
        expect(panel.textContent?.includes("Started:")).toBe(
            Boolean(startedAt),
        );
        expect(panel.textContent?.includes("Ended:")).toBe(Boolean(endedAt));
    },
);

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

test("concrete cycles put deletion in their action menu while generated cycles have no actions", async () => {
    const data = props();
    data.rows = data.rows.map((cycle) => ({
        ...cycle,
        deleteHref: `/delete/${cycle.order}/`,
    }));
    render(<CampaignSchedule {...data} />);
    await userEvent.click(
        screen.getByRole("button", { name: "More actions for Cycle 3" }),
    );
    expect(
        screen.getByRole("menuitem", { name: "Delete" }).getAttribute("href"),
    ).toBe("/delete/3/");
    expect(
        screen.queryByRole("button", { name: "More actions for Cycle 4" }),
    ).toBeNull();
    expect(screen.queryByRole("link", { name: "Delete Cycle 4" })).toBeNull();
});

function timeline(): ScheduleProps {
    const value = props();
    value.phases = [
        {
            ...phase("a", "Occupation"),
            phaseId: "occupation",
            number: 1,
            addCycleHref: "/add-cycle/?occurrence=a",
            addPhaseHref: "/add-phase/?after=a",
            moveHref: "/move-phase/?occurrence=a",
        },
        {
            ...phase("empty", "Downtime"),
            phaseId: "downtime",
            number: 2,
            addCycleHref: "/add-cycle/?occurrence=empty",
        },
        {
            ...phase("b", "Occupation"),
            phaseId: "occupation",
            number: 3,
            addCycleHref: "/add-cycle/?occurrence=b",
        },
        {
            ...phase("preview-c", "Takeover"),
            phaseId: "takeover",
            number: 4,
            generated: true,
        },
    ];
    value.rows = [
        {
            ...cycle(1, "occupation", "Current"),
            occurrenceId: "a",
            moveHref: "/move-cycle/?cycle=1",
            duplicateHref: "/duplicate-cycle/?cycle=1",
        },
        { ...cycle(2, "occupation", "Saved future"), occurrenceId: "b" },
        { ...cycle(3, "occupation", "Projected"), occurrenceId: "b" },
        { ...cycle(4, "takeover", "Projected"), occurrenceId: "preview-c" },
    ];
    return value;
}

test("occurrence identities keep empty blocks and repeated definitions in their authored order", () => {
    render(<CampaignSchedule {...timeline()} />);
    expect(
        screen
            .getAllByRole("heading", { level: 3 })
            .map((heading) => heading.textContent),
    ).toEqual(["01 Occupation", "02 Downtime", "03 Occupation", "04 Takeover"]);
    const empty = screen.getByRole("region", { name: "Phase 2: Downtime" });
    expect(within(empty).getByText("No cycles in this phase.")).toBeTruthy();
    expect(
        within(empty)
            .getByRole("link", { name: "Add cycle to phase 02: Downtime" })
            .getAttribute("href"),
    ).toBe("/add-cycle/?occurrence=empty");
    const first = screen.getByRole("region", { name: "Phase 1: Occupation" });
    expect(
        within(first)
            .getByRole("link", { name: "Add phase after 01: Occupation" })
            .getAttribute("href"),
    ).toBe("/add-phase/?after=a");
});

test("generated continuation is explained before its first row even when it extends a concrete occurrence", () => {
    render(<CampaignSchedule {...timeline()} />);
    const marker = screen.getByText(
        "Generated repeat continuation. Added cycles move this preview later.",
    );
    const third = document.getElementById("cycle-saved-3")!;
    expect(
        marker.compareDocumentPosition(third) &
            Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    const second = screen.getByRole("region", { name: "Phase 3: Occupation" });
    const add = within(second).getByRole("link", {
        name: "Add cycle to phase 03: Occupation",
    });
    expect(
        add.compareDocumentPosition(marker) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Edit Cycle 3" })).toBeNull();
    const generated = screen.getByRole("region", { name: "Phase 4: Takeover" });
    expect(within(generated).queryByRole("button")).toBeNull();
    expect(within(generated).queryByRole("link")).toBeNull();
    expect(screen.getByRole("link", { name: "Edit Cycle 2" })).toBeTruthy();
});

test("occurrence and cycle menus use supplied move and duplicate URLs", async () => {
    render(<CampaignSchedule {...timeline()} />);
    await userEvent.click(
        within(
            screen.getByRole("region", { name: "Phase 1: Occupation" }),
        ).getByRole("button", {
            name: "More actions for phase 01: Occupation",
        }),
    );
    expect(
        screen.getByRole("menuitem", { name: "Move" }).getAttribute("href"),
    ).toBe("/move-phase/?occurrence=a");
    await userEvent.keyboard("{Escape}");
    await userEvent.click(
        screen.getByRole("button", {
            name: "More actions for cycle 01: Cycle 1",
        }),
    );
    expect(
        screen.getByRole("menuitem", { name: "Move" }).getAttribute("href"),
    ).toBe("/move-cycle/?cycle=1");
    expect(
        screen
            .getByRole("menuitem", { name: "Duplicate" })
            .getAttribute("href"),
    ).toBe("/duplicate-cycle/?cycle=1");
});

test("readers see empty blocks and generated provenance without authoring links or menus", () => {
    const value = timeline();
    value.canManage = false;
    value.actions = {};
    render(<CampaignSchedule {...value} />);
    expect(screen.getByText("No cycles in this phase.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /More actions/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /^Add / })).toBeNull();
    expect(screen.queryByRole("link", { name: /^Edit / })).toBeNull();
    expect(screen.getByText(/Generated repeat continuation/)).toBeTruthy();
});

test("an empty timeline gives the arbitrator its server-provided add-phase entry", () => {
    const value = timeline();
    value.phases = [];
    value.rows = [];
    value.actions = { addPhase: "/add-first-phase/" };
    render(<CampaignSchedule {...value} />);
    expect(
        screen.getByText(
            "Add a phase to start planning this campaign’s cycles.",
        ),
    ).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Add phase" }).getAttribute("href"),
    ).toBe("/add-first-phase/");
});

test("the repeating-pattern entry appears at the first generated boundary before the read-only tail", () => {
    const value = timeline();
    value.actions.pattern = "/cycles/edit/pattern/";
    render(<CampaignSchedule {...value} />);
    const entry = screen.getByRole("link", { name: "Edit repeating pattern" });
    expect(entry.getAttribute("href")).toBe("/cycles/edit/pattern/");
    expect(
        entry.compareDocumentPosition(
            document.getElementById("cycle-saved-3")!,
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
});

test("owners can explicitly add from the pattern at its first preview boundary", () => {
    const value = timeline();
    value.actions.planCycles = "/cycles/edit/plan-cycles/";
    render(<CampaignSchedule {...value} />);
    const entry = screen.getByRole("link", { name: "Add from pattern" });
    expect(entry.getAttribute("href")).toBe("/cycles/edit/plan-cycles/");
    expect(
        entry.compareDocumentPosition(
            document.getElementById("cycle-saved-3")!,
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
});

test("the pattern append entry stays available before preview rows have loaded", () => {
    const value = timeline();
    value.rows = [];
    value.phases = [];
    value.actions = { planCycles: "/cycles/edit/plan-cycles/" };
    value.plan = null;
    render(<CampaignSchedule {...value} />);
    expect(
        screen
            .getByRole("link", { name: "Add from pattern" })
            .getAttribute("href"),
    ).toBe("/cycles/edit/plan-cycles/");
});

test("paged timelines omit off-page blocks while preserving real empty blocks and global counts", () => {
    const value = timeline();
    value.phases[0].count = 10;
    value.phases.push({
        ...phase("off-page", "Later block"),
        phaseId: "takeover",
        number: 5,
        count: 8,
    });
    value.rows = value.rows.filter((row) => row.state !== "Projected");
    render(<CampaignSchedule {...value} />);
    const first = screen.getByRole("region", { name: "Phase 1: Occupation" });
    expect(within(first).getByText("10 cycles")).toBeTruthy();
    expect(
        screen.getByRole("region", { name: "Phase 2: Downtime" }),
    ).toBeTruthy();
    expect(
        screen.queryByRole("region", { name: "Phase 4: Takeover" }),
    ).toBeNull();
    expect(
        screen.queryByRole("region", { name: "Phase 5: Later block" }),
    ).toBeNull();
    expect(screen.getAllByText("No cycles in this phase.")).toHaveLength(1);
});

test("long repeating patterns name every step even when the preview only reaches the first definition", () => {
    const value = timeline();
    value.phases = [value.phases[0]];
    value.rows = [
        value.rows[0],
        { ...cycle(2, "occupation", "Projected"), occurrenceId: "a" },
    ];
    value.plan = {
        mode: "repeating",
        steps: [
            { id: "opening", phase_id: "occupation", count: 40 },
            { id: "rest", phase_id: "downtime", count: 1 },
            { id: "closing", phase_id: "takeover", count: 3 },
        ],
        phaseNames: {
            occupation: "Occupation",
            downtime: "Downtime",
            takeover: "Takeover",
        },
        startsAfter: "Cycle 13",
        nextPosition: 1,
    };
    render(<CampaignSchedule {...value} />);
    expect(screen.getByText("Occupation × 40")).toBeTruthy();
    expect(screen.getByText("Downtime × 1")).toBeTruthy();
    expect(screen.getByText("Takeover × 3")).toBeTruthy();
    expect(
        screen.queryByRole("region", { name: "Phase 2: Downtime" }),
    ).toBeNull();
});

test.each([true, false])(
    "fixed planned previews expose only supplied edit links to managers (canManage=%s)",
    (canManage) => {
        const value = timeline();
        value.canManage = canManage;
        value.plan!.mode = "fixed";
        value.phases = [value.phases[0], value.phases[3]];
        value.rows = [
            value.rows[0],
            {
                ...value.rows[3],
                editablePreview: true,
                editHref: "/cycles/edit/cycle/?plan=active&position=3",
            },
        ];
        render(<CampaignSchedule {...value} />);
        const preview = within(
            screen.getByRole("region", { name: "Phase 4: Takeover" }),
        );
        const edit = preview.queryByRole("link", { name: "Edit Cycle 4" });
        const dates = preview.queryAllByRole("link", {
            name: /^Edit dates for Cycle 4:/,
        });
        if (canManage) {
            expect(edit?.getAttribute("href")).toBe(
                "/cycles/edit/cycle/?plan=active&position=3",
            );
            expect(dates.length).toBeGreaterThan(0);
            for (const link of dates)
                expect(link.getAttribute("href")).toBe(
                    "/cycles/edit/cycle/?plan=active&position=3&fields=dates",
                );
        } else {
            expect(edit).toBeNull();
            expect(dates).toHaveLength(0);
        }
        expect(
            preview.queryByRole("button", { name: /More actions/ }),
        ).toBeNull();
        expect(screen.queryByText(/Generated repeat continuation/)).toBeNull();
    },
);

test("repeating previews remain read-only even with supplied authoring URLs", () => {
    const value = timeline();
    value.rows[3] = {
        ...value.rows[3],
        moveHref: "/move-preview/",
        duplicateHref: "/duplicate-preview/",
        deleteHref: "/delete-preview/",
    };
    render(<CampaignSchedule {...value} />);
    const preview = within(
        screen.getByRole("region", { name: "Phase 4: Takeover" }),
    );
    expect(preview.queryByRole("link")).toBeNull();
    expect(preview.queryByRole("button")).toBeNull();
});
