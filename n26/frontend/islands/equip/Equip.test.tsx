import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Equip } from "./Equip";
import { page, response, sell } from "./fixtures";
import type { EquipQuestion } from "./types";
import { model } from "../../test/modelCard";

beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState({}, "", "/equip/?list=house");
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
    };
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
    };
});
afterEach(() => vi.unstubAllGlobals());
const completed = (requestKey: string) =>
    response({
        requestKey,
        outcome: "completed",
        confirmation: null,
        page: {
            ...page,
            figures: {
                ...page.figures,
                items: [{ ...page.figures.items[0], value: "55¢" }],
            },
            messages: [
                {
                    tone: "success",
                    text: "Bought Harness for the stash — 45¢.",
                },
            ],
        },
    });

const completeFetch = (_href: unknown, options: { body: URLSearchParams }) =>
    Promise.resolve(completed(options.body.get("request_key")!));

test("fighter categories start collapsed while unnamed equipment remains reachable", async () => {
    render(<Equip {...page} model={model} />);
    expect(screen.queryByRole("button", { name: "Buy Harness" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(screen.getByRole("button", { name: "Buy Harness" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Manage visit" })).toBeTruthy();
    expect(
        screen.getByText("The visit is open with", { exact: false })
            .textContent,
    ).toContain("9 TP");
    expect(
        screen
            .getByRole("link", { name: "Equip" })
            .getAttribute("aria-current"),
    ).toBe("page");
    expect(document.querySelector("form form")).toBeNull();
});

test("in-place counter changes use fresh keys and preserve an edited purchase through refresh", async () => {
    const changed = {
        ...model,
        card: {
            ...model.card,
            details: [
                {
                    ...model.card.details[0],
                    parts: [{ ...model.card.details[0].parts[0], value: 4 }],
                },
                model.card.details[1],
            ],
        },
    };
    const fetcher = vi.fn().mockImplementation((_href, options) =>
        Promise.resolve(
            response({
                requestKey: options.body.get("request_key"),
                outcome: "completed",
                confirmation: null,
                page: { ...page, model: changed },
            }),
        ),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} model={model} />);
    await userEvent.click(screen.getByRole("button", { name: "Expand all" }));
    await userEvent.click(screen.getByRole("radio", { name: /Armed/ }));
    await userEvent.click(
        screen.getByRole("button", { name: "Add one to Ammo" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fetcher).toHaveBeenCalledTimes(1);
    const first = new URLSearchParams(fetcher.mock.calls[0][1].body);
    expect(Object.fromEntries(first)).toMatchObject({
        action: "tally",
        assignment: "ammo-counter",
        change: "1",
        personal_activity: "hire-action",
    });
    expect(
        (screen.getByRole("radio", { name: /Armed/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    await userEvent.click(
        screen.getByRole("button", { name: "Add one to Ammo" }),
    );
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(fetcher.mock.calls[1][1].body.get("request_key")).not.toBe(
        first.get("request_key"),
    );
});

test("an uncertain counter step survives reload with its original identity and fresh CSRF", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("lost response"));
    vi.stubGlobal("fetch", fetcher);
    const first = render(<Equip {...page} model={model} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Add one to Ammo" }),
    );
    await screen.findByRole("button", { name: "Retry change" });
    const original = new URLSearchParams(fetcher.mock.calls[0][1].body);
    expect(
        (
            screen.getByRole("button", {
                name: "Dismiss Skills",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    first.unmount();
    fetcher.mockImplementation((_href, options) =>
        Promise.resolve(
            response({
                requestKey: options.body.get("request_key"),
                outcome: "completed",
                confirmation: null,
                page: { ...page, model },
            }),
        ),
    );
    render(
        <Equip
            {...page}
            model={model}
            csrfToken="rotated"
            requestKey="new-page"
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry change" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    original.set("csrfmiddlewaretoken", "rotated");
    expect([...fetcher.mock.calls[1][1].body]).toEqual([...original]);
    await waitFor(() =>
        expect(sessionStorage.getItem(page.recoveryKey)).toBeNull(),
    );
});

test("rapid counter clicks queue distinct commands and uncertainty stops unsent steps", async () => {
    let rejectFirst!: (reason: unknown) => void;
    const fetcher = vi.fn().mockImplementation(
        () =>
            new Promise((_resolve, reject) => {
                rejectFirst = reject;
            }),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} model={model} />);
    const add = screen.getByRole("button", { name: "Add one to Ammo" });
    await userEvent.click(add);
    await userEvent.click(add);
    await userEvent.click(add);
    const progress = screen.getByRole("status", { name: "Saving Ammo" });
    expect(add.nextElementSibling?.contains(progress)).toBe(true);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).toBeNull();
    await act(async () => rejectFirst(new TypeError("lost")));
    await screen.findByRole("button", { name: "Retry change" });
    expect(
        screen.getByText(/2 queued counter changes were not sent/),
    ).toBeTruthy();
    expect(fetcher).toHaveBeenCalledTimes(1);
    fetcher.mockImplementation((_href, options) =>
        Promise.resolve(
            response({
                requestKey: options.body.get("request_key"),
                outcome: "completed",
                confirmation: null,
                page: { ...page, model },
            }),
        ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry change" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
        screen.getByText(/2 queued counter changes were not sent/),
    ).toBeTruthy();
    expect(fetcher).toHaveBeenCalledTimes(2);
});

test("each queued counter step drains only after the previous one is confirmed", async () => {
    const resolvers: Array<(value: Response) => void> = [];
    const fetcher = vi
        .fn()
        .mockImplementation(
            () => new Promise<Response>((resolve) => resolvers.push(resolve)),
        );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} model={model} />);
    const add = screen.getByRole("button", { name: "Add one to Ammo" });
    await userEvent.click(add);
    await userEvent.click(add);
    await userEvent.click(add);
    for (let index = 0; index < 3; index++) {
        await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(index + 1));
        const body = fetcher.mock.calls[index][1].body as URLSearchParams;
        await act(async () =>
            resolvers[index](
                response({
                    requestKey: body.get("request_key"),
                    outcome: "completed",
                    confirmation: null,
                    page: { ...page, model },
                }),
            ),
        );
    }
    expect(
        new Set(
            fetcher.mock.calls.map((call) => call[1].body.get("request_key")),
        ).size,
    ).toBe(3);
    await waitFor(() =>
        expect(screen.queryByText("Saving counter change…")).toBeNull(),
    );
});

test("initial catalogue needs no request and Enter in search cannot buy", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.type(screen.getByRole("searchbox"), "Harness{Enter}");
    expect(screen.getByRole("button", { name: "Buy Harness" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
});

test("commands preserve the dismissed-choice URL flag through an authoritative refresh", async () => {
    const marked = {
        ...page,
        action: "/equip/?list=house&dismissed=show",
        listingHref: "/equip/?list=house&dismissed=show",
    };
    const fetcher = vi.fn().mockImplementation((_href, options) =>
        Promise.resolve(
            response({
                requestKey: options.body.get("request_key"),
                outcome: "completed",
                confirmation: null,
                page: marked,
            }),
        ),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...marked} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher.mock.calls[0][1].body.get("dismissed")).toBe("show");
    await waitFor(() =>
        expect(window.location.search).toContain("dismissed=show"),
    );
});

test("a closed Trading Post has one visit action and an open visit has none", () => {
    const first = render(<Equip {...page} postIsShut />);
    expect(screen.getByText("Not tracking trade points")).toBeTruthy();
    expect(
        screen.getByRole("link", { name: "Set up Trading Post visit →" }),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Track TP spend/ })).toBeNull();
    first.unmount();
    render(<Equip {...page} visitingTradingPost />);
    expect(screen.queryByText("Not tracking trade points")).toBeNull();
    expect(
        screen.queryByRole("link", {
            name: /Trading Post visit|Track TP spend/,
        }),
    ).toBeNull();
});

test("founding blocks a new visit with a readable reason beside the disabled control", () => {
    render(<Equip {...page} postIsShut foundingBlocksVisit />);
    const button = screen.getByRole("button", {
        name: "Set up Trading Post visit →",
    }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(
        document.getElementById(button.getAttribute("aria-describedby")!)
            ?.textContent,
    ).toContain("Complete Spend founding TP first.");
    expect(
        screen.queryByRole("link", { name: "Set up Trading Post visit →" }),
    ).toBeNull();
});

test("detaching an accessory posts held and offers no model or weapon destination", async () => {
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(
        <Equip
            {...page}
            model={model}
            dialog={{
                ...sell,
                kind: "detach",
                title: "Take Sight off Autogun?",
                lead: "The model keeps it. Its rating does not change.",
                submit_label: "Detach",
            }}
        />,
    );
    expect(screen.queryByRole("combobox")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Detach" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher.mock.calls[0][1].body.get("to")).toBe("held");
});

test("posts full displayed payment and stable options, then keeps filters after authoritative refresh", async () => {
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.type(screen.getByRole("searchbox"), "Harness");
    await userEvent.click(screen.getByRole("radio", { name: /Armed/ }));
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await waitFor(() =>
        expect(
            screen.getByText("Bought Harness for the stash — 45¢."),
        ).toBeTruthy(),
    );
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(Object.fromEntries(body)).toMatchObject({
        action: "buy",
        thing: "harness",
        paid: "45",
        selection: '["armed"]',
        parts: "[]",
        rate: "",
        csrfmiddlewaretoken: "fresh-csrf",
    });
    expect(screen.getByRole("searchbox").getAttribute("value")).toBe("Harness");
    expect(screen.getByRole("link", { name: "55¢" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("a lost response retains the exact command through reload with fresh credentials", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("offline"));
    vi.stubGlobal("fetch", fetcher);
    const first = render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("radio", { name: /Armed/ }));
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await screen.findByRole("button", { name: "Retry change" });
    const original = new URLSearchParams(fetcher.mock.calls[0][1].body);
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    const warning = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(warning);
    expect(warning.defaultPrevented).toBe(true);
    first.unmount();
    fetcher.mockImplementation(completeFetch);
    render(
        <Equip
            {...page}
            csrfToken="rotated-csrf"
            requestKey="different-page-key"
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry change" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    const retry = fetcher.mock.calls[1][1].body as URLSearchParams;
    original.set("csrfmiddlewaretoken", "rotated-csrf");
    expect([...retry]).toEqual([...original]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(sessionStorage.getItem(page.recoveryKey)).toBeNull();
});

test("a refused retry cannot unlock an earlier unknown purchase", async () => {
    const fetcher = vi
        .fn()
        .mockRejectedValueOnce(new TypeError("lost"))
        .mockResolvedValueOnce(
            response(
                {
                    errors: {
                        __all__: [
                            "This form was already used for a different equipment change.",
                        ],
                    },
                },
                409,
            ),
        );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry change" }),
    );
    await screen.findByText(
        "This form was already used for a different equipment change.",
    );
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    expect(sessionStorage.getItem(page.recoveryKey)).not.toBeNull();
});

test("pending commands prevent duplicate submits and dismissal", async () => {
    let finish!: (response: Response) => void;
    const fetcher = vi.fn().mockImplementation(
        () =>
            new Promise((resolve) => {
                finish = resolve;
            }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { container } = render(<Equip {...page} />);
    const buy = screen.getByRole("button", { name: "Buy Harness" });
    await userEvent.click(buy);
    expect(buy.getAttribute("data-busy")).toBe("on");
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.submit(container.querySelector("[data-equip-command]")!);
    fireEvent.click(buy);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect((buy as HTMLButtonElement).disabled).toBe(true);
    await act(async () =>
        finish(response({ errors: { __all__: ["Not enough credits."] } }, 422)),
    );
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Buy" });
    await userEvent.click(submit);
    expect(submit.getAttribute("data-busy")).toBe("on");
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(
        (
            within(dialog).getByRole("button", {
                name: "Cancel",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    await act(async () =>
        finish(response({ errors: { __all__: ["Not enough credits."] } }, 422)),
    );
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
    ).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("an uncertain retry keeps its warning and dialog while its button shows progress", async () => {
    let finish!: () => void;
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockRejectedValueOnce(new TypeError("Lost response"))
            .mockImplementationOnce(
                (_href, options) =>
                    new Promise<Response>((resolve) => {
                        finish = () =>
                            resolve(completed(options.body.get("request_key")));
                    }),
            ),
    );
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    const dialog = await screen.findByRole("dialog");
    const warning = screen.getByText(/The save may have completed/);
    const retry = within(dialog).getByRole("button", { name: "Retry change" });
    await userEvent.click(retry);
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(warning.isConnected).toBe(true);
    expect(retry.getAttribute("data-busy")).toBe("on");
    await act(async () => finish());
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("a confirmation uses its own key and an explicitly unchecked rating value", async () => {
    let question!: EquipQuestion;
    const fetcher = vi
        .fn()
        .mockImplementationOnce((_href, options) => {
            const body = options.body as URLSearchParams;
            question = {
                title: "Choose the rating",
                lead: "Harness — 0¢.",
                heading: "You are paying less than the full price",
                body: "Choose the rating.",
                confirm_label: "Buy Harness",
                confirm_field: "confirmed",
                confirm_value: "1",
                carry: [...body]
                    .filter(
                        ([name]) =>
                            name !== "csrfmiddlewaretoken" &&
                            name !== "request_key" &&
                            name !== "rate",
                    )
                    .concat([["request_key", "confirmation-key"]]),
                facts: [],
                aside: null,
                checkbox: {
                    name: "rate",
                    value: "paid",
                    label: "Match rating to price",
                    description:
                        "Keep the full rating unless your group agrees otherwise.",
                    checked: false,
                },
            };
            return Promise.resolve(
                response({
                    requestKey: body.get("request_key"),
                    outcome: "confirmation",
                    confirmation: question,
                    page,
                }),
            );
        })
        .mockImplementationOnce(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    const paid = screen.getByRole("spinbutton", {
        name: "Base price for Harness",
    });
    await userEvent.clear(paid);
    await userEvent.type(paid, "0");
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    const dialog = await screen.findByRole("dialog", {
        name: "Choose the rating",
    });
    expect(
        (
            within(dialog).getByRole("checkbox", {
                name: "Match rating to price",
            }) as HTMLInputElement
        ).checked,
    ).toBe(false);
    await userEvent.click(
        within(dialog).getByRole("button", { name: "Buy Harness" }),
    );
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(Object.fromEntries(fetcher.mock.calls[1][1].body)).toMatchObject({
        paid: "0",
        request_key: "confirmation-key",
        confirmed: "1",
        rate: "",
    });
});

test("cancelling a card possession panel restores focus to its menu trigger", async () => {
    const equipped = {
        ...model,
        card: {
            ...model.card,
            weapons: [
                {
                    name: "Autogun",
                    key: "gun-copy",
                    stats: [],
                    traits: [],
                    profiles: [],
                    accessories: [],
                    choices: [],
                    actions: [
                        {
                            label: "Refund",
                            target: "/equip/?list=house&refund=gun-copy",
                            tone: "danger",
                        },
                    ],
                },
            ],
        },
    };
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            response({
                page: {
                    ...page,
                    model: equipped,
                    dialog: {
                        ...sell,
                        kind: "refund",
                        title: "Refund Autogun?",
                        submit_label: "Refund",
                    },
                },
            }),
        ),
    );
    render(<Equip {...page} model={equipped} />);
    const trigger = screen.getByRole("button", { name: "More for Autogun" });
    await userEvent.click(trigger);
    await userEvent.click(screen.getByRole("menuitem", { name: "Refund" }));
    await screen.findByRole("dialog", { name: "Refund Autogun?" });
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(trigger));
});

test("fighter equipment can move directly to the stash when another model is offered", async () => {
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(
        <Equip
            {...page}
            model={model}
            dialog={{
                ...sell,
                kind: "reassign",
                title: "Move Autogun",
                submit_label: "Move",
                models: [{ key: "rook", name: "Rook" }],
            }}
        />,
    );
    expect(
        (screen.getByRole("combobox", { name: "To" }) as HTMLSelectElement)
            .value,
    ).toBe("rook");
    await userEvent.click(screen.getByRole("button", { name: "To the stash" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(Object.fromEntries(fetcher.mock.calls[0][1].body)).toMatchObject({
        action: "reassign",
        to: "stash",
        assignment: "gun-copy",
    });
});

test("the ordinary Move action still posts the selected model", async () => {
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(
        <Equip
            {...page}
            model={model}
            dialog={{
                ...sell,
                kind: "reassign",
                title: "Move Autogun",
                submit_label: "Move",
                models: [
                    { key: "rook", name: "Rook" },
                    { key: "nell", name: "Nell" },
                ],
            }}
        />,
    );
    await userEvent.selectOptions(
        screen.getByRole("combobox", { name: "To" }),
        "nell",
    );
    await userEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(Object.fromEntries(fetcher.mock.calls[0][1].body)).toMatchObject({
        to: "model",
        miniature: "nell",
    });
});

test("a lost stash move restores the clicked destination rather than a fresh model pick", async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError("lost"));
    vi.stubGlobal("fetch", fetcher);
    const dialog = {
        ...sell,
        kind: "reassign",
        title: "Move Autogun",
        submit_label: "Move",
        models: [{ key: "rook", name: "Rook" }],
    };
    const first = render(<Equip {...page} model={model} dialog={dialog} />);
    await userEvent.click(screen.getByRole("button", { name: "To the stash" }));
    await screen.findByRole("button", { name: "Retry change" });
    const original = new URLSearchParams(fetcher.mock.calls[0][1].body);
    expect(original.get("to")).toBe("stash");
    first.unmount();
    fetcher.mockImplementation(completeFetch);
    render(
        <Equip
            {...page}
            model={model}
            requestKey="fresh-page"
            csrfToken="fresh-after-login"
            dialog={{ ...dialog, models: [{ key: "nell", name: "Nell" }] }}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Retry change" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    original.set("csrfmiddlewaretoken", "fresh-after-login");
    expect([...fetcher.mock.calls[1][1].body]).toEqual([...original]);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("owned-panel navigation carries current section and expanded entry without a page reload", async () => {
    const fetcher = vi.fn().mockResolvedValue(
        response({
            page: {
                ...page,
                dialog: sell,
                owned: "gun",
                listingHref: "/equip/?list=house&owned=gun",
            },
        }),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(
        screen.getByRole("button", { name: /Autogun in stash/ }),
    );
    await userEvent.click(screen.getByRole("link", { name: "Sell" }));
    await screen.findByRole("dialog", { name: "Sell Autogun?" });
    const url = new URL(String(fetcher.mock.calls[0][0]));
    expect(url.searchParams.get("owned")).toBe("gun");
    expect(url.searchParams.get("sell")).toBe("gun-copy");
    expect(window.location.search).toContain("owned=gun");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(window.location.search).toBe("?list=house&owned=gun");
    expect(
        screen
            .getByRole("button", { name: /Autogun in stash/ })
            .getAttribute("aria-expanded"),
    ).toBe("true");
});

test("a delayed panel read keeps progress in its initiating control", async () => {
    let finish!: (response: Response) => void;
    const fetcher = vi.fn().mockImplementation(
        () =>
            new Promise<Response>((resolve) => {
                finish = resolve;
            }),
    );
    vi.stubGlobal("fetch", fetcher);
    const { container } = render(<Equip {...page} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Show Autogun in stash (1)" }),
    );
    const link = screen.getByRole("link", { name: "Sell" });
    await userEvent.click(link);
    expect(link.getAttribute("aria-busy")).toBe("true");
    expect([...container.querySelectorAll('[data-busy="on"]')]).toEqual([link]);
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(link);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await act(async () =>
        finish(response({ page: { ...page, dialog: sell } })),
    );
    await screen.findByRole("dialog", { name: "Sell Autogun?" });
    expect(link.getAttribute("data-busy")).toBe("off");
});

test("a failed panel read has plain feedback and can be retried", async () => {
    const fetcher = vi
        .fn()
        .mockRejectedValueOnce(new TypeError("Failed to fetch"))
        .mockResolvedValueOnce(response({ page: { ...page, dialog: sell } }));
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Show Autogun in stash (1)" }),
    );
    await userEvent.click(screen.getByRole("link", { name: "Sell" }));
    await screen.findByText(
        "The equipment details could not be loaded. Try again.",
    );
    expect(screen.queryByText("Failed to fetch")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("dialog", { name: "Sell Autogun?" });
});

test("an owned-only stash has no search and keeps its management actions", async () => {
    render(
        <Equip
            {...page}
            scope="stash"
            scopeLabel="In stash"
            owned="gun"
            sections={[
                {
                    name: "Gear",
                    categories: [
                        {
                            name: "",
                            entries: [
                                {
                                    ...page.sections[0].categories[0]
                                        .entries[1],
                                    purchase: null,
                                },
                            ],
                        },
                    ],
                },
            ]}
        />,
    );
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.getByRole("link", { name: "Sell" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Buy Autogun" })).toBeNull();
});

test("an acknowledgement for another request cannot clear an unresolved purchase", async () => {
    const fetcher = vi.fn().mockResolvedValue(completed("another-request"));
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await screen.findByRole("button", { name: "Retry change" });
    expect(sessionStorage.getItem(page.recoveryKey)).not.toBeNull();
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
});

test("a broken confirmation cannot replace the retained purchase with a new command", async () => {
    const fetcher = vi.fn().mockImplementation((_href, options) =>
        response({
            requestKey: options.body.get("request_key"),
            outcome: "confirmation",
            page,
            confirmation: {
                title: "Choose the rating",
                lead: "",
                heading: "",
                body: "",
                confirm_label: "Buy",
                confirm_field: "confirmed",
                confirm_value: "1",
                carry: [["request_key", "new-key"]],
                facts: [],
                aside: null,
                checkbox: null,
            },
        }),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await screen.findByRole("button", { name: "Retry change" });
    const stored = new URLSearchParams(
        sessionStorage.getItem(page.recoveryKey)!,
    );
    expect(stored.get("thing")).toBe("harness");
    expect(stored.get("request_key")).toBe(
        fetcher.mock.calls[0][1].body.get("request_key"),
    );
});

for (const rejected of [false, true]) {
    test(`${rejected ? "a rejected" : "an uncertain"} earlier action never uses a different item's confirmation`, async () => {
        const { blankValues } = await import("./types");
        const retained = {
            ...blankValues(page),
            action: "sell",
            assignment: "old-copy",
            display_name: "Old autogun",
            display_details: JSON.stringify(["Half of its 35¢ rating — 18¢."]),
            request_key: "earlier-key",
        };
        const stored = new URLSearchParams(retained);
        if (rejected) stored.set("__workflow_rejected", "1");
        sessionStorage.setItem(page.recoveryKey, stored.toString());
        const other = {
            ...sell,
            assignment: "new-copy",
            name: "New sword",
            title: "Sell New sword?",
            lead: "New sword sale details.",
        };
        const fetcher = vi.fn().mockImplementation(completeFetch);
        vi.stubGlobal("fetch", fetcher);
        render(<Equip {...page} dialog={other} />);
        const dialog = screen.getByRole("dialog");
        expect(dialog.textContent).toContain("Old autogun");
        expect(dialog.textContent).toContain("18¢");
        expect(dialog.textContent).not.toContain("New sword");
        expect(
            (
                within(dialog).getByRole("button", {
                    name: "Cancel",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(!rejected);
        await userEvent.click(
            within(dialog).getByRole("button", {
                name: rejected ? "Retry earlier change" : "Retry change",
            }),
        );
        await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
        expect(Object.fromEntries(fetcher.mock.calls[0][1].body)).toMatchObject(
            {
                action: "sell",
                assignment: "old-copy",
                request_key: "earlier-key",
            },
        );
    });
}

test("new presentation metadata does not discard an older retained command", async () => {
    const { blankValues } = await import("./types");
    const retained = new URLSearchParams({
        ...blankValues(page),
        action: "buy",
        thing: "harness",
        display_name: "Harness",
        paid: "30",
        request_key: "older-key",
    });
    retained.delete("display_details");
    sessionStorage.setItem(page.recoveryKey, retained.toString());
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Retry change" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(body.get("request_key")).toBe("older-key");
    expect(body.has("display_details")).toBe(false);
});

test("different owned entries can remain expanded while the URL records the latest one", async () => {
    const another = {
        ...page.sections[0].categories[0].entries[1],
        key: "second-gun",
        name: "Second gun",
    };
    render(
        <Equip
            {...page}
            sections={[
                {
                    name: "Gear",
                    categories: [
                        {
                            name: "Equipment",
                            entries: [
                                page.sections[0].categories[0].entries[1],
                                another,
                            ],
                        },
                    ],
                },
            ]}
        />,
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Show Autogun in stash (1)" }),
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Show Second gun in stash (1)" }),
    );
    expect(
        screen
            .getByRole("button", { name: "Hide Autogun in stash (1)" })
            .getAttribute("aria-expanded"),
    ).toBe("true");
    expect(
        screen
            .getByRole("button", { name: "Hide Second gun in stash (1)" })
            .getAttribute("aria-expanded"),
    ).toBe("true");
    expect(new URLSearchParams(window.location.search).get("owned")).toBe(
        "second-gun",
    );
});

test("complete row drafts survive filtering and section switches", async () => {
    const fetcher = vi.fn().mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(
        <Equip
            {...page}
            categories={[...page.categories, "Other"]}
            categoryOptions={[...page.categoryOptions, "Other"]}
            sections={[
                ...page.sections,
                {
                    name: "Other",
                    categories: [
                        {
                            name: "Other",
                            entries: [
                                {
                                    ...page.sections[0].categories[0]
                                        .entries[0],
                                    key: "other",
                                    name: "Other",
                                },
                            ],
                        },
                    ],
                },
            ]}
        />,
    );
    await userEvent.click(screen.getByRole("radio", { name: /Armed/ }));
    await userEvent.clear(
        screen.getByRole("spinbutton", { name: "Base price for Harness" }),
    );
    await userEvent.type(
        screen.getByRole("spinbutton", { name: "Base price for Harness" }),
        "11",
    );
    await userEvent.click(
        screen.getByRole("button", { name: "Show Autogun in stash (1)" }),
    );
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Warp rounds" }),
    );
    await userEvent.clear(
        screen.getByRole("spinbutton", { name: "Price for Warp rounds" }),
    );
    await userEvent.type(
        screen.getByRole("spinbutton", { name: "Price for Warp rounds" }),
        "4",
    );
    await userEvent.type(screen.getByRole("searchbox"), "Nothing here");
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.click(screen.getAllByRole("tab", { name: /Other\s*1/ })[0]);
    await userEvent.click(screen.getAllByRole("tab", { name: /Gear\s*2/ })[0]);
    expect(
        (screen.getByRole("radio", { name: /Armed/ }) as HTMLInputElement)
            .checked,
    ).toBe(true);
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Base price for Harness",
            }) as HTMLInputElement
        ).value,
    ).toBe("11");
    expect(
        (
            screen.getByRole("checkbox", {
                name: "Warp rounds",
            }) as HTMLInputElement
        ).checked,
    ).toBe(true);
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Price for Warp rounds",
            }) as HTMLInputElement
        ).value,
    ).toBe("4");
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
    expect(fetcher.mock.calls[0][1].body.get("paid")).toBe("26");
});

test("a selected profile keeps the same displayed and posted payment after quote refresh", async () => {
    const changed = {
        ...page,
        dialog: sell,
        sections: page.sections.map((section) => ({
            ...section,
            categories: section.categories.map((category) => ({
                ...category,
                entries: category.entries.map((entry) => ({
                    ...entry,
                    purchase: entry.purchase
                        ? {
                              ...entry.purchase,
                              parts: entry.purchase.parts.map((part) => ({
                                  ...part,
                                  price: 20,
                              })),
                          }
                        : null,
                })),
            })),
        })),
    };
    const fetcher = vi
        .fn()
        .mockResolvedValueOnce(response({ page: changed }))
        .mockImplementation(completeFetch);
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(
        screen.getByRole("button", { name: "Show Autogun in stash (1)" }),
    );
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Warp rounds" }),
    );
    await userEvent.click(screen.getByRole("link", { name: "Sell" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Cancel" }),
    );
    expect(
        (
            screen.getByRole("spinbutton", {
                name: "Price for Warp rounds",
            }) as HTMLInputElement
        ).value,
    ).toBe("10");
    await userEvent.click(screen.getByRole("button", { name: "Buy Autogun" }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetcher.mock.calls[1][1].body.get("parts"))).toEqual([
        { key: "warp", paid: "10" },
    ]);
});

test("a later overspend question preserves the chosen match-payment rating", async () => {
    let calls = 0;
    const fetcher = vi.fn().mockImplementation((_href, options) => {
        const body = options.body as URLSearchParams;
        calls++;
        if (calls === 3)
            return Promise.resolve(completed(body.get("request_key")!));
        return Promise.resolve(
            response({
                requestKey: body.get("request_key"),
                outcome: "confirmation",
                page,
                confirmation: {
                    title:
                        calls === 1
                            ? "Choose rating"
                            : "Not enough trade points",
                    lead: "Harness",
                    heading: "Review this purchase",
                    body: "Confirm the purchase.",
                    confirm_label: calls === 1 ? "Buy Harness" : "Buy anyway",
                    confirm_field: "confirmed",
                    confirm_value: "1",
                    carry: [...body]
                        .filter(
                            ([name]) =>
                                name !== "csrfmiddlewaretoken" &&
                                name !== "request_key",
                        )
                        .concat([["request_key", `question-${calls}`]]),
                    facts: [],
                    aside: null,
                    checkbox:
                        calls === 1
                            ? {
                                  name: "rate",
                                  value: "paid",
                                  label: "Match rating to price",
                                  description: "Use the paid amount.",
                                  checked: false,
                              }
                            : null,
                },
            }),
        );
    });
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    await userEvent.click(
        await screen.findByRole("checkbox", { name: "Match rating to price" }),
    );
    await userEvent.click(
        within(screen.getByRole("dialog")).getByRole("button", {
            name: "Buy Harness",
        }),
    );
    await userEvent.click(
        await screen.findByRole("button", { name: "Buy anyway" }),
    );
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(3));
    expect(fetcher.mock.calls[2][1].body.get("rate")).toBe("paid");
});
