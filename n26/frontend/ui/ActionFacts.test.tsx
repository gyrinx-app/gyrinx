import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ActionFacts } from "./ActionFacts";

const base = {
    stage: "review",
    outcome: "Augment a carried rig",
    selection_summary: "Hunting rig: Tier1",
    show_outcome: true,
    outcome_description: "Raise one tier.",
    reviewChoice: {
        label: "Selection",
        title: "Hunting rig: Tier1",
        description: "Improve S by1.\nImprove T by1.",
        meta: "Model rating0¢ →20¢",
    },
    changes: [],
    receipt: [{ label: "Rating", value: "+20¢" }],
    allowanceThreshold: true,
};
test("review preserves choice and selection captions and the small change control", () => {
    render(
        <ActionFacts
            facts={{ ...base, change_href: "/change/" }}
            modelName="Mara"
            frozen={false}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.getByText("Choice").className).toContain("uppercase");
    expect(screen.getByText("Selection").className).toContain("uppercase");
    expect(screen.getByText(/Improve S/).className).toContain(
        "whitespace-pre-line",
    );
    expect(
        screen.getByRole("link", { name: "Change selection" }).className,
    ).toContain("py-1");
});
test("completed results preserve their choice caption and separate result tally", () => {
    render(
        <ActionFacts
            facts={{ ...base, stage: "done" }}
            modelName="Mara"
            frozen={false}
            onNavigate={vi.fn()}
        />,
    );
    expect(screen.getByText("Choice").className).toContain("uppercase");
    expect(screen.getByRole("heading", { name: "Result" })).toBeTruthy();
    expect(screen.getByText("+20¢")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Completed" })).toBeTruthy();
});
