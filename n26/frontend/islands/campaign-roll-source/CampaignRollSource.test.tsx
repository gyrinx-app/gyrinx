import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import {
    CampaignRollSource,
    type CampaignRollSourceProps,
} from "./CampaignRollSource";

const props: CampaignRollSourceProps = {
    source: "generated",
    rolled: "",
    choices: [
        { value: "generated", label: "Roll here" },
        { value: "manual", label: "Use physical dice" },
    ],
    sourceErrors: [],
    rolledErrors: [],
};

describe("campaign roll source", () => {
    it("enables and submits the physical result only for physical dice", async () => {
        const user = userEvent.setup();
        const view = render(
            <form>
                <CampaignRollSource {...props} />
            </form>,
        );
        const result = screen.getByRole("spinbutton", {
            name: "Physical result",
        }) as HTMLInputElement;
        const form = view.container.querySelector("form")!;
        expect(result.disabled).toBe(true);
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(
            screen.getByRole("radio", { name: "Use physical dice" }),
        );
        expect(result.disabled).toBe(false);
        expect(result.required).toBe(true);
        await user.type(result, "61");
        expect(new FormData(form).get("rolled")).toBe("61");
        await user.click(screen.getByRole("radio", { name: "Roll here" }));
        expect(result.disabled).toBe(true);
        expect(result.required).toBe(false);
        expect(new FormData(form).has("rolled")).toBe(false);
        await user.click(
            screen.getByRole("radio", { name: "Use physical dice" }),
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
            name: "Physical result",
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
});
