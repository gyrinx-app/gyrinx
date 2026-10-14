import { act, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { CampaignViewLink } from "./entry";

test("asset navigation uses the live table view and restores the default on Back", () => {
    window.history.replaceState(null, "", "/campaign/?sort=-rating&group=");
    const view = render(
        <CampaignViewLink
            href="/assets/add/?type=territory&sort=name&group=old"
            label="Add territories"
            variant="default"
            className=""
        />,
    );
    const link = screen.getByRole("link", { name: "Add territories" });
    expect(link.getAttribute("href")).toBe(
        "/assets/add/?type=territory&sort=-rating&group=",
    );
    act(() => {
        window.history.replaceState(
            null,
            "",
            "/campaign/?sort=-wealth&group=label%3Adivision",
        );
        window.dispatchEvent(new Event("n26:location-changed"));
    });
    expect(link.getAttribute("href")).toBe(
        "/assets/add/?type=territory&sort=-wealth&group=label%3Adivision",
    );
    act(() => {
        window.history.replaceState(null, "", "/campaign/");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(link.getAttribute("href")).toBe("/assets/add/?type=territory");
    view.unmount();
});
