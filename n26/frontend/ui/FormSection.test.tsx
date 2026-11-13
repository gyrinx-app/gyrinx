import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormSection } from "./index";

describe("FormSection", () => {
    it("keeps the description with its heading before the fields", () => {
        render(
            <FormSection title="Choose" description="Select a result.">
                <input aria-label="Result" />
            </FormSection>,
        );
        const heading = screen.getByRole("heading", {
            name: "Choose",
            level: 2,
        });
        const description = screen.getByText("Select a result.");
        expect(description.parentElement).toBe(heading.parentElement);
        expect(
            heading
                .closest("section")
                ?.lastElementChild?.contains(
                    screen.getByRole("textbox", { name: "Result" }),
                ),
        ).toBe(true);
    });

    it("supports a description without drawing an empty heading", () => {
        render(
            <FormSection description="Select a result.">Fields</FormSection>,
        );
        expect(screen.queryByRole("heading")).toBeNull();
        expect(screen.getByText("Select a result.").tagName).toBe("P");
    });
});
