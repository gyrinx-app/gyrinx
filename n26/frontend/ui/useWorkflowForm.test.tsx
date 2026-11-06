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
