import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Catalogue } from "./Catalogue";
import type { CatalogueData, HireEntry } from "./types";

const ganger: HireEntry = {
    key: "ganger-offer",
    name: "Ganger",
    profileType: "Fighter",
    basePrice: 60,
    previewHref: "/preview/?entry=offer",
    confirmationHref: "/hire/?hire=ganger-offer&section=Fighters",
    groups: [
        {
            choose: "one",
            offersChoice: true,
            options: [
                {
                    key: "knife",
                    name: "Knife",
                    price: 0,
                    totalPrice: 60,
                    default: true,
                },
                {
                    key: "sword",
                    name: "Sword",
                    price: 25,
                    totalPrice: 85,
                    default: false,
                },
            ],
        },
        {
            choose: "any",
            offersChoice: true,
            options: [
                {
                    key: "armour",
                    name: "Armour",
                    price: 10,
                    totalPrice: 70,
                    default: false,
                },
            ],
        },
    ],
};
const data: CatalogueData = {
    scope: "gang",
    scopeLabel: "Gang list",
    section: "Fighters",
    listingHref: "/hire/",
    scopeTabs: [
        { key: "gang", label: "Gang list", href: "/hire/" },
        { key: "all", label: "All profiles", href: "/hire/?list=all" },
    ],
    priceFloor: 10,
    priceCeiling: 60,
    categories: ["Gangers", "Beasts", "Uncategorised"],
    categoryOptions: ["Gangers", "Beasts"],
    sections: [
        {
            name: "Fighters",
            categories: [{ name: "Gangers", entries: [ganger] }],
        },
        {
            name: "Beasts",
            categories: [
                {
                    name: "Beasts",
                    entries: [
                        {
                            ...ganger,
                            key: "mastiff",
                            name: "Mastiff",
                            basePrice: 10,
                            groups: [],
                        },
                    ],
                },
            ],
        },
        {
            name: "Uncategorised",
            categories: [
                {
                    name: "",
                    entries: [
                        {
                            ...ganger,
                            key: "drifter",
                            name: "Drifter",
                            basePrice: 30,
                            groups: [],
                        },
                    ],
                },
            ],
        },
    ],
};

beforeEach(() =>
    window.history.replaceState(null, "", "/n26/gangs/gang/hire/"),
);
afterEach(() => vi.unstubAllGlobals());
const desktopTabs = () =>
    within(screen.getAllByRole("tablist", { name: "Profile sections" })[0]);

describe("Hire catalogue", () => {
    it("changes the displayed selection and confirmation URL without fetching previews", async () => {
        const user = userEvent.setup();
        const fetcher = vi.fn();
        vi.stubGlobal("fetch", fetcher);
        render(<Catalogue {...data} />);
        await user.click(screen.getByRole("radio", { name: /Sword/ }));
        await user.click(screen.getByRole("checkbox", { name: /Armour/ }));
        expect(screen.getByText("95¢")).toBeTruthy();
        const href = new URL(
            screen
                .getByRole("link", { name: "Hire Ganger" })
                .getAttribute("href")!,
            window.location.origin,
        );
        expect(href.searchParams.get("hire")).toBe("ganger-offer");
        expect(JSON.parse(href.searchParams.get("selection")!)).toEqual([
            "sword",
            "armour",
        ]);
        expect(href.searchParams.get("section")).toBe("Fighters");
        expect(fetcher).not.toHaveBeenCalled();
    });

    it("expands category groups without expanding or loading model cards", async () => {
        const user = userEvent.setup();
        const fetcher = vi.fn();
        vi.stubGlobal("fetch", fetcher);
        render(<Catalogue {...data} />);
        await user.click(screen.getByRole("radio", { name: /Sword/ }));
        await user.click(screen.getByRole("button", { name: "Collapse all" }));
        expect(screen.queryByRole("link", { name: "Hire Ganger" })).toBeNull();
        await user.click(screen.getByRole("button", { name: "Expand all" }));
        expect(screen.getByRole("link", { name: "Hire Ganger" })).toBeTruthy();
        expect(
            (screen.getByRole("radio", { name: /Sword/ }) as HTMLInputElement)
                .checked,
        ).toBe(true);
        expect(
            screen
                .getByRole("button", { name: "Show card for Ganger" })
                .getAttribute("aria-expanded"),
        ).toBe("false");
        expect(fetcher).not.toHaveBeenCalled();
    });

    it("search temporarily reveals a collapsed category and then restores its disclosure", async () => {
        const user = userEvent.setup();
        render(<Catalogue {...data} />);
        await user.click(screen.getByRole("button", { name: "Gangers" }));
        expect(screen.queryByRole("link", { name: "Hire Ganger" })).toBeNull();
        await user.type(screen.getByRole("searchbox"), "ganger");
        expect(screen.getByRole("link", { name: "Hire Ganger" })).toBeTruthy();
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(screen.queryByRole("link", { name: "Hire Ganger" })).toBeNull();
    });

    it("retains the chosen section while filtering temporarily shows another", async () => {
        const user = userEvent.setup();
        render(<Catalogue {...data} />);
        await user.click(desktopTabs().getByRole("tab", { name: /Beasts/ }));
        expect(new URLSearchParams(window.location.search).get("section")).toBe(
            "Beasts",
        );
        await user.type(screen.getByRole("searchbox"), "ganger");
        expect(screen.getByRole("link", { name: "Hire Ganger" })).toBeTruthy();
        expect(new URLSearchParams(window.location.search).get("section")).toBe(
            "Beasts",
        );
        await user.click(screen.getByRole("button", { name: "Clear search" }));
        expect(screen.getByRole("link", { name: "Hire Mastiff" })).toBeTruthy();
    });

    it("searches the type and section without losing category-less rows", async () => {
        const user = userEvent.setup();
        const submit = vi.fn((event) => event.preventDefault());
        render(
            <form onSubmit={submit}>
                <Catalogue {...data} />
            </form>,
        );
        await user.type(
            screen.getByRole("searchbox"),
            "Fighter Uncategorised{Enter}",
        );
        expect(screen.getByRole("link", { name: "Hire Drifter" })).toBeTruthy();
        expect(submit).not.toHaveBeenCalled();
    });

    it("supports keyboard section selection and browser history restoration", async () => {
        const user = userEvent.setup();
        render(<Catalogue {...data} />);
        const first = desktopTabs().getByRole("tab", { name: /Fighters/ });
        first.focus();
        await user.keyboard("{ArrowRight}");
        const beasts = desktopTabs().getByRole("tab", { name: /Beasts/ });
        expect(document.activeElement).toBe(beasts);
        expect(beasts.getAttribute("aria-selected")).toBe("true");
        expect(
            fireEvent.keyDown(beasts, { key: "ArrowLeft", altKey: true }),
        ).toBe(true);
        expect(beasts.getAttribute("aria-selected")).toBe("true");
        await user.keyboard("{End}");
        expect(screen.getByRole("link", { name: "Hire Drifter" })).toBeTruthy();
        act(() => {
            window.history.replaceState(null, "", "?section=Fighters");
            window.dispatchEvent(new PopStateEvent("popstate"));
        });
        expect(screen.getByRole("link", { name: "Hire Ganger" })).toBeTruthy();
    });

    it("chooses a section through the phone overflow menu without a read request", async () => {
        const user = userEvent.setup();
        const fetcher = vi.fn();
        vi.stubGlobal("fetch", fetcher);
        render(<Catalogue {...data} />);
        await user.click(
            screen.getByRole("button", { name: "Other sections" }),
        );
        await user.click(screen.getByRole("menuitem", { name: "Beasts" }));
        expect(screen.getByRole("link", { name: "Hire Mastiff" })).toBeTruthy();
        expect(new URLSearchParams(window.location.search).get("section")).toBe(
            "Beasts",
        );
        expect(fetcher).not.toHaveBeenCalled();
    });
});
