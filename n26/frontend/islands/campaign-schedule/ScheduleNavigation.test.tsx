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
        screen.getAllByRole("link", { name: "Edit dates for Cycle 1" })[0],
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
    await screen.findByRole("dialog", { name: "Schedule settings" });
    await act(async () => finish(json(data(editor))));
    expect(screen.queryByRole("dialog", { name: "Edit cycle" })).toBeNull();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
});
