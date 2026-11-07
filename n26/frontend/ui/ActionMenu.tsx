import {
    Fragment,
    useId,
    useEffect,
    useRef,
    useState,
    type KeyboardEvent,
} from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";
import { Glyph } from "./glyph";

export type ActionMenuItem = {
    label: string;
    href: string;
    tone: "default" | "danger";
    /** Show a separator above this entry when requested by the server. */
    separatorBefore: boolean;
};

export type ActionMenuProps = {
    /** The trigger's accessible name and its tooltip. */
    label: string;
    /** Entries in display order. */
    items: ActionMenuItem[];
    trigger?: "ellipsis" | "chevron";
    variant?: "default" | "ghost";
    align?: "start" | "end";
    /** A CSS length. */
    minWidth?: string;
};

type Edge = "first" | "last";

/**
 * Detect assistive-technology clicks using React Aria's isVirtualClick
 * conditions: Firefox mozInputSource, Android buttons, or detail 0 without a
 * pointerType.
 */
export function isVirtualClick(event: MouseEvent) {
    const { pointerType } = event as PointerEvent;
    const { mozInputSource } = event as MouseEvent & {
        mozInputSource?: number;
    };
    if (mozInputSource === 0 && event.isTrusted) return true;
    if (/Android/i.test(navigator.userAgent) && pointerType)
        return event.type === "click" && event.buttons === 1;
    return event.detail === 0 && !pointerType;
}

/**
 * A button that opens a menu of links, following the WAI-ARIA menu button
 * pattern. Arrow keys, Home and End move between the links; Escape closes the
 * menu and returns focus to the button; Tab closes it and moves on.
 */
export function ActionMenu({
    label,
    items,
    trigger = "ellipsis",
    variant = "default",
    align = "start",
    minWidth = "12rem",
}: ActionMenuProps) {
    const triggerId = useId();
    const panelId = useId();
    const root = useRef<HTMLDivElement>(null);
    const button = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const links = useRef<(HTMLAnchorElement | null)[]>([]);
    const pendingFocus = useRef<Edge | null>(null);
    const [open, setOpen] = useState(false);

    useDismiss(root, button, open, () => setOpen(false));
    const placement = useAnchoredPlacement({
        open,
        trigger: button,
        panel,
        align,
        width: "content",
        minWidth,
        gap: 4,
        margin: 8,
    });

    function shown() {
        return links.current.filter(
            (link): link is HTMLAnchorElement => link !== null,
        );
    }

    function focusEdge(edge: Edge) {
        const list = shown();
        const target = edge === "first" ? list[0] : list.at(-1);
        // Scroll the panel to reveal the focused link without moving the
        // page.
        target?.focus({ preventScroll: true });
        target?.scrollIntoView?.({ block: "nearest" });
    }

    // Keyboard opening focuses the first or last link after mount; pointer
    // opening retains trigger focus.
    useEffect(() => {
        if (open && pendingFocus.current) focusEdge(pendingFocus.current);
        pendingFocus.current = null;
    }, [open]);

    function openAt(edge: Edge) {
        if (open) {
            focusEdge(edge);
            return;
        }
        pendingFocus.current = edge;
        setOpen(true);
    }

    function onTriggerKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
        if (
            event.key === "Enter" ||
            event.key === " " ||
            event.key === "ArrowDown"
        ) {
            event.preventDefault();
            openAt("first");
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            openAt("last");
        }
    }

    function onPanelKeyDown(event: KeyboardEvent<HTMLDivElement>) {
        const list = shown();
        const at = list.indexOf(document.activeElement as HTMLAnchorElement);
        switch (event.key) {
            case "ArrowDown":
                event.preventDefault();
                list[at < 0 ? 0 : (at + 1) % list.length]?.focus();
                break;
            case "ArrowUp":
                event.preventDefault();
                list[
                    at < 0
                        ? list.length - 1
                        : (at - 1 + list.length) % list.length
                ]?.focus();
                break;
            case "Home":
                event.preventDefault();
                list[0]?.focus();
                break;
            case "End":
                event.preventDefault();
                list.at(-1)?.focus();
                break;
            case " ":
                if (at >= 0) {
                    event.preventDefault();
                    list[at].click();
                }
                break;
            case "Tab":
                // Restore trigger focus before unmounting so Tab continues
                // from the trigger in document order.
                button.current?.focus();
                setOpen(false);
                break;
        }
    }

    links.current.length = items.length;

    return (
        <div ref={root} className="contents">
            <button
                ref={button}
                type="button"
                className={`${cotton.buttonSmall[variant]} ${trigger === "chevron" ? "px-1.5!" : ""}`}
                id={triggerId}
                aria-label={label}
                title={label}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={open ? panelId : undefined}
                onClick={(event) => {
                    if (open) {
                        // Restore trigger focus before removing the focused
                        // link.
                        if (panel.current?.contains(document.activeElement))
                            button.current?.focus();
                        setOpen(false);
                        return;
                    }
                    // Assistive-technology activation focuses the first
                    // link. Keyboard handlers prevent their native click,
                    // while pointer clicks retain trigger focus.
                    if (isVirtualClick(event.nativeEvent))
                        pendingFocus.current = "first";
                    setOpen(true);
                }}
                onKeyDown={onTriggerKeyDown}
                onKeyUp={(event) => {
                    // Prevent Firefox's Space keyup click from closing a
                    // menu already opened on keydown.
                    if (event.key === " ") event.preventDefault();
                }}
            >
                {trigger === "chevron" ? (
                    <span className="n26-icon-only">
                        <Glyph
                            name="chevron-down"
                            strokeWidth={2.5}
                            className={`size-3 transition-transform${open ? " rotate-180" : ""}`}
                        />
                    </span>
                ) : (
                    <span className="n26-icon-only gap-0.5">
                        <Glyph
                            name="ellipsis-vertical"
                            className="size-4"
                            strokeWidth={1.7}
                        />
                        <Glyph
                            name="chevron-down"
                            className="size-3"
                            strokeWidth={2.5}
                        />
                    </span>
                )}
            </button>
            {open && (
                <div
                    ref={panel}
                    id={panelId}
                    role="menu"
                    aria-orientation="vertical"
                    aria-labelledby={triggerId}
                    className={`${cotton.actionMenu.panel} fixed`}
                    style={placement}
                    onKeyDown={onPanelKeyDown}
                >
                    {items.map((item, index) => (
                        <Fragment key={index}>
                            {item.separatorBefore && (
                                <div
                                    role="separator"
                                    aria-orientation="horizontal"
                                    className={cotton.actionMenu.separator}
                                />
                            )}
                            <a
                                ref={(element) => {
                                    links.current[index] = element;
                                }}
                                role="menuitem"
                                tabIndex={-1}
                                href={item.href}
                                className={
                                    item.tone === "danger"
                                        ? cotton.actionMenu.itemDanger
                                        : cotton.actionMenu.item
                                }
                                onPointerMove={(event) =>
                                    event.currentTarget.focus({
                                        preventScroll: true,
                                    })
                                }
                                onClick={() => setOpen(false)}
                            >
                                <span className={cotton.actionMenu.itemLabel}>
                                    {item.label}
                                </span>
                            </a>
                        </Fragment>
                    ))}
                </div>
            )}
        </div>
    );
}
