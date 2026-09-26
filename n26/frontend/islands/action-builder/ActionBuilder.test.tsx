import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ActionBuilder, type ActionBuilderProps } from "./ActionBuilder";

const props: ActionBuilderProps = {
    draft: "",
    counters: [{ value: "xp", label: "XP" }],
    rankTables: [{ value: "ranks", label: "Standard ranks", counter: "xp" }],
    slotTypes: [{ value: "tier", label: "Augmentation" }],
    slots: [{ value: "slot", label: "Advancement" }],
    outcomes: [],
};

describe("action builder", () => {
    it("normalises malformed returned drafts instead of crashing", async () => {
        const user = userEvent.setup();
        render(
            <ActionBuilder
                {...props}
                draft='{"name":null,"prices":null,"outcomes":[null,{"name":null,"changes":null}]}'
            />,
        );
        expect(
            (
                screen.getByRole("textbox", {
                    name: "Action name",
                }) as HTMLInputElement
            ).value,
        ).toBe("");
        await user.click(screen.getByRole("button", { name: "3. Outcomes" }));
        expect(
            screen.getByRole("textbox", { name: "Outcome 1 name" }),
        ).toBeTruthy();
    });

    it("blocks an unnamed action and an incomplete review", async () => {
        const user = userEvent.setup();
        render(<ActionBuilder {...props} />);
        await user.click(screen.getByRole("button", { name: "Continue →" }));
        expect(screen.getByRole("alert").textContent).toContain(
            "Name the action",
        );
        await user.type(
            screen.getByRole("textbox", { name: "Action name" }),
            "Suit Evolution",
        );
        await user.click(screen.getByRole("button", { name: "4. Review" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Create action",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        expect(screen.getByText("Add at least one outcome.")).toBeTruthy();
    });

    it("reorders outcomes and serialises the completed draft", async () => {
        const user = userEvent.setup();
        const { container } = render(<ActionBuilder {...props} />);
        await user.type(
            screen.getByRole("textbox", { name: "Action name" }),
            "Suit Evolution",
        );
        await user.click(screen.getByRole("button", { name: "2. Uses" }));
        await user.click(screen.getByRole("radio", { name: /No use price/ }));
        await user.click(screen.getByRole("button", { name: "3. Outcomes" }));
        await user.click(
            screen.getByRole("button", { name: "+ Create outcome" }),
        );
        await user.click(
            screen.getByRole("button", { name: "+ Create outcome" }),
        );
        await user.type(
            screen.getByRole("textbox", { name: "Outcome 1 name" }),
            "First tier",
        );
        await user.type(
            screen.getByRole("textbox", { name: "Outcome 2 name" }),
            "Second tier",
        );
        await user.selectOptions(
            screen.getByRole("combobox", { name: "Outcome 1 tier slot type" }),
            "tier",
        );
        await user.selectOptions(
            screen.getByRole("combobox", { name: "Outcome 2 tier slot type" }),
            "tier",
        );
        await user.click(
            screen.getAllByRole("button", { name: "Move outcome down" })[0],
        );
        await user.click(screen.getByRole("button", { name: "4. Review" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Create action",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(false);
        const draft = JSON.parse(
            (container.querySelector('input[name="draft"]') as HTMLInputElement)
                .value,
        );
        expect(
            draft.outcomes.map((outcome: { name: string }) => outcome.name),
        ).toEqual(["Second tier", "First tier"]);
        expect(draft.useMode).toBe("free");
    });

    it("blocks incomplete counter and picks changes on review", async () => {
        const user = userEvent.setup();
        render(
            <ActionBuilder
                {...props}
                draft={JSON.stringify({
                    name: "Repair",
                    useMode: "free",
                    outcomes: [
                        {
                            name: "Clear effects",
                            operation: "changes",
                            changes: [
                                { kind: "counter", counter: "", amount: "" },
                                { kind: "picks", slotType: "" },
                            ],
                        },
                    ],
                })}
            />,
        );
        await user.click(screen.getByRole("button", { name: "4. Review" }));
        expect(
            (
                screen.getByRole("button", {
                    name: "Create action",
                }) as HTMLButtonElement
            ).disabled,
        ).toBe(true);
        expect(
            screen.getByText(
                "Set the counter and amount for change 1 in outcome 1.",
            ),
        ).toBeTruthy();
        expect(
            screen.getByText("Choose a slot type for change 2 in outcome 1."),
        ).toBeTruthy();
    });

    it("prevents form submission until a valid review step", async () => {
        const user = userEvent.setup();
        const { container } = render(
            <form>
                <ActionBuilder
                    {...props}
                    draft={JSON.stringify({
                        name: "Repair",
                        useMode: "free",
                        outcomes: [
                            {
                                name: "Advance rig",
                                operation: "augment",
                                slotType: "tier",
                            },
                        ],
                    })}
                />
            </form>,
        );
        const form = container.querySelector("form")!;
        const submit = () =>
            form.dispatchEvent(
                new Event("submit", { bubbles: true, cancelable: true }),
            );
        expect(submit()).toBe(false);
        await user.click(screen.getByRole("button", { name: "4. Review" }));
        expect(submit()).toBe(true);
    });
});
