import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ChoiceWorkflow, type ChoiceWorkflowProps } from "./ChoiceWorkflow";

const props: ChoiceWorkflowProps = {
    title: "Equipment results",
    lead: "Add results for Vex.",
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    owner: { name: "agent", badge: null },
    back: "/edit/",
    switcher: null,
    offer: {
        label: "Results",
        takesSeveral: true,
        empty: false,
        groups: [
            {
                name: "Equipment",
                caption: "Primary",
                lifted: false,
                options: [
                    {
                        key: "armour",
                        name: "Extra armour",
                        band: "1–3",
                        current: true,
                        remark: "Already chosen elsewhere",
                        summary: "Armour summary.",
                        rating: 15,
                        removalRating: 10,
                        control: "both",
                    },
                ],
            },
        ],
    },
    rollTable: { dice: "D6", lowest: 1, highest: 6 },
    roll: null,
    values: {
        request_key: "original-key",
        act: "",
        thing: "",
        remove: "",
        roll: "",
        rolled: "",
        returning: "/edit/",
        summary: "",
    },
    errors: {},
    action: "/choices/",
    commandHref: "/choices/command/",
    csrfToken: "fresh-token",
    recoveryKey: "choice:actor:gang:slot",
    recoveryHref: "/choices/?recover=1",
    signInHref: "/login/?next=/choices/",
    recoveryOnly: false,
    terminal: false,
    dialog: false,
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

test("draws repeat controls, separate ratings, band and authored copy", () => {
    render(<ChoiceWorkflow {...props} />);
    expect(screen.getByText("Primary")).toBeTruthy();
    expect(screen.getByText("1–3")).toBeTruthy();
    expect(screen.getByText("Armour summary.")).toBeTruthy();
    expect(screen.getByText("Rating per added pick 15¢")).toBeTruthy();
    expect(screen.getByText("Rating of next removed pick 10¢")).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    ).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Remove Extra armour" }),
    ).toBeTruthy();
    expect(document.querySelector("form form")).toBeNull();
    expect(document.querySelector("[data-busy=off]")).toBeTruthy();
});

test("captures the clicked repeat intent before constructing the retained body", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/choices/" }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ChoiceWorkflow {...props} onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("act")).toBe("choose");
    expect(body.get("thing")).toBe("armour");
    expect(body.get("remove")).toBe("");
    expect(body.get("request_key")).toBe("original-key");
    expect(navigate).toHaveBeenCalledWith("/choices/");
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("Enter in the manual roll input records the entered number instead of rolling", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: "/choices/?roll=event" }));
    vi.stubGlobal("fetch", fetch);
    render(<ChoiceWorkflow {...props} onNavigate={vi.fn()} />);
    expect(screen.getByRole("spinbutton").hasAttribute("min")).toBe(false);
    expect(screen.getByRole("spinbutton").hasAttribute("max")).toBe(false);
    await userEvent.type(
        screen.getByRole("spinbutton", { name: "The roll you made yourself" }),
        "4{Enter}",
    );
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("act")).toBe("enter");
    expect(body.get("rolled")).toBe("4");
});

test("a lost roll response freezes input and retries its exact key and business values", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost"))
        .mockResolvedValueOnce(json({ nextUrl: "/choices/?roll=event" }));
    vi.stubGlobal("fetch", fetch);
    render(<ChoiceWorkflow {...props} onNavigate={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: "Roll a D6" }));
    expect((screen.getByRole("spinbutton") as HTMLInputElement).disabled).toBe(
        true,
    );
    const stored = new URLSearchParams(
        sessionStorage.getItem(props.recoveryKey)!,
    );
    expect(stored.get("act")).toBe("roll");
    expect(stored.has("csrfmiddlewaretoken")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect((fetch.mock.calls[0][1].body as URLSearchParams).toString()).toBe(
        (fetch.mock.calls[1][1].body as URLSearchParams).toString(),
    );
});

test("reload restores an uncertain removal with fresh CSRF after reauthentication", async () => {
    const retained = new URLSearchParams({
        ...props.values,
        act: "remove",
        remove: "armour",
        summary: "Remove Extra armour — Results.",
    });
    sessionStorage.setItem(props.recoveryKey, retained.toString());
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ChoiceWorkflow
            {...props}
            csrfToken="rotated-token"
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByText(/Submitted choice: Remove Extra armour/),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("remove")).toBe("armour");
    expect(body.get("request_key")).toBe("original-key");
    expect(body.get("csrfmiddlewaretoken")).toBe("rotated-token");
});

test("a rejected retry cannot make an earlier unknown command editable", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            act: "roll",
            summary: "Roll D6.",
        }).toString(),
    );
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json({ errors: { __all__: ["The choice changed."] } }, 422),
            ),
    );
    render(<ChoiceWorkflow {...props} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(screen.getByText(/earlier save is still unconfirmed/)).toBeTruthy();
    expect(
        (
            screen.getByRole("button", {
                name: "Add Extra armour again",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    expect(sessionStorage.getItem(props.recoveryKey)).not.toBeNull();
});

test("terminal removal requires explicit navigation and never exposes replacement controls", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams({
            ...props.values,
            act: "roll",
            summary: "Roll D6.",
        }).toString(),
    );
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "choice_unavailable",
                    errors: { __all__: ["This save was not applied."] },
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(
        <ChoiceWorkflow
            {...props}
            offer={null}
            rollTable={null}
            recoveryOnly
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(screen.getByText("This save was not applied.")).toBeTruthy();
    expect(screen.queryByRole("radio")).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
    await userEvent.click(
        screen.getByRole("button", { name: "Return to gang" }),
    );
    expect(navigate).toHaveBeenCalledWith(props.back);
});

test("arrival selections survive a roll navigation and carry the clicked question", async () => {
    const question = {
        key: "original-choice",
        label: "Starting result",
        bearer: "Vex",
        chosen: null,
        settled: false,
        rollHref: "/roll/",
        offer: {
            ...props.offer!,
            takesSeveral: false,
            groups: props.offer!.groups.map((group) => ({
                ...group,
                options: group.options.map((option) => ({
                    ...option,
                    current: false,
                })),
            })),
        },
    };
    const values = {
        request_key: "arrival-key",
        asks: '["original-choice"]',
        next: "/edit/",
        selection: "{}",
        choice: "",
        act: "continue",
        thing: "",
        remove: "",
        summary: "",
    };
    const navigate = vi.fn();
    render(
        <ChoiceWorkflow
            {...props}
            offer={null}
            rollTable={null}
            blocks={[
                {
                    heading: "Starting choices",
                    description: "Make these choices.",
                    skippable: false,
                    questions: [question],
                },
            ]}
            values={values}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /Extra armour/ }));
    expect(
        (screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement)
            .disabled,
    ).toBe(false);
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    const retained = new URLSearchParams(
        sessionStorage.getItem(
            Array.from({ length: sessionStorage.length }, (_, index) =>
                sessionStorage.key(index)!,
            ).find((key) => key.startsWith(`${props.recoveryKey}:draft:`))!,
        )!,
    );
    expect(JSON.parse(retained.get("selection")!)).toEqual({
        "original-choice": "armour",
    });
    expect(retained.get("asks")).toBe('["original-choice"]');
    expect(navigate).toHaveBeenCalledWith("/roll/");
});

test("a completed cached page refreshes on browser Back", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(json({ nextUrl: props.back })),
    );
    const reload = vi.fn();
    render(
        <ChoiceWorkflow {...props} onNavigate={vi.fn()} onReload={reload} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Roll a D6" }));
    fireEvent(window, new PageTransitionEvent("pageshow", { persisted: true }));
    expect(reload).toHaveBeenCalledOnce();
});

test("repeated arrival questions keep distinct headings that label their controls", () => {
    const values = {
        request_key: "arrival-key",
        asks: '["original-choice"]',
        next: "/edit/",
        selection: "{}",
        choice: "",
        act: "continue",
        thing: "",
        remove: "",
        summary: "",
    };
    const question = {
        key: "original-choice",
        label: "Starting result",
        bearer: "Vex",
        chosen: null,
        settled: false,
        rollHref: "",
        offer: { ...props.offer!, takesSeveral: false },
    };
    render(
        <ChoiceWorkflow
            {...props}
            offer={null}
            rollTable={null}
            values={values}
            blocks={[
                {
                    heading: "First screen",
                    description: "",
                    skippable: false,
                    questions: [{ ...question, headingId: "first-question" }],
                },
                {
                    heading: "Second screen",
                    description: "",
                    skippable: true,
                    questions: [{ ...question, headingId: "second-question" }],
                },
            ]}
        />,
    );
    expect(
        screen.getAllByRole("heading", { name: "Starting result for Vex" }),
    ).toHaveLength(2);
    for (const id of ["first-question", "second-question"]) {
        const fieldset = document.querySelector(
            `fieldset[aria-labelledby="${id}"]`,
        );
        expect(fieldset).not.toBeNull();
        expect(fieldset!.querySelector("input[type=radio]")).not.toBeNull();
        expect(document.getElementById(id)?.tagName).toBe("H3");
    }
});

test("an externally inserted campaign dialog owns its controls and restores trigger focus on removal", async () => {
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
    };
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
    };
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const navigate = vi.fn();
    const view = render(
        <div data-external-host>
            <ChoiceWorkflow {...props} dialog onNavigate={navigate} />
        </div>,
    );
    expect(screen.getByRole("dialog").parentElement).toBe(document.body);
    expect(view.container.querySelector("dialog")).toBeNull();
    expect(document.querySelector("form form")).toBeNull();
    fireEvent(
        screen.getByRole("dialog"),
        new Event("cancel", { cancelable: true }),
    );
    expect(navigate).toHaveBeenCalledWith(props.back);
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
});

test("an uncertain dialog command prevents Escape from abandoning its retained input", async () => {
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
    };
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
    };
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("lost")));
    const navigate = vi.fn();
    render(<ChoiceWorkflow {...props} dialog onNavigate={navigate} />);
    await userEvent.click(screen.getByRole("button", { name: "Roll a D6" }));
    fireEvent(
        screen.getByRole("dialog"),
        new Event("cancel", { cancelable: true }),
    );
    expect(navigate).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(props.recoveryKey)).not.toBeNull();
    expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
});

test("a recorded roll exposes its faces and submits its exact event with Add", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: "/choices/?roll=event" }));
    vi.stubGlobal("fetch", fetch);
    render(
        <ChoiceWorkflow
            {...props}
            rollTable={null}
            values={{ ...props.values, roll: "recorded-roll" }}
            roll={{
                key: "recorded-roll",
                total: 24,
                dice: "D66",
                faces: [2, 4],
                landed: ["Extra armour"],
                entered: true,
                applied: "",
                threshold: false,
                add: { key: "armour", name: "Extra armour" },
            }}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.getByRole("img", { name: "A die showing 2" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "A die showing 4" })).toBeTruthy();
    expect(screen.getByText(/Manual roll/)).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour" }),
    );
    expect((fetch.mock.calls[0][1].body as URLSearchParams).get("roll")).toBe(
        "recorded-roll",
    );
});

test("a spent roll describes its original pick without offering its old Add action", () => {
    render(
        <ChoiceWorkflow
            {...props}
            roll={{
                key: "spent",
                total: 4,
                dice: "D6",
                faces: [4],
                landed: ["Extra armour"],
                entered: false,
                applied: "Extra armour",
                threshold: false,
                add: null,
            }}
        />,
    );
    expect(screen.getByText(/Already applied: Extra armour/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Roll again" })).toBeNull();
    expect(screen.getByRole("button", { name: "Roll a D6" })).toBeTruthy();
});

test.each([
    "Add Extra armour again",
    "Remove Extra armour",
    "Roll a D6",
    "Enter",
    "Roll again",
])(
    "only the clicked %s control shows progress while its command is pending",
    async (name) => {
        let finish!: (value: ReturnType<typeof json>) => void;
        vi.stubGlobal(
            "fetch",
            vi.fn(
                () =>
                    new Promise((resolve) => {
                        finish = resolve;
                    }),
            ),
        );
        const rolled = name === "Roll again";
        render(
            <ChoiceWorkflow
                {...props}
                rollTable={rolled ? null : props.rollTable}
                roll={
                    rolled
                        ? {
                              key: "recorded",
                              total: 4,
                              dice: "D6",
                              faces: [4],
                              landed: ["Extra armour"],
                              entered: false,
                              applied: "",
                              threshold: false,
                              add: null,
                          }
                        : null
                }
                onNavigate={vi.fn()}
            />,
        );
        const button = screen.getByRole("button", { name });
        const originalText = button.textContent;
        const originalClasses = button.className;
        await userEvent.click(button);
        expect(button.getAttribute("data-busy")).toBe("on");
        expect(button.textContent).toBe(originalText);
        expect(button.className).toBe(originalClasses);
        expect(
            document.querySelectorAll('button[data-busy="on"]'),
        ).toHaveLength(1);
        await act(async () => finish(json({ nextUrl: props.back })));
    },
);

test("authored arrival instructions preserve single line breaks and separate paragraphs", () => {
    render(
        <ChoiceWorkflow
            {...props}
            offer={null}
            rollTable={null}
            blocks={[
                {
                    heading: "Starting choices",
                    description:
                        "Choose the first result.\nThen check the equipment.\n\nContinue when ready.",
                    skippable: true,
                    questions: [],
                },
            ]}
        />,
    );
    const description = screen.getByRole("heading", {
        name: "Starting choices",
    }).parentElement!;
    const paragraphs = description.querySelectorAll("p");
    expect(paragraphs).toHaveLength(2);
    expect(paragraphs[0].querySelectorAll("br")).toHaveLength(1);
    expect(paragraphs[0].textContent).toContain("Then check the equipment.");
    expect(paragraphs[1].textContent).toBe("Continue when ready.");
});

function arrivalFixture(keys: string[], next = "/edit/"): ChoiceWorkflowProps {
    const action = `/arrivals/?${new URLSearchParams([
        ...keys.map((key) => ["ask", key]),
        ["next", next],
    ])}`;
    return {
        ...props,
        action,
        recoveryKey: "arrivals:actor:gang",
        recoveryHref: `${action}&recover=1`,
        offer: null,
        rollTable: null,
        values: {
            request_key: `${keys.join("-")}-key`,
            asks: JSON.stringify(keys),
            next,
            selection: "{}",
            choice: "",
            act: "continue",
            thing: "",
            remove: "",
            summary: "",
        },
        blocks: [
            {
                heading: "Starting choices",
                description: "",
                skippable: false,
                questions: keys.map((key) => ({
                    key,
                    headingId: `question-${key}`,
                    label: key,
                    bearer: "Vex",
                    chosen: null,
                    settled: false,
                    rollHref: key === "B" ? "/roll-B/" : "",
                    offer: {
                        ...props.offer!,
                        takesSeveral: false,
                        groups: props.offer!.groups.map((group) => ({
                            ...group,
                            options: group.options.map((option) => ({
                                ...option,
                                current: false,
                            })),
                        })),
                    },
                })),
            },
        ],
    };
}

test("an unsent A+B draft stays separate from a new C screen and returns to A+B", async () => {
    const original = arrivalFixture(["A", "B"]);
    const navigate = vi.fn();
    const first = render(
        <ChoiceWorkflow {...original} onNavigate={navigate} />,
    );
    await userEvent.click(
        within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
            "radio",
        ),
    );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    first.unmount();
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: "/arrivals-A-B/" }));
    vi.stubGlobal("fetch", fetch);
    const current = arrivalFixture(["C"], "/arrivals-A-B/");
    const second = render(
        <ChoiceWorkflow {...current} onNavigate={navigate} />,
    );
    expect((screen.getByRole("radio") as HTMLInputElement).checked).toBe(false);
    await userEvent.click(screen.getByRole("radio"));
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("asks")).toBe('["C"]');
    expect(JSON.parse(body.get("selection")!)).toEqual({ C: "armour" });
    expect(body.get("summary")).toBe("C for Vex: Extra armour");
    second.unmount();
    render(<ChoiceWorkflow {...original} onNavigate={navigate} />);
    expect(
        (
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (
            within(screen.getByRole("group", { name: "B for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(false);
});

test("an unknown A+B command stays frozen on C and retries its original scope", async () => {
    const original = arrivalFixture(["A", "B"]);
    sessionStorage.setItem(
        original.recoveryKey,
        new URLSearchParams({
            ...original.values,
            selection: '{"A":"armour"}',
            summary: "A for Vex: Extra armour",
        }).toString(),
    );
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ nextUrl: "/arrivals-A-B/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ChoiceWorkflow {...arrivalFixture(["C"])} onNavigate={vi.fn()} />);
    expect((screen.getByRole("radio") as HTMLInputElement).disabled).toBe(true);
    expect(
        screen.getByText(/Submitted choice: A for Vex: Extra armour/),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("asks")).toBe('["A","B"]');
    expect(JSON.parse(body.get("selection")!)).toEqual({ A: "armour" });
    expect(body.get("request_key")).toBe("A-B-key");
});

test("a nested saved answer replaces its stale draft while its sibling remains unsent", async () => {
    const original = arrivalFixture(["A", "B"]);
    const first = render(<ChoiceWorkflow {...original} onNavigate={vi.fn()} />);
    for (const name of ["A for Vex", "B for Vex"])
        await userEvent.click(
            within(screen.getByRole("group", { name })).getByRole("radio"),
        );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    first.unmount();
    const current = arrivalFixture(["A", "B"]);
    current.values.request_key = "fresh-return-key";
    const b = current.blocks![0].questions[1];
    b.chosen = "Helmet";
    b.settled = true;
    b.offer.groups[0].options.push({
        ...b.offer.groups[0].options[0],
        key: "helmet",
        name: "Helmet",
        current: true,
    });
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/gang/" }));
    vi.stubGlobal("fetch", fetch);
    render(<ChoiceWorkflow {...current} onNavigate={vi.fn()} />);
    expect(
        (
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (screen.getByRole("radio", { name: /Helmet/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    expect(
        (
            within(screen.getByRole("group", { name: "B for Vex" })).getByRole(
                "radio",
                { name: /Extra armour/ },
            ) as HTMLInputElement
        ).checked,
    ).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(JSON.parse(body.get("selection")!)).toEqual({ A: "armour" });
    expect(body.get("request_key")).toBe("fresh-return-key");
});

test("a confirmed nested save carries unchanged drafts into its expanded arrival task", async () => {
    const original = arrivalFixture(["A", "B"]);
    const first = render(<ChoiceWorkflow {...original} onNavigate={vi.fn()} />);
    await userEvent.click(
        within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
            "radio",
        ),
    );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    first.unmount();
    const expanded = arrivalFixture(["A", "B", "C"]);
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json({ nextUrl: expanded.action }))
        .mockResolvedValueOnce(json({ nextUrl: "/gang/" }));
    vi.stubGlobal("fetch", fetch);
    const nested = render(
        <ChoiceWorkflow
            {...props}
            action="/roll-B/"
            arrivalRecoveryKey={original.recoveryKey}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    nested.unmount();
    expanded.values.request_key = "expanded-key";
    const b = expanded.blocks![0].questions[1];
    b.chosen = "Extra armour";
    b.settled = true;
    b.offer.groups[0].options[0].current = true;
    render(<ChoiceWorkflow {...expanded} onNavigate={vi.fn()} />);
    expect(
        (
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (
            within(screen.getByRole("group", { name: "C for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(false);
    await userEvent.click(
        within(screen.getByRole("group", { name: "C for Vex" })).getByRole(
            "radio",
        ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const body = fetch.mock.calls[1][1].body as URLSearchParams;
    expect(body.get("asks")).toBe('["A","B","C"]');
    expect(JSON.parse(body.get("selection")!)).toEqual({
        A: "armour",
        C: "armour",
    });
    expect(body.get("request_key")).toBe("expanded-key");
});

test("a rejected save keeps its displayed roll in the stamped recovery URL", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json({ errors: { thing: ["Review this result."] } }, 422),
            ),
    );
    const replace = vi.spyOn(window.history, "replaceState");
    render(
        <ChoiceWorkflow
            {...props}
            recoveryHref="/choices/?roll=recorded-roll&recover=1"
            values={{ ...props.values, roll: "recorded-roll" }}
            rollTable={null}
            roll={{
                key: "recorded-roll",
                total: 4,
                dice: "D6",
                faces: [4],
                landed: ["Extra armour"],
                entered: true,
                applied: "",
                threshold: false,
                add: { key: "armour", name: "Extra armour" },
            }}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour" }),
    );
    expect(screen.getByText("Review this result.")).toBeTruthy();
    expect(replace.mock.calls.at(-1)?.[2]).toBe(
        "/choices/?roll=recorded-roll&recover=1",
    );
    expect(screen.getByRole("img", { name: "A die showing 4" })).toBeTruthy();
});

test.each([
    { keys: ["A", "C"], next: "/edit/" },
    { keys: ["A", "B", "C"], next: "/another-task/" },
])(
    "a confirmed nested return cannot transfer drafts into another task $keys $next",
    async ({ keys, next }) => {
        const original = arrivalFixture(["A", "B"]);
        const first = render(
            <ChoiceWorkflow {...original} onNavigate={vi.fn()} />,
        );
        await userEvent.click(
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ),
        );
        await userEvent.click(
            screen.getByRole("link", { name: "Roll on its own page" }),
        );
        first.unmount();
        const unrelated = arrivalFixture(keys, next);
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(json({ nextUrl: unrelated.action })),
        );
        const nested = render(
            <ChoiceWorkflow
                {...props}
                action="/roll-B/"
                arrivalRecoveryKey={original.recoveryKey}
                onNavigate={vi.fn()}
            />,
        );
        await userEvent.click(
            screen.getByRole("button", { name: "Add Extra armour again" }),
        );
        nested.unmount();
        render(<ChoiceWorkflow {...unrelated} onNavigate={vi.fn()} />);
        expect(
            (
                within(
                    screen.getByRole("group", { name: "A for Vex" }),
                ).getByRole("radio") as HTMLInputElement
            ).checked,
        ).toBe(false);
    },
);

test("passive nested handoff never rewrites an unknown arrival command", async () => {
    const original = arrivalFixture(["A", "B"]);
    const first = render(<ChoiceWorkflow {...original} onNavigate={vi.fn()} />);
    await userEvent.click(
        within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
            "radio",
        ),
    );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    first.unmount();
    const submitted = new URLSearchParams({
        ...original.values,
        selection: '{"A":"armour","B":"armour"}',
    }).toString();
    sessionStorage.setItem(original.recoveryKey, submitted);
    const expanded = arrivalFixture(["A", "B", "C"]);
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json({ nextUrl: expanded.action }))
        .mockResolvedValueOnce(json({ nextUrl: "/gang/" }));
    vi.stubGlobal("fetch", fetch);
    const nested = render(
        <ChoiceWorkflow
            {...props}
            action="/roll-B/"
            arrivalRecoveryKey={original.recoveryKey}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    nested.unmount();
    expect(sessionStorage.getItem(original.recoveryKey)).toBe(submitted);
    render(<ChoiceWorkflow {...expanded} onNavigate={vi.fn()} />);
    expect(
        (
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).disabled,
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const body = fetch.mock.calls[1][1].body as URLSearchParams;
    const exact = new URLSearchParams(body);
    exact.delete("csrfmiddlewaretoken");
    expect(exact.toString()).toBe(submitted);
});

test("a confirmed nested answer wins even when its saved state is unchanged", async () => {
    const original = arrivalFixture(["A", "B"]);
    const b = original.blocks![0].questions[1];
    const helmet = {
        ...b.offer.groups[0].options[0],
        key: "helmet",
        name: "Helmet",
        current: true,
    };
    b.chosen = "Helmet";
    b.settled = true;
    b.offer.groups[0].options.push(helmet);
    const first = render(<ChoiceWorkflow {...original} onNavigate={vi.fn()} />);
    for (const name of ["A for Vex", "B for Vex"])
        await userEvent.click(
            within(screen.getByRole("group", { name })).getByRole("radio", {
                name: /Extra armour/,
            }),
        );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    first.unmount();
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(json({ nextUrl: original.action }))
        .mockResolvedValueOnce(json({ nextUrl: "/gang/" }));
    vi.stubGlobal("fetch", fetch);
    const nested = render(
        <ChoiceWorkflow
            {...props}
            action="/roll-B/"
            arrivalRecoveryKey={original.recoveryKey}
            values={{ ...props.values, thing: "helmet" }}
            offer={{
                ...props.offer!,
                takesSeveral: false,
                groups: [{ ...props.offer!.groups[0], options: [helmet] }],
            }}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    nested.unmount();
    render(<ChoiceWorkflow {...original} onNavigate={vi.fn()} />);
    expect(
        (screen.getByRole("radio", { name: /Helmet/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    expect(
        (
            within(screen.getByRole("group", { name: "A for Vex" })).getByRole(
                "radio",
            ) as HTMLInputElement
        ).checked,
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
        JSON.parse(
            (fetch.mock.calls[1][1].body as URLSearchParams).get("selection")!,
        ),
    ).toEqual({ A: "armour" });
});

function refreshedDialog(key: string, chosen: boolean): ChoiceWorkflowProps {
    return {
        ...props,
        dialog: true,
        values: { ...props.values, request_key: key },
        offer: {
            ...props.offer!,
            groups: props.offer!.groups.map((group) => ({
                ...group,
                options: group.options.map((option) => ({
                    ...option,
                    current: chosen,
                    control: chosen ? "both" : "choose",
                })),
            })),
        },
        messages: [
            {
                text: chosen ? "Added Extra armour." : "Removed Extra armour.",
                tone: "success",
            },
        ],
    };
}

test("successive campaign commands keep one dialog and use fresh issued keys", async () => {
    const show = vi
        .spyOn(HTMLDialogElement.prototype, "showModal")
        .mockImplementation(function (this: HTMLDialogElement) {
            this.open = true;
        });
    const close = vi
        .spyOn(HTMLDialogElement.prototype, "close")
        .mockImplementation(function (this: HTMLDialogElement) {
            this.open = false;
        });
    const trigger = document.createElement("button");
    document.body.append(trigger);
    trigger.focus();
    const fetch = vi
        .fn()
        .mockResolvedValueOnce(
            json({ errors: { thing: ["Review this choice."] } }, 422),
        )
        .mockResolvedValueOnce(
            json({
                nextUrl: props.action,
                page: refreshedDialog("fresh-key-2", true),
            }),
        )
        .mockResolvedValueOnce(
            json({
                nextUrl: props.action,
                page: refreshedDialog("fresh-key-3", false),
            }),
        );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const view = render(
        <div data-gang-backdrop>
            <ChoiceWorkflow {...props} dialog onNavigate={navigate} />
        </div>,
    );
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    expect(screen.getByText("Review this choice.")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    expect(screen.queryByText("Review this choice.")).toBeNull();
    expect(screen.getByText("Added Extra armour.")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBe(dialog);
    await userEvent.click(
        screen.getByRole("button", { name: "Remove Extra armour" }),
    );
    expect(screen.getByText("Removed Extra armour.")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(dialog.contains(document.activeElement)).toBe(true);
    expect(show).toHaveBeenCalledOnce();
    expect(close).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(view.container.querySelector("[data-gang-backdrop]")).toBeTruthy();
    expect(
        fetch.mock.calls.map((call) =>
            (call[1].body as URLSearchParams).get("request_key"),
        ),
    ).toEqual(["original-key", "original-key", "fresh-key-2"]);
    expect(
        (
            document.querySelector(
                'input[name="request_key"]',
            ) as HTMLInputElement
        ).value,
    ).toBe("fresh-key-3");
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    view.unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
});

test("a campaign dialog still navigates to actual onward questions", async () => {
    const navigate = vi.fn();
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(json({ nextUrl: "/next/?ask=new" })),
    );
    render(<ChoiceWorkflow {...props} dialog onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    expect(navigate).toHaveBeenCalledWith("/next/?ask=new");
});

test("a malformed dialog refresh cannot release an uncertain command", async () => {
    const page = refreshedDialog("original-key", true);
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost"))
        .mockResolvedValueOnce(json({ nextUrl: props.action, page }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ChoiceWorkflow {...props} dialog onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    const retained = sessionStorage.getItem(props.recoveryKey);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(sessionStorage.getItem(props.recoveryKey)).toBe(retained);
    expect(screen.getByRole("button", { name: "Retry save" })).toBeTruthy();
    expect(navigate).not.toHaveBeenCalled();
    expect(
        (
            screen.getByRole("button", {
                name: "Remove Extra armour",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});

test("a lost dialog save retries its exact command before issuing the next key", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost"))
        .mockResolvedValueOnce(
            json({
                nextUrl: props.action,
                page: refreshedDialog("retry-confirmed-key", true),
            }),
        )
        .mockResolvedValueOnce(
            json({
                nextUrl: props.action,
                page: refreshedDialog("next-choice-key", false),
            }),
        );
    vi.stubGlobal("fetch", fetch);
    render(<ChoiceWorkflow {...props} dialog onNavigate={vi.fn()} />);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
        screen.getByRole("button", { name: "Add Extra armour again" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect((fetch.mock.calls[0][1].body as URLSearchParams).toString()).toBe(
        (fetch.mock.calls[1][1].body as URLSearchParams).toString(),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Remove Extra armour" }),
    );
    expect(
        (fetch.mock.calls[2][1].body as URLSearchParams).get("request_key"),
    ).toBe("retry-confirmed-key");
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("a persisted arrival instance reloads updated nested drafts without saving its cached selections", async () => {
    const original = arrivalFixture(["A", "B"]);
    const reload = vi.fn();
    const arrival = render(
        <ChoiceWorkflow {...original} onNavigate={vi.fn()} onReload={reload} />,
    );
    const arrivalForm = arrival.container.querySelector("form")!;
    for (const name of ["A for Vex", "B for Vex"])
        await userEvent.click(
            within(screen.getByRole("group", { name })).getByRole("radio"),
        );
    await userEvent.click(
        screen.getByRole("link", { name: "Roll on its own page" }),
    );
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: original.action }));
    vi.stubGlobal("fetch", fetch);
    const nested = render(
        <ChoiceWorkflow
            {...props}
            action="/roll-B/"
            values={{ ...props.values, thing: "helmet" }}
            offer={{
                ...props.offer!,
                takesSeveral: false,
                groups: [
                    {
                        ...props.offer!.groups[0],
                        options: [
                            {
                                ...props.offer!.groups[0].options[0],
                                key: "helmet",
                                name: "Helmet",
                                current: false,
                                control: "choose",
                            },
                        ],
                    },
                ],
            }}
            arrivalRecoveryKey={original.recoveryKey}
            onNavigate={vi.fn()}
        />,
    );
    await userEvent.click(
        within(nested.container).getByRole("button", {
            name: "Save",
        }),
    );
    expect((fetch.mock.calls[0][1].body as URLSearchParams).get("thing")).toBe(
        "helmet",
    );
    nested.unmount();
    const draftKey = Array.from({ length: sessionStorage.length }, (_, i) =>
        sessionStorage.key(i)!,
    ).find((key) => key.startsWith(`${original.recoveryKey}:draft:`))!;
    const updated = sessionStorage.getItem(draftKey)!;
    expect(JSON.parse(new URLSearchParams(updated).get("selection")!)).toEqual({
        A: "armour",
    });
    fireEvent(
        window,
        new PageTransitionEvent("pageshow", { persisted: false }),
    );
    expect(reload).not.toHaveBeenCalled();
    fireEvent(window, new PageTransitionEvent("pageshow", { persisted: true }));
    expect(reload).toHaveBeenCalledOnce();
    expect(arrival.container.querySelector("form")).toBe(arrivalForm);
    expect(
        (screen.getByRole("button", { name: "Continue" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    fireEvent.submit(arrivalForm);
    expect(fetch).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(draftKey)).toBe(updated);
    expect(sessionStorage.getItem(original.recoveryKey)).toBeNull();
});

test("persisted arrival refresh preserves the exact unknown command and requests one reload", async () => {
    const original = arrivalFixture(["A", "B"]);
    const fetch = vi.fn().mockRejectedValue(new Error("lost"));
    vi.stubGlobal("fetch", fetch);
    const reload = vi.fn();
    render(
        <ChoiceWorkflow {...original} onNavigate={vi.fn()} onReload={reload} />,
    );
    for (const name of ["A for Vex", "B for Vex"])
        await userEvent.click(
            within(screen.getByRole("group", { name })).getByRole("radio"),
        );
    await userEvent.click(screen.getByRole("button", { name: "Continue" }));
    const retained = sessionStorage.getItem(original.recoveryKey);
    expect(retained).toBeTruthy();
    fireEvent(window, new PageTransitionEvent("pageshow", { persisted: true }));
    expect(reload).toHaveBeenCalledOnce();
    expect(sessionStorage.getItem(original.recoveryKey)).toBe(retained);
    expect(
        (
            screen.getByRole("button", {
                name: "Retry save",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    expect(
        (
            screen.getByRole("button", {
                name: "Sign in again",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    expect(fetch).toHaveBeenCalledOnce();
});

test.each([false, true])(
    "unknown picker retry retains its original campaign endpoint: campaign=%s",
    async (campaign) => {
        const plain = props.commandHref;
        const dialog = `${plain}?dialog=campaign&display=dialog`;
        const original = campaign ? dialog : plain;
        const current = campaign ? plain : dialog;
        const fetch = vi
            .fn()
            .mockRejectedValueOnce(new Error("lost response"))
            .mockResolvedValueOnce(json({ nextUrl: "/confirmed/" }));
        vi.stubGlobal("fetch", fetch);
        const first = render(
            <ChoiceWorkflow
                {...props}
                commandHref={original}
                dialog={campaign}
                onNavigate={vi.fn()}
            />,
        );
        await userEvent.click(
            screen.getByRole("button", { name: "Add Extra armour again" }),
        );
        const stored = sessionStorage.getItem(props.recoveryKey);
        const originalBody = new URLSearchParams(fetch.mock.calls[0][1].body);
        originalBody.delete("csrfmiddlewaretoken");
        expect(originalBody.get("__choice_command")).toBe(original);
        first.unmount();
        const navigate = vi.fn();
        render(
            <ChoiceWorkflow
                {...props}
                commandHref={current}
                dialog={!campaign}
                csrfToken="rotated-context-token"
                onNavigate={navigate}
            />,
        );
        expect(sessionStorage.getItem(props.recoveryKey)).toBe(stored);
        await userEvent.click(
            screen.getByRole("button", { name: "Retry save" }),
        );
        expect(fetch.mock.calls[1][0]).toBe(original);
        const retry = new URLSearchParams(fetch.mock.calls[1][1].body);
        expect(retry.get("csrfmiddlewaretoken")).toBe("rotated-context-token");
        retry.delete("csrfmiddlewaretoken");
        expect(retry.toString()).toBe(originalBody.toString());
        expect(navigate).toHaveBeenCalledWith("/confirmed/");
        expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
    },
);

test.each([
    "https://outside.invalid/choices/command/",
    "/another-gang/command/",
    "/choices/command/?dialog=other",
    "/choices/command/?display=dialog",
    "/choices/command/?dialog=campaign&dialog=campaign",
])(
    "an unknown picker never sends retained input to an invalid command context %s",
    async (endpoint) => {
        const retained = new URLSearchParams({
            ...props.values,
            __choice_command: endpoint,
        }).toString();
        sessionStorage.setItem(props.recoveryKey, retained);
        const fetch = vi.fn();
        vi.stubGlobal("fetch", fetch);
        render(<ChoiceWorkflow {...props} onNavigate={vi.fn()} />);
        expect(
            screen.getByText(/Reopen the original choice to retry it/),
        ).toBeTruthy();
        await userEvent.click(
            screen.getByRole("button", { name: "Retry save" }),
        );
        expect(fetch).not.toHaveBeenCalled();
        expect(sessionStorage.getItem(props.recoveryKey)).toBe(retained);
    },
);
