import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FilterMenu } from "./FilterMenu";

const options = [
    { value: "model", label: "The model carrying it" },
    { value: "weapons", label: "The model's weapons" },
];

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

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

    it("flips, clamps, and repositions the panel with the viewport", async () => {
        const user = userEvent.setup();
        let anchor = {
            left: 350,
            top: 320,
            right: 390,
            bottom: 350,
            width: 40,
            height: 30,
            x: 350,
            y: 320,
            toJSON: () => ({}),
        };
        const rect = vi
            .spyOn(HTMLElement.prototype, "getBoundingClientRect")
            .mockImplementation(() => anchor);
        vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
            300,
        );
        vi.stubGlobal("innerWidth", 390);
        vi.stubGlobal("innerHeight", 400);

        render(
            <FilterMenu label="Reaches" options={options} onApply={vi.fn()} />,
        );
        await user.click(screen.getByRole("button", { name: "Reaches" }));

        const panel = screen.getByRole("group", { name: "Filter: Reaches" });
        expect(panel.style.left).toBe("54px");
        expect(panel.style.top).toBe("16px");
        expect(panel.style.width).toBe("320px");
        expect(panel.style.maxHeight).toBe("300px");

        anchor = { ...anchor, left: -5, top: 20, bottom: 50, x: -5, y: 20 };
        fireEvent.resize(window);
        expect(panel.style.left).toBe("16px");
        expect(panel.style.top).toBe("54px");
        expect(panel.style.maxHeight).toBe("330px");

        anchor = { ...anchor, left: 30, top: 100, bottom: 130, x: 30, y: 100 };
        fireEvent.scroll(window);
        expect(rect).toHaveBeenCalledTimes(3);
        expect(panel.style.left).toBe("30px");
        expect(panel.style.top).toBe("134px");
        expect(panel.style.maxHeight).toBe("250px");
    });
});
