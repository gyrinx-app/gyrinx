import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GalleryNav, type GalleryNavProps } from "./GalleryNav";
import { mount } from "./entry";

const component = (slug: string, group: string, extra = {}) => ({
    slug,
    href: `/n26/design/c/${slug}/`,
    current: false,
    usesReact: false,
    parts: 0,
    term: `${slug} c-ui.${slug} ${group}`.toLowerCase(),
    ...extra,
});

const props: GalleryNavProps = {
    pages: [
        { label: "Overview", href: "/n26/design/", current: false },
        { label: "Tokens", href: "/n26/design/tokens/", current: false },
    ],
    shell: { label: "App shell", href: "/n26/design/shell/" },
    groups: [
        {
            name: "Actions",
            href: "/n26/design/#actions",
            current: true,
            components: [
                component("button", "Actions", { current: true, parts: 2 }),
                component("dropdown", "Actions", { usesReact: true }),
            ],
        },
        {
            name: "Forms",
            href: "/n26/design/#forms",
            current: false,
            components: [component("input", "Forms")],
        },
    ],
};

const filter = () =>
    screen.getByRole("searchbox", { name: "Filter components" });

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
    vi.restoreAllMocks();
});

describe("gallery nav", () => {
    it("lists the pages, groups and components with the current one marked", () => {
        render(<GalleryNav {...props} />);
        expect(
            screen.getByRole("link", { name: "Overview" }).getAttribute("href"),
        ).toBe("/n26/design/");
        expect(screen.getByRole("link", { name: "App shell" })).toBeTruthy();
        const button = screen.getByRole("link", { name: /^button/ });
        expect(button.getAttribute("aria-current")).toBe("page");
        expect(button.className).toContain("nav-current");
        expect(button.textContent).toContain("+2");
        expect(
            screen
                .getByRole("link", { name: /dropdown/ })
                .querySelector("svg")
                ?.getAttribute("aria-label"),
        ).toBe("Uses React");
        expect(
            screen.getByRole("link", { name: "Actions" }).className,
        ).toContain("text-ink-900");
        expect(screen.getByRole("link", { name: "Forms" }).className).toContain(
            "text-muted",
        );
    });

    it("scrolls the current component into view on mount", () => {
        render(<GalleryNav {...props} />);
        expect(Element.prototype.scrollIntoView).toHaveBeenCalledWith({
            block: "nearest",
        });
    });

    it("narrows to matching components, hides empty groups and the pages", async () => {
        const user = userEvent.setup();
        render(<GalleryNav {...props} />);
        await user.type(filter(), "  FORMS ");
        expect(screen.queryByRole("link", { name: "Overview" })).toBeNull();
        expect(screen.queryByRole("link", { name: "Actions" })).toBeNull();
        expect(screen.getByRole("link", { name: "input" })).toBeTruthy();
        await user.clear(filter());
        expect(screen.getByRole("link", { name: "Overview" })).toBeTruthy();
        expect(
            screen.getAllByRole("link", { name: /button|dropdown|input/ }),
        ).toHaveLength(3);
    });

    it("says what was typed when nothing matches", async () => {
        const user = userEvent.setup();
        render(<GalleryNav {...props} />);
        await user.type(filter(), "zz<b>");
        expect(screen.getByText("Nothing matches “zz<b>”.")).toBeTruthy();
        expect(screen.queryAllByRole("link")).toHaveLength(0);
    });

    it("keeps a filter typed, and focus, before it mounts", async () => {
        const host = document.createElement("div");
        host.innerHTML = '<input id="component-filter" value="inp">';
        document.body.append(host);
        host.querySelector<HTMLInputElement>("#component-filter")!.focus();
        let dispose: () => void;
        await act(async () => {
            dispose = mount(host, props);
        });
        await waitFor(() => expect(filter()).toHaveProperty("value", "inp"));
        expect(document.activeElement).toBe(filter());
        expect(screen.queryByRole("link", { name: /button/ })).toBeNull();
        await act(async () => {
            dispose!();
        });
        host.remove();
    });
});
