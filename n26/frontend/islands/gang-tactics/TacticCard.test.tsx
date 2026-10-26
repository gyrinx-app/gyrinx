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
    timing: [{ text: "Play this tactic.", keyword: true }],
    effect: [],
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
test("click, Space and Enter select the same card without bolding keywords", () => {
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

test("a bonus card says so under its rules, not in the footer", () => {
    const view = render(
        <TacticCard
            card={{
                ...card,
                effect: [{ text: "They move.", keyword: false }],
                bonus: true,
            }}
            selected={false}
            printView={false}
            onToggle={() => {}}
        />,
    );
    const label = screen.getByText("Bonus card");
    expect(label.closest(".n26-tactic-rules")).toBeTruthy();
    expect(view.container.querySelector("footer")?.textContent).not.toContain(
        "Bonus",
    );
});
