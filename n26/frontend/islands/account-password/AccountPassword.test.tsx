import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AccountPassword } from "./AccountPassword";
const props = {
    actionUrl: "/accounts/password/change/",
    returnUrl: "/accounts/security/",
    resetUrl: "/accounts/password/reset/",
    csrfToken: "token",
    errors: [],
    fields: [
        {
            name: "oldpassword",
            label: "Current password",
            autocomplete: "current-password",
            errors: [],
            help: "",
        },
        {
            name: "password1",
            label: "New password",
            autocomplete: "new-password",
            errors: [],
            help: "",
        },
        {
            name: "password2",
            label: "Repeat password",
            autocomplete: "new-password",
            errors: [],
            help: "",
        },
    ],
};
describe("Account password", () => {
    it("shows passwords on request and prevents mismatched submissions", () => {
        render(<AccountPassword {...props} />);
        fireEvent.change(screen.getByLabelText("New password"), {
            target: { value: "first" },
        });
        fireEvent.change(screen.getByLabelText("Repeat password"), {
            target: { value: "second" },
        });
        expect(
            (
                screen.getByRole("button", {
                    name: "Save password",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        expect(screen.getByText("The new passwords must match.")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Show passwords" }));
        expect(screen.getByLabelText("New password").getAttribute("type")).toBe(
            "text",
        );
        fireEvent.change(screen.getByLabelText("Repeat password"), {
            target: { value: "first" },
        });
        expect(
            (
                screen.getByRole("button", {
                    name: "Save password",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(false);
    });
    it("keeps server validation errors on the security form", () => {
        render(
            <AccountPassword
                {...props}
                fields={props.fields.map((field) =>
                    field.name === "oldpassword"
                        ? {
                              ...field,
                              errors: ["The current password is incorrect."],
                          }
                        : field,
                )}
            />,
        );
        expect(
            screen
                .getByLabelText("Current password")
                .getAttribute("aria-invalid"),
        ).toBe("true");
    });
});
