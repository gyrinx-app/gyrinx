import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import cotton from "../../generated/cotton.json";
import { TradePoints, type TradePointsProps } from "./TradePoints";

const props: TradePointsProps = {
    amountLabel: "Or enter a specific TP amount",
    emptyMessage: "No model in The Ashen Choir adds Trade Points.",
    groups: [
        {
            name: "2 Trade Points each",
            options: [{ key: "vex", name: "Vex", points: 2 }],
        },
        {
            name: "1 Trade Point each",
            options: [{ key: "sura", name: "Sura", points: 1 }],
        },
    ],
};

function formText() {
    return document.body.textContent ?? "";
}

function renderForm(initial?: Partial<TradePointsProps>) {
    const { container } = render(
        <form>
            <TradePoints {...props} {...initial} />
        </form>,
    );
    return container.querySelector("form")!;
}

describe("TradePoints", () => {
    it("starts unticked and shows a zero total", () => {
        const form = renderForm();
        expect(
            (screen.getByRole("checkbox", { name: "Vex" }) as HTMLInputElement)
                .checked,
        ).toBe(false);
        expect(screen.getByText("2 Trade Points each")).toBeTruthy();
        expect(screen.getByText("0").textContent).toBe("0");
        expect(new FormData(form).getAll("visiting")).toEqual([]);
        expect(
            screen
                .getByRole("button", { name: "Start TP visit" })
                .getAttribute("type"),
        ).toBe("submit");
    });

    it("adds the ticked models", () => {
        const form = renderForm();
        fireEvent.click(screen.getByRole("checkbox", { name: "Vex" }));
        fireEvent.click(screen.getByRole("checkbox", { name: "Sura" }));
        expect(screen.getByText("3").textContent).toBe("3");
        expect(new FormData(form).getAll("visiting")).toEqual(["vex", "sura"]);
    });

    it("shuts the ticks and drops the total when a figure is typed", () => {
        const form = renderForm();
        fireEvent.click(screen.getByRole("checkbox", { name: "Vex" }));
        fireEvent.change(
            screen.getByLabelText("Or enter a specific TP amount"),
            {
                target: { value: "9" },
            },
        );
        expect(formText()).not.toContain("Selected models add");
        const box = screen.getByRole("checkbox", { name: "Vex" });
        expect((box as HTMLInputElement).checked).toBe(true);
        expect((box as HTMLInputElement).disabled).toBe(true);
        // The row takes the tick list's disabled look, not only the box.
        expect(box.closest("label")!.className).toBe(
            cotton.tickList.labelDisabled,
        );
        expect(new FormData(form).getAll("visiting")).toEqual([]);
        expect(new FormData(form).get("brought")).toBe("9");
    });

    it("treats a blank figure as no override", () => {
        renderForm();
        fireEvent.change(
            screen.getByLabelText("Or enter a specific TP amount"),
            {
                target: { value: "   " },
            },
        );
        expect(formText()).toContain("Selected models add");
        expect(
            (screen.getByRole("checkbox", { name: "Vex" }) as HTMLInputElement)
                .disabled,
        ).toBe(false);
    });

    it("offers only the amount when nobody adds Trade Points", () => {
        renderForm({ groups: [] });
        expect(
            screen.getByText("No model in The Ashen Choir adds Trade Points."),
        ).toBeTruthy();
        expect(screen.queryByRole("checkbox")).toBeNull();
        expect(formText()).not.toContain("Selected models add");
        expect(
            screen.getByLabelText("Or enter a specific TP amount"),
        ).toBeTruthy();
    });
});
