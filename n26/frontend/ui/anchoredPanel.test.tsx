import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
    useAnchoredPlacement,
    useDismiss,
    type AnchoredPlacementOptions,
} from "./anchoredPanel";

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
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

function stubWindow(width: number, height: number) {
    vi.stubGlobal("innerWidth", width);
    vi.stubGlobal("innerHeight", height);
}

function stubTrigger(box: ReturnType<typeof rect>) {
    return vi
        .spyOn(HTMLElement.prototype, "getBoundingClientRect")
        .mockImplementation(() => box);
}

function stubPanelSize(width: number, height: number) {
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(
        width,
    );
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(
        height,
    );
    vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(
        height,
    );
}

function Panel({
    onEscape,
    onClose,
    placement = { width: 200, gap: 4 },
}: {
    onEscape?: () => void;
    onClose?: () => void;
    placement?: Omit<AnchoredPlacementOptions, "open" | "trigger" | "panel">;
}) {
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    useDismiss(
        root,
        trigger,
        open,
        () => {
            onClose?.();
            setOpen(false);
        },
        { onEscape },
    );
    const style = useAnchoredPlacement({ open, trigger, panel, ...placement });
    return (
        <div>
            <div ref={root}>
                <button
                    ref={trigger}
                    type="button"
                    aria-expanded={open}
                    onClick={() => setOpen(!open)}
                >
                    Open
                </button>
                {open && (
                    <div
                        ref={panel}
                        role="dialog"
                        aria-label="Panel"
                        className="fixed"
                        style={style}
                    >
                        <button type="button">Inside</button>
                    </div>
                )}
            </div>
            <button type="button">Outside</button>
        </div>
    );
}

describe("useDismiss", () => {
    it("closes on a pointer outside and leaves focus where it went", async () => {
        const user = userEvent.setup();
        render(<Panel />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        await user.click(screen.getByRole("button", { name: "Inside" }));
        expect(screen.getByRole("dialog")).toBeTruthy();

        await user.click(screen.getByRole("button", { name: "Outside" }));
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Outside" }),
        );
    });

    it("closes when focus moves outside", async () => {
        const user = userEvent.setup();
        render(<Panel />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        await user.tab();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Inside" }),
        );
        expect(screen.getByRole("dialog")).toBeTruthy();

        await user.tab();
        expect(screen.queryByRole("dialog")).toBeNull();
    });

    it("closes on Escape and returns focus to the trigger", async () => {
        const user = userEvent.setup();
        render(<Panel />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        await user.click(screen.getByRole("button", { name: "Inside" }));
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Open" }),
        );
    });

    it("hands Escape to onEscape instead of closing and focusing", async () => {
        const user = userEvent.setup();
        const onEscape = vi.fn();
        const onClose = vi.fn();
        render(<Panel onEscape={onEscape} onClose={onClose} />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        await user.click(screen.getByRole("button", { name: "Inside" }));
        await user.keyboard("{Escape}");
        expect(onEscape).toHaveBeenCalledTimes(1);
        expect(onClose).not.toHaveBeenCalled();
        expect(document.activeElement).toBe(
            screen.getByRole("button", { name: "Inside" }),
        );
    });

    it("stops listening once the panel is closed", async () => {
        const user = userEvent.setup();
        const onClose = vi.fn();
        render(<Panel onClose={onClose} />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        await user.click(screen.getByRole("button", { name: "Outside" }));
        expect(onClose).toHaveBeenCalledTimes(1);

        await user.click(screen.getByRole("button", { name: "Outside" }));
        await user.keyboard("{Escape}");
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});

describe("useAnchoredPlacement", () => {
    it("lines up with the trigger's start and narrows to the window", async () => {
        const user = userEvent.setup();
        stubWindow(300, 800);
        stubTrigger(rect(40, 100, 60, 30));
        stubPanelSize(0, 120);
        render(<Panel placement={{ width: 320, gap: 4 }} />);
        await user.click(screen.getByRole("button", { name: "Open" }));

        const panel = screen.getByRole("dialog");
        expect(panel.style.visibility).toBe("visible");
        expect(panel.style.width).toBe("268px");
        expect(panel.style.left).toBe("16px");
        expect(panel.style.top).toBe("134px");
        expect(panel.style.maxHeight).toBe("");
    });

    it("lines up with the trigger's end and keeps a 16px margin from the window edge", async () => {
        const user = userEvent.setup();
        stubWindow(1280, 800);
        const box = rect(1000, 100, 40, 30);
        stubTrigger(box);
        stubPanelSize(200, 120);
        render(<Panel placement={{ width: 200, gap: 4, align: "end" }} />);
        await user.click(screen.getByRole("button", { name: "Open" }));

        const panel = screen.getByRole("dialog");
        expect(panel.style.left).toBe("840px");

        Object.assign(box, rect(1180, 100, 90, 30));
        fireEvent.resize(window);
        expect(panel.style.left).toBe("1064px");
    });

    it("flips above when only above has room for the whole panel", async () => {
        const user = userEvent.setup();
        stubWindow(390, 600);
        const box = rect(20, 500, 40, 30);
        stubTrigger(box);
        stubPanelSize(200, 200);
        render(<Panel placement={{ width: 288, gap: 8 }} />);
        await user.click(screen.getByRole("button", { name: "Open" }));

        const panel = screen.getByRole("dialog");
        expect(panel.style.top).toBe("292px");

        // Neither side fits: it stays below and runs past the window.
        Object.assign(box, rect(20, 150, 40, 30));
        stubPanelSize(200, 500);
        fireEvent.scroll(window);
        expect(panel.style.top).toBe("188px");
    });

    it("clamps the height to the larger side when the panel overflows", async () => {
        const user = userEvent.setup();
        stubWindow(390, 400);
        stubTrigger(rect(20, 300, 40, 30));
        stubPanelSize(0, 500);
        render(<Panel placement={{ width: 320, gap: 4, clampHeight: true }} />);
        await user.click(screen.getByRole("button", { name: "Open" }));

        const panel = screen.getByRole("dialog");
        expect(panel.style.top).toBe("16px");
        expect(panel.style.maxHeight).toBe("280px");
    });

    it("is hidden until placed, and unplaced again when reopened", async () => {
        const user = userEvent.setup();
        stubWindow(1280, 800);
        const trigger = stubTrigger(rect(40, 100, 60, 30));
        stubPanelSize(0, 100);
        render(<Panel />);
        await user.click(screen.getByRole("button", { name: "Open" }));
        expect(trigger).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("dialog").style.visibility).toBe("visible");

        await user.click(screen.getByRole("button", { name: "Open" }));
        fireEvent.resize(window);
        expect(trigger).toHaveBeenCalledTimes(1);

        let seen = "";
        trigger.mockImplementation(() => {
            seen ||=
                screen.queryByRole("dialog", { hidden: true })?.style
                    .visibility ?? "";
            return rect(40, 100, 60, 30);
        });
        await user.click(screen.getByRole("button", { name: "Open" }));
        expect(seen).toBe("hidden");
        expect(screen.getByRole("dialog").style.visibility).toBe("visible");
    });
});

// The shape of a link menu: opened by a button, lined up with the button's
// end, as wide as its longest item but never narrower than a minimum, and
// fixed to the window so the scroll box around it does not clip it.
function LinkMenu({ links }: { links: { label: string; href: string }[] }) {
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const menu = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    useDismiss(root, trigger, open, () => setOpen(false));
    const style = useAnchoredPlacement({
        open,
        trigger,
        panel: menu,
        align: "end",
        width: "content",
        minWidth: "12rem",
        gap: 4,
    });
    return (
        <div ref={root} className="relative inline-block">
            <button
                ref={trigger}
                type="button"
                aria-haspopup="menu"
                aria-expanded={open}
                onClick={() => setOpen(!open)}
            >
                Actions
            </button>
            {open && (
                <div
                    ref={menu}
                    role="menu"
                    className="fixed z-50"
                    style={style}
                >
                    {links.map((link) => (
                        <a key={link.href} role="menuitem" href={link.href}>
                            {link.label}
                        </a>
                    ))}
                </div>
            )}
        </div>
    );
}

describe("a link menu built on both hooks", () => {
    const links = [
        { label: "Edit", href: "/edit/" },
        { label: "Print", href: "/print/" },
    ];

    it("sizes to its content and lines up with the end of its trigger", async () => {
        const user = userEvent.setup();
        stubWindow(390, 800);
        stubTrigger(rect(330, 200, 32, 32));
        stubPanelSize(192, 80);
        render(
            <div className="max-h-80 overflow-y-auto">
                <LinkMenu links={links} />
            </div>,
        );
        const trigger = screen.getByRole("button", { name: "Actions" });
        await user.click(trigger);

        const menu = screen.getByRole("menu");
        expect(trigger.getAttribute("aria-expanded")).toBe("true");
        expect(menu.style.left).toBe("170px");
        expect(menu.style.top).toBe("236px");
        expect(menu.style.width).toBe("");
        // jsdom rewrites calc() as "-32px + 100vw".
        expect(menu.style.minWidth).toMatch(/^min\(12rem, .*100vw/);
        expect(menu.style.maxWidth).toMatch(/32px.*100vw|100vw.*32px/);
        expect(
            screen
                .getAllByRole("menuitem")
                .map((item) => item.getAttribute("href")),
        ).toEqual(["/edit/", "/print/"]);
    });

    it("measures its content width at the window's top left", async () => {
        const user = userEvent.setup();
        stubWindow(390, 800);
        let measured = { left: "", top: "", visibility: "" };
        vi.spyOn(
            HTMLElement.prototype,
            "getBoundingClientRect",
        ).mockImplementation(() => {
            const menu = screen.queryByRole("menu", { hidden: true });
            if (menu) {
                const { left, top, visibility } = menu.style;
                measured = { left, top, visibility };
            }
            return rect(330, 200, 32, 32);
        });
        stubPanelSize(192, 80);
        render(<LinkMenu links={links} />);
        await user.click(screen.getByRole("button", { name: "Actions" }));
        expect(measured).toEqual({
            left: "0px",
            top: "0px",
            visibility: "hidden",
        });
    });

    it("closes on Escape with focus back on its trigger", async () => {
        const user = userEvent.setup();
        render(<LinkMenu links={links} />);
        const trigger = screen.getByRole("button", { name: "Actions" });
        await user.click(trigger);
        screen.getByRole("menuitem", { name: "Edit" }).focus();
        await user.keyboard("{Escape}");
        expect(screen.queryByRole("menu")).toBeNull();
        expect(document.activeElement).toBe(trigger);
        expect(trigger.getAttribute("aria-expanded")).toBe("false");
    });
});
