import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import cotton from "../generated/cotton.json";
import {
    Button,
    ButtonLink,
    Callout,
    CheckboxCard,
    Field,
    FormActions,
    Input,
    NativeSelect,
    Switch,
} from "./index";

function setupCard(initialChecked = false, disabled = false) {
    const changed = vi.fn();
    const nestedClicked = vi.fn();
    function Example() {
        const [checked, setChecked] = useState(initialChecked);
        return (
            <CheckboxCard
                checked={checked}
                onCheckedChange={(value) => {
                    changed(value);
                    setChecked(value);
                }}
                label="Mara"
                description="Leader"
                meta={<span>240¢</span>}
                disabled={disabled}
            >
                <Field label="Model card" htmlFor="model-card">
                    <NativeSelect name="model_card" defaultValue="ranged">
                        <option value="ranged">Long range</option>
                        <option value="close">Close quarters</option>
                    </NativeSelect>
                </Field>
                <Button onClick={nestedClicked}>View card</Button>
            </CheckboxCard>
        );
    }
    const user = userEvent.setup();
    const view = render(<Example />);
    return {
        user,
        changed,
        nestedClicked,
        ...view,
        checkbox: screen.getByRole("checkbox", {
            name: "Mara",
        }) as HTMLInputElement,
    };
}

describe("checkbox card", () => {
    it("keeps notices and errors inside the card and readable when unselected", () => {
        const { container } = render(
            <CheckboxCard
                checked={false}
                onCheckedChange={() => {}}
                label="Mara"
                description="Leader"
                checkboxDescribedBy="recovery-note"
                notice={<Callout id="recovery-note">In recovery.</Callout>}
                errors={<p role="alert">Select the model again.</p>}
            >
                <input aria-label="Nested value" />
            </CheckboxCard>,
        );
        const note = screen.getByRole("note");
        const error = screen.getByRole("alert");
        expect(note.parentElement).toBe(container.firstElementChild);
        expect(error.parentElement).toBe(container.firstElementChild);
        expect(note.closest("[inert]")).toBeNull();
        expect(error.closest("[inert]")).toBeNull();
        expect(note.className).toContain(cotton.callout.root);
        expect(
            screen.getByRole("checkbox").getAttribute("aria-describedby"),
        ).toContain("recovery-note");
        expect(
            screen.getByLabelText("Nested value").closest("[inert]"),
        ).not.toBeNull();
    });

    it("uses the label as its name and the description separately", () => {
        const { checkbox } = setupCard();
        expect(checkbox.checked).toBe(false);
        expect(
            document.getElementById(checkbox.getAttribute("aria-labelledby")!)
                ?.textContent,
        ).toBe("Mara");
        expect(
            document.getElementById(checkbox.getAttribute("aria-describedby")!)
                ?.textContent,
        ).toBe("Leader");
        expect(checkbox.closest("label")?.textContent).toContain("240¢");
    });

    it("changes selection from the header but not nested controls or blank card space", async () => {
        const { user, checkbox, changed, nestedClicked, container } =
            setupCard();
        const root = container.firstElementChild!;
        expect(root.className).toContain(
            cotton.checkboxCard.selection.unchecked,
        );
        await user.click(screen.getByText("Mara"));
        expect(checkbox.checked).toBe(true);
        expect(changed).toHaveBeenCalledExactlyOnceWith(true);
        expect(root.className).toContain(cotton.checkboxCard.selection.checked);

        await user.selectOptions(screen.getByRole("combobox"), "close");
        await user.click(screen.getByRole("button", { name: "View card" }));
        await user.click(root);
        expect(nestedClicked).toHaveBeenCalledOnce();
        expect(changed).toHaveBeenCalledTimes(1);
        expect(checkbox.checked).toBe(true);
    });

    it("makes nested controls inert and dimmed without clearing their values", async () => {
        const { user, checkbox, container } = setupCard(true);
        const select = screen.getByRole("combobox") as HTMLSelectElement;
        const body = select.closest(
            `.${cotton.checkboxCard.body.split(" ")[0]}`,
        )!;
        expect(body.hasAttribute("inert")).toBe(false);
        await user.selectOptions(select, "close");
        await user.click(checkbox);
        expect(checkbox.checked).toBe(false);
        expect(body.hasAttribute("inert")).toBe(true);
        expect(body.className).toContain(cotton.checkboxCard.nested.unchecked);
        expect(select.value).toBe("close");
        expect(select.disabled).toBe(false);
        expect(container.querySelectorAll("select")).toHaveLength(1);
        await user.click(checkbox);
        expect(body.hasAttribute("inert")).toBe(false);
        expect(select.value).toBe("close");
    });

    it("supports keyboard selection and gives a disabled card no editable body", async () => {
        const user = userEvent.setup();
        const changed = vi.fn();
        const { rerender } = render(
            <CheckboxCard
                checked={false}
                onCheckedChange={changed}
                label="Nell"
            >
                <input aria-label="Nested value" />
            </CheckboxCard>,
        );
        const checkbox = screen.getByRole("checkbox", { name: "Nell" });
        await user.tab();
        expect(document.activeElement).toBe(checkbox);
        await user.keyboard(" ");
        expect(changed).toHaveBeenCalledExactlyOnceWith(true);
        rerender(
            <CheckboxCard
                checked
                disabled
                onCheckedChange={changed}
                label="Nell"
            >
                <input aria-label="Nested value" />
            </CheckboxCard>,
        );
        expect((checkbox as HTMLInputElement).disabled).toBe(true);
        expect(
            screen.getByLabelText("Nested value").closest("[inert]"),
        ).not.toBeNull();
        await user.click(screen.getByText("Nell"));
        expect(changed).toHaveBeenCalledTimes(1);
    });

    it("supports an explicit checkbox name without rendering labels as HTML", () => {
        const label = '<img src=x onerror="alert(1)">';
        const { container } = render(
            <CheckboxCard
                checked={false}
                onCheckedChange={() => {}}
                label={label}
                checkboxLabel="Select Mara for the crew"
            />,
        );
        expect(
            screen.getByRole("checkbox", { name: "Select Mara for the crew" }),
        ).toBeTruthy();
        expect(screen.getByText(label)).toBeTruthy();
        expect(container.querySelector("img")).toBeNull();
        expect(container.querySelector("[inert]")).toBeNull();
    });
});

describe("form controls", () => {
    it("associates labels and errors while preserving an existing description", () => {
        const { rerender } = render(
            <Field label="Crew role" htmlFor="role" errors={["Select a role."]}>
                <p id="role-help">Choose where this model starts.</p>
                <NativeSelect
                    aria-describedby="role-help"
                    defaultValue="starting"
                >
                    <option value="starting">Starting crew</option>
                </NativeSelect>
            </Field>,
        );
        const select = screen.getByRole("combobox", { name: "Crew role" });
        expect(select.id).toBe("role");
        expect(select.getAttribute("aria-invalid")).toBe("true");
        const descriptions = select
            .getAttribute("aria-describedby")!
            .split(" ");
        expect(descriptions[0]).toBe("role-help");
        expect(document.getElementById(descriptions[1])?.textContent).toBe(
            "Select a role.",
        );
        expect(screen.getByText("Select a role.").className).toBe(
            cotton.field.error,
        );
        rerender(
            <Field label="Crew role" htmlFor="role">
                <p id="role-help">Choose where this model starts.</p>
                <NativeSelect
                    aria-describedby="role-help"
                    defaultValue="starting"
                >
                    <option value="starting">Starting crew</option>
                </NativeSelect>
            </Field>,
        );
        const currentSelect = screen.getByRole("combobox", {
            name: "Crew role",
        });
        expect(currentSelect).toBe(select);
        expect(currentSelect.getAttribute("aria-invalid")).toBeNull();
        expect(currentSelect.getAttribute("aria-describedby")).toBe(
            "role-help",
        );
        expect(document.getElementById(descriptions[1])).toBeNull();
    });

    it("keeps native select values, events, disabled state and the Cotton chevron", async () => {
        const changed = vi.fn();
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <NativeSelect
                    name="role"
                    aria-label="Crew role"
                    defaultValue="starting"
                    onChange={changed}
                    required
                    className="test-select"
                >
                    <option value="starting">Starting crew</option>
                    <option value="reserve">Reinforcements</option>
                </NativeSelect>
                <NativeSelect
                    name="ignored"
                    aria-label="Unavailable card"
                    disabled
                >
                    <option value="full">Full equipment</option>
                </NativeSelect>
            </form>,
        );
        const select = screen.getByRole("combobox", {
            name: "Crew role",
        }) as HTMLSelectElement;
        await user.selectOptions(select, "reserve");
        expect(changed).toHaveBeenCalledOnce();
        const values = new FormData(container.querySelector("form")!);
        expect(values.get("role")).toBe("reserve");
        expect(values.has("ignored")).toBe(false);
        expect(select.required).toBe(true);
        expect(select.className).toContain(cotton.nativeSelect.className);
        expect(select.classList.contains("test-select")).toBe(true);
        expect(select.style.backgroundImage).toContain("data:image/svg+xml");
        expect(select.style.backgroundSize).toBe(
            cotton.nativeSelect.style.backgroundSize,
        );
    });

    it("associates a Cotton text input with trailing help and errors", () => {
        render(
            <Field
                label="Name"
                htmlFor="name"
                description="Leave blank to use the generated name."
                errors={["Use a shorter name."]}
            >
                <Input id="name" name="name" defaultValue="Berserker" />
            </Field>,
        );

        const input = screen.getByRole("textbox", {
            name: "Name",
        }) as HTMLInputElement;
        expect(input.value).toBe("Berserker");
        expect(input.className).toContain(cotton.input.control);
        const descriptions = input.getAttribute("aria-describedby")!.split(" ");
        expect(document.getElementById(descriptions[0])?.textContent).toBe(
            "Leave blank to use the generated name.",
        );
        expect(document.getElementById(descriptions[1])?.textContent).toBe(
            "Use a shorter name.",
        );
    });

    it("submits the Cotton switch only while it is on", async () => {
        const user = userEvent.setup();

        function Example() {
            const [checked, setChecked] = useState(false);
            return (
                <form>
                    <Field
                        label="Make reusable"
                        htmlFor="reusable"
                        description="Use a generic name."
                        variant="toggle"
                    >
                        <Switch
                            id="reusable"
                            name="make_reusable"
                            checked={checked}
                            onCheckedChange={setChecked}
                            label="Make reusable"
                        />
                    </Field>
                </form>
            );
        }

        const { container } = render(<Example />);
        const control = screen.getByRole("switch", {
            name: "Make reusable",
        });
        const form = container.querySelector("form")!;
        expect(control.className).toContain(cotton.switch.trackUnchecked);
        expect(new FormData(form).has("make_reusable")).toBe(false);
        await user.click(screen.getByText("Make reusable"));
        expect(control.getAttribute("aria-checked")).toBe("true");
        expect(control.className).toContain(cotton.switch.trackChecked);
        expect(new FormData(form).get("make_reusable")).toBe("on");
        await user.keyboard(" ");
        expect(new FormData(form).has("make_reusable")).toBe(false);
    });
});

describe("form actions", () => {
    it("uses the Cotton action group and a real anchor for navigation", () => {
        const { container } = render(
            <FormActions className="test-actions">
                <ButtonLink href="/battle/" variant="ghost">
                    Cancel
                </ButtonLink>
                <Button type="submit" variant="success">
                    Save crew
                </Button>
            </FormActions>,
        );
        expect(container.firstElementChild?.className).toBe(
            `${cotton.formActions} test-actions`,
        );
        const cancel = screen.getByRole("link", { name: "Cancel" });
        expect(cancel.getAttribute("href")).toBe("/battle/");
        expect(cancel.className.trim()).toBe(cotton.buttonLink.ghost);
        expect(
            screen
                .getByRole("button", { name: "Save crew" })
                .getAttribute("type"),
        ).toBe("submit");
    });
});
