import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { CampaignEffects } from "./CampaignEffects";

test("effects open in separate popovers without interpreting markup", async () => {
    const effects = "<img src=x onerror=alert(1)>\nApply after each battle.";
    const { container } = render(
        <>
            <CampaignEffects label="Phase effects" effects={effects} />
            <CampaignEffects
                label="Cycle effects"
                effects="Use the cycle rule."
            />
        </>,
    );
    const phase = screen.getByRole("button", { name: "Phase effects" });
    const cycle = screen.getByRole("button", { name: "Cycle effects" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(phase);
    expect(phase.getAttribute("aria-expanded")).toBe("true");
    expect(cycle.getAttribute("aria-expanded")).toBe("false");
    const panel = screen.getByRole("dialog", { name: "Phase effects" });
    expect(panel.querySelector("p")?.textContent).toBe(effects);
    expect(container.querySelector("img")).toBeNull();
    await userEvent.click(cycle);
    expect(screen.queryByRole("dialog", { name: "Phase effects" })).toBeNull();
    expect(
        screen.getByRole("dialog", { name: "Cycle effects" }).textContent,
    ).toBe("Use the cycle rule.");
    await userEvent.click(cycle);
    expect(screen.queryByRole("dialog")).toBeNull();
});

test("keyboard readers can open effects and return to the trigger", async () => {
    render(
        <CampaignEffects
            label="Phase effects"
            effects="Apply after each battle."
        />,
    );
    const trigger = screen.getByRole("button", { name: "Phase effects" });
    trigger.focus();
    await userEvent.keyboard("{Enter}");
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(trigger);
});

test("empty effects have no trigger", () => {
    const { container } = render(
        <CampaignEffects label="Phase effects" effects="" />,
    );
    expect(container.textContent).toBe("");
});
