import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CrewWorkflow, type CrewWorkflowProps } from "./CrewWorkflow";
import { type CrewModel } from "./CrewPicker";

function model(id: string, name: string, role = "out"): CrewModel {
    return {
        id,
        name,
        profile: "Gunner",
        fullRating: 120,
        savedSource: "",
        search: `${name} gunner`.toLowerCase(),
        warning: "",
        mayOverride: false,
        available: true,
        role: {
            name: `role_${id}`,
            id: `id_role_${id}`,
            value: role,
            errors: [],
            choices: [
                { value: "out", label: "Not selected" },
                { value: "starting", label: "Starting crew" },
                { value: "reserve", label: "Reinforcements" },
            ],
        },
        card: {
            name: `card_${id}`,
            id: `id_card_${id}`,
            value: "long",
            errors: [],
            choices: [
                { value: "long", label: "Long range" },
                { value: "short", label: "Close range" },
            ],
        },
        override: {
            name: `override_${id}`,
            id: `id_override_${id}`,
            value: false,
            errors: [],
        },
    };
}
function props(
    models = [model("a", "Mara", "reserve"), model("b", "Nell")],
): CrewWorkflowProps {
    return {
        campaignName: "Sump Road",
        campaignUrl: "/campaign/",
        battleName: "Toll bridge",
        battleUrl: "/battle/",
        gangName: "Iron Hounds",
        revision: 2,
        models,
        values: {
            revision: "2",
            request_key: "key",
            random_count: "1",
            random_role: "starting",
            action: "save",
            submitted_snapshot: "[]",
            ...Object.fromEntries(
                models.flatMap((m) => [
                    [m.role.name, m.role.value ?? "out"],
                    [m.card.name, m.card.value ?? ""],
                    [m.override.name, m.override.value ? "on" : ""],
                ]),
            ),
        },
        errors: {},
        crewHelp: {
            label: "More about crew selection",
            paragraphs: ["Pets join their owners."],
        },
        drawHelp: {
            label: "More about the random draw",
            paragraphs: ["The draw saves the draft."],
        },
        action: "/crew/",
        commandHref: "/crew/command/",
        displayHref: "/crew/display/",
        csrfToken: "csrf",
        recoveryKey: "crew:actor:battle:gang",
        signInHref: "/accounts/login/?next=/crew/?recover=1",
        initialConflict: false,
        readOnly: false,
        current: { revision: 2, selections: [] },
        acknowledgement: null,
    };
}
const json = (data: unknown, status = 200) => ({
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
});

describe("CrewWorkflow", () => {
    it.each(["Save crew", "Save draft", "Draw and save draft"])(
        "submits the exact %s intent with all hidden-by-search model fields",
        async (label) => {
            const fetch = vi
                .fn()
                .mockResolvedValue(json({ nextUrl: "/saved/" }));
            vi.stubGlobal("fetch", fetch);
            const navigate = vi.fn();
            render(<CrewWorkflow {...props()} onNavigate={navigate} />);
            expect(fetch).not.toHaveBeenCalled();
            const user = userEvent.setup();
            await user.click(
                screen.getByRole("checkbox", { name: "Select Nell" }),
            );
            await user.selectOptions(
                screen.getByRole("combobox", {
                    name: "Equipment set for Nell",
                }),
                "short",
            );
            await user.type(
                screen.getByRole("searchbox", { name: "Find a model" }),
                "Mara",
            );
            await user.click(screen.getByRole("button", { name: label }));
            expect(fetch).toHaveBeenCalledTimes(1);
            const body = fetch.mock.calls[0][1].body;
            expect(body.get("action")).toBe(
                label === "Save crew"
                    ? "save"
                    : label === "Save draft"
                      ? "draft"
                      : "draw",
            );
            expect(body.get("role_a")).toBe("reserve");
            expect(body.get("role_b")).toBe("starting");
            expect(body.get("card_b")).toBe("short");
            expect(body.get("override_a")).toBe("");
            expect(body.get("request_key")).toBe("key");
            expect(navigate).toHaveBeenCalledWith("/saved/");
        },
    );
    it("keeps a selected unavailable model's raw role and requires an explicit allowance", async () => {
        const mara = {
            ...model("a", "Mara", "reserve"),
            mayOverride: true,
            warning: "In Recovery. Usually unavailable for selection.",
        };
        const fetch = vi.fn().mockResolvedValue(
            json(
                {
                    errors: {
                        override_a: [
                            "Allow this model for this battle or remove it from the crew.",
                        ],
                    },
                },
                422,
            ),
        );
        vi.stubGlobal("fetch", fetch);
        render(<CrewWorkflow {...props([mara])} />);
        const user = userEvent.setup();
        expect(
            screen.getByRole("checkbox", { name: "Select Mara" }),
        ).toHaveProperty("checked", true);
        expect(
            screen.getByRole("checkbox", { name: "Allow for this battle" }),
        ).toHaveProperty("checked", false);
        await user.click(screen.getByRole("button", { name: "Save crew" }));
        expect(fetch.mock.calls[0][1].body.get("role_a")).toBe("reserve");
        expect(
            await screen.findByText(
                "Allow this model for this battle or remove it from the crew.",
            ),
        ).not.toBeNull();
        await user.click(
            screen.getByRole("checkbox", { name: "Allow for this battle" }),
        );
        await user.click(screen.getByRole("button", { name: "Save crew" }));
        expect(fetch.mock.calls[1][1].body.getAll("override_a")).toEqual([
            "on",
        ]);
    });
    it("keeps invalid equipment values explicit until replaced", async () => {
        const mara = model("a", "Mara", "starting");
        mara.card.value = "removed";
        render(<CrewWorkflow {...props([mara])} />);
        const select = screen.getByRole("combobox", {
            name: "Equipment set for Mara",
        });
        expect(select).toHaveProperty("value", "removed");
        expect(
            screen.getByRole("option", { name: "Select an equipment set" }),
        ).toHaveProperty("disabled", true);
        await userEvent.setup().selectOptions(select, "short");
        expect(select).toHaveProperty("value", "short");
    });
    it("searches without submitting and retains hidden selections", async () => {
        const fetch = vi.fn();
        vi.stubGlobal("fetch", fetch);
        render(<CrewWorkflow {...props()} />);
        const user = userEvent.setup();
        await user.type(screen.getByRole("searchbox"), "missing{Enter}");
        expect(fetch).not.toHaveBeenCalled();
        expect(screen.getByText("No models match your search.")).not.toBeNull();
        expect(screen.getByText("1 model selected")).not.toBeNull();
    });
    it.each(["added", "removed"])(
        "retries an uncertain draw's exact body after a model was %s and CSRF rotated",
        async (change) => {
            const first = props();
            const fail = vi.fn().mockRejectedValue(new Error("lost response"));
            vi.stubGlobal("fetch", fail);
            const rendered = render(<CrewWorkflow {...first} />);
            const user = userEvent.setup();
            await user.click(
                screen.getByRole("button", { name: "Draw and save draft" }),
            );
            await screen.findByRole("button", { name: "Retry draw" });
            const original = fail.mock.calls[0][1].body;
            expect(sessionStorage.getItem(first.recoveryKey)).not.toContain(
                "csrf",
            );
            rendered.unmount();
            const changed = props(
                change === "added"
                    ? [...first.models, model("c", "New model")]
                    : [first.models[1]],
            );
            const fetch = vi
                .fn()
                .mockResolvedValue(json({ nextUrl: "/crew/" }));
            vi.stubGlobal("fetch", fetch);
            const navigate = vi.fn();
            render(
                <CrewWorkflow
                    {...changed}
                    csrfToken="fresh-csrf"
                    onNavigate={navigate}
                />,
            );
            expect(
                screen.getByRole("region", {
                    name: "Unconfirmed crew selections",
                }),
            ).toHaveProperty("textContent", expect.stringContaining("Mara"));
            expect(
                screen.queryByRole("checkbox", { name: "Select New model" }),
            ).toBeNull();
            await user.click(
                screen.getByRole("button", { name: "Retry draw" }),
            );
            const replay = fetch.mock.calls[0][1].body;
            const originalBusiness = new URLSearchParams(original);
            originalBusiness.delete("csrfmiddlewaretoken");
            const replayBusiness = new URLSearchParams(replay);
            replayBusiness.delete("csrfmiddlewaretoken");
            expect(replayBusiness.toString()).toBe(originalBusiness.toString());
            expect(replay.get("csrfmiddlewaretoken")).toBe("fresh-csrf");
            expect(navigate).toHaveBeenCalledWith("/crew/");
        },
    );
    it("does not let a rejected retry discard an earlier uncertain command", async () => {
        const fetch = vi
            .fn()
            .mockRejectedValueOnce(new Error("lost response"))
            .mockResolvedValueOnce(
                json(
                    { errors: { __all__: ["This model is unavailable."] } },
                    422,
                ),
            )
            .mockResolvedValueOnce(json({ nextUrl: "/crew/" }));
        vi.stubGlobal("fetch", fetch);
        render(<CrewWorkflow {...props()} onNavigate={vi.fn()} />);
        const user = userEvent.setup();
        await user.click(
            screen.getByRole("button", { name: "Draw and save draft" }),
        );
        await user.click(
            await screen.findByRole("button", { name: "Retry draw" }),
        );
        expect(
            await screen.findByText(
                "The earlier save is still unconfirmed. Retry it before making another change.",
            ),
        ).not.toBeNull();
        await user.click(screen.getByRole("button", { name: "Retry draw" }));
        expect(fetch.mock.calls[0][1].body.toString()).toBe(
            fetch.mock.calls[2][1].body.toString(),
        );
    });
    it("distinguishes an acknowledged historical draw from a newer current crew", async () => {
        const fetch = vi.fn().mockResolvedValue(
            json({
                nextUrl: "/crew/",
                newer: true,
                acknowledged: {
                    action: "draw",
                    revision: 3,
                    drawn: ["Earlier model"],
                    selections: [
                        {
                            id: "earlier",
                            name: "Earlier model",
                            role: "starting",
                            card: "Earlier card",
                        },
                    ],
                },
            }),
        );
        vi.stubGlobal("fetch", fetch);
        render(<CrewWorkflow {...props()} />);
        await userEvent
            .setup()
            .click(screen.getByRole("button", { name: "Save crew" }));
        expect(
            await screen.findByRole("region", { name: "Saved crew change" }),
        ).toHaveProperty(
            "textContent",
            expect.stringContaining("Earlier model"),
        );
        expect(screen.queryByRole("checkbox")).toBeNull();
        expect(
            screen
                .getByRole("link", { name: "Review current crew" })
                .getAttribute("href"),
        ).toBe("/crew/?recover=1");
    });
    it("requires explicit review after a revision conflict and leaves the draft frozen", async () => {
        const fetch = vi.fn().mockResolvedValue(
            json(
                {
                    errors: { __all__: ["This crew changed."] },
                    code: "revision_conflict",
                    current: {
                        revision: 5,
                        selections: [
                            {
                                name: "Current model",
                                role: "Starting crew",
                                card: "Current card",
                            },
                        ],
                    },
                },
                409,
            ),
        );
        vi.stubGlobal("fetch", fetch);
        const navigate = vi.fn();
        render(<CrewWorkflow {...props()} onNavigate={navigate} />);
        const user = userEvent.setup();
        await user.click(screen.getByRole("button", { name: "Save crew" }));
        await screen.findByText("Current model · Starting crew · Current card");
        expect(navigate).not.toHaveBeenCalled();
        expect(
            screen.getByRole("button", { name: "Retry save" }),
        ).toHaveProperty("disabled", true);
        await user.click(
            screen.getByRole("button", { name: "Review current crew" }),
        );
        expect(navigate).toHaveBeenCalledWith("/crew/?recover=1");
    });
    it("keeps the initiating draw control stable while preventing duplicate submissions", async () => {
        let finish: (value: unknown) => void = () => {};
        const fetch = vi.fn().mockImplementation(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                }),
        );
        vi.stubGlobal("fetch", fetch);
        const rendered = render(
            <CrewWorkflow {...props()} onNavigate={vi.fn()} />,
        );
        const user = userEvent.setup();
        const draw = screen.getByRole("button", {
            name: "Draw and save draft",
        });
        await user.click(draw);
        expect(draw.getAttribute("aria-busy")).toBe("true");
        expect(draw.textContent).toContain("Draw and save draft");
        expect(draw.closest("fieldset")?.disabled).toBe(true);
        fireEvent.submit(rendered.container.querySelector("form")!);
        expect(fetch).toHaveBeenCalledTimes(1);
        finish(json({ nextUrl: "/crew/" }));
        await waitFor(() => expect(draw.getAttribute("aria-busy")).toBeNull());
    });
});

it("keeps a known rejected draft's removed model visible until explicit roster review", async () => {
    const initial = props();
    const retained = new URLSearchParams({
        ...initial.values,
        __workflow_rejected: "1",
        submitted_snapshot: JSON.stringify([
            {
                id: "a",
                name: "Earlier Mara",
                role: "reserve",
                card: "Earlier card",
            },
        ]),
    });
    sessionStorage.setItem(initial.recoveryKey, retained.toString());
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <CrewWorkflow {...props([model("b", "Nell")])} onNavigate={navigate} />,
    );
    expect(screen.getByText("Earlier Mara · Earlier card")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Save crew" })).toHaveProperty(
        "disabled",
        true,
    );
    fireEvent.submit(document.querySelector("form")!);
    expect(fetch).not.toHaveBeenCalled();
    await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Review current crew" }));
    expect(navigate).toHaveBeenCalledWith("/crew/?recover=1");
});

it("retains a save whose acknowledged historical result is malformed", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ nextUrl: "/crew/", newer: true, acknowledged: {} }),
        );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const initial = props();
    render(<CrewWorkflow {...initial} onNavigate={navigate} />);
    await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Save crew" }));
    expect(
        await screen.findByRole("button", { name: "Retry save" }),
    ).not.toBeNull();
    expect(sessionStorage.getItem(initial.recoveryKey)).not.toBeNull();
    expect(navigate).not.toHaveBeenCalled();
});

it("preserves false checkbox values and an invalid numeric draft until edited", async () => {
    const mara = { ...model("a", "Mara", "starting"), mayOverride: true };
    const initial = props([mara]);
    initial.values.override_a = "false";
    initial.values.random_count = "invalid";
    const fetch = vi
        .fn()
        .mockResolvedValue(
            json({ errors: { random_count: ["Enter a whole number."] } }, 422),
        );
    vi.stubGlobal("fetch", fetch);
    render(<CrewWorkflow {...initial} />);
    expect(
        screen.getByRole("checkbox", { name: "Allow for this battle" }),
    ).toHaveProperty("checked", false);
    await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Save draft" }));
    expect(fetch.mock.calls[0][1].body.get("override_a")).toBe("false");
    expect(fetch.mock.calls[0][1].body.get("random_count")).toBe("invalid");
});

it("recovers a retained draw before accepting unrelated fresh acknowledgement metadata", async () => {
    const initial = props();
    sessionStorage.setItem(
        initial.recoveryKey,
        new URLSearchParams({
            ...initial.values,
            action: "draw",
            request_key: "earlier-key",
            submitted_snapshot: JSON.stringify([
                {
                    id: "a",
                    name: "Earlier Mara",
                    role: "reserve",
                    card: "Earlier card",
                },
            ]),
        }).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/crew/" }));
    vi.stubGlobal("fetch", fetch);
    const fresh = props();
    fresh.acknowledgement = {
        action: "save",
        revision: 9,
        drawn: [],
        selections: [
            {
                id: "other",
                name: "Unrelated model",
                role: "starting",
                card: "Other card",
            },
        ],
    };
    render(<CrewWorkflow {...fresh} onNavigate={vi.fn()} />);
    expect(
        screen.queryByRole("region", { name: "Saved crew change" }),
    ).toBeNull();
    expect(
        screen.getByRole("region", { name: "Unconfirmed crew selections" })
            .textContent,
    ).toContain("Earlier Mara");
    await userEvent
        .setup()
        .click(screen.getByRole("button", { name: "Retry draw" }));
    expect(fetch.mock.calls[0][1].body.get("request_key")).toBe("earlier-key");
    expect(fetch.mock.calls[0][1].body.get("action")).toBe("draw");
});

it("allows an unavailable model with the same single intentional selection as the native picker", async () => {
    const mara = {
        ...model("a", "Mara"),
        mayOverride: true,
        warning: "In Recovery. Usually unavailable for selection.",
    };
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/crew/" }));
    vi.stubGlobal("fetch", fetch);
    render(<CrewWorkflow {...props([mara])} onNavigate={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "Select Mara" }));
    expect(
        screen.queryByRole("checkbox", { name: "Allow for this battle" }),
    ).toBeNull();
    await user.click(screen.getByRole("button", { name: "Save crew" }));
    expect(fetch.mock.calls[0][1].body.get("role_a")).toBe("starting");
    expect(fetch.mock.calls[0][1].body.getAll("override_a")).toEqual(["on"]);
});

it("shows the exact two submitted manual selections immediately after a lost draw response", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValue(new Error("Response lost after commit"));
    vi.stubGlobal("fetch", fetch);
    render(<CrewWorkflow {...props()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: "Select Nell" }));
    await user.selectOptions(
        screen.getByRole("combobox", { name: "Equipment set for Mara" }),
        "short",
    );
    await user.click(
        screen.getByRole("button", { name: "Draw and save draft" }),
    );
    await screen.findByRole("button", { name: "Retry draw" });
    const snapshot = screen.getByRole("region", {
        name: "Unconfirmed crew selections",
    });
    expect(snapshot.textContent).toContain(
        "Mara · Reinforcements · Close range",
    );
    expect(snapshot.textContent).toContain("Nell · Starting crew · Long range");
    expect(screen.getByText("2 models selected")).not.toBeNull();
    const stored = new URLSearchParams(
        sessionStorage.getItem(props().recoveryKey)!,
    );
    expect(JSON.parse(stored.get("submitted_snapshot")!)).toHaveLength(2);
});
