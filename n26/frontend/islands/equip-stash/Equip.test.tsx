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

test("initial catalogue needs no request and Enter in search cannot buy", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    render(<Equip {...page} />);
    await userEvent.type(screen.getByRole("searchbox"), "Harness{Enter}");
    expect(screen.getByRole("button", { name: "Buy Harness" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
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
    render(<Equip {...page} />);
    await userEvent.click(screen.getByRole("button", { name: "Buy Harness" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.submit(dialog.querySelector("form")!);
    fireEvent(dialog, new Event("cancel", { cancelable: true }));
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
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
