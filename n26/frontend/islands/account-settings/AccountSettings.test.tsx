import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountSettings, type AccountSettingsProps } from "./AccountSettings";
const props: AccountSettingsProps = {
    actionUrl: "/accounts/settings/",
    csrfToken: "token",
    errors: [],
    fields: [
        {
            name: "selected_badge",
            label: "Badge",
            value: "none",
            help: "",
            errors: [],
            choices: [
                { value: "none", label: "Hide badge" },
                { value: "staff", label: "Staff", imageUrl: "/staff.svg" },
            ],
        },
        {
            name: "timezone",
            label: "Time zone",
            value: "UTC",
            help: "Dates use this time zone.",
            errors: [],
            choices: [{ value: "UTC", label: "UTC" }],
        },
        {
            name: "email",
            label: "Email",
            value: "agent@example.com",
            help: "Verify a new address.",
            errors: [],
            choices: [],
        },
    ],
};
describe("Account settings", () => {
    it("shows badge artwork and lets the reader choose a visible badge or hide it", () => {
        const { container } = render(<AccountSettings {...props} />);
        expect(screen.getByRole("group", { name: "Badge" })).toBeTruthy();
        const staff = screen.getByRole("radio", {
            name: "Staff",
        }) as HTMLInputElement;
        const hide = screen.getByRole("radio", {
            name: "Hide badge",
        }) as HTMLInputElement;
        expect(
            staff.closest("label")?.querySelector("img")?.getAttribute("src"),
        ).toBe("/staff.svg");
        expect(
            container.querySelector('select[name="selected_badge"]'),
        ).toBeNull();
        fireEvent.click(staff);
        expect(staff.checked).toBe(true);
        expect(hide.checked).toBe(false);
        fireEvent.click(hide);
        expect(staff.checked).toBe(false);
        expect(
            new FormData(container.querySelector("form")!).get(
                "selected_badge",
            ),
        ).toBe("none");
    });
    it("posts all three edited settings in one CSRF-protected form", () => {
        const { container } = render(<AccountSettings {...props} />);
        fireEvent.click(screen.getByRole("radio", { name: "Staff" }));
        fireEvent.change(screen.getByLabelText("Email"), {
            target: { value: "new@example.com" },
        });
        const form = container.querySelector("form")!;
        const data = new FormData(form);
        expect(data.get("selected_badge")).toBe("staff");
        expect(data.get("timezone")).toBe("UTC");
        expect(data.get("email")).toBe("new@example.com");
        expect(data.get("csrfmiddlewaretoken")).toBe("token");
        fireEvent.submit(form);
        expect(
            (
                screen.getByRole("button", {
                    name: "Saving…",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
    });
    it("associates validation errors with their field", () => {
        render(
            <AccountSettings
                {...props}
                fields={props.fields.map((field) =>
                    field.name === "email"
                        ? {
                              ...field,
                              errors: ["This address is already in use."],
                          }
                        : field,
                )}
            />,
        );
        expect(
            screen.getByLabelText("Email").getAttribute("aria-invalid"),
        ).toBe("true");
        expect(
            screen.getByText("This address is already in use."),
        ).toBeTruthy();
    });
});
