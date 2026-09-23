import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FileInput, type FileInputProps } from "./FileInput";

const props: FileInputProps = {
    htmlName: "file",
    id: "id_file",
    label: "The All Profiles sheet",
    helpText: "A CSV export.",
    errors: [],
    required: true,
    accept: ".csv,text/csv",
};

function setup(overrides: Partial<FileInputProps> = {}) {
    const applied = { ...props, ...overrides };
    const rendered = render(
        <form>
            <FileInput {...applied} />
        </form>,
    );
    const input = screen.getByLabelText<HTMLInputElement>(
        `${applied.label}${applied.required ? " *" : ""}`,
    );
    return {
        ...rendered,
        input,
        form: rendered.container.querySelector("form")!,
        dropTarget: input.parentElement!.parentElement!,
        user: userEvent.setup(),
    };
}

describe("FileInput", () => {
    it("keeps Django's native file field contract", async () => {
        const { input, form, user } = setup();
        const file = new File(["Assignable,Name"], "profiles.csv", {
            type: "text/csv",
        });

        expect(input.name).toBe("file");
        expect(input.id).toBe("id_file");
        expect(input.accept).toBe(".csv,text/csv");
        expect(screen.getByText("A CSV export.")).toBeTruthy();

        await user.upload(input, file);
        expect(new FormData(form).get("file")).toEqual(file);
    });

    it("keeps the drop target highlighted while a child is crossed", () => {
        const { input, dropTarget } = setup();

        fireEvent.dragEnter(dropTarget);
        fireEvent.dragEnter(input);
        fireEvent.dragLeave(input);
        expect(dropTarget.className).toContain("ring-2");

        fireEvent.dragLeave(dropTarget);
        expect(dropTarget.className).not.toContain("ring-2");

        fireEvent.dragEnter(dropTarget);
        fireEvent.drop(input);
        expect(dropTarget.className).not.toContain("ring-2");
    });

    it("associates server errors without interpreting their text as markup", () => {
        const error = '<img src=x onerror="alert(1)">';
        const { container, input } = setup({
            errors: [error],
            required: false,
        });

        expect(input.getAttribute("aria-invalid")).toBe("true");
        expect(screen.getByText(error)).toBeTruthy();
        expect(container.querySelector("img")).toBeNull();
    });
});
