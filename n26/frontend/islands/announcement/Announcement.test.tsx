import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Announcement, type AnnouncementProps } from "./Announcement";

const props: AnnouncementProps = {
    dismissUrl: "/dismiss/",
    bannerId: "12",
    csrfToken: "token",
};

function draw(extra: Partial<AnnouncementProps> = {}) {
    return render(
        <aside className="n26-announcement">
            <span>Campaigns are live.</span>
            <Announcement {...props} {...extra} />
        </aside>,
    );
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("Announcement", () => {
    it("hides the bar after the dismissal is saved", async () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response());
        vi.stubGlobal("fetch", fetchMock);
        const view = draw();
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        const bar = view.container.querySelector(".n26-announcement");
        expect(bar?.hasAttribute("hidden")).toBe(false);
        await waitFor(() => {
            expect(bar?.hasAttribute("hidden")).toBe(true);
        });
        expect(fetchMock).toHaveBeenCalledWith("/dismiss/", {
            method: "POST",
            headers: {
                "X-CSRFToken": "token",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ banner_id: "12" }),
        });
    });

    it("leaves the bar up when the dismissal is refused", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(new Response(null, { status: 403 })),
        );
        const view = draw();
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        expect(await screen.findByRole("alert")).toBeTruthy();
        expect(screen.getByRole("alert").textContent).toBe(
            "This announcement is still showing. Try again.",
        );
        expect(
            view.container
                .querySelector(".n26-announcement")
                ?.hasAttribute("hidden"),
        ).toBe(false);
    });

    it("leaves the bar up when the dismissal request fails", async () => {
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
        const view = draw();
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        expect(await screen.findByRole("alert")).toBeTruthy();
        expect(
            view.container
                .querySelector(".n26-announcement")
                ?.hasAttribute("hidden"),
        ).toBe(false);
    });

    it("hides without posting when the bar is only for this visit", () => {
        const fetchMock = vi.fn();
        vi.stubGlobal("fetch", fetchMock);
        const view = draw({ dismissUrl: "", bannerId: "" });
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        expect(fetchMock).not.toHaveBeenCalled();
        expect(
            view.container
                .querySelector(".n26-announcement")
                ?.hasAttribute("hidden"),
        ).toBe(true);
    });
});
