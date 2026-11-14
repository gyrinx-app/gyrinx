import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { CampaignSchedule } from "./CampaignSchedule";
import type { Editor, ScheduleProps } from "./types";

const base = "/n26/campaigns/campaign/cycles/";
const edit = base + "edit/cycle/?cycle=one";
const editor: Editor = {
    kind: "cycle",
    heading: "Edit cycle",
    lead: "Dates are retained.",
    context: {},
    values: {
        request_key: "original-key",
        expected_revision: "1",
        target: '{"cycle_id":"one"}',
        phase_id: "phase",
        custom_name: "",
        starts_on: "2026-11-01",
        ends_on: "2026-11-07",
        description: "",
        effects: "",
    },
    errors: {},
    initialConflict: false,
    current: null,
    templates: [],
    action: edit,
    commandHref: base + "commands/cycle/?cycle=one",
    csrfToken: "fresh-csrf",
    recoveryKey: "cycle:user:campaign:one",
    back: base,
};
function data(open: Editor | null = null): ScheduleProps {
    const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        campaignName: "Ash Road",
        campaignHref: "/campaign/",
        scheduleHref: base,
        canManage: true,
        configured: true,
        status: "In progress",
        currentName: "Cycle 1",
        currentPhase: "Occupation",
        currentPhaseId: "phase",
        rows: [
            {
                key: "one",
                name: "Cycle 1",
                order: 1,
                phaseId: "phase",
                phaseName: "Occupation",
                state: "Current",
                startsOn: "2026-11-01",
                endsOn: "2026-11-07",
                description: "",
                effects: "",
                editHref: edit,
                href: base + "one/",
                startedAt: "",
                endedAt: "",
            },
        ],
        phases: [
            {
                id: "phase",
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
                editHref: base + "edit/phase/?phase=phase",
                duplicateHref: base + "edit/duplicate-phase/?phase=phase",
                deleteHref: "",
            },
        ],
        plan: null,
        actions: { plan: base + "edit/plan/" },
        previousHref: "",
        nextHref: "",
        moreHref: "",
        focusId: "",
        editor: open,
    };
}
const json = (schedule: ScheduleProps) => ({
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ schedule, notices: [] }),
});

test("the phase menu keeps its trigger busy while React navigation loads the editor", async () => {
    const initial = data();
    const phase = initial.phases[0];
    const phaseEditor: Editor = {
        ...editor,
        kind: "phase",
        heading: "Edit phase",
        action: phase.editHref,
        commandHref: base + "commands/phase/?phase=phase",
        recoveryKey: "phase:user:campaign:phase",
        back: base + "edit/plan/",
        values: {
            request_key: "phase-key",
            expected_revision: "1",
            phase_id: phase.id,
            name: phase.name,
            description: "",
            effects: "",
            rewards: JSON.stringify(phase.rewards),
        },
    };
    let finish!: (value: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const fetch = vi.fn().mockReturnValueOnce(slow);
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...initial} />);
    const trigger = screen.getByRole("button", {
        name: "More actions for Occupation",
    });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(screen.queryByRole("menu")).toBeNull();
    expect(trigger.getAttribute("aria-busy")).toBe("true");
    expect(trigger.getAttribute("data-busy")).toBe("on");
    expect(trigger).toHaveProperty("disabled", true);
    expect(
        screen.queryByRole("heading", { name: "Edit phase", level: 1 }),
    ).toBeNull();
    expect(
        screen
            .getByRole("link", { name: "Settings" })
            .hasAttribute("aria-busy"),
    ).toBe(false);
    await act(async () => finish(json(data(phaseEditor))));
    await screen.findByRole("heading", { name: "Edit phase", level: 1 });
    expect(trigger.isConnected).toBe(false);
    expect(window.location.pathname + window.location.search).toBe(
        phase.editHref,
    );
    expect(screen.getByLabelText("Phase name")).toHaveProperty(
        "value",
        "Occupation",
    );
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][1].headers).toEqual({
        Accept: "application/json",
    });
});

test.each([
    ["2026-11-01", "", "1 Nov 2026", "End date not set"],
    ["", "2026-11-07", "7 Nov 2026", "Start date not set"],
    ["2026-11-01", "2026-11-07", "1 Nov 2026", "7 Nov 2026"],
    ["", "", "Dates not set", "Dates not set"],
])(
    "shows saved date bounds and names missing dates",
    (startsOn, endsOn, saved, missing) => {
        const schedule = data();
        schedule.rows[0] = { ...schedule.rows[0], startsOn, endsOn };
        render(<CampaignSchedule {...schedule} />);
        const links = screen.getAllByRole("link", {
            name: /Edit dates for Cycle 1:/,
        });
        for (const link of links) {
            expect(link.textContent).toContain(saved);
            expect(link.textContent).toContain(missing);
            expect(link.getAttribute("aria-label")).toContain(saved);
            expect(link.getAttribute("aria-label")).toContain(missing);
        }
    },
);
beforeEach(() => {
    vi.stubGlobal("scrollX", 0);
    vi.stubGlobal("scrollY", 0);
    vi.spyOn(window, "scrollTo").mockImplementation(
        (options: number | ScrollToOptions) => {
            if (typeof options === "object") {
                vi.stubGlobal("scrollX", options.left ?? window.scrollX);
                vi.stubGlobal("scrollY", options.top ?? window.scrollY);
            }
        },
    );
    window.history.replaceState(null, "", base);
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

test("opening and closing an editor use JSON reads while retaining the schedule DOM", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce(json(data()));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    const row = document.getElementById("cycle-one")!;
    const trigger = screen.getByRole("link", { name: "Edit Cycle 1" });
    await userEvent.click(trigger);
    await screen.findByRole("dialog", { name: "Edit cycle" });
    expect(fetch.mock.calls[0][0]).toBe(edit);
    expect(fetch.mock.calls[0][1].headers.Accept).toBe("application/json");
    expect(window.location.pathname + window.location.search).toBe(edit);
    expect(row.isConnected).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(window.location.pathname).toBe(base);
    expect(row.isConnected).toBe(true);
    expect(document.activeElement).toBe(trigger);
    expect(window.scrollTo).not.toHaveBeenCalled();
});

test("a confirmed save refreshes rows through JSON and returns to the cycle anchor", async () => {
    const updated = data();
    updated.rows[0].name = "Market week";
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ nextUrl: base + "#cycle-one" }),
        })
        .mockResolvedValueOnce(json(updated));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    await userEvent.type(
        screen.getByRole("textbox", { name: "Custom cycle name" }),
        "Market week",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Market week", { selector: "span.font-medium" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(window.location.pathname + window.location.hash).toBe(
        base + "#cycle-one",
    );
    expect(fetch.mock.calls[1][1].method).toBe("POST");
    expect(fetch.mock.calls[1][1].body.get("request_key")).toBe("original-key");
    expect(fetch.mock.calls[2][0]).toBe(base);
});

test("the list date link opens a two-field editor and preserves the other cycle values", async () => {
    const dates = {
        ...editor,
        heading: "Edit cycle dates",
        context: { datesOnly: true },
        values: { ...editor.values, description: "Keep these rules." },
    };
    const updated = data();
    updated.rows[0].startsOn = "2026-11-08";
    updated.rows[0].endsOn = "2026-11-14";
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(dates)))
        .mockResolvedValueOnce({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ nextUrl: base + "#cycle-one" }),
        })
        .mockResolvedValueOnce(json(updated));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(
        screen.getAllByRole("link", {
            name: /Edit dates for Cycle 1: Start date/,
        })[0],
    );
    await screen.findByRole("dialog", { name: "Edit cycle dates" });
    expect(fetch.mock.calls[0][0]).toBe(edit + "&fields=dates");
    expect(
        screen.queryByRole("textbox", { name: "Custom cycle name" }),
    ).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Phase" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Start date"), {
        target: { value: "2026-11-08" },
    });
    fireEvent.change(screen.getByLabelText("End date"), {
        target: { value: "2026-11-14" },
    });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const body = fetch.mock.calls[1][1].body as URLSearchParams;
    expect(body.get("starts_on")).toBe("2026-11-08");
    expect(body.get("ends_on")).toBe("2026-11-14");
    expect(body.get("description")).toBe("Keep these rules.");
});

test("Back and Forward fetch fresh editor props without document navigation", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce(json(data()))
        .mockResolvedValueOnce(
            json(
                data({
                    ...editor,
                    values: { ...editor.values, request_key: "fresh-key" },
                }),
            ),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    window.history.back();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    window.history.forward();
    await screen.findByRole("dialog", { name: "Edit cycle" });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(
        document.querySelector<HTMLInputElement>('input[name="request_key"]')
            ?.value,
    ).toBe("fresh-key");
});

test("rapid Back then Forward cancels the obsolete read even when the editor is still rendered", async () => {
    let finish!: (response: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockReturnValueOnce(slow);
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    window.history.back();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    window.history.forward();
    await waitFor(() =>
        expect(window.location.pathname + window.location.search).toBe(edit),
    );
    await waitFor(() =>
        expect(fetch.mock.calls[1][1].signal.aborted).toBe(true),
    );
    await act(async () => finish(json(data())));
    expect(screen.getByRole("dialog", { name: "Edit cycle" })).toBeTruthy();
    expect(screen.queryByText("Loading schedule…")).toBeNull();
});

test("rapid Back twice restores the schedule and retains later viewport changes", async () => {
    vi.stubGlobal("scrollY", 1188);
    let finish!: (response: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce(json(data()))
        .mockReturnValueOnce(slow)
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce(json(data()));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    window.history.back();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    vi.stubGlobal("scrollY", 575);
    window.history.back();
    await waitFor(() =>
        expect(fetch.mock.calls[2][1].signal.aborted).toBe(true),
    );
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 1188,
            behavior: "instant",
        }),
    );
    await act(async () => finish(json(data(editor))));
    expect(screen.queryByRole("dialog")).toBeNull();

    vi.mocked(window.scrollTo).mockClear();
    vi.stubGlobal("scrollY", 1640);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    expect(window.scrollTo).not.toHaveBeenCalled();
    window.history.back();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 1640,
            behavior: "instant",
        }),
    );
    expect(fetch).toHaveBeenCalledTimes(5);
});

test("a failed cancel read cannot be retried while a save is pending or uncertain", async () => {
    let reject!: (error: Error) => void;
    const saving = new Promise<never>((_resolve, fail) => {
        reject = fail;
    });
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockRejectedValueOnce(new Error("Offline"))
        .mockReturnValueOnce(saving);
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByRole("button", { name: "Try again" });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(screen.getByRole("button", { name: "Try again" })).toHaveProperty(
        "disabled",
        true,
    );
    await act(async () => reject(new Error("Lost response")));
    await screen.findByText(/The save may have completed/);
    expect(screen.getByRole("button", { name: "Try again" })).toHaveProperty(
        "disabled",
        true,
    );
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(screen.getByRole("dialog", { name: "Edit cycle" })).toBeTruthy();
});

test("an unreadable editor leaves the current page intact and can be retried", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Offline"))
        .mockResolvedValueOnce(json(data(editor)));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("alert");
    expect(window.location.pathname).toBe(base);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
});

test("a failed refresh after a confirmed save retries only the read", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockResolvedValueOnce({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ nextUrl: base }),
        })
        .mockRejectedValueOnce(new Error("Offline"))
        .mockResolvedValueOnce(json(data()));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    expect(
        screen.getByRole("button", { name: "Save" }).matches(":disabled"),
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
        fetch.mock.calls.filter((call) => call[1].method === "POST"),
    ).toHaveLength(1);
});

test("Back cannot discard a pending or uncertain save", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(editor)))
        .mockRejectedValueOnce(new Error("Lost response"));
    vi.stubGlobal("fetch", fetch);
    const go = vi.spyOn(window.history, "go");
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Edit cycle" });
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    window.history.back();
    await waitFor(() => expect(go).toHaveBeenCalledWith(1));
    await waitFor(() =>
        expect(window.location.pathname + window.location.search).toBe(edit),
    );
    expect(screen.getByRole("button", { name: "Retry save" })).not.toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
});

test("a later editor request supersedes an earlier slow response", async () => {
    let finish!: (value: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const plan = {
        ...editor,
        kind: "plan",
        heading: "Settings",
        values: {
            request_key: "plan-key",
            expected_revision: "1",
            mode: "fixed",
            steps: "[]",
        },
    };
    const fetch = vi
        .fn()
        .mockReturnValueOnce(slow)
        .mockResolvedValueOnce(json(data(plan)));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    fireEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await userEvent.click(screen.getByRole("link", { name: "Settings" }));
    await screen.findByRole("heading", {
        level: 1,
        name: "Settings",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    await act(async () => finish(json(data(editor))));
    expect(screen.queryByRole("dialog", { name: "Edit cycle" })).toBeNull();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
});

test("Settings uses a full page and keeps loading inside its trigger", async () => {
    let finish!: (value: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const plan = {
        ...editor,
        kind: "plan",
        heading: "Settings",
        action: base + "edit/plan/",
        values: {
            request_key: "plan-key",
            expected_revision: "1",
            mode: "fixed",
            steps: "[]",
        },
    };
    const fetch = vi
        .fn()
        .mockReturnValueOnce(slow)
        .mockResolvedValueOnce(json(data()));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    const row = document.getElementById("cycle-one")!;
    const trigger = screen.getByRole("link", {
        name: "Settings",
    });
    await userEvent.click(trigger);
    expect(trigger.getAttribute("aria-busy")).toBe("true");
    expect(trigger.getAttribute("data-busy")).toBe("on");
    expect(screen.queryByText("Loading schedule…")).toBeNull();
    expect(row.isConnected).toBe(true);
    expect(window.scrollTo).not.toHaveBeenCalled();
    await act(async () => finish(json(data(plan))));
    const heading = await screen.findByRole("heading", {
        level: 1,
        name: "Settings",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(row.isConnected).toBe(false);
    expect(document.activeElement).toBe(heading);
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 0,
            behavior: "instant",
        }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByRole("heading", { level: 1, name: "Phases & cycles" });
    expect(window.location.pathname).toBe(base);
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledTimes(2));
});

test("schedule messages use dismissible design-system alerts and repeated saves show a fresh message", async () => {
    const initial = {
        ...data(),
        notices: [
            { message: "Campaign schedule saved.", tone: "success" as const },
        ],
    };
    const fetch = vi.fn().mockResolvedValue({
        ...json(data(editor)),
        json: async () => ({
            schedule: data(editor),
            notices: [{ message: "Campaign schedule saved.", tone: "success" }],
        }),
    });
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...initial} />);
    expect(screen.getByRole("alert").getAttribute("data-message")).toBe(
        "success",
    );
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText("Campaign schedule saved.")).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByText("Campaign schedule saved.");
    expect(screen.getByRole("alert").getAttribute("data-message")).toBe(
        "success",
    );
});

test("setup steps have URLs, retain edits through Back/Forward and refresh without retaining credentials", async () => {
    const action = base + "edit/setup/";
    window.history.replaceState(null, "", action);
    const setup: Editor = {
        ...editor,
        kind: "setup",
        heading: "Set up campaign phases & cycles",
        action,
        recoveryKey: "setup:actor:campaign",
        context: { setupStage: 1 },
        values: {
            request_key: "new-key",
            template_id: "",
            setup_definition: "",
            mode: "fixed",
            date_start: "2026-11-01",
            cycle_interval: "1",
            cycle_unit: "weeks",
            current_number: "1",
            no_current: "False",
        },
        templates: [
            {
                id: "template",
                name: "Opening pattern",
                definition: {
                    phases: [{ id: "phase", details: data().phases[0] }],
                    steps: [{ id: "step", phase_id: "phase", count: 3 }],
                },
            },
        ],
    };
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const view = render(<CampaignSchedule {...data(setup)} />);
    await userEvent.selectOptions(
        screen.getByLabelText("Starting schedule"),
        "template",
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(window.location.search).toBe("?step=2");
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 0,
            behavior: "instant",
        }),
    );
    vi.mocked(window.scrollTo).mockClear();
    fireEvent.change(screen.getByLabelText("Phase 1 name"), {
        target: { value: "My phase" },
    });
    const previous = {
        ...window.history.state,
        n26Schedule: { ...window.history.state.n26Schedule, index: 0 },
    };
    act(() => {
        window.history.replaceState(previous, "", action);
        window.dispatchEvent(
            new PopStateEvent("popstate", { state: previous }),
        );
    });
    expect(screen.getByLabelText("Starting schedule")).toBeTruthy();
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledOnce());
    vi.mocked(window.scrollTo).mockClear();
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("My phase");
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledOnce());
    vi.mocked(window.scrollTo).mockClear();
    vi.stubGlobal("scrollY", 1188);
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 0,
            behavior: "instant",
        }),
    );
    vi.mocked(window.scrollTo).mockClear();
    expect(window.location.search).toBe("?step=3");
    expect(screen.getByText(/1. My phase/)).toBeTruthy();
    const forward = window.history.state;
    act(() => {
        const back = {
            ...forward,
            n26Schedule: { ...forward.n26Schedule, index: 1 },
        };
        window.history.replaceState(back, "", action + "?step=2");
        window.dispatchEvent(new PopStateEvent("popstate", { state: back }));
        vi.stubGlobal("scrollY", 575);
    });
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("My phase");
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 1188,
            behavior: "instant",
        }),
    );
    vi.mocked(window.scrollTo).mockClear();
    act(() => {
        window.history.replaceState(forward, "", action + "?step=3");
        window.dispatchEvent(new PopStateEvent("popstate", { state: forward }));
    });
    expect(screen.getByText(/1. My phase/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 0,
            behavior: "instant",
        }),
    );
    const draft = sessionStorage.getItem(setup.recoveryKey + ":setup-draft")!;
    expect(draft).not.toContain("csrf");
    expect(draft).not.toContain("request_key");
    view.unmount();
    render(
        <CampaignSchedule
            {...data({
                ...setup,
                context: { setupStage: 3 },
                values: { ...setup.values, request_key: "fresh-key" },
                csrfToken: "rotated",
            })}
        />,
    );
    expect(screen.getByText(/1. My phase/)).toBeTruthy();
});

test("expanding the timeline keeps the viewport position", async () => {
    const initial = { ...data(), moreHref: base + "?preview=24" };
    const fetch = vi.fn().mockResolvedValue(json({ ...initial, moreHref: "" }));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...initial} />);
    await userEvent.click(
        screen.getByRole("link", { name: "Preview more cycles" }),
    );
    await waitFor(() => expect(window.location.search).toBe("?preview=24"));
    expect(
        screen.queryByRole("link", { name: "Preview more cycles" }),
    ).toBeNull();
    expect(window.scrollTo).not.toHaveBeenCalled();
});

test("a failed page read keeps the viewport until the destination is loaded", async () => {
    const plan = {
        ...editor,
        kind: "plan",
        heading: "Settings",
        action: base + "edit/plan/",
        values: {
            request_key: "plan-key",
            expected_revision: "1",
            mode: "fixed",
            steps: "[]",
        },
    };
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Offline"))
        .mockResolvedValueOnce(json(data(plan)));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Settings" }));
    await screen.findByRole("alert");
    expect(window.scrollTo).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("heading", {
        level: 1,
        name: "Settings",
    });
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 0,
            behavior: "instant",
        }),
    );
});

test("Back restores saved coordinates after an asynchronous destination replaces a shorter page", async () => {
    const replace = vi.spyOn(window.history, "replaceState");
    vi.stubGlobal("scrollY", 1188);
    const plan = {
        ...editor,
        kind: "plan",
        heading: "Settings",
        action: base + "edit/plan/",
        values: {
            request_key: "plan-key",
            expected_revision: "1",
            mode: "fixed",
            steps: "[]",
        },
    };
    let finish!: (value: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(plan)))
        .mockReturnValueOnce(slow);
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...data()} />);
    await userEvent.click(screen.getByRole("link", { name: "Settings" }));
    await screen.findByRole("heading", {
        level: 1,
        name: "Settings",
    });
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalledOnce());
    const source = replace.mock.calls.find(
        ([state]) => state?.n26Schedule?.scroll?.top === 1188,
    )![0];
    expect(source.n26Schedule.scroll).toEqual({ left: 0, top: 1188 });
    vi.mocked(window.scrollTo).mockClear();
    vi.stubGlobal("scrollY", 0);
    act(() => {
        window.history.replaceState(source, "", base);
        window.dispatchEvent(new PopStateEvent("popstate", { state: source }));
        vi.stubGlobal("scrollY", 575);
    });
    expect(window.scrollTo).not.toHaveBeenCalled();
    expect(
        screen.getByRole("heading", {
            level: 1,
            name: "Settings",
        }),
    ).toBeTruthy();
    await act(async () => finish(json(data())));
    await screen.findByRole("heading", { level: 1, name: "Phases & cycles" });
    await waitFor(() =>
        expect(window.scrollTo).toHaveBeenCalledExactlyOnceWith({
            left: 0,
            top: 1188,
            behavior: "instant",
        }),
    );
});

function settingsEditor(revision = "1"): Editor {
    return {
        ...editor,
        kind: "plan",
        heading: "Settings",
        action: base + "edit/plan/",
        commandHref: base + "commands/plan/",
        recoveryKey: "plan:user:campaign",
        values: {
            request_key: `plan-key-${revision}`,
            expected_revision: revision,
            mode: "fixed",
            steps: JSON.stringify([
                { id: "step", phase_id: "phase", count: 2 },
            ]),
            date_mode: "manual",
            date_start: "",
            cycle_interval: "1",
            cycle_unit: "weeks",
        },
    };
}

function phaseEditor(kind = "phase"): Editor {
    return {
        ...editor,
        kind,
        heading: kind === "phase" ? "Edit phase" : "Add phase",
        action: base + `edit/${kind}/?phase=phase`,
        commandHref: base + `commands/${kind}/?phase=phase`,
        recoveryKey: "phase:user:campaign",
        back: base + "edit/plan/",
        values: {
            request_key: "phase-key",
            expected_revision: "1",
            phase_id: "phase",
            name: "Occupation",
            description: "",
            effects: "",
            rewards: JSON.stringify(data().phases[0].rewards),
        },
    };
}

test("phase edits return to settings with its draft and fresh revision, key and CSRF", async () => {
    const settings = settingsEditor();
    const updated = { ...settingsEditor("2"), csrfToken: "updated-csrf" };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json(data(phaseEditor())))
        .mockResolvedValueOnce({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ nextUrl: settings.action }),
        })
        .mockResolvedValueOnce(json(data(updated)))
        .mockResolvedValueOnce({
            status: 200,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ nextUrl: base }),
        })
        .mockResolvedValueOnce(json(data()));
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState(null, "", settings.action);
    const initial = data(settings);
    initial.actions.addPhase = base + "edit/add-phase/";
    render(<CampaignSchedule {...initial} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
        screen.getByRole("link", { name: "Add phase" }).getAttribute("href"),
    ).toBe(initial.actions.addPhase);
    await userEvent.clear(screen.getByLabelText("Step 1 cycles"));
    await userEvent.type(screen.getByLabelText("Step 1 cycles"), "7");
    await userEvent.click(
        screen.getByRole("radio", { name: /^Repeating pattern/ }),
    );
    await userEvent.click(
        screen.getByRole("link", { name: "Edit Occupation" }),
    );
    await screen.findByRole("heading", { level: 1, name: "Edit phase" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
        screen.queryByRole("heading", { level: 1, name: settings.heading }),
    ).toBeNull();
    expect(document.title).toContain("Edit phase");
    await userEvent.type(screen.getByLabelText("Phase name"), " updated");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { level: 1, name: settings.heading });
    expect(window.location.pathname).toBe(settings.action);
    expect(screen.getByLabelText("Step 1 cycles")).toHaveProperty("value", "7");
    expect(
        screen.getByRole("radio", { name: /^Repeating pattern/ }),
    ).toHaveProperty("checked", true);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("heading", { level: 1, name: "Phases & cycles" });
    const payload = fetch.mock.calls[3][1].body as URLSearchParams;
    expect(payload.get("expected_revision")).toBe("2");
    expect(payload.get("request_key")).toBe("plan-key-2");
    expect(payload.get("csrfmiddlewaretoken")).toBe("updated-csrf");
    expect(JSON.parse(payload.get("steps")!)[0].count).toBe(7);
});

test("Back and Forward between phase settings and a phase editor retain the editable draft", async () => {
    const settings = settingsEditor();
    const replace = vi.spyOn(window.history, "replaceState");
    const push = vi.spyOn(window.history, "pushState");
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValueOnce(json(data(phaseEditor())))
            .mockResolvedValueOnce(json(data(settingsEditor("2"))))
            .mockResolvedValueOnce(json(data(phaseEditor()))),
    );
    window.history.replaceState(null, "", settings.action);
    render(<CampaignSchedule {...data(settings)} />);
    const source = replace.mock.calls.at(-1)![0];
    await userEvent.clear(screen.getByLabelText("Step 1 cycles"));
    await userEvent.type(screen.getByLabelText("Step 1 cycles"), "9");
    await userEvent.click(
        screen.getByRole("link", { name: "Edit Occupation" }),
    );
    await screen.findByRole("heading", { name: "Edit phase", level: 1 });
    const target = push.mock.calls.at(-1)![0];
    act(() => {
        window.history.replaceState(source, "", settings.action);
        window.dispatchEvent(new PopStateEvent("popstate", { state: source }));
    });
    await screen.findByRole("heading", { name: settings.heading, level: 1 });
    expect(screen.getByLabelText("Step 1 cycles")).toHaveProperty("value", "9");
    act(() => {
        window.history.replaceState(target, "", phaseEditor().action);
        window.dispatchEvent(new PopStateEvent("popstate", { state: target }));
    });
    await screen.findByRole("heading", { name: "Edit phase", level: 1 });
    expect(screen.getByLabelText("Phase name")).toHaveProperty(
        "value",
        "Occupation",
    );
});

test("an uncertain settings save blocks phase links until its original command is confirmed", async () => {
    const settings = settingsEditor();
    const fetch = vi.fn().mockRejectedValueOnce(new Error("Lost response"));
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState(null, "", settings.action);
    render(<CampaignSchedule {...data(settings)} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Retry save" });
    await userEvent.click(
        screen.getByRole("link", { name: "Edit Occupation" }),
    );
    expect(fetch).toHaveBeenCalledOnce();
    expect(window.location.pathname).toBe(settings.action);
    expect(
        screen.getByRole("heading", { level: 1, name: settings.heading }),
    ).toBeTruthy();
});

test.each(["fixed", "repeating"])(
    "deleting the current phase into a projected replacement saves the reconciled settings draft (%s)",
    async (mode) => {
        const repeating = mode === "repeating";
        const opening = {
            id: "opening-step",
            phase_id: "phase",
            count: repeating ? 1 : 2,
        };
        const downtime = {
            id: "downtime-step",
            phase_id: "downtime",
            count: repeating ? 2 : 4,
        };
        const settings = settingsEditor();
        settings.context = {
            savedStepCounts: { "opening-step": 1 },
            fixedSteps: [downtime],
        };
        settings.values = {
            ...settings.values,
            mode,
            steps: JSON.stringify([opening, downtime]),
            date_mode: "planned",
            date_start: "2026-11-08",
        };
        const initial = data(settings);
        initial.phases[0].deleteHref = base + "edit/delete-phase/?phase=phase";
        initial.phases.push({
            ...initial.phases[0],
            id: "downtime",
            name: "Downtime",
            count: 0,
        });
        const deletion: Editor = {
            ...phaseEditor("delete-phase"),
            heading: "Delete phase",
            context: {
                planRecoveryKey: settings.recoveryKey,
                replacesCurrent: true,
                currentChoices: [
                    {
                        value: repeating
                            ? '{"plan_id":"plan","index":4}'
                            : '{"plan_id":"plan","index":3}',
                        label: repeating
                            ? "Cycle 5 · Downtime"
                            : "Cycle 4 · Downtime",
                    },
                ],
            },
            values: {
                request_key: "delete-key",
                expected_revision: "1",
                phase_id: "phase",
                current_choice: "",
            },
        };
        const fresh = settingsEditor("2");
        fresh.context = {
            fixedSteps: [{ ...downtime, count: repeating ? 1 : 2 }],
            savedStepCounts: {
                "opening-step": repeating ? 2 : 3,
                "downtime-step": repeating ? 3 : 2,
            },
        };
        fresh.values = {
            ...fresh.values,
            mode,
            steps: JSON.stringify([{ ...downtime, count: 2 }]),
            date_mode: "planned",
            date_start: "2026-11-22",
        };
        const returned = { ...data(fresh), phases: initial.phases.slice(1) };
        const saved = (value: Record<string, unknown>, status = 200) => ({
            status,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => value,
        });
        const fetch = vi
            .fn()
            .mockResolvedValueOnce(json({ ...initial, editor: deletion }))
            .mockResolvedValueOnce(
                saved({ nextUrl: settings.action, revision: 2 }),
            )
            .mockResolvedValueOnce(json(returned))
            .mockImplementationOnce((_url, request) =>
                request.body.get("expected_revision") === "2"
                    ? saved({ nextUrl: base })
                    : saved(
                          {
                              code: "revision_conflict",
                              errors: { __all__: ["The schedule changed."] },
                              current: {
                                  revision: 2,
                                  cycle: "Cycle 4",
                                  phase: "Downtime",
                              },
                          },
                          409,
                      ),
            )
            .mockResolvedValueOnce(json(data()));
        vi.stubGlobal("fetch", fetch);
        window.history.replaceState(null, "", settings.action);
        render(<CampaignSchedule {...initial} />);
        if (repeating)
            await userEvent.click(
                screen.getByRole("radio", { name: /^Fixed plan/ }),
            );
        const count = screen.getByLabelText(
            repeating ? "Step 1 cycles" : "Step 2 cycles",
        );
        await userEvent.clear(count);
        await userEvent.type(count, repeating ? "5" : "7");
        fireEvent.change(screen.getByLabelText("Cycle 1 starts"), {
            target: { value: "2026-12-10" },
        });
        await userEvent.click(
            screen.getByRole("link", { name: "Delete Occupation" }),
        );
        await screen.findByRole("heading", { level: 1, name: "Delete phase" });
        await userEvent.selectOptions(
            screen.getByLabelText("Current cycle after deletion"),
            repeating
                ? '{"plan_id":"plan","index":4}'
                : '{"plan_id":"plan","index":3}',
        );
        await userEvent.click(
            screen.getByRole("button", { name: "Delete phase" }),
        );
        await screen.findByRole("heading", {
            level: 1,
            name: settings.heading,
        });
        expect(screen.getByLabelText("Step 1 cycles")).toHaveProperty(
            "value",
            repeating ? "2" : "5",
        );
        expect(screen.getByLabelText("Cycle 1 starts")).toHaveProperty(
            "value",
            "2026-12-10",
        );
        await userEvent.click(screen.getByRole("button", { name: "Save" }));
        await screen.findByRole("heading", {
            level: 1,
            name: "Phases & cycles",
        });
        const payload = fetch.mock.calls[3][1].body as URLSearchParams;
        expect(payload.get("expected_revision")).toBe("2");
        expect(JSON.parse(payload.get("steps")!)).toEqual([
            { ...downtime, count: repeating ? 2 : 5 },
        ]);
        expect(payload.get("date_start")).toBe("2026-12-10");
    },
);
