import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ModelSkills, type ModelSkillsProps } from "./ModelSkills";

const props: ModelSkillsProps = {
    name: "Vex",
    lead: "Select skills for Vex.",
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    owner: { name: "agent", badge: null },
    back: "/edit/",
    switcher: {
        heading: "Vex",
        menuLabel: "Select skills for another fighter",
        placeholder: "Find model",
        empty: "No models",
        source: "/switch/",
        next: null,
        items: [],
    },
    collections: [
        { label: "Skills", href: "?list=skills", current: true },
        { label: "Powers", href: "?list=powers", current: false },
    ],
    nothingToSelect: false,
    groups: [
        {
            name: "Agility",
            caption: "Primary",
            options: [
                {
                    key: "catfall",
                    name: "Catfall",
                    remark: "already known",
                    summary: "A skill summary.",
                    rating: 0,
                },
                {
                    key: "dodge",
                    name: "Dodge",
                    remark: "Usable by walkers only",
                    summary: "",
                    rating: 0,
                },
            ],
        },
        {
            name: "Wyrd Powers",
            caption: "Secondary",
            options: [
                {
                    key: "terrify",
                    name: "Terrify (Double)",
                    remark: "",
                    summary: "A power summary.",
                    rating: 30,
                },
            ],
        },
    ],
    values: {
        gang: "gang",
        collection: "skills",
        thing: "",
        thing_label: "",
        request_key: "request-key",
    },
    errors: {},
    action: "/skills/?list=skills",
    commandHref: "/skills/command/",
    signInHref: "/login/?next=/skills/",
    csrfToken: "fresh",
    recoveryKey: "model-skills:actor:gang:model",
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

test("preserves placed tiers, known and restricted skills, summaries and power rating", () => {
    render(<ModelSkills {...props} />);
    expect(screen.getByRole("group", { name: "Agility" })).toBeTruthy();
    expect(screen.getByText("Primary")).toBeTruthy();
    expect(screen.getByText("Secondary")).toBeTruthy();
    expect(screen.getByText("already known")).toBeTruthy();
    expect(screen.getByText("Usable by walkers only")).toBeTruthy();
    expect(screen.getByText("A skill summary.")).toBeTruthy();
    expect(screen.getByText("Rating 30¢")).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Cancel" }).getAttribute("href"),
    ).toBe(props.back);
    expect(
        screen.getAllByRole("link", { name: "Powers" })[0].getAttribute("href"),
    ).toBe("?list=powers");
    expect(document.querySelector("form form")).toBeNull();
    expect(
        screen.getByRole("link", { name: "Cancel" }).nextElementSibling,
    ).toBe(screen.getByRole("button", { name: "Select" }));
});

test("selects one stable identity across skill and power groups at no entered payment", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ModelSkills {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Terrify/ }));
    expect(
        (screen.getByRole("radio", { name: /Dodge/ }) as HTMLInputElement)
            .checked,
    ).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    const body = fetch.mock.calls[0][1].body;
    expect(body.get("thing")).toBe("terrify");
    expect(body.get("collection")).toBe("skills");
    expect(body.get("thing_label")).toBe("Terrify (Double)");
    expect(body.get("request_key")).toBe("request-key");
    expect(body.has("paid")).toBe(false);
    expect(navigate).toHaveBeenCalledWith(props.back);
});

test("known refusals leave the selected skill editable", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json({ errors: { thing: ["Vex already has Catfall."] } }, 422),
            ),
    );
    render(<ModelSkills {...props} />);
    await userEvent.click(screen.getByRole("radio", { name: /Catfall/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(await screen.findByText("Vex already has Catfall.")).toBeTruthy();
    expect(
        screen
            .getByRole("radio", { name: /Catfall/ })
            .closest("fieldset[disabled]"),
    ).toBeNull();
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    expect(
        (screen.getByRole("radio", { name: /Dodge/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    expect(document.activeElement).toBe(
        screen.getByRole("radio", { name: /Dodge/ }),
    );
});

test("retains a lost save and cannot edit it until the original command is confirmed", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new TypeError("network"))
        .mockResolvedValueOnce(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ModelSkills {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Terrify/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(
        await screen.findByText("Submitted selection: Terrify (Double)."),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("radio", { name: /Dodge/ })
            .closest("fieldset[disabled]"),
    ).not.toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("alert"));
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[1][1].body.toString()).toBe(
        fetch.mock.calls[0][1].body.toString(),
    );
    expect(navigate).toHaveBeenCalledWith(props.back);
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("reload after an offer disappears still retries the readable original selection with fresh CSRF", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            thing: "removed",
            thing_label: "Original skill",
            csrfmiddlewaretoken: "old",
        }).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ModelSkills
            {...props}
            groups={[]}
            csrfToken="new-csrf"
            values={{
                ...props.values,
                collection: "new-list",
                request_key: "new-key",
            }}
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByText("Submitted selection: Original skill."),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body;
    expect(body.get("thing")).toBe("removed");
    expect(body.get("collection")).toBe("skills");
    expect(body.get("request_key")).toBe("request-key");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("new-csrf");
});

test("a rejected retry cannot release an earlier uncertain selection", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockRejectedValueOnce(new TypeError("network"))
            .mockResolvedValueOnce(
                json(
                    { errors: { thing: ["That skill is no longer offered."] } },
                    422,
                ),
            ),
    );
    render(<ModelSkills {...props} />);
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry save" }),
    );
    expect(
        await screen.findByText(/earlier save is still unconfirmed/),
    ).toBeTruthy();
    expect(
        screen
            .getByRole("radio", { name: /Dodge/ })
            .closest("fieldset[disabled]"),
    ).not.toBeNull();
    expect(sessionStorage.getItem(props.recoveryKey)).toContain("request-key");
});

test("sign-in recovery retains a rejected draft and rotates CSRF", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json({ error: "Sign in again." }, 401))
        .mockResolvedValueOnce(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const mounted = render(<ModelSkills {...props} onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    await userEvent.click(await screen.findByRole("link", { name: "Sign in" }));
    expect(navigate).toHaveBeenCalledWith(props.signInHref);
    mounted.unmount();
    render(
        <ModelSkills
            {...props}
            csrfToken="rotated"
            values={{ ...props.values, request_key: "new-key" }}
            onNavigate={navigate}
        />,
    );
    expect(
        (screen.getByRole("radio", { name: /Dodge/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(fetch.mock.calls[1][1].body.get("request_key")).toBe("request-key");
    expect(fetch.mock.calls[1][1].headers["X-CSRFToken"]).toBe("rotated");
});

test("the submitting control keeps its label and blocks another save while pending", async () => {
    const fetch = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetch);
    render(<ModelSkills {...props} />);
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(
        screen
            .getByRole("button", { name: "Select" })
            .getAttribute("aria-busy"),
    ).toBe("true");
    expect(
        screen.getByRole("button", { name: "Select" }).hasAttribute("disabled"),
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(
        screen
            .getByRole("radio", { name: /Dodge/ })
            .closest("fieldset[disabled]"),
    ).not.toBeNull();
});

test.each([true, false])(
    "empty grids and empty placed sets keep navigation without a submit: %s",
    (nothingToSelect) => {
        render(
            <ModelSkills
                {...props}
                nothingToSelect={nothingToSelect}
                groups={[]}
            />,
        );
        expect(screen.queryByRole("button", { name: "Select" })).toBeNull();
        expect(
            screen.getByRole("link", { name: props.name }).getAttribute("href"),
        ).toBe(props.back);
        expect(
            screen.getByText(
                nothingToSelect
                    ? /not graded in any skill category/
                    : /No skills or powers/,
            ),
        ).toBeTruthy();
    },
);

test("marks the collection-aware recovery address before sending a selection", async () => {
    const history = vi.spyOn(window.history, "replaceState");
    const fetch = vi.fn().mockImplementation(() => {
        expect(history).toHaveBeenCalledWith(
            window.history.state,
            "",
            "/skills/?list=skills&recover=1",
        );
        return new Promise(() => {});
    });
    vi.stubGlobal("fetch", fetch);
    render(
        <ModelSkills
            {...props}
            recoveryHref="/skills/?list=skills&recover=1"
        />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /Dodge/ }));
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(fetch).toHaveBeenCalledTimes(1);
});

test("a removed model restores only its retained selection with fresh credentials", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            thing: "terrify",
            thing_label: "Terrify (Double)",
        }).toString(),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.gangHref }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ModelSkills
            {...props}
            recoveryOnly
            groups={[]}
            collections={[]}
            switcher={null}
            values={{ ...props.values, request_key: "new-key" }}
            csrfToken="rotated"
            onNavigate={navigate}
        />,
    );
    expect(
        screen.getByText("Submitted selection: Terrify (Double)."),
    ).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.queryByRole("button", { name: "Select" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.get("request_key")).toBe("request-key");
    expect(fetch.mock.calls[0][1].body.get("thing")).toBe("terrify");
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("rotated");
    expect(navigate).toHaveBeenCalledWith(props.gangHref);
});

test("a durable no-write result allows returning to the gang without enabling editing", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            thing: "dodge",
            thing_label: "Dodge",
        }).toString(),
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
        <ModelSkills
            {...props}
            recoveryOnly
            groups={[]}
            collections={[]}
            switcher={null}
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

test("a recovery page with no browser command provides no write control", () => {
    render(
        <ModelSkills
            {...props}
            recoveryOnly
            groups={[]}
            collections={[]}
            switcher={null}
        />,
    );
    expect(
        screen.getByText("No unconfirmed save was found in this browser."),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retry save" })).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
});
