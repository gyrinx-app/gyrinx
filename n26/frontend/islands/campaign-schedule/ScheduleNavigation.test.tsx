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
        date_version: "1",
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

test.each([
    ["2026-11-01", "", "1 Nov 2026", "End date not set"],
    ["", "2026-11-07", "7 Nov 2026", "Start date not set"],
])(
    "keeps a saved endpoint visible when the other date is missing",
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
        heading: "Schedule settings",
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
    await userEvent.click(
        screen.getByRole("link", { name: "Schedule settings" }),
    );
    await screen.findByRole("heading", { level: 1, name: "Schedule settings" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await act(async () => finish(json(data(editor))));
    expect(screen.queryByRole("dialog", { name: "Edit cycle" })).toBeNull();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
});

test("Schedule settings uses a full page and keeps loading inside its trigger", async () => {
    let finish!: (value: ReturnType<typeof json>) => void;
    const slow = new Promise<ReturnType<typeof json>>((resolve) => {
        finish = resolve;
    });
    const plan = {
        ...editor,
        kind: "plan",
        heading: "Schedule settings",
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
    const trigger = screen.getByRole("link", { name: "Schedule settings" });
    await userEvent.click(trigger);
    expect(trigger.getAttribute("aria-busy")).toBe("true");
    expect(trigger.getAttribute("data-busy")).toBe("on");
    expect(screen.queryByText("Loading schedule…")).toBeNull();
    expect(row.isConnected).toBe(true);
    await act(async () => finish(json(data(plan))));
    const heading = await screen.findByRole("heading", {
        level: 1,
        name: "Schedule settings",
    });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(row.isConnected).toBe(false);
    expect(document.activeElement).toBe(heading);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByRole("heading", { level: 1, name: "Phases & cycles" });
    expect(window.location.pathname).toBe(base);
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
        screen.getByLabelText("Starting template"),
        "template",
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(window.location.search).toBe("?step=2");
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
    expect(screen.getByLabelText("Starting template")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Customise schedule" }),
    );
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("My phase");
    await userEvent.click(
        screen.getByRole("button", { name: "Review schedule" }),
    );
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
    });
    expect(
        (screen.getByLabelText("Phase 1 name") as HTMLInputElement).value,
    ).toBe("My phase");
    act(() => {
        window.history.replaceState(forward, "", action + "?step=3");
        window.dispatchEvent(new PopStateEvent("popstate", { state: forward }));
    });
    expect(screen.getByText(/1. My phase/)).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
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
