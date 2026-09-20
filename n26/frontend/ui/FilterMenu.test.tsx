import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterMenu } from "./FilterMenu";

const options = [
    { value: "model", label: "The model carrying it" },
    { value: "weapons", label: "The model's weapons" },
];

describe("filter menu", () => {
    it("supports keyboard opening, selection, dismissal, and focus return", async () => {
        const user = userEvent.setup();
        render(
            <FilterMenu label="Reaches" options={options} onApply={vi.fn()} />,
        );

        const trigger = screen.getByRole("button", { name: "Reaches" });
        trigger.focus();
        await user.keyboard("{Enter}");
        expect(
            screen.getByRole("group", { name: "Filter: Reaches" }),
        ).toBeTruthy();

        await user.tab();
        await user.tab();
        await user.tab();
        const checkbox = screen.getByRole("checkbox", {
            name: "The model carrying it",
        });
        expect(document.activeElement).toBe(checkbox);
        await user.keyboard(" ");
        expect(checkbox.getAttribute("aria-checked")).toBe("false");

        await user.keyboard("{Escape}");
        expect(document.activeElement).toBe(trigger);
        expect(
            screen.queryByRole("group", { name: "Filter: Reaches" }),
        ).toBeNull();
    });

    it("applies All, None, and one option while returning focus", async () => {
        const user = userEvent.setup();
        const onApply = vi.fn();
        render(
            <FilterMenu label="Reaches" options={options} onApply={onApply} />,
        );

        const trigger = screen.getByRole("button", { name: "Reaches" });
        await user.click(trigger);
        await user.click(
            screen.getByRole("button", {
                name: "Select only: The model's weapons",
            }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(onApply).toHaveBeenLastCalledWith(["weapons"]);
        expect(document.activeElement).toBe(trigger);

        await user.click(trigger);
        await user.click(screen.getByRole("button", { name: "None" }));
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(onApply).toHaveBeenLastCalledWith([]);

        await user.click(trigger);
        await user.click(screen.getByRole("button", { name: "All" }));
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(onApply).toHaveBeenLastCalledWith(["model", "weapons"]);
    });

    it("retains a dismissed draft and Cancel restores the opening snapshot", async () => {
        const user = userEvent.setup();
        const onApply = vi.fn();
        render(
            <FilterMenu label="Reaches" options={options} onApply={onApply} />,
        );

        const trigger = screen.getByRole("button", { name: "Reaches" });
        await user.click(trigger);
        await user.click(
            screen.getByRole("checkbox", { name: "The model carrying it" }),
        );
        fireEvent.keyDown(document, { key: "Escape" });
        expect(document.activeElement).toBe(trigger);

        await user.click(trigger);
        const checkbox = screen.getByRole("checkbox", {
            name: "The model carrying it",
        });
        expect(checkbox.getAttribute("aria-checked")).toBe("false");
        await user.click(checkbox);
        await user.click(screen.getByRole("button", { name: "Cancel" }));

        await user.click(trigger);
        expect(
            screen
                .getByRole("checkbox", { name: "The model carrying it" })
                .getAttribute("aria-checked"),
        ).toBe("false");
        expect(onApply).not.toHaveBeenCalled();
    });

    it("dismisses on an outside pointer without taking focus or applying", async () => {
        const user = userEvent.setup();
        const onApply = vi.fn();
        render(
            <div>
                <FilterMenu
                    label="Reaches"
                    options={options}
                    onApply={onApply}
                />
                <button type="button">Outside</button>
            </div>,
        );

        await user.click(screen.getByRole("button", { name: "Reaches" }));
        await user.click(screen.getByRole("button", { name: "Outside" }));
        expect(screen.queryByRole("group", { name: "Filter: Reaches" })).toBe(
            null,
        );
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Outside" }),
        );
        expect(onApply).not.toHaveBeenCalled();
    });
});
