import {
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
    NotificationInbox,
    type NotificationInboxProps,
} from "./NotificationInbox";
const props: NotificationInboxProps = {
    filters: { bucket: "inbox", status: "all", type: "", q: "" },
    csrfToken: "token",
    inboxUrl: "/notifications/",
    bulkUrl: "/notifications/bulk",
    returnUrl: "/notifications/",
    unreadCount: 2,
    typeChoices: [{ value: "system", label: "System" }],
    page: 1,
    pages: 2,
    previousUrl: "",
    nextUrl: "/notifications/?page=2",
    rows: ["first", "second"].map((id) => ({
        id,
        subject: `${id} update`,
        content: [
            {
                tag: "p",
                attrs: {},
                children: [
                    "Hello ",
                    { tag: "strong", attrs: {}, children: ["bold"] },
                ],
            },
        ],
        sender: "Gyrinx",
        system: true,
        created: "2026-10-04T12:00:00Z",
        age: "1 hour ago",
        type: "System",
        read: false,
        archived: false,
        openUrl: `/notification/${id}/open`,
        actions: {
            read: `/notification/${id}/read`,
            unread: `/notification/${id}/unread`,
            archive: `/notification/${id}/archive`,
            unarchive: `/notification/${id}/unarchive`,
            delete: `/notification/${id}/delete`,
        },
    })),
};
afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
});
function response(data: unknown = { ok: true }) {
    return {
        ok: true,
        status: 200,
        redirected: false,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => data,
    };
}
describe("Notification inbox", () => {
    it("opens titles through the read proxy and preserves rich text", () => {
        render(<NotificationInbox {...props} />);
        expect(
            screen
                .getByRole("link", { name: "first update" })
                .getAttribute("href"),
        ).toBe("/notification/first/open");
        expect(screen.getAllByText("bold")[0].tagName).toBe("STRONG");
        expect(
            screen.getByRole("link", { name: "Next" }).getAttribute("href"),
        ).toBe(props.nextUrl);
        expect(
            (screen.getByLabelText("Status") as HTMLSelectElement).value,
        ).toBe("all");
    });
    it("selects the page, posts only selected IDs with CSRF, and removes archived notifications", async () => {
        const fetch = vi
            .fn()
            .mockResolvedValueOnce(response())
            .mockResolvedValueOnce(
                response({
                    ...props,
                    rows: props.rows.slice(1),
                    page: 1,
                    pages: 1,
                    nextUrl: "",
                    unreadCount: 1,
                }),
            );
        vi.stubGlobal("fetch", fetch);
        render(<NotificationInbox {...props} />);
        fireEvent.click(screen.getByLabelText("Select: first update"));
        expect(screen.getByLabelText("Select this page")).toHaveProperty(
            "indeterminate",
            true,
        );
        fireEvent.click(
            within(
                screen.getByRole("group", { name: "Selected notifications" }),
            ).getByRole("button", { name: /^Archive$/ }),
        );
        await waitFor(() =>
            expect(
                screen.queryByRole("link", { name: "first update" }),
            ).toBeNull(),
        );
        const [url, options] = fetch.mock.calls[0];
        expect(url).toBe(props.bulkUrl);
        expect(options.headers["X-CSRFToken"]).toBe("token");
        expect(options.body.getAll("ids")).toEqual(["first"]);
        expect(
            screen.getByRole("link", { name: "second update" }),
        ).toBeTruthy();
        expect(fetch.mock.calls[1][0]).toBe(
            "/notifications/?bucket=inbox&status=all&type=&q=",
        );
        expect(screen.queryByRole("link", { name: "Next" })).toBeNull();
        expect(screen.getByText("Page 1 of 1")).toBeTruthy();
    });
    it("keeps rows when an action fails and permits retry", async () => {
        const fetch = vi.fn().mockRejectedValue(new Error("offline"));
        vi.stubGlobal("fetch", fetch);
        render(<NotificationInbox {...props} />);
        const first = screen
            .getByRole("link", { name: "first update" })
            .closest("li")!;
        fireEvent.click(
            within(first).getByRole("button", { name: "Mark read" }),
        );
        await screen.findByRole("alert");
        expect(screen.getByRole("link", { name: "first update" })).toBeTruthy();
        expect(
            (
                within(first).getByRole("button", {
                    name: "Mark read",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(false);
    });
    it("marks the whole active inbox read even from filtered archived pages", async () => {
        const fetch = vi.fn().mockResolvedValue(response());
        vi.stubGlobal("fetch", fetch);
        render(
            <NotificationInbox
                {...props}
                filters={{
                    bucket: "archived",
                    status: "read",
                    type: "system",
                    q: "needle",
                }}
                rows={[]}
            />,
        );
        fireEvent.click(
            screen.getByRole("button", { name: "Mark inbox read" }),
        );
        await screen.findByRole("status");
        const body = fetch.mock.calls[0][1].body;
        expect(body.get("all")).toBe("1");
        expect(body.get("bucket")).toBe("inbox");
        expect(body.get("q")).toBe("");
    });
});

it("toolkit attribution shows the live sender name with their badge", () => {
    render(
        <NotificationInbox
            {...props}
            rows={[
                {
                    ...props.rows[0],
                    context: {
                        campaignName: "Ash Road",
                        campaignHref: "/campaign/",
                        sender: {
                            name: "Ada",
                            href: "/user/@Ada/",
                            badge: {
                                label: "Campaign supporter",
                                svg: {
                                    tag: "svg",
                                    props: { viewBox: "0 0 24 24" },
                                    children: [
                                        { tag: "path", props: { d: "M0 0h1" } },
                                    ],
                                },
                            },
                        },
                    },
                },
            ]}
        />,
    );
    expect(screen.getByText("· Sent by")).toBeDefined();
    expect(screen.getByRole("link", { name: /Ada/ })).toBeDefined();
    expect(
        screen.getByRole("img", { name: "Campaign supporter" }),
    ).toBeDefined();
});

const offered = (choices = 1): NotificationInboxProps => ({
    ...props,
    rows: [
        {
            ...props.rows[0],
            offer: {
                id: "receipt-a",
                gang: "Glass Vipers",
                choices,
                resolved: false,
                selected: [],
                rewards: [{ label: "30¢" }, { label: "60¢" }, { label: "90¢" }],
                commandHref: "/toolkit/choose/command/",
                recoveryKey: "toolkit-offer-a",
                values: { request_key: "offer-command-1", payload: "" },
            },
        },
    ],
});

it("confirms a radio choice inside the notification without navigating", async () => {
    const fetch = vi
        .fn()
        .mockResolvedValue(response({ nextUrl: "/intervention/" }));
    vi.stubGlobal("fetch", fetch);
    render(<NotificationInbox {...offered()} />);
    fireEvent.click(screen.getByRole("radio", { name: "30¢" }));
    fireEvent.click(screen.getByRole("radio", { name: "60¢" }));
    expect(screen.getAllByRole("radio", { checked: true })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Confirm choice" }));
    await screen.findByText("Applied: 60¢");
    const [url, options] = fetch.mock.calls[0];
    expect(url).toBe("/toolkit/choose/command/");
    expect(JSON.parse(options.body.get("payload"))).toEqual({
        receipt: "receipt-a",
        selected: [1],
    });
    expect(options.headers["X-CSRFToken"]).toBe("token");
    expect(sessionStorage.getItem("toolkit-offer-a")).toBeNull();
});

it("limits multiple rewards and retains an uncertain inline choice for reload", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    const view = render(<NotificationInbox {...offered(2)} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "30¢" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "60¢" }));
    expect(screen.getByRole("checkbox", { name: "90¢" })).toHaveProperty(
        "disabled",
        true,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "30¢" }));
    expect(screen.getByRole("checkbox", { name: "90¢" })).toHaveProperty(
        "disabled",
        false,
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "90¢" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm choices" }));
    await screen.findByRole("button", { name: "Retry save" });
    expect(sessionStorage.getItem("toolkit-offer-a")).toContain(
        "offer-command-1",
    );
    view.unmount();
    render(<NotificationInbox {...offered(2)} csrfToken="fresh-token" />);
    expect(screen.getByRole("button", { name: "Retry save" })).toBeDefined();
    expect(screen.getByRole("checkbox", { name: "60¢" })).toHaveProperty(
        "checked",
        true,
    );
    expect(
        screen.getByRole("checkbox", { name: "60¢" }).closest("fieldset"),
    ).toHaveProperty("disabled", true);
});

it("shows edited content and lets the reader open the original version", () => {
    render(
        <NotificationInbox
            {...props}
            rows={[
                {
                    ...props.rows[0],
                    edited: {
                        at: "2026-11-12T12:00:00Z",
                        originalSubject: "Original title",
                        originalContent: ["Original message."],
                    },
                },
            ]}
        />,
    );
    expect(screen.getByText(/Edited/)).toBeDefined();
    expect(screen.queryByText("Original message.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "View original" }));
    expect(screen.getByText("Original message.")).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "Hide original" }));
    expect(screen.queryByText("Original message.")).toBeNull();
});
