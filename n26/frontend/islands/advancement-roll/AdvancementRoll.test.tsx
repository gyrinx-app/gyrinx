import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AdvancementRoll, type AdvancementRollProps } from "./AdvancementRoll";

const twoDice: AdvancementRollProps = {
    dice: "2D6",
    minimum: 2,
    maximum: 12,
    totalLabel: "Your 2D6 total",
    totalHelp: "If you rolled your own dice, enter their total.",
    mode: "roll",
    rolled: "",
    modeErrors: [],
    rolledErrors: [],
    previousRoll: null,
    choices: null,
};

const skillRoll: AdvancementRollProps = {
    ...twoDice,
    dice: "D6",
    minimum: 1,
    maximum: 6,
    totalLabel: "Your D6 roll",
    totalHelp: "If you rolled your own die, enter the number.",
    choices: {
        legend: "Select a skill set",
        name: "skill_set_id",
        value: "agility",
        errors: [],
        options: [
            { value: "agility", label: "Agility", carried: "" },
            {
                value: "cunning",
                label: "Cunning",
                carried: "Your D6 roll of 3 carries over to this skill set.",
            },
        ],
    },
};

describe("advancement roll", () => {
    it("keeps the total visible and submits it only when recording a roll", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <AdvancementRoll {...twoDice} />
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
                {...twoDice}
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

    it("records a D6 for the chosen skill set", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <AdvancementRoll {...skillRoll} />
            </form>,
        );
        const form = view.container.querySelector("form")!;
        expect(screen.getByRole("group", { name: "Roll D6" })).toBeTruthy();
        const roll = screen.getByRole("spinbutton", {
            name: "Your D6 roll",
        }) as HTMLInputElement;
        expect(roll.min).toBe("1");
        expect(roll.max).toBe("6");
        expect(roll.disabled).toBe(true);
        await user.click(screen.getByRole("radio", { name: "Record my roll" }));
        await user.type(roll, "4");
        const data = new FormData(form);
        expect(data.get("skill_set_id")).toBe("agility");
        expect(data.get("roll_mode")).toBe("record");
        expect(data.get("rolled")).toBe("4");
    });

    it("hides the roll controls when a set reuses an earlier die", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <AdvancementRoll {...skillRoll} />
            </form>,
        );
        const form = view.container.querySelector("form")!;
        await user.click(screen.getByRole("radio", { name: "Record my roll" }));
        await user.type(
            screen.getByRole("spinbutton", { name: "Your D6 roll" }),
            "5",
        );
        await user.click(screen.getByRole("radio", { name: "Cunning" }));
        expect(
            screen.getByText(
                "Your D6 roll of 3 carries over to this skill set.",
            ),
        ).toBeTruthy();
        expect(screen.queryByRole("spinbutton")).toBeNull();
        const data = new FormData(form);
        expect(data.get("skill_set_id")).toBe("cunning");
        expect(data.has("roll_mode")).toBe(false);
        expect(data.has("rolled")).toBe(false);
        await user.click(screen.getByRole("radio", { name: "Agility" }));
        expect(
            (
                screen.getByRole("spinbutton", {
                    name: "Your D6 roll",
                }) as HTMLInputElement
            ).value,
        ).toBe("5");
    });
});
