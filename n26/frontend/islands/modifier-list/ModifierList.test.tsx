import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ModifierList, type ModifierListProps } from "./ModifierList";

const props: ModifierListProps = {
    rows: [
        {
            pk: "1",
            label: "Grants Mounted",
            url: "/modifiers/1/",
            notes: ["the model carrying it", "adds Mounted", "on 1 carrier"],
            facets: {
                scope: "targets_model",
                effect: "ef_adds",
                carried: "carried",
                search: "grants mounted the model carrying it adds mounted on 1 carrier",
            },
        },
        {
            pk: "2",
            label: "Arms every weapon",
            url: "/modifiers/2/",
            notes: [
                "the model's weapons",
                "adds Backstab",
                "reusable — attached nowhere yet",
            ],
            facets: {
                scope: "targets_weapons",
                effect: "ef_adds",
                carried: "uncarried",
                search: "arms every weapon the model's weapons adds backstab reusable — attached nowhere yet",
            },
        },
        {
            pk: "3",
            label: "Weakens fighters",
            url: "/modifiers/3/",
            notes: [
                "the model carrying it",
                "changes a stat",
                "reusable — attached nowhere yet",
            ],
            facets: {
                scope: "targets_model",
                effect: "ef_changes_stat",
                carried: "uncarried",
                search: "weakens fighters the model carrying it changes a stat reusable — attached nowhere yet",
            },
        },
    ],
    scopeOptions: [
        { value: "targets_model", label: "The model carrying it" },
        { value: "targets_weapons", label: "The model's weapons" },
    ],
    effectOptions: [
        { value: "ef_adds", label: "Adds something" },
        { value: "ef_changes_stat", label: "Changes a stat" },
    ],
    carriedOptions: [
        { value: "carried", label: "Carried by something" },
        { value: "uncarried", label: "Carried by nothing" },
    ],
};

function setup(overrides: Partial<ModifierListProps> = {}) {
    const user = userEvent.setup();
    const view = render(<ModifierList {...props} {...overrides} />);
    return {
        user,
        ...view,
        search: screen.getByRole("searchbox", { name: "Search modifiers" }),
    };
}

describe("modifier list", () => {
    it("combines trimmed search with applied facets", async () => {
        const { user, search } = setup();
        await user.type(search, "  REUSABLE  ");
        expect(screen.getAllByRole("row")).toHaveLength(2);
        expect(screen.getByRole("status").textContent).toBe("2 of 3 modifiers");

        await user.click(screen.getByRole("button", { name: "Does" }));
        await user.click(
            screen.getByRole("button", {
                name: "Select only: Changes a stat",
            }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));

        expect(screen.getAllByRole("row")).toHaveLength(1);
        expect(
            screen.getByRole("link", { name: "Weakens fighters" }),
        ).toBeTruthy();
        expect(screen.getByRole("status").textContent).toBe("1 of 3 modifiers");
    });

    it("keeps combined facets when search is cleared", async () => {
        const { user, search } = setup();
        await user.type(search, "reusable");

        await user.click(screen.getByRole("button", { name: "Reaches" }));
        await user.click(
            screen.getByRole("button", {
                name: "Select only: The model carrying it",
            }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));

        await user.click(screen.getByRole("button", { name: "Does" }));
        await user.click(
            screen.getByRole("button", {
                name: "Select only: Changes a stat",
            }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));

        await user.click(screen.getByRole("button", { name: "Carried" }));
        await user.click(
            screen.getByRole("button", {
                name: "Select only: Carried by nothing",
            }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));

        await user.clear(search);
        expect(screen.getAllByRole("row")).toHaveLength(1);
        expect(
            screen.getByRole("link", { name: "Weakens fighters" }),
        ).toBeTruthy();
        expect(screen.getByRole("status").textContent).toBe("1 of 3 modifiers");
    });

    it("shows an empty result when a facet applies no values", async () => {
        const { user } = setup();
        await user.click(screen.getByRole("button", { name: "Carried" }));
        await user.click(screen.getByRole("button", { name: "None" }));
        await user.click(screen.getByRole("button", { name: "OK" }));

        expect(screen.getByText("No modifiers match that.")).toBeTruthy();
        expect(screen.queryAllByRole("row")).toHaveLength(0);
        expect(screen.getByRole("status").textContent).toBe("0 of 3 modifiers");
    });

    it("omits facets that cannot narrow the rows", () => {
        setup({
            scopeOptions: [props.scopeOptions[0]],
            effectOptions: [props.effectOptions[0]],
            carriedOptions: [props.carriedOptions[0]],
        });

        expect(screen.queryByRole("button", { name: "Reaches" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Does" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Carried" })).toBeNull();
    });

    it("renders server URLs and treats labels as text", () => {
        const label = '<img src=x onerror="alert(1)"> & name';
        const { container } = setup({
            rows: [{ ...props.rows[0], label }],
            scopeOptions: [props.scopeOptions[0]],
            effectOptions: [props.effectOptions[0]],
            carriedOptions: [props.carriedOptions[0]],
        });

        expect(
            screen.getByRole("link", { name: label }).getAttribute("href"),
        ).toBe("/modifiers/1/");
        expect(container.querySelector("img")).toBeNull();
    });

    it("wraps long names without squeezing the notes column", () => {
        const label = "A modifier name that needs more than one line";
        setup({
            rows: [{ ...props.rows[0], label }],
            scopeOptions: [props.scopeOptions[0]],
            effectOptions: [props.effectOptions[0]],
            carriedOptions: [props.carriedOptions[0]],
        });

        const table = screen.getByRole("table");
        const link = screen.getByRole("link", { name: label });
        const nameCell = link.closest("td");
        const notesCell = nameCell?.nextElementSibling;

        expect(table.classList.contains("table-fixed")).toBe(true);
        expect(link.classList.contains("break-words")).toBe(true);
        expect(nameCell?.classList.contains("w-2/5")).toBe(true);
        expect(notesCell?.classList.contains("w-3/5")).toBe(true);
    });
});
