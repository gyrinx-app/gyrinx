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
const move = base + "edit/move-cycle/?cycle=two";
const phaseMove = base + "edit/move-phase/?phase=second";
const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
function overview(): ScheduleProps {
    return {
        campaignName: "Ash Road",
        campaignHref: "/campaign/",
        scheduleHref: base,
        canManage: true,
        configured: true,
        status: "In progress",
        currentName: "Cycle 1",
        currentPhase: "Occupation",
        currentPhaseId: "first",
        phases: ["first", "second", "empty"].map((id, index) => ({
            id,
            phaseId: "rules",
            number: index + 1,
            name:
                id === "first"
                    ? "Occupation"
                    : id === "second"
                      ? "Downtime"
                      : "Empty",
            description: "",
            effects: "",
            count: id === "empty" ? 0 : 1,
            rewards: {
                win: reward,
                draw: reward,
                loss: reward,
                entry_credits: reward.credits,
            },
            editHref: "",
            duplicateHref: "",
            deleteHref: "",
            moveHref: id === "second" ? phaseMove : "",
        })),
        rows: ["one", "two", "ghost"].map((key, index) => ({
            key,
            name: `Cycle ${index + 1}`,
            order: index + 1,
            phaseId: "rules",
            occurrenceId: index === 0 ? "first" : "second",
            phaseName: "Occupation",
            state:
                index === 0 ? "Current" : index === 2 ? "Projected" : "Future",
            startsOn: "",
            endsOn: "",
            description: "",
            effects: "",
            href: "",
            editHref: base + `edit/cycle/?cycle=${key}`,
            startedAt: "",
            endedAt: "",
            moveHref: index === 1 ? move : "",
        })),
        plan: null,
        actions: {},
        previousHref: "",
        nextHref: "",
        moreHref: "",
        focusId: "",
        editor: null,
        reorder: {
            revision: 4,
            sources: [
                {
                    id: "cycle:two",
                    label: "Cycle 2",
                    origin: "cycle-start:second",
                    targets: ["cycle-after:one", "cycle-start:empty"],
                    moveHref: move,
                },
                {
                    id: "phase:second",
                    label: "Phase 2: Downtime",
                    origin: "phase-after:first",
                    targets: ["phase-after:empty"],
                    moveHref: phaseMove,
                },
            ],
            targets: [
                {
                    id: "cycle-after:one",
                    label: "After Cycle 1",
                    kind: "cycle",
                    occurrenceId: "first",
                    afterId: "one",
                },
                {
                    id: "phase-after:first",
                    label: "After phase 1: Occupation",
                    kind: "phase",
                    occurrenceId: "first",
                    afterId: "first",
                },
                {
                    id: "cycle-start:second",
                    label: "Start of phase 2",
                    kind: "cycle",
                    occurrenceId: "second",
                    afterId: null,
                },
                {
                    id: "cycle-after:two",
                    label: "After Cycle 2",
                    kind: "cycle",
                    occurrenceId: "second",
                    afterId: "two",
                },
                {
                    id: "phase-after:second",
                    label: "After phase 2: Downtime",
                    kind: "phase",
                    occurrenceId: "second",
                    afterId: "second",
                },
                {
                    id: "cycle-start:empty",
                    label: "Start of phase 3: Empty",
                    kind: "cycle",
                    occurrenceId: "empty",
                    afterId: null,
                },
                {
                    id: "phase-after:empty",
                    label: "After phase 3: Empty",
                    kind: "phase",
                    occurrenceId: "empty",
                    afterId: "empty",
                },
            ],
        },
    };
}
function editor(kind = "move-cycle", revision = "4"): Editor {
    return {
        kind,
        heading: kind === "move-phase" ? "Move phase" : "Move cycle",
        lead: "Existing dates are kept.",
        context: {
            timelineOccurrences: overview().phases.map((phase) => ({
                ...phase,
                cycles: overview()
                    .rows.filter(
                        (cycle) =>
                            cycle.state !== "Projected" &&
                            cycle.occurrenceId === phase.id,
                    )
                    .map((cycle) => ({
                        id: cycle.key,
                        name: cycle.name,
                        order: cycle.order,
                    })),
            })),
            selectedCycle: {
                id: "two",
                name: "Cycle 2",
                order: 2,
                occurrenceId: "second",
            },
        },
        values: {
            request_key: "fresh-key",
            expected_revision: revision,
            ...(kind === "move-phase"
                ? { occurrence_id: "second", after_occurrence_id: "first" }
                : {
                      cycle_id: "two",
                      occurrence_id: "second",
                      after_cycle_id: "",
                  }),
        },
        errors: {},
        initialConflict: false,
        current: null,
        templates: [],
        action: kind === "move-phase" ? phaseMove : move,
        commandHref:
            base +
            `commands/${kind}/?${kind === "move-phase" ? "phase=second" : "cycle=two"}`,
        csrfToken: "fresh-csrf",
        recoveryKey: "move:user:campaign:two",
        back: base,
    };
}
const json = (data: object, status = 200) => ({
    ok: status < 400,
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
const prepared = (open = editor()) =>
    json({ schedule: { ...overview(), editor: open } });
const saved = () => json({ nextUrl: base + "#cycle-two", revision: 5 });
const refreshed = () => json({ schedule: overview() });
function lift(name = "Move Cycle 2") {
    const handle = screen.getByRole("button", { name });
    handle.focus();
    fireEvent.keyDown(handle, { key: " " });
    return handle;
}
function drop(key = "End", name?: string) {
    const handle = lift(name);
    fireEvent.keyDown(handle, { key });
    fireEvent.keyDown(handle, { key: " " });
}
beforeEach(() => {
    window.history.replaceState(null, "", base);
    sessionStorage.clear();
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(window, "scrollTo").mockImplementation(() => {});
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
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    sessionStorage.clear();
});

test("only eligible saved rows and blocks have handles; boundaries are unique and precede ghosts", () => {
    const { container } = render(<CampaignSchedule {...overview()} />);
    expect(screen.queryByRole("button", { name: "Move Cycle 1" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Move Cycle 3" })).toBeNull();
    expect(
        screen.getByRole("button", { name: "Move Cycle 2" }).closest("tr")?.id,
    ).toBe("cycle-two");
    expect(
        screen
            .getByRole("button", { name: "Move Phase 2: Downtime" })
            .closest("section")?.id,
    ).toBe("phase-second");
    expect(
        container.querySelectorAll(
            '[data-reorder-target="phase-after:second"]',
        ),
    ).toHaveLength(1);
    const boundary = container.querySelector(
        '[data-reorder-target="phase-after:second"]',
    )!;
    const ghost = container.querySelector("#cycle-ghost")!;
    expect(
        boundary.compareDocumentPosition(ghost) &
            Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
        container.querySelector('[data-reorder-target="cycle-start:empty"]'),
    ).not.toBeNull();
    expect(screen.getByRole("link", { name: "Edit Cycle 2" })).toBeTruthy();
});

test("an empty saved phase keeps its visible start gap when it contains generated previews", () => {
    const data = overview();
    data.rows = data.rows.map((row) =>
        row.state === "Projected" ? { ...row, occurrenceId: "empty" } : row,
    );
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<CampaignSchedule {...data} />);
    const boundary = container.querySelector(
        '[data-reorder-target="cycle-start:empty"]',
    );
    expect(boundary).not.toBeNull();
    expect(
        boundary!.compareDocumentPosition(
            container.querySelector("#cycle-ghost")!,
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.queryByText("No cycles in this phase.")).toBeNull();
    const handle = lift();
    fireEvent.keyDown(handle, { key: "End" });
    expect(boundary!.getAttribute("data-reorder-active")).toBe("true");
    expect(screen.queryByRole("button", { name: "Move Cycle 3" })).toBeNull();
    fireEvent.keyDown(handle, { key: "Escape" });
    expect(fetch).not.toHaveBeenCalled();
});

test("read-only pages never expose drag handles", () => {
    render(<CampaignSchedule {...overview()} canManage={false} />);
    expect(screen.queryByRole("button", { name: /^Move / })).toBeNull();
});

test("pagination does not turn a clipped phase start into an insertion boundary", () => {
    const data = overview();
    data.rows = data.rows.filter((cycle) => cycle.key !== "one");
    data.phases[1].count = 12;
    data.reorder!.targets = data.reorder!.targets.filter(
        (target) => target.id !== "cycle-start:second",
    );
    data.reorder!.sources[0].origin = "cycle-after:offpage";
    const { container } = render(<CampaignSchedule {...data} />);
    expect(
        container.querySelector('[data-reorder-target="cycle-start:second"]'),
    ).toBeNull();
    expect(
        container.querySelector('[data-reorder-target="phase-after:second"]'),
    ).not.toBeNull();
});

test("a drop prepares canonical Move, posts destination with its fresh key, refreshes and restores handle focus", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(fetch.mock.calls[0][0]).toBe(move);
    expect(fetch.mock.calls[0][1].method).toBeUndefined();
    expect(fetch.mock.calls[1][1].method).toBe("POST");
    const body = fetch.mock.calls[1][1].body as URLSearchParams;
    expect(Object.fromEntries(body)).toMatchObject({
        cycle_id: "two",
        occurrence_id: "empty",
        after_cycle_id: "",
        expected_revision: "4",
        request_key: "fresh-key",
        csrfmiddlewaretoken: "fresh-csrf",
    });
    await waitFor(() =>
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Move Cycle 2" }),
        ),
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(HTMLDialogElement.prototype.showModal).not.toHaveBeenCalled();
});

test("whole block drops use the phase destination, retaining the selected occurrence", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared(editor("move-phase")))
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop("End", "Move Phase 2: Downtime");
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(fetch.mock.calls[0][0]).toBe(phaseMove);
    expect(Object.fromEntries(fetch.mock.calls[1][1].body)).toMatchObject({
        occurrence_id: "second",
        after_occurrence_id: "empty",
    });
});

test("a moved phase without destinations is revealed and focused at its heading", async () => {
    const after = overview();
    after.currentName = "No current cycle";
    after.currentPhaseId = "";
    after.phases = after.phases.filter((phase) => phase.id === "second");
    after.rows = after.rows.filter((row) => row.key === "two");
    after.reorder = { revision: 5, sources: [], targets: [] };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared(editor("move-phase")))
        .mockResolvedValueOnce(
            json({ nextUrl: base + "?page=3#phase-second", revision: 5 }),
        )
        .mockResolvedValueOnce(json({ schedule: after }));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<CampaignSchedule {...overview()} />);
    drop("End", "Move Phase 2: Downtime");
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    const heading = screen.getByRole("heading", { name: "Phase 2: Downtime" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(heading.getAttribute("tabindex")).toBe("-1");
    expect(vi.mocked(Element.prototype.scrollIntoView).mock.contexts).toContain(
        heading,
    );
    expect(container.querySelector("#phase-second")).not.toBeNull();
    expect(
        screen.queryByRole("button", { name: "Move Phase 2: Downtime" }),
    ).toBeNull();
    expect(window.location.search).toBe("?page=3");
    expect(window.location.hash).toBe("#phase-second");
});

test("a moved cycle without visible destinations is revealed and focused at its row", async () => {
    const after = overview();
    after.currentName = "No current cycle";
    after.currentPhaseId = "";
    after.phases = after.phases
        .filter((phase) => phase.id === "empty")
        .map((phase) => ({ ...phase, count: 1 }));
    after.rows = after.rows
        .filter((row) => row.key === "two")
        .map((row) => ({ ...row, occurrenceId: "empty" }));
    after.reorder = { revision: 5, sources: [], targets: [] };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(
            json({ nextUrl: base + "?page=3#cycle-two", revision: 5 }),
        )
        .mockResolvedValueOnce(json({ schedule: after }));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<CampaignSchedule {...overview()} />);
    drop();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    const row = container.querySelector("#cycle-two")!;
    await waitFor(() => expect(document.activeElement).toBe(row));
    expect(row.getAttribute("tabindex")).toBe("-1");
    expect(vi.mocked(Element.prototype.scrollIntoView).mock.contexts).toContain(
        row,
    );
    expect(screen.queryByRole("button", { name: "Move Cycle 2" })).toBeNull();
    expect(window.location.search).toBe("?page=3");
    expect(window.location.hash).toBe("#cycle-two");
});

test("dropping at the unchanged origin performs no read or write", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    const handle = lift();
    fireEvent.keyDown(handle, { key: " " });
    expect(fetch).not.toHaveBeenCalled();
});

test.each(["stale", "invalid", "conflict", "unavailable"])(
    "a %s preparation reports inline without opening a dialog or saving",
    async (reason) => {
        const open = editor("move-cycle", reason === "stale" ? "5" : "4");
        if (reason === "invalid")
            open.errors = { __all__: ["These dates overlap."] };
        if (reason === "conflict") open.initialConflict = true;
        if (reason === "unavailable") open.context.unavailable = true;
        const fetch = vi.fn().mockResolvedValueOnce(prepared(open));
        vi.stubGlobal("fetch", fetch);
        render(<CampaignSchedule {...overview()} />);
        drop();
        await screen.findByRole("alert", {
            name: "Move could not be completed",
        });
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(HTMLDialogElement.prototype.showModal).not.toHaveBeenCalled();
        expect(window.location.pathname).toBe(base);
        if (reason === "stale")
            expect(
                screen.getByText(
                    "The schedule changed. Refresh it before moving this item.",
                ),
            ).toBeTruthy();
        expect(fetch).toHaveBeenCalledOnce();
    },
);

test("server date refusal stays inline and never repeats the write automatically", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(
            json({ errors: { __all__: ["These dates overlap."] } }, 422),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await screen.findByText("These dates overlap.");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(HTMLDialogElement.prototype.showModal).not.toHaveBeenCalled();
    expect(fetch).toHaveBeenCalledTimes(2);
});

test.each([false, true])(
    "a recovered draft (rejected=%s) overrides the drop and never autosaves",
    async (rejected) => {
        const open = editor();
        const retained = new URLSearchParams({
            ...open.values,
            request_key: "retained-key",
            occurrence_id: "first",
            after_cycle_id: "one",
            ...(rejected ? { __workflow_rejected: "1" } : {}),
        });
        sessionStorage.setItem(open.recoveryKey, retained.toString());
        const fetch = vi.fn().mockResolvedValueOnce(prepared(open));
        vi.stubGlobal("fetch", fetch);
        render(<CampaignSchedule {...overview()} />);
        drop();
        await screen.findByRole("alert", {
            name: "Move could not be completed",
        });
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(sessionStorage.getItem(open.recoveryKey) ?? "").not.toContain(
            "fresh-key",
        );
        expect(fetch).toHaveBeenCalledOnce();
    },
);

test("a failed prepare retains intent for Retry and keeps handles disabled during its read", async () => {
    let finish!: (value: ReturnType<typeof prepared>) => void;
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error())
        .mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        )
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await userEvent.click(
        await screen.findByRole("button", { name: "Try again" }),
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Move Cycle 2",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    await act(async () => finish(prepared()));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));
    expect(
        fetch.mock.calls.filter(([, options]) => options.method === "POST"),
    ).toHaveLength(1);
});

test("ordinary navigation wins a racing prepare response and clears its drop intent", async () => {
    let finish!: (value: ReturnType<typeof prepared>) => void;
    const manual = editor();
    const fetch = vi
        .fn()
        .mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        )
        .mockResolvedValueOnce(prepared(manual));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await screen.findByRole("dialog", { name: "Move cycle" });
    await act(async () => finish(prepared()));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(
        (
            screen.getByRole("combobox", {
                name: "Phase block",
            }) as HTMLSelectElement
        ).value,
    ).toBe("second");
});

test("an unknown drop save retries the exact command after reload with fresh CSRF", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockRejectedValueOnce(new Error());
    vi.stubGlobal("fetch", fetch);
    const view = render(<CampaignSchedule {...overview()} />);
    drop();
    await screen.findByText(/The save may have completed/);
    const original = (
        fetch.mock.calls[1][1].body as URLSearchParams
    ).toString();
    view.unmount();
    const restored = editor();
    restored.csrfToken = "renewed-csrf";
    restored.values.request_key = "unused-key";
    fetch
        .mockResolvedValueOnce(prepared(restored))
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed());
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry move" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(5));
    const retried = new URLSearchParams(fetch.mock.calls[3][1].body);
    const expected = new URLSearchParams(original);
    expected.set("csrfmiddlewaretoken", "renewed-csrf");
    expect(retried.toString()).toBe(expected.toString());
});

test("a confirmed drop followed by a failed refresh retries only navigation", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(saved())
        .mockRejectedValueOnce(new Error())
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await screen.findByText(/The schedule could not be loaded/);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));
    expect(
        fetch.mock.calls.filter(([, options]) => options.method === "POST"),
    ).toHaveLength(1);
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("returning to a Move history entry never repeats the earlier drop", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed())
        .mockResolvedValueOnce(
            prepared({
                ...editor(),
                values: { ...editor().values, request_key: "new-history-key" },
            }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    act(() => {
        window.history.replaceState(null, "", move);
        window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
    });
    await screen.findByRole("dialog", { name: "Move cycle" });
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(
        fetch.mock.calls.filter(([, options]) => options.method === "POST"),
    ).toHaveLength(1);
});

test("a drop keeps the overview and URL while its command is pending", async () => {
    let finish!: (value: ReturnType<typeof saved>) => void;
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        )
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(window.location.pathname).toBe(base);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(HTMLDialogElement.prototype.showModal).not.toHaveBeenCalled();
    expect(
        screen
            .getByRole("button", { name: "Move Cycle 2" })
            .hasAttribute("disabled"),
    ).toBe(true);
    await act(async () => finish(saved()));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(HTMLDialogElement.prototype.showModal).not.toHaveBeenCalled();
});

test("the lifted source visibly changes until a cancelled drop", () => {
    const { container } = render(<CampaignSchedule {...overview()} />);
    const handle = lift();
    expect(
        container.querySelector("#cycle-two")?.getAttribute("data-moving"),
    ).toBe("true");
    expect(
        container.querySelector("#cycle-two")?.classList.contains("opacity-40"),
    ).toBe(true);
    fireEvent.keyDown(handle, { key: "Escape" });
    expect(
        container.querySelector("#cycle-two")?.classList.contains("opacity-40"),
    ).toBe(false);
});

test("a retained unknown move is retried even when its old revision is now stale", async () => {
    const open = editor();
    sessionStorage.setItem(
        open.recoveryKey,
        new URLSearchParams({
            ...open.values,
            request_key: "retained",
            occurrence_id: "empty",
        }).toString(),
    );
    sessionStorage.setItem(
        `schedule-move:${base}`,
        JSON.stringify({
            sourceId: "cycle:two",
            revision: 3,
            destination: { occurrence_id: "empty", after_cycle_id: "" },
            href: move,
            recoveryKey: open.recoveryKey,
        }),
    );
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared(open))
        .mockResolvedValueOnce(saved())
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    expect(
        screen.queryByRole("button", { name: "Refresh schedule" }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Dismiss" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry move" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(
        new URLSearchParams(fetch.mock.calls[1][1].body).get("request_key"),
    ).toBe("retained");
});

test("a resume marker from another actor cannot submit a new command", async () => {
    sessionStorage.setItem(
        `schedule-move:${base}`,
        JSON.stringify({
            sourceId: "cycle:two",
            revision: 4,
            destination: { occurrence_id: "empty" },
            href: move,
            recoveryKey: "another-actor",
        }),
    );
    const fetch = vi.fn().mockResolvedValueOnce(prepared());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    await waitFor(() =>
        expect(sessionStorage.getItem(`schedule-move:${base}`)).toBeNull(),
    );
    expect(fetch).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("an unvalidated conflict cannot discard an unknown move", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(
            json(
                {
                    code: "revision_conflict",
                    errors: { __all__: ["Malformed conflict"] },
                },
                409,
            ),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    await screen.findByRole("button", { name: "Retry move" });
    expect(
        screen.queryByRole("button", { name: "Refresh schedule" }),
    ).toBeNull();
    expect(sessionStorage.getItem(editor().recoveryKey)).not.toBeNull();
});

test("a delayed or failed recovery read cannot abandon the unresolved move", async () => {
    const open = editor();
    sessionStorage.setItem(
        open.recoveryKey,
        new URLSearchParams(open.values).toString(),
    );
    const marker = `schedule-move:${base}`;
    sessionStorage.setItem(
        marker,
        JSON.stringify({
            sourceId: "cycle:two",
            revision: 4,
            destination: { occurrence_id: "empty", after_cycle_id: "" },
            href: move,
            recoveryKey: open.recoveryKey,
        }),
    );
    let fail!: (error: Error) => void;
    const fetch = vi
        .fn()
        .mockReturnValueOnce(
            new Promise((_resolve, reject) => {
                fail = reject;
            }),
        )
        .mockResolvedValueOnce(prepared());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    expect(fetch).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(marker)).not.toBeNull();
    act(() => {
        window.history.replaceState(null, "", base + "?page=2");
        window.dispatchEvent(new PopStateEvent("popstate", { state: null }));
    });
    expect(window.location.search).toBe("");
    expect(sessionStorage.getItem(marker)).not.toBeNull();
    expect(fetch).toHaveBeenCalledOnce();
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    await act(async () => fail(new Error()));
    await screen.findByText(/The earlier move is still unconfirmed/);
    drop();
    expect(fetch).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(marker)).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("button", { name: "Retry move" });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).toBeNull();
});

test.each(["http://[", "https://example.com/move/"])(
    "an invalid resume target %s cannot navigate or mount an editor",
    async (href) => {
        sessionStorage.setItem(
            `schedule-move:${base}`,
            JSON.stringify({
                sourceId: "cycle:two",
                revision: 4,
                destination: {},
                href,
                recoveryKey: editor().recoveryKey,
            }),
        );
        const fetch = vi.fn();
        vi.stubGlobal("fetch", fetch);
        render(<CampaignSchedule {...overview()} />);
        await waitFor(() =>
            expect(sessionStorage.getItem(`schedule-move:${base}`)).toBeNull(),
        );
        expect(fetch).not.toHaveBeenCalled();
        expect(window.location.pathname).toBe(base);
        expect(screen.queryByRole("dialog")).toBeNull();
    },
);

function keepUnknownMove() {
    const open = editor();
    sessionStorage.setItem(
        open.recoveryKey,
        new URLSearchParams({
            ...open.values,
            request_key: "retained-key",
            occurrence_id: "first",
            after_cycle_id: "one",
        }).toString(),
    );
    sessionStorage.setItem(
        `schedule-move:${base}`,
        JSON.stringify({
            sourceId: "cycle:two",
            revision: 4,
            destination: { occurrence_id: "first", after_cycle_id: "one" },
            href: move,
            recoveryKey: open.recoveryKey,
        }),
    );
    return open;
}

test("a recovered unknown command gets a resume marker without another POST", async () => {
    const open = keepUnknownMove();
    sessionStorage.removeItem(`schedule-move:${base}`);
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(prepared({ ...editor(), csrfToken: "renewed" }));
    vi.stubGlobal("fetch", fetch);
    const view = render(<CampaignSchedule {...overview()} />);
    drop();
    await screen.findByRole("button", { name: "Retry move" });
    const marker = JSON.parse(sessionStorage.getItem(`schedule-move:${base}`)!);
    expect(marker.destination).toEqual({
        occurrence_id: "first",
        after_cycle_id: "one",
    });
    expect(sessionStorage.getItem(open.recoveryKey)).not.toBeNull();
    view.unmount();
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(
        fetch.mock.calls.every(([, options]) => options.method !== "POST"),
    ).toBe(true);
    expect(screen.getByText("01 Occupation · After Cycle 1")).toBeTruthy();
});

test("returning from an unrelated initial editor discovers the outstanding move", async () => {
    keepUnknownMove();
    const unrelated = {
        ...editor("move-phase"),
        recoveryKey: "unrelated-editor",
    };
    window.history.replaceState(null, "", phaseMove);
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(refreshed())
        .mockResolvedValueOnce(prepared());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} editor={unrelated} />);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await screen.findByRole("button", { name: "Retry move" });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(sessionStorage.getItem(`schedule-move:${base}`)).not.toBeNull();
    expect(
        fetch.mock.calls.every(([, options]) => options.method !== "POST"),
    ).toBe(true);
});

test("bfcache restoration rechecks storage before allowing another move", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(prepared());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    expect(fetch).not.toHaveBeenCalled();
    keepUnknownMove();
    act(() =>
        window.dispatchEvent(
            new PageTransitionEvent("pageshow", { persisted: true }),
        ),
    );
    await screen.findByRole("button", { name: "Retry move" });
    expect(fetch).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    expect(fetch).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(`schedule-move:${base}`)).not.toBeNull();
});

test("a retained destination missing from current choices is identified rather than replaced", async () => {
    const open = keepUnknownMove();
    const body = new URLSearchParams(sessionStorage.getItem(open.recoveryKey)!);
    body.set("occurrence_id", "removed-phase");
    body.set("after_cycle_id", "removed-cycle");
    sessionStorage.setItem(open.recoveryKey, body.toString());
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(prepared()));
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    expect(
        screen.getByText(
            "Phase no longer available · After cycle no longer available",
        ),
    ).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("an actor change during cached recovery removes the old actor's move UI", async () => {
    const open = keepUnknownMove();
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(
            prepared({
                ...editor(),
                recoveryKey: "another-actor",
                values: {
                    ...editor().values,
                    request_key: "another-actor-key",
                },
            }),
        )
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    act(() =>
        window.dispatchEvent(
            new PageTransitionEvent("pageshow", { persisted: true }),
        ),
    );
    await waitFor(() =>
        expect(screen.queryByRole("button", { name: "Retry move" })).toBeNull(),
    );
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(sessionStorage.getItem(`schedule-move:${base}`)).toBeNull();
    expect(sessionStorage.getItem(open.recoveryKey)).not.toBeNull();
    await waitFor(() =>
        expect(
            screen
                .getByRole("button", { name: "Move Cycle 2" })
                .hasAttribute("disabled"),
        ).toBe(false),
    );
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(
        fetch.mock.calls.every(([, options]) => options.method !== "POST"),
    ).toBe(true);
});

test("cached recovery replaces older retry UI and keeps its guard if the new read fails", async () => {
    keepUnknownMove();
    const phase = {
        ...editor("move-phase"),
        recoveryKey: "phase-recovery",
        values: { ...editor("move-phase").values, request_key: "phase-key" },
    };
    let fail!: (reason: Error) => void;
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockReturnValueOnce(
            new Promise((_resolve, reject) => {
                fail = reject;
            }),
        )
        .mockResolvedValueOnce(prepared(phase));
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    await screen.findByRole("button", { name: "Retry move" });
    sessionStorage.setItem(
        phase.recoveryKey,
        new URLSearchParams(phase.values).toString(),
    );
    const marker = JSON.stringify({
        sourceId: "phase:second",
        revision: 4,
        destination: { after_occurrence_id: "first" },
        href: phaseMove,
        recoveryKey: phase.recoveryKey,
    });
    sessionStorage.setItem(`schedule-move:${base}`, marker);
    act(() =>
        window.dispatchEvent(
            new PageTransitionEvent("pageshow", { persisted: true }),
        ),
    );
    expect(screen.queryByRole("button", { name: "Retry move" })).toBeNull();
    await act(async () => fail(new Error()));
    await screen.findByText(/The earlier move is still unconfirmed/);
    expect(screen.queryByRole("button", { name: "Retry move" })).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Edit Cycle 1" }));
    drop();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(sessionStorage.getItem(`schedule-move:${base}`)).toBe(marker);
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("button", { name: "Retry move" });
    expect(screen.getByText("02 Downtime")).toBeTruthy();
    expect(
        fetch.mock.calls.every(([, options]) => options.method !== "POST"),
    ).toBe(true);
    fetch
        .mockResolvedValueOnce(
            json({ nextUrl: base + "#phase-second", revision: 5 }),
        )
        .mockResolvedValueOnce(refreshed());
    await userEvent.click(screen.getByRole("button", { name: "Retry move" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(5));
    await waitFor(() =>
        expect(
            screen
                .getByRole("button", { name: "Move Cycle 2" })
                .hasAttribute("disabled"),
        ).toBe(false),
    );
    const confirmed = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(confirmed);
    expect(confirmed.defaultPrevented).toBe(false);
});

test("a cached unsent editor preserves its draft without reloading props", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    window.history.replaceState(null, "", phaseMove);
    render(
        <CampaignSchedule
            {...overview()}
            editor={{ ...editor("move-phase"), recoveryKey: "manual-phase" }}
        />,
    );
    const select = screen.getByRole("combobox", { name: "Move phase after" });
    await userEvent.selectOptions(select, "empty");
    act(() =>
        window.dispatchEvent(
            new PageTransitionEvent("pageshow", { persisted: true }),
        ),
    );
    expect(fetch).not.toHaveBeenCalled();
    expect((select as HTMLSelectElement).value).toBe("empty");
});

test("retry keeps its alert, focused control and busy feedback while the POST is pending", async () => {
    let finish!: (value: ReturnType<typeof saved>) => void;
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockRejectedValueOnce(new Error())
        .mockReturnValueOnce(
            new Promise((resolve) => {
                finish = resolve;
            }),
        )
        .mockResolvedValueOnce(refreshed());
    vi.stubGlobal("fetch", fetch);
    render(<CampaignSchedule {...overview()} />);
    drop();
    const button = await screen.findByRole("button", { name: "Retry move" });
    const alert = screen.getByRole("alert", {
        name: "Move could not be completed",
    });
    const message = alert.textContent;
    await userEvent.click(button);
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    expect(
        screen.getByRole("alert", { name: "Move could not be completed" }),
    ).toBe(alert);
    expect(alert.textContent).toBe(message);
    expect(screen.getByRole("button", { name: "Retry move" })).toBe(button);
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect(document.activeElement).toBe(button);
    expect(
        screen
            .getByRole("button", { name: "Move Cycle 2" })
            .getAttribute("aria-busy"),
    ).toBeNull();
    await act(async () => finish(saved()));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4));
});

test("a recovered move focuses its row on the returned page after confirmation", async () => {
    keepUnknownMove();
    const after = overview();
    after.rows = after.rows.filter((row) => row.key === "two");
    after.reorder = { revision: 5, sources: [], targets: [] };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(prepared())
        .mockResolvedValueOnce(
            json({ nextUrl: base + "?page=3#cycle-two", revision: 5 }),
        )
        .mockResolvedValueOnce(json({ schedule: after }));
    vi.stubGlobal("fetch", fetch);
    const { container } = render(<CampaignSchedule {...overview()} />);
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry move" }),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3));
    const row = container.querySelector("#cycle-two")!;
    await waitFor(() => expect(document.activeElement).toBe(row));
    expect(vi.mocked(Element.prototype.scrollIntoView).mock.contexts).toContain(
        row,
    );
    expect(window.location.search).toBe("?page=3");
});
