import {
    fireEvent,
    render,
    screen,
    waitFor,
    cleanup,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ArbitratorToolkit, type ToolkitProps } from "./ArbitratorToolkit";
const base: ToolkitProps = {
    campaignName: "Ash Road",
    campaignHref: "/campaign/",
    toolkitHref: "/toolkit/",
    isArbitrator: true,
    screen: "form",
    actionKind: "intervention",
    icons: ["crosshair", "key-round", "paintbrush", "printer", "library-big"],
    catalogue: [],
    gangs: [{ id: "gang-a", name: "Glass Vipers", owner: "Ada" }],
    players: [{ id: "player-a", name: "Ada", owner: "Player" }],
    values: {
        request_key: "request-1",
        payload: JSON.stringify({
            title: "Supply drop",
            narrative: "A guild delivery.",
            mode: "bundle",
            choices: 1,
            rewards: [{ kind: "credits", amount: 30 }],
            recipients_mode: "selected",
            gangs: ["gang-a"],
            inform_all: false,
        }),
    },
    errors: {},
    csrfToken: "fresh-token",
    commandHref: "/command/",
    recoveryKey: "toolkit-test",
};
beforeEach(() => {
    sessionStorage.clear();
});
afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
});
test("player targets offer tags and retain the requested icon choices", () => {
    render(<ArbitratorToolkit {...base} />);
    fireEvent.click(
        screen.getByRole("radio", { name: /Players.*Informational/ }),
    );
    expect(screen.getByLabelText("Tag name *")).toBeDefined();
    for (const icon of base.icons!)
        expect(screen.getByRole("button", { name: icon })).toBeDefined();
    expect(screen.getByRole("option", { name: "Player tag" })).toBeDefined();
    expect(screen.queryByRole("option", { name: "Credits" })).toBeNull();
});
test("recipients and choice limits are included in the submitted payload", () => {
    const view = render(<ArbitratorToolkit {...base} />);
    fireEvent.click(screen.getByRole("radio", { name: /Offer a choice/ }));
    fireEvent.click(screen.getByRole("button", { name: /Add option/ }));
    fireEvent.change(screen.getByLabelText("Number of rewards to choose *"), {
        target: { value: "2" },
    });
    const payload = JSON.parse(
        (
            view.container.querySelector(
                'input[name="payload"]',
            ) as HTMLInputElement
        ).value,
    );
    expect(payload.mode).toBe("choice");
    expect(payload.choices).toBe(2);
    expect(payload.rewards).toHaveLength(2);
    expect(payload.gangs).toEqual(["gang-a"]);
});
test("failed submissions preserve the exact command for a safe retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    render(<ArbitratorToolkit {...base} />);
    fireEvent.click(screen.getByRole("button", { name: "Send intervention" }));
    await waitFor(() =>
        expect(
            screen.getByRole("button", { name: "Retry save" }),
        ).toBeDefined(),
    );
    expect(sessionStorage.getItem("toolkit-test")).toContain(
        "request_key=request-1",
    );
    expect(screen.getByLabelText("Title *").closest("fieldset")?.disabled).toBe(
        true,
    );
});
test("recipient choices show the exact required count and preserve selections", () => {
    const props: ToolkitProps = {
        ...base,
        actionKind: "choose",
        receipt: {
            title: "The guild's offer",
            gang: "Glass Vipers",
            choices: 1,
            rewards: [
                { kind: "credits", amount: 30, label: "30¢" },
                { kind: "credits", amount: 60, label: "60¢" },
            ],
            narrative: "Choose your support.",
        },
        values: {
            request_key: "choice-1",
            payload: JSON.stringify({ receipt: "receipt-a", selected: [] }),
        },
    };
    const view = render(<ArbitratorToolkit {...props} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "60¢" }));
    expect(screen.getByText("1 of 1 chosen")).toBeDefined();
    expect(
        JSON.parse(
            (
                view.container.querySelector(
                    'input[name="payload"]',
                ) as HTMLInputElement
            ).value,
        ).selected,
    ).toEqual([1]);
});
