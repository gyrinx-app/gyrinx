import { render, screen, within } from "@testing-library/react";
import { useLayoutEffect } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ScheduleEditor } from "./ScheduleEditor";
import type { Editor, SetupDefinition } from "./types";

function definition(): SetupDefinition {
    const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        phases: [
            {
                id: "phase-1",
                details: {
                    name: "Phase 1",
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
        steps: [{ id: "step-1", phase_id: "phase-1", count: 1 }],
    };
}
function setup(): Editor {
    return {
        kind: "setup",
        heading: "Set up campaign phases & cycles",
        lead: "",
        context: { setupStage: 1, customDefinition: definition() },
        values: {
            request_key: "custom-key",
            template_id: "",
            setup_definition: JSON.stringify(definition()),
            mode: "fixed",
            current_number: "1",
            no_current: "on",
            date_start: "2026-11-01",
            cycle_interval: "1",
            cycle_unit: "weeks",
        },
        errors: {},
        initialConflict: false,
        current: null,
        templates: [
            {
                id: "template",
                name: "Occupation and Takeover",
                definition: {
                    ...definition(),
                    phases: [
                        {
                            ...definition().phases[0],
                            details: {
                                ...definition().phases[0].details,
                                name: "Occupation",
                            },
                        },
                    ],
                },
            },
        ],
        action: "/cycles/edit/setup/",
        commandHref: "/cycles/commands/setup/",
        csrfToken: "fresh-token",
        recoveryKey: "cycles:actor:campaign:setup",
        back: "/cycles/",
    };
}
afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
});

test("Custom is immediately usable and phase details survive review, Back and reload", async () => {
    const fetch = vi.fn().mockResolvedValue({
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ nextUrl: "/cycles/" }),
    });
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const editor = setup();
    const mounted = render(
        <ScheduleEditor editor={editor} phases={[]} onNavigate={navigate} />,
    );
    expect(
        (screen.getByLabelText("Starting schedule") as HTMLSelectElement).value,
    ).toBe("");
    expect(screen.getByText(/1. Phase 1/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(navigate).toHaveBeenLastCalledWith("/cycles/edit/setup/?step=2");
    await userEvent.click(
        screen.getByRole("button", { name: "Edit phase 1 details" }),
    );
    await userEvent.type(
        screen.getByLabelText("Phase 1 description"),
        "The gates open.",
    );
    await userEvent.type(
        screen.getByLabelText("Phase 1 effects"),
        "Use the opening missions.",
    );
    await userEvent.clear(screen.getByLabelText("Win fixed credits"));
    await userEvent.type(screen.getByLabelText("Win fixed credits"), "25");
    await userEvent.selectOptions(screen.getByLabelText("Win die type"), "6");
    await userEvent.clear(screen.getByLabelText("Win dice count"));
    await userEvent.type(screen.getByLabelText("Win dice count"), "2");
    await userEvent.clear(screen.getByLabelText("Win multiplier"));
    await userEvent.type(screen.getByLabelText("Win multiplier"), "10");
    await userEvent.clear(screen.getByLabelText("Win reputation"));
    await userEvent.type(screen.getByLabelText("Win reputation"), "2");
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
    expect(navigate).toHaveBeenLastCalledWith("/cycles/edit/setup/?step=3");
    expect(fetch).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(
        (screen.getByLabelText("Phase 1 description") as HTMLTextAreaElement)
            .value,
    ).toBe("The gates open.");
    mounted.unmount();
    render(
        <ScheduleEditor
            editor={{
                ...setup(),
                context: { ...editor.context, setupStage: 2 },
            }}
            phases={[]}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Edit phase 1 details" }),
    );
    expect(
        (screen.getByLabelText("Win fixed credits") as HTMLInputElement).value,
    ).toBe("25");
    expect(
        (screen.getByLabelText("Phase 1 effects") as HTMLTextAreaElement).value,
    ).toBe("Use the opening missions.");
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Set up phases & cycles" }),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("template_id")).toBe("");
    expect(body.get("no_current")).toBe("on");
    const saved = JSON.parse(body.get("setup_definition")!).phases[0].details;
    expect(saved.description).toBe("The gates open.");
    expect(saved.effects).toBe("Use the opening missions.");
    expect(saved.rewards.win).toEqual({
        credits: { fixed: 25, dice: { count: 2, sides: 6, multiplier: 10 } },
        reputation: 2,
    });
});

test("returning to Custom uses its own starting definition after template validation", async () => {
    const editor = setup();
    editor.values = {
        ...editor.values,
        template_id: "template",
        setup_definition: JSON.stringify(editor.templates[0].definition),
    };
    editor.errors = { current_number: ["Choose a cycle."] };
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    expect(screen.getByText(/1. Occupation/)).toBeTruthy();
    await userEvent.selectOptions(
        screen.getByLabelText("Starting schedule"),
        "",
    );
    expect(screen.getByText(/1. Phase 1/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("Phase 1");
});

test("adding phases opens one details editor and retains each phase's own rewards", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Edit phase 1 details" }),
    );
    await userEvent.type(
        screen.getByLabelText("Phase 1 description"),
        "First phase story.",
    );
    await userEvent.click(screen.getByRole("button", { name: "Add phase" }));
    expect(screen.getAllByLabelText("Win fixed credits")).toHaveLength(1);
    expect(
        (screen.getByLabelText("Phase 2 description") as HTMLTextAreaElement)
            .value,
    ).toBe("");
    await userEvent.type(
        screen.getByLabelText("Phase 2 description"),
        "Second phase story.",
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Edit phase 1 details" }),
    );
    expect(screen.getAllByLabelText("Win fixed credits")).toHaveLength(1);
    expect(
        (screen.getByLabelText("Phase 1 description") as HTMLTextAreaElement)
            .value,
    ).toBe("First phase story.");
});

test("an empty retained draft uses the new Custom default and keeps its dates", async () => {
    const editor = setup();
    sessionStorage.setItem(
        `${editor.recoveryKey}:setup-draft`,
        JSON.stringify({
            template_id: "",
            setup_definition: "",
            date_start: "2026-12-01",
        }),
    );
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    expect(screen.getByText(/1. Phase 1/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("Phase 1");
    expect(
        (screen.getByLabelText("Cycle 1 starts") as HTMLInputElement).value,
    ).toBe("2026-12-01");
});

test("new manual setup hides dates, retains optional dates when toggled, and saves without dates", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    editor.values.date_mode = "manual";
    const fetch = vi.fn().mockResolvedValue({
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ nextUrl: "/cycles/" }),
    });
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    expect(
        (
            screen.getByRole("radio", {
                name: /^No planned dates/,
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(screen.queryByLabelText("Cycle 1 starts")).toBeNull();
    expect(screen.getByText(/You advance cycles yourself/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("radio", { name: /^Plan cycle dates/ }),
    );
    expect(
        (screen.getByLabelText("Cycle 1 starts") as HTMLInputElement).value,
    ).toBe("2026-11-01");
    await userEvent.click(
        screen.getByRole("radio", { name: /^No planned dates/ }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Set up phases & cycles" }),
    );
    expect(fetch.mock.calls[0][1].body.get("date_mode")).toBe("manual");
});

test("old passive setup drafts retain their planned date selection", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    editor.values.date_mode = "manual";
    sessionStorage.setItem(
        `${editor.recoveryKey}:setup-draft`,
        JSON.stringify({
            date_start: "2026-12-01",
            cycle_interval: "2",
            cycle_unit: "months",
        }),
    );
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    expect(
        (
            screen.getByRole("radio", {
                name: /^Plan cycle dates/,
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (screen.getByLabelText("Cycle 1 starts") as HTMLInputElement).value,
    ).toBe("2026-12-01");
});

test("older uncertain dated setup retries its exact input against new manual defaults", async () => {
    const editor = setup();
    const original = new URLSearchParams(editor.values);
    sessionStorage.setItem(editor.recoveryKey, original.toString());
    editor.values.date_mode = "manual";
    editor.values.request_key = "fresh-key";
    const fetch = vi.fn().mockResolvedValue({
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ nextUrl: "/cycles/" }),
    });
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.has("date_mode")).toBe(false);
    expect(body.get("request_key")).toBe("custom-key");
    body.delete("csrfmiddlewaretoken");
    expect(body.toString()).toBe(original.toString());
});

test("schedule review exposes two named tables with row labels and values", () => {
    const editor = setup();
    editor.context.setupStage = 3;
    editor.values.date_mode = "manual";
    render(<ScheduleEditor editor={editor} phases={[]} />);
    const pattern = screen.getByRole("table", { name: "Phase pattern" });
    expect(
        within(pattern).getByRole("rowheader", { name: "1. Phase 1" }),
    ).toBeTruthy();
    expect(within(pattern).getByRole("cell", { name: "1 cycle" })).toBeTruthy();
    const settings = screen.getByRole("table", { name: "Schedule settings" });
    for (const label of ["Campaign length", "Cycle dates", "Current cycle"])
        expect(
            within(settings).getByRole("rowheader", { name: label }),
        ).toBeTruthy();
    expect(within(settings).getByRole("cell", { name: "Fixed" })).toBeTruthy();
    expect(
        within(settings).getByRole("cell", { name: "No planned dates" }),
    ).toBeTruthy();
    expect(within(settings).getByRole("cell", { name: "None" })).toBeTruthy();
});

test("a history destination renders its setup step before layout effects restore scrolling", () => {
    const editor = setup();
    const observed: string[] = [];
    function Page({ step }: { step: number }) {
        useLayoutEffect(() => {
            observed.push(
                document.getElementById("cycle-setup-step")?.textContent ?? "",
            );
        }, [step]);
        return (
            <ScheduleEditor
                editor={{
                    ...editor,
                    context: { ...editor.context, setupStage: step },
                }}
                phases={[]}
            />
        );
    }
    const view = render(<Page step={3} />);
    view.rerender(<Page step={2} />);
    expect(observed).toEqual(["Review schedule", "Customise schedule"]);
});

test("customisation separates numbered phases from mode-specific cycle options", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    render(<ScheduleEditor editor={editor} phases={[]} />);
    expect(
        screen.getByRole("heading", { level: 2, name: "Phases" }),
    ).toBeTruthy();
    expect(
        screen.getByRole("heading", { level: 2, name: "Cycles" }),
    ).toBeTruthy();
    expect(screen.queryByText("Customise your campaign")).toBeNull();
    const phase = screen.getByRole("region", { name: "Phase 1" });
    expect(within(phase).getByText("Name", { exact: true })).toBeTruthy();
    expect(
        within(phase).getByRole("textbox", { name: "Phase 1 name" }),
    ).toBeTruthy();
    const choices = screen.getByRole("group", { name: "Planning mode" });
    const options = screen.getByRole("region", { name: "Fixed plan options" });
    expect(
        choices.compareDocumentPosition(options) &
            Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
        screen.getByText("Choose whether the cycle steps run once or repeat."),
    ).toBeTruthy();
    await userEvent.click(
        within(choices).getByRole("radio", { name: /^Repeating pattern/ }),
    );
    expect(
        screen.queryByRole("region", { name: "Fixed plan options" }),
    ).toBeNull();
    expect(
        within(
            screen.getByRole("region", { name: "Repeating pattern options" }),
        ).getByText("Choose the cycle steps to repeat."),
    ).toBeTruthy();
});

test("phase overview remains available while its details expand and collapse", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    const draft = definition();
    draft.phases[0].details.description = "The opening phase story.";
    draft.phases[0].details.effects = "Choose opening missions.";
    draft.phases[0].details.rewards.win = {
        credits: { fixed: 25, dice: null },
        reputation: 2,
    };
    editor.values.setup_definition = JSON.stringify(draft);
    render(<ScheduleEditor editor={editor} phases={[]} />);
    expect(screen.getByText("The opening phase story.")).toBeTruthy();
    expect(screen.getByText("Win: 25¢, 2 reputation")).toBeTruthy();
    const edit = screen.getByRole("button", { name: "Edit phase 1 details" });
    expect(edit.getAttribute("aria-expanded")).toBe("false");
    expect(edit.querySelectorAll("svg")).toHaveLength(2);
    expect(screen.queryByLabelText("Phase 1 description")).toBeNull();
    await userEvent.click(
        screen.getByRole("button", { name: "Effects for Phase 1" }),
    );
    expect(screen.getByRole("dialog").textContent).toContain(
        "Choose opening missions.",
    );
    await userEvent.keyboard("{Escape}");
    await userEvent.click(edit);
    const collapse = screen.getByRole("button", {
        name: "Hide phase 1 details",
    });
    expect(collapse.getAttribute("aria-expanded")).toBe("true");
    expect(
        document.getElementById(collapse.getAttribute("aria-controls")!),
    ).toBeTruthy();
    await userEvent.clear(screen.getByLabelText("Phase 1 description"));
    await userEvent.type(
        screen.getByLabelText("Phase 1 description"),
        "A revised phase story.",
    );
    await userEvent.click(collapse);
    expect(screen.queryByLabelText("Phase 1 description")).toBeNull();
    expect(screen.getByText("A revised phase story.")).toBeTruthy();
});

test("setup starts with the selected cycle active and retains its number while switched off", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    editor.values.no_current = "";
    const fetch = vi.fn().mockResolvedValue({
        status: 200,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ nextUrl: "/cycles/" }),
    });
    vi.stubGlobal("fetch", fetch);
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    const active = screen.getByRole("switch", {
        name: "Start with cycle active",
    });
    expect(active.getAttribute("aria-checked")).toBe("true");
    expect(
        screen.getByText(
            "Make the selected cycle current when you save. Leave this off to activate a cycle later.",
        ),
    ).toBeTruthy();
    await userEvent.clear(screen.getByLabelText("Current cycle number"));
    await userEvent.type(screen.getByLabelText("Current cycle number"), "3");
    await userEvent.click(active);
    expect(active.getAttribute("aria-checked")).toBe("false");
    expect(screen.queryByLabelText("Current cycle number")).toBeNull();
    await userEvent.click(active);
    expect(
        (screen.getByLabelText("Current cycle number") as HTMLInputElement)
            .value,
    ).toBe("3");
    await userEvent.click(active);
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Set up phases & cycles" }),
    );
    expect(fetch.mock.calls[0][1].body.get("no_current")).toBe("on");
    expect(fetch.mock.calls[0][1].body.get("current_number")).toBe("3");
});

test("a restored sparse-reward draft remains readable and editable", async () => {
    const editor = setup();
    editor.context.setupStage = 2;
    const original = definition();
    const sparse = {
        ...original,
        phases: original.phases.map((phase) => ({
            ...phase,
            details: {
                ...phase.details,
                name: "Retained phase",
                rewards: { win: { reputation: 2 } },
            },
        })),
    };
    sessionStorage.setItem(
        `${editor.recoveryKey}:setup-draft`,
        JSON.stringify({
            setup_definition: JSON.stringify(sparse),
            date_mode: "manual",
        }),
    );
    render(<ScheduleEditor editor={editor} phases={[]} onNavigate={vi.fn()} />);
    expect(screen.getByLabelText("Phase 1 name")).toHaveProperty(
        "value",
        "Retained phase",
    );
    expect(screen.getByText("Win: 2 reputation")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Edit phase 1 details" }),
    );
    expect(screen.getByLabelText("Win fixed credits")).toHaveProperty(
        "value",
        "0",
    );
    expect(screen.getByLabelText("Win reputation")).toHaveProperty(
        "value",
        "2",
    );
    await userEvent.clear(screen.getByLabelText("Win fixed credits"));
    await userEvent.type(screen.getByLabelText("Win fixed credits"), "25");
    await userEvent.click(
        screen.getByRole("button", { name: "Hide phase 1 details" }),
    );
    expect(screen.getByText("Win: 25¢, 2 reputation")).toBeTruthy();
});
