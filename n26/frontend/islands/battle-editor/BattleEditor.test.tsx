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
        previous: null,
        next: null,
        choices: [
            {
                value: { cycle_id: "one" },
                label: "Cycle 1 · Occupation · Current",
                hint: "",
                isCurrent: true,
            },
            {
                value: { plan_id: "plan", index: 3 },
                label: "Cycle 4 · Downtime · Projected",
                hint: "Saving this battle also saves Cycle 2 through Cycle 4. The current cycle remains Cycle 1.",
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
    await userEvent.selectOptions(
        screen.getByRole("combobox", { name: "Campaign cycle" }),
        '{"plan_id":"plan","index":3}',
    );
    expect(
        screen.getByText(
            /Saving this battle also saves Cycle 2 through Cycle 4/,
        ),
    ).toBeTruthy();
    expect(screen.getByText(/selected cycle differs/)).toBeTruthy();
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
    expect(
        screen.queryByRole("combobox", { name: "Campaign cycle" }),
    ).toBeNull();
    expect(screen.getByRole("checkbox", { name: "Ash Walkers" })).toBeTruthy();
});
