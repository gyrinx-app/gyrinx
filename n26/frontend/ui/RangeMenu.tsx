import {
    createElement,
    useId,
    useRef,
    useState,
    type KeyboardEvent,
} from "react";
import cotton from "../generated/cotton.json";
import { useAnchoredPlacement, useDismiss } from "./anchoredPanel";

function ChevronDown() {
    return (
        <svg
            className="size-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            {cotton.icons["chevron-down"].map(({ tag, attrs }, key) =>
                createElement(tag, { ...attrs, key }),
            )}
        </svg>
    );
}

// Enter in a range input submits the surrounding form with its first button.
function swallowEnter(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") event.preventDefault();
}

/**
 * A menu that narrows a minimum and maximum, as the two-thumb
 * `<c-n26.range-menu>` draws it. Each drag applies at once: there is no OK.
 */
export function RangeMenu({
    label,
    min,
    max,
    step = 1,
    prefix = "",
    suffix = "",
    atMaxLabel = "",
    value,
    onChange,
}: {
    label: string;
    min: number;
    /** Must sit on a step: a native range reaches only min + n × step. */
    max: number;
    step?: number;
    prefix?: string;
    suffix?: string;
    /** Names the high end, and the trigger when nothing is narrowed. */
    atMaxLabel?: string;
    value: [number, number];
    onChange: (value: [number, number]) => void;
}) {
    const recipe = cotton.rangeMenu;
    const panelId = useId();
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const [open, setOpen] = useState(false);
    const [low, high] = value;
    const span = max - min || 1;
    const range = `${prefix}${low}–${high}${suffix}`;

    useDismiss(root, trigger, open, () => setOpen(false));
    const panelStyle = useAnchoredPlacement({
        open,
        trigger,
        panel,
        width: "content",
        minWidth: "16rem",
        gap: 4,
        clampHeight: true,
    });

    return (
        <div className={recipe.root}>
            <div ref={root} className={recipe.anchor}>
                <button
                    ref={trigger}
                    type="button"
                    className={recipe.trigger}
                    aria-expanded={open}
                    aria-controls={panelId}
                    onClick={() => setOpen(!open)}
                >
                    <span className={recipe.triggerContent}>
                        {label}
                        <span className={recipe.value}>
                            {atMaxLabel && low <= min && high >= max
                                ? atMaxLabel
                                : range}
                        </span>
                        <ChevronDown />
                    </span>
                </button>
                {open && (
                    <div
                        ref={panel}
                        id={panelId}
                        role="group"
                        aria-label={label}
                        className={`${recipe.panel} fixed`}
                        style={panelStyle}
                    >
                        <div className={recipe.body}>
                            <div className={recipe.heading}>
                                <span className={recipe.headingLabel}>
                                    {label}
                                </span>
                                <span className={recipe.headingValue}>
                                    {range}
                                </span>
                            </div>
                            <div className={recipe.slider}>
                                <div className={recipe.track} />
                                <div
                                    className={recipe.fill}
                                    style={{
                                        left: `${((low - min) / span) * 100}%`,
                                        right: `${100 - ((high - min) / span) * 100}%`,
                                    }}
                                />
                                <input
                                    type="range"
                                    aria-label={recipe.minimumLabel}
                                    min={min}
                                    max={max}
                                    step={step}
                                    value={low}
                                    onKeyDown={swallowEnter}
                                    onChange={(event) =>
                                        onChange([
                                            Math.min(
                                                Number(event.target.value),
                                                high,
                                            ),
                                            high,
                                        ])
                                    }
                                />
                                <input
                                    type="range"
                                    aria-label={recipe.maximumLabel}
                                    min={min}
                                    max={max}
                                    step={step}
                                    value={high}
                                    onKeyDown={swallowEnter}
                                    onChange={(event) =>
                                        onChange([
                                            low,
                                            Math.max(
                                                Number(event.target.value),
                                                low,
                                            ),
                                        ])
                                    }
                                />
                            </div>
                            <div className={recipe.ends}>
                                <span>{min}</span>
                                <span>{atMaxLabel || max}</span>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
