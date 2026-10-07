import {
    createElement,
    type MouseEvent,
    type ReactNode,
    useEffect,
    useId,
    useRef,
    useState,
} from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";

const OPEN_DELAY = 120;
const CLOSE_DELAY = 200;

/**
 * A question-mark button that opens a short explanation.
 *
 * Hovering opens the panel and leaving closes it. A click keeps it open until
 * the next click, Escape, or a click or focus outside, so touch and keyboard
 * readers can open it too.
 */
const TONES = {
    help: {
        icon: "circle-question-mark",
        button: "inline-flex cursor-pointer items-center rounded-full text-ink-500 transition-colors hover:text-ink-900 focus-ring dark:text-ink-400 dark:hover:text-white",
        svg: "size-4",
    },
    warning: {
        icon: "triangle-alert",
        button: `${cotton.buttonSmall.ghost} n26-icon-only`,
        svg: "size-4 text-red-600 dark:text-red-400",
    },
} as const;

export function HelpPopover({
    label,
    triggerId,
    tone = "help",
    cta,
    triggerContent,
    children,
}: {
    label: string;
    triggerId?: string;
    tone?: keyof typeof TONES;
    /** A link under the explanation, for what the reader can do next. */
    cta?: { label: string; href: string };
    /** Text that opens the explanation, with a dashed underline. */
    triggerContent?: ReactNode;
    children: ReactNode;
}) {
    const look = TONES[tone];
    const panelId = useId();
    const root = useRef<HTMLSpanElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const timer = useRef<number | undefined>(undefined);
    const focusPanel = useRef(false);
    const [open, setOpen] = useState(false);
    const [pinned, setPinned] = useState(false);

    function close() {
        window.clearTimeout(timer.current);
        setOpen(false);
        setPinned(false);
    }

    function later(next: boolean, delay: number) {
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(
            () => (next ? setOpen(true) : close()),
            delay,
        );
    }

    useEffect(() => () => window.clearTimeout(timer.current), []);

    useEffect(() => {
        if (!open || !focusPanel.current) return;
        focusPanel.current = false;
        panel.current?.focus();
    }, [open, pinned]);

    useDismiss(root, trigger, open, close);
    const panelStyle = useAnchoredPlacement({
        open,
        trigger,
        panel,
        width: 288,
        gap: 8,
    });

    function onClick(event: MouseEvent<HTMLButtonElement>) {
        window.clearTimeout(timer.current);
        if (open && pinned) {
            close();
            return;
        }
        // A keyboard press reports no click count. Moving focus into the
        // panel is what tells a screen reader the explanation has opened.
        focusPanel.current = event.detail === 0;
        setOpen(true);
        setPinned(true);
    }

    return (
        <span
            ref={root}
            className="inline-flex align-middle"
            onMouseEnter={() => {
                if (!pinned) later(true, OPEN_DELAY);
            }}
            onMouseLeave={() => {
                if (!pinned) later(false, CLOSE_DELAY);
            }}
        >
            <button
                ref={trigger}
                id={triggerId}
                type="button"
                aria-label={label}
                aria-expanded={open}
                aria-controls={panelId}
                onClick={onClick}
                className={
                    triggerContent
                        ? `${cotton.explanationTrigger[0]} focus-ring`
                        : look.button
                }
            >
                {triggerContent ? (
                    <span className={cotton.explanationTrigger[1]}>
                        {triggerContent}
                    </span>
                ) : (
                    <svg
                        className={look.svg}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={2}
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                    >
                        {cotton.icons[look.icon].map(({ tag, attrs }, key) =>
                            createElement(tag, { ...attrs, key }),
                        )}
                    </svg>
                )}
            </button>
            {open && (
                <div
                    ref={panel}
                    id={panelId}
                    role="dialog"
                    aria-label={label}
                    tabIndex={-1}
                    className={`${cotton.popover.panel} fixed z-50 space-y-2 whitespace-normal font-normal`}
                    style={panelStyle}
                >
                    {children}
                    {cta && (
                        <p>
                            <a href={cta.href} className={cotton.link[0]}>
                                <span className={cotton.link[1]}>
                                    {cta.label}
                                </span>
                            </a>
                        </p>
                    )}
                </div>
            )}
        </span>
    );
}
