import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
    CampaignRollSource,
    type CampaignRollSourceProps,
} from "./CampaignRollSource";

const props: CampaignRollSourceProps = {
    requestKey: "9db976dd-3e3e-4392-84ee-dfa3dd31a1bd",
    source: "generated",
    rolled: "",
    choices: [
        { value: "generated", label: "Generate a roll" },
        { value: "manual", label: "I already rolled" },
    ],
    sourceErrors: [],
    rolledErrors: [],
    count: "1",
    countErrors: [],
    maxDice: 20,
    modifier: "",
    modifierErrors: [],
    modifierApplication: "total",
    modifierApplicationErrors: [],
    modifierChoices: [
        { value: "total", label: "Total" },
        { value: "each", label: "Each die" },
    ],
};

describe("campaign roll source", () => {
    it("starts a fresh submission when browser Back restores the form", () => {
        const view = render(
            <form>
                <CampaignRollSource {...props} />
            </form>,
        );
        const form = view.container.querySelector("form")!;
        expect(new FormData(form).get("request_key")).toBe(props.requestKey);
        act(() =>
            window.dispatchEvent(
                new PageTransitionEvent("pageshow", { persisted: false }),
            ),
        );
        expect(new FormData(form).get("request_key")).toBe(props.requestKey);
        act(() =>
            window.dispatchEvent(
                new PageTransitionEvent("pageshow", { persisted: true }),
            ),
        );
        expect(new FormData(form).get("request_key")).not.toBe(
            props.requestKey,
        );
    });

    it("enables and submits the physical result only for physical dice", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <CampaignRollSource {...props} />
            </form>,
        );
        const result = screen.getByRole("spinbutton", {
            name: "Result if already rolled",
        }) as HTMLInputElement;
        const form = view.container.querySelector("form")!;
        const manualRadio = screen.getByRole("radio", {
            name: "I already rolled",
        });
        expect(manualRadio.closest("label")!.contains(result)).toBe(false);
        expect(
            manualRadio.closest("label")!.parentElement!.contains(result),
        ).toBe(true);
        expect(result.disabled).toBe(true);
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(
            screen.getByRole("radio", { name: "I already rolled" }),
        );
        expect(result.disabled).toBe(false);
        expect(result.required).toBe(true);
        await user.type(result, "61");
        expect(new FormData(form).get("rolled")).toBe("61");
        await user.click(
            screen.getByRole("radio", { name: "Generate a roll" }),
        );
        expect(result.disabled).toBe(true);
        expect(result.required).toBe(false);
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(
            screen.getByRole("radio", { name: "I already rolled" }),
        );
        expect(result.value).toBe("61");
    });

    it("restores a submitted physical result and its validation error", () => {
        render(
            <CampaignRollSource
                {...props}
                source="manual"
                rolled="17"
                rolledErrors={[
                    "Enter a D66 result with both digits from 1 to 6.",
                ]}
            />,
        );
        const result = screen.getByRole("spinbutton", {
            name: "Result if already rolled",
        }) as HTMLInputElement;
        expect(result.disabled).toBe(false);
        expect(result.value).toBe("17");
        expect(result.getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByText(
                "Enter a D66 result with both digits from 1 to 6.",
            ),
        ).toBeTruthy();
    });
    it("records a manual total with a modifier applied to each die", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <CampaignRollSource {...props} />
            </form>,
        );
        const count = screen.getByRole("spinbutton", {
            name: "Number of dice *",
        });
        await user.clear(count);
        await user.type(count, "3");
        await user.click(
            screen.getByRole("radio", { name: "I already rolled" }),
        );
        const total = screen.getByRole("spinbutton", {
            name: "Total before modifiers",
        });
        await user.type(total, "12");
        await user.type(
            screen.getByRole("spinbutton", { name: "Modifier" }),
            "-2",
        );
        await user.click(screen.getByRole("radio", { name: "Each die" }));
        expect(
            screen.getByText(
                "The total includes the modifier once for each die.",
            ),
        ).toBeTruthy();
        const form = view.container.querySelector("form")!;
        expect(Object.fromEntries(new FormData(form))).toMatchObject({
            count: "3",
            rolled: "12",
            modifier: "-2",
            modifier_application: "each",
        });
        await user.click(
            screen.getByRole("radio", { name: "Generate a roll" }),
        );
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(
            screen.getByRole("radio", { name: "I already rolled" }),
        );
        expect((total as HTMLInputElement).value).toBe("12");
    });

    it("keeps invalid quantities and server errors visible", () => {
        render(
            <CampaignRollSource
                {...props}
                count="21"
                countErrors={["Ensure this value is less than or equal to 20."]}
            />,
        );
        const count = screen.getByRole("spinbutton", {
            name: "Number of dice *",
        }) as HTMLInputElement;
        expect(count.value).toBe("21");
        expect(count.max).toBe("20");
        expect(count.getAttribute("aria-invalid")).toBe("true");
        expect(
            (screen.getByRole("radio", { name: "Total" }) as HTMLInputElement)
                .checked,
        ).toBe(true);
    });
});
