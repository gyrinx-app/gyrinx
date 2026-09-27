import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HelpPopover } from "./HelpPopover";

function setup() {
    render(
        <div>
            <HelpPopover label="More about the draw">
                <p>Drawn models are saved in your draft.</p>
            </HelpPopover>
            <button type="button">Elsewhere</button>
        </div>,
    );
    return screen.getByRole("button", { name: "More about the draw" });
}

describe("HelpPopover", () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it("opens on hover after a short delay and closes on leaving", () => {
        const trigger = setup();
        fireEvent.mouseEnter(trigger.parentElement!);
        expect(screen.queryByRole("dialog")).toBeNull();
        act(() => vi.advanceTimersByTime(150));
        expect(
            screen.getByRole("dialog", { name: "More about the draw" }),
        ).toBeTruthy();
        expect(trigger.getAttribute("aria-expanded")).toBe("true");
        fireEvent.mouseLeave(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(250));
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("stays open after a click until the next click", () => {
        const trigger = setup();
        fireEvent.click(trigger);
        expect(
            screen.getByText("Drawn models are saved in your draft."),
        ).toBeTruthy();
        fireEvent.mouseLeave(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(250));
        expect(screen.getByRole("dialog")).toBeTruthy();
        fireEvent.click(trigger);
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("keeps a hovered panel open when it is clicked", () => {
        const trigger = setup();
        fireEvent.mouseEnter(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(150));
        fireEvent.click(trigger);
        fireEvent.mouseLeave(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(250));
        expect(screen.getByRole("dialog")).toBeTruthy();
    });

    it("closes on Escape and returns focus to the icon", () => {
        const trigger = setup();
        fireEvent.click(trigger);
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("moves focus into the panel when opened from the keyboard", () => {
        const trigger = setup();
        trigger.focus();
        fireEvent.click(trigger, { detail: 0 });
        expect(document.activeElement).toBe(screen.getByRole("dialog"));
        fireEvent.keyDown(document, { key: "Escape" });
        expect(document.activeElement).toBe(trigger);
    });

    it("leaves focus on the icon when opened with a pointer", () => {
        const trigger = setup();
        trigger.focus();
        fireEvent.click(trigger, { detail: 1 });
        expect(screen.getByRole("dialog")).toBeTruthy();
        expect(document.activeElement).toBe(trigger);
    });

    it("draws the warning tone as a ghost button with a red icon", () => {
        render(
            <HelpPopover label="Why this card needs attention" tone="warning">
                <p>Too many weapons.</p>
            </HelpPopover>,
        );
        const trigger = screen.getByRole("button", {
            name: "Why this card needs attention",
        });
        expect(trigger.className).toContain("n26-icon-only");
        expect(trigger.querySelector("svg")!.getAttribute("class")).toContain(
            "text-red-600",
        );
        fireEvent.click(trigger);
        expect(screen.getByText("Too many weapons.")).toBeTruthy();
    });

    it("closes on a click outside", () => {
        const trigger = setup();
        fireEvent.click(trigger);
        fireEvent.pointerDown(
            screen.getByRole("button", { name: "Elsewhere" }),
        );
        expect(screen.queryByRole("dialog")).toBeNull();
    });
});
