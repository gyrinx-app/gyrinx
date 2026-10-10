import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { IncomeTooltip } from "./IncomeTooltip";

it("keeps the breakdown hidden until opened and supports zero income", () => {
    render(<IncomeTooltip value={0} contributed={0} adjustment={0} />);
    const trigger = screen.getByRole("button", {
        name: "Income breakdown: 0¢",
    });
    expect(trigger.textContent).toBe("0");
    expect(screen.queryByText("Manual adjustment")).toBeNull();
    fireEvent.click(trigger, { detail: 0 });
    expect(screen.getByRole("dialog")).toBe(document.activeElement);
    expect(screen.getByText("Manual adjustment")).toBeTruthy();
    expect(screen.getByText("Contributions")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
});
