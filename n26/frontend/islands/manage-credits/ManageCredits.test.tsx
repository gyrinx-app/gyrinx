import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ManageCredits, type ManageCreditsProps } from "./ManageCredits";

const props: ManageCreditsProps = {
    gangName: "Ashen Choir",
    balance: 100,
    gangHref: "/gang/",
    owner: { name: "player", href: "/player/" },
    historyHref: "/history/",
    directions: [
        {
            value: "add",
            label: "Add credits",
            description: "Scenario rewards.",
        },
        {
            value: "remove",
            label: "Remove credits",
            description: "Spending outside the app.",
        },
    ],
    values: {
        direction: "add",
        amount: "",
        note: "",
        request_key: "46ebdbaa-4618-45b6-8d27-e25ca7c2b200",
    },
    errors: {},
    noteHelp: "Optional. Shown in the gang's history.",
    back: "/gang/?sort=-wealth&group=#gangs",
    action: "/credits/",
    commandHref: "/credits/change/",
    csrfToken: "csrf",
};
const json = (data: unknown, status = 200) => ({
    status,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => data,
});
afterEach(() => vi.unstubAllGlobals());

test("saves the selected direction, note, request key and exact return URL", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<ManageCredits {...props} onNavigate={navigate} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("radio", { name: /Remove credits/ }));
    await user.type(
        screen.getByRole("spinbutton", { name: "Credits *" }),
        "30",
    );
    await user.type(screen.getByRole("textbox", { name: "Note" }), "Supplies");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(navigate).toHaveBeenCalledWith(props.back);
    const options = fetch.mock.calls[0][1];
    expect(options.body.get("direction")).toBe("remove");
    expect(options.body.get("note")).toBe("Supplies");
    expect(options.body.get("request_key")).toBe(props.values.request_key);
    expect(options.body.get("back")).toBe(props.back);
    expect(options.headers["X-CSRFToken"]).toBe("csrf");
    expect(options.credentials).toBe("same-origin");
});

test("shows fresh server balance and accessible field errors without losing the draft", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
            json(
                {
                    balance: 70,
                    errors: {
                        amount: [
                            "You cannot remove more than Ashen Choir has (70¢).",
                        ],
                    },
                },
                422,
            ),
        ),
    );
    render(
        <ManageCredits
            {...props}
            values={{ ...props.values, direction: "remove", amount: "100" }}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
        expect(document.activeElement).toBe(screen.getByRole("alert")),
    );
    const amount = screen.getByRole("spinbutton", { name: "Credits *" });
    expect((amount as HTMLInputElement).value).toBe("100");
    expect(amount.getAttribute("aria-invalid")).toBe("true");
    expect(
        document.getElementById(amount.getAttribute("aria-describedby")!)
            ?.textContent,
    ).toBe("You cannot remove more than Ashen Choir has (70¢).");
    expect(amount.matches(":disabled")).toBe(false);
    expect(screen.getByText("Ashen Choir has 70¢.")).not.toBeNull();
});

test("freezes an uncertain save and retries the identical payload before allowing another change", async () => {
    const fetch = vi
        .fn()
        .mockRejectedValueOnce(new Error("lost response"))
        .mockResolvedValueOnce(json({ nextUrl: props.back }));
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(
        <ManageCredits
            {...props}
            values={{ ...props.values, amount: "40" }}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Retry save" });
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    expect(
        screen.getByRole("textbox", { name: "Note" }).matches(":disabled"),
    ).toBe(true);
    expect(screen.getByText(/The save may have completed/)).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry save" }));
    expect(fetch.mock.calls[0][1].body.toString()).toBe(
        fetch.mock.calls[1][1].body.toString(),
    );
    expect(navigate).toHaveBeenCalledWith(props.back);
});

test("a rejected retry does not clear an earlier uncertain outcome", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockRejectedValueOnce(new Error())
            .mockResolvedValueOnce(json({}, 403)),
    );
    render(
        <ManageCredits {...props} values={{ ...props.values, amount: "40" }} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(
        await screen.findByRole("button", { name: "Retry save" }),
    );
    await screen.findByText(/Your session could not be verified/);
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    expect(
        screen.getByRole("button", { name: "Retry save" }).matches(":disabled"),
    ).toBe(false);
});

test("disables duplicate submission while a request is pending", async () => {
    let finish!: (value: unknown) => void;
    const fetch = vi.fn().mockReturnValue(
        new Promise((resolve) => {
            finish = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(
        <ManageCredits
            {...props}
            values={{ ...props.values, amount: "40" }}
            onNavigate={() => {}}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(
        screen.getByRole("button", { name: "Saving…" }).matches(":disabled"),
    ).toBe(true);
    expect(screen.getByRole("spinbutton").matches(":disabled")).toBe(true);
    finish(json({ nextUrl: props.back }));
    await waitFor(() =>
        expect(
            screen.getByRole("button", { name: "Save" }).matches(":disabled"),
        ).toBe(false),
    );
    expect(fetch).toHaveBeenCalledTimes(1);
});

test("warns before leaving while a save is pending and clears the warning after success", async () => {
    let finish!: (value: unknown) => void;
    vi.stubGlobal(
        "fetch",
        vi.fn().mockReturnValue(
            new Promise((resolve) => {
                finish = resolve;
            }),
        ),
    );
    const navigate = vi.fn(() => {
        const event = new Event("beforeunload", { cancelable: true });
        window.dispatchEvent(event);
        expect(event.defaultPrevented).toBe(false);
    });
    render(
        <ManageCredits
            {...props}
            values={{ ...props.values, amount: "40" }}
            onNavigate={navigate}
        />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const leaving = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leaving);
    expect(leaving.defaultPrevented).toBe(true);
    finish(json({ nextUrl: props.back }));
    await waitFor(() => expect(navigate).toHaveBeenCalled());
});
