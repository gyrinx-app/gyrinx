import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PickList, type PickListProps } from "./PickList";

function option(
    key: string,
    name: string,
    more: Partial<PickListProps["addable"][number]> = {},
) {
    return {
        key,
        name,
        detail: "",
        grantedBy: "",
        fixedBecause: "",
        picked: false,
        ...more,
    };
}

const base: PickListProps = {
    name: "skills",
    groups: [
        {
            name: "Agility",
            caption: "primary",
            options: [
                option("s:1", "Catfall", { picked: true }),
                option("s:2", "Clamber"),
                option("s:3", "Keen-eyed", {
                    picked: true,
                    grantedBy: "Scout",
                }),
            ],
        },
    ],
    addable: [option("s:9", "Iron Will"), option("s:8", "Nerves of Steel")],
    addLabel: "Add a skill",
    placeholder: "Search skills",
    grouped: true,
    addedLabel: "From other sets",
    save: "Save skills",
    resetForm: "",
};

function ticked() {
    return screen
        .getAllByRole<HTMLInputElement>("checkbox")
        .filter((box) => box.checked)
        .map((box) => box.value);
}

describe("pick list", () => {
    it("draws the list as ticked, with a grant fixed and saying why", () => {
        render(<PickList {...base} />);
        expect(
            screen.getByRole("group", { name: "Agility primary" }),
        ).toBeTruthy();
        expect(ticked()).toEqual(["s:1", "s:3"]);
        const granted = screen.getByRole<HTMLInputElement>("checkbox", {
            name: /Keen-eyed/,
        });
        expect(granted.disabled).toBe(true);
        expect(screen.getByText("From Scout")).toBeTruthy();
        expect(screen.queryByText("Iron Will")).toBeNull();
    });

    it("keeps Save off until a box changes, and off again when it changes back", async () => {
        const user = userEvent.setup();
        render(<PickList {...base} />);
        const save = screen.getByRole<HTMLButtonElement>("button", {
            name: "Save skills",
        });
        expect(save.disabled).toBe(true);
        await user.click(screen.getByRole("checkbox", { name: "Clamber" }));
        expect(save.disabled).toBe(false);
        await user.click(screen.getByRole("checkbox", { name: "Clamber" }));
        expect(save.disabled).toBe(true);
    });

    it("adds from the switcher by ticking a box under its own heading", async () => {
        const user = userEvent.setup();
        render(<PickList {...base} />);
        await user.click(screen.getByRole("button", { name: "Add a skill" }));
        expect(
            screen.getAllByRole("menuitem").map((row) => row.textContent),
        ).toEqual(["Iron Will", "Nerves of Steel"]);

        await user.click(screen.getByRole("menuitem", { name: "Iron Will" }));
        expect(screen.queryByRole("menu")).toBeNull();
        expect(ticked()).toEqual(["s:1", "s:3", "s:9"]);
        expect(
            screen.getByRole("group", { name: "From other sets" }),
        ).toBeTruthy();

        await user.click(screen.getByRole("button", { name: "Add a skill" }));
        expect(
            screen.getAllByRole("menuitem").map((row) => row.textContent),
        ).toEqual(["Nerves of Steel"]);
    });

    it("lists an added option inline when the list is not grouped", async () => {
        const user = userEvent.setup();
        render(<PickList {...base} grouped={false} addedLabel="" />);
        expect(
            screen.queryByRole("group", { name: "Agility primary" }),
        ).toBeNull();
        await user.click(screen.getByRole("button", { name: "Add a skill" }));
        await user.click(
            screen.getByRole("menuitem", { name: "Nerves of Steel" }),
        );
        expect(ticked()).toEqual(["s:1", "s:3", "s:8"]);
    });

    it("offers Reset only with a form to submit, and no buttons without Save", () => {
        const { rerender } = render(
            <PickList {...base} resetForm="reset-skills" />,
        );
        const reset = screen.getByRole<HTMLButtonElement>("button", {
            name: "Reset",
        });
        expect(reset.getAttribute("form")).toBe("reset-skills");
        expect(reset.type).toBe("submit");

        rerender(<PickList {...base} save="" />);
        expect(
            screen.queryByRole("button", { name: "Save skills" }),
        ).toBeNull();
        expect(screen.queryByRole("button", { name: "Reset" })).toBeNull();
    });

    it("offers no switcher when there is nothing to add", () => {
        render(<PickList {...base} addable={[]} />);
        expect(
            screen.queryByRole("button", { name: "Add a skill" }),
        ).toBeNull();
    });
});
