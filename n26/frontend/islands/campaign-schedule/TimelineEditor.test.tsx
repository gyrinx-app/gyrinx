import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScheduleEditor } from "./ScheduleEditor";
import { CampaignSchedule } from "./CampaignSchedule";
import type { Editor, ScheduleProps } from "./types";

const occurrences = [
    {
        id: "a",
        number: 1,
        name: "Occupation",
        cycles: [
            { id: "one", order: 1, name: "Opening" },
            { id: "two", order: 2, name: "Second cycle" },
        ],
    },
    {
        id: "b",
        number: 2,
        name: "Occupation",
        cycles: [{ id: "three", order: 3, name: "Later cycle" }],
    },
];
function editor(kind = "move-cycle"): Editor {
    return {
        kind,
        heading:
            kind === "add-cycle"
                ? "Add cycle"
                : kind === "move-phase"
                  ? "Move phase"
                  : kind === "duplicate-cycle"
                    ? "Duplicate cycle"
                    : "Move cycle",
        lead: "Choose its position in the timeline.",
        context: {
            timelineOccurrences: occurrences,
            selectedCycle: {
                id: "two",
                name: "Second cycle",
                order: 2,
                occurrenceId: "a",
            },
        },
        values: {
            request_key: "timeline-key",
            expected_revision: "5",
            cycle_id: "two",
            occurrence_id: "a",
            after_cycle_id: "one",
        },
        errors: {},
        initialConflict: false,
        current: null,
        templates: [],
        action: `/cycles/edit/${kind}/`,
        commandHref: `/cycles/commands/${kind}/`,
        csrfToken: "fresh-token",
        recoveryKey: `timeline:${kind}`,
        back: "/cycles/#phase-a",
    };
}
const json = (data: unknown, status = 200) => ({
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
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
afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

test("moving cycles distinguishes repeated phases and resets the insertion anchor when the destination changes", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: "/cycles/#phase-b" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor editor={editor()} phases={[]} onNavigate={vi.fn()} />,
    );
    expect(screen.getByRole("option", { name: "01 Occupation" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "02 Occupation" })).toBeTruthy();
    expect(
        screen.queryByRole("option", { name: "02 Second cycle" }),
    ).toBeNull();
    await userEvent.selectOptions(screen.getByLabelText("Phase block"), "b");
    expect(screen.getByLabelText("Move cycle after")).toHaveProperty(
        "value",
        "",
    );
    await userEvent.selectOptions(
        screen.getByLabelText("Move cycle after"),
        "three",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("occurrence_id")).toBe("b");
    expect(body.get("after_cycle_id")).toBe("three");
    expect(body.get("cycle_id")).toBe("two");
    expect(fetch.mock.calls[0][0]).toBe("/cycles/commands/move-cycle/");
});

test("moving a phase offers start and other occurrence IDs without offering itself", async () => {
    const value = editor("move-phase");
    value.values = {
        request_key: "move-phase-key",
        expected_revision: "5",
        occurrence_id: "b",
        after_occurrence_id: "a",
    };
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={value} phases={[]} onNavigate={vi.fn()} />);
    expect(screen.queryByRole("option", { name: "02 Occupation" })).toBeNull();
    await userEvent.selectOptions(
        screen.getByLabelText("Move phase after"),
        "",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(fetch.mock.calls[0][1].body.get("after_occurrence_id")).toBe("");
    expect(fetch.mock.calls[0][1].body.get("occurrence_id")).toBe("b");
});

test("duplicating a cycle defaults to blank copied dates and permits insertion after its source", async () => {
    const value = editor("duplicate-cycle");
    value.values.clear_dates = "True";
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={value} phases={[]} onNavigate={vi.fn()} />);
    const blank = screen.getByRole("switch", {
        name: "Leave copied dates blank",
    });
    expect(blank.getAttribute("aria-checked")).toBe("true");
    await userEvent.selectOptions(
        screen.getByLabelText("Add cycle after"),
        "two",
    );
    await userEvent.click(blank);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(fetch.mock.calls[0][1].body.get("clear_dates")).toBe("");
    expect(fetch.mock.calls[0][1].body.get("after_cycle_id")).toBe("two");
});

test("adding a cycle fixes its phase block and posts independently optional dates and details", async () => {
    const value = editor("add-cycle");
    value.values = {
        request_key: "add-key",
        expected_revision: "5",
        occurrence_id: "b",
        after_cycle_id: "",
        custom_name: "",
        starts_on: "",
        ends_on: "",
        description: "",
        effects: "",
    };
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={value} phases={[]} onNavigate={vi.fn()} />);
    expect(screen.getByText("Phase 02 Occupation")).toBeTruthy();
    expect(screen.queryByLabelText("Phase block")).toBeNull();
    expect(screen.queryByLabelText("Phase")).toBeNull();
    await userEvent.type(
        screen.getByLabelText("Custom cycle name"),
        "Market week",
    );
    fireEvent.change(screen.getByLabelText("End date"), {
        target: { value: "2026-12-10" },
    });
    await userEvent.type(
        screen.getByLabelText("Description and rules"),
        "Trade before the next phase.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("occurrence_id")).toBe("b");
    expect(body.has("phase_id")).toBe(false);
    expect(body.get("starts_on")).toBe("");
    expect(body.get("ends_on")).toBe("2026-12-10");
    expect(body.get("custom_name")).toBe("Market week");
    expect(body.get("description")).toBe("Trade before the next phase.");
});

test("an uncertain move freezes destinations and replays its exact payload", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    const setGuard = vi.fn();
    render(
        <ScheduleEditor
            editor={editor()}
            phases={[]}
            onNavigate={vi.fn()}
            navigation={{ pending: false, error: "", retry: vi.fn(), setGuard }}
        />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Phase block"), "b");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    expect(
        (screen.getByLabelText("Phase block") as HTMLSelectElement).closest(
            "fieldset",
        ),
    ).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveProperty(
        "disabled",
        true,
    );
    expect(setGuard).toHaveBeenLastCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
});

test("occurrence deletion only describes the selected block", () => {
    const value = editor("delete-phase");
    value.heading = "Delete phase";
    value.context = {
        occurrenceOnly: true,
        savedCount: 2,
        futureCount: 0,
        repeating: true,
    };
    value.values.current_choice = "";
    render(<ScheduleEditor editor={value} phases={[]} />);
    expect(
        screen.getByText(/2 saved cycles will be removed from the schedule/),
    ).toBeTruthy();
    expect(screen.queryByText(/every repetition/)).toBeNull();
    expect(screen.queryByText(/projected cycles will also/)).toBeNull();
});

function schedule(open: Editor | null = null): ScheduleProps {
    const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        campaignName: "Ash Road",
        campaignHref: "/campaign/",
        scheduleHref: "/cycles/",
        canManage: true,
        configured: true,
        status: "In progress",
        currentName: "",
        currentPhase: "",
        currentPhaseId: "",
        rows: [
            {
                key: "two",
                order: 2,
                name: "Second cycle",
                phaseId: "definition",
                occurrenceId: "a",
                phaseName: "Occupation",
                state: "Saved future",
                startsOn: "",
                endsOn: "",
                description: "",
                effects: "",
                editHref: "",
                href: "/cycles/two/",
                moveHref: "/cycles/edit/move-cycle/",
                startedAt: "",
                endedAt: "",
            },
        ],
        phases: [
            {
                id: "a",
                phaseId: "definition",
                number: 1,
                name: "Occupation",
                description: "",
                effects: "",
                rewards: {
                    win: reward,
                    draw: reward,
                    loss: reward,
                    entry_credits: { fixed: 0, dice: null },
                },
                count: 1,
                editHref: "",
                duplicateHref: "",
                deleteHref: "",
            },
        ],
        plan: null,
        actions: {},
        previousHref: "",
        nextHref: "",
        moreHref: "",
        focusId: "",
        editor: open,
    };
}

test("move dialogs use JSON navigation, retain the timeline and support browser Back and Forward", async () => {
    window.history.replaceState(null, "", "/cycles/");
    const replace = vi.spyOn(window.history, "replaceState");
    const push = vi.spyOn(window.history, "pushState");
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            json({ schedule: schedule(editor()), notices: [] }),
        )
        .mockResolvedValueOnce(json({ schedule: schedule(), notices: [] }))
        .mockResolvedValueOnce(
            json({ schedule: schedule(editor()), notices: [] }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...schedule()} />);
    const source = replace.mock.calls.at(-1)![0];
    const row = document.getElementById("cycle-two")!;
    const trigger = screen.getByRole("button", {
        name: "More actions for cycle 02: Second cycle",
    });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("menuitem", { name: "Move" }));
    await screen.findByRole("dialog", { name: "Move cycle" });
    expect(window.location.pathname).toBe("/cycles/edit/move-cycle/");
    expect(row.isConnected).toBe(true);
    expect(fetch.mock.calls[0][1].headers.Accept).toBe("application/json");
    const target = push.mock.calls.at(-1)![0];
    act(() => {
        window.history.replaceState(source, "", "/cycles/");
        window.dispatchEvent(new PopStateEvent("popstate", { state: source }));
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(row.isConnected).toBe(true);
    act(() => {
        window.history.replaceState(target, "", "/cycles/edit/move-cycle/");
        window.dispatchEvent(new PopStateEvent("popstate", { state: target }));
    });
    await screen.findByRole("dialog", { name: "Move cycle" });
    expect(row.isConnected).toBe(true);
    expect(fetch).toHaveBeenCalledTimes(3);
});

test("older uncertain phase duplication retries without newly introduced copy-position fields", async () => {
    const value = editor("duplicate-phase");
    value.heading = "Duplicate phase";
    value.context = {};
    const original = new URLSearchParams({
        request_key: "old-copy",
        expected_revision: "3",
        phase_id: "a",
        name: "Copied phase",
    });
    sessionStorage.setItem(value.recoveryKey, original.toString());
    value.values = {
        ...Object.fromEntries(original),
        request_key: "new-key",
        clear_dates: "True",
        after_occurrence_id: "a",
    };
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={value} phases={[]} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    body.delete("csrfmiddlewaretoken");
    expect(body.toString()).toBe(original.toString());
});

test.each(["Cancel", "Escape", "Back"])(
    "a delayed keyboard menu read restores its trigger after %s",
    async (close) => {
        window.history.replaceState(null, "", "/cycles/");
        const replace = vi.spyOn(window.history, "replaceState");
        let finish!: (value: ReturnType<typeof json>) => void;
        const slow = new Promise<ReturnType<typeof json>>((resolve) => {
            finish = resolve;
        });
        const fetch = vi
            .fn()
            .mockReturnValueOnce(slow)
            .mockResolvedValueOnce(json({ schedule: schedule(), notices: [] }));
        vi.stubGlobal("fetch", fetch);
        render(<CampaignSchedule {...schedule()} />);
        const source = replace.mock.calls.at(-1)![0];
        const trigger = screen.getByRole("button", {
            name: "More actions for cycle 02: Second cycle",
        });
        trigger.focus();
        await userEvent.keyboard("{ArrowDown}{Enter}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(trigger.getAttribute("aria-busy")).toBe("true");
        await act(async () =>
            finish(json({ schedule: schedule(editor()), notices: [] })),
        );
        const dialog = await screen.findByRole("dialog", {
            name: "Move cycle",
        });
        screen.getByLabelText("Phase block").focus();
        if (close === "Cancel")
            await userEvent.click(
                screen.getByRole("button", { name: "Cancel" }),
            );
        else if (close === "Escape")
            fireEvent(
                dialog,
                new Event("cancel", { bubbles: false, cancelable: true }),
            );
        else
            act(() => {
                window.history.replaceState(source, "", "/cycles/");
                window.dispatchEvent(
                    new PopStateEvent("popstate", { state: source }),
                );
            });
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(document.activeElement).toBe(trigger);
        expect(window.location.pathname).toBe("/cycles/");
    },
);

test("adding cycles from the pattern posts a bounded explicit count and retries an unknown save exactly", async () => {
    const value = editor("plan-cycles");
    value.heading = "Add cycles from pattern";
    value.lead =
        "Add upcoming cycles from the repeating pattern to your timeline.";
    value.values = {
        request_key: "pattern-add-key",
        expected_revision: "5",
        pattern_count: "2",
    };
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    const setGuard = vi.fn();
    render(
        <ScheduleEditor
            editor={value}
            phases={[]}
            onNavigate={vi.fn()}
            navigation={{ pending: false, error: "", retry: vi.fn(), setGuard }}
        />,
    );
    const count = screen.getByLabelText("Cycles to add");
    expect(count).toHaveProperty("value", "2");
    expect(count.getAttribute("min")).toBe("1");
    expect(count.getAttribute("max")).toBe("1000");
    expect(count).toHaveProperty("required", true);
    expect(
        screen.getByText("You can edit these cycles after you add them."),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Phase block")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Add cycles" }));
    await screen.findByRole("button", { name: "Retry save" });
    expect(count.closest("fieldset")).toHaveProperty("disabled", true);
    expect(setGuard).toHaveBeenLastCalledWith(true);
    expect(fetch.mock.calls[0][1].body.get("pattern_count")).toBe("2");
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
});
