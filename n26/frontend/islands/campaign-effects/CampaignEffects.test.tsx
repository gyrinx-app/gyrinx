import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { CampaignEffects } from "./CampaignEffects";

test("effects start collapsed and open independently without interpreting markup", async () => {
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
    const phase = screen.getByText("Phase effects");
    const cycle = screen.getByText("Cycle effects");
    expect(phase.closest("details")?.open).toBe(false);
    expect(cycle.closest("details")?.open).toBe(false);
    await userEvent.click(phase);
    expect(phase.closest("details")?.open).toBe(true);
    expect(cycle.closest("details")?.open).toBe(false);
    expect(phase.closest("details")?.querySelector("p")?.textContent).toBe(
        effects,
    );
    expect(container.querySelector("img")).toBeNull();
    await userEvent.click(phase);
    expect(phase.closest("details")?.open).toBe(false);
});

test("empty effects have no disclosure", () => {
    const { container } = render(
        <CampaignEffects label="Phase effects" effects="" />,
    );
    expect(container.querySelector("details")).toBeNull();
});
