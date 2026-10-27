import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BattleScenario, type BattleScenarioProps } from "./BattleScenario";
const props: BattleScenarioProps = {
    rollUrl: "/n26/scenario/",
    rolls: {},
    tables: [
        {
            key: "crew",
            name: "Crew",
            entries: [
                {
                    roll: 2,
                    name: "Hold Nothing Back",
                    text: "Both players use Custom (10).",
                    image: "",
                },
            ],
        },
        {
            key: "objective",
            name: "Objective",
            entries: [
                {
                    roll: 1,
                    name: "King of the Hive",
                    text: "Objective text.",
                    image: "",
                },
            ],
        },
    ],
};
afterEach(() => vi.unstubAllGlobals());
it("generates an optional scenario without changing the battle name", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <>
            <input aria-label="Name" defaultValue="Sump clash" />
            <BattleScenario {...props} />
        </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await screen.findByRole("button", { name: "Remove scenario" });
    expect(screen.getByLabelText("Name")).toHaveProperty("value", "Sump clash");
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
    expect(
        screen
            .getByRole("link", { name: "View scenario" })
            .getAttribute("href"),
    ).toBe("/n26/scenario/?crew=2");
    fireEvent.click(screen.getByRole("button", { name: "Remove scenario" }));
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("");
});
it("sends component choices to the generator", async () => {
    const request = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    vi.stubGlobal("fetch", request);
    render(<BattleScenario {...props} />);
    fireEvent.change(screen.getByLabelText("Crew"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Objective"), {
        target: { value: "leave" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await waitFor(() => expect(request).toHaveBeenCalled());
    const url = new URL(request.mock.calls[0][0]);
    expect(url.searchParams.get("crew_pick")).toBe("2");
    expect(url.searchParams.get("objective_pick")).toBe("leave");
});
it("preserves the existing result after a failed generation", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error()));
    const { container } = render(
        <BattleScenario {...props} rolls={{ crew: "2" }} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await screen.findByRole("alert");
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
});
it("retains an invalid component until the reader generates or removes it", () => {
    const { container } = render(
        <BattleScenario {...props} rolls={{ crew: "9", objective: "1" }} />,
    );
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("9");
    expect(container.querySelector("dl")).toBeNull();
});

it("attaches generated results immediately and uses the updated revision on the next roll", async () => {
    const request = vi
        .fn()
        .mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ rolls: { crew: 2 }, revision: 4 }),
        })
        .mockResolvedValueOnce({
            ok: true,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({ rolls: { objective: 1 }, revision: 5 }),
        });
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <BattleScenario
            {...props}
            save={{
                action: "/connect/",
                csrfToken: "token",
                campaign: "campaign",
                battle: "battle",
                revision: 3,
                printUrl: "/print/",
            }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    await waitFor(() =>
        expect(
            container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
        ).toBe("2"),
    );
    expect(request).toHaveBeenCalledTimes(1);
    const first = request.mock.calls[0][1].body as FormData;
    expect(first.get("generate")).toBe("1");
    expect(first.get("battle")).toBe("battle");
    expect(first.get("revision")).toBe("3");
    expect(
        screen.queryByRole("button", { name: /Save scenario|Discard preview/ }),
    ).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await waitFor(() =>
        expect(
            container.querySelector<HTMLInputElement>('[name="objective"]')
                ?.value,
        ).toBe("1"),
    );
    expect(request).toHaveBeenCalledTimes(2);
    const second = request.mock.calls[1][1].body as FormData;
    expect(second.get("revision")).toBe("4");
    expect(second.has("crew")).toBe(false);
});
it("preserves the saved result when automatic attachment is refused", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValueOnce({
            ok: false,
            headers: new Headers({ "content-type": "application/json" }),
            json: async () => ({
                errors: [
                    "This battle changed. Reload it before saving your changes.",
                ],
            }),
        }),
    );
    const { container } = render(
        <BattleScenario
            {...props}
            rolls={{ crew: "2" }}
            save={{
                action: "/connect/",
                csrfToken: "token",
                campaign: "campaign",
                battle: "battle",
                revision: 3,
                printUrl: "/print/",
            }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate again" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain(
        "This battle changed.",
    );
    expect(
        container.querySelector<HTMLInputElement>('[name="crew"]')?.value,
    ).toBe("2");
    expect(
        container.querySelector<HTMLInputElement>('[name="objective"]')?.value,
    ).toBe("");
});

it("blocks battle submission while generation is pending", async () => {
    let finish!: (value: unknown) => void;
    const request = vi.fn().mockReturnValue(
        new Promise((resolve) => {
            finish = resolve;
        }),
    );
    vi.stubGlobal("fetch", request);
    const { container } = render(
        <form>
            <BattleScenario {...props} />
        </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate scenario" }));
    expect(fireEvent.submit(container.querySelector("form")!)).toBe(false);
    expect(screen.getByLabelText("Crew")).toHaveProperty("disabled", true);
    finish({
        ok: true,
        headers: new Headers({ "content-type": "application/json" }),
        json: async () => ({ rolls: { crew: 2 } }),
    });
    await screen.findByRole("button", { name: "Generate again" });
    expect(fireEvent.submit(container.querySelector("form")!)).toBe(true);
    expect(request).toHaveBeenCalledTimes(1);
});
