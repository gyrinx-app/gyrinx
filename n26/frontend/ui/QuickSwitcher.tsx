import {
    createElement,
    useCallback,
    useEffect,
    useId,
    useLayoutEffect,
    useRef,
    useState,
    type CSSProperties,
    type KeyboardEvent,
} from "react";
import cotton from "../generated/cotton.json";

const recipe = cotton.quickSwitcher;

/** One destination. The href is its identity. */
export type SwitcherRow = { label: string; href: string };

export type QuickSwitcherProps = {
    /** The leading link's words; empty draws the chevron alone. */
    label: string;
    href: string;
    heading: string;
    /** The chevron's accessible name. Unique on the page. */
    menuLabel: string;
    placeholder: string;
    empty: string;
    align: "start" | "end";
    minWidth: string;
    /** One letter: Alt+Shift+that letter opens the panel. */
    hotkey: string;
    /** The first page, with the current destination in it. */
    items: SwitcherRow[];
    /** The href of the page being viewed, or empty. */
    current: string;
    /** Where further pages and searches are read; empty means `items` is the whole list. */
    source: string;
    /** The offset of the next page, or null when `items` is all of it. */
    next: number | null;
};

type Listing = { rows: SwitcherRow[]; next: number | null };

type Page = { items: SwitcherRow[]; next: number | null };

const GUTTER = 8;
const GAP = 4;
const SEARCH_DELAY = 150;
/** How close to the bottom of the list, in pixels, the next page is fetched. */
const PREFETCH = 160;

function SvgIcon({
    name,
    className,
    strokeWidth,
}: {
    name: keyof typeof cotton.icons;
    className: string;
    strokeWidth: number;
}) {
    return (
        <svg
            className={className}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            {cotton.icons[name].map(({ tag, attrs }, key) =>
                createElement(tag, { ...attrs, key }),
            )}
        </svg>
    );
}

function pageUrl(source: string, query: string, offset: number) {
    const url = new URL(source, window.location.origin);
    url.searchParams.set("q", query);
    url.searchParams.set("offset", String(offset));
    return url.toString();
}

function appendNew(rows: SwitcherRow[], more: SwitcherRow[]) {
    const seen = new Set(rows.map((row) => row.href));
    return [...rows, ...more.filter((row) => !seen.has(row.href))];
}

/**
 * A searchable menu of destinations that reads the rest of its list from the
 * server as it scrolls. Without a source, it is a fixed list searched here.
 */
export function QuickSwitcher({
    label,
    href,
    heading,
    menuLabel,
    placeholder,
    empty,
    align,
    minWidth,
    hotkey,
    items,
    current,
    source,
    next,
}: QuickSwitcherProps) {
    const panelId = useId();
    const listId = useId();
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const header = useRef<HTMLDivElement>(null);
    const input = useRef<HTMLInputElement>(null);
    const listings = useRef(
        new Map<string, Listing>([["", { rows: items, next }]]),
    );
    const inFlight = useRef<AbortController | null>(null);
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [shownQuery, setShownQuery] = useState("");
    const [listing, setListing] = useState<Listing>({ rows: items, next });
    const [base, setBase] = useState<Listing>({ rows: items, next });
    const [loading, setLoading] = useState(false);
    const [failed, setFailed] = useState(false);
    const [active, setActive] = useState(-1);
    const [placed, setPlaced] = useState<CSSProperties | null>(null);
    const isOpen = useRef(open);
    useEffect(() => {
        isOpen.current = open;
    }, [open]);

    // Once every row is here, a search needs nothing from the server.
    const whole = !source || base.next === null;
    const wanted = query.trim().toLowerCase();
    const searching = !whole && shownQuery !== query.trim();
    const matches = (row: SwitcherRow) =>
        row.label.toLowerCase().includes(wanted);
    // Until the server answers a new search, what is already loaded is
    // narrowed here so the list responds to every keystroke.
    const found = whole
        ? (source ? base.rows : items).filter(matches)
        : searching
          ? listing.rows.filter(matches)
          : listing.rows;
    // The row being viewed may not be one the source lists (a gang sheet
    // anyone can read), so a server search would drop it.
    const pinned = items.find((row) => !!current && row.href === current);
    const rows =
        pinned &&
        wanted &&
        matches(pinned) &&
        !found.some((row) => row.href === pinned.href)
            ? [pinned, ...found]
            : found;
    const name = menuLabel || heading;

    const fetchPage = useCallback(
        (forQuery: string, offset: number) => {
            inFlight.current?.abort();
            const controller = new AbortController();
            inFlight.current = controller;
            setLoading(true);
            setFailed(false);
            fetch(pageUrl(source, forQuery, offset), {
                headers: { Accept: "application/json" },
                credentials: "same-origin",
                signal: controller.signal,
            })
                .then((response) => {
                    if (!response.ok) throw new Error(`${response.status}`);
                    return response.json() as Promise<Page>;
                })
                .then((page) => {
                    if (controller.signal.aborted) return;
                    const known =
                        offset === 0
                            ? { rows: [], next: null }
                            : (listings.current.get(forQuery) ?? {
                                  rows: [],
                                  next: null,
                              });
                    const updated = {
                        rows: appendNew(known.rows, page.items),
                        next: page.next,
                    };
                    listings.current.set(forQuery, updated);
                    if (forQuery === "") setBase(updated);
                    setListing(updated);
                    setShownQuery(forQuery);
                    setLoading(false);
                    // A new answer can put other rows where the highlight
                    // was; Enter must not follow one nobody chose.
                    if (offset === 0) setActive(-1);
                })
                .catch((error: unknown) => {
                    if (controller.signal.aborted) return;
                    console.error("Switcher page failed to load", error);
                    setLoading(false);
                    setFailed(true);
                });
        },
        [source],
    );

    const loadMore = useCallback(() => {
        if (whole || loading || failed || listing.next === null) return;
        if (shownQuery !== query.trim()) return;
        fetchPage(shownQuery, listing.next);
    }, [whole, loading, failed, listing.next, shownQuery, query, fetchPage]);

    // A search reads the whole list on the server; a query already read is
    // shown again without asking twice.
    useEffect(() => {
        if (whole || !open) return;
        const trimmed = query.trim();
        const known = listings.current.get(trimmed);
        if (known) {
            inFlight.current?.abort();
            setLoading(false);
            setFailed(false);
            setListing(known);
            setShownQuery(trimmed);
            return;
        }
        const timer = window.setTimeout(
            () => fetchPage(trimmed, 0),
            SEARCH_DELAY,
        );
        return () => window.clearTimeout(timer);
    }, [whole, open, query, fetchPage]);

    useEffect(() => () => inFlight.current?.abort(), []);

    function show() {
        setQuery("");
        setActive(-1);
        setPlaced(null);
        setOpen(true);
    }

    function close() {
        setOpen(false);
    }

    function closeAndFocus() {
        setOpen(false);
        trigger.current?.focus();
    }

    useEffect(() => {
        if (!hotkey) return;
        const letter = hotkey.toUpperCase();
        function chord(event: globalThis.KeyboardEvent) {
            if (
                !event.altKey ||
                !event.shiftKey ||
                event.metaKey ||
                event.ctrlKey
            )
                return;
            // With Alt held, event.key is whatever glyph the layout types;
            // code is the physical key and keyCode follows the letter.
            if (
                event.code !== `Key${letter}` &&
                event.keyCode !== letter.charCodeAt(0)
            )
                return;
            event.preventDefault();
            if (event.repeat) return;
            if (isOpen.current) {
                setOpen(false);
                if (root.current?.contains(document.activeElement))
                    trigger.current?.focus();
            } else {
                setQuery("");
                setActive(-1);
                setPlaced(null);
                setOpen(true);
            }
        }
        window.addEventListener("keydown", chord, true);
        return () => window.removeEventListener("keydown", chord, true);
    }, [hotkey]);

    useEffect(() => {
        if (!open) return;
        input.current?.focus({ preventScroll: true });

        function dismissOnOutsidePointer(event: PointerEvent) {
            if (!root.current?.contains(event.target as Node)) setOpen(false);
        }
        function dismissOnOutsideFocus(event: FocusEvent) {
            if (!root.current?.contains(event.target as Node)) setOpen(false);
        }
        function dismissOnEscape(event: globalThis.KeyboardEvent) {
            if (event.key !== "Escape") return;
            setOpen(false);
            trigger.current?.focus();
        }
        document.addEventListener("pointerdown", dismissOnOutsidePointer);
        document.addEventListener("focusin", dismissOnOutsideFocus);
        document.addEventListener("keydown", dismissOnEscape);
        return () => {
            document.removeEventListener(
                "pointerdown",
                dismissOnOutsidePointer,
            );
            document.removeEventListener("focusin", dismissOnOutsideFocus);
            document.removeEventListener("keydown", dismissOnEscape);
        };
    }, [open]);

    // Fixed to the window, beside the control, and inside the visual
    // viewport: the on-screen keyboard shrinks that without changing the
    // layout viewport.
    const place = useCallback(() => {
        const box = panel.current;
        const anchorNode = root.current;
        if (!box || !anchorNode) return;
        const viewport = window.visualViewport;
        const left = viewport ? viewport.offsetLeft : 0;
        const top = viewport ? viewport.offsetTop : 0;
        const room = viewport
            ? viewport.width
            : document.documentElement.clientWidth;
        const drop = viewport
            ? viewport.height
            : document.documentElement.clientHeight;
        const anchor = anchorNode.getBoundingClientRect();
        const width = box.offsetWidth;
        const at = align === "end" ? anchor.right - width : anchor.left;
        const x = Math.max(
            left + GUTTER,
            Math.min(at, left + room - GUTTER - width),
        );
        const preferred =
            21.25 *
            parseFloat(getComputedStyle(document.documentElement).fontSize);
        const below = Math.max(0, top + drop - GUTTER - anchor.bottom - GAP);
        const above = Math.max(0, anchor.top - GAP - top - GUTTER);
        const opensAbove =
            below < Math.min(box.scrollHeight, preferred) && above > below;
        const available = Math.min(
            drop - 2 * GUTTER,
            opensAbove ? above : below,
        );
        const maxHeight = Math.max(0, Math.min(preferred, available));
        const height = Math.min(box.scrollHeight, maxHeight);
        const y = opensAbove ? anchor.top - GAP - height : anchor.bottom + GAP;
        const next: CSSProperties = {
            left: x,
            top: Math.max(
                top + GUTTER,
                Math.min(y, top + drop - GUTTER - height),
            ),
            maxHeight,
            scrollPaddingTop: header.current?.offsetHeight ?? 0,
        };
        setPlaced((previous) =>
            previous && JSON.stringify(previous) === JSON.stringify(next)
                ? previous
                : next,
        );
    }, [align]);

    useLayoutEffect(() => {
        if (!open) return;
        place();
    }, [open, place, rows.length, loading, failed]);

    useEffect(() => {
        if (!open) return;
        function replace(event: Event) {
            // A scroll inside the panel is the list moving, not the page.
            if (
                event.type === "scroll" &&
                panel.current?.contains(event.target as Node)
            )
                return;
            requestAnimationFrame(place);
        }
        const viewport = window.visualViewport;
        viewport?.addEventListener("resize", replace);
        viewport?.addEventListener("scroll", replace);
        window.addEventListener("resize", replace);
        window.addEventListener("scroll", replace, true);
        return () => {
            viewport?.removeEventListener("resize", replace);
            viewport?.removeEventListener("scroll", replace);
            window.removeEventListener("resize", replace);
            window.removeEventListener("scroll", replace, true);
        };
    }, [open, place]);

    // A list shorter than the panel never scrolls, so it would never ask
    // for the page after it.
    useEffect(() => {
        const box = panel.current;
        if (!open || !box || !placed) return;
        if (box.scrollHeight - box.scrollTop - box.clientHeight < PREFETCH)
            loadMore();
    }, [open, placed, rows.length, loadMore]);

    function onScroll() {
        const box = panel.current;
        if (!box) return;
        if (box.scrollHeight - box.scrollTop - box.clientHeight < PREFETCH)
            loadMore();
    }

    function move(step: number) {
        if (!rows.length) {
            setActive(-1);
            return;
        }
        const to =
            active < 0
                ? step > 0
                    ? 0
                    : rows.length - 1
                : (active + step + rows.length) % rows.length;
        setActive(to);
        document
            .getElementById(`${listId}-${to}`)
            ?.scrollIntoView({ block: "nearest" });
    }

    function keys(event: KeyboardEvent<HTMLInputElement>) {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            move(event.key === "ArrowDown" ? 1 : -1);
        } else if (event.key === "Enter") {
            const row = document.getElementById(`${listId}-${active}`);
            if (active < 0 || !row) return;
            event.preventDefault();
            row.click();
        } else if (event.key === "Escape") {
            // Clearing the search is the smaller thing to undo; Escape
            // again closes.
            event.stopPropagation();
            event.nativeEvent.stopImmediatePropagation();
            if (query) {
                setQuery("");
                setActive(-1);
            } else {
                closeAndFocus();
            }
        }
    }

    // Width is settled before placing, so the first measurement is the
    // one that sticks. Transparent rather than hidden until placed, because
    // a hidden search box cannot take focus.
    const panelStyle: CSSProperties = {
        minWidth: `min(${minWidth}, calc(100vw - ${2 * GUTTER}px))`,
        maxWidth: `calc(100vw - ${2 * GUTTER}px)`,
        ...(placed ?? { opacity: 0, left: GUTTER, top: 0 }),
    };

    return (
        <div ref={root} data-quick-switcher className={recipe.root}>
            <div role="group" className={recipe.group}>
                {label && (
                    <a href={href} className={recipe.label}>
                        <span className={recipe.labelContent}>
                            <span className={recipe.labelText}>{label}</span>
                        </span>
                    </a>
                )}
                <button
                    ref={trigger}
                    type="button"
                    className={recipe.chevron}
                    aria-label={name}
                    title={
                        hotkey ? `${name} (⌥⇧${hotkey.toUpperCase()})` : name
                    }
                    aria-keyshortcuts={
                        hotkey ? `Alt+Shift+${hotkey.toUpperCase()}` : undefined
                    }
                    aria-haspopup="menu"
                    aria-expanded={open}
                    aria-controls={open ? panelId : undefined}
                    onClick={() => (open ? close() : show())}
                >
                    <span className={recipe.chevronIcon}>
                        <SvgIcon
                            name="chevron-down"
                            strokeWidth={2.5}
                            className={`${recipe.chevronSvg} ${open ? "rotate-180" : ""}`}
                        />
                    </span>
                </button>
            </div>
            {open && (
                <div
                    ref={panel}
                    id={panelId}
                    className={`${recipe.panel} fixed`}
                    style={panelStyle}
                    onScroll={onScroll}
                >
                    <div className={recipe.body}>
                        <div ref={header} className={recipe.header}>
                            <div className={recipe.inputGroup}>
                                <div className={recipe.inputIcon}>
                                    <SvgIcon
                                        name="search"
                                        strokeWidth={1.5}
                                        className="size-4"
                                    />
                                </div>
                                <input
                                    ref={input}
                                    type="search"
                                    className={recipe.input}
                                    placeholder={placeholder}
                                    aria-label={placeholder}
                                    autoComplete="off"
                                    value={query}
                                    onChange={(event) => {
                                        setQuery(event.target.value);
                                        setActive(-1);
                                    }}
                                    onKeyDown={keys}
                                    aria-controls={listId}
                                    aria-activedescendant={
                                        active >= 0
                                            ? `${listId}-${active}`
                                            : undefined
                                    }
                                />
                            </div>
                        </div>
                        <div
                            id={listId}
                            role="menu"
                            aria-label={heading}
                            aria-busy={loading || searching}
                        >
                            {rows.map((row, index) => {
                                const here = row.href === current;
                                return (
                                    <a
                                        key={row.href}
                                        id={`${listId}-${index}`}
                                        href={row.href}
                                        role="menuitem"
                                        aria-current={here ? "page" : undefined}
                                        className={`${recipe.row} ${here ? recipe.rowCurrent : recipe.rowOther} ${active === index ? recipe.rowHighlight : ""}`}
                                        onMouseEnter={() => setActive(index)}
                                        onClick={close}
                                    >
                                        <span className={recipe.rowLabel}>
                                            {row.label}
                                        </span>
                                        {here && (
                                            <SvgIcon
                                                name="check"
                                                strokeWidth={2}
                                                className={recipe.rowCheck}
                                            />
                                        )}
                                    </a>
                                );
                            })}
                        </div>
                        {failed ? (
                            <p role="alert" className={recipe.empty}>
                                The list did not load.{" "}
                                <button
                                    type="button"
                                    className="underline"
                                    onClick={() =>
                                        fetchPage(
                                            query.trim(),
                                            shownQuery === query.trim()
                                                ? (listing.next ?? 0)
                                                : 0,
                                        )
                                    }
                                >
                                    Try again
                                </button>
                            </p>
                        ) : loading || searching ? (
                            <p role="status" className={recipe.empty}>
                                Loading…
                            </p>
                        ) : (
                            rows.length === 0 && (
                                <p className={recipe.empty}>{empty}</p>
                            )
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
