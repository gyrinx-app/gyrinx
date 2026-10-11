import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
    CampaignGangPicker,
    type CampaignGangPickerProps,
} from "./CampaignGangPicker";

const gang = (
    pk: string,
    name: string,
    owner: string,
    wealth: number,
    extra: Partial<CampaignGangPickerProps["gangs"][number]> = {},
) => ({
    pk,
    name,
    href: `/n26/gangs/${pk}/`,
    unlimited: false,
    budgetHref: "",
    owner,
    ownerLink: {
        name: owner,
        href: `/n26/users/@${owner}/`,
        badge: owner === "vex" ? "guilder" : null,
    },
    wealth,
    search: `${name} ${owner}`.toLowerCase(),
    playing: false,
    ...extra,
});

const props: CampaignGangPickerProps = {
    gangs: [
        gang("a", "Slag Kings", "vex", 1000),
        gang("b", "Wild Cats", "kesh", 400),
        gang("c", "Ash Rats", "kesh", 900, { playing: true }),
        gang("d", "Free Spirits", "vex", 200, {
            unlimited: true,
            budgetHref: "/n26/gangs/d/edit/#starting-credits",
        }),
    ],
    badges: {
        guilder: {
            label: "Guilder supporter",
            svg: { tag: "svg", props: { viewBox: "0 0 1 1" } },
        },
    },
    playerOptions: [
        { value: "kesh", label: "kesh" },
        { value: "vex", label: "vex" },
    ],
    wealthCeiling: 1000,
};

const rows = () =>
    screen
        .getAllByRole("listitem")
        .map((row) => within(row).getAllByRole("link")[0].textContent);
const count = () => screen.getByText(/of 4 gangs/).textContent;

describe("campaign gang picker", () => {
    it("starts with gangs already in a campaign hidden, and counts what shows", () => {
        render(<CampaignGangPicker {...props} />);
        expect(rows()).toEqual(["Slag Kings", "Wild Cats", "Free Spirits"]);
        expect(count()).toBe("3 of 4 gangs");
    });

    it("shows a playing gang without an Add when the toggle is off", async () => {
        const user = userEvent.setup();
        render(<CampaignGangPicker {...props} />);
        await user.click(
            screen.getByRole("switch", {
                name: "Hide gangs already in a campaign",
            }),
        );
        const ash = screen
            .getByRole("link", { name: "Ash Rats" })
            .closest("li")!;
        expect(within(ash).getByText("In a campaign")).toBeTruthy();
        expect(within(ash).queryByRole("button", { name: "Add" })).toBeNull();
        expect(count()).toBe("4 of 4 gangs");
    });

    it("searches names and owners, ignoring case and spaces", async () => {
        const user = userEvent.setup();
        render(<CampaignGangPicker {...props} />);
        await user.type(
            screen.getByRole("searchbox", { name: "Search gangs" }),
            "  KESH ",
        );
        expect(rows()).toEqual(["Wild Cats"]);
        await user.clear(
            screen.getByRole("searchbox", { name: "Search gangs" }),
        );
        await user.type(
            screen.getByRole("searchbox", { name: "Search gangs" }),
            "zzz",
        );
        expect(screen.queryAllByRole("listitem")).toHaveLength(0);
        expect(screen.getByText("No gangs match that.")).toBeTruthy();
    });

    it("narrows to the players applied in the filter", async () => {
        const user = userEvent.setup();
        render(<CampaignGangPicker {...props} />);
        await user.click(screen.getByRole("button", { name: /Player/ }));
        await user.click(
            screen.getByRole("button", { name: "Select only: vex" }),
        );
        await user.click(screen.getByRole("button", { name: "OK" }));
        expect(rows()).toEqual(["Slag Kings", "Free Spirits"]);
    });

    it("narrows to the wealth range", async () => {
        const user = userEvent.setup();
        render(<CampaignGangPicker {...props} />);
        await user.click(screen.getByRole("button", { name: /Wealth/ }));
        fireEvent.change(screen.getByRole("slider", { name: "Minimum" }), {
            target: { value: "300" },
        });
        fireEvent.change(screen.getByRole("slider", { name: "Maximum" }), {
            target: { value: "950" },
        });
        expect(rows()).toEqual(["Wild Cats"]);
    });

    it("names each owner with their badge and offers Add as the form's submit", () => {
        const view = render(
            <form>
                <CampaignGangPicker {...props} />
            </form>,
        );
        const kings = screen
            .getByRole("link", { name: "Slag Kings" })
            .closest("li")!;
        expect(
            within(kings).getByRole("img", { name: "Guilder supporter" }),
        ).toBeTruthy();
        expect(
            within(kings)
                .getByRole("link", { name: /vex/ })
                .getAttribute("href"),
        ).toBe("/n26/users/@vex/");
        const add = within(kings).getByRole("button", { name: "Add" });
        expect(add).toHaveProperty("type", "submit");
        const data = new FormData(
            view.container.querySelector("form")!,
            add as HTMLButtonElement,
        );
        expect(data.get("gang")).toBe("a");
        const spirits = screen
            .getByRole("link", { name: "Free Spirits" })
            .closest("li")!;
        expect(within(spirits).getByText(/Unlimited credits/)).toBeTruthy();
        expect(
            within(spirits)
                .getByRole("link", { name: "Review credits budget" })
                .getAttribute("href"),
        ).toBe("/n26/gangs/d/edit/#starting-credits");
    });

    it("draws no owner, player filter or wealth range where none applies", () => {
        render(
            <CampaignGangPicker
                gangs={[gang("a", "Slag Kings", "vex", 0, { ownerLink: null })]}
                badges={{}}
                playerOptions={[]}
                wealthCeiling={0}
            />,
        );
        expect(screen.queryByRole("button", { name: /Player/ })).toBeNull();
        expect(screen.queryByRole("button", { name: /Wealth/ })).toBeNull();
        expect(screen.getAllByRole("link")).toHaveLength(1);
        expect(screen.getByText(/of 1 gang$/)).toBeTruthy();
    });
});
