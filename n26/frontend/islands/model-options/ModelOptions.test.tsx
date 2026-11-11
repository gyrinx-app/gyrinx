import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { card } from "../../test/modelCard";
import { ModelOptions, type ModelOptionsProps } from "./ModelOptions";

const props: ModelOptionsProps = {
    name: "Vex",
    role: "Ganger",
    owner: { name: "agent", badge: null },
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    figures: {
        items: [],
        roster: { count: 0, rating: 0, groups: [], models: [] },
    },
    card,
    tabs: [
        { label: "Edit", href: "/edit/", current: false },
        { label: "Equip", href: "/equip/", current: false },
        { label: "Options", href: "/options/", current: true },
    ],
    switcher: {
        heading: "Vex",
        menuLabel: "Switch model",
        placeholder: "Find model",
        empty: "No models",
        source: "/switch/",
        next: null,
        items: [],
    },
    groups: [
        {
            key: "one",
            choose: "one",
            visible: true,
            options: [
                { key: "knife", name: "Knife", price: 0, checked: true },
                { key: "sword", name: "Chainsword", price: 25, checked: false },
            ],
        },
        {
            key: "any",
            choose: "any",
            visible: true,
            options: [
                { key: "grenade", name: "Grenade", price: 5, checked: false },
            ],
        },
        {
            key: "maybe",
            choose: "one-or-none",
            visible: true,
            options: [
                { key: "pistol", name: "Pistol", price: 10, checked: false },
            ],
        },
    ],
    values: {
        gang: "gang",
        selection: '["knife"]',
        selection_label: "Knife",
        snapshot: "signed",
        request_key: "request-key",
    },
    errors: {},
    conflict: null,
    signInHref: "/login/?next=/options/",
    action: "/options/",
    back: "/edit/",
    commandHref: "/options/command/",
    csrfToken: "fresh",
    recoveryKey: "options:actor:gang:model",
    messages: [],
};
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

test("posts stable choices across one, any and optional groups", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.action }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ModelOptions {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Chainsword/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Grenade/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Pistol/ }));
    await userEvent.click(screen.getByRole("radio", { name: "None" }));
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    const body = fetch.mock.calls[0][1].body;
    expect(JSON.parse(body.get("selection"))).toEqual(["sword", "grenade"]);
    expect(body.get("request_key")).toBe("request-key");
    expect(body.get("snapshot")).toBe("signed");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("fresh");
    expect(navigate).toHaveBeenCalledWith(props.action);
});

test("keeps the clicked label stable while saving and blocks selection edits", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<ModelOptions {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    expect(
        screen
            .getByRole("button", { name: "Save options" })
            .hasAttribute("disabled"),
    ).toBe(true);
    expect(
        screen
            .getByRole("radio", { name: "Knife" })
            .closest("form")
            ?.querySelector("fieldset[disabled]"),
    ).not.toBeNull();
    expect(
        screen
            .getByRole("button", { name: "Save options" })
            .getAttribute("aria-busy"),
    ).toBe("true");
});

test("retries a lost response with the original identity and frozen readable choices", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new TypeError("network"))
        .mockResolvedValueOnce(json({ nextUrl: props.action }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ModelOptions {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Chainsword/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    expect(
        await screen.findByText("Submitted options: Chainsword."),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("radio", { name: "Knife" })
            .closest("form")
            ?.querySelector("fieldset[disabled]"),
    ).not.toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("alert"));
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
    expect(navigate).toHaveBeenCalledWith(props.action);
});

test("reload recovery preserves removed choices and uses fresh credentials", async () => {
    const retained = new URLSearchParams({
        ...props.values,
        selection: '["removed"]',
        selection_label: "Original armament",
        csrfmiddlewaretoken: "old",
    });
    sessionStorage.setItem(props.recoveryKey, retained.toString());
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.action }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ModelOptions
            {...props}
            values={{
                ...props.values,
                snapshot: "new",
                request_key: "new-key",
            }}
            csrfToken="new-csrf"
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByText("Submitted options: Original armament."),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.get("selection")).toBe('["removed"]');
    expect(fetch.mock.calls[0][1].body.get("snapshot")).toBe("signed");
    expect(fetch.mock.calls[0][1].body.get("request_key")).toBe("request-key");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("new-csrf");
});

test("a refusal after an unknown write does not release the original draft", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockRejectedValueOnce(new TypeError("network"))
            .mockResolvedValueOnce(
                json(
                    { errors: { __all__: ["This form was already used."] } },
                    422,
                ),
            ),
    );
    render(<ModelOptions {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry save" }),
    );
    expect(
        await screen.findByText(/earlier save is still unconfirmed/),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("radio", { name: "Knife" })
            .closest("form")
            ?.querySelector("fieldset[disabled]"),
    ).not.toBeNull();
    expect(sessionStorage.getItem(props.recoveryKey)).toContain("request-key");
});

test.each([false, true])(
    "a confirmed revision conflict requires explicit review after uncertainty: %s",
    async (uncertain) => {
        const fetch = vi.fn();
        if (uncertain) fetch.mockRejectedValueOnce(new TypeError("network"));
        vi.stubGlobal(
            "fetch",
            fetch.mockResolvedValue(
                json(
                    {
                        code: "revision_conflict",
                        current: { name: "Vex", options: ["Pistol"] },
                        errors: { __all__: ["Review the current options."] },
                    },
                    409,
                ),
            ),
        );
        const navigate = vi.fn();
        render(<ModelOptions {...props} onNavigate={navigate} />);
        await userEvent.click(
            screen.getByRole("button", { name: "Save options" }),
        );
        if (uncertain) {
            await userEvent.click(
                await screen.findByRole("button", { name: "Retry save" }),
            );
        }
        expect(
            (
                await screen.findByRole("region", {
                    name: "Current model options",
                })
            ).textContent,
        ).toContain("Pistol");
        expect(
            screen
                .getByRole("radio", { name: "Knife" })
                .closest("form")
                ?.querySelector("fieldset[disabled]"),
        ).not.toBeNull();
        await userEvent.click(
            screen.getByRole("button", { name: "Review current options" }),
        );
        expect(navigate).toHaveBeenCalledWith(props.action);
        expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    },
);

test("known validation errors keep controls editable and preserve selections", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json({ errors: { __all__: ["Not enough credits."] } }, 422),
            ),
    );
    render(<ModelOptions {...props} />);
    await userEvent.click(screen.getByRole("radio", { name: /Chainsword/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    expect(await screen.findByText("Not enough credits.")).toBeTruthy();
    expect(
        (screen.getByRole("radio", { name: /Chainsword/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    expect(
        screen
            .getByRole("radio", { name: "Knife" })
            .closest("form")
            ?.querySelector("fieldset[disabled]"),
    ).toBeNull();
});

test("the card's independent counter forms do not nest inside the options form", () => {
    render(<ModelOptions {...props} />);
    expect(document.querySelector("form form")).toBeNull();
    expect(
        screen
            .getByRole("button", { name: "Add one to Ammo" })
            .closest("form")
            ?.getAttribute("action"),
    ).toBe("/counter/");
    expect(
        screen.getByRole("navigation", { name: "This model's screens" })
            .textContent,
    ).toContain("Options");
});

test("no selectable alternatives produces an informational page without save controls", () => {
    render(<ModelOptions {...props} groups={[]} />);
    expect(screen.getByText(/offers no options/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save options" })).toBeNull();
});

test("stamps a reloadable recovery address before a pending request is sent", async () => {
    const history = vi.spyOn(window.history, "replaceState");
    const fetch = vi.fn().mockImplementation(() => {
        expect(history).toHaveBeenCalledWith(
            window.history.state,
            "",
            "/options/?recover=1",
        );
        return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetch);
    render(<ModelOptions {...props} recoveryHref="/options/?recover=1" />);
    await userEvent.click(screen.getByRole("button", { name: "Save options" }));
    expect(fetch).toHaveBeenCalledTimes(1);
});

test("a removed-model reload restores only the original read-only command", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            selection: '["sword"]',
            selection_label: "Chainsword",
        }).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.gangHref }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ModelOptions
            {...props}
            recoveryOnly
            recoveryHref="/options/?recover=1"
            card={null}
            figures={null}
            switcher={null}
            groups={[]}
            csrfToken="rotated"
            values={{
                ...props.values,
                request_key: "new-key",
                snapshot: "new-snapshot",
            }}
            onNavigate={navigate}
        />,
    );
    expect(screen.getByText("Submitted options: Chainsword.")).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save options" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.get("request_key")).toBe("request-key");
    expect(fetch.mock.calls[0][1].body.get("snapshot")).toBe("signed");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("rotated");
    expect(navigate).toHaveBeenCalledWith(props.gangHref);
});

test("a durable removed-model refusal ends recovery only through return to the gang", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams(props.values).toString(),
    );
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "model_removed",
                    errors: { __all__: ["This save was not applied."] },
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(
        <ModelOptions
            {...props}
            recoveryOnly
            card={null}
            figures={null}
            switcher={null}
            groups={[]}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(await screen.findByText("This save was not applied.")).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    await userEvent.click(
        screen.getByRole("button", { name: "Return to gang" }),
    );
    expect(navigate).toHaveBeenCalledWith(props.gangHref);
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("a recovery address without a retained command has no write control", () => {
    render(
        <ModelOptions
            {...props}
            recoveryOnly
            card={null}
            figures={null}
            switcher={null}
            groups={[]}
        />,
    );
    expect(
        screen.getByText("No unconfirmed save was found in this browser."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
});
