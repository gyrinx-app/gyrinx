import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { AccountLoginName } from "./AccountLoginName";
it("keeps the login field contract and warns when an email is entered", () => {
    render(
        <AccountLoginName
            id="id_login"
            name="login"
            label="Username"
            value=""
            errors={[]}
            required
            autocomplete="username"
        />,
    );
    const input = screen.getByLabelText("Username");
    expect(input.getAttribute("name")).toBe("login");
    fireEvent.change(input, { target: { value: "user@example.com" } });
    expect(screen.getByRole("status").textContent).toBe(
        "Use your username to sign in.",
    );
    fireEvent.change(input, { target: { value: "username" } });
    expect(screen.queryByRole("status")).toBeNull();
});
