import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ModelCard, isModelCard } from "./ModelCard";
import { card } from "../test/modelCard";

test("stored cards keep native workflow links and standalone CSRF-protected dismiss forms", () => {
    const { container } = render(
        <ModelCard
            card={card}
            csrfToken="fresh"
            frozen={false}
            onTally={vi.fn()}
        />,
    );
    expect(
        screen.getByRole("link", { name: "Rename Vex" }).getAttribute("href"),
    ).toBe("/rename/");
    expect(
        screen
            .getByRole("link", { name: "Choose skills" })
            .getAttribute("href"),
    ).toBe("/choose/");
    const form = screen
        .getByRole("button", { name: "Dismiss Skills" })
        .closest("form")!;
    expect(form.getAttribute("action")).toBe("/dismiss/");
    expect(Object.fromEntries(new FormData(form))).toEqual({
        csrfmiddlewaretoken: "fresh",
        back: "/equip/",
    });
    expect(container.querySelector("form form")).toBeNull();
    expect(screen.queryByText("Lore")).toBeNull();
});

test("counter decrement uses recorded tally and frozen cards block writes", async () => {
    const onTally = vi.fn();
    const view = render(
        <ModelCard
            card={card}
            csrfToken="fresh"
            frozen={false}
            onTally={onTally}
        />,
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Take one off Ammo",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    await userEvent.click(
        screen.getByRole("button", { name: "Add one to Ammo" }),
    );
    expect(onTally).toHaveBeenCalledWith("ammo-counter", 1, "Ammo");
    view.rerender(
        <ModelCard card={card} csrfToken="fresh" frozen onTally={onTally} />,
    );
    expect(
        (
            screen.getByRole("button", {
                name: "Add one to Ammo",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
    expect(
        (
            screen.getByRole("button", {
                name: "Dismiss Skills",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});

test("stored metadata and action targets are validated before a response replaces the card", () => {
    expect(isModelCard(card)).toBe(true);
    expect(
        isModelCard({
            ...card,
            stored: {
                ...card.stored,
                statusHref: "https://elsewhere.invalid/",
            },
        }),
    ).toBe(false);
    expect(
        isModelCard({
            ...card,
            details: [
                {
                    ...card.details[0],
                    parts: [
                        {
                            kind: "counter",
                            value: 1,
                            control: { name: "Ammo" },
                        },
                    ],
                },
            ],
        }),
    ).toBe(false);
});
