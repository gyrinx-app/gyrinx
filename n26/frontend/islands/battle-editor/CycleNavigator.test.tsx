import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, expect, test, vi } from "vitest";
import {
    CycleNavigator,
    type CycleChoice,
    type CycleOptions,
} from "./CycleNavigator";

const choice = (order: number): CycleChoice => ({
    order,
    name: `Cycle ${order}`,
    phase: "Occupation",
    label: `Cycle ${order} · Occupation`,
    value: { cycle_id: String(order) },
    startsOn: "2026-11-02",
    endsOn: "2026-11-08",
    hint: "",
    isCurrent: order === 2,
});
const initial: CycleOptions = {
    configured: true,
    current: "Cycle 2",
    currentValue: choice(2).value,
    lastOrder: 7,
    choices: [
        choice(1),
        choice(2),
        { ...choice(3), startsOn: null, endsOn: null },
    ],
    previous: null,
    next: null,
};
function Navigator({ data = initial }: { data?: CycleOptions }) {
    const [value, setValue] = useState(JSON.stringify(choice(2).value));
    return (
        <CycleNavigator
            initial={data}
            value={value}
            onChange={setValue}
            readUrl="/choices/"
        />
    );
}
afterEach(() => vi.unstubAllGlobals());

test("current cycle and dates remain clear when moving backwards, forwards and back to current", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    render(<Navigator />);
    expect(screen.getByText("Current cycle")).toBeTruthy();
    expect(screen.getByText("2 Nov 2026")).toBeTruthy();
    expect(screen.getByText("8 Nov 2026")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Previous cycle" }),
    );
    expect(screen.getByText("Cycle 1")).toBeTruthy();
    expect(
        screen.getByRole("button", { name: "Previous cycle" }),
    ).toHaveProperty("disabled", true);
    await userEvent.click(
        screen.getByRole("button", { name: "Return to current cycle" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(screen.getByText("Cycle 3")).toBeTruthy();
    expect(screen.getByText("Dates not set")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Leave unassigned" }),
    );
    expect(screen.getByText("No cycle selected")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Return to current cycle" }),
    );
    expect(screen.getByText("Current cycle")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
});

test("a schedule without a current cycle stays unassigned until browsing its first preview", async () => {
    const change = vi.fn();
    const preview = {
        ...choice(1),
        isCurrent: false,
        value: { plan_id: "pattern", index: 0 },
    };
    render(
        <CycleNavigator
            initial={{
                ...initial,
                current: "No current cycle",
                currentValue: null,
                choices: [preview],
            }}
            value="null"
            onChange={change}
            readUrl="/choices/"
        />,
    );
    expect(screen.getByText("No cycle selected")).toBeTruthy();
    expect(
        screen.queryByRole("button", { name: "Return to current cycle" }),
    ).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(change).toHaveBeenCalledWith(JSON.stringify(preview.value));
});

test("a gap in loaded history fetches the adjacent cycle rather than skipping forward", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("Offline"))
        .mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
                ...initial,
                choices: [choice(2), choice(3), choice(7)],
            }),
        });
    vi.stubGlobal("fetch", fetch);
    render(
        <Navigator data={{ ...initial, choices: [choice(2), choice(7)] }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Cycle 2")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(await screen.findByText("Cycle 3")).toBeTruthy();
    expect(screen.queryByText("Cycle 7")).toBeNull();
    expect(fetch.mock.calls[0][0]).toContain("selected=");
});

test("deleted number gaps use the server's live neighbours", async () => {
    const change = vi.fn();
    render(
        <CycleNavigator
            initial={{
                ...initial,
                choices: [choice(2), choice(5)],
                adjacent: { anchor: 2, previous: null, next: 5 },
            }}
            value={JSON.stringify(choice(2).value)}
            onChange={change}
            readUrl="/choices/"
        />,
    );
    expect(
        screen.getByRole("button", { name: "Previous cycle" }),
    ).toHaveProperty("disabled", true);
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(change).toHaveBeenCalledWith(JSON.stringify(choice(5).value));
});

test.each(["Previous cycle", "Next cycle"])(
    "a refreshed %s boundary keeps the selection without showing an error",
    async (label) => {
        const forwards = label === "Next cycle";
        const fetch = vi.fn().mockResolvedValue({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
                ...initial,
                choices: forwards ? [choice(2), choice(5)] : [choice(2)],
                adjacent: forwards
                    ? { anchor: 5, previous: 2, next: null }
                    : { anchor: 2, previous: null, next: null },
            }),
        });
        vi.stubGlobal("fetch", fetch);
        render(
            <Navigator
                data={{
                    ...initial,
                    choices: forwards ? [choice(2), choice(5)] : [choice(2)],
                    ...(forwards
                        ? { adjacent: { anchor: 2, previous: null, next: 5 } }
                        : {}),
                }}
            />,
        );
        const button = screen.getByRole("button", { name: label });
        if (forwards) {
            await userEvent.click(button);
            expect(screen.getByText("Cycle 5")).toBeTruthy();
            expect(fetch).not.toHaveBeenCalled();
        }
        expect(button).toHaveProperty("disabled", false);
        await userEvent.click(button);
        await waitFor(() => expect(button).toHaveProperty("disabled", true));
        expect(screen.getByText(forwards ? "Cycle 5" : "Cycle 2")).toBeTruthy();
        expect(screen.queryByRole("alert")).toBeNull();
        expect(fetch).toHaveBeenCalledTimes(1);
    },
);

test.each([
    [null, null, [], ["Dates not set"]],
    ["2026-11-02", null, ["2 Nov 2026"], ["End date not set"]],
    [null, "2026-11-08", ["8 Nov 2026"], ["Start date not set"]],
    ["2026-11-02", "2026-11-08", ["2 Nov 2026", "8 Nov 2026"], []],
] as const)(
    "cycle navigation shows each known bound and explicit missing dates (%s, %s)",
    (start, end, known, missing) => {
        render(
            <Navigator
                data={{
                    ...initial,
                    choices: [{ ...choice(2), startsOn: start, endsOn: end }],
                }}
            />,
        );
        for (const date of known) expect(screen.getByText(date)).toBeTruthy();
        for (const label of missing)
            expect(screen.getByText(label)).toBeTruthy();
        expect(screen.queryByText(/^From |^Until /)).toBeNull();
        expect(
            screen.getByRole("button", { name: "Previous cycle" }),
        ).toBeTruthy();
        expect(screen.getByRole("button", { name: "Next cycle" })).toBeTruthy();
    },
);
