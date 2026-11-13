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
test("tags have their own screen with the requested icon choices", () => {
    render(
        <ArbitratorToolkit
            {...base}
            actionKind="tags"
            values={{
                request_key: "tags-1",
                payload: JSON.stringify({
                    target: "gangs",
                    rewards: [
                        { kind: "tag", name: "", icon: "crosshair", amount: 1 },
                    ],
                    recipients_mode: "selected",
                    gangs: [],
                    players: [],
                }),
            }}
        />,
    );
    fireEvent.click(screen.getByRole("radio", { name: "Players" }));
    expect(screen.getByLabelText("Tag name *")).toBeDefined();
    for (const icon of base.icons!)
        expect(screen.getByRole("button", { name: icon })).toBeDefined();
    expect(
        screen.queryByText("Rewards or tags for campaign gangs."),
    ).toBeNull();
});
test("interventions only offer gang recipients and contain no tag type", () => {
    render(<ArbitratorToolkit {...base} />);
    expect(screen.queryByRole("radio", { name: /Players/ })).toBeNull();
    expect(screen.queryByRole("option", { name: "Gang tag" })).toBeNull();
    expect(
        screen.getByText(
            "Inform everyone in the campaign about this intervention.",
        ),
    ).toBeDefined();
});
test("recipients and choice limits are included in the submitted payload", () => {
    const view = render(<ArbitratorToolkit {...base} />);
    fireEvent.click(screen.getByRole("radio", { name: /Offer a choice/ }));
    fireEvent.click(screen.getByRole("button", { name: /Add option/ }));
    fireEvent.change(screen.getByLabelText("Number of rewards to choose"), {
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
    fireEvent.click(screen.getByRole("radio", { name: "60¢" }));
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

test("single choices replace the selected reward instead of selecting two", () => {
    render(
        <ArbitratorToolkit
            {...base}
            actionKind="choose"
            receipt={{
                title: "Offer",
                gang: "Vipers",
                choices: 1,
                rewards: [
                    { kind: "credits", amount: 30, label: "30¢" },
                    { kind: "credits", amount: 60, label: "60¢" },
                ],
                narrative: "Support.",
            }}
            values={{
                request_key: "choice",
                payload: JSON.stringify({ receipt: "r", selected: [] }),
            }}
        />,
    );
    fireEvent.click(screen.getByRole("radio", { name: "30¢" }));
    fireEvent.click(screen.getByRole("radio", { name: "60¢" }));
    expect(
        (screen.getByRole("radio", { name: "30¢" }) as HTMLInputElement)
            .checked,
    ).toBe(false);
    expect(screen.getByText("1 of 1 chosen")).toBeDefined();
    expect(
        screen.getByText("Choose exactly 1 reward. Applied when you confirm."),
    ).toBeDefined();
    expect(
        screen.getByRole("button", { name: "Confirm choice" }),
    ).toBeDefined();
});
test("multiple choices disable unselected rewards at the limit and re-enable them after deselection", () => {
    render(
        <ArbitratorToolkit
            {...base}
            actionKind="choose"
            receipt={{
                title: "Offer",
                gang: "Vipers",
                choices: 2,
                rewards: [
                    { kind: "credits", amount: 30, label: "30¢" },
                    { kind: "credits", amount: 60, label: "60¢" },
                    { kind: "credits", amount: 90, label: "90¢" },
                ],
                narrative: "Support.",
            }}
            values={{
                request_key: "choice",
                payload: JSON.stringify({ receipt: "r", selected: [] }),
            }}
        />,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "30¢" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "60¢" }));
    expect(
        (screen.getByRole("checkbox", { name: "90¢" }) as HTMLInputElement)
            .disabled,
    ).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "30¢" }));
    expect(
        (screen.getByRole("checkbox", { name: "90¢" }) as HTMLInputElement)
            .disabled,
    ).toBe(false);
    fireEvent.click(screen.getByRole("checkbox", { name: "90¢" }));
    expect(screen.getByText("2 of 2 chosen")).toBeDefined();
});
test("profiles can be searched inside the picker and selected without submitting the form", () => {
    const { container } = render(
        <ArbitratorToolkit
            {...base}
            catalogue={[
                {
                    kind: "profile",
                    id: "runner",
                    name: "Ash runner",
                    detail: "Fighter",
                    rating: 50,
                },
                {
                    kind: "profile",
                    id: "crawler",
                    name: "Cargo crawler",
                    detail: "Vehicle",
                    rating: 120,
                },
            ]}
            values={{
                request_key: "search",
                payload: JSON.stringify({
                    title: "Support",
                    rewards: [{ kind: "profile", id: "", amount: 1 }],
                    gangs: ["gang-a"],
                }),
            }}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Select profile 1" }));
    fireEvent.change(screen.getByPlaceholderText("Search profiles"), {
        target: { value: "cargo" },
    });
    expect(screen.queryByRole("menuitem", { name: /Ash runner/ })).toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: /Cargo crawler/ }));
    expect(
        JSON.parse(
            (
                container.querySelector(
                    'input[name="payload"]',
                ) as HTMLInputElement
            ).value,
        ).rewards[0].id,
    ).toBe("crawler");
});
test("immediate alerts and wrap-up reports are independent controls", () => {
    const { container } = render(
        <ArbitratorToolkit
            {...base}
            actionKind="alerts"
            alertEvents={[
                { value: "battle_created", label: "A battle is created" },
            ]}
            values={{
                request_key: "alerts",
                payload: JSON.stringify({
                    events: [],
                    immediate: true,
                    report_enabled: false,
                    report_days: 7,
                }),
            }}
        />,
    );
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Send alerts immediately" }),
    );
    fireEvent.click(
        screen.getByRole("checkbox", { name: "Send a wrap-up report" }),
    );
    fireEvent.change(screen.getByLabelText("Send a report every *"), {
        target: { value: "3" },
    });
    const values = JSON.parse(
        (container.querySelector('input[name="payload"]') as HTMLInputElement)
            .value,
    );
    expect(values.immediate).toBe(false);
    expect(values.report_enabled).toBe(true);
    expect(values.report_days).toBe(3);
});

test("choice counts reject negative, zero and fractional values", () => {
    const view = render(<ArbitratorToolkit {...base} />);
    fireEvent.click(screen.getByRole("radio", { name: /Offer a choice/ }));
    fireEvent.click(screen.getByRole("button", { name: /Add option/ }));
    const input = screen.getByLabelText("Number of rewards to choose");
    for (const value of ["-1", "0", "1.5"]) {
        fireEvent.change(input, { target: { value } });
        expect((input as HTMLInputElement).value).toBe("1");
    }
    expect(view.container.querySelector("fieldset")?.className).toBe(
        "space-y-8",
    );
    expect(screen.queryByRole("heading", { name: "Intervention" })).toBeNull();
    expect(
        screen.queryByText("Included with the rewards and in notifications."),
    ).toBeNull();
});

test("a tag assignment has one tag and no numbered header or add button", () => {
    render(
        <ArbitratorToolkit
            {...base}
            actionKind="tags"
            values={{
                request_key: "tag-one",
                payload: JSON.stringify({
                    rewards: [
                        {
                            kind: "tag",
                            amount: 1,
                            name: "Painter",
                            icon: "paintbrush",
                        },
                    ],
                    target: "gangs",
                }),
            }}
        />,
    );
    expect(screen.getAllByLabelText("Tag name *")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Add tag" })).toBeNull();
    expect(screen.queryByText("Tag 1")).toBeNull();
});

test("interventions require rewards, application mode and recipients before sending", () => {
    render(
        <ArbitratorToolkit
            {...base}
            values={{
                request_key: "required",
                payload: JSON.stringify({
                    title: "Supply",
                    mode: "",
                    recipients_mode: "",
                    gangs: [],
                    rewards: [{ kind: "", amount: 1 }],
                }),
            }}
        />,
    );
    const send = screen.getByRole("button", { name: "Send intervention" });
    expect(send).toHaveProperty("disabled", true);
    expect(screen.getByText("Select a reward type.").className).toContain(
        "text-red",
    );
    expect(screen.getByRole("note").textContent).toContain(
        "cannot be undone once sent",
    );
    fireEvent.click(screen.getByRole("radio", { name: /All rewards/ }));
    fireEvent.change(screen.getByLabelText("Type"), {
        target: { value: "credits" },
    });
    expect(send).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("radio", { name: "All gangs" }));
    expect(send).toHaveProperty("disabled", false);
});

test("reward picker names follow the selected type", () => {
    render(<ArbitratorToolkit {...base} />);
    for (const [kind, label, button] of [
        ["resource", "Resource type", "Select resource type 1"],
        ["weapon", "Weapon", "Select weapon 1"],
        ["equipment", "Equipment", "Select equipment 1"],
    ]) {
        fireEvent.change(screen.getByLabelText("Type"), {
            target: { value: kind },
        });
        expect(screen.getByLabelText(label)).toBeDefined();
        expect(screen.getByRole("button", { name: button })).toBeDefined();
        expect(
            screen.getByRole("button", { name: "Send intervention" }),
        ).toHaveProperty("disabled", true);
    }
});

test("a conflicting communication edit freezes its draft until review", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
            status: 409,
            headers: new Headers({ "Content-Type": "application/json" }),
            json: async () => ({
                code: "revision_conflict",
                errors: { __all__: ["This content has changed."] },
            }),
        }),
    );
    render(
        <ArbitratorToolkit
            {...base}
            actionKind="edit_communication"
            reviewHref="/edit-message/"
            recipientNames={["Ada"]}
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save message" }));
    await screen.findByRole("button", { name: "Review current version" });
    expect(screen.getByLabelText("Title *").closest("fieldset")).toHaveProperty(
        "disabled",
        true,
    );
});

test("tag tables pool recipients and keep gang and player tags separate", () => {
    render(
        <ArbitratorToolkit
            {...base}
            screen="home"
            tab="tags"
            tags={[
                {
                    id: "a",
                    assignmentKey: "convoy",
                    name: "Convoy guides",
                    icon: "snail",
                    info: "Route advice.",
                    target: "gangs",
                    recipient: "Glass Vipers",
                    editHref: "/edit/",
                    removeHref: "/remove/a/",
                },
                {
                    id: "b",
                    assignmentKey: "convoy",
                    name: "Convoy guides",
                    icon: "snail",
                    info: "Route advice.",
                    target: "gangs",
                    recipient: "Iron Lanterns",
                    editHref: "/edit/",
                    removeHref: "/remove/b/",
                },
                {
                    id: "c",
                    assignmentKey: "painter",
                    name: "Painter",
                    icon: "paintbrush",
                    info: "Painting advice.",
                    target: "players",
                    recipient: "Ada",
                    editHref: "/edit/painter/",
                    removeHref: "/remove/c/",
                },
            ]}
        />,
    );
    const gangs = screen.getByRole("table", { name: "Gang tags" });
    const players = screen.getByRole("table", { name: "Player tags" });
    expect(gangs.querySelectorAll("tbody tr")).toHaveLength(1);
    expect(gangs.textContent).toContain("Glass Vipers");
    expect(gangs.textContent).toContain("Iron Lanterns");
    expect(gangs.textContent).not.toContain("Ada");
    expect(players.textContent).toContain("Ada");
    expect(
        screen
            .getByRole("link", {
                name: "Remove Convoy guides from Iron Lanterns",
            })
            .getAttribute("href"),
    ).toBe("/remove/b/");
});
