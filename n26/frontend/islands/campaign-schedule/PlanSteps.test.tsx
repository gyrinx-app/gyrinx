import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PlanSteps } from "./PlanSteps";
import type { Phase, Step } from "./types";

Element.prototype.scrollIntoView = vi.fn();

const reward = { credits: { fixed: 0, dice: null }, reputation: 0 };
const phases: Phase[] = ["Opening", "Downtime"].map((name, index) => ({
    id: "phase-" + index,
    name,
    description: "",
    effects: "",
    count: 0,
    rewards: {
        win: reward,
        draw: reward,
        loss: reward,
        entry_credits: { fixed: 0, dice: null },
    },
    editHref: "",
    duplicateHref: "",
    deleteHref: "",
}));
const steps: Step[] = [
    { id: "opening", phase_id: "phase-0", count: 3 },
    { id: "break", phase_id: "phase-1", count: 1 },
    { id: "closing", phase_id: "phase-0", count: 2 },
];

function setup(initial = steps, disabled = false) {
    const changed = vi.fn();
    function Example() {
        const [value, setValue] = useState(JSON.stringify(initial));
        return (
            <>
                <PlanSteps
                    value={value}
                    onChange={(next) => {
                        changed(next);
                        setValue(next);
                    }}
                    phases={phases}
                    disabled={disabled}
                    startsAfterOrder={4}
                />
                <output data-testid="payload">{value}</output>
            </>
        );
    }
    const view = render(<Example />);
    return { ...view, changed };
}
const saved = () =>
    JSON.parse(screen.getByTestId("payload").textContent!) as Step[];
const ids = () => saved().map((step) => step.id);

describe("Pattern step reordering", () => {
    it("commits one stable-ID move only after a keyboard drop", () => {
        const { changed } = setup();
        const handle = screen.getByRole("button", { name: "Move step 2" });
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "Home" });
        expect(ids()).toEqual(["opening", "break", "closing"]);
        expect(changed).not.toHaveBeenCalled();
        fireEvent.keyDown(handle, { key: "Enter" });
        expect(ids()).toEqual(["break", "opening", "closing"]);
        expect(changed).toHaveBeenCalledTimes(1);
        expect(saved()).toEqual([steps[1], steps[0], steps[2]]);
        expect(screen.getByText("Ends after Cycle 10.")).not.toBeNull();
    });

    it("cancels previews with Escape or Tab without changing the payload", () => {
        const { container, changed } = setup();
        const handle = screen.getByRole("button", { name: "Move step 1" });
        for (const cancel of ["Escape", "Tab"]) {
            handle.focus();
            fireEvent.keyDown(handle, { key: " " });
            fireEvent.keyDown(handle, { key: "End" });
            expect(
                container.querySelector('[data-reorder-active="true"]'),
            ).not.toBeNull();
            expect(ids()).toEqual(["opening", "break", "closing"]);
            fireEvent.keyDown(handle, { key: cancel });
            expect(
                container.querySelector('[data-reorder-active="true"]'),
            ).toBeNull();
        }
        expect(changed).not.toHaveBeenCalled();
    });

    it("keeps cycle counts and phase selectors editable without starting a move", () => {
        setup();
        fireEvent.change(
            screen.getByRole("spinbutton", { name: "Step 1 cycles" }),
            { target: { value: "7" } },
        );
        fireEvent.change(
            screen.getByRole("combobox", { name: "Step 2 phase" }),
            { target: { value: "phase-0" } },
        );
        expect(ids()).toEqual(["opening", "break", "closing"]);
        expect(saved()[0].count).toBe(7);
        expect(saved()[1].phase_id).toBe("phase-0");
        expect(screen.queryByRole("button", { pressed: true })).toBeNull();
    });

    it("retains arrow moves, removal and addition as local edits", () => {
        setup();
        fireEvent.click(
            screen.getByRole("button", { name: "Move step 2 earlier" }),
        );
        expect(ids()).toEqual(["break", "opening", "closing"]);
        fireEvent.click(
            screen.getByRole("button", { name: "Move step 1 later" }),
        );
        expect(ids()).toEqual(["opening", "break", "closing"]);
        fireEvent.click(screen.getByRole("button", { name: "Remove step 3" }));
        fireEvent.click(screen.getByRole("button", { name: "Add step" }));
        expect(ids().slice(0, 2)).toEqual(["opening", "break"]);
        expect(saved()[2]).toMatchObject({ phase_id: "phase-0", count: 1 });
        expect(saved()[2].id).not.toBe("closing");
    });

    it("provides no no-op handle for a single step and disables locked controls", () => {
        const first = setup([steps[0]]);
        expect(
            screen.queryByRole("button", { name: "Move step 1" }),
        ).toBeNull();
        expect(screen.getByRole("spinbutton").hasAttribute("disabled")).toBe(
            false,
        );
        first.unmount();
        setup(steps, true);
        for (const button of screen.getAllByRole("button"))
            expect(button.hasAttribute("disabled")).toBe(true);
        for (const input of screen.getAllByRole("spinbutton"))
            expect(input.hasAttribute("disabled")).toBe(true);
    });

    it("keeps table rows valid and leaves native row dragging disabled", () => {
        const { container } = setup();
        const body = container.querySelector("tbody")!;
        expect([...body.children].map((element) => element.tagName)).toEqual([
            "TR",
            "TR",
            "TR",
        ]);
        for (const row of body.children) {
            expect((row as HTMLTableRowElement).draggable).toBe(false);
            for (const target of row.querySelectorAll("[data-reorder-target]"))
                expect(target.closest("td")).not.toBeNull();
        }
    });
});
