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
    it("keeps batches unnamed and restores a single draft after selection changes", () => {
        const data = page({ selected: ["ruins"] });
        fireEvent.change(
            screen.getByLabelText("Name in this campaign (optional)"),
            {
                target: { value: "By the sump" },
            },
        );
        expect(data().get("name_ruins")).toBe("By the sump");
        fireEvent.click(screen.getByRole("button", { name: "Select all" }));
        expect(data().getAll("asset")).toEqual(["ruins", "market"]);
        expect(data().has("name_ruins")).toBe(false);
        expect(screen.queryByRole("textbox")).toBeNull();
        expect(
            screen.getByText(/they keep their catalogue names/),
        ).toBeTruthy();
        fireEvent.click(screen.getByRole("checkbox", { name: "Market" }));
        expect(data().get("name_ruins")).toBe("By the sump");
        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(data().getAll("asset")).toEqual([]);
    });
    it("restores submitted names and shows field errors after server validation", () => {
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
            screen
                .getByLabelText("Name in this campaign (optional)")
                .getAttribute("aria-invalid"),
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
