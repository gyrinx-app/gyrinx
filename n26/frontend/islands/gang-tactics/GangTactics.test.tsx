import {
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { GangTactics, type GangTacticsProps } from "./GangTactics";

const props: GangTacticsProps = {
    cards: [
        {
            pk: "one",
            name: "Chem Queen",
            table_name: "Escher",
            dice_label: "D6",
            roll: 3,
            timing: [],
            effect: [],
            developed: false,
            reference: "Book · Page 42",
            tableKey: "escher",
        },
    ],
    yours: true,
    toGenerate: 0,
    tableChoices: [
        {
            value: "escher",
            label: "Escher (D6)",
            description: "6 tactics.",
            checked: true,
            full: false,
        },
    ],
    count: "1",
    errors: {},
    csrfToken: "token",
    rollUrl: "/tactics/",
    batchUrl: "/tactics/batch/",
    bonusChoices: [
        {
            value: "universal",
            label: "Universal (D66)",
            description: "18 tactics.",
            checked: true,
            full: false,
        },
        {
            value: "goliath",
            label: "Goliath (D6)",
            description: "6 tactics.",
            checked: false,
            full: false,
        },
    ],
    bonusUrl: "/tactics/bonus/",
    printView: false,
    initialLayout: "grid",
};
beforeEach(() => {
    vi.stubGlobal(
        "ResizeObserver",
        class {
            observe() {}
            disconnect() {}
        },
    );
    vi.stubGlobal("matchMedia", () => ({
        matches: false,
        addEventListener() {},
        removeEventListener() {},
    }));
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
        configurable: true,
        value() {
            this.setAttribute("open", "");
        },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
        configurable: true,
        value() {
            this.removeAttribute("open");
        },
    });
});
afterEach(() => vi.unstubAllGlobals());
function open(kind: "delete" | "reroll") {
    const view = render(<GangTactics {...props} />);
    fireEvent.click(view.container.querySelector(`#${kind}-one`)!);
    return screen.getByRole("dialog");
}
test("cancel closes the React dialog without a request", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const dialog = open("delete");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
});
test("delete submits CSRF and selection and updates the collection in place", async () => {
    const fetch = vi.fn().mockResolvedValue(
        new Response(
            JSON.stringify({
                cards: [],
                toGenerate: 1,
                tableChoices: props.tableChoices,
                message: "Deleted 1 gang tactic.",
            }),
            { headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    const dialog = open("delete");
    fireEvent.click(within(dialog).getByRole("button", { name: /^Delete$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(
        screen.getByText("No gang tactics yet.", { exact: false }),
    ).toBeTruthy();
    const [, request] = fetch.mock.calls[0];
    expect(request.headers["X-CSRFToken"]).toBe("token");
    expect(request.body.getAll("selected")).toEqual(["one"]);
    expect(request.body.get("confirmed")).toBe("yes");
});
test("reroll retains the dialog and current cards after a server refusal", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            new Response(
                JSON.stringify({
                    error: "Choose an available gang tactics set.",
                }),
                {
                    status: 400,
                    headers: { "Content-Type": "application/json" },
                },
            ),
        ),
    );
    const dialog = open("reroll");
    fireEvent.click(within(dialog).getByRole("button", { name: /^Re-roll$/ }));
    await waitFor(() =>
        expect(within(dialog).getByRole("alert").textContent).toBe(
            "Choose an available gang tactics set.",
        ),
    );
    expect(screen.getByRole("checkbox", { name: "Chem Queen" })).toBeTruthy();
});

test("the reference-only disclaimer follows the cards, and only when there are cards", () => {
    const disclaimer =
        "All text is provided for reference only. Please consult the official Necromunda Skirmish books/journals for official wording.";
    const view = render(<GangTactics {...props} />);
    expect(screen.getByText(disclaimer)).toBeTruthy();
    view.unmount();
    render(<GangTactics {...props} cards={[]} />);
    expect(screen.queryByText(disclaimer)).toBeNull();
});

test("re-rolling several cards asks for one set and sends it", async () => {
    const fetch = vi.fn().mockResolvedValue(
        new Response(
            JSON.stringify({
                cards: [],
                toGenerate: 0,
                tableChoices: [],
                message: "Re-rolled 2 gang tactics.",
            }),
            { headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    const two: GangTacticsProps = {
        ...props,
        cards: [
            props.cards[0],
            {
                ...props.cards[0],
                pk: "two",
                name: "Crossfire",
                table_name: "Universal",
                tableKey: "universal",
            },
        ],
        tableChoices: [
            ...props.tableChoices,
            {
                value: "universal",
                label: "Universal (D66)",
                description: "18 tactics.",
                checked: false,
                full: false,
            },
        ],
    };
    const view = render(<GangTactics {...two} />);
    fireEvent.click(screen.getByRole("button", { name: /^All$/ }));
    const direct = view.container.querySelector(".n26-tactics-direct-actions")!;
    fireEvent.click(
        within(direct as HTMLElement).getByRole("button", { name: /Re-roll/ }),
    );
    const dialog = screen.getByRole("dialog");
    const set = within(dialog).getByLabelText(
        "Re-roll all selected cards from",
    );
    expect((set as HTMLSelectElement).value).toBe("escher");
    fireEvent.change(set, { target: { value: "universal" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^Re-roll$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [, request] = fetch.mock.calls[0];
    expect(request.body.getAll("selected").sort()).toEqual(["one", "two"]);
    expect(request.body.get("table")).toBe("universal");
});

test("generate bonus card draws from any set and shows the new cards", async () => {
    const fetch = vi.fn().mockResolvedValue(
        new Response(
            JSON.stringify({
                cards: [
                    {
                        ...props.cards[0],
                        pk: "bonus",
                        name: "Ironhide",
                        table_name: "Goliath",
                        tableKey: "goliath",
                        bonus: true,
                    },
                ],
                toGenerate: 0,
                tableChoices: props.tableChoices,
                bonusChoices: props.bonusChoices,
                message: "Drew 1 bonus card: Ironhide.",
            }),
            { headers: { "Content-Type": "application/json" } },
        ),
    );
    vi.stubGlobal("fetch", fetch);
    render(<GangTactics {...props} />);
    fireEvent.click(
        screen.getAllByRole("button", { name: /Generate bonus card/ })[0],
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Draw from"), {
        target: { value: "goliath" },
    });
    fireEvent.change(within(dialog).getByLabelText("Number to draw"), {
        target: { value: "2" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: /^Draw$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [url, request] = fetch.mock.calls[0];
    expect(url).toBe("/tactics/bonus/");
    expect(request.body.get("table")).toBe("goliath");
    expect(request.body.get("count")).toBe("2");
    expect(screen.getByText("Bonus card")).toBeTruthy();
});
