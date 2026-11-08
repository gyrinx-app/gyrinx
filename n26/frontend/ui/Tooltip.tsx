import {
    cloneElement,
    type ReactElement,
    useEffect,
    useId,
    useLayoutEffect,
    useRef,
    useState,
    type CSSProperties,
} from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";

/** Supplement a control with help on hover and focus, without stealing focus. */
export function Tooltip({
    label,
    children,
    size = "md",
    closeOnActivate = true,
}: {
    label: string;
    size?: "md" | "sm";
    closeOnActivate?: boolean;
    children: ReactElement<{ "aria-describedby"?: string }>;
}) {
    const id = useId();
    const root = useRef<HTMLSpanElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const timer = useRef<number | undefined>(undefined);
    const [open, setOpen] = useState(false);
    const [arrow, setArrow] = useState<CSSProperties>({});
    const style = useAnchoredPlacement({
        open,
        trigger: root,
        panel,
        width: "content",
        minWidth: "0px",
        gap: size === "sm" ? 8 : 6,
        align: size === "sm" ? "center" : "start",
        preferredSide: size === "sm" ? "top" : "bottom",
    });
    useLayoutEffect(() => {
        if (!open || size !== "sm" || !root.current || !panel.current) return;
        const anchor = root.current.getBoundingClientRect();
        const above = Number(style.top) < anchor.top;
        setArrow({
            left: Math.max(
                8,
                Math.min(
                    panel.current.offsetWidth - 8,
                    anchor.left + anchor.width / 2 - Number(style.left),
                ),
            ),
            [above ? "bottom" : "top"]: -4,
            transform: "translateX(-50%) rotate(45deg)",
        });
    }, [open, size, style]);
    const close = () => {
        window.clearTimeout(timer.current);
        setOpen(false);
    };
    const leave = () => {
        window.clearTimeout(timer.current);
        if (!root.current?.contains(document.activeElement))
            timer.current = window.setTimeout(() => setOpen(false), 200);
    };
    useDismiss(root, root, open, close, { onEscape: close });
    useEffect(() => () => window.clearTimeout(timer.current), []);
    return (
        <span
            ref={root}
            className="inline-flex"
            onMouseEnter={() => {
                window.clearTimeout(timer.current);
                timer.current = window.setTimeout(() => setOpen(true), 120);
            }}
            onMouseLeave={leave}
            onFocusCapture={() => {
                window.clearTimeout(timer.current);
                setOpen(true);
            }}
            onBlurCapture={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) close();
            }}
            onPointerDownCapture={closeOnActivate ? close : undefined}
            onClickCapture={closeOnActivate ? close : undefined}
            onKeyDown={(event) => {
                if (open && event.key === "Escape") {
                    event.preventDefault();
                    event.stopPropagation();
                    close();
                }
            }}
        >
            {cloneElement(children, {
                "aria-describedby": [children.props["aria-describedby"], id]
                    .filter(Boolean)
                    .join(" "),
            })}
            <div
                ref={panel}
                id={id}
                role="tooltip"
                hidden={!open}
                className={`${size === "sm" ? cotton.tooltip.small : cotton.tooltip.panel} fixed whitespace-normal`}
                style={{
                    ...style,
                    maxWidth: "min(var(--container-xs), calc(100vw - 32px))",
                }}
                onMouseEnter={() => window.clearTimeout(timer.current)}
                onMouseLeave={leave}
            >
                {label}
                {size === "sm" && (
                    <span
                        aria-hidden="true"
                        className={cotton.tooltip.arrow}
                        style={arrow}
                    />
                )}
            </div>
        </span>
    );
}
