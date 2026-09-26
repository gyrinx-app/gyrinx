import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { FilterSelect, type FilterSelectProps } from "./FilterSelect";

const options: FilterSelectProps["options"] = [
    {
        value: "",
        label: "Choose one",
        selected: true,
        disabled: true,
    },
    { value: "alpha", label: "Alpha", selected: false, disabled: false },
    { value: "beta", label: "Beta", selected: false, disabled: false },
    { value: "hidden", label: "Hidden", selected: false, disabled: true },
];

const props: FilterSelectProps = {
    name: "thing",
    id: "id_thing",
    multiple: false,
    required: true,
    disabled: false,
    attrs: {
        "data-union-of": "thing",
        "data-union-member": "skill",
    },
    options,
    placeholder: "Type to filter",
    empty: "No matches",
};

function setup(overrides: Partial<FilterSelectProps> = {}) {
    const applied = { ...props, ...overrides };
    const onSubmit = vi.fn((event: FormEvent<HTMLFormElement>) =>
        event.preventDefault(),
    );
    const rendered = render(
        <form onSubmit={onSubmit}>
            <label htmlFor={applied.id}>Thing</label>
            <FilterSelect {...applied} />
        </form>,
    );
    return {
        ...rendered,
        form: rendered.container.querySelector("form")!,
        select: rendered.container.querySelector<HTMLSelectElement>(
            `select[name="${applied.name}"]`,
        )!,
        trigger: screen.getByRole("button", { name: "Thing" }),
        onSubmit,
        user: userEvent.setup(),
    };
}

describe("FilterSelect", () => {
    it("keeps the native select's form and union contracts", async () => {
        const { form, select, trigger, user } = setup();
        const changed = vi.fn();
        select.addEventListener("change", changed);

        expect(trigger.id).toBe("id_thing");
        expect(select.id).toBe("");
        expect(select.required).toBe(true);
        expect(select.dataset.unionOf).toBe("thing");
        expect(select.dataset.unionMember).toBe("skill");

        await user.click(trigger);
        await user.click(screen.getByRole("option", { name: "Beta" }));

        expect(new FormData(form).get("thing")).toBe("beta");
        expect(changed).toHaveBeenCalledOnce();
        expect(trigger.textContent).toContain("Beta");
        expect(screen.queryByRole("listbox")).toBeNull();
    });

    it("posts every selected value from a multiple select", async () => {
        const { form, trigger, user } = setup({
            multiple: true,
            required: false,
            options: options.map((option) => ({
                ...option,
                selected: option.value === "alpha",
            })),
        });

        expect(trigger.textContent).toContain("Alpha");
        await user.click(trigger);
        await user.click(screen.getByRole("option", { name: "Beta" }));

        expect(new FormData(form).getAll("thing")).toEqual(["alpha", "beta"]);
        expect(screen.getByRole("listbox")).toBeTruthy();
    });

    it("shows and posts an existing single selection", () => {
        const { form, trigger } = setup({
            options: options.map((option) => ({
                ...option,
                selected: option.value === "alpha",
            })),
        });

        expect(trigger.textContent).toContain("Alpha");
        expect(new FormData(form).get("thing")).toBe("alpha");
    });

    it("filters enabled options and shows the empty state", async () => {
        const { trigger, user } = setup();
        await user.click(trigger);
        const search = screen.getByRole("combobox");
        await waitFor(() => expect(document.activeElement).toBe(search));

        expect(screen.queryByRole("option", { name: "Hidden" })).toBeNull();
        await user.type(search, "bet");
        expect(
            screen.getAllByRole("option").map((row) => row.textContent),
        ).toEqual(["Beta"]);

        await user.clear(search);
        await user.type(search, "missing");
        expect(screen.getByText("No matches")).toBeTruthy();
    });

    it("keeps keyboard selection inside the picker", async () => {
        const { form, trigger, onSubmit, user } = setup();
        await user.click(trigger);
        const search = screen.getByRole("combobox");
        await user.type(search, "bet");
        await user.keyboard("{ArrowDown}{Enter}");

        expect(new FormData(form).get("thing")).toBe("beta");
        expect(onSubmit).not.toHaveBeenCalled();
        expect(document.activeElement).toBe(trigger);

        await user.click(trigger);
        const reopened = screen.getByRole("combobox");
        await user.type(reopened, "alp");
        await user.keyboard("{Escape}");
        expect(screen.getByRole("listbox")).toBeTruthy();
        expect((reopened as HTMLInputElement).value).toBe("");
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("listbox")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("closes when the pointer leaves the picker", async () => {
        const { trigger, user } = setup();
        await user.click(trigger);
        expect(screen.getByRole("listbox")).toBeTruthy();

        fireEvent.click(document.body);
        expect(screen.queryByRole("listbox")).toBeNull();
    });
});
