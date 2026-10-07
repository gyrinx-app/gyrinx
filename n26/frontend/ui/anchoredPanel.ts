import {
    useEffect,
    useLayoutEffect,
    useRef,
    useState,
    type CSSProperties,
    type RefObject,
} from "react";

/**
 * Closes an open panel when the reader moves on: a pointer pressed outside
 * `root`, focus landing outside it, or Escape anywhere.
 *
 * Escape closes and returns focus to `trigger`. `onEscape` replaces both, for
 * a panel whose Escape does more than close. A control inside the panel that
 * handles Escape itself stops the event there and this never sees it.
 */
export function useDismiss(
    root: RefObject<HTMLElement | null>,
    trigger: RefObject<HTMLElement | null>,
    open: boolean,
    onClose: () => void,
    { onEscape }: { onEscape?: () => void } = {},
) {
    const handlers = useRef({ onClose, onEscape });
    useLayoutEffect(() => {
        handlers.current = { onClose, onEscape };
    });

    useEffect(() => {
        if (!open) return;

        function dismissOutside(event: Event) {
            if (!root.current?.contains(event.target as Node))
                handlers.current.onClose();
        }

        function dismissOnEscape(event: KeyboardEvent) {
            if (event.key !== "Escape") return;
            const { onClose, onEscape } = handlers.current;
            if (onEscape) {
                onEscape();
                return;
            }
            onClose();
            trigger.current?.focus();
        }

        document.addEventListener("pointerdown", dismissOutside);
        document.addEventListener("focusin", dismissOutside);
        document.addEventListener("keydown", dismissOnEscape);
        return () => {
            document.removeEventListener("pointerdown", dismissOutside);
            document.removeEventListener("focusin", dismissOutside);
            document.removeEventListener("keydown", dismissOnEscape);
        };
    }, [open, root, trigger]);
}

export type AnchoredPlacementOptions = {
    open: boolean;
    trigger: RefObject<HTMLElement | null>;
    panel: RefObject<HTMLElement | null>;
    /** Which edge of the trigger the panel lines up with. */
    align?: "start" | "end";
    /**
     * A width in pixels, narrowed to fit the window, or "content" to let the
     * panel size itself between `minWidth` and the window.
     */
    width: number | "content";
    /** A CSS length. Used only when `width` is "content". */
    minWidth?: string;
    /** Space between the trigger and the panel, in pixels. */
    gap: number;
    /** Space kept clear of the window's edges, in pixels. */
    margin?: number;
    /**
     * Off: the panel opens below, or above when only above has room for all
     * of it. On: the panel takes the side with more room when it overflows
     * below, and its height is capped to the room on that side.
     */
    clampHeight?: boolean;
};

const MIN_CLAMPED_HEIGHT = 80;

function contentWidth(minWidth: string, margin: number): CSSProperties {
    const room = `calc(100vw - ${2 * margin}px)`;
    return { minWidth: `min(${minWidth}, ${room})`, maxWidth: room };
}

function hiddenStyle(
    width: number | "content",
    minWidth: string,
    margin: number,
): CSSProperties {
    // A content-sized panel is measured at the window's top left, so the
    // space to its right never narrows it.
    if (width !== "content") return { visibility: "hidden" };
    return {
        visibility: "hidden",
        left: 0,
        top: 0,
        ...contentWidth(minWidth, margin),
    };
}

function sameStyle(a: CSSProperties, b: CSSProperties) {
    const keys = Object.keys(a) as (keyof CSSProperties)[];
    return (
        keys.length === Object.keys(b).length &&
        keys.every((key) => a[key] === b[key])
    );
}

/**
 * Places a `position: fixed` panel beside its trigger, inside the window, so
 * no scrolling ancestor clips it. Returns the panel's style: hidden until the
 * first placement, then placed again on every resize and scroll.
 */
export function useAnchoredPlacement({
    open,
    trigger,
    panel,
    align = "start",
    width,
    minWidth = "0px",
    gap,
    margin = 16,
    clampHeight = false,
}: AnchoredPlacementOptions): CSSProperties {
    const [style, setStyle] = useState<CSSProperties>(() =>
        hiddenStyle(width, minWidth, margin),
    );

    useLayoutEffect(() => {
        if (!open) return;

        function place() {
            if (!trigger.current || !panel.current) return;
            const box = panel.current;
            const anchor = trigger.current.getBoundingClientRect();
            const panelWidth =
                width === "content"
                    ? box.offsetWidth
                    : Math.min(width, window.innerWidth - margin * 2);
            const at =
                align === "end" ? anchor.right - panelWidth : anchor.left;
            const left = Math.min(
                Math.max(margin, at),
                window.innerWidth - panelWidth - margin,
            );
            const sizing =
                width === "content"
                    ? contentWidth(minWidth, margin)
                    : { width: panelWidth };

            let next: CSSProperties;
            if (clampHeight) {
                const belowTop = Math.min(
                    Math.max(margin, anchor.bottom + gap),
                    window.innerHeight - margin,
                );
                const aboveBottom = Math.max(
                    margin,
                    Math.min(anchor.top - gap, window.innerHeight - margin),
                );
                const below = window.innerHeight - margin - belowTop;
                const above = aboveBottom - margin;
                const opensAbove = box.scrollHeight > below && above > below;
                const maxHeight = Math.max(
                    MIN_CLAMPED_HEIGHT,
                    opensAbove ? above : below,
                );
                const height = Math.min(box.scrollHeight, maxHeight);
                const top = opensAbove
                    ? Math.max(margin, aboveBottom - height)
                    : belowTop;
                next = {
                    visibility: "visible",
                    left,
                    top,
                    ...sizing,
                    maxHeight,
                };
            } else {
                const height = box.offsetHeight;
                const below = anchor.bottom + gap;
                const top =
                    below + height > window.innerHeight - margin &&
                    anchor.top - gap - height >= margin
                        ? anchor.top - gap - height
                        : below;
                next = { visibility: "visible", left, top, ...sizing };
            }
            setStyle((previous) =>
                sameStyle(previous, next) ? previous : next,
            );
        }

        place();
        window.addEventListener("resize", place);
        window.addEventListener("scroll", place, true);
        return () => {
            window.removeEventListener("resize", place);
            window.removeEventListener("scroll", place, true);
            // Reopening measures the panel unplaced again, as the first
            // opening did.
            setStyle(hiddenStyle(width, minWidth, margin));
        };
    }, [
        open,
        trigger,
        panel,
        align,
        width,
        minWidth,
        gap,
        margin,
        clampHeight,
    ]);

    return style;
}
