import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import cotton from "../generated/cotton.json";
import { FlowProgress } from "./FlowProgress";

test("progress uses Cotton states, links earlier steps and keeps skipped numbering", () => {
    const view = render(
        <FlowProgress
            steps={[
                { label: "Template", complete: true, href: "?step=1" },
                { label: "Customise", current: true },
                { label: "Review", skipped: true },
            ]}
        />,
    );
    expect(
        screen.getByRole("link", { name: "Template" }).getAttribute("href"),
    ).toBe("?step=1");
    expect(
        view.container.querySelector('[aria-current="step"]')?.textContent,
    ).toContain("Customise");
    expect(view.container.querySelector("ol")?.className).toBe(
        cotton.flowProgress.shortList,
    );
    expect(screen.getByText("3").className).toBe(
        cotton.flowProgress.states.skipped.circle,
    );
    expect(screen.getByText("(skipped)")).toBeTruthy();
});
