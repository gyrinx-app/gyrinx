import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Help } from "./Help";

describe("Help in a refreshed model section", () => {
    it("starts closed after a redraw and opens only when requested", () => {
        const props = {
            label: "Why Cinder cannot take XP",
            paragraphs: [
                "XP cannot be recorded until counter history is switched on.",
            ],
            triggerId: "cinder-xp-why-button",
        };
        const { rerender } = render(<Help key="before" {...props} />);
        const trigger = screen.getByRole("button", { name: props.label });
        expect(trigger.id).toBe(props.triggerId);
        trigger.focus();
        expect(screen.queryByRole("dialog")).toBeNull();
        fireEvent.click(trigger);
        expect(screen.getByRole("dialog")).toBeTruthy();
        rerender(<Help key="after" {...props} />);
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(
            screen
                .getByRole("button", { name: props.label })
                .getAttribute("aria-expanded"),
        ).toBe("false");
        fireEvent.click(screen.getByRole("button", { name: props.label }));
        expect(screen.getByText(props.paragraphs[0])).toBeTruthy();
    });
});
