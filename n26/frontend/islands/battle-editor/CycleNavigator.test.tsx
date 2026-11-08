import { render, screen } from "@testing-library/react";
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
        screen.getByRole("button", { name: /Use current cycle/ }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Next cycle" }));
    expect(screen.getByText("Cycle 3")).toBeTruthy();
    expect(screen.getByText("Dates not set")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: "Leave unassigned" }),
    );
    expect(screen.getByText("No cycle selected")).toBeTruthy();
    await userEvent.click(
        screen.getByRole("button", { name: /Use current cycle/ }),
    );
    expect(screen.getByText("Current cycle")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
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
