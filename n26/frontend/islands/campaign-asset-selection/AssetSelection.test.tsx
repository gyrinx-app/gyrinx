import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssetSelection, type AssetSelectionProps } from "./AssetSelection";

const options = [
    {
        value: "ruins",
        label: "Old Ruins",
        description: "Territory, income 30¢",
    },
    { value: "market", label: "Market", description: "Territory" },
];
function page(props: Partial<AssetSelectionProps> = {}) {
    const { container } = render(
        <form>
            <AssetSelection options={options} selected={[]} {...props} />
        </form>,
    );
    return () => new FormData(container.querySelector("form")!);
}

describe("Campaign asset selection", () => {
    it("adds selected assets to the optional rename table and clears them", () => {
        const data = page({
            renameLabel: "Optional: Rename territories",
            itemLabel: "Territory",
        });
        expect(screen.queryByText("Optional: Rename territories")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Select all" }));
        expect(data().getAll("asset")).toEqual(["ruins", "market"]);
        const summary = screen.getByText("Optional: Rename territories");
        expect(summary.closest("details")?.open).toBe(false);
        expect(screen.getByPlaceholderText("Old Ruins")).toBeTruthy();
        expect(screen.getByPlaceholderText("Market")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(data().getAll("asset")).toEqual([]);
        expect(data().has("name_ruins")).toBe(false);
        expect(screen.queryByText("Optional: Rename territories")).toBeNull();
    });
    it("keeps each draft name while selection changes and submits only selected names", () => {
        const data = page({ selected: ["ruins", "market"] });
        fireEvent.change(screen.getByLabelText("Rename Old Ruins"), {
            target: { value: "By the sump" },
        });
        fireEvent.change(screen.getByLabelText("Rename Market"), {
            target: { value: "Eastern market" },
        });
        expect(data().get("name_ruins")).toBe("By the sump");
        expect(data().get("name_market")).toBe("Eastern market");
        fireEvent.click(screen.getByRole("checkbox", { name: "Market" }));
        expect(data().has("name_market")).toBe(false);
        fireEvent.click(screen.getByRole("checkbox", { name: "Market" }));
        expect(data().get("name_market")).toBe("Eastern market");
    });
    it("restores submitted names and expands errors after server validation", () => {
        const data = page({
            selected: ["market"],
            options: [
                options[0],
                {
                    ...options[1],
                    name: "Eastern market",
                    nameErrors: ["Use at most 200 characters."],
                },
            ],
        });
        expect(data().get("name_market")).toBe("Eastern market");
        expect(
            screen.getByText("Optional: Rename assets").closest("details")
                ?.open,
        ).toBe(true);
        expect(
            screen.getByLabelText("Rename Market").getAttribute("aria-invalid"),
        ).toBe("true");
        expect(screen.getByText("Use at most 200 characters.")).toBeTruthy();
    });
});

it("names the asset group and associates server help and errors", () => {
    page({ label: "Select territories", invalid: true });
    const group = screen.getByRole("group", { name: "Select territories" });
    expect(group.getAttribute("aria-describedby")).toBe(
        "campaign-assets-help campaign-assets-errors",
    );
    expect(group.getAttribute("aria-invalid")).toBe("true");
});
