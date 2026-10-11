import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
    CampaignRollAttribution,
    type CampaignRollAttributionProps,
} from "./CampaignRollAttribution";

const props: CampaignRollAttributionProps = {
    gang: "",
    miniature: "",
    gangErrors: [],
    miniatureErrors: [],
    gangs: [
        { value: "a", label: "Ashen Choir" },
        { value: "b", label: "Wild Cats" },
    ],
    models: [
        { value: "1", label: "Skabb", gang: "a" },
        { value: "2", label: "Mags", gang: "b" },
    ],
};

describe("campaign roll attribution", () => {
    it("limits models to the selected gang and clears the model on gang changes", () => {
        const view = render(
            <form>
                <CampaignRollAttribution {...props} />
            </form>,
        );
        const gang = screen.getByRole("combobox", { name: "Gang" });
        const model = screen.getByRole("combobox", {
            name: "Model",
        }) as HTMLSelectElement;
        expect(model.disabled).toBe(true);
        fireEvent.change(gang, { target: { value: "a" } });
        expect(model.disabled).toBe(false);
        expect(screen.getByRole("option", { name: "Skabb" })).toBeTruthy();
        expect(screen.queryByRole("option", { name: "Mags" })).toBeNull();
        fireEvent.change(model, { target: { value: "1" } });
        expect(
            new FormData(view.container.querySelector("form")!).get(
                "miniature",
            ),
        ).toBe("1");
        fireEvent.change(gang, { target: { value: "b" } });
        expect(model.value).toBe("");
        expect(screen.queryByRole("option", { name: "Skabb" })).toBeNull();
        fireEvent.change(gang, { target: { value: "" } });
        expect(model.disabled).toBe(true);
    });

    it("preserves selected attribution and displays server errors", () => {
        render(
            <CampaignRollAttribution
                {...props}
                gang="a"
                miniature="1"
                miniatureErrors={[
                    "Select a model currently in the related gang.",
                ]}
            />,
        );
        const model = screen.getByRole("combobox", {
            name: "Model",
        }) as HTMLSelectElement;
        expect(model.value).toBe("1");
        expect(model.getAttribute("aria-invalid")).toBe("true");
        expect(
            screen.getByText("Select a model currently in the related gang."),
        ).toBeTruthy();
    });

    it("allows gang-only attribution when the gang has no models", () => {
        render(<CampaignRollAttribution {...props} gang="a" models={[]} />);
        expect(screen.getByText("No models in this gang.")).toBeTruthy();
        expect(
            screen.getByRole("option", { name: "No related model" }),
        ).toBeTruthy();
    });
});
