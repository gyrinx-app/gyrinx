import {
    createElement,
    useEffect,
    useId,
    useLayoutEffect,
    useRef,
    useState,
    type CSSProperties,
} from "react";
import cotton from "../generated/cotton.json";

export type FilterOption = {
    value: string;
    label: string;
};

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

export function FilterMenu({
    label,
    options,
    onApply,
}: {
    label: string;
    options: FilterOption[];
    onApply: (values: string[]) => void;
}) {
    const panelId = useId();
    const root = useRef<HTMLDivElement>(null);
    const trigger = useRef<HTMLButtonElement>(null);
    const panel = useRef<HTMLDivElement>(null);
    const snapshot = useRef<string[]>([]);
    const [open, setOpen] = useState(false);
    const [panelStyle, setPanelStyle] = useState<CSSProperties>({
        visibility: "hidden",
    });
    const [values, setValues] = useState(() =>
        options.map((option) => option.value),
    );

    useEffect(() => {
        if (!open) return;

        function dismissOnOutsideClick(event: PointerEvent) {
            if (!root.current?.contains(event.target as Node)) setOpen(false);
        }

        function dismissOnOutsideFocus(event: FocusEvent) {
            if (!root.current?.contains(event.target as Node)) setOpen(false);
        }

        function dismissOnEscape(event: KeyboardEvent) {
            if (event.key !== "Escape") return;
            setOpen(false);
            trigger.current?.focus();
        }

        document.addEventListener("pointerdown", dismissOnOutsideClick);
        document.addEventListener("focusin", dismissOnOutsideFocus);
        document.addEventListener("keydown", dismissOnEscape);
        return () => {
            document.removeEventListener("pointerdown", dismissOnOutsideClick);
            document.removeEventListener("focusin", dismissOnOutsideFocus);
            document.removeEventListener("keydown", dismissOnEscape);
        };
    }, [open]);

    useLayoutEffect(() => {
        if (!open) return;

        function placePanel() {
            if (!trigger.current || !panel.current) return;
            const margin = 16;
            const gap = 4;
            const anchor = trigger.current.getBoundingClientRect();
            const width = Math.min(320, window.innerWidth - margin * 2);
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
            const opensAbove =
                panel.current.scrollHeight > below && above > below;
            const maxHeight = Math.max(80, opensAbove ? above : below);
            const height = Math.min(panel.current.scrollHeight, maxHeight);
            const top = opensAbove
                ? Math.max(margin, aboveBottom - height)
                : belowTop;
            const left = Math.min(
                Math.max(margin, anchor.left),
                window.innerWidth - width - margin,
            );
            const nextStyle = {
                visibility: "visible",
                left,
                top,
                width,
                maxHeight,
            } satisfies CSSProperties;
            setPanelStyle((previous) =>
                previous.visibility === nextStyle.visibility &&
                previous.left === nextStyle.left &&
                previous.top === nextStyle.top &&
                previous.width === nextStyle.width &&
                previous.maxHeight === nextStyle.maxHeight
                    ? previous
                    : nextStyle,
            );
        }

        placePanel();
        window.addEventListener("resize", placePanel);
        window.addEventListener("scroll", placePanel, true);
        return () => {
            window.removeEventListener("resize", placePanel);
            window.removeEventListener("scroll", placePanel, true);
        };
    }, [open]);

    function show() {
        snapshot.current = values.slice();
        setPanelStyle({ visibility: "hidden" });
        setOpen(true);
    }

    function closeAndFocus() {
        setOpen(false);
        trigger.current?.focus();
    }

    function select(value: string, selected: boolean) {
        setValues((previous) => {
            if (selected) {
                return options
                    .map((option) => option.value)
                    .filter(
                        (candidate) =>
                            candidate === value || previous.includes(candidate),
                    );
            }
            return previous.filter((candidate) => candidate !== value);
        });
    }

    return (
        <div ref={root} className={cotton.filterMenu.root}>
            <button
                ref={trigger}
                type="button"
                className={cotton.filterMenu.trigger}
                aria-expanded={open}
                aria-controls={panelId}
                onClick={() => (open ? setOpen(false) : show())}
            >
                <span className={cotton.filterMenu.triggerContent}>
                    {label}
                    {values.length !== options.length && (
                        <span className={cotton.filterMenu.count}>
                            {values.length}
                        </span>
                    )}
                    <ChevronDown />
                </span>
            </button>
            {open && (
                <div
                    ref={panel}
                    id={panelId}
                    role="group"
                    aria-label={`Filter: ${label}`}
                    className={`${cotton.filterMenu.panel} fixed`}
                    style={panelStyle}
                >
                    <div className={cotton.filterMenu.body}>
                        <div className={cotton.filterMenu.quickActions}>
                            <button
                                type="button"
                                className={cotton.filterMenu.quickAction}
                                onClick={() =>
                                    setValues(
                                        options.map((option) => option.value),
                                    )
                                }
                            >
                                All
                            </button>
                            <span className={cotton.filterMenu.separator}>
                                /
                            </span>
                            <button
                                type="button"
                                className={cotton.filterMenu.quickAction}
                                onClick={() => setValues([])}
                            >
                                None
                            </button>
                        </div>
                        <div className={cotton.filterMenu.options}>
                            {options.map((option) => (
                                <div
                                    key={option.value}
                                    className={cotton.filterMenu.option}
                                >
                                    <label
                                        role="checkbox"
                                        aria-checked={values.includes(
                                            option.value,
                                        )}
                                        tabIndex={0}
                                        className={`${cotton.filterMenu.checkbox} min-w-0 flex-1`}
                                        onClick={(event) => {
                                            event.preventDefault();
                                            select(
                                                option.value,
                                                !values.includes(option.value),
                                            );
                                        }}
                                        onKeyDown={(event) => {
                                            if (
                                                event.key !== "Enter" &&
                                                event.key !== " "
                                            )
                                                return;
                                            event.preventDefault();
                                            select(
                                                option.value,
                                                !values.includes(option.value),
                                            );
                                        }}
                                    >
                                        <input
                                            type="checkbox"
                                            tabIndex={-1}
                                            aria-hidden="true"
                                            className={
                                                cotton.filterMenu.checkboxInput
                                            }
                                            checked={values.includes(
                                                option.value,
                                            )}
                                            disabled
                                            readOnly
                                        />
                                        <span
                                            aria-hidden="true"
                                            className={
                                                cotton.filterMenu
                                                    .checkboxIndicatorWrap
                                            }
                                        >
                                            <span
                                                className={`${cotton.filterMenu.checkboxIndicator} ${
                                                    values.includes(
                                                        option.value,
                                                    )
                                                        ? cotton.filterMenu
                                                              .checkboxIndicatorChecked
                                                        : cotton.filterMenu
                                                              .checkboxIndicatorUnchecked
                                                }`}
                                            >
                                                <svg
                                                    className={`${cotton.filterMenu.checkboxCheck} ${
                                                        values.includes(
                                                            option.value,
                                                        )
                                                            ? cotton.filterMenu
                                                                  .checkboxCheckChecked
                                                            : cotton.filterMenu
                                                                  .checkboxCheckUnchecked
                                                    }`}
                                                    fill="none"
                                                    viewBox="0 0 24 24"
                                                    stroke="currentColor"
                                                    strokeWidth="3"
                                                >
                                                    <path
                                                        strokeLinecap="round"
                                                        strokeLinejoin="round"
                                                        d="M5 13l4 4L19 7"
                                                    />
                                                </svg>
                                            </span>
                                        </span>
                                        <span
                                            className={
                                                cotton.filterMenu
                                                    .checkboxContent
                                            }
                                        >
                                            <span
                                                className={
                                                    cotton.filterMenu
                                                        .checkboxText
                                                }
                                            >
                                                {option.label}
                                            </span>
                                        </span>
                                    </label>
                                    <span
                                        className={cotton.filterMenu.separator}
                                    >
                                        ·
                                    </span>
                                    <button
                                        type="button"
                                        className={cotton.filterMenu.only}
                                        aria-label={`Select only: ${option.label}`}
                                        onClick={() =>
                                            setValues([option.value])
                                        }
                                    >
                                        only
                                    </button>
                                </div>
                            ))}
                        </div>
                        <div className={cotton.filterMenu.actions}>
                            <button
                                type="button"
                                className={cotton.filterMenu.apply}
                                onClick={() => {
                                    onApply(values);
                                    closeAndFocus();
                                }}
                            >
                                OK
                            </button>
                            <button
                                type="button"
                                className={cotton.filterMenu.cancel}
                                onClick={() => {
                                    setValues(snapshot.current);
                                    closeAndFocus();
                                }}
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
