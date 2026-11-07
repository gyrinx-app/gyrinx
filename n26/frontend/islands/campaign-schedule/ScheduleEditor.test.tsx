import { render, screen } from "@testing-library/react";
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
