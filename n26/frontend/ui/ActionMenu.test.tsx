import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import cotton from "../generated/cotton.json";
import { ActionMenu, isVirtualClick, type ActionMenuItem } from "./ActionMenu";

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

const links: ActionMenuItem[] = [
    {
        label: "View gang",
        href: "/gang",
        tone: "default",
        separatorBefore: false,
    },
    {
        label: "Edit gang settings",
        href: "/gang/edit",
        tone: "default",
        separatorBefore: false,
    },
    {
        label: "Print",
        href: "/gang/print",
        tone: "default",
        separatorBefore: false,
    },
];

function setup(props: Partial<Parameters<typeof ActionMenu>[0]> = {}) {
    const user = userEvent.setup();
    render(
        <div>
            <button type="button">Before</button>
            <ActionMenu
                label="Actions for The Ashen Choir"
                items={links}
                {...props}
            />
            <button type="button">After</button>
        </div>,
    );
    const trigger = screen.getByRole("button", {
        name: "Actions for The Ashen Choir",
    });
    return { user, trigger };
}

function item(name: string) {
    return screen.getByRole("menuitem", { name });
}

// A test cannot follow a link, so stop every click from navigating.
function stopNavigation() {
    const listener = (event: Event) => event.preventDefault();
    document.addEventListener("click", listener);
    return () => document.removeEventListener("click", listener);
}

describe("ActionMenu keyboard", () => {
    it.each(["{Enter}", " ", "{ArrowDown}"])(
        "%s on the trigger opens the menu at the first link",
        async (key) => {
            const { user, trigger } = setup();
            trigger.focus();
            await user.keyboard(key);
            expect(screen.getByRole("menu")).toBeTruthy();
            expect(document.activeElement).toBe(item("View gang"));
        },
    );

    it.each(["Enter", " "])(
        "%s on the trigger prevents the click that would toggle it again",
        (key) => {
            const { trigger } = setup();
            trigger.focus();
            // dispatchEvent returns false when the handler prevented the
            // default, which is the browser's click on that key.
            expect(fireEvent.keyDown(trigger, { key })).toBe(false);
            expect(screen.getByRole("menu")).toBeTruthy();
            if (key === " ")
                expect(fireEvent.keyUp(trigger, { key })).toBe(false);
            expect(screen.getByRole("menu")).toBeTruthy();
        },
    );

    it("ArrowUp on the trigger opens the menu at the last link", async () => {
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowUp}");
        expect(document.activeElement).toBe(item("Print"));
    });

    it("scrolls the panel to the link a keyboard opening focuses", async () => {
        // A panel past its height cap scrolls; the focused link must show.
        const scrolled: Element[] = [];
        const scrollIntoView = vi.fn(function (this: Element) {
            scrolled.push(this);
        });
        const original = Element.prototype.scrollIntoView;
        Element.prototype.scrollIntoView = scrollIntoView;
        try {
            const { user, trigger } = setup();
            trigger.focus();
            await user.keyboard("{ArrowUp}");
            expect(scrolled).toEqual([item("Print")]);
            expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
        } finally {
            Element.prototype.scrollIntoView = original;
        }
    });

    it("arrows wrap, and Home and End jump to the ends", async () => {
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowDown}");
        await user.keyboard("{ArrowDown}");
        expect(document.activeElement).toBe(item("Edit gang settings"));
        await user.keyboard("{ArrowDown}{ArrowDown}");
        expect(document.activeElement).toBe(item("View gang"));
        await user.keyboard("{ArrowUp}");
        expect(document.activeElement).toBe(item("Print"));
        await user.keyboard("{Home}");
        expect(document.activeElement).toBe(item("View gang"));
        await user.keyboard("{End}");
        expect(document.activeElement).toBe(item("Print"));
    });

    it("Escape closes the menu and returns focus to the trigger", async () => {
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowDown}{ArrowDown}");
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(trigger);
    });

    it("Tab closes the menu and moves on from the trigger", async () => {
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowDown}");
        await user.tab();
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "After" }),
        );
    });

    it("Shift+Tab closes the menu and moves back from the trigger", async () => {
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowDown}");
        await user.tab({ shift: true });
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Before" }),
        );
    });

    it("Space on a link follows it and closes the menu", async () => {
        const restore = stopNavigation();
        const clicked = vi.fn();
        const { user, trigger } = setup();
        trigger.focus();
        await user.keyboard("{ArrowDown}{ArrowDown}");
        item("Edit gang settings").addEventListener("click", clicked);
        await user.keyboard(" ");
        expect(clicked).toHaveBeenCalledTimes(1);
        expect(screen.queryByRole("menu")).toBeNull();
        restore();
    });
});

describe("ActionMenu pointer", () => {
    it("a click opens the menu without moving focus, and a second closes it", async () => {
        const { user, trigger } = setup();
        await user.click(trigger);
        expect(screen.getByRole("menu")).toBeTruthy();
        expect(document.activeElement).toBe(trigger);
        await user.click(trigger);
        expect(screen.queryByRole("menu")).toBeNull();
    });

    it("a pointer outside closes the menu", async () => {
        const { user, trigger } = setup();
        await user.click(trigger);
        await user.click(screen.getByRole("button", { name: "After" }));
        expect(screen.queryByRole("menu")).toBeNull();
    });

    it("clicking a link closes the menu and keeps the link's address", async () => {
        const restore = stopNavigation();
        const { user, trigger } = setup();
        await user.click(trigger);
        expect(item("Print").getAttribute("href")).toBe("/gang/print");
        await user.click(item("Print"));
        expect(screen.queryByRole("menu")).toBeNull();
        restore();
    });

    it("hovering a link focuses it", async () => {
        const { user, trigger } = setup();
        await user.click(trigger);
        fireEvent.pointerMove(item("Edit gang settings"));
        expect(document.activeElement).toBe(item("Edit gang settings"));
    });
});

/** Clicks the trigger with event fields a test cannot pass to MouseEvent. */
function clickWith(
    trigger: HTMLElement,
    { detail = 1, ...fields }: Record<string, unknown> & { detail?: number },
) {
    const event = new MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        detail,
    });
    for (const [key, value] of Object.entries(fields))
        Object.defineProperty(event, key, { value });
    act(() => {
        trigger.dispatchEvent(event);
    });
}

function asAndroid() {
    Object.defineProperty(window.navigator, "userAgent", {
        value: "Mozilla/5.0 (Linux; Android 15; Pixel 9) Chrome/140.0",
        configurable: true,
    });
    return () => {
        delete (window.navigator as { userAgent?: string }).userAgent;
    };
}

describe("ActionMenu virtual clicks", () => {
    it("a click with detail 0 and no pointer type opens at the first link", () => {
        // What element.click() sends, and most screen readers.
        const { trigger } = setup();
        act(() => trigger.click());
        expect(screen.getByRole("menu")).toBeTruthy();
        expect(document.activeElement).toBe(item("View gang"));
        act(() => trigger.click());
        expect(screen.queryByRole("menu")).toBeNull();
        // The focused link went with the panel; focus is back on the button.
        expect(document.activeElement).toBe(trigger);
    });

    it("a mouse click leaves focus on the trigger", () => {
        const { trigger } = setup();
        trigger.focus();
        clickWith(trigger, { detail: 1, pointerType: "mouse", buttons: 0 });
        expect(screen.getByRole("menu")).toBeTruthy();
        expect(document.activeElement).toBe(trigger);
    });

    it("a pointer click that reports detail 0 leaves focus on the trigger", () => {
        const { trigger } = setup();
        trigger.focus();
        clickWith(trigger, { detail: 0, pointerType: "mouse" });
        expect(screen.getByRole("menu")).toBeTruthy();
        expect(document.activeElement).toBe(trigger);
    });

    it("counts a trusted Firefox click with mozInputSource 0 as virtual", () => {
        // NVDA and JAWS in Firefox send detail 1 with mozInputSource 0. A
        // test cannot dispatch a trusted event, so this asks the check
        // directly.
        const click = {
            type: "click",
            detail: 1,
            buttons: 0,
            isTrusted: true,
            mozInputSource: 0,
        } as unknown as MouseEvent;
        expect(isVirtualClick(click)).toBe(true);
        expect(isVirtualClick({ ...click, isTrusted: false })).toBe(false);
    });

    it("an untrusted click claiming mozInputSource 0 is not virtual", () => {
        const { trigger } = setup();
        trigger.focus();
        clickWith(trigger, { detail: 1, mozInputSource: 0 });
        expect(document.activeElement).toBe(trigger);
    });

    it("TalkBack's click on Android opens at the first link", () => {
        const restore = asAndroid();
        try {
            const { trigger } = setup();
            clickWith(trigger, { detail: 1, pointerType: "touch", buttons: 1 });
            expect(document.activeElement).toBe(item("View gang"));
        } finally {
            restore();
        }
    });

    it("a touch on Android leaves focus on the trigger", () => {
        const restore = asAndroid();
        try {
            const { trigger } = setup();
            trigger.focus();
            clickWith(trigger, { detail: 1, pointerType: "touch", buttons: 0 });
            expect(screen.getByRole("menu")).toBeTruthy();
            expect(document.activeElement).toBe(trigger);
        } finally {
            restore();
        }
    });

    it("a desktop click with a pointer type and buttons 1 leaves focus on the trigger", () => {
        // The Android check must not reach a desktop browser.
        const { trigger } = setup();
        trigger.focus();
        clickWith(trigger, { detail: 1, pointerType: "mouse", buttons: 1 });
        expect(document.activeElement).toBe(trigger);
    });
});

describe("ActionMenu rendering", () => {
    it("reports its state on the trigger", async () => {
        const { user, trigger } = setup();
        expect(trigger.getAttribute("aria-expanded")).toBe("false");
        expect(trigger.getAttribute("aria-haspopup")).toBe("menu");
        expect(trigger.getAttribute("title")).toBe(
            "Actions for The Ashen Choir",
        );
        expect(trigger.hasAttribute("aria-controls")).toBe(false);
        await user.click(trigger);
        const menu = screen.getByRole("menu");
        expect(trigger.getAttribute("aria-expanded")).toBe("true");
        expect(trigger.getAttribute("aria-controls")).toBe(menu.id);
        expect(menu.getAttribute("aria-labelledby")).toBe(trigger.id);
        await user.click(trigger);
        expect(trigger.getAttribute("aria-expanded")).toBe("false");
        expect(trigger.hasAttribute("aria-controls")).toBe(false);
    });

    it("draws a separator only above the items that ask for one", async () => {
        const { user, trigger } = setup({
            items: [
                {
                    label: "Reassign",
                    href: "/r",
                    tone: "default",
                    separatorBefore: false,
                },
                {
                    label: "Refund",
                    href: "/f",
                    tone: "default",
                    separatorBefore: false,
                },
                {
                    label: "Sell",
                    href: "/s",
                    tone: "danger",
                    separatorBefore: true,
                },
                {
                    label: "Delete",
                    href: "/d",
                    tone: "danger",
                    separatorBefore: true,
                },
            ],
        });
        await user.click(trigger);
        const menu = screen.getByRole("menu");
        const order = [...menu.children].map((child) =>
            child.getAttribute("role") === "separator"
                ? "—"
                : child.textContent,
        );
        expect(order).toEqual([
            "Reassign",
            "Refund",
            "—",
            "Sell",
            "—",
            "Delete",
        ]);
        for (const separator of screen.getAllByRole("separator")) {
            expect(separator.className).toBe(cotton.actionMenu.separator);
        }
    });

    it("draws no separator when no item asks for one", async () => {
        const { user, trigger } = setup();
        await user.click(trigger);
        expect(screen.queryAllByRole("separator")).toHaveLength(0);
    });

    it("styles a danger item from the danger recipe", async () => {
        const { user, trigger } = setup({
            items: [
                ...links,
                {
                    label: "Delete gang",
                    href: "/d",
                    tone: "danger",
                    separatorBefore: false,
                },
            ],
        });
        await user.click(trigger);
        expect(item("Delete gang").className).toBe(
            cotton.actionMenu.itemDanger,
        );
        expect(item("View gang").className).toBe(cotton.actionMenu.item);
    });

    it("turns the chevron trigger while open", async () => {
        const { user, trigger } = setup({
            trigger: "chevron",
            variant: "default",
        });
        const chevron = trigger.querySelector("svg")!;
        expect(trigger.querySelectorAll("svg")).toHaveLength(1);
        expect(chevron.getAttribute("class")).not.toContain("rotate-180");
        await user.click(trigger);
        expect(chevron.getAttribute("class")).toContain("rotate-180");
        expect(trigger.className).toContain("px-1.5!");
        expect(trigger.className).toContain(cotton.buttonSmall.default);
    });

    it("draws the ellipsis trigger without turning", async () => {
        const { user, trigger } = setup({ variant: "ghost" });
        expect(trigger.querySelectorAll("svg")).toHaveLength(2);
        await user.click(trigger);
        for (const svg of trigger.querySelectorAll("svg"))
            expect(svg.getAttribute("class")).not.toContain("rotate-180");
        expect(trigger.className).toContain(cotton.buttonSmall.ghost);
    });

    it("draws link labels as text", async () => {
        const { user, trigger } = setup({
            items: [
                {
                    label: "<b>O'Brien & Sons</b>",
                    href: "/o",
                    tone: "default",
                    separatorBefore: false,
                },
            ],
        });
        await user.click(trigger);
        expect(item("<b>O'Brien & Sons</b>").querySelector("b")).toBeNull();
    });
});

function rect(left: number, top: number, width: number, height: number) {
    return {
        left,
        top,
        right: left + width,
        bottom: top + height,
        width,
        height,
        x: left,
        y: top,
        toJSON: () => ({}),
    };
}

function stubLayout(
    window: { width: number; height: number },
    trigger: ReturnType<typeof rect>,
    panel: { width: number; height: number },
) {
    vi.stubGlobal("innerWidth", window.width);
    vi.stubGlobal("innerHeight", window.height);
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
        () => trigger,
    );
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(
        panel.width,
    );
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(
        panel.height,
    );
}

describe("ActionMenu placement", () => {
    it("lines up with the trigger's end below it", async () => {
        stubLayout({ width: 1280, height: 800 }, rect(1000, 100, 40, 30), {
            width: 192,
            height: 120,
        });
        const { user, trigger } = setup({ align: "end" });
        await user.click(trigger);
        const menu = screen.getByRole("menu");
        expect(menu.style.opacity).not.toBe("0");
        expect(menu.style.pointerEvents).not.toBe("none");
        expect(menu.style.left).toBe(`${1040 - 192}px`);
        expect(menu.style.top).toBe("134px");
        expect(menu.style.minWidth).toContain("12rem");
        expect(menu.style.minWidth).toContain("16px");
    });

    it("keeps 8px from the window's right edge", async () => {
        stubLayout({ width: 390, height: 800 }, rect(350, 100, 36, 30), {
            width: 192,
            height: 120,
        });
        const { user, trigger } = setup({ align: "start" });
        await user.click(trigger);
        expect(screen.getByRole("menu").style.left).toBe(`${390 - 192 - 8}px`);
    });

    it("opens above when there is no room below", async () => {
        stubLayout({ width: 1280, height: 800 }, rect(1000, 700, 40, 30), {
            width: 192,
            height: 120,
        });
        const { user, trigger } = setup({ align: "end" });
        await user.click(trigger);
        expect(screen.getByRole("menu").style.top).toBe(`${700 - 4 - 120}px`);
    });
});
