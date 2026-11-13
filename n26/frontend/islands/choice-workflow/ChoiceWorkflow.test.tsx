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
    return {
        ...props,
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
        props.recoveryKey,
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
