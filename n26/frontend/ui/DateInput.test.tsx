import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type FormEvent } from "react";
import { describe, expect, it, vi } from "vitest";
import { DateInput, Field } from "./index";

describe("date input", () => {
    it("clears the submitted value without submitting and returns focus to the date field", async () => {
        const changed = vi.fn();
        const submitted = vi.fn((event: FormEvent<HTMLFormElement>) =>
            event.preventDefault(),
        );
        function Example() {
            const [value, setValue] = useState("2026-11-07");
            return (
                <form onSubmit={submitted} aria-label="Dates">
                    <p id="date-pair-help">
                        Enter both dates or leave both blank.
                    </p>
                    <Field
                        label="Start date"
                        htmlFor="starts-on"
                        errors={["Review this date."]}
                    >
                        <DateInput
                            name="starts_on"
                            value={value}
                            clearLabel="Clear start date"
                            aria-describedby="date-pair-help"
                            onValueChange={(value) => {
                                changed(value);
                                setValue(value);
                            }}
                        />
                    </Field>
                </form>
            );
        }
        render(<Example />);
        const input = screen.getByLabelText("Start date") as HTMLInputElement;
        const clear = screen.getByRole("button", {
            name: "Clear start date",
        }) as HTMLButtonElement;
        expect(input.type).toBe("date");
        expect(input.getAttribute("aria-invalid")).toBe("true");
        const descriptions = input.getAttribute("aria-describedby")!.split(" ");
        expect(descriptions).toContain("date-pair-help");
        expect(descriptions).toContain(
            screen.getByText("Review this date.").parentElement!.id,
        );
        fireEvent.change(input, { target: { value: "2026-11-08" } });
        expect(changed).toHaveBeenLastCalledWith("2026-11-08");
        await userEvent.click(clear);
        expect(changed).toHaveBeenLastCalledWith("");
        expect(input.value).toBe("");
        expect(
            new FormData(
                screen.getByRole("form", { name: "Dates" }) as HTMLFormElement,
            ).get("starts_on"),
        ).toBe("");
        expect(submitted).not.toHaveBeenCalled();
        expect(document.activeElement).toBe(input);
        expect(clear.disabled).toBe(true);
        expect(screen.getByRole("button", { name: "Clear start date" })).toBe(
            clear,
        );
    });

    it.each(["disabled", "readOnly"] as const)(
        "keeps the clear action disabled for a %s date",
        async (state) => {
            const changed = vi.fn();
            render(
                <Field label="Start date" htmlFor="starts-on">
                    <DateInput
                        value="2026-11-07"
                        onValueChange={changed}
                        {...{ [state]: true }}
                    />
                </Field>,
            );
            const clear = screen.getByRole("button", {
                name: "Clear date",
            }) as HTMLButtonElement;
            expect(clear.disabled).toBe(true);
            await userEvent.click(clear);
            expect(changed).not.toHaveBeenCalled();
            expect(
                (screen.getByLabelText("Start date") as HTMLInputElement)[
                    state
                ],
            ).toBe(true);
        },
    );

    it("honours a pending form's disabled fieldset", async () => {
        const changed = vi.fn();
        render(
            <fieldset disabled>
                <DateInput
                    aria-label="Start date"
                    value="2026-11-07"
                    onValueChange={changed}
                />
            </fieldset>,
        );
        await userEvent.click(
            screen.getByRole("button", { name: "Clear date" }),
        );
        expect(changed).not.toHaveBeenCalled();
    });
});
