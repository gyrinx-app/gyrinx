import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScheduleEditor } from "./ScheduleEditor";
import type { Editor, Phase } from "./types";

const phases = [
    { id: "opening", name: "Opening", count: 1 },
    { id: "downtime", name: "Downtime", count: 0 },
] as Phase[];
const editor: Editor = {
    kind: "cycle",
    heading: "Edit cycle",
    lead: "The current cycle remains Cycle 1.",
    context: {},
    values: {
        request_key: "original-command",
        expected_revision: "1",
        target: '{"kind":"saved","id":"cycle"}',
        phase_id: "opening",
        custom_name: "Market week",
        starts_on: "",
        ends_on: "",
        description: "",
        effects: "",
    },
    errors: {},
    initialConflict: false,
    current: null,
    templates: [],
    action: "/cycles/edit/cycle/",
    commandHref: "/cycles/commands/cycle/",
    csrfToken: "fresh-csrf",
    recoveryKey: "cycle:actor:campaign:subject",
    back: "/cycles/",
};
const json = (data: unknown, status = 200) => ({
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
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
});

test("end date changes offer an explicit shift and retain it for an exact retry", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            phases={phases}
            onNavigate={vi.fn()}
            editor={{
                ...editor,
                context: {
                    shiftLater: {
                        endsOn: "2026-11-07",
                        followingOn: "2026-11-08",
                    },
                },
                values: {
                    ...editor.values,
                    starts_on: "2026-11-01",
                    ends_on: "2026-11-07",
                    shift_later: "False",
                },
            }}
        />,
    );
    expect(
        screen.queryByRole("switch", { name: "Move later cycle dates too" }),
    ).toBeNull();
    fireEvent.change(screen.getByLabelText("End date"), {
        target: { value: "2026-11-05" },
    });
    const shift = screen.getByRole("switch", {
        name: "Move later cycle dates too",
    });
    expect(shift.getAttribute("aria-checked")).toBe("false");
    await userEvent.click(shift);
    expect(screen.getByText(/2 days earlier/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    expect(fetch.mock.calls[0][1].body.get("shift_later")).toBe("on");
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
});

test.each([false, true])(
    "setup is a page and reviews the optional current-cycle choice before writing",
    async (noCurrent) => {
        const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
        const definition = {
            phases: [
                {
                    id: "opening",
                    details: {
                        name: "Opening",
                        description: "",
                        effects: "",
                        rewards: {
                            win: reward,
                            draw: reward,
                            loss: reward,
                            entry_credits: { fixed: 0, dice: null },
                        },
                    },
                },
            ],
            steps: [{ id: "step", phase_id: "opening", count: 3 }],
        };
        const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
        vi.stubGlobal("fetch", fetch);
        render(
            <ScheduleEditor
                phases={[]}
                onNavigate={vi.fn()}
                editor={{
                    ...editor,
                    kind: "setup",
                    heading: "Set up campaign phases & cycles",
                    context: { activates: true },
                    templates: [
                        {
                            id: "template",
                            name: "Starting pattern",
                            definition,
                        },
                    ],
                    values: {
                        request_key: "setup-key",
                        template_id: "",
                        setup_definition: "",
                        mode: "fixed",
                        current_number: "1",
                        no_current: "False",
                        date_start: "2026-11-01",
                        cycle_interval: "1",
                        cycle_unit: "weeks",
                    },
                }}
            />,
        );
        expect(
            screen.getByRole("heading", {
                level: 1,
                name: "Set up campaign phases & cycles",
            }),
        ).toBeTruthy();
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(screen.queryByText(/This will send notifications/)).toBeNull();
        await userEvent.selectOptions(
            screen.getByRole("combobox", { name: "Starting schedule" }),
            "template",
        );
        expect(screen.getByText(/1. Opening/)).toBeTruthy();
        await userEvent.click(
            screen.getByRole("button", { name: "Customise schedule" }),
        );
        screen.getByRole("button", { name: "Back" }).focus();
        await userEvent.keyboard("{Enter}");
        expect(document.activeElement?.textContent).toContain(
            "Choose a starting schedule",
        );
        await userEvent.tab();
        expect(document.activeElement).toBe(
            screen.getByRole("combobox", { name: "Starting schedule" }),
        );
        await userEvent.click(
            screen.getByRole("button", { name: "Customise schedule" }),
        );
        await userEvent.clear(screen.getByLabelText("Phase 1 name"));
        await userEvent.type(
            screen.getByLabelText("Phase 1 name"),
            "My opening",
        );
        const addPhase = screen.getByRole("button", { name: "Add phase" });
        expect(
            addPhase.compareDocumentPosition(
                screen.getByRole("table", { name: "Future phase steps" }),
            ) & Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
        if (noCurrent) {
            await userEvent.click(
                screen.getByRole("switch", { name: "Start with cycle active" }),
            );
            expect(screen.queryByLabelText("Current cycle number")).toBeNull();
        } else {
            expect(
                screen
                    .getByLabelText("Current cycle number")
                    .hasAttribute("required"),
            ).toBe(false);
            await userEvent.clear(
                screen.getByLabelText("Current cycle number"),
            );
        }
        expect(screen.queryByText(/This will send notifications/)).toBeNull();
        await userEvent.click(
            screen.getByRole("button", { name: "Review schedule" }),
        );
        expect(screen.getByText(/1. My opening/)).toBeTruthy();
        expect(screen.getByText("1 week")).toBeTruthy();
        expect(
            !!screen.queryByText(/Selecting “Set up phases & cycles” starts/),
        ).toBe(!noCurrent);
        expect(
            screen.getByText(noCurrent ? "None" : "Cycle 1", { exact: true }),
        ).toBeTruthy();
        expect(fetch).not.toHaveBeenCalled();
        await userEvent.click(
            screen.getByRole("button", { name: "Set up phases & cycles" }),
        );
        expect(fetch).toHaveBeenCalledTimes(1);
        const body = fetch.mock.calls[0][1].body as URLSearchParams;
        expect(body.get("no_current")).toBe(noCurrent ? "on" : "False");
        expect(body.has("current_number")).toBe(true);
        expect(
            JSON.parse(body.get("setup_definition")!).phases[0].details.name,
        ).toBe("My opening");
        expect(definition.phases[0].details.name).toBe("Opening");
    },
);

test("advancing a projected cycle keeps the transition clear without a saving notice", () => {
    render(
        <ScheduleEditor
            phases={phases}
            editor={{
                ...editor,
                kind: "advance",
                heading: "Advance cycle",
                lead: "End Cycle 1 and start Cycle 2. This will send notifications to players participating in the campaign.",
                context: { ending: "Cycle 1", starting: "Cycle 2" },
            }}
        />,
    );
    expect(screen.getByText(/End Cycle 1 and start Cycle 2/)).toBeTruthy();
    expect(screen.queryByText(/next projected cycle/)).toBeNull();
    expect(screen.getByRole("button", { name: "Advance cycle" })).toBeTruthy();
});

test("a lost response freezes the draft and retries the exact command", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/cycles/cycle/" }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ScheduleEditor
            editor={editor}
            phases={phases}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    expect(
        screen
            .getByRole("textbox", { name: "Custom cycle name" })
            .matches(":disabled"),
    ).toBe(true);
    expect(
        screen.getByRole("button", { name: "Cancel" }).matches(":disabled"),
    ).toBe(true);
    expect(sessionStorage.getItem(editor.recoveryKey)).not.toContain(
        "fresh-csrf",
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
    expect(navigate).toHaveBeenCalledWith("/cycles/cycle/");
    expect(sessionStorage.getItem(editor.recoveryKey)).toBeNull();
});

test("reload recovery keeps the earlier identity while using fresh credentials", async () => {
    const retained = new URLSearchParams({
        ...editor.values,
        request_key: "earlier-command",
        custom_name: "Earlier draft",
    });
    sessionStorage.setItem(editor.recoveryKey, retained.toString());
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor editor={editor} phases={phases} onNavigate={vi.fn()} />,
    );
    expect(
        (
            screen.getByRole("textbox", {
                name: "Custom cycle name",
            }) as HTMLInputElement
        ).value,
    ).toBe("Earlier draft");
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("request_key")).toBe("earlier-command");
    expect(body.get("csrfmiddlewaretoken")).toBe("fresh-csrf");
});

test("revision conflicts show current facts and require explicit review", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "revision_conflict",
                    errors: { __all__: ["The schedule changed."] },
                    current: {
                        revision: 2,
                        cycle: "Cycle 2",
                        phase: "Downtime",
                    },
                    reviewUrl: "/cycles/",
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(
        <ScheduleEditor
            editor={editor}
            phases={phases}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Cycle 2 · Downtime");
    expect(
        (
            screen.getByRole("textbox", {
                name: "Custom cycle name",
            }) as HTMLInputElement
        ).value,
    ).toBe("Market week");
    expect(
        screen
            .getByRole("textbox", { name: "Custom cycle name" })
            .matches(":disabled"),
    ).toBe(true);
    expect(navigate).not.toHaveBeenCalled();
    await userEvent.click(
        screen.getByRole("button", { name: "Review current schedule" }),
    );
    expect(navigate).toHaveBeenCalledWith("/cycles/");
});

test("keyboard reordering submits phase identities and counts in the chosen order", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    const steps = [
        { id: "one", phase_id: "opening", count: 3 },
        { id: "two", phase_id: "downtime", count: 1 },
    ];
    render(
        <ScheduleEditor
            editor={{
                ...editor,
                kind: "plan",
                heading: "Edit future plan",
                values: {
                    request_key: "plan-command",
                    expected_revision: "1",
                    mode: "fixed",
                    steps: JSON.stringify(steps),
                },
            }}
            phases={phases}
            onNavigate={vi.fn()}
        />,
    );
    screen.getByRole("button", { name: "Move step 2 earlier" }).focus();
    await userEvent.keyboard("{Enter}");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(JSON.parse(fetch.mock.calls[0][1].body.get("steps"))).toEqual([
        steps[1],
        steps[0],
    ]);
});

test("fixed conversion shows its finite endpoint and updates it after edits", async () => {
    const full = [
        { id: "one", phase_id: "opening", count: 3 },
        { id: "two", phase_id: "downtime", count: 1 },
    ];
    render(
        <ScheduleEditor
            editor={{
                ...editor,
                kind: "plan",
                context: {
                    patternSteps: full,
                    fixedSteps: [{ ...full[0], count: 1 }, full[1]],
                    startsAfterOrder: 2,
                },
                values: {
                    request_key: "convert-key",
                    expected_revision: "1",
                    mode: "repeating",
                    steps: JSON.stringify(full),
                },
            }}
            phases={phases}
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByRole("heading", { level: 2, name: "Cycles" }),
    ).toBeTruthy();
    expect(
        screen.getByRole("region", { name: "Repeating pattern options" }),
    ).toBeTruthy();
    expect(screen.queryByText(/Ends after Cycle/)).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: /^Fixed plan/ }));
    expect(
        screen.queryByRole("region", { name: "Repeating pattern options" }),
    ).toBeNull();
    expect(
        screen.getByRole("region", { name: "Fixed plan options" }),
    ).toBeTruthy();
    expect(screen.getByText("Ends after Cycle 4.")).toBeTruthy();
    const count = screen.getByRole("spinbutton", { name: "Step 1 cycles" });
    await userEvent.clear(count);
    await userEvent.type(count, "2");
    expect(screen.getByText("Ends after Cycle 5.")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Remove step 2" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Remove step 1" }),
    );
    expect(screen.getByText("No additional cycles.")).toBeTruthy();
});

test("switching to repeating proposes the full pattern and preserves edits to each mode", async () => {
    const full = [
        { id: "one", phase_id: "opening", count: 3 },
        { id: "two", phase_id: "downtime", count: 1 },
    ];
    const remaining = [{ ...full[1] }];
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            editor={{
                ...editor,
                kind: "plan",
                context: { patternSteps: full, fixedSteps: remaining },
                values: {
                    request_key: "mode-key",
                    expected_revision: "1",
                    mode: "fixed",
                    steps: JSON.stringify(remaining),
                },
            }}
            phases={phases}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(
        screen.getByRole("radio", { name: /^Repeating pattern/ }),
    );
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Step 1 cycles",
            }) as HTMLInputElement
        ).value,
    ).toBe("3");
    await userEvent.clear(
        screen.getByRole("spinbutton", { name: "Step 1 cycles" }),
    );
    await userEvent.type(
        screen.getByRole("spinbutton", { name: "Step 1 cycles" }),
        "2",
    );
    await userEvent.click(screen.getByRole("radio", { name: /^Fixed plan/ }));
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Step 1 cycles",
            }) as HTMLInputElement
        ).value,
    ).toBe("1");
    await userEvent.click(
        screen.getByRole("radio", { name: /^Repeating pattern/ }),
    );
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Step 1 cycles",
            }) as HTMLInputElement
        ).value,
    ).toBe("2");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(JSON.parse(fetch.mock.calls[0][1].body.get("steps"))[0].count).toBe(
        2,
    );
});

test("retained plan commands survive the addition of date controls without changing their payload", async () => {
    const retained = {
        request_key: "earlier-plan",
        expected_revision: "1",
        mode: "fixed",
        steps: "[]",
    };
    sessionStorage.setItem(
        editor.recoveryKey,
        new URLSearchParams(retained).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            editor={{
                ...editor,
                kind: "plan",
                values: {
                    ...retained,
                    request_key: "fresh-plan",
                    date_start: "2026-11-01",
                    cycle_interval: "1",
                    cycle_unit: "weeks",
                },
            }}
            phases={phases}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("request_key")).toBe("earlier-plan");
    expect(body.has("date_start")).toBe(false);
});

test("malformed recovered structured input stays available for exact retry", async () => {
    const values = {
        request_key: "phase-command",
        expected_revision: "1",
        phase_id: "opening",
        name: "Opening",
        description: "",
        effects: "",
        rewards: '{"win":null}',
    };
    sessionStorage.setItem(
        editor.recoveryKey,
        new URLSearchParams(values).toString(),
    );
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ errors: { __all__: ["Invalid reward settings."] } }, 422),
        );
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            editor={{ ...editor, kind: "phase", heading: "Edit phase", values }}
            phases={phases}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.get("rewards")).toBe('{"win":null}');
    expect(
        screen
            .getByRole("spinbutton", { name: "Win fixed credits" })
            .matches(":disabled"),
    ).toBe(true);
});

test("an unavailable editor offers review while retaining exact reload recovery", async () => {
    const unavailable = { ...editor, context: { unavailable: true } };
    const first = render(
        <ScheduleEditor
            editor={unavailable}
            phases={phases}
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByRole("button", { name: "Review current schedule" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    first.unmount();
    const retained = new URLSearchParams(editor.values).toString();
    sessionStorage.setItem(editor.recoveryKey, retained);
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ScheduleEditor
            editor={unavailable}
            phases={phases}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const data = new URLSearchParams(fetch.mock.calls[0][1].body);
    data.delete("csrfmiddlewaretoken");
    expect(data.toString()).toBe(retained);
    expect(navigate).toHaveBeenCalledWith("/cycles/");
});

test.each([
    ["", ""],
    ["2026-11-01", ""],
    ["", "2026-11-07"],
    ["2026-11-01", "2026-11-07"],
])(
    "cycle date edits submit independently optional bounds (%s, %s)",
    async (start, end) => {
        const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
        vi.stubGlobal("fetch", fetch);
        render(
            <ScheduleEditor
                editor={{
                    ...editor,
                    values: {
                        ...editor.values,
                        starts_on: start,
                        ends_on: end,
                    },
                }}
                phases={phases}
                onNavigate={vi.fn()}
            />,
        );
        expect(screen.getByLabelText("Start date")).toHaveProperty(
            "required",
            false,
        );
        expect(screen.getByLabelText("End date")).toHaveProperty(
            "required",
            false,
        );
        expect(
            screen.getByText(
                "Start and end dates are optional. You can set either one.",
            ),
        ).toBeTruthy();
        await userEvent.click(screen.getByRole("button", { name: "Save" }));
        expect(fetch.mock.calls[0][1].body.get("starts_on")).toBe(start);
        expect(fetch.mock.calls[0][1].body.get("ends_on")).toBe(end);
    },
);

test.each([true, false])(
    "planned settings name the actual next cycle while retaining legacy labels (%s)",
    (explicit) => {
        render(
            <ScheduleEditor
                editor={{
                    ...editor,
                    kind: "plan",
                    context: { nextCycleNumber: 4, needsDates: true },
                    values: {
                        request_key: "plan",
                        expected_revision: "1",
                        mode: "repeating",
                        steps: "[]",
                        date_start: "2027-01-01",
                        cycle_interval: "1",
                        cycle_unit: "weeks",
                        ...(explicit ? { date_mode: "planned" } : {}),
                    },
                }}
                phases={phases}
                onNavigate={vi.fn()}
            />,
        );
        expect(
            screen.getByLabelText(
                explicit ? "Cycle 4 starts" : "Cycle 1 starts",
            ),
        ).toBeTruthy();
    },
);

test("deleting the current phase retains its explicit replacement through an uncertain retry", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            phases={phases}
            onNavigate={vi.fn()}
            editor={{
                ...editor,
                kind: "delete-phase",
                heading: "Delete phase",
                lead: "Delete Opening and all its cycles.",
                context: {
                    savedCount: 3,
                    battleCount: 2,
                    futureCount: 4,
                    repeating: true,
                    replacesCurrent: true,
                    currentChoices: [
                        {
                            value: '{"cycle_id":"replacement"}',
                            label: "Cycle 4 · Downtime",
                        },
                    ],
                },
                values: {
                    request_key: "delete-command",
                    expected_revision: "2",
                    phase_id: "opening",
                    current_choice: "",
                },
            }}
        />,
    );
    expect(screen.getByText(/every repetition/)).toBeTruthy();
    expect(screen.getByText(/2 battles will have no phase/)).toBeTruthy();
    await userEvent.selectOptions(
        screen.getByLabelText("Current cycle after deletion"),
        "none",
    );
    await userEvent.click(screen.getByRole("button", { name: "Delete phase" }));
    expect(
        await screen.findByRole("button", { name: "Retry save" }),
    ).toBeTruthy();
    expect(
        screen.getByLabelText("Current cycle after deletion"),
    ).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch).toHaveBeenCalledTimes(2);
    const first = String(fetch.mock.calls[0][1].body);
    expect(new URLSearchParams(first).get("current_choice")).toBe("none");
    expect(String(fetch.mock.calls[1][1].body)).toBe(first);
});

test("single-cycle confirmation explains projected prefix and preserves the pattern", () => {
    render(
        <ScheduleEditor
            phases={phases}
            editor={{
                ...editor,
                kind: "delete-cycle",
                heading: "Delete cycle",
                context: { savedCount: 1, battleCount: 0, projectedPrefix: 3 },
                values: {
                    request_key: "delete-cycle",
                    expected_revision: "1",
                    target: '{"plan_id":"pattern","index":3}',
                    current_choice: "",
                },
            }}
        />,
    );
    expect(
        screen.getByText(/future pattern will remain unchanged/),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Current cycle after deletion")).toBeNull();
    expect(screen.queryByText(/0 battles will/)).toBeNull();
    expect(screen.getByText(/Battles and results will be kept/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete cycle" })).toBeTruthy();
});

test("starting after deletion posts an explicit surviving cycle", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            phases={phases}
            onNavigate={vi.fn()}
            editor={{
                ...editor,
                kind: "start",
                heading: "Start cycle",
                context: {
                    selectStart: true,
                    startChoices: [
                        {
                            value: '{"plan_id":"pattern","index":2}',
                            label: "Cycle 3 · Opening",
                        },
                    ],
                },
                values: {
                    request_key: "resume",
                    expected_revision: "3",
                    expected_current: "",
                    start_target: "",
                },
            }}
        />,
    );
    await userEvent.selectOptions(
        screen.getByLabelText("Cycle to start"),
        '{"plan_id":"pattern","index":2}',
    );
    await userEvent.click(screen.getByRole("button", { name: "Start cycle" }));
    expect(
        new URLSearchParams(String(fetch.mock.calls[0][1].body)).get(
            "start_target",
        ),
    ).toBe('{"plan_id":"pattern","index":2}');
});

test.each(["start", "end", "both"])(
    "clearing %s cycle dates leaves the other bound unchanged",
    async (bound) => {
        const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
        vi.stubGlobal("fetch", fetch);
        render(
            <ScheduleEditor
                phases={phases}
                onNavigate={vi.fn()}
                editor={{
                    ...editor,
                    values: {
                        ...editor.values,
                        starts_on: "2026-11-01",
                        ends_on: "2026-11-07",
                    },
                }}
            />,
        );
        const help = screen.getByText(
            "Start and end dates are optional. You can set either one.",
        );
        expect(
            screen
                .getByLabelText("Start date")
                .getAttribute("aria-describedby"),
        ).toContain(help.id);
        expect(
            screen.getByLabelText("End date").getAttribute("aria-describedby"),
        ).toContain(help.id);
        if (bound !== "end")
            await userEvent.click(
                screen.getByRole("button", { name: "Clear start date" }),
            );
        if (bound !== "start")
            await userEvent.click(
                screen.getByRole("button", { name: "Clear end date" }),
            );
        expect(fetch).not.toHaveBeenCalled();
        await userEvent.click(screen.getByRole("button", { name: "Save" }));
        expect(fetch).toHaveBeenCalledOnce();
        expect(fetch.mock.calls[0][1].body.get("starts_on")).toBe(
            bound === "end" ? "2026-11-01" : "",
        );
        expect(fetch.mock.calls[0][1].body.get("ends_on")).toBe(
            bound === "start" ? "2026-11-07" : "",
        );
    },
);

test("a missing old end offers a shift only when the new end reaches the following date", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ScheduleEditor
            phases={phases}
            onNavigate={vi.fn()}
            editor={{
                ...editor,
                context: {
                    shiftLater: { endsOn: "", followingOn: "2026-11-10" },
                },
                values: { ...editor.values, shift_later: "" },
            }}
        />,
    );
    fireEvent.change(screen.getByLabelText("End date"), {
        target: { value: "2026-11-08" },
    });
    expect(
        screen.queryByRole("switch", { name: "Move later cycle dates too" }),
    ).toBeNull();
    fireEvent.change(screen.getByLabelText("End date"), {
        target: { value: "2026-11-12" },
    });
    const shift = screen.getByRole("switch", {
        name: "Move later cycle dates too",
    });
    expect(shift.getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText(/3 days later/)).toBeTruthy();
    await userEvent.click(shift);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(fetch.mock.calls[0][1].body.get("starts_on")).toBe("");
    expect(fetch.mock.calls[0][1].body.get("ends_on")).toBe("2026-11-12");
    expect(fetch.mock.calls[0][1].body.get("shift_later")).toBe("on");
});

test.each([
    ["", ""],
    ["", "2026-11-09"],
    ["2026-11-07", ""],
])(
    "a shift is cleared when the replacement end cannot move following dates (%s, %s)",
    async (oldEnd, end) => {
        const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/cycles/" }));
        vi.stubGlobal("fetch", fetch);
        render(
            <ScheduleEditor
                phases={phases}
                onNavigate={vi.fn()}
                editor={{
                    ...editor,
                    context: {
                        shiftLater: {
                            endsOn: oldEnd,
                            followingOn: "2026-11-10",
                        },
                    },
                    values: {
                        ...editor.values,
                        starts_on: "2026-11-01",
                        shift_later: "",
                    },
                }}
            />,
        );
        fireEvent.change(screen.getByLabelText("End date"), {
            target: { value: "2026-11-12" },
        });
        await userEvent.click(
            screen.getByRole("switch", { name: "Move later cycle dates too" }),
        );
        fireEvent.change(screen.getByLabelText("End date"), {
            target: { value: end },
        });
        expect(
            screen.queryByRole("switch", {
                name: "Move later cycle dates too",
            }),
        ).toBeNull();
        await userEvent.click(screen.getByRole("button", { name: "Save" }));
        expect(fetch.mock.calls[0][1].body.get("shift_later")).toBe("");
        expect(fetch.mock.calls[0][1].body.get("starts_on")).toBe("2026-11-01");
        expect(fetch.mock.calls[0][1].body.get("ends_on")).toBe(end);
    },
);
