import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, afterEach, expect, test, vi } from "vitest";
import { TacticCard, type Card } from "./TacticCard";
import { fitRules } from "./useFittedRules";

const card: Card = {
    pk: "one",
    name: "Chem Queen",
    table_name: "Escher",
    dice_label: "D6",
    roll: 3,
    tactic: "chem-queen",
    notes: "<p>Play this tactic.</p>",
    suggested_notes: "",
    developed: false,
    reference: "Page 42 - Underhive Journal: Escher",
    tableKey: "escher",
};
beforeEach(() =>
    vi.stubGlobal(
        "ResizeObserver",
        class {
            observe() {}
            disconnect() {}
        },
    ),
);
afterEach(() => vi.unstubAllGlobals());
test("body text grows up to its maximum while reserving 20 percent", () => {
    expect(fitRules(200, 14, (size) => size * 10)).toBe(14);
    expect(fitRules(100, 14, (size) => size * 10)).toBeCloseTo(8, 1);
    const fitted = fitRules(100, 14, (size) => Math.ceil(size) * 20);
    expect(Math.ceil(fitted) * 20).toBeLessThanOrEqual(80);
});
test("click, Space and Enter select the same card", () => {
    const toggle = vi.fn();
    render(
        <TacticCard
            card={card}
            selected={false}
            printView={false}
            onToggle={toggle}
        />,
    );
    const article = screen.getByRole("checkbox", { name: card.name });
    fireEvent.click(article);
    fireEvent.keyDown(article, { key: " " });
    fireEvent.keyDown(article, { key: "Enter" });
    fireEvent.keyDown(article, { key: "ArrowDown" });
    expect(toggle).toHaveBeenCalledTimes(3);
    expect(screen.getByText("Play this tactic.").tagName).toBe("P");
    expect(
        screen.getByText("Underhive Journal: Escher · Page 42"),
    ).toBeTruthy();
});
test("print cards have no selection interaction", () => {
    const toggle = vi.fn();
    const { container } = render(
        <TacticCard card={card} selected printView onToggle={toggle} />,
    );
    fireEvent.click(container.querySelector("article")!);
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(toggle).not.toHaveBeenCalled();
});

test("a bonus card says so under the Save notes button, not in the footer", () => {
    const view = render(
        <TacticCard
            card={{
                ...card,
                bonus: true,
            }}
            selected={false}
            printView={false}
            onToggle={() => {}}
            notes={{
                saveUrl: "/notes/",
                csrfToken: "token",
                editorScript: "/tinymce.js",
                onSaved: () => {},
            }}
        />,
    );
    const label = screen.getByText("Bonus card");
    const save = screen.getByRole("button", { name: "Save notes" });
    expect(label.previousElementSibling?.contains(save)).toBe(true);
    expect(view.container.querySelector("footer")?.textContent).not.toContain(
        "Bonus",
    );
});

test("a printed bonus card still says so", () => {
    render(
        <TacticCard
            card={{ ...card, bonus: true }}
            selected={false}
            printView
            onToggle={() => {}}
        />,
    );
    expect(screen.getByText("Bonus card")).toBeTruthy();
});

test("a printed card shows only the saved notes, or lines to write on", () => {
    const { container, rerender } = render(
        <TacticCard
            card={{ ...card, suggested_notes: "<p>Suggested.</p>" }}
            selected={false}
            printView
            onToggle={() => {}}
        />,
    );
    expect(screen.getByText("Play this tactic.")).toBeTruthy();
    expect(screen.queryByText("Suggested.")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
    rerender(
        <TacticCard
            card={{ ...card, notes: "" }}
            selected={false}
            printView
            onToggle={() => {}}
        />,
    );
    expect(container.querySelector(".n26-tactic-notes-lines")).toBeTruthy();
});
