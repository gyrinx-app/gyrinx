import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CounterAdjustment } from "./CounterAdjustment";

const props = { value: 5, recorded: 2, change: "", errors: [], maximum: 1000 };

describe("counter adjustment", () => {
    it("previews additions and removals without changing the input contract", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <CounterAdjustment {...props} />
            </form>,
        );
        const input = screen.getByRole("spinbutton", { name: "Change *" });
        await user.type(input, "4");
        expect(
            view.container.querySelector("[data-counter-preview]")?.textContent,
        ).toBe("9");
        expect(
            view.container.querySelector("[data-counter-delta]")?.textContent,
        ).toBe("+4");
        expect(
            new FormData(view.container.querySelector("form")!).get("change"),
        ).toBe("4");
        await user.clear(input);
        await user.type(input, "-1");
        expect(
            view.container.querySelector("[data-counter-preview]")?.textContent,
        ).toBe("4");
        expect(
            view.container.querySelector("[data-counter-delta]")?.textContent,
        ).toBe("-1");
    });
    it("keeps contributions when removal reaches the recorded floor", () => {
        const view = render(<CounterAdjustment {...props} change="-10" />);
        expect(
            view.container.querySelector("[data-counter-preview]")?.textContent,
        ).toBe("3");
        expect(
            view.container.querySelector("[data-counter-delta]")?.textContent,
        ).toBe("-2");
    });
    it("retains server errors and avoids previewing invalid amounts", () => {
        const view = render(
            <CounterAdjustment
                {...props}
                change="1001"
                errors={["Too much."]}
            />,
        );
        expect(screen.getByText("Too much.")).toBeTruthy();
        expect(
            view.container.querySelector("[data-counter-preview]")?.textContent,
        ).toBe("5");
        expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
            "1001",
        );
    });
});

it("shows the persistent income adjustment and submits a reset separately", () => {
    render(
        <form>
            <CounterAdjustment
                {...props}
                isIncome
                recorded={2005}
                value={2025}
            />
        </form>,
    );
    expect(
        screen.getByText("Contributions 20¢ · manual adjustment 2005¢"),
    ).toBeTruthy();
    const reset = screen.getByRole("button", {
        name: "Reset adjustment",
    }) as HTMLButtonElement;
    expect(reset.name).toBe("reset");
    expect(reset.type).toBe("submit");
    expect(reset.formNoValidate).toBe(true);
});

it("edits the income total and updates its adjustment underneath", async () => {
    const user = userEvent.setup();
    const view = render(
        <form>
            <CounterAdjustment {...props} isIncome value={25} recorded={5} />
        </form>,
    );
    const input = screen.getByRole("spinbutton", { name: "Income *" });
    expect((input as HTMLInputElement).value).toBe("25");
    expect(screen.queryByRole("spinbutton", { name: "Change *" })).toBeNull();
    await user.clear(input);
    expect(
        screen.getByText("Contributions 20¢ · manual adjustment —"),
    ).toBeTruthy();
    await user.type(input, "30");
    expect(
        screen.getByText("Contributions 20¢ · manual adjustment 10¢"),
    ).toBeTruthy();
    expect(
        new FormData(view.container.querySelector("form")!).get("value"),
    ).toBe("30");
    expect(
        new FormData(view.container.querySelector("form")!).has("change"),
    ).toBe(false);
    await user.clear(input);
    await user.type(input, "19");
    expect((input as HTMLInputElement).validity.rangeUnderflow).toBe(true);
});

it("retains the entered income total and server errors", () => {
    render(
        <CounterAdjustment
            {...props}
            isIncome
            inputValue="19"
            errors={["Income must be at least 20¢ from held assets."]}
        />,
    );
    expect((screen.getByRole("spinbutton") as HTMLInputElement).value).toBe(
        "19",
    );
    expect(
        screen.getByText("Income must be at least 20¢ from held assets."),
    ).toBeTruthy();
});
