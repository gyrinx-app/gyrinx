import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tooltip } from "./Tooltip";

afterEach(() => vi.useRealTimers());

describe("Tooltip", () => {
    it("describes its control on focus and dismisses without moving focus", async () => {
        const user = userEvent.setup();
        render(
            <Tooltip label="Models in the gang">
                <button>Roster</button>
            </Tooltip>,
        );
        const button = screen.getByRole("button", { name: "Roster" });
        expect(
            document.getElementById(button.getAttribute("aria-describedby")!)
                ?.textContent,
        ).toBe("Models in the gang");
        expect(screen.queryByRole("tooltip")).toBeNull();
        await user.tab();
        expect(screen.getByRole("tooltip").textContent).toBe(
            "Models in the gang",
        );
        expect(document.activeElement).toBe(button);
        fireEvent.mouseLeave(button.parentElement!);
        expect(screen.getByRole("tooltip")).toBeTruthy();
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("tooltip")).toBeNull();
        expect(document.activeElement).toBe(button);
    });

    it("delays hover help and cancels a hover that ends before opening", () => {
        vi.useFakeTimers();
        render(
            <Tooltip label="Rating">
                <button>R</button>
            </Tooltip>,
        );
        const anchor = screen.getByRole("button").parentElement!;
        fireEvent.mouseEnter(anchor);
        act(() => vi.advanceTimersByTime(100));
        expect(screen.queryByRole("tooltip")).toBeNull();
        fireEvent.mouseLeave(anchor);
        act(() => vi.advanceTimersByTime(100));
        expect(screen.queryByRole("tooltip")).toBeNull();
        fireEvent.mouseEnter(anchor);
        act(() => vi.advanceTimersByTime(120));
        expect(screen.getByRole("tooltip").textContent).toBe("Rating");
        fireEvent.mouseLeave(anchor);
        expect(screen.queryByRole("tooltip")).toBeNull();
    });

    it("keeps existing descriptions and the control's own action", async () => {
        const user = userEvent.setup();
        const clicked = vi.fn();
        render(
            <>
                <span id="balance-help">Cash available</span>
                <Tooltip label="Credits">
                    <button aria-describedby="balance-help" onClick={clicked}>
                        Cr
                    </button>
                </Tooltip>
            </>,
        );
        const button = screen.getByRole("button");
        expect(button.getAttribute("aria-describedby")).toMatch(
            /^balance-help /,
        );
        await user.tab();
        await user.keyboard("{Enter}");
        expect(clicked).toHaveBeenCalledOnce();
        expect(screen.queryByRole("tooltip")).toBeNull();
        expect(document.activeElement).toBe(button);
    });
});
