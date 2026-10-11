import {
    createContext,
    useContext,
    useEffect,
    useId,
    useRef,
    useState,
    type KeyboardEvent,
    type ReactNode,
} from "react";
import cotton from "../generated/cotton.json";
import { isVirtualClick } from "./ActionMenu";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";

// Every kind of row a menu holds: links, form buttons and radio choices.
const ITEMS =
    '[role="menuitem"], [role="menuitemradio"], [role="menuitemcheckbox"]';

type Edge = "first" | "last";

// How a row closes the menu it sits in.
const CloseMenu = createContext<() => void>(() => {});

/**
 * A button that opens a menu of mixed rows, following the WAI-ARIA menu
 * button pattern over every item the panel holds. Arrow keys, Home and End
 * move between them; Escape closes and returns focus to the button; Tab
 * closes and moves on. ActionMenu is the links-only form.
 */
export function MenuButton({
    label,
    title,
    className,
    trigger,
    align = "end",
    minWidth = "12rem",
    children,
}: {
    /** The button's accessible name. */
    label: string;
    title?: string;
    className: string;
    /** What the button shows. */
    trigger: ReactNode;
    align?: "start" | "end";
    /** A CSS length. */
    minWidth?: string;
    children: ReactNode;
}) {
    const triggerId = useId();
    const panelId = useId();
    const root = useRef<HTMLDivElement>(null);
    const button = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
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

    function items() {
        return [...(panel.current?.querySelectorAll<HTMLElement>(ITEMS) ?? [])];
    }

    function focusEdge(edge: Edge) {
        const list = items();
        const target = edge === "first" ? list[0] : list.at(-1);
        target?.focus({ preventScroll: true });
        target?.scrollIntoView?.({ block: "nearest" });
    }

    useEffect(() => {
        if (open && pendingFocus.current) focusEdge(pendingFocus.current);
        pendingFocus.current = null;
    }, [open]);

    // A posting row cannot close the menu as it is used: a form taken out
    // of the page before its submission runs is not sent. So a page the
    // browser restores from its back-forward cache closes the menu instead.
    useEffect(() => {
        function onPageShow(event: PageTransitionEvent) {
            if (event.persisted) setOpen(false);
        }
        window.addEventListener("pageshow", onPageShow);
        return () => window.removeEventListener("pageshow", onPageShow);
    }, []);

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
        const list = items();
        const at = list.indexOf(document.activeElement as HTMLElement);
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
                // Focus the button before the panel goes, so Tab moves on
                // from it rather than from the start of the page.
                button.current?.focus();
                setOpen(false);
                break;
        }
    }

    return (
        <div ref={root} className="relative inline-block">
            <button
                ref={button}
                type="button"
                className={className}
                id={triggerId}
                aria-label={label}
                title={title}
                aria-haspopup="menu"
                aria-expanded={open}
                aria-controls={open ? panelId : undefined}
                onClick={(event) => {
                    if (open) {
                        if (panel.current?.contains(document.activeElement))
                            button.current?.focus();
                        setOpen(false);
                        return;
                    }
                    if (isVirtualClick(event.nativeEvent))
                        pendingFocus.current = "first";
                    setOpen(true);
                }}
                onKeyDown={onTriggerKeyDown}
                onKeyUp={(event) => {
                    if (event.key === " ") event.preventDefault();
                }}
            >
                {trigger}
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
                    onPointerMove={(event) => {
                        const item = (
                            event.target as HTMLElement
                        ).closest<HTMLElement>(ITEMS);
                        item?.focus({ preventScroll: true });
                    }}
                >
                    <CloseMenu.Provider value={() => setOpen(false)}>
                        {children}
                    </CloseMenu.Provider>
                </div>
            )}
        </div>
    );
}

const itemClass = (tone: "default" | "danger") =>
    tone === "danger" ? cotton.actionMenu.itemDanger : cotton.actionMenu.item;

/** A menu row that goes somewhere. */
export function MenuLink({
    href,
    tone = "default",
    children,
}: {
    href: string;
    tone?: "default" | "danger";
    children: ReactNode;
}) {
    const close = useContext(CloseMenu);
    return (
        <a
            role="menuitem"
            tabIndex={-1}
            href={href}
            className={itemClass(tone)}
            onClick={close}
        >
            <span className={cotton.actionMenu.itemLabel}>{children}</span>
        </a>
    );
}

/**
 * A menu row that posts a form. The form is not a menu row itself, so it
 * is hidden from the menu's structure.
 */
export function MenuSubmit({
    action,
    fields,
    tone = "default",
    children,
}: {
    action: string;
    /** Hidden inputs, in order, as name and value. */
    fields: [string, string][];
    tone?: "default" | "danger";
    children: ReactNode;
}) {
    return (
        <form method="post" action={action} role="none">
            {fields.map(([name, value]) => (
                <input key={name} type="hidden" name={name} value={value} />
            ))}
            <button
                type="submit"
                role="menuitem"
                tabIndex={-1}
                className={`${itemClass(tone)} w-full`}
            >
                <span className={cotton.actionMenu.itemLabel}>{children}</span>
            </button>
        </form>
    );
}

export function MenuSeparator() {
    return (
        <div
            role="separator"
            aria-orientation="horizontal"
            className={cotton.actionMenu.separator}
        />
    );
}

/**
 * A section of a menu under a heading, as `<c-ui.dropdown.group>` draws it.
 * The heading names the group, so a screen reader says it on entering.
 */
export function MenuGroup({
    label,
    children,
}: {
    label: string;
    children: ReactNode;
}) {
    const labelId = useId();
    return (
        <div
            role="group"
            aria-labelledby={labelId}
            className={cotton.dropdownGroup.root}
        >
            <div id={labelId} className={cotton.dropdownGroup.label}>
                {label}
            </div>
            {children}
        </div>
    );
}
