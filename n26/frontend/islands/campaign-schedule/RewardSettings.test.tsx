import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test } from "vitest";
import { RewardSettings } from "./RewardSettings";
import type { Rewards } from "./types";

function settings(): Rewards {
    const reward = () => ({
        credits: { fixed: 0, dice: null },
        reputation: 0,
    });
    return {
        win: {
            credits: {
                fixed: 100,
                dice: { count: 2, sides: 6, multiplier: 10 },
            },
            reputation: 1,
        },
        draw: reward(),
        loss: reward(),
        entry_credits: { fixed: 250, dice: null },
    };
}

function Editor({ initial = settings() }: { initial?: unknown }) {
    const [value, setValue] = useState(JSON.stringify(initial));
    return (
        <>
            <RewardSettings value={value} onChange={setValue} />
            <output aria-label="Saved reward settings">{value}</output>
        </>
    );
}

function saved(): Rewards {
    return JSON.parse(
        screen.getByLabelText("Saved reward settings").textContent!,
    );
}

test("distinguishes die type, count and multiplier", () => {
    render(<Editor />);
    expect(
        (screen.getByLabelText("Win die type") as HTMLSelectElement).value,
    ).toBe("6");
    expect(
        (screen.getByLabelText("Win dice count") as HTMLInputElement).value,
    ).toBe("2");
    const multiplier = screen.getByLabelText("Win multiplier");
    expect((multiplier as HTMLInputElement).value).toBe("10");
    const description = document.getElementById(
        multiplier.getAttribute("aria-describedby")!,
    );
    expect(description?.textContent).toBe(
        "Multiply the total rolled, then add the fixed credits.",
    );
});

test("edits each dice component without changing fixed credits or other rewards", async () => {
    const user = userEvent.setup();
    render(<Editor />);
    await user.selectOptions(screen.getByLabelText("Win die type"), "3");
    await user.clear(screen.getByLabelText("Win dice count"));
    await user.type(screen.getByLabelText("Win dice count"), "4");
    await user.clear(screen.getByLabelText("Win multiplier"));
    await user.type(screen.getByLabelText("Win multiplier"), "20");
    expect(saved()).toEqual({
        ...settings(),
        win: {
            credits: {
                fixed: 100,
                dice: { count: 4, sides: 3, multiplier: 20 },
            },
            reputation: 1,
        },
    });
});

test("removing dice retains the fixed phase entry credits", async () => {
    const user = userEvent.setup();
    render(<Editor />);
    await user.selectOptions(
        screen.getByLabelText("Phase entry die type"),
        "6",
    );
    expect(saved().entry_credits).toEqual({
        fixed: 250,
        dice: { count: 1, sides: 6, multiplier: 1 },
    });
    await user.selectOptions(screen.getByLabelText("Phase entry die type"), "");
    expect(screen.queryByLabelText("Phase entry multiplier")).toBeNull();
    expect(saved().entry_credits).toEqual({ fixed: 250, dice: null });
});

test("editing another amount preserves sparse win and entry dice with their defaults", async () => {
    render(
        <Editor
            initial={{
                win: { credits: { dice: { sides: 3 } } },
                entry_credits: { dice: { count: 2, multiplier: 10 } },
            }}
        />,
    );
    expect(screen.getByLabelText("Win die type")).toHaveProperty("value", "3");
    expect(screen.getByLabelText("Win dice count")).toHaveProperty(
        "value",
        "1",
    );
    expect(screen.getByLabelText("Win multiplier")).toHaveProperty(
        "value",
        "1",
    );
    expect(screen.getByLabelText("Phase entry die type")).toHaveProperty(
        "value",
        "6",
    );
    await userEvent.clear(screen.getByLabelText("Draw reputation"));
    await userEvent.type(screen.getByLabelText("Draw reputation"), "2");
    expect(saved().win.credits).toEqual({
        fixed: 0,
        dice: { count: 1, sides: 3, multiplier: 1 },
    });
    expect(saved().entry_credits).toEqual({
        fixed: 0,
        dice: { count: 2, sides: 6, multiplier: 10 },
    });
});
