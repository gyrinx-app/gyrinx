import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FileInput, type FileInputProps } from "./FileInput";

const props: FileInputProps = {
    htmlName: "file",
    id: "id_file",
    accept: ".csv,text/csv",
};

function setup(overrides: Partial<FileInputProps> = {}) {
    const applied = { ...props, ...overrides };
    const rendered = render(
        <form>
            <label htmlFor={applied.id}>Upload a file</label>
            <FileInput {...applied} />
        </form>,
    );
    const input = screen.getByLabelText<HTMLInputElement>("Upload a file");
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
});
