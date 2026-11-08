import {
    cloneElement,
    type ReactElement,
    useEffect,
    useId,
    useRef,
    useState,
} from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";

/** Supplement a control with help on hover and focus, without stealing focus. */
export function Tooltip({
    label,
    children,
}: {
    label: string;
    children: ReactElement<{ "aria-describedby"?: string }>;
}) {
    const id = useId();
    const root = useRef<HTMLSpanElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const timer = useRef<number | undefined>(undefined);
    const [open, setOpen] = useState(false);
    const style = useAnchoredPlacement({
        open,
        trigger: root,
        panel,
        width: "content",
        minWidth: "0px",
        gap: 6,
    });
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
            onPointerDownCapture={close}
            onClickCapture={close}
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
                className={`${cotton.tooltip.panel} fixed`}
                style={style}
                onMouseEnter={() => window.clearTimeout(timer.current)}
                onMouseLeave={leave}
            >
                {label}
            </div>
        </span>
    );
}
