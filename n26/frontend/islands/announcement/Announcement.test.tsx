import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Announcement, type AnnouncementProps } from "./Announcement";

const props: AnnouncementProps = {
    tone: "info",
    icon: "",
    message: "Campaigns are live.",
    ctaText: "Read the notes",
    ctaUrl: "/notes/",
    dismissible: true,
    dismissUrl: "/dismiss/",
    bannerId: "12",
    csrfToken: "token",
    id: "site-banner-12",
    className: "",
};

afterEach(() => {
    vi.unstubAllGlobals();
});

describe("Announcement", () => {
    it("draws the message, the tone and the call to action", () => {
        render(<Announcement {...props} />);
        const bar = screen.getByRole("complementary", {
            name: "Site announcement",
        });
        expect(bar.getAttribute("data-tone")).toBe("info");
        expect(bar.textContent).toContain("Campaigns are live.");
        expect(
            screen
                .getByRole("link", { name: "Read the notes" })
                .getAttribute("href"),
        ).toBe("/notes/");
    });

    it("hides the bar and posts the banner id", () => {
        const fetchMock = vi.fn().mockResolvedValue(new Response());
        vi.stubGlobal("fetch", fetchMock);
        render(<Announcement {...props} />);
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        expect(
            screen.queryByRole("complementary", { name: "Site announcement" }),
        ).toBeNull();
        expect(fetchMock).toHaveBeenCalledWith("/dismiss/", {
            method: "POST",
            headers: {
                "X-CSRFToken": "token",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ banner_id: "12" }),
        });
    });

    it("hides without posting when the bar is only for this visit", () => {
        const fetchMock = vi.fn();
        vi.stubGlobal("fetch", fetchMock);
        render(<Announcement {...props} dismissUrl="" bannerId="" />);
        fireEvent.click(
            screen.getByRole("button", { name: "Dismiss announcement" }),
        );
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("draws no dismiss button and no icon when asked not to", () => {
        render(
            <Announcement
                {...props}
                dismissible={false}
                icon="none"
                ctaText=""
            />,
        );
        expect(
            screen.queryByRole("button", { name: "Dismiss announcement" }),
        ).toBeNull();
        expect(document.querySelector("svg")).toBeNull();
    });
});
