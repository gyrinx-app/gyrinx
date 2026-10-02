import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RatingTooltip } from "./RatingTooltip";

function setup() {
    render(
        <>
            <RatingTooltip
                name="Vex"
                rating={170}
                baseRating={150}
                defaultBaseRating={100}
            />
            <button>Elsewhere</button>
        </>,
    );
    return screen.getByRole("button", {
        name: "Vex's rating includes a base rating override",
    });
}

describe("RatingTooltip", () => {
    afterEach(() => vi.useRealTimers());

    it.each([0, 50, -30])(
        "opens a title-free breakdown with override delta %i",
        (overrideDelta) => {
            const total = 130 + overrideDelta;
            render(
                <RatingTooltip
                    name="Vex"
                    rating={total}
                    receipt={{
                        defaultRating: 100,
                        overrideDelta,
                        contributions: [
                            { label: "Weapons", rating: 20 },
                            { label: "Gear", rating: 10 },
                        ],
                        total,
                    }}
                />,
            );
            const trigger = screen.getByRole("button", {
                name: "Vex's rating breakdown",
            });
            expect(trigger.firstElementChild!.className).toContain(
                "decoration-dashed",
            );
            expect(screen.queryByRole("dialog")).toBeNull();
            fireEvent.click(trigger, { detail: 1 });
            const panel = screen.getByRole("dialog");
            expect(panel.textContent).toContain("Default base rating100¢");
            expect(panel.textContent).toContain("Weapons+20¢");
            expect(panel.textContent).toContain("Gear+10¢");
            expect(panel.textContent).toContain(`Total rating${total}¢`);
            expect(screen.queryByText("Rating receipt")).toBeNull();
            if (overrideDelta) {
                expect(panel.textContent).toContain(
                    `Base rating override${overrideDelta > 0 ? "+" : ""}${overrideDelta}¢`,
                );
            } else {
                expect(screen.queryByText("Base rating override")).toBeNull();
            }
        },
    );

    it("marks the total with a dashed underline and explains the two base ratings on click", () => {
        const trigger = setup();
        expect(trigger.textContent).toBe("170¢");
        expect(trigger.firstElementChild!.className).toContain(
            "decoration-dashed",
        );
        fireEvent.click(trigger, { detail: 1 });
        expect(
            screen.getByText("Base rating overridden to 150¢."),
        ).toBeTruthy();
        expect(
            screen.getByText("Base rating without an override: 100¢."),
        ).toBeTruthy();
        fireEvent.pointerDown(
            screen.getByRole("button", { name: "Elsewhere" }),
        );
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("opens on hover and stays open after a touch or pointer click", () => {
        vi.useFakeTimers();
        const trigger = setup();
        fireEvent.mouseEnter(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(150));
        expect(screen.getByRole("dialog")).toBeTruthy();
        fireEvent.click(trigger, { detail: 1 });
        fireEvent.mouseLeave(trigger.parentElement!);
        act(() => vi.advanceTimersByTime(250));
        expect(screen.getByRole("dialog")).toBeTruthy();
        fireEvent.click(trigger, { detail: 1 });
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("opens from the keyboard and Escape returns focus to the rating", () => {
        const trigger = setup();
        trigger.focus();
        fireEvent.click(trigger, { detail: 0 });
        expect(document.activeElement).toBe(screen.getByRole("dialog"));
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });
});
