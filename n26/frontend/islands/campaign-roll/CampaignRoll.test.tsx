import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CampaignRoll, type CampaignRollProps } from "./CampaignRoll";
import { mount } from "./entry";

const props: CampaignRollProps = {
    rolled: {
        label: "Your own roll",
        helpText: "Optional. Leave blank and the roll is made for you.",
        value: "",
        errors: [],
    },
    inputId: "starting-roll",
    table: "journal",
    tableErrors: [],
    tables: [
        {
            value: "journal",
            label: "Goliath Territories",
            die: "D6",
            lowest: 1,
            highest: 6,
        },
        {
            value: "selection",
            label: "Territory Selection Table",
            die: "D66",
            lowest: 11,
            highest: 66,
        },
    ],
    cancelUrl: "/n26/campaigns/1/",
};

const roll = () =>
    screen.getByRole("spinbutton", {
        name: "Your own roll",
    }) as HTMLInputElement;

describe("campaign roll", () => {
    it("names the act Roll until a roll is typed, then Use my roll", async () => {
        const user = userEvent.setup();
        render(<CampaignRoll {...props} />);
        expect(screen.getByRole("button", { name: "Roll" })).toHaveProperty(
            "type",
            "submit",
        );
        await user.type(roll(), "4");
        expect(
            screen.getByRole("button", { name: "Use my roll" }),
        ).toBeTruthy();
        await user.clear(roll());
        expect(screen.getByRole("button", { name: "Roll" })).toBeTruthy();
    });

    it("describes the selected table's die and follows the choice", async () => {
        const user = userEvent.setup();
        render(<CampaignRoll {...props} />);
        const description = roll().getAttribute("aria-describedby")!;
        const text = () => document.getElementById(description)!.textContent;
        expect(text()).toContain(props.rolled.helpText);
        expect(text()).toContain("A D6 roll is 1 to 6.");
        expect(text()).not.toContain("D66");
        await user.click(
            screen.getByRole("radio", { name: /Territory Selection Table/ }),
        );
        expect(text()).toContain("A D66 roll is 11 to 66.");
        expect(text()).not.toContain("A D6 roll");
    });

    it("submits the chosen table and typed roll under the form's names", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <CampaignRoll {...props} table="selection" />
            </form>,
        );
        await user.type(roll(), "63");
        const data = new FormData(view.container.querySelector("form")!);
        expect(data.get("table")).toBe("selection");
        expect(data.get("rolled")).toBe("63");
        expect(roll().id).toBe("starting-roll");
    });

    it("names a single table as settled and posts it hidden", () => {
        const view = render(
            <CampaignRoll
                {...props}
                tables={[props.tables[1]]}
                table="selection"
                tableErrors={["That table is not available here."]}
            />,
        );
        expect(screen.queryByRole("radio")).toBeNull();
        expect(screen.getByRole("definition").textContent).toBe(
            "Territory Selection Table · D66",
        );
        const hidden = view.container.querySelector<HTMLInputElement>(
            'input[type="hidden"][name="table"]',
        );
        expect(hidden?.value).toBe("selection");
        expect(view.container.textContent).toContain(
            "That table is not available here.",
        );
    });

    it("keeps a refused roll and its errors beside the field", () => {
        render(
            <CampaignRoll
                {...props}
                rolled={{
                    ...props.rolled,
                    value: "9",
                    errors: ["You cannot roll 9 on a D6."],
                }}
                tableErrors={["Select a table."]}
            />,
        );
        expect(roll().value).toBe("9");
        expect(roll().getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByRole("group", { name: "Table" }).textContent,
        ).toContain("Select a table.");
        expect(screen.getByText("You cannot roll 9 on a D6.")).toBeTruthy();
        expect(
            screen.getByRole("button", { name: "Use my roll" }),
        ).toBeTruthy();
    });

    it("links Cancel to the dialog's cancel address", () => {
        render(<CampaignRoll {...props} />);
        expect(
            screen.getByRole("link", { name: "Cancel" }).getAttribute("href"),
        ).toBe("/n26/campaigns/1/");
    });

    it("keeps a choice, a typed roll and focus made before it mounts", async () => {
        const host = document.createElement("div");
        host.innerHTML =
            '<input type="radio" name="table" value="journal">' +
            '<input type="radio" name="table" value="selection" checked>' +
            '<input name="rolled" value="34">';
        document.body.append(host);
        host.querySelector<HTMLInputElement>('[name="rolled"]')!.focus();
        let dispose: () => void;
        await act(async () => {
            dispose = mount(host, props);
        });
        await waitFor(() =>
            expect(
                screen.getByRole("button", { name: "Use my roll" }),
            ).toBeTruthy(),
        );
        expect(roll().value).toBe("34");
        expect(document.activeElement).toBe(roll());
        expect(
            host.querySelector<HTMLInputElement>('[name="table"]:checked')
                ?.value,
        ).toBe("selection");
        await act(async () => {
            dispose!();
        });
        host.remove();
    });
});
