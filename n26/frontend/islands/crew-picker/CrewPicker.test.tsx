import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CrewPicker, type CrewModel } from "./CrewPicker";

function model(id: string, name: string, role = "out"): CrewModel {
    return {
        id,
        name,
        profile: "Gunner",
        fullRating: 120,
        savedSource: "",
        search: `${name} gunner`.toLowerCase(),
        warning: "",
        mayOverride: false,
        available: true,
        role: {
            name: `role_${id}`,
            id: `id_role_${id}`,
            value: role,
            errors: [],
            choices: [
                { value: "out", label: "Not selected" },
                { value: "starting", label: "Starting crew" },
                { value: "reserve", label: "Reinforcements" },
            ],
        },
        card: {
            name: `card_${id}`,
            id: `id_card_${id}`,
            value: "saved:old",
            errors: [],
            choices: [
                { value: "saved:old", label: "Long range — saved selection" },
                { value: "long", label: "Long range" },
                { value: "short", label: "Close range" },
            ],
        },
        override: {
            name: `override_${id}`,
            id: `id_override_${id}`,
            value: false,
            errors: [],
        },
    };
}

function setup(models = [model("a", "Mara", "reserve"), model("b", "Nell")]) {
    const submit = vi.fn((event) => event.preventDefault());
    const rendered = render(
        <form onSubmit={submit}>
            <input type="hidden" name="revision" value="2" />
            <button type="submit" name="action" value="draw">
                Draw and save draft
            </button>
            <CrewPicker models={models} battleUrl="/battle/" revision={2} />
        </form>,
    );
    const form = rendered.container.querySelector("form")!;
    return {
        ...rendered,
        form,
        data: () => new FormData(form),
        submit,
        user: userEvent.setup(),
    };
}

describe("CrewPicker", () => {
    it.each(["deleted", ""])(
        "makes an unavailable equipment selection explicit and replaceable (%s)",
        async (invalid) => {
            const changed = model("a", "Mara", "starting");
            changed.card.value = invalid;
            changed.card.choices = [{ value: "full", label: "Full equipment" }];
            changed.card.errors = ["Select a valid choice."];
            const { user, data } = setup([changed]);
            const select = screen.getByRole<HTMLSelectElement>("combobox", {
                name: "Equipment set for Mara",
            });
            expect(select.selectedOptions[0].textContent).toBe(
                "Select an equipment set",
            );
            expect(data().get("card_a")).toBe(invalid);
            await user.selectOptions(select, "full");
            expect(select.selectedOptions[0].textContent).toBe(
                "Full equipment",
            );
            expect(data().get("card_a")).toBe("full");
        },
    );

    it("uses a header checkbox with nested choices and live selection counts", async () => {
        const { user, data } = setup();
        expect(
            screen
                .getByRole("combobox", { name: "Crew for Nell" })
                .hasAttribute("disabled"),
        ).toBe(true);
        expect(data().get("role_b")).toBe("out");
        expect(screen.getByText("1 model")).toBeTruthy();
        await user.click(screen.getByRole("checkbox", { name: "Select Nell" }));
        expect(data().get("role_b")).toBe("starting");
        expect(screen.getByText("2 models")).toBeTruthy();
        expect(
            screen.getByText("1 starting · 1 reinforcement · Revision 2"),
        ).toBeTruthy();
        expect(
            screen
                .getByRole("combobox", { name: "Crew for Nell" })
                .hasAttribute("disabled"),
        ).toBe(false);
    });

    it("keeps role and equipment choices when a model is unticked and re-ticked", async () => {
        const { user, data } = setup();
        await user.selectOptions(
            screen.getByRole("combobox", { name: "Equipment set for Mara" }),
            "short",
        );
        await user.click(screen.getByRole("checkbox", { name: "Select Mara" }));
        expect(data().get("role_a")).toBe("out");
        expect(data().get("card_a")).toBe("short");
        await user.click(screen.getByRole("checkbox", { name: "Select Mara" }));
        expect(data().get("role_a")).toBe("reserve");
        expect(
            screen.getByRole<HTMLSelectElement>("combobox", {
                name: "Equipment set for Mara",
            }).value,
        ).toBe("short");
    });

    it("submits every canonical field once even when models are hidden by search", async () => {
        const { user, data } = setup();
        await user.type(
            screen.getByRole("searchbox", { name: "Find a model" }),
            "Nell",
        );
        expect(
            screen.queryByRole("checkbox", { name: "Select Mara" }),
        ).toBeNull();
        expect(data().getAll("role_a")).toEqual(["reserve"]);
        expect(data().getAll("card_a")).toEqual(["saved:old"]);
        expect(data().getAll("role_b")).toEqual(["out"]);
        expect(data().getAll("card_b")).toEqual(["saved:old"]);
        await user.click(screen.getByRole("checkbox", { name: "Select Nell" }));
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(
            screen.getByRole<HTMLInputElement>("checkbox", {
                name: "Select Mara",
            }).checked,
        ).toBe(true);
        expect(
            screen.getByRole<HTMLInputElement>("checkbox", {
                name: "Select Nell",
            }).checked,
        ).toBe(true);
    });

    it("preserves saved selections until the equipment set is explicitly changed", async () => {
        const { user, data } = setup();
        expect(data().get("card_a")).toBe("saved:old");
        await user.selectOptions(
            screen.getByRole("combobox", { name: "Equipment set for Mara" }),
            "long",
        );
        expect(data().get("card_a")).toBe("long");
    });

    it("opts into an unavailable model with its single selection checkbox", async () => {
        const recovering = model("a", "Mara");
        recovering.warning = "In Recovery. Usually unavailable for selection.";
        recovering.mayOverride = true;
        recovering.override.errors = [
            "Allow this model for this battle or remove it from the crew.",
        ];
        const { user, data } = setup([recovering]);
        expect(screen.getByRole("note").closest("[inert]")).toBeNull();
        expect(screen.getByRole("alert").textContent).toContain(
            "Allow this model",
        );
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Select Mara",
        });
        expect(screen.getAllByRole("checkbox")).toHaveLength(1);
        const notice = screen.getByRole("note");
        expect(notice.textContent).toBe(recovering.warning);
        expect(checkbox.getAttribute("aria-describedby")).toContain(notice.id);
        expect(notice.parentElement).toBe(
            checkbox.closest("label")!.parentElement,
        );
        expect(checkbox.disabled).toBe(false);
        expect(checkbox.checked).toBe(false);
        expect(data().get("role_a")).toBe("out");
        expect(data().get("override_a")).toBeNull();
        await user.click(checkbox);
        expect(data().getAll("override_a")).toEqual(["on"]);
        expect(data().get("role_a")).toBe("starting");
    });

    it("clears the override when deselected and restores choices when selected again", async () => {
        const recovering = model("a", "Mara", "reserve");
        recovering.warning = "In Recovery. Usually unavailable for selection.";
        recovering.mayOverride = true;
        recovering.override.value = true;
        const { user, data } = setup([recovering]);
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Select Mara",
        });
        const equipment = screen.getByRole<HTMLSelectElement>("combobox", {
            name: "Equipment set for Mara",
        });
        await user.selectOptions(equipment, "short");
        await user.click(checkbox);
        expect(checkbox.checked).toBe(false);
        expect(checkbox.disabled).toBe(false);
        expect(equipment.disabled).toBe(true);
        expect(data().get("role_a")).toBe("out");
        expect(data().get("override_a")).toBeNull();
        expect(data().get("card_a")).toBe("short");
        expect(screen.getByText("0 models")).toBeTruthy();
        await user.click(checkbox);
        expect(checkbox.checked).toBe(true);
        expect(equipment.disabled).toBe(false);
        expect(equipment.value).toBe("short");
        expect(data().get("role_a")).toBe("reserve");
        expect(data().get("override_a")).toBe("on");
        expect(screen.getByText("1 model")).toBeTruthy();
    });

    it("requires a fresh selection for a saved model whose status has since changed", async () => {
        const recovering = model("a", "Mara", "starting");
        recovering.warning = "In Recovery. Usually unavailable for selection.";
        recovering.mayOverride = true;
        const { user, data } = setup([recovering]);
        expect(data().get("role_a")).toBe("out");
        expect(data().get("card_a")).toBe("saved:old");
        expect(screen.getByText("0 models")).toBeTruthy();
        await user.click(
            screen.getByRole("checkbox", {
                name: "Select Mara",
            }),
        );
        expect(data().get("role_a")).toBe("starting");
        expect(data().get("card_a")).toBe("saved:old");
        expect(data().get("override_a")).toBe("on");
        expect(screen.getByText("1 model")).toBeTruthy();
    });

    it("preserves the selection override when the model is hidden by search", async () => {
        const recovering = model("a", "Mara");
        recovering.warning = "In Recovery. Usually unavailable for selection.";
        recovering.mayOverride = true;
        const { user, data } = setup([recovering, model("b", "Nell")]);
        await user.click(screen.getByRole("checkbox", { name: "Select Mara" }));
        await user.type(
            screen.getByRole("searchbox", { name: "Find a model" }),
            "Nell",
        );
        expect(data().getAll("role_a")).toEqual(["starting"]);
        expect(data().getAll("override_a")).toEqual(["on"]);
        expect(data().get("override_b")).toBeNull();
    });

    it("lets an unavailable saved model be removed but not selected again", async () => {
        const missing = model("a", "Mara", "starting");
        missing.available = false;
        missing.warning =
            "This model is no longer available. Remove it from the crew.";
        missing.role.errors = [missing.warning];
        const { user, data } = setup([missing]);
        const checkbox = screen.getByRole<HTMLInputElement>("checkbox", {
            name: "Select Mara",
        });
        expect(checkbox.disabled).toBe(false);
        await user.click(checkbox);
        expect(checkbox.disabled).toBe(true);
        expect(data().get("role_a")).toBe("out");
        expect(screen.getByRole("alert").closest("[inert]")).toBeNull();
    });

    it("keeps native draw, draft and save submission actions", async () => {
        const { user, form, submit } = setup();
        for (const [label, action] of [
            ["Draw and save draft", "draw"],
            ["Save draft", "draft"],
            ["Save crew", "save"],
        ]) {
            const button = screen.getByRole<HTMLButtonElement>("button", {
                name: label,
            });
            expect(new FormData(form, button).get("action")).toBe(action);
            await user.click(button);
        }
        expect(submit).toHaveBeenCalledTimes(3);
        expect(
            screen
                .getByRole<HTMLAnchorElement>("link", { name: "Back" })
                .getAttribute("href"),
        ).toBe("/battle/");
    });

    it("does not submit the form when Enter is pressed in search", () => {
        const { submit } = setup();
        fireEvent.keyDown(
            screen.getByRole("searchbox", { name: "Find a model" }),
            { key: "Enter" },
        );
        expect(submit).not.toHaveBeenCalled();
    });

    it("shows no-match and empty-roster states without discarding form values", async () => {
        const { user, data, unmount } = setup();
        await user.type(
            screen.getByRole("searchbox", { name: "Find a model" }),
            "missing",
        );
        expect(screen.getByText("No models match your search.")).toBeTruthy();
        expect(data().get("role_a")).toBe("reserve");
        unmount();
        setup([]);
        expect(screen.getByText("No models in this gang yet.")).toBeTruthy();
        expect(screen.getByText("0 models")).toBeTruthy();
    });
});
