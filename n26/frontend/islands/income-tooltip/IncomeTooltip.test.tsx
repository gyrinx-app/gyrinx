import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IncomeTooltip } from "./IncomeTooltip";

function open(value: number) {
    const trigger = screen.getByRole("button", {
        name: `Income breakdown: ${value}¢`,
    });
    fireEvent.click(trigger, { detail: 0 });
    return trigger;
}

function sourceGroup(name: string) {
    return within(screen.getByText(name).closest("section")!);
}

describe("IncomeTooltip", () => {
    it("keeps the aggregate breakdown hidden until opened and supports zero income", () => {
        render(<IncomeTooltip value={0} contributed={0} adjustment={0} />);
        const trigger = screen.getByRole("button", {
            name: "Income breakdown: 0¢",
        });
        expect(trigger.textContent).toBe("0");
        expect(screen.queryByText("Manual adjustment")).toBeNull();
        expect(screen.queryByRole("dialog")).toBeNull();
        open(0);
        expect(screen.getByRole("dialog")).toBe(document.activeElement);
        expect(screen.getByText("Manual adjustment")).toBeTruthy();
        expect(screen.getByText("Contributions")).toBeTruthy();
        expect(
            screen.getByText("Total income").parentElement!.textContent,
        ).toBe("Total income0¢");
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("groups each holding's supplied contributions and includes the manual adjustment", () => {
        render(
            <IncomeTooltip
                value={43}
                contributed={40}
                adjustment={3}
                sources={[
                    {
                        name: "Generatorium",
                        value: 15,
                        parts: [
                            {
                                label: "Base income",
                                amount: 15,
                                detail: "Generatorium: income",
                                replaced: false,
                            },
                        ],
                    },
                    {
                        name: "Amneo-vats",
                        value: 25,
                        parts: [
                            {
                                label: "Base income",
                                amount: 15,
                                detail: "Amneo-vats: income",
                                replaced: false,
                            },
                            {
                                label: "Boon",
                                amount: 10,
                                detail: "Goliath standing Income",
                                replaced: false,
                            },
                        ],
                    },
                ]}
            />,
        );
        open(43);
        const generatorium = sourceGroup("Generatorium");
        const amneo = sourceGroup("Amneo-vats");
        expect(generatorium.getByText("15¢")).toBeTruthy();
        expect(generatorium.getByText("Generatorium: income")).toBeTruthy();
        expect(generatorium.queryByText("Boon")).toBeNull();
        expect(amneo.getByText("25¢")).toBeTruthy();
        expect(amneo.getByText("Boon")).toBeTruthy();
        expect(amneo.getByText("Goliath standing Income")).toBeTruthy();
        expect(amneo.getByText("+10¢")).toBeTruthy();
        expect(screen.queryByText("Contributions")).toBeNull();
        const scrollable = within(
            screen.getByRole("region", { name: "Income breakdown details" }),
        );
        expect(scrollable.queryByText("Manual adjustment")).toBeNull();
        expect(scrollable.queryByText("Total income")).toBeNull();
        expect(
            screen.getByText("Manual adjustment").parentElement!.textContent,
        ).toBe("Manual adjustment3¢");
        expect(
            screen.getByText("Total income").parentElement!.textContent,
        ).toBe("Total income43¢");
    });

    it.each([
        { override: 42, total: 52 },
        { override: 0, total: 10 },
    ])(
        "excludes the replaced base beside override $override and its boon",
        ({ override, total }) => {
            render(
                <IncomeTooltip
                    value={total}
                    contributed={total}
                    adjustment={0}
                    currency
                    showAdjustment={false}
                    sources={[
                        {
                            name: "Amneo-vats",
                            value: total,
                            parts: [
                                {
                                    label: "Base income",
                                    amount: 15,
                                    detail: "Amneo-vats: income",
                                    replaced: true,
                                },
                                {
                                    label: "Income override",
                                    amount: override,
                                    detail: "",
                                    replaced: false,
                                },
                                {
                                    label: "Boon",
                                    amount: 10,
                                    detail: "Goliath standing Income",
                                    replaced: false,
                                },
                            ],
                        },
                    ]}
                />,
            );
            const trigger = open(total);
            expect(trigger.textContent).toBe(`${total}¢`);
            const group = sourceGroup("Amneo-vats");
            expect(group.getByText("+15¢").tagName).toBe("S");
            expect(
                group.getByText("Replaced by override; excluded from total."),
            ).toBeTruthy();
            expect(
                group.getByText("Income override").closest("div")!.textContent,
            ).toBe(`Income override${override ? "+" : ""}${override}¢`);
            expect(group.getByText("+10¢")).toBeTruthy();
            expect(screen.queryByText("Manual adjustment")).toBeNull();
            expect(
                screen.getByText("Total income").parentElement!.textContent,
            ).toBe(`Total income${total}¢`);
        },
    );

    it("keeps the aggregate fallback when source data is empty", () => {
        render(
            <IncomeTooltip
                value={10}
                contributed={15}
                adjustment={-5}
                sources={[]}
            />,
        );
        open(10);
        expect(
            screen.getByText("Contributions").parentElement!.textContent,
        ).toBe("Contributions15¢");
        expect(
            screen.getByText("Manual adjustment").parentElement!.textContent,
        ).toBe("Manual adjustment-5¢");
    });

    it("retains repeated holdings, long authored names, zero and negative contributions", () => {
        const longName = "An authored territory name ".repeat(20);
        const longDetail = "An authored modifier or pick name "
            .repeat(20)
            .trim();
        const sources = Array.from({ length: 30 }, (_, index) => ({
            name: index < 2 ? "Old Ruins" : `${longName}${index}`,
            value: index === 0 ? -5 : index === 1 ? 5 : 0,
            parts: [
                {
                    label: "Boon",
                    amount: index === 0 ? -5 : index === 1 ? 5 : 0,
                    detail: longDetail,
                    replaced: false,
                },
            ],
        }));
        render(
            <IncomeTooltip
                value={0}
                contributed={0}
                adjustment={0}
                sources={sources}
            />,
        );
        open(0);
        const details = screen.getByRole("region", {
            name: "Income breakdown details",
        });
        expect(details.tabIndex).toBe(0);
        expect(within(details).queryByText("Manual adjustment")).toBeNull();
        expect(within(details).queryByText("Total income")).toBeNull();
        expect(within(details).getAllByText("Old Ruins")).toHaveLength(2);
        expect(within(details).getAllByText(longDetail)).toHaveLength(30);
        expect(within(details).getAllByText("Boon")).toHaveLength(30);
        expect(within(details).getAllByText("-5¢")).toHaveLength(2);
        expect(within(details).getByText("+5¢")).toBeTruthy();
        expect(within(details).getByText(sources[29].name).textContent).toBe(
            sources[29].name,
        );
        expect(
            screen.getByText("Total income").parentElement!.textContent,
        ).toBe("Total income0¢");
    });
});
