import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ModifierNaming, type ModifierNamingProps } from "./ModifierNaming";

const props: ModifierNamingProps = {
    carrier: "Berserker",
    name: {
        htmlName: "name",
        label: "Name",
        helpText: "Blank writes the modifier's own sentence as its name.",
        value: "",
        errors: [],
    },
    reusable: {
        htmlName: "make_reusable",
        label: "Make reusable",
        helpText: "Name this modifier generically.",
        value: false,
        errors: [],
    },
};

function setup(overrides: Partial<ModifierNamingProps> = {}) {
    const user = userEvent.setup();
    const applied = { ...props, ...overrides };
    const view = render(
        <form>
            <ModifierNaming {...applied} />
        </form>,
    );
    return {
        user,
        ...view,
        form: view.container.querySelector("form")!,
        name: screen.getByRole("textbox", { name: applied.name.label }),
        reusable: screen.getByRole("switch", { name: "Make reusable" }),
    };
}

describe("modifier naming", () => {
    it("previews the submitted name and trims it as Django will", async () => {
        const { user, name } = setup();
        expect(screen.getByText("Berserker: what it does")).toBeTruthy();

        await user.type(name, "  Ash wastes rider  ");
        expect(screen.getByText("Ash wastes rider")).toBeTruthy();
        expect((name as HTMLInputElement).value).toBe("  Ash wastes rider  ");

        await user.clear(name);
        await user.type(name, "   ");
        expect(screen.getByText("Berserker: what it does")).toBeTruthy();
    });

    it("keeps the Django field names and only submits an enabled switch", async () => {
        const { user, form, name, reusable } = setup();
        await user.type(name, "Mounted");
        expect(new FormData(form).get("name")).toBe("Mounted");
        expect(new FormData(form).has("make_reusable")).toBe(false);

        await user.click(reusable);
        expect(new FormData(form).get("make_reusable")).toBe("on");
        expect(screen.getByText("Mounted")).toBeTruthy();

        await user.clear(name);
        expect(screen.getByText("what it does")).toBeTruthy();
        await user.click(reusable);
        expect(new FormData(form).has("make_reusable")).toBe(false);
        expect(screen.getByText("Berserker: what it does")).toBeTruthy();
    });

    it("restores carried values and associates server errors", () => {
        const label = '<img src=x onerror="alert(1)">';
        const { container, form, name } = setup({
            name: {
                ...props.name,
                label,
                value: "Carried name",
                errors: ["A modifier with that name already exists."],
            },
            reusable: { ...props.reusable, value: true },
        });

        expect((name as HTMLInputElement).value).toBe("Carried name");
        expect(new FormData(form).get("make_reusable")).toBe("on");
        expect(name.getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByText("A modifier with that name already exists."),
        ).toBeTruthy();
        expect(screen.getByText(label)).toBeTruthy();
        expect(container.querySelector("img")).toBeNull();
    });
});
