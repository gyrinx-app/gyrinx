import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
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

test("asset dialog hrefs and ordinary clicks use the live view after a local change", async () => {
    window.history.replaceState(
        null,
        "",
        "/campaign/?sort=name&group=label%3Adivision",
    );
    const user = userEvent.setup();
    const open = vi.fn().mockResolvedValue(undefined);
    render(
        <CampaignViewLink
            href="/assets/assign/?sort=name&group=label%3Adivision"
            label="Assign"
            variant="ghost"
            className=""
            dialog
            onOpenDialog={open}
        />,
    );
    act(() => {
        window.history.replaceState(null, "", "/campaign/?sort=-rating&group=");
        window.dispatchEvent(new Event("n26:location-changed"));
    });
    const link = screen.getByRole("link", { name: "Assign" });
    expect(link.getAttribute("href")).toBe(
        "/assets/assign/?sort=-rating&group=",
    );
    fireEvent.click(link, { ctrlKey: true });
    expect(open).not.toHaveBeenCalled();
    await user.click(link);
    expect(open).toHaveBeenCalledWith("/assets/assign/?sort=-rating&group=");
});

test("territory details and actions preserve the independent inventory view", () => {
    window.history.replaceState(
        null,
        "",
        "/campaign/?sort=-rating&group=&asset_sort=-income&asset_group=holder",
    );
    render(
        <CampaignViewLink
            href="/assets/one/"
            label="Old Ruins"
            variant="default"
            className="font-semibold"
        />,
    );
    const link = screen.getByRole("link", { name: "Old Ruins" });
    expect(link.getAttribute("href")).toBe(
        "/assets/one/?sort=-rating&group=&asset_sort=-income&asset_group=holder",
    );
    act(() => {
        window.history.replaceState(null, "", "/campaign/?asset_group=");
        window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(link.getAttribute("href")).toBe("/assets/one/?asset_group=");
});
