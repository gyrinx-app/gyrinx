import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { GangFigures, type GangFiguresData } from "./GangFigures";

const data: GangFiguresData = {
    items: [
        {
            short: "TP",
            label: "Trade Points",
            value: "—",
            absent: "No Visit Trading Post action open",
            href: "/trade/",
        },
        { short: "R", label: "Rating", value: "125¢", absent: "", href: "" },
        {
            short: "Cr",
            label: "Credits",
            value: "0¢",
            absent: "",
            href: "/credits/",
        },
        { short: "St", label: "Stash", value: "0¢", absent: "", href: "" },
        { short: "W", label: "Wealth", value: "125¢", absent: "", href: "" },
    ],
    roster: {
        count: 2,
        rating: 30,
        groups: [{ profile: "Ganger", category: "Fighter", count: 2 }],
        models: [
            { name: "Vex", rating: 10 },
            { name: "Sull", rating: 20 },
        ],
    },
};

describe("GangFigures", () => {
    it("keeps zero amounts, absent figures and the server's navigation", () => {
        render(<GangFigures data={data} />);
        expect(
            screen.getByRole("link", { name: "0¢" }).getAttribute("href"),
        ).toBe("/credits/");
        expect(
            screen
                .getByRole("link", {
                    name: "No Visit Trading Post action open",
                })
                .getAttribute("href"),
        ).toBe("/trade/");
        expect(
            screen.getByRole("button", {
                name: "Roster breakdown: 2 models in the gang",
            }),
        ).toBeTruthy();
        expect(screen.getAllByText("125¢")).toHaveLength(2);
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("opens the roster by keyboard, switches tables and restores trigger focus", async () => {
        const user = userEvent.setup();
        render(<GangFigures data={data} />);
        const trigger = screen.getByRole("button", {
            name: /Roster breakdown/,
        });
        await user.tab();
        expect(document.activeElement).toBe(trigger);
        await user.keyboard("{Enter}");
        expect(document.activeElement).toBe(
            screen.getByRole("tab", { name: "Profiles" }),
        );
        expect(
            screen.getByRole("table", { name: "Models by profile" })
                .textContent,
        ).toContain("GangerFighter2");
        await user.keyboard("{ArrowRight}");
        const ratings = screen.getByRole("tab", { name: "Ratings" });
        expect(document.activeElement).toBe(ratings);
        expect(ratings.getAttribute("aria-selected")).toBe("true");
        const table = screen.getByRole("table", { name: "Model ratings" });
        expect(within(table).getByText("Vex")).toBeTruthy();
        expect(within(table).getByText("Sull")).toBeTruthy();
        expect(within(table).getByText("30¢")).toBeTruthy();
        expect(within(table).queryByText("125¢")).toBeNull();
        await user.tab();
        expect(document.activeElement).toBe(screen.getByRole("tabpanel"));
        await user.tab({ shift: true });
        expect(document.activeElement).toBe(ratings);
        await user.keyboard("{Home}");
        expect(document.activeElement).toBe(
            screen.getByRole("tab", { name: "Profiles" }),
        );
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("dismisses the roster when focus moves outside", async () => {
        const user = userEvent.setup();
        render(
            <>
                <GangFigures data={data} />
                <button>Outside</button>
            </>,
        );
        await user.click(
            screen.getByRole("button", { name: /Roster breakdown/ }),
        );
        expect(
            screen.getByRole("dialog", { name: "Roster breakdown" }),
        ).toBeTruthy();
        await user.click(screen.getByRole("button", { name: "Outside" }));
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("explains absent figures on activation and returns focus on Escape", async () => {
        const user = userEvent.setup();
        render(<GangFigures data={data} />);
        const label = screen.getByRole("button", { name: "Trade Points" });
        await user.click(label);
        const help = screen.getByRole("dialog", { name: "Trade Points" });
        expect(
            within(help).getByText("No Visit Trading Post action open"),
        ).toBeTruthy();
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(label);
    });

    it("renders authoritative replacements and model names as text", async () => {
        const user = userEvent.setup();
        const view = render(<GangFigures data={data} />);
        await user.click(
            screen.getByRole("button", { name: /Roster breakdown/ }),
        );
        await user.click(screen.getByRole("tab", { name: "Ratings" }));
        view.rerender(
            <GangFigures
                data={{
                    ...data,
                    roster: {
                        count: 1,
                        rating: 0,
                        groups: [{ profile: "Ganger", category: "", count: 1 }],
                        models: [
                            { name: "<img src=x onerror=alert(1)>", rating: 0 },
                        ],
                    },
                }}
            />,
        );
        expect(
            screen.getByRole("button", {
                name: "Roster breakdown: 1 model in the gang",
            }),
        ).toBeTruthy();
        const table = screen.getByRole("table", { name: "Model ratings" });
        expect(
            within(table).getByText("<img src=x onerror=alert(1)>"),
        ).toBeTruthy();
        expect(table.querySelector("img")).toBeNull();
        expect(within(table).queryByText("Vex")).toBeNull();
        expect(within(table).getAllByText("0¢")).toHaveLength(2);
    });
});
