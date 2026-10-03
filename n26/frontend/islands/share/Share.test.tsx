import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import cotton from "../../generated/cotton.json";
import { Share, shareNavigation, type ShareProps } from "./Share";

const props: ShareProps = {
    url: "/n26/g/1/",
    message: "Link copied.",
    size: "xs",
    variant: "ghost",
};

function installShare(share: ReturnType<typeof vi.fn> | undefined) {
    Object.defineProperty(navigator, "share", {
        configurable: true,
        value: share,
    });
}

function installCanShare(canShare: ReturnType<typeof vi.fn> | undefined) {
    Object.defineProperty(navigator, "canShare", {
        configurable: true,
        value: canShare,
    });
}

function installClipboard(writeText: ReturnType<typeof vi.fn> | undefined) {
    Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: writeText ? { writeText } : undefined,
    });
}

afterEach(() => {
    vi.useRealTimers();
    installShare(undefined);
    installCanShare(undefined);
    installClipboard(undefined);
    vi.restoreAllMocks();
});

function renderShare(initial?: Partial<ShareProps>) {
    render(<Share {...props} {...initial} />);
    return screen.getByRole<HTMLAnchorElement>("link", { name: "Share" });
}

function prevented(link: HTMLElement, init: MouseEventInit = {}) {
    let defaultPrevented = false;
    document.addEventListener(
        "click",
        (event) => {
            defaultPrevented = event.defaultPrevented;
        },
        { once: true },
    );
    fireEvent.click(link, init);
    return defaultPrevented;
}

describe("Share", () => {
    it("draws the extra-small ghost link and hides the word below sm", () => {
        const link = renderShare();
        expect(link.getAttribute("href")).toBe("/n26/g/1/");
        expect(link.className).toContain(cotton.buttonLinkBySize.xs.ghost);
        expect(link.className).toContain(
            "!inline-flex min-h-5 items-center gap-1.5 !py-px",
        );
        expect(link.querySelector("svg")?.getAttribute("class")).toContain(
            "size-3.5",
        );
        expect(screen.getByText("Share").className).toContain("hidden");
        expect(screen.getByText("Share").className).toContain("sm:inline");
        expect(screen.getByRole("status").textContent).toBe("");
    });

    it("opens the share sheet with the link's absolute href", () => {
        const share = vi.fn().mockResolvedValue(undefined);
        const writeText = vi.fn();
        installShare(share);
        installCanShare(vi.fn().mockReturnValue(true));
        installClipboard(writeText);
        const link = renderShare();

        expect(prevented(link)).toBe(true);
        expect(share).toHaveBeenCalledWith({ url: link.href });
        expect(link.href).toMatch(/^https?:\/\//);
        expect(writeText).not.toHaveBeenCalled();
        expect(screen.getByRole("status").textContent).toBe("");
    });

    it("leaves a modified click or a new-window link to the browser", () => {
        const share = vi.fn();
        installShare(share);
        const link = renderShare();

        expect(prevented(link, { metaKey: true })).toBe(false);
        expect(prevented(link, { ctrlKey: true })).toBe(false);
        expect(prevented(link, { button: 1 })).toBe(false);
        link.target = "_blank";
        expect(prevented(link)).toBe(false);
        expect(share).not.toHaveBeenCalled();
    });

    it("ignores a dismissed share sheet", async () => {
        const share = vi
            .fn()
            .mockRejectedValue(
                Object.assign(new Error("dismissed"), { name: "AbortError" }),
            );
        const writeText = vi.fn();
        installShare(share);
        installClipboard(writeText);
        const link = renderShare();

        fireEvent.click(link);
        await vi.waitFor(() => expect(share).toHaveBeenCalled());
        expect(writeText).not.toHaveBeenCalled();
        expect(screen.getByRole("status").textContent).toBe("");
    });

    it("copies the absolute link when the share sheet fails", async () => {
        const share = vi.fn().mockRejectedValue(new Error("unavailable"));
        const writeText = vi.fn().mockResolvedValue(undefined);
        installShare(share);
        installCanShare(undefined);
        installClipboard(writeText);
        const link = renderShare({
            message: "Link copied. Only people with the link can open it.",
        });

        fireEvent.click(link);
        expect((await screen.findByRole("status")).textContent).toBe(
            "Link copied. Only people with the link can open it.",
        );
        expect(writeText).toHaveBeenCalledWith(link.href);
    });

    it("copies when the browser has no share sheet", async () => {
        const writeText = vi.fn().mockResolvedValue(undefined);
        installShare(undefined);
        installClipboard(writeText);
        const link = renderShare();

        fireEvent.click(link);
        expect((await screen.findByRole("status")).textContent).toBe(
            "Link copied.",
        );
        expect(writeText).toHaveBeenCalledWith(link.href);
    });

    it("copies when the page cannot be shared", async () => {
        const share = vi.fn();
        const writeText = vi.fn().mockResolvedValue(undefined);
        installShare(share);
        installCanShare(vi.fn().mockReturnValue(false));
        installClipboard(writeText);
        const link = renderShare();

        fireEvent.click(link);
        expect(await screen.findByText("Link copied.")).not.toBeNull();
        expect(share).not.toHaveBeenCalled();
        expect(writeText).toHaveBeenCalledWith(link.href);
    });

    it("follows the link when the copy fails", async () => {
        const assign = vi
            .spyOn(shareNavigation, "assign")
            .mockImplementation(() => {});
        const writeText = vi.fn().mockRejectedValue(new Error("denied"));
        installShare(undefined);
        installClipboard(writeText);
        const link = renderShare();

        fireEvent.click(link);
        await vi.waitFor(() => expect(assign).toHaveBeenCalledWith(link.href));
        expect(screen.getByRole("status").textContent).toBe("");
    });

    it("follows the link when the clipboard is missing", () => {
        const assign = vi
            .spyOn(shareNavigation, "assign")
            .mockImplementation(() => {});
        installShare(undefined);
        installClipboard(undefined);
        const link = renderShare();

        fireEvent.click(link);
        expect(assign).toHaveBeenCalledWith(link.href);
    });

    it("hides the copied message after four seconds, reset by another copy", () => {
        vi.useFakeTimers();
        const writeText = vi.fn().mockImplementation(
            () =>
                ({
                    then(onSuccess: () => void) {
                        onSuccess();
                    },
                }) as Promise<void>,
        );
        installShare(undefined);
        installClipboard(writeText);
        const link = renderShare();

        fireEvent.click(link);
        expect(screen.getByRole("status").textContent).toBe("Link copied.");

        act(() => {
            vi.advanceTimersByTime(3999);
        });
        expect(screen.getByRole("status").textContent).toBe("Link copied.");
        fireEvent.click(link);
        act(() => {
            vi.advanceTimersByTime(3999);
        });
        expect(screen.getByRole("status").textContent).toBe("Link copied.");
        act(() => {
            vi.advanceTimersByTime(1);
        });
        expect(screen.getByRole("status").textContent).toBe("");
    });
});
