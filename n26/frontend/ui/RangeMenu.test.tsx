import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { RangeMenu } from "./RangeMenu";

function Harness({ initial = [0, 500] as [number, number] }) {
    const [value, setValue] = useState<[number, number]>(initial);
    return (
        <>
            <RangeMenu
                label="Wealth"
                min={0}
                max={500}
                step={50}
                suffix="¢"
                atMaxLabel="Any"
                value={value}
                onChange={setValue}
            />
            <output data-testid="value">{value.join(",")}</output>
            <button type="button">Elsewhere</button>
        </>
    );
}

const trigger = () => screen.getByRole("button", { name: /Wealth/ });
const minimum = () =>
    screen.getByRole("slider", { name: "Minimum" }) as HTMLInputElement;
const maximum = () =>
    screen.getByRole("slider", { name: "Maximum" }) as HTMLInputElement;

describe("RangeMenu", () => {
    it("names the whole range Any and a narrowed one by its ends", () => {
        const whole = render(<Harness />);
        expect(trigger().textContent).toBe("WealthAny");
        whole.unmount();
        render(<Harness initial={[100, 300]} />);
        expect(trigger().textContent).toBe("Wealth100–300¢");
    });

    it("opens a panel whose thumbs narrow the range at once", async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.click(trigger());
        expect(trigger().getAttribute("aria-expanded")).toBe("true");
        expect(
            screen.getByRole("group", { name: "Wealth" }).textContent,
        ).toContain("0–500¢");
        fireEvent.change(minimum(), { target: { value: "100" } });
        fireEvent.change(maximum(), { target: { value: "300" } });
        expect(screen.getByTestId("value").textContent).toBe("100,300");
        expect(trigger().textContent).toContain("100–300¢");
        expect(minimum().value).toBe("100");
    });

    it("never lets the thumbs cross", async () => {
        const user = userEvent.setup();
        render(<Harness initial={[100, 300]} />);
        await user.click(trigger());
        fireEvent.change(minimum(), { target: { value: "450" } });
        expect(screen.getByTestId("value").textContent).toBe("300,300");
        fireEvent.change(maximum(), { target: { value: "50" } });
        expect(screen.getByTestId("value").textContent).toBe("300,300");
    });

    it("labels its ends and closes on Escape back to the trigger", async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.click(trigger());
        const panel = screen.getByRole("group", { name: "Wealth" });
        expect(panel.textContent).toContain("0");
        expect(panel.textContent).toContain("Any");
        minimum().focus();
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("group", { name: "Wealth" })).toBeNull();
        expect(document.activeElement).toBe(trigger());
    });

    it("closes when the reader moves elsewhere", async () => {
        const user = userEvent.setup();
        render(<Harness />);
        await user.click(trigger());
        await user.click(screen.getByRole("button", { name: "Elsewhere" }));
        expect(screen.queryByRole("group", { name: "Wealth" })).toBeNull();
    });
});
