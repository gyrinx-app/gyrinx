import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { BattleEditor, type BattleEditorProps } from "./BattleEditor";

const props: BattleEditorProps = {
    campaignName: "Ash Road",
    campaignHref: "/campaign/",
    heading: "Record a battle",
    editing: false,
    action: "/battle/new/",
    commandHref: "/battle/new/save/",
    back: "/campaign/",
    csrfToken: "fresh-csrf",
    values: {
        request_key: "command-one",
        scenario: "Street fight",
        date: "2026-11-07",
        gangs: "[]",
        cycle: '{"cycle_id":"one"}',
        crew: "",
    },
    choices: {
        gangs: [
            { value: "gang-one", label: "Ash Walkers" },
            { value: "gang-two", label: "Dust Riders" },
        ],
    },
    labels: {},
    errors: {},
    initialConflict: false,
    current: null,
    recoveryKey: "battle:actor:campaign:new",
    cycles: {
        configured: true,
        current: "Cycle 1",
        currentValue: { cycle_id: "one" },
        lastOrder: 4,
        previous: null,
        next: null,
        choices: [
            {
                value: { cycle_id: "one" },
                order: 1,
                name: "Cycle 1",
                phase: "Occupation",
                startsOn: "2026-11-02",
                endsOn: "2026-11-08",
                label: "Cycle 1 · Occupation · Current",
                hint: "",
                isCurrent: true,
            },
            {
                value: { cycle_id: "two" },
                order: 2,
                name: "Cycle 2",
                phase: "Occupation",
                startsOn: "2026-11-09",
                endsOn: "2026-11-15",
                label: "Cycle 2",
                hint: "",
                isCurrent: false,
            },
            {
                value: { cycle_id: "three" },
                order: 3,
                name: "Cycle 3",
                phase: "Occupation",
                startsOn: null,
                endsOn: null,
                label: "Cycle 3",
                hint: "",
                isCurrent: false,
            },
            {
                value: { plan_id: "plan", index: 3 },
                order: 4,
                name: "Cycle 4",
                phase: "Downtime",
                startsOn: "2026-11-23",
                endsOn: "2026-11-29",
                label: "Cycle 4 · Downtime · Projected",
                hint: "",
                isCurrent: false,
            },
        ],
    },
    cycleOptionsHref: "/cycles/options/",
    scenario: {
        rollUrl: "/scenario/",
        rolls: { crew: "" },
        tables: [
            {
                key: "crew",
                name: "Crew",
                entries: [
                    {
                        roll: 2,
                        name: "All fighters",
                        text: "Crew description.",
                        image: "",
                    },
                ],
            },
        ],
    },
};
const json = (data: unknown, status = 200) => ({
    status,
    ok: status < 400,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    sessionStorage.clear();
});

test("recovered projection remains visibly selected after materialisation and retries its original payload", async () => {
    const retained = props.cycles!.choices[3];
    const resolved = {
        ...props.cycles!,
        choices: [
            {
                ...retained,
                label: "Cycle 4 · Downtime · Saved",
                hint: "This cycle is already saved.",
            },
        ],
    };
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json(resolved))
        .mockResolvedValueOnce(json({ nextUrl: "/battle/" }));
    vi.stubGlobal("fetch", fetch);
    const first = render(<BattleEditor {...props} />);
    for (let i = 0; i < 3; i++)
        await userEvent.click(
            screen.getByRole("button", { name: "Next cycle" }),
        );
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    await screen.findByText(/The save may have completed/);
    first.unmount();
    const payload = sessionStorage.getItem(props.recoveryKey)!;
    const navigate = vi.fn();
    render(
        <BattleEditor
            {...props}
            onNavigate={navigate}
            cycles={{
                ...props.cycles!,
                choices: [
                    props.cycles!.choices[0],
                    {
                        ...retained,
                        value: { cycle_id: "four" },
                        label: "Cycle 4 · Downtime · Saved future",
                        hint: "",
                        isCurrent: false,
                    },
                ],
            }}
        />,
    );
    await screen.findByText("This cycle is already saved.");
    expect(screen.getByText("Cycle 4")).toBeTruthy();
    expect(fetch.mock.calls[1][0]).toContain("selected=");
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const retried = new URLSearchParams(fetch.mock.calls[2][1].body);
    retried.delete("csrfmiddlewaretoken");
    expect(retried.toString()).toBe(payload);
    expect(navigate).toHaveBeenCalledWith("/battle/");
});

test("archived recovery permits exact retry while fresh archived edits stay disabled", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/battle/" }));
    vi.stubGlobal("fetch", fetch);
    const first = render(<BattleEditor {...props} editing />);
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/The save may have completed/);
    first.unmount();
    const recovered = render(
        <BattleEditor {...props} editing archived onNavigate={vi.fn()} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch).toHaveBeenCalledTimes(2);
    recovered.unmount();
    render(<BattleEditor {...props} editing archived />);
    expect(
        screen
            .getByRole("button", { name: "Save changes" })
            .matches(":disabled"),
    ).toBe(true);
    expect(
        screen.getByRole("textbox", { name: "Name" }).matches(":disabled"),
    ).toBe(true);
});

test("saving waits for an adjacent-cycle read to settle", async () => {
    let finish!: (response: unknown) => void;
    vi.stubGlobal(
        "fetch",
        vi.fn().mockImplementation(
            () =>
                new Promise((resolve) => {
                    finish = resolve;
                }),
        ),
    );
    render(
        <BattleEditor
            {...props}
            cycles={{
                ...props.cycles!,
                choices: [props.cycles!.choices[0], props.cycles!.choices[3]],
            }}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(
        screen.getByRole("button", { name: "Record battle" }),
    ).toHaveProperty("disabled", true);
    expect(screen.getByText("Cycle 1")).toBeTruthy();
    await act(async () => finish(json(props.cycles)));
    expect(await screen.findByText("Cycle 2")).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Record battle" }),
    ).toHaveProperty("disabled", false);
});

test("scenario generation has its own section after the battle metadata", () => {
    render(<BattleEditor {...props} />);
    const heading = screen.getByRole("heading", { name: "Scenario", level: 2 });
    const section = heading.parentElement!.parentElement!;
    expect(
        section.contains(
            screen.getByRole("button", { name: "Generate scenario" }),
        ),
    ).toBe(true);
    expect(
        section.contains(screen.getByRole("textbox", { name: "Name" })),
    ).toBe(false);
    expect(section.contains(screen.getByLabelText("Date *"))).toBe(false);
});

test("records participant identities and an explicitly selected projected cycle", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/battle/" }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<BattleEditor {...props} onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Ash Walkers" }),
    );
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Dust Riders" }),
    );
    for (let i = 0; i < 3; i++)
        await userEvent.click(
            screen.getByRole("button", { name: "Next cycle" }),
        );
    expect(
        screen.queryByText(
            /Saving this battle also saves Cycle 2 through Cycle 4/,
        ),
    ).toBeNull();
    expect(
        screen.getByRole("button", { name: "Return to current cycle" }),
    ).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    const body = fetch.mock.calls[0][1].body as URLSearchParams;
    expect(JSON.parse(body.get("gangs")!)).toEqual(["gang-one", "gang-two"]);
    expect(JSON.parse(body.get("cycle")!)).toEqual({
        plan_id: "plan",
        index: 3,
    });
    expect(navigate).toHaveBeenCalledWith("/battle/");
});

test("scenario generation stays in the parent form and its results are saved", async () => {
    let resolve!: (value: ReturnType<typeof json>) => void;
    const fetch = vi
        .fn()
        .mockImplementationOnce(
            () =>
                new Promise((done) => {
                    resolve = done;
                }),
        )
        .mockResolvedValueOnce(json({ nextUrl: "/battle/" }));
    vi.stubGlobal("fetch", fetch);
    render(<BattleEditor {...props} onNavigate={vi.fn()} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Generate scenario" }),
    );
    await userEvent.clear(screen.getByRole("textbox", { name: "Name" }));
    await userEvent.type(
        screen.getByRole("textbox", { name: "Name" }),
        "Edited while generating",
    );
    await act(async () => {
        resolve(json({ rolls: { crew: 2 } }));
    });
    await screen.findByRole("button", { name: "Remove scenario" });
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    expect(fetch.mock.calls[1][1].body.get("crew")).toBe("2");
    expect(fetch.mock.calls[1][1].body.get("scenario")).toBe(
        "Edited while generating",
    );
});

test("an uncertain save survives reload with the exact selections and fresh credentials", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Lost response"))
        .mockResolvedValueOnce(json({ nextUrl: "/battle/" }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    const first = render(<BattleEditor {...props} onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Ash Walkers" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    await screen.findByText(/The save may have completed/);
    expect(
        screen.getByRole("textbox", { name: "Name" }).matches(":disabled"),
    ).toBe(true);
    const retained = sessionStorage.getItem(props.recoveryKey)!;
    expect(retained).not.toContain("csrf");
    first.unmount();
    render(
        <BattleEditor
            {...props}
            csrfToken="rotated-csrf"
            onNavigate={navigate}
        />,
    );
    expect(
        screen.getByRole("checkbox", { name: "Ash Walkers" }),
    ).toHaveProperty("checked", true);
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    const sent = new URLSearchParams(fetch.mock.calls[1][1].body);
    expect(sent.get("csrfmiddlewaretoken")).toBe("rotated-csrf");
    sent.delete("csrfmiddlewaretoken");
    expect(sent.toString()).toBe(retained);
    expect(navigate).toHaveBeenCalledWith("/battle/");
});

test("a specific revision conflict freezes the draft beside current facts", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    code: "revision_conflict",
                    errors: { __all__: ["The battle changed."] },
                    current: {
                        revision: 2,
                        scenario: "Server battle",
                        date: "2026-11-08",
                    },
                    reviewUrl: "/edit/",
                },
                409,
            ),
        ),
    );
    const navigate = vi.fn();
    render(<BattleEditor {...props} onNavigate={navigate} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    await screen.findByText("Server battle · 2026-11-08");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveProperty(
        "value",
        "Street fight",
    );
    expect(
        screen.getByRole("textbox", { name: "Name" }).matches(":disabled"),
    ).toBe(true);
    await userEvent.click(
        screen.getByRole("button", { name: "Review current battle" }),
    );
    expect(navigate).toHaveBeenCalledWith("/edit/");
});

test("server validation preserves checked participants and focuses its errors", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                json(
                    { errors: { gangs: ["Choose an active campaign gang."] } },
                    422,
                ),
            ),
    );
    render(<BattleEditor {...props} onNavigate={vi.fn()} />);
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Ash Walkers" }),
    );
    fireEvent.submit(
        screen.getByRole("textbox", { name: "Name" }).closest("form")!,
    );
    const summary = await screen.findByRole("alert", {
        name: "Battle save errors",
    });
    expect(document.activeElement).toBe(summary);
    expect(
        screen.getByRole("checkbox", { name: "Ash Walkers" }),
    ).toHaveProperty("checked", true);
    expect(
        screen.getByRole("textbox", { name: "Name" }).matches(":disabled"),
    ).toBe(false);
});

test("flag-off props render the legacy fields without cycle selection", () => {
    const { cycle: _cycle, ...values } = props.values;
    render(
        <BattleEditor
            {...props}
            values={values}
            cycles={null}
            cycleOptionsHref=""
        />,
    );
    expect(screen.queryByRole("group", { name: "Campaign cycle" })).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Ash Walkers" })).toBeTruthy();
});

test("editing retains the awarded stake and visibly reports a stale ownership snapshot", async () => {
    const message =
        "The available stakes changed. Reload the battle before saving.";
    const fetch = vi
        .fn()
        .mockResolvedValue(json({ errors: { __all__: [message] } }, 422));
    vi.stubGlobal("fetch", fetch);
    render(
        <BattleEditor
            {...props}
            editing
            heading="Edit battle"
            scenario={null}
            values={{
                ...props.values,
                gangs: '["gang-one"]',
                winners: '["gang-one"]',
                result: "winners",
                revision: "1",
                stake: "ruins",
                stake_awarded_to: "gang-one",
                stake_versions: "signed-version",
            }}
            labels={{
                result: "Outcome",
                stake: "Territory staked",
                stake_awarded_to: "Territory goes to",
            }}
            choices={{
                ...props.choices,
                winners: props.choices.gangs,
                result: [{ value: "winners", label: "Winner or winners" }],
                stake: [{ value: "ruins", label: "Old Ruins" }],
                stake_awarded_to: props.choices.gangs,
            }}
        />,
    );
    const award = screen.getByRole("combobox", { name: "Territory goes to" });
    expect(award).toHaveProperty("value", "gang-one");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const summary = await screen.findByRole("alert", {
        name: "Battle save errors",
    });
    expect(summary.textContent).toContain(message);
    expect(award).toHaveProperty("value", "gang-one");
    expect(fetch.mock.calls[0][1].body.get("stake_awarded_to")).toBe(
        "gang-one",
    );
    expect(fetch.mock.calls[0][1].body.get("stake_versions")).toBe(
        "signed-version",
    );
});

test("invalid prefilled components remain visible and are submitted unchanged", async () => {
    const fetch = vi.fn().mockResolvedValue(
        json(
            {
                errors: {
                    __all__: ["A scenario component is not on its table."],
                },
            },
            422,
        ),
    );
    vi.stubGlobal("fetch", fetch);
    render(<BattleEditor {...props} values={{ ...props.values, crew: "9" }} />);
    expect(
        screen.getByText(/This link names a scenario component/),
    ).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Record battle" }),
    );
    await screen.findByRole("alert", { name: "Battle save errors" });
    expect(fetch.mock.calls[0][1].body.get("crew")).toBe("9");
    expect(screen.getByRole("textbox", { name: "Name" })).toHaveProperty(
        "value",
        "Street fight",
    );
});

test.each([false, true])(
    "flag changes preserve the exact earlier command (initially enabled: %s)",
    async (initiallyEnabled) => {
        const { cycle: _cycle, ...withoutCycle } = props.values;
        const original = new URLSearchParams(
            initiallyEnabled ? props.values : withoutCycle,
        );
        sessionStorage.setItem(props.recoveryKey, original.toString());
        const fetch = vi.fn().mockResolvedValue(json({ nextUrl: "/battle/" }));
        vi.stubGlobal("fetch", fetch);
        const navigate = vi.fn();
        render(
            <BattleEditor
                {...props}
                values={initiallyEnabled ? withoutCycle : props.values}
                cycles={initiallyEnabled ? null : props.cycles}
                onNavigate={navigate}
            />,
        );
        expect(
            screen.getByRole("textbox", { name: "Name" }).matches(":disabled"),
        ).toBe(true);
        await userEvent.click(
            screen.getByRole("button", { name: "Retry save" }),
        );
        const body = new URLSearchParams(fetch.mock.calls[0][1].body);
        body.delete("csrfmiddlewaretoken");
        expect(body.toString()).toBe(original.toString());
        expect(navigate).toHaveBeenCalledWith("/battle/");
    },
);
