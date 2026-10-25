import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import cotton from "../../generated/cotton.json";
import { FilterMenuIsland } from "./FilterMenuIsland";

const options = [
    { value: "house", label: "House" },
    { value: "outlaw", label: "Outlaw" },
];

const props = {
    label: "Category",
    name: "category",
    options,
    selected: [] as string[],
    selectAll: true,
    applyLabel: "OK",
    cancelLabel: "Cancel",
    size: "sm" as const,
    align: "start" as const,
    width: 320,
};

describe("filter menu island", () => {
    it("posts the ticked values and tells the page when OK is pressed", async () => {
        const user = userEvent.setup();
        const applied: Array<{ name: string; values: string[] }> = [];
        const { container } = render(
            <form>
                <div data-parent>
                    <FilterMenuIsland {...props} />
                </div>
            </form>,
        );
        container
            .querySelector("[data-parent]")!
            .addEventListener("filter-apply", (event) => {
                applied.push((event as CustomEvent).detail);
            });
        const form = container.querySelector("form")!;
        expect(new FormData(form).getAll("category")).toEqual([
            "house",
            "outlaw",
        ]);

        await user.click(screen.getByRole("button", { name: "Category" }));
        await user.click(screen.getByRole("checkbox", { name: "House" }));
        expect(new FormData(form).getAll("category")).toEqual(["outlaw"]);

        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(applied).toEqual([{ name: "category", values: ["outlaw"] }]);
        expect(new FormData(form).getAll("category")).toEqual(["outlaw"]);
    });

    it("restores every tick when that name is reset, and ignores another name", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <FilterMenuIsland {...props} />
            </form>,
        );
        const form = container.querySelector("form")!;
        await user.click(screen.getByRole("button", { name: "Category" }));
        await user.click(screen.getByRole("button", { name: "None" }));
        expect(new FormData(form).getAll("category")).toEqual([]);

        act(() => {
            window.dispatchEvent(
                new CustomEvent("filter-reset", { detail: { name: "house" } }),
            );
        });
        expect(new FormData(form).getAll("category")).toEqual([]);

        act(() => {
            window.dispatchEvent(
                new CustomEvent("filter-reset", {
                    detail: { name: "category" },
                }),
            );
        });
        expect(new FormData(form).getAll("category")).toEqual([
            "house",
            "outlaw",
        ]);
    });

    it("starts empty when select all is off, and uses the narrow trigger", () => {
        render(
            <FilterMenuIsland
                {...props}
                selectAll={false}
                size="xs"
                applyLabel="Update"
                cancelLabel="Reset"
            />,
        );
        const trigger = screen.getByRole("button", { name: "Category0" });
        expect(trigger.className).toContain(cotton.filterMenu.triggerXs);
        fireEvent.click(trigger);
        expect(screen.getByRole("button", { name: "Update" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Reset" })).toBeTruthy();
        expect(
            screen
                .getByRole("checkbox", { name: "House" })
                .getAttribute("aria-checked"),
        ).toBe("false");
    });
});
