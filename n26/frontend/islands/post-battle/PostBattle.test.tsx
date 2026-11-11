import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { PostBattle } from "./PostBattle";
import { page, cinder, response } from "./fixtures";
import { fields } from "./types";

beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal(
        "ResizeObserver",
        class {
            observe() {}
            disconnect() {}
        },
    );
});
afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});
const bodyAt = (fetch: ReturnType<typeof vi.fn>, index = 0) =>
    fetch.mock.calls[index][1].body as URLSearchParams;
const saved = (revision: number, xp = "2") => ({
    ...page,
    revision,
    review: `review-${revision}`,
    models: [{ ...cinder, xp }, page.models[1]],
});

test("one root draws model sections, required participation and ordinary breadcrumbs", () => {
    render(<PostBattle {...page} />);
    expect(
        screen.getByRole("heading", { name: "Post-battle results", level: 1 }),
    ).toBeTruthy();
    expect(screen.getByRole("group", { name: "Cinder" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Ember" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Mission results" })).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Ashen Choir" }).getAttribute("href"),
    ).toBe("/gang/");
    expect(
        screen
            .getByRole("checkbox", {
                name: "I have checked which models took part.",
            })
            .getAttribute("aria-required"),
    ).toBe("true");
    expect(
        screen.getByText(
            "Entries save as you go. The gang changes only when you apply the results.",
        ),
    ).toBeTruthy();
    expect(document.querySelectorAll("[data-react-name]")).toHaveLength(0);
    expect(document.querySelector("form form")).toBeNull();
    expect(
        document.querySelector("[data-battle-actions].n26-battle-actions"),
    ).toBeTruthy();
});

test("the toolbar keeps native counts, accessible labels and participant-only XP steps", () => {
    render(<PostBattle {...page} />);
    expect(screen.getByText("1 model took part")).toBeTruthy();
    fireEvent.click(
        screen.getByRole("button", {
            name: "Add 1 XP to the model that took part",
        }),
    );
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "3",
    );
    expect(screen.getAllByLabelText("XP gained")[1]).toHaveProperty(
        "value",
        "",
    );
    fireEvent.click(screen.getByRole("button", { name: "Mark all attended" }));
    expect(screen.getByText("2 models took part")).toBeTruthy();
    expect(
        screen.getByRole("button", {
            name: "Add 1 XP to each of the 2 models that took part",
        }),
    ).toBeTruthy();
});

test("unselected and blocked models disable bulk XP while notes and counters remain labelled", () => {
    render(
        <PostBattle
            {...page}
            models={[
                {
                    ...cinder,
                    participated: false,
                    xpAvailable: false,
                    xpHelp: "This model has no XP counter.",
                },
            ]}
        />,
    );
    expect(
        screen.getByRole("button", {
            name: "Add 1 XP to each of the 0 models that took part",
        }),
    ).toHaveProperty("disabled", true);
    expect(
        screen.getByRole("button", { name: "Why Cinder cannot take XP" }),
    ).toBeTruthy();
    expect(
        screen
            .getByLabelText("Add to Cinder's notes (optional)")
            .getAttribute("aria-describedby"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add 1 to Marks" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add 1 to Marks" }));
    expect(screen.getByLabelText("Marks")).toHaveProperty("value", "1");
});

test("equipment controls only appear for dead models, with retained effects and choices", () => {
    const effect = {
        id: "effect-1",
        selected: "injury|wound",
        label: "Lasting Injury 1",
        name: "Grievous Wound",
        retainedOption: false,
        retainedChoices: [{ key: "old", selected: ["old-value"] }],
        questions: [
            {
                key: "location",
                label: "Choose location",
                multiple: false,
                required: true,
                selected: ["arm"],
                options: [{ value: "arm", label: "Arm" }],
            },
        ],
    };
    const props = {
        ...page,
        models: [{ ...cinder, equipmentApplies: true, effects: [effect] }],
    };
    render(<PostBattle {...props} />);
    expect(
        screen.getByLabelText("What happens to Cinder's equipment"),
    ).toBeTruthy();
    expect(screen.getByLabelText("Lasting Injury 1")).toHaveProperty(
        "value",
        "injury|wound",
    );
    expect(screen.getByLabelText("Choose location")).toHaveProperty(
        "value",
        "arm",
    );
    expect(screen.getByRole("button", { name: "Reset choices" })).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Remove Lasting Injury 1" }),
    ).toBeTruthy();
    const group = screen.getByRole("group", { name: "Cinder" });
    const participation = within(group).getByRole("checkbox");
    expect(
        participation.compareDocumentPosition(
            within(group).getByLabelText("XP gained"),
        ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
});

test("territory outcomes remain informational and correction copy keeps its receipt link", () => {
    render(
        <PostBattle
            {...page}
            correcting
            territory={{
                name: "Slag Furnace",
                heading: "Territory",
                outcome: "Outcome not recorded.",
                currentHolder: "Ashen Choir",
                applied: false,
                note: "The campaign’s arbitrator records this outcome on Edit battle.",
            }}
        />,
    );
    expect(screen.getByText("Slag Furnace")).toBeTruthy();
    expect(
        within(screen.getByRole("region", { name: "Territory" })).getByText(
            "Ashen Choir",
        ),
    ).toBeTruthy();
    expect(
        screen.getByText(
            "The campaign’s arbitrator records this outcome on Edit battle.",
        ),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("link", { name: "View recorded results" })
            .getAttribute("href"),
    ).toBe("/receipt/");
});

test("manual saves use form-encoded commands, fresh CSRF and stable button text", async () => {
    let resolve: (value: Response) => void;
    const fetch = vi.fn(
        (_href: unknown, _options: RequestInit) =>
            new Promise<Response>((done) => {
                resolve = done;
            }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    const body = bodyAt(fetch);
    expect(body.get("intent")).toBe("save");
    expect(body.get("csrfmiddlewaretoken")).toBeNull();
    expect(new Headers(fetch.mock.calls[0][1].headers).get("X-CSRFToken")).toBe(
        "fresh-token",
    );
    expect(
        screen
            .getByRole("button", { name: "Save draft" })
            .getAttribute("data-busy"),
    ).toBe("on");
    await act(async () => resolve!(response(saved(2))));
    expect(screen.getByRole("button", { name: "Save draft" })).toHaveProperty(
        "disabled",
        false,
    );
});

test("edits made during autosave survive its response and become the next save", async () => {
    vi.useFakeTimers();
    let resolve: (value: Response) => void;
    const fetch = vi.fn(
        (_href: unknown, _options: RequestInit) =>
            new Promise<Response>((done) => {
                resolve = done;
            }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "4" },
    });
    await act(async () => vi.advanceTimersByTime(900));
    expect(bodyAt(fetch).get("model-cinder-xp")).toBe("4");
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "6" },
    });
    await act(async () => resolve!(response(saved(2, "4"))));
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "6",
    );
    await act(async () => vi.advanceTimersByTime(900));
    expect(bodyAt(fetch, 1).get("model-cinder-xp")).toBe("6");
    expect(bodyAt(fetch, 1).get("revision")).toBe("2");
});

test("Apply waits for the current draft acknowledgement and then uses its reviewed version", async () => {
    const navigate = vi.fn();
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(response(saved(2, "4")))
        .mockResolvedValueOnce(
            response(saved(3, "4"), { nextUrl: "/receipt/2/" }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} onNavigate={navigate} />);
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "4" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply results" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("/receipt/2/"));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(bodyAt(fetch).get("intent")).toBe("autosave");
    expect(bodyAt(fetch, 1).get("intent")).toBe("apply");
    expect(bodyAt(fetch, 1).get("review")).toBe("review-2");
    expect(bodyAt(fetch, 1).get("command_key")).not.toBe(
        bodyAt(fetch).get("command_key"),
    );
});

test("lost responses retain the exact command and rejected retries do not unfreeze it", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("offline"))
        .mockResolvedValueOnce(
            response(
                page,
                {
                    acknowledged: null,
                    errors: ["Draft changed."],
                    conflict: true,
                },
                409,
            ),
        )
        .mockResolvedValueOnce(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Retry save" });
    const original = bodyAt(fetch).toString();
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "disabled",
        false,
    );
    expect(
        (screen.getAllByLabelText("XP gained")[0] as HTMLInputElement).closest(
            "fieldset[disabled]",
        ),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await screen.findByText("Draft changed.");
    expect(
        screen.queryByRole("button", { name: "Use latest saved draft" }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() =>
        expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull(),
    );
    expect(bodyAt(fetch, 1).toString()).toBe(original);
    expect(bodyAt(fetch, 2).toString()).toBe(original);
});

test("reload restores both unresolved snapshot and later edits with fresh credentials", async () => {
    const original = fields(page);
    const submitted = new URLSearchParams(original);
    for (const [key, val] of Object.entries({
        intent: "autosave",
        generation: "generation-1",
        revision: "1",
        review: "review-1",
        submission_key: "submission-1",
        command_key: "command-1",
    }))
        submitted.set(key, val);
    const later = new URLSearchParams(original);
    later.set("model-cinder-xp", "8");
    sessionStorage.setItem(
        page.recoveryKey,
        JSON.stringify({
            draft: later.toString(),
            command: submitted.toString(),
            intent: "autosave",
            rejected: false,
        }),
    );
    const fetch = vi.fn().mockResolvedValue(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} csrfToken="rotated-token" />);
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "8",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() =>
        expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull(),
    );
    expect(bodyAt(fetch).get("command_key")).toBe("command-1");
    expect(new Headers(fetch.mock.calls[0][1].headers).get("X-CSRFToken")).toBe(
        "rotated-token",
    );
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "8",
    );
});

test("a confirmed earlier save with a newer draft requires review without staying uncertain", async () => {
    const latest = { ...saved(4, "9"), participationConfirmed: true };
    const fetch = vi
        .fn()
        .mockResolvedValue(
            response(saved(2), { newer: true, currentDisplay: latest }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Use latest saved draft" });
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    fireEvent.click(
        screen.getByRole("button", { name: "Use latest saved draft" }),
    );
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "9",
    );
    expect(
        screen.getByRole("checkbox", {
            name: "I have checked which models took part.",
        }),
    ).toHaveProperty("checked", true);
});

test("malformed acknowledgements keep the original command identity recoverable", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            new Response(JSON.stringify({ acknowledged: {}, display: {} }), {
                headers: { "Content-Type": "application/json" },
            }),
        )
        .mockResolvedValueOnce(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Retry save" });
    const first = bodyAt(fetch).toString();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(bodyAt(fetch, 1).toString()).toBe(first);
});

test("storage refusal prevents sending a command whose identity cannot be recovered", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const store = vi
        .spyOn(Storage.prototype, "setItem")
        .mockImplementation(() => {
            throw new Error("blocked");
        });
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    expect(
        screen.getByText(
            "Your browser could not keep this save for recovery. Allow this site to store data, then try again.",
        ),
    ).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    store.mockRestore();
});

test("pending and uncertain saves warn before leaving and focus their error summary", async () => {
    const fetch = vi.fn().mockRejectedValue(new Error("offline"));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Retry save" });
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    await waitFor(() =>
        expect(document.activeElement?.getAttribute("tabindex")).toBe("-1"),
    );
});

test("a completed form restored from history reloads instead of reusing a consumed submission", async () => {
    const reload = vi.fn();
    const navigate = vi.fn();
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(response(saved(2), { nextUrl: "/receipt/2/" })),
    );
    render(<PostBattle {...page} onNavigate={navigate} onReload={reload} />);
    fireEvent.click(screen.getByRole("button", { name: "Apply results" }));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
    window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true }),
    );
    expect(reload).toHaveBeenCalledOnce();
});

test("an older cached form checks recovery storage on history restoration", () => {
    const reload = vi.fn();
    render(<PostBattle {...page} onReload={reload} />);
    sessionStorage.setItem(
        page.recoveryKey,
        JSON.stringify({
            draft: fields(page).toString(),
            command: "command_key=later",
            intent: "save",
            rejected: false,
        }),
    );
    window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true }),
    );
    expect(reload).toHaveBeenCalledOnce();
});

test("a native stale submission starts frozen until the latest saved draft is explicitly reviewed", () => {
    const latest = saved(5, "7");
    render(<PostBattle {...page} initialConflict currentDisplay={latest} />);
    expect(screen.getByRole("button", { name: "Save draft" })).toHaveProperty(
        "disabled",
        true,
    );
    expect(
        screen.getByRole("button", { name: "Use latest saved draft" }),
    ).toBeTruthy();
});

test("an acknowledgement with malformed nested display cannot discard its retained body", async () => {
    const malformed = { ...page, models: [{ ...cinder, effects: null }] };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(response(malformed as unknown as typeof page))
        .mockResolvedValueOnce(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Retry save" });
    const first = bodyAt(fetch).toString();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(bodyAt(fetch, 1).toString()).toBe(first);
});

test("correcting a known validation refusal resumes autosave without repeating unchanged refusals", async () => {
    vi.useFakeTimers();
    const message = "Check which models took part before applying the results.";
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            response(
                { ...page, errors: [message] },
                {
                    acknowledged: null,
                    errors: [message],
                    conflict: false,
                },
                409,
            ),
        )
        .mockResolvedValueOnce(response(saved(2, "4")));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Apply results" })),
    );
    expect(screen.getAllByText(message)).toHaveLength(1);
    await act(async () => vi.advanceTimersByTime(5000));
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "4" },
    });
    await act(async () => vi.advanceTimersByTime(900));
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(bodyAt(fetch, 1).get("intent")).toBe("autosave");
    expect(bodyAt(fetch, 1).get("command_key")).not.toBe(
        bodyAt(fetch).get("command_key"),
    );
});

test("editing after an authentication refusal does not keep retrying autosave", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValue(
        new Response(
            JSON.stringify({ error: "Sign in again to save this change." }),
            {
                status: 401,
                headers: { "Content-Type": "application/json" },
            },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    await act(async () =>
        fireEvent.click(screen.getByRole("button", { name: "Save draft" })),
    );
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "4" },
    });
    await act(async () => vi.advanceTimersByTime(5000));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Sign in again to save this change.")).toBeTruthy();
});

test("credit totals and counter forecasts update locally and counter steps stop at zero", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    const total = screen.getByText(
        "Credits from this battle",
    ).nextElementSibling;
    fireEvent.change(screen.getByLabelText("Amount"), {
        target: { value: "55" },
    });
    expect(total?.textContent).toBe("+55¢");
    fireEvent.change(screen.getByLabelText("Amount"), {
        target: { value: "-1" },
    });
    expect(total?.textContent).toBe("0¢");
    fireEvent.change(screen.getByLabelText("Amount"), {
        target: { value: "1.5" },
    });
    expect(total?.textContent).toBe("0¢");
    fireEvent.click(
        screen.getByRole("button", { name: "Remove 1 from Marks" }),
    );
    fireEvent.click(
        screen.getByRole("button", { name: "Remove 1 from Marks" }),
    );
    expect(screen.getByLabelText("Marks")).toHaveProperty("value", "-2");
    expect(
        screen.getByRole("button", { name: "Remove 1 from Marks" }),
    ).toHaveProperty("disabled", true);
    expect(fetch).not.toHaveBeenCalled();
});

test("a delayed correction preserves a later note and its focused caret", async () => {
    vi.useFakeTimers();
    let resolve: (value: Response) => void;
    const fetch = vi.fn(
        () =>
            new Promise<Response>((done) => {
                resolve = done;
            }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    const note = screen.getByLabelText(
        "Add to Cinder's notes (optional)",
    ) as HTMLTextAreaElement;
    fireEvent.change(note, { target: { value: "First note" } });
    await act(async () => vi.advanceTimersByTime(900));
    fireEvent.change(note, { target: { value: "First and later note" } });
    note.focus();
    note.setSelectionRange(7, 7);
    await act(async () =>
        resolve!(
            response({
                ...saved(2, ""),
                models: [
                    { ...cinder, xp: "", note: "First note" },
                    page.models[1],
                ],
            }),
        ),
    );
    expect(document.activeElement).toBe(note);
    expect(note.value).toBe("First and later note");
    expect(note.selectionStart).toBe(7);
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "",
    );
    await act(async () => vi.advanceTimersByTime(900));
    expect(bodyAt(fetch, 1).get("model-cinder-note")).toBe(
        "First and later note",
    );
});

test("a malformed choice list leaves the exact command available instead of breaking the editor", async () => {
    const malformed = {
        ...page,
        models: [{ ...cinder, statusOptions: null }, page.models[1]],
    };
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(response(malformed as unknown as typeof page))
        .mockResolvedValueOnce(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Retry save" });
    const first = bodyAt(fetch).toString();
    fireEvent.click(screen.getByRole("button", { name: "Retry save" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(bodyAt(fetch, 1).toString()).toBe(first);
});

test("a clean acknowledged draft leaves no recovery copy that can overwrite another tab", async () => {
    const fetch = vi.fn().mockResolvedValue(response(saved(2)));
    vi.stubGlobal("fetch", fetch);
    const view = render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await waitFor(() =>
        expect(
            screen.getByRole("button", { name: "Save draft" }),
        ).toHaveProperty("disabled", false),
    );
    expect(sessionStorage.getItem(page.recoveryKey)).toBeNull();
    view.unmount();
    render(<PostBattle {...saved(5, "9")} />);
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "9",
    );
    expect(
        screen.queryByRole("button", { name: "Use latest saved draft" }),
    ).toBeNull();
});

test.each(["revision", "generation", "legacy"])(
    "restored unsent entries require explicit review after a different %s",
    async (change) => {
        vi.useFakeTimers();
        const fetch = vi.fn();
        vi.stubGlobal("fetch", fetch);
        const view = render(<PostBattle {...page} />);
        fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
            target: { value: "8" },
        });
        const retained = JSON.parse(sessionStorage.getItem(page.recoveryKey)!);
        expect(retained.generation).toBe(page.generation);
        expect(retained.revision).toBe(page.revision);
        if (change === "legacy") {
            delete retained.generation;
            delete retained.revision;
            sessionStorage.setItem(page.recoveryKey, JSON.stringify(retained));
        }
        view.unmount();
        const latest = {
            ...saved(change === "revision" ? 5 : 1, "9"),
            generation:
                change === "generation" ? "correction-2" : page.generation,
        };
        render(<PostBattle {...latest} />);
        expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
            "value",
            "8",
        );
        expect(
            screen.getByRole("button", { name: "Save draft" }),
        ).toHaveProperty("disabled", true);
        await act(async () => vi.advanceTimersByTime(5000));
        expect(fetch).not.toHaveBeenCalled();
        fireEvent.click(
            screen.getByRole("button", { name: "Use latest saved draft" }),
        );
        expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
            "value",
            "9",
        );
        expect(
            new URLSearchParams(
                sessionStorage.getItem(`${page.recoveryKey}:previous`)!,
            ).get("model-cinder-xp"),
        ).toBe("8");
    },
);

test("restored unsent entries still save when their baseline matches the current draft", async () => {
    vi.useFakeTimers();
    const fetch = vi.fn().mockResolvedValue(response(saved(2, "8")));
    vi.stubGlobal("fetch", fetch);
    const view = render(<PostBattle {...page} />);
    fireEvent.change(screen.getAllByLabelText("XP gained")[0], {
        target: { value: "8" },
    });
    view.unmount();
    render(<PostBattle {...page} />);
    await act(async () => vi.advanceTimersByTime(900));
    expect(bodyAt(fetch).get("revision")).toBe("1");
    expect(bodyAt(fetch).get("model-cinder-xp")).toBe("8");
    expect(sessionStorage.getItem(page.recoveryKey)).toBeNull();
});

test("an older acknowledged save retains its own baseline across reload while requiring latest-draft review", async () => {
    const latest = saved(5, "9");
    const olderAtCurrentVersion = { ...saved(5, "2") };
    const fetch = vi.fn().mockResolvedValue(
        response(olderAtCurrentVersion, {
            acknowledged: {
                generation: page.generation,
                revision: 2,
                payload: {},
                sequence: null,
            },
            newer: true,
            currentDisplay: latest,
        }),
    );
    vi.stubGlobal("fetch", fetch);
    const view = render(<PostBattle {...page} />);
    fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("button", { name: "Use latest saved draft" });
    expect(JSON.parse(sessionStorage.getItem(page.recoveryKey)!).revision).toBe(
        2,
    );
    view.unmount();
    render(<PostBattle {...latest} />);
    expect(
        screen.getByRole("button", { name: "Use latest saved draft" }),
    ).toBeTruthy();
    expect(screen.getAllByLabelText("XP gained")[0]).toHaveProperty(
        "value",
        "2",
    );
    expect(screen.getByRole("button", { name: "Save draft" })).toHaveProperty(
        "disabled",
        true,
    );
});
