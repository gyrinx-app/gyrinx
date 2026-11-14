import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
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
    expect(heading.textContent).toBe("02 Occupation");
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

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

test("long effects stay scrollable within a short phone viewport", () => {
    vi.stubGlobal("innerWidth", 390);
    vi.stubGlobal("innerHeight", 400);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
        x: 240,
        y: 300,
        left: 240,
        top: 300,
        right: 300,
        bottom: 330,
        width: 60,
        height: 30,
        toJSON: () => ({}),
    });
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
        1200,
    );
    const effects = `${"Apply the phase effect after every battle.\n".repeat(30)}Final phase effect.`;
    render(<PhaseSummary name="Occupation" effects={effects} />);
    fireEvent.click(
        screen.getByRole("button", { name: "Effects for Occupation" }),
    );
    const panel = screen.getByRole("dialog", {
        name: "Effects for Occupation",
    });
    const top = Number.parseFloat(panel.style.top);
    const maxHeight = Number.parseFloat(panel.style.maxHeight);
    expect(top).toBeGreaterThanOrEqual(16);
    expect(maxHeight).toBeGreaterThan(0);
    expect(top + maxHeight).toBeLessThanOrEqual(window.innerHeight - 16);
    expect(panel.textContent).toContain("Final phase effect.");
    expect(panel.className).toContain("overflow-y-auto");
});

test("sparse reward previews show backend dice defaults without undefined amounts", () => {
    render(
        <PhaseSummary
            name="Occupation"
            rewards={
                {
                    win: { credits: { dice: { sides: 3 } } },
                    draw: { reputation: 2 },
                    loss: { credits: { dice: {} } },
                    entry_credits: { dice: { count: 2, multiplier: 10 } },
                } as unknown as Rewards
            }
        />,
    );
    expect(
        screen.getByText(
            "Win: 1D3¢ · Draw: 2 reputation · Loss: 1D6¢ · Phase entry: 2D6 × 10¢",
        ),
    ).toBeTruthy();
    expect(screen.queryByText(/undefined/)).toBeNull();
});
