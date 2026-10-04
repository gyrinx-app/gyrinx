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
afterEach(() => vi.unstubAllGlobals());
function response() {
    return {
        ok: true,
        redirected: false,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => ({ ok: true }),
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
        const fetch = vi.fn().mockResolvedValue(response());
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
