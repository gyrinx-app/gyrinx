import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AssetSelection } from "./AssetSelection";

const options = [
    {
        value: "ruins",
        label: "Old Ruins",
        description: "Territory, income 30¢",
    },
    { value: "market", label: "Market", description: "Territory" },
];
function page(selected: string[] = [], name = "") {
    const { container } = render(
        <form>
            <AssetSelection
                options={options}
                selected={selected}
                name={name}
                nameErrors={[]}
            />
        </form>,
    );
    return () => new FormData(container.querySelector("form")!);
}

describe("Campaign asset selection", () => {
    it("selects and clears a batch through native form values", () => {
        const data = page();
        fireEvent.click(screen.getByRole("button", { name: "Select all" }));
        expect(data().getAll("asset")).toEqual(["ruins", "market"]);
        expect(
            (screen.getByLabelText("Name in this campaign") as HTMLInputElement)
                .disabled,
        ).toBe(true);
        expect(data().has("name")).toBe(false);
        fireEvent.click(screen.getByRole("button", { name: "Clear" }));
        expect(data().getAll("asset")).toEqual([]);
    });
    it("keeps an optional name only while a single asset is selected", () => {
        const data = page();
        fireEvent.click(screen.getByRole("checkbox", { name: "Old Ruins" }));
        fireEvent.change(screen.getByLabelText("Name in this campaign"), {
            target: { value: "By the sump" },
        });
        expect(data().getAll("asset")).toEqual(["ruins"]);
        expect(data().get("name")).toBe("By the sump");
        fireEvent.click(screen.getByRole("checkbox", { name: "Market" }));
        expect(data().has("name")).toBe(false);
        fireEvent.click(screen.getByRole("checkbox", { name: "Market" }));
        expect(data().get("name")).toBe("By the sump");
    });
    it("restores a submitted selection and name after server validation", () => {
        const data = page(["market"], "Eastern market");
        expect(data().getAll("asset")).toEqual(["market"]);
        expect(data().get("name")).toBe("Eastern market");
    });
});

it("names the asset group and associates server help and errors", () => {
    render(
        <AssetSelection
            options={options}
            selected={[]}
            name=""
            nameErrors={[]}
            label="Select territories"
            invalid
        />,
    );
    const group = screen.getByRole("group", { name: "Select territories" });
    expect(group.getAttribute("aria-describedby")).toBe(
        "campaign-assets-help campaign-assets-errors",
    );
    expect(group.getAttribute("aria-invalid")).toBe("true");
});
