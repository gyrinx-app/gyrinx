import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AdvancementRoll } from "./AdvancementRoll";

describe("advancement roll", () => {
    it("keeps the total visible and submits it only when recording a roll", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <AdvancementRoll
                    mode="roll"
                    rolled=""
                    modeErrors={[]}
                    rolledErrors={[]}
                    previousRoll={null}
                />
            </form>,
        );
        const total = screen.getByRole("spinbutton", {
            name: "Your 2D6 total",
        }) as HTMLInputElement;
        const form = view.container.querySelector("form")!;
        expect(total.disabled).toBe(true);
        await user.click(screen.getByRole("radio", { name: "Record my roll" }));
        expect(total.disabled).toBe(false);
        await user.type(total, "8");
        expect(new FormData(form).get("rolled")).toBe("8");
        await user.click(screen.getByRole("radio", { name: "Roll in Gyrinx" }));
        expect(total.disabled).toBe(true);
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(screen.getByRole("radio", { name: "Record my roll" }));
        expect(total.value).toBe("8");
    });

    it("restores a previous roll and associates server validation errors", () => {
        render(
            <AdvancementRoll
                mode="record"
                rolled="13"
                modeErrors={["Choose how to roll."]}
                rolledErrors={["Enter a total from 2 to 12."]}
                previousRoll={4}
            />,
        );
        const total = screen.getByRole("spinbutton", {
            name: "Your 2D6 total",
        }) as HTMLInputElement;
        expect(total.disabled).toBe(false);
        expect(total.value).toBe("13");
        expect(total.getAttribute("aria-invalid")).toBe("true");
        const group = screen.getByRole("group", { name: "Roll 2D6" });
        expect(group.getAttribute("aria-invalid")).toBe("true");
        expect(
            document.getElementById(group.getAttribute("aria-describedby")!)
                ?.textContent,
        ).toBe("Choose how to roll.");
        expect(screen.getByText(/Recorded roll: 4/)).toBeTruthy();
    });
});
