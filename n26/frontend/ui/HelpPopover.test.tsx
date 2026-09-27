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

    it("closes on a click outside", () => {
        const trigger = setup();
        fireEvent.click(trigger);
        fireEvent.pointerDown(
            screen.getByRole("button", { name: "Elsewhere" }),
        );
        expect(screen.queryByRole("dialog")).toBeNull();
    });
});
