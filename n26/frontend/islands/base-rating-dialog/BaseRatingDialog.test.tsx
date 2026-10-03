import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import {
    BaseRatingDialog,
    type BaseRatingDialogProps,
} from "./BaseRatingDialog";

import { saveBaseRatingDialog } from "./entry";

const props: BaseRatingDialogProps = {
    value: "100",
    errors: [],
    formErrors: [],
    description:
        "Equipment and advancements add to this figure. Credits paid stay the same.",
    actionUrl: "/fighters/vex/rating/",
    cancelUrl: "/fighters/vex/edit/",
    csrfToken: "token",
    defaultRating: 100,
    hasOverride: false,
};

const viewProps = {
    ...props,
    onSave: (value: string, removing: boolean) =>
        saveBaseRatingDialog(
            document.getElementById("n26-rating-dialog-host"),
            props,
            value,
            removing,
        ),
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
    host.id = "n26-rating-dialog-host";
    document.body.append(host);
});
afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    document.getElementById("n26-rating-dialog-host")?.remove();
});

test("opens with the base rating and sends the draft through htmx with CSRF", async () => {
    const ajax = vi.fn().mockImplementation(async () => {
        document.getElementById("n26-rating-dialog-host")!.dispatchEvent(
            new CustomEvent("htmx:beforeOnLoad", {
                detail: { xhr: { getResponseHeader: () => props.cancelUrl } },
            }),
        );
    });
    vi.stubGlobal("htmx", { ajax });
    const user = userEvent.setup();
    render(<BaseRatingDialog {...viewProps} />);
    expect(
        screen.getByRole("dialog", { name: "Override base rating" }),
    ).toBeTruthy();
    const input = screen.getByRole("spinbutton", { name: "Base rating (¢)" });
    expect((input as HTMLInputElement).value).toBe("100");
    await user.clear(input);
    await user.type(input, "150");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(ajax).toHaveBeenCalledWith("POST", props.actionUrl, {
        source: document.getElementById("n26-rating-dialog-host"),
        swap: "none",
        values: { rating: "150", csrfmiddlewaretoken: "token" },
    });
});

test("blocks duplicate saves and dismissal while a request is pending", async () => {
    let resolve!: () => void;
    const ajax = vi.fn(
        () =>
            new Promise<void>((done) => {
                resolve = done;
            }),
    );
    vi.stubGlobal("htmx", { ajax });
    const user = userEvent.setup();
    render(<BaseRatingDialog {...viewProps} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(
        (screen.getByRole("button", { name: "Saving…" }) as HTMLButtonElement)
            .disabled,
    ).toBe(true);
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);
    fireEvent(
        screen.getByRole("dialog"),
        new Event("cancel", { cancelable: true }),
    );
    expect(ajax).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("dialog")).toBeTruthy();
    resolve();
    await waitFor(() =>
        expect(screen.getByRole("button", { name: "Save" })).toBeTruthy(),
    );
});

test("a failed request preserves the draft and allows retry", async () => {
    vi.stubGlobal("htmx", {
        ajax: vi.fn().mockRejectedValue(new Error("Offline")),
    });
    const user = userEvent.setup();
    render(<BaseRatingDialog {...viewProps} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
        "textContent",
        "The rating could not be saved. Try again.",
    );
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
        "100",
    );
    expect(
        (screen.getByRole("button", { name: "Save" }) as HTMLButtonElement)
            .disabled,
    ).toBe(false);
});

test("a login or CSRF redirect does not silently appear to save", async () => {
    vi.stubGlobal("htmx", { ajax: vi.fn().mockResolvedValue(undefined) });
    const user = userEvent.setup();
    render(<BaseRatingDialog {...viewProps} />);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(
        screen
            .getByRole("link", { name: "Reload the page" })
            .getAttribute("href"),
    ).toBe(props.cancelUrl);
});

test("shows the unmodified contribution and removes the saved override despite an invalid draft", async () => {
    const ajax = vi.fn().mockImplementation(async () => {
        document.getElementById("n26-rating-dialog-host")!.dispatchEvent(
            new CustomEvent("htmx:beforeOnLoad", {
                detail: { xhr: { getResponseHeader: () => props.cancelUrl } },
            }),
        );
    });
    vi.stubGlobal("htmx", { ajax });
    const user = userEvent.setup();
    render(<BaseRatingDialog {...viewProps} value="150" hasOverride />);
    expect(screen.getByText("Without an override")).toBeTruthy();
    expect(screen.getByText("100¢")).toBeTruthy();
    const buttons = screen
        .getAllByRole("button")
        .map((button) => button.textContent);
    expect(buttons).toEqual(["Cancel", "Remove Override", "Save"]);
    await user.clear(screen.getByRole("spinbutton"));
    await user.click(screen.getByRole("button", { name: "Remove Override" }));
    expect(ajax).toHaveBeenCalledWith(
        "POST",
        props.actionUrl,
        expect.objectContaining({
            values: {
                rating: "",
                csrfmiddlewaretoken: "token",
                act: "remove-override",
            },
        }),
    );
});

test("removal is disabled when there is no saved override", () => {
    render(<BaseRatingDialog {...viewProps} />);
    expect(
        (
            screen.getByRole("button", {
                name: "Remove Override",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});

test.each(["Cancel", "Escape"])(
    "%s closes without saving and restores URL and focus",
    async (action) => {
        const previous = document.createElement("button");
        previous.textContent = "Edit rating";
        document.body.append(previous);
        previous.focus();
        const user = userEvent.setup();
        render(<BaseRatingDialog {...viewProps} />);
        if (action === "Cancel")
            await user.click(screen.getByRole("button", { name: "Cancel" }));
        else
            fireEvent(
                screen.getByRole("dialog"),
                new Event("cancel", { cancelable: true }),
            );
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(window.location.pathname).toBe(props.cancelUrl);
        expect(document.activeElement).toBe(previous);
        previous.remove();
    },
);

test("field and operation errors remain visible and associated with the input", () => {
    render(
        <BaseRatingDialog
            {...viewProps}
            errors={["Enter a whole number."]}
            formErrors={["This rating change is too large."]}
        />,
    );
    const input = screen.getByRole("spinbutton");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(
        document.getElementById(
            input.getAttribute("aria-describedby")!.split(" ").at(-1)!,
        )?.textContent,
    ).toBe("Enter a whole number.");
    expect(screen.getByRole("alert").textContent).toBe(
        "This rating change is too large.",
    );
});

test("accepts the response before htmx removes the outer host", async () => {
    const source = document.getElementById("n26-rating-dialog-host")!;
    vi.stubGlobal("htmx", {
        ajax: vi.fn(async () => {
            source.dispatchEvent(
                new CustomEvent("htmx:beforeOnLoad", {
                    detail: {
                        xhr: { getResponseHeader: () => props.cancelUrl },
                    },
                }),
            );
            source.remove();
        }),
    });
    await expect(
        saveBaseRatingDialog(source, props, "150", false),
    ).resolves.toBeUndefined();
});
