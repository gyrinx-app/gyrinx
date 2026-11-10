import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ModelCard, isModelCard } from "./ModelCard";
import { card } from "../test/modelCard";

test("weapon, profile and accessory menus keep independent actions and accessory acquisition inside the weapon menu", async () => {
    const action = (
        label: string,
        target: string,
        separatorBefore = false,
    ) => ({ label, target, tone: "default", separatorBefore });
    render(
        <ModelCard
            card={{
                ...card,
                weapons: [
                    {
                        key: "gun",
                        name: "Autogun",
                        stats: [],
                        traits: [],
                        choices: [],
                        actions: [
                            action("Sell", "/sell/"),
                            {
                                ...action("Delete", "/delete/", true),
                                tone: "danger",
                            },
                        ],
                        accessorise: action("Add accessory", "/add-sight/"),
                        profiles: [
                            {
                                key: "ammo",
                                name: "Warp rounds",
                                stats: [],
                                traits: [],
                                actions: [action("Remove", "/remove-ammo/")],
                            },
                        ],
                        accessories: [
                            {
                                key: "sight",
                                text: "Sight",
                                explanation: "",
                                choices: [],
                                actions: [action("Remove", "/remove-sight/")],
                            },
                        ],
                    },
                ],
            }}
            csrfToken="fresh"
            frozen={false}
            onTally={vi.fn()}
        />,
    );
    expect(screen.queryByRole("link", { name: /Add accessory/ })).toBeNull();
    const trigger = screen.getByRole("button", { name: "More for Autogun" });
    await userEvent.click(trigger);
    const menu = screen.getByRole("menu");
    expect(
        within(menu)
            .getAllByRole("menuitem")
            .map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
        ["Add accessory", "/add-sight/"],
        ["Sell", "/sell/"],
        ["Delete", "/delete/"],
    ]);
    expect(within(menu).getAllByRole("separator")).toHaveLength(2);
    await userEvent.keyboard("{Escape}");
    expect(document.activeElement).toBe(trigger);
    for (const [name, href] of [
        ["Warp rounds", "/remove-ammo/"],
        ["Sight", "/remove-sight/"],
    ]) {
        await userEvent.click(
            screen.getByRole("button", { name: `More for ${name}` }),
        );
        expect(
            screen
                .getByRole("menuitem", { name: "Remove" })
                .getAttribute("href"),
        ).toBe(href);
        await userEvent.keyboard("{Escape}");
    }
});

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

test("short rating help stays a tooltip while overrides and pictures have separate disclosures", async () => {
    const user = userEvent.setup();
    const view = render(
        <ModelCard
            card={card}
            csrfToken="fresh"
            frozen={false}
            onTally={vi.fn()}
        />,
    );
    await user.click(screen.getByRole("button", { name: "35¢" }));
    expect(screen.getByRole("tooltip").textContent).toBe(
        "Rating, including weapons and wargear",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    view.rerender(
        <ModelCard
            card={{
                ...card,
                stored: {
                    ...card.stored,
                    imageHref: "/picture.png",
                    ratingOverride: { baseRating: 20, defaultBaseRating: 30 },
                },
            }}
            csrfToken="fresh"
            frozen={false}
            onTally={vi.fn()}
        />,
    );
    const rating = screen.getByRole("button", {
        name: "Vex's rating: 35¢. Includes a base rating override",
    });
    await user.click(rating);
    expect(screen.getByRole("dialog").textContent).toContain(
        "Base rating overridden to 20¢.",
    );
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(rating);
    const picture = screen.getByRole("button", {
        name: "Show this model's picture",
    });
    await user.click(picture);
    expect(
        within(screen.getByRole("dialog", { name: "Model picture" }))
            .getByRole("img")
            .getAttribute("src"),
    ).toBe("/picture.png");
    await user.keyboard("{Escape}");
    expect(document.activeElement).toBe(picture);
});

test("cards outside Equip submit counter steps as independent native forms", () => {
    const view = render(
        <ModelCard card={card} csrfToken="fresh" frozen={false} />,
    );
    for (const [label, change] of [
        ["Take one off Ammo", "-1"],
        ["Add one to Ammo", "1"],
    ]) {
        const button = screen.getByRole("button", {
            name: label,
        }) as HTMLButtonElement;
        const form = button.closest("form")!;
        expect(form.getAttribute("method")).toBe("post");
        expect(form.getAttribute("action")).toBe("/counter/");
        expect(button.type).toBe("submit");
        expect(Object.fromEntries(new FormData(form))).toEqual({
            csrfmiddlewaretoken: "fresh",
            back: "/equip/",
            change,
        });
    }
    expect(view.container.querySelector("form form")).toBeNull();
    view.rerender(<ModelCard card={card} csrfToken="fresh" frozen />);
    expect(
        (
            screen.getByRole("button", {
                name: "Add one to Ammo",
            }) as HTMLButtonElement
        ).disabled,
    ).toBe(true);
});
