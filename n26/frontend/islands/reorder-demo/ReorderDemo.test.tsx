import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ReorderDemo } from "./ReorderDemo";

Element.prototype.scrollIntoView = vi.fn();

function group(id: string) {
    return document.querySelector(
        '[data-group-id="' + id + '"]',
    ) as HTMLElement;
}
const groupIds = () =>
    [...document.querySelectorAll("[data-group-id]")].map((element) =>
        element.getAttribute("data-group-id"),
    );

describe("Reorder gallery", () => {
    it("moves a whole group after confirmation while recorded positions stay fixed", () => {
        render(<ReorderDemo />);
        const handle = screen.getByRole("button", {
            name: "Move Planned group",
        });
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "End" });
        expect(groupIds()).toEqual(["recorded", "planned", "empty"]);
        fireEvent.keyDown(handle, { key: "Enter" });
        expect(groupIds()).toEqual(["recorded", "empty", "planned"]);
        expect(
            within(group("planned")).getByText("Market visit"),
        ).not.toBeNull();
        expect(
            screen.queryByRole("button", { name: "Move Recorded group" }),
        ).toBeNull();
    });

    it("moves an entry into an empty group and retains its note", () => {
        render(<ReorderDemo />);
        const note = screen.getByRole("textbox", {
            name: "Note for Market visit",
        });
        fireEvent.change(note, { target: { value: "An edited note" } });
        const handle = screen.getByRole("button", {
            name: "Move Market visit",
        });
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "End" });
        expect(
            within(group("planned")).getByText("Market visit"),
        ).not.toBeNull();
        fireEvent.keyDown(handle, { key: "Enter" });
        expect(within(group("empty")).getByText("Market visit")).not.toBeNull();
        expect(
            (
                within(group("empty")).getByRole("textbox", {
                    name: "Note for Market visit",
                }) as HTMLInputElement
            ).value,
        ).toBe("An edited note");
        expect(within(group("planned")).queryByText("Market visit")).toBeNull();
    });

    it("cancels a group preview and keeps nested controls usable", () => {
        render(<ReorderDemo />);
        const handle = screen.getByRole("button", {
            name: "Move Planned group",
        });
        handle.focus();
        fireEvent.keyDown(handle, { key: " " });
        fireEvent.keyDown(handle, { key: "End" });
        fireEvent.keyDown(handle, { key: "Escape" });
        expect(groupIds()).toEqual(["recorded", "planned", "empty"]);
        fireEvent.change(
            screen.getByRole("textbox", { name: "Note for Recorded visit" }),
            { target: { value: "Recorded note" } },
        );
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Note for Recorded visit",
                }) as HTMLInputElement
            ).value,
        ).toBe("Recorded note");
        expect(screen.queryByRole("button", { pressed: true })).toBeNull();
    });

    it("disables move handles in read-only mode and can reset the local example", () => {
        render(<ReorderDemo />);
        expect(screen.getByText("Read-only")).not.toBeNull();
        fireEvent.click(screen.getByRole("switch", { name: "Read-only" }));
        for (const handle of screen.getAllByRole("button", { name: /^Move / }))
            expect(handle.hasAttribute("disabled")).toBe(true);
        expect(
            screen
                .getByRole("textbox", { name: "Note for Market visit" })
                .hasAttribute("readonly"),
        ).toBe(true);
        expect(
            screen
                .getByRole("button", { name: "Reset" })
                .hasAttribute("disabled"),
        ).toBe(false);
        fireEvent.click(screen.getByRole("switch", { name: "Read-only" }));
        expect(
            screen
                .getByRole("button", { name: "Move Market visit" })
                .hasAttribute("disabled"),
        ).toBe(false);
    });
});
