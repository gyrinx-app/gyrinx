import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { RenameDialog, type RenameDialogProps } from "./RenameDialog";

const props: RenameDialogProps = {
    name: "Vex",
    value: "Vex",
    errors: [],
    actionUrl: "/fighters/vex/rename/?back=edit",
    cancelUrl: "/fighters/vex/edit/",
    csrfToken: "token",
    returnFocusId: "pencil",
};
beforeEach(() => {
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
        configurable: true,
        value: function (this: HTMLDialogElement) {
            this.setAttribute("open", "");
        },
    });
    Object.defineProperty(HTMLDialogElement.prototype, "close", {
        configurable: true,
        value: function (this: HTMLDialogElement) {
            this.removeAttribute("open");
        },
    });
    const host = document.createElement("div");
    host.id = "n26-rename-dialog-host";
    document.body.append(host);
    const pencil = document.createElement("button");
    pencil.id = "pencil";
    document.body.append(pencil);
    pencil.focus();
});
afterEach(() => {
    vi.unstubAllGlobals();
    document.getElementById("n26-rename-dialog-host")?.remove();
    document.getElementById("pencil")?.remove();
});

test("opens with the name and posts the edited draft with CSRF", async () => {
    const ajax = vi.fn().mockImplementation(async () => {
        document.getElementById("n26-rename-dialog-host")!.dispatchEvent(
            new CustomEvent("htmx:afterRequest", {
                detail: {
                    xhr: { getResponseHeader: () => props.cancelUrl },
                },
            }),
        );
    });
    vi.stubGlobal("htmx", { ajax });
    const user = userEvent.setup();
    render(<RenameDialog {...props} />);
    const input = screen.getByRole("textbox", { name: "Name" });
    expect((input as HTMLInputElement).value).toBe("Vex");
    await user.clear(input);
    await user.type(input, "Karn");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(ajax).toHaveBeenCalledWith(
        "POST",
        props.actionUrl,
        expect.objectContaining({
            values: { name: "Karn", csrfmiddlewaretoken: "token" },
            swap: "none",
        }),
    );
});
test.each(["Cancel", "Escape"])(
    "%s closes without a request and restores focus",
    async (action) => {
        const ajax = vi.fn();
        vi.stubGlobal("htmx", { ajax });
        const user = userEvent.setup();
        render(<RenameDialog {...props} />);
        if (action === "Cancel")
            await user.click(screen.getByRole("button", { name: "Cancel" }));
        else
            fireEvent(
                screen.getByRole("dialog"),
                new Event("cancel", { cancelable: true }),
            );
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(ajax).not.toHaveBeenCalled();
        expect(document.activeElement).toBe(document.getElementById("pencil"));
        expect(location.pathname).toBe(props.cancelUrl);
    },
);
test("disables duplicate saves and dismissal while pending", async () => {
    let resolve!: () => void;
    const ajax = vi.fn(
        () =>
            new Promise<void>((done) => {
                resolve = done;
            }),
    );
    vi.stubGlobal("htmx", { ajax });
    const user = userEvent.setup();
    render(<RenameDialog {...props} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
    fireEvent(
        screen.getByRole("dialog"),
        new Event("cancel", { cancelable: true }),
    );
    expect(ajax).toHaveBeenCalledTimes(1);
    expect(
        (screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    resolve();
    await waitFor(() =>
        expect(screen.getByRole("button", { name: "Save" })).toBeTruthy(),
    );
});
test.each(["offline", "session"])(
    "%s error preserves the draft and allows retry",
    async (failure) => {
        vi.stubGlobal("htmx", {
            ajax:
                failure === "offline"
                    ? vi.fn().mockRejectedValue(new Error("Offline"))
                    : vi.fn().mockResolvedValue(undefined),
        });
        const user = userEvent.setup();
        render(<RenameDialog {...props} />);
        await user.click(screen.getByRole("button", { name: "Save" }));
        expect(await screen.findByRole("alert")).toHaveProperty(
            "textContent",
            "The name could not be saved. Try again.",
        );
        expect((screen.getByRole("textbox") as HTMLInputElement).value).toBe(
            "Vex",
        );
        expect(
            screen.getByRole("link", { name: "Reload the page" }),
        ).toBeTruthy();
    },
);
test("server field errors are attached to the name input", () => {
    render(
        <RenameDialog
            {...props}
            value=" "
            errors={["A model needs a name."]}
        />,
    );
    expect(screen.getByRole("textbox").getAttribute("aria-invalid")).toBe(
        "true",
    );
    expect(screen.getByText("A model needs a name.")).toBeTruthy();
});
