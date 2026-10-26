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
