import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { PhaseSummary } from "./PhaseSummary";
import type { Rewards } from "./types";

function rewards(): Rewards {
    const blank = { credits: { fixed: 0, dice: null }, reputation: 0 };
    return {
        win: {
            credits: { fixed: 0, dice: { count: 2, sides: 3, multiplier: 10 } },
            reputation: 1,
        },
        draw: blank,
        loss: blank,
        entry_credits: { fixed: 250, dice: null },
    };
}

test("numbered phase summaries place cycle count and rewards beside the title", () => {
    render(
        <PhaseSummary
            name="Occupation"
            number={2}
            count={3}
            rewards={rewards()}
            description="Rules for this phase."
        />,
    );
    const heading = screen.getByRole("heading", {
        name: "Phase 2: Occupation",
    });
    expect(heading.textContent).toBe("2. Occupation");
    const count = screen.getByText("3 cycles");
    const reward = screen.getByText(
        "Win: 2D3 × 10¢, 1 reputation · Phase entry: 250¢",
    );
    expect(count.parentElement).toBe(heading.parentElement);
    expect(reward.parentElement).toBe(heading.parentElement);
    expect(screen.getByText("Rules for this phase.")).toBeTruthy();
});

test("effects use the shared dismissible popover and remain plain text", async () => {
    const effects =
        "<strong>Keep this literal.</strong>\nApply after each cycle.";
    render(<PhaseSummary name="Occupation" effects={effects} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByText(/Keep this literal/)).toBeNull();
    const trigger = screen.getByRole("button", {
        name: "Effects for Occupation",
    });
    await userEvent.click(trigger);
    const panel = screen.getByRole("dialog", {
        name: "Effects for Occupation",
    });
    expect(panel.textContent).toContain(effects);
    expect(panel.querySelector("strong")).toBeNull();
    expect(panel.querySelector("p")?.className).toContain(
        "whitespace-pre-wrap",
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
});

test("editable cards can omit the name while retaining their description and rewards", () => {
    render(
        <PhaseSummary
            name="Occupation"
            number={1}
            showName={false}
            description="Keep the authored description."
            rewards={rewards()}
            actions={<button type="button">Edit details</button>}
        />,
    );
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.getByText("Keep the authored description.")).toBeTruthy();
    expect(screen.getByText(/Win: 2D3/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Edit details" })).toBeTruthy();
    expect(screen.queryByText(/cycles/)).toBeNull();
});

test("empty summaries do not invent rewards, effects or cycle counts", () => {
    render(<PhaseSummary name="Downtime" count={0} />);
    expect(screen.getByRole("heading", { name: "Downtime" })).toBeTruthy();
    expect(screen.getByText("0 cycles")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/¢/)).toBeNull();
});
