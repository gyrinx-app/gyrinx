import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { useWorkflowForm } from "./useWorkflowForm";

afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
});
test("review cannot discard an unresolved write without a confirmed conflict", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error()));
    const navigate = vi.fn();
    function Example() {
        const form = useWorkflowForm({
            values: { amount: 0 },
            errors: {},
            commandHref: "/save/",
            csrfToken: "csrf",
            recoveryKey: "example",
            interpret: () => null,
            onNavigate: navigate,
        });
        return (
            <form onSubmit={form.save}>
                <input name="amount" value={form.values.amount} readOnly />
                <button type="submit">Save</button>
                <button type="button" onClick={() => form.review("/review/")}>
                    Review
                </button>
                <p>{form.notice}</p>
            </form>
        );
    }
    render(<Example />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    await userEvent.click(screen.getByRole("button", { name: "Review" }));
    expect(navigate).not.toHaveBeenCalled();
    expect(
        new URLSearchParams(sessionStorage.getItem("example")!).get("amount"),
    ).toBe("0");
});

test("history restoration protects a later form's unresolved command", () => {
    const reload = vi.fn();
    function Example() {
        useWorkflowForm({
            values: { name: "Old draft", snapshot: "old" },
            errors: {},
            commandHref: "/save/",
            csrfToken: "csrf",
            recoveryKey: "example",
            interpret: () => null,
            onReload: reload,
        });
        return null;
    }
    render(<Example />);
    const retained = "name=Later+draft&snapshot=later";
    sessionStorage.setItem("example", retained);
    window.dispatchEvent(
        new PageTransitionEvent("pageshow", { persisted: true }),
    );
    expect(reload).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("example")).toBe(retained);
});

function RecoveryExample({
    navigate,
    csrf = "old-csrf",
}: {
    navigate: (url: string) => void;
    csrf?: string;
}) {
    const form = useWorkflowForm({
        values: { name: "", request_key: "original-key" },
        errors: {},
        commandHref: "/save/",
        csrfToken: csrf,
        recoveryKey: "example",
        onNavigate: navigate,
        interpret: (status, data) =>
            status === 200 && typeof data.nextUrl === "string"
                ? { kind: "saved", nextUrl: data.nextUrl }
                : null,
    });
    return (
        <form onSubmit={form.save}>
            <input type="hidden" name="csrfmiddlewaretoken" value={csrf} />
            <input
                type="hidden"
                name="request_key"
                value={form.values.request_key}
            />
            <fieldset disabled={form.frozen}>
                <label>
                    Name
                    <input
                        name="name"
                        value={form.values.name}
                        onChange={(event) =>
                            form.setValues({
                                ...form.values,
                                name: event.target.value,
                            })
                        }
                    />
                </label>
            </fieldset>
            <div ref={form.summary} tabIndex={-1} role="alert">
                {form.notice}
            </div>
            <button type="submit">Save</button>
            <button
                type="button"
                onClick={(event) => {
                    if (event.currentTarget.form)
                        form.recoverAt("/sign-in/", event.currentTarget.form);
                }}
            >
                Sign in
            </button>
        </form>
    );
}

test("sign-in recovery preserves an editable rejected draft and uses fresh CSRF", async () => {
    const user = userEvent.setup();
    const fetcher = vi
        .fn()
        .mockResolvedValueOnce(new Response("", { status: 401 }))
        .mockResolvedValueOnce(
            new Response(JSON.stringify({ nextUrl: "/done/" }), {
                headers: { "Content-Type": "application/json" },
            }),
        );
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    const first = render(<RecoveryExample navigate={navigate} />);
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Vex");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Sign in again to save this change.");
    await user.clear(screen.getByRole("textbox", { name: "Name" }));
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Sull");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const retained = new URLSearchParams(sessionStorage.getItem("example")!);
    expect(retained.get("name")).toBe("Sull");
    expect(retained.get("__workflow_rejected")).toBe("1");
    expect(retained.has("csrfmiddlewaretoken")).toBe(false);
    expect(navigate).toHaveBeenCalledWith("/sign-in/");
    first.unmount();
    render(<RecoveryExample navigate={navigate} csrf="fresh-csrf" />);
    const name = screen.getByRole("textbox", {
        name: "Name",
    }) as HTMLInputElement;
    expect(name.value).toBe("Sull");
    expect(name.closest("fieldset")?.disabled).toBe(false);
    expect(sessionStorage.getItem("example")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Save" }));
    const body = fetcher.mock.calls[1][1].body as URLSearchParams;
    expect(body.get("name")).toBe("Sull");
    expect(body.get("request_key")).toBe("original-key");
    expect(body.get("csrfmiddlewaretoken")).toBe("fresh-csrf");
    expect(body.has("__workflow_rejected")).toBe(false);
    expect(navigate).toHaveBeenLastCalledWith("/done/");
});

test("sign-in after a rejected retry keeps an earlier unknown command frozen", async () => {
    const user = userEvent.setup();
    const fetcher = vi
        .fn()
        .mockRejectedValueOnce(new Error())
        .mockResolvedValue(new Response("", { status: 401 }));
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    const first = render(<RecoveryExample navigate={navigate} />);
    await user.type(screen.getByRole("textbox", { name: "Name" }), "Vex");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText(/The save may have completed/);
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(
        new URLSearchParams(sessionStorage.getItem("example")!).has(
            "__workflow_rejected",
        ),
    ).toBe(false);
    first.unmount();
    render(<RecoveryExample navigate={navigate} csrf="fresh-csrf" />);
    expect(
        (
            screen
                .getByRole("textbox", { name: "Name" })
                .closest("fieldset") as HTMLFieldSetElement
        ).disabled,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Sign in again to save this change.");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    const retained = new URLSearchParams(sessionStorage.getItem("example")!);
    expect(retained.get("name")).toBe("Vex");
    expect(retained.get("request_key")).toBe("original-key");
    expect(retained.has("__workflow_rejected")).toBe(false);
    expect(retained.has("csrfmiddlewaretoken")).toBe(false);
});

test("recovery navigation cannot leave while a write is still in flight", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn(() => new Promise<Response>(() => {})),
    );
    const navigate = vi.fn();
    render(<RecoveryExample navigate={navigate} />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(navigate).not.toHaveBeenCalled();
    const leaving = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(leaving);
    expect(leaving.defaultPrevented).toBe(true);
});
