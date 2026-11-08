import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ModelPreview, type ModelPreviewProps } from "./ModelPreview";

const stat = {
    shortName: "T",
    fullName: "Toughness",
    value: "4",
    highlighted: false,
    firstOfGroup: false,
    explanation: "T changed by Armour. Cannot get any better.",
};
const line = { text: "Mesh armour", explanation: "From Harness", choices: [] };
const sample: ModelPreviewProps = {
    name: "Agent <One>",
    rating: 125,
    profileName: "Gang leader",
    ownerLine: "",
    typeLine: "Fighter (Leader)",
    xp: 0,
    xpTarget: "–",
    typeSpan: 1,
    statGroups: [[stat]],
    details: [
        {
            label: "Skills",
            parts: [
                { kind: "names", lines: [] },
                { kind: "choice", chosen: null, prompt: "Choose skills" },
            ],
        },
        { label: "Tally", parts: [{ kind: "counter", value: 0 }] },
        { label: "Gear", parts: [{ kind: "gear", lines: [line] }] },
        {
            label: "Allegiance",
            parts: [
                { kind: "choice", chosen: "Alpha", prompt: "Add" },
                { kind: "choice", chosen: null, prompt: "Choose" },
            ],
        },
    ],
    weaponColumns: [{ ...stat, explanation: "" }],
    weapons: [
        {
            name: "Launcher* (Fang)",
            stats: [],
            traits: [],
            profiles: [
                {
                    name: "Focused",
                    stats: [{ ...stat, value: "6", explanation: "" }],
                    traits: [
                        { text: "Accurate", explanation: "", choices: [] },
                    ],
                },
            ],
            accessories: [{ text: "Sight", explanation: "", choices: [] }],
            choices: [{ label: "Channel", values: ["Blue", "—"] }],
        },
    ],
};

describe("model preview", () => {
    it("shows a numeric zero XP target", () => {
        render(<ModelPreview {...sample} xp={3} xpTarget={0} />);
        const stats = screen.getByRole("table", { name: "Characteristics" });
        expect(within(stats).getByText("3").closest("td")?.textContent).toBe(
            "3/0",
        );
    });

    it("preserves formatted stats, weapons, choices and zero values", () => {
        render(<ModelPreview {...sample} />);
        const stats = screen.getByRole("table", { name: "Characteristics" });
        expect(
            within(stats).getByRole("columnheader", { name: "T" }).title,
        ).toBe("Toughness");
        expect(within(stats).getByText("Fighter (Leader)")).toBeTruthy();
        expect(screen.getByText("Choose skills")).toBeTruthy();
        expect(screen.getByText("Alpha").parentElement?.textContent).toBe(
            "Alpha Add",
        );
        expect(screen.getByText("Tally").nextElementSibling?.textContent).toBe(
            "0",
        );
        const weapons = screen.getByRole("table", { name: "Weapons" });
        expect(
            within(weapons)
                .getByText("Launcher* (Fang)")
                .closest("td")
                ?.getAttribute("colspan"),
        ).toBe("99");
        expect(within(weapons).getByText("Focused")).toBeTruthy();
        expect(within(weapons).getByText("6")).toBeTruthy();
        expect(within(weapons).getByText("Accurate")).toBeTruthy();
        expect(within(weapons).getByText("Sight")).toBeTruthy();
        expect(
            within(weapons).getByText("Channel:").closest("li")?.textContent,
        ).toBe("Channel: Blue, —");
    });

    it("makes modifier and provenance explanations available from the keyboard", async () => {
        const user = userEvent.setup();
        render(<ModelPreview {...sample} />);
        const trigger = screen.getByRole("button", {
            name: "4",
        });
        trigger.focus();
        await user.keyboard("{Enter}");
        const panel = screen.getByRole("tooltip");
        expect(within(panel).getByText(stat.explanation)).toBeTruthy();
        await user.keyboard("{Escape}");
        expect(document.activeElement).toBe(trigger);
        await user.click(screen.getByRole("button", { name: "Mesh armour" }));
        expect(screen.getByRole("tooltip").textContent).toBe("From Harness");
    });

    it("renders all supplied content as text and exposes no editing controls", () => {
        const text = '<img src=x onerror="window.bad=true">';
        const { container } = render(
            <ModelPreview
                {...sample}
                name={text}
                weapons={[]}
                details={[
                    {
                        label: "Rules",
                        parts: [{ kind: "names", lines: [{ ...line, text }] }],
                    },
                ]}
            />,
        );
        expect(screen.getAllByText(text)).toHaveLength(2);
        expect(container.querySelector("img, script, input, form")).toBeNull();
        expect(screen.queryByRole("table", { name: "Weapons" })).toBeNull();
        expect(
            screen.queryByRole("button", { name: /Save|Hire|Change/ }),
        ).toBeNull();
    });
});
