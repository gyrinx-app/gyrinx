import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Confirmation } from "./Confirmation";
import type { HireProps } from "./types";

const props: HireProps = {
    scope: "gang",
    scopeLabel: "Gang list",
    scopeTabs: [],
    section: "Fighters",
    listingHref: "/hire/",
    priceFloor: 60,
    priceCeiling: 60,
    categories: [],
    categoryOptions: [],
    sections: [],
    gangName: "Ashen Choir",
    gangHref: "/gang/",
    owner: { name: "Keeper" },
    figures: {
        items: [],
        roster: { count: 0, rating: 0, groups: [], models: [] },
    },
    values: {
        list: "gang",
        section: "Fighters",
        profile: "ganger-offer",
        selection: '["sword"]',
        name: "",
        paid: "",
        rate: "paid",
        request_key: "original-key",
        profile_name: "Ganger",
        choice_names: '["Sword"]',
        quoted: "85",
    },
    errors: {},
    confirmation: true,
    notice: "",
    messages: [],
    csrfToken: "fresh-csrf",
    action: "/hire/",
    commandHref: "/hire/command/",
    recoveryKey: "hire:owner:gang",
    back: "/hire/",
    signInHref: "/sign-in/?next=/hire/",
};
beforeEach(() => {
    sessionStorage.clear();
    HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
        this.querySelector<HTMLInputElement>(
            'input:not([type="hidden"])',
        )?.focus();
    };
    HTMLDialogElement.prototype.close = function () {
        this.open = false;
    };
});
afterEach(() => vi.unstubAllGlobals());
function response(data: unknown, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json" },
    });
}

test("posts stable options, explicit zero and an unchecked rating choice", async () => {
    const fetcher = vi
        .fn()
        .mockResolvedValue(response({ nextUrl: "/arrivals/" }));
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    render(
        <Confirmation {...props} onFigures={vi.fn()} onNavigate={navigate} />,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Vex");
    await userEvent.type(
        screen.getByRole("spinbutton", { name: "Price" }),
        "0",
    );
    await userEvent.click(
        screen.getByRole("checkbox", { name: "Match rating to price" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Hire" }));
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(Object.fromEntries(body)).toMatchObject({
        profile: "ganger-offer",
        selection: '["sword"]',
        paid: "0",
        rate: "",
        name: "Vex",
        request_key: "original-key",
        csrfmiddlewaretoken: "fresh-csrf",
    });
    expect(navigate).toHaveBeenCalledWith("/arrivals/");
    expect(sessionStorage.getItem(props.recoveryKey)).toBeNull();
});

test("shows authoritative figures and focuses errors without clearing the draft", async () => {
    const figures = {
        ...props.figures,
        items: [
            {
                short: "Cr",
                label: "Credits",
                value: "40¢",
                absent: "",
                href: "",
            },
        ],
    };
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                response(
                    { errors: { name: ["Choose a shorter name."] }, figures },
                    422,
                ),
            ),
    );
    const onFigures = vi.fn();
    render(<Confirmation {...props} onFigures={onFigures} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Vex");
    await userEvent.click(screen.getByRole("button", { name: "Hire" }));
    await screen.findByText("Choose a shorter name.");
    expect(onFigures).toHaveBeenCalledWith(figures);
    expect(screen.getByRole("alert", { name: "Hire errors" })).toBe(
        document.activeElement,
    );
    expect(
        (screen.getByRole("textbox", { name: "Name" }) as HTMLInputElement)
            .value,
    ).toBe("Vex");
});

test("a lost response freezes input, blocks dismissal and retries the exact command", async () => {
    const fetcher = vi
        .fn()
        .mockRejectedValueOnce(new Error())
        .mockResolvedValueOnce(response({ nextUrl: "/hire/" }));
    vi.stubGlobal("fetch", fetcher);
    const navigate = vi.fn();
    render(
        <Confirmation {...props} onFigures={vi.fn()} onNavigate={navigate} />,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Name" }), "Vex");
    await userEvent.click(screen.getByRole("button", { name: "Hire" }));
    await screen.findByText(/The save may have completed/);
    expect(
        (
            screen
                .getByRole("textbox", { name: "Name" })
                .closest("fieldset") as HTMLFieldSetElement
        ).disabled,
    ).toBe(true);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(navigate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Retry hire" }));
    expect(fetcher.mock.calls[1][1].body.toString()).toBe(
        fetcher.mock.calls[0][1].body.toString(),
    );
    expect(navigate).toHaveBeenCalledWith("/hire/");
});

test("reload recovers an unknown hire even when the current catalogue has no dialog", async () => {
    sessionStorage.setItem(
        props.recoveryKey,
        new URLSearchParams(props.values).toString(),
    );
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(response({ nextUrl: "/hire/" })),
    );
    render(
        <Confirmation
            {...props}
            confirmation={false}
            values={{ ...props.values, profile: "", profile_name: "" }}
            onFigures={vi.fn()}
            onNavigate={vi.fn()}
        />,
    );
    expect(
        screen.getByRole("dialog", { name: "Confirm earlier hire: Ganger" }),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Retry hire" }));
    await waitFor(() =>
        expect(sessionStorage.getItem(props.recoveryKey)).toBeNull(),
    );
});

test("malformed success data cannot release an unresolved command", async () => {
    vi.stubGlobal(
        "fetch",
        vi
            .fn()
            .mockResolvedValue(
                response({ nextUrl: "https://elsewhere.example/" }),
            ),
    );
    const navigate = vi.fn();
    render(
        <Confirmation {...props} onFigures={vi.fn()} onNavigate={navigate} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Hire" }));
    await screen.findByRole("button", { name: "Retry hire" });
    expect(navigate).not.toHaveBeenCalled();
    expect(sessionStorage.getItem(props.recoveryKey)).not.toBeNull();
});

test("opens the confirmation with name focus, rating help and a working Escape destination", () => {
    const navigate = vi.fn();
    render(
        <Confirmation
            {...props}
            values={{ ...props.values, paid: "85" }}
            onFigures={vi.fn()}
            onNavigate={navigate}
        />,
    );
    expect(document.activeElement).toBe(
        screen.getByRole("textbox", { name: "Name" }),
    );
    expect(
        (screen.getByRole("spinbutton", { name: "Price" }) as HTMLInputElement)
            .max,
    ).toBe("100000");
    const rating = screen.getByRole("checkbox", {
        name: "Match rating to price",
    });
    expect(
        document.getElementById(rating.getAttribute("aria-describedby")!)
            ?.textContent,
    ).toContain("quoted rating of 85¢");
    fireEvent(
        screen.getByRole("dialog"),
        new Event("cancel", { cancelable: true }),
    );
    expect(navigate).toHaveBeenCalledWith(props.back);
});
