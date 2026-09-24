import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mount } from "../islands/quick-switcher/entry";
import { QuickSwitcher, type QuickSwitcherProps } from "./QuickSwitcher";

function rows(prefix: string, count: number, start = 0) {
    return Array.from({ length: count }, (_, index) => ({
        label: `${prefix} ${String(start + index).padStart(2, "0")}`,
        href: `/${prefix.toLowerCase()}/${start + index}/`,
    }));
}

const base: QuickSwitcherProps = {
    label: "The Ashen Choir",
    href: "/gangs/ashen/",
    heading: "Your gangs",
    menuLabel: "Switch to another gang",
    placeholder: "Search gangs",
    empty: "No gangs match",
    align: "start",
    minWidth: "16rem",
    hotkey: "f",
    items: [
        { label: "The Ashen Choir", href: "/gangs/ashen/" },
        { label: "Pit of Teeth", href: "/gangs/pit/" },
    ],
    current: "/gangs/ashen/",
    source: "",
    next: null,
};

function respond(
    pages: Record<string, { items: object[]; next: number | null }>,
) {
    const fetchMock = vi.fn(async (input: string) => {
        const url = new URL(input);
        const key = `${url.searchParams.get("q")}@${url.searchParams.get("offset")}`;
        const page = pages[key];
        if (!page) return new Response("missing", { status: 404 });
        return new Response(JSON.stringify(page), {
            headers: { "Content-Type": "application/json" },
        });
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
}

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

function menuRows() {
    return screen.queryAllByRole("menuitem").map((row) => row.textContent);
}

describe("quick switcher", () => {
    it("names the current place and opens onto its list", async () => {
        const user = userEvent.setup();
        render(<QuickSwitcher {...base} />);

        expect(
            screen
                .getByRole("link", { name: "The Ashen Choir" })
                .getAttribute("href"),
        ).toBe("/gangs/ashen/");
        const chevron = screen.getByRole("button", {
            name: "Switch to another gang",
        });
        expect(chevron.getAttribute("title")).toBe(
            "Switch to another gang (⌥⇧F)",
        );
        expect(chevron.getAttribute("aria-keyshortcuts")).toBe("Alt+Shift+F");

        await user.click(chevron);
        expect(document.activeElement).toBe(
            screen.getByRole("searchbox", { name: "Search gangs" }),
        );
        expect(menuRows()).toEqual(["The Ashen Choir", "Pit of Teeth"]);
        const here = screen.getByRole("menuitem", { name: "The Ashen Choir" });
        expect(here.getAttribute("aria-current")).toBe("page");
        expect(
            screen
                .getByRole("menuitem", { name: "Pit of Teeth" })
                .getAttribute("aria-current"),
        ).toBeNull();
    });

    it("searches a fixed list without asking the server", async () => {
        const fetchMock = respond({});
        const user = userEvent.setup();
        render(<QuickSwitcher {...base} />);
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );

        await user.keyboard("pit");
        expect(menuRows()).toEqual(["Pit of Teeth"]);
        await user.keyboard("zzz");
        expect(menuRows()).toEqual([]);
        expect(screen.getByText("No gangs match")).toBeTruthy();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("reads the next page when the list runs out, without repeating a row", async () => {
        const first = rows("Gang", 3);
        const fetchMock = respond({
            // The current row was rescued into the first page and comes
            // round again in its own place.
            "@3": { items: [...rows("Gang", 3, 3), first[0]], next: 6 },
            "@6": { items: rows("Gang", 1, 6), next: null },
        });
        const user = userEvent.setup();
        render(
            <QuickSwitcher
                {...base}
                items={first}
                current={first[0].href}
                source="/n26/switcher/gangs/"
                next={3}
            />,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );

        await waitFor(() => expect(menuRows()).toHaveLength(7));
        expect(menuRows()).toEqual(rows("Gang", 7).map((row) => row.label));
        expect(fetchMock).toHaveBeenCalledTimes(2);
        const asked = fetchMock.mock.calls.map(([url]) => new URL(url));
        expect(asked[0].pathname).toBe("/n26/switcher/gangs/");
        expect(asked.map((url) => url.searchParams.get("offset"))).toEqual([
            "3",
            "6",
        ]);
    });

    it("asks the server to search, and shows the list again when cleared", async () => {
        const fetchMock = respond({
            "pit@0": {
                items: [{ label: "Pit of Teeth", href: "/gangs/pit/" }],
                next: null,
            },
            "zed@0": {
                items: [{ label: "Zed's Last", href: "/gangs/zed/" }],
                next: null,
            },
        });
        // A panel taller than its rows would read the next page at once.
        vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
            1000,
        );
        vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(
            300,
        );
        const user = userEvent.setup();
        render(
            <QuickSwitcher {...base} source="/n26/switcher/gangs/" next={2} />,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );

        await user.keyboard("zed");
        await waitFor(() => expect(menuRows()).toEqual(["Zed's Last"]));

        await user.clear(screen.getByRole("searchbox"));
        expect(menuRows()).toEqual(["The Ashen Choir", "Pit of Teeth"]);

        await user.keyboard("pit");
        // Narrowed at once from what is loaded, then the server's answer.
        expect(menuRows()).toEqual(["Pit of Teeth"]);
        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
        expect(
            fetchMock.mock.calls.map(([url]) =>
                new URL(url).searchParams.get("q"),
            ),
        ).toEqual(["zed", "pit"]);
    });

    it("searches a list it already holds whole without the server", async () => {
        const fetchMock = respond({});
        const user = userEvent.setup();
        render(<QuickSwitcher {...base} source="/n26/switcher/gangs/" />);
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );

        await user.keyboard("pit");
        expect(menuRows()).toEqual(["Pit of Teeth"]);
        expect(screen.queryByRole("status")).toBeNull();
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("keeps the row being viewed in a server search the source cannot answer", async () => {
        // A gang sheet anyone can read: the source lists only the reader's own.
        respond({ "ashen@0": { items: [], next: null } });
        vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
            1000,
        );
        vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(
            300,
        );
        const user = userEvent.setup();
        render(
            <QuickSwitcher {...base} source="/n26/switcher/gangs/" next={2} />,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        await user.keyboard("ashen");
        await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
        expect(menuRows()).toEqual(["The Ashen Choir"]);
    });

    it("drops the highlight when a new search answer arrives", async () => {
        respond({
            "p@0": {
                items: [
                    { label: "Pale Riders", href: "/gangs/pale/" },
                    { label: "Pit of Teeth", href: "/gangs/pit/" },
                ],
                next: null,
            },
        });
        vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
            1000,
        );
        vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(
            300,
        );
        Element.prototype.scrollIntoView = vi.fn();
        const user = userEvent.setup();
        render(
            <QuickSwitcher {...base} source="/n26/switcher/gangs/" next={2} />,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        await user.keyboard("p{ArrowDown}");
        const box = screen.getByRole("searchbox");
        expect(box.getAttribute("aria-activedescendant")).not.toBeNull();
        await waitFor(() => expect(menuRows()).toHaveLength(2));
        expect(box.getAttribute("aria-activedescendant")).toBeNull();
    });

    it("follows new items when its list has no source", async () => {
        const user = userEvent.setup();
        const { rerender } = render(<QuickSwitcher {...base} />);
        rerender(<QuickSwitcher {...base} items={base.items.slice(1)} />);
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        expect(menuRows()).toEqual(["Pit of Teeth"]);
    });

    it("offers a retry when a page does not load", async () => {
        const fetchMock = respond({});
        const user = userEvent.setup();
        render(
            <QuickSwitcher {...base} source="/n26/switcher/gangs/" next={2} />,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        vi.spyOn(console, "error").mockImplementation(() => {});

        const alert = await screen.findByRole("alert");
        expect(alert.textContent).toContain("The list did not load.");
        expect(menuRows()).toEqual(["The Ashen Choir", "Pit of Teeth"]);

        respond({ "@2": { items: rows("Gang", 1, 9), next: null } });
        await user.click(screen.getByRole("button", { name: "Try again" }));
        await waitFor(() => expect(menuRows()).toHaveLength(3));
        expect(screen.queryByRole("alert")).toBeNull();
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("walks the rows from the keyboard and follows the highlighted one", async () => {
        // jsdom lays nothing out, so it has no scrollIntoView.
        const scrolled = vi.fn();
        Element.prototype.scrollIntoView = scrolled;
        const user = userEvent.setup();
        render(<QuickSwitcher {...base} />);
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        const box = screen.getByRole("searchbox");
        const followed = vi.fn((event: Event) => event.preventDefault());
        screen
            .getByRole("menuitem", { name: "Pit of Teeth" })
            .addEventListener("click", followed);

        await user.keyboard("{ArrowDown}{ArrowDown}");
        const highlighted = box.getAttribute("aria-activedescendant");
        expect(document.getElementById(highlighted!)?.textContent).toBe(
            "Pit of Teeth",
        );
        expect(scrolled).toHaveBeenLastCalledWith({ block: "nearest" });
        await user.keyboard("{Enter}");
        expect(followed).toHaveBeenCalledTimes(1);
    });

    it("clears the search on Escape, then closes and returns focus", async () => {
        const user = userEvent.setup();
        render(<QuickSwitcher {...base} />);
        const chevron = screen.getByRole("button", {
            name: "Switch to another gang",
        });
        await user.click(chevron);

        await user.keyboard("pit{Escape}");
        expect(screen.getByRole<HTMLInputElement>("searchbox").value).toBe("");
        expect(screen.getByRole("menu")).toBeTruthy();

        await user.keyboard("{Escape}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(chevron);
    });

    it("opens and closes on its chord from anywhere on the page", () => {
        render(<QuickSwitcher {...base} />);
        const chord = { altKey: true, shiftKey: true, code: "KeyF" };

        act(() => {
            fireEvent.keyDown(document.body, chord);
        });
        expect(screen.getByRole("menu")).toBeTruthy();
        act(() => {
            fireEvent.keyDown(document.body, chord);
        });
        expect(screen.queryByRole("menu")).toBeNull();
        act(() => {
            fireEvent.keyDown(document.body, { ...chord, code: "KeyR" });
        });
        expect(screen.queryByRole("menu")).toBeNull();
    });

    it("closes when focus or a click goes elsewhere", async () => {
        const user = userEvent.setup();
        render(
            <>
                <QuickSwitcher {...base} />
                <button type="button">Elsewhere</button>
            </>,
        );
        await user.click(
            screen.getByRole("button", { name: "Switch to another gang" }),
        );
        await user.click(screen.getByRole("button", { name: "Elsewhere" }));
        expect(screen.queryByRole("menu")).toBeNull();
    });

    it("draws the chevron alone when the switcher has no label", () => {
        render(<QuickSwitcher {...base} label="" href="" />);
        expect(screen.queryByRole("link")).toBeNull();
        expect(
            screen.getByRole("button", { name: "Switch to another gang" }),
        ).toBeTruthy();
    });
});

describe("quick switcher island", () => {
    it("replaces the markup the server drew in its place", async () => {
        const host = document.createElement("div");
        host.id = "react-test";
        const drawn = document.createElement("button");
        drawn.setAttribute("aria-label", "Server trigger");
        host.append(drawn);
        document.body.append(host);

        let dispose = () => {};
        await act(async () => {
            dispose = mount(host, base);
        });
        expect(host.querySelector('[aria-label="Server trigger"]')).toBeNull();
        expect(
            host.querySelector('[aria-label="Switch to another gang"]'),
        ).not.toBeNull();
        act(() => dispose());
        host.remove();
    });
});
