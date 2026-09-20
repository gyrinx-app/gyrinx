import {
    Children,
    type CSSProperties,
    type ReactNode,
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

export type { CSSProperties, RefObject } from "react";
export { useEffect, useMemo, useRef, useState } from "react";

type Tone = "success" | "danger" | "warning" | "info" | "neutral";
type Color =
    | "gray"
    | "blue"
    | "green"
    | "yellow"
    | "orange"
    | "red"
    | "purple"
    | "pink"
    | "cyan";

const categoryColours: Record<Color, string> = {
    gray: "var(--cv-category-gray)",
    blue: "var(--cv-category-blue)",
    green: "var(--cv-category-green)",
    yellow: "var(--cv-category-yellow)",
    orange: "var(--cv-category-orange)",
    red: "var(--cv-category-red)",
    purple: "var(--cv-category-purple)",
    pink: "var(--cv-category-pink)",
    cyan: "var(--cv-category-cyan)",
};

export const usageColorSequence: Color[] = [
    "gray",
    "purple",
    "green",
    "yellow",
    "pink",
    "blue",
    "orange",
    "cyan",
    "red",
];
export const colorPalette = categoryColours;
export const categoryPaletteDark = categoryColours;
export const categoryPaletteLight = categoryColours;

function createTheme(kind: "light" | "dark") {
    const theme: Record<string, unknown> = {
        kind,
        text: {
            primary: "var(--cv-text-primary)",
            secondary: "var(--cv-text-secondary)",
            tertiary: "var(--cv-text-tertiary)",
            quaternary: "var(--cv-text-quaternary)",
            link: "var(--cv-link)",
            onAccent: "var(--cv-on-accent)",
        },
        bg: {
            editor: "var(--cv-bg)",
            chrome: "var(--cv-chrome)",
            elevated: "var(--cv-elevated)",
        },
        fill: {
            primary: "var(--cv-fill-primary)",
            secondary: "var(--cv-fill-secondary)",
            tertiary: "var(--cv-fill-tertiary)",
            quaternary: "var(--cv-fill-quaternary)",
        },
        stroke: {
            primary: "var(--cv-stroke-primary)",
            secondary: "var(--cv-stroke-secondary)",
            tertiary: "var(--cv-stroke-tertiary)",
        },
        accent: {
            primary: "var(--cv-accent)",
            control: "var(--cv-accent)",
        },
        diff: {
            added: "var(--cv-success)",
            deleted: "var(--cv-danger)",
        },
        category: categoryColours,
        palette: categoryColours,
    };
    theme.tokens = theme;
    return theme;
}

export const canvasTokensLight = createTheme("light");
export const canvasTokens = createTheme("dark");
export const canvasPaletteLight = categoryColours;
export const canvasPaletteDark = categoryColours;

export function useHostTheme(): any {
    const [dark, setDark] = useState(() =>
        typeof window === "undefined"
            ? false
            : window.matchMedia("(prefers-color-scheme: dark)").matches,
    );
    useEffect(() => {
        const media = window.matchMedia("(prefers-color-scheme: dark)");
        const update = () => setDark(media.matches);
        media.addEventListener("change", update);
        return () => media.removeEventListener("change", update);
    }, []);
    return dark ? canvasTokens : canvasTokensLight;
}

export function useCanvasState<T>(
    key: string,
    defaultValue: T,
): [T, (value: T | ((previous: T) => T)) => void] {
    const canvasId =
        typeof window === "undefined"
            ? "server"
            : (window.__canvasViewerCanvasId ?? "canvas");
    const storageKey = `gyrinx-canvas-viewer:${canvasId}:${key}`;
    const [value, setValue] = useState<T>(() => {
        if (typeof window === "undefined") return defaultValue;
        const stored = window.localStorage.getItem(storageKey);
        if (!stored) return defaultValue;
        try {
            return JSON.parse(stored) as T;
        } catch {
            return defaultValue;
        }
    });
    useEffect(() => {
        window.localStorage.setItem(storageKey, JSON.stringify(value));
    }, [storageKey, value]);
    return [value, setValue];
}

export function useCanvasAction() {
    return useCallback((action: Record<string, unknown>) => {
        window.dispatchEvent(
            new CustomEvent("canvas-viewer-action", { detail: action }),
        );
    }, []);
}

export function mergeStyle(
    base: CSSProperties,
    override?: CSSProperties,
): CSSProperties {
    return { ...base, ...override };
}

export function Stack({
    children,
    gap = 12,
    style,
}: {
    children?: ReactNode;
    gap?: number;
    style?: CSSProperties;
}) {
    return (
        <div className="cv-stack" style={{ gap, ...style }}>
            {children}
        </div>
    );
}

export function Row({
    children,
    gap = 8,
    align = "center",
    justify = "start",
    wrap = false,
    style,
}: {
    children?: ReactNode;
    gap?: number;
    align?: "start" | "center" | "end" | "stretch";
    justify?: "start" | "center" | "end" | "space-between";
    wrap?: boolean;
    style?: CSSProperties;
}) {
    return (
        <div
            className="cv-row"
            style={{
                gap,
                alignItems:
                    align === "start"
                        ? "flex-start"
                        : align === "end"
                          ? "flex-end"
                          : align,
                justifyContent:
                    justify === "start"
                        ? "flex-start"
                        : justify === "end"
                          ? "flex-end"
                          : justify,
                flexWrap: wrap ? "wrap" : "nowrap",
                ...style,
            }}
        >
            {children}
        </div>
    );
}

export function Grid({
    children,
    columns,
    gap = 12,
    align = "stretch",
    style,
}: {
    children?: ReactNode;
    columns: number | string;
    gap?: number;
    align?: "start" | "center" | "end" | "stretch";
    style?: CSSProperties;
}) {
    return (
        <div
            className="cv-grid"
            style={{
                gridTemplateColumns:
                    typeof columns === "number"
                        ? `repeat(${columns}, minmax(0, 1fr))`
                        : columns,
                gap,
                alignItems: align,
                ...style,
            }}
        >
            {children}
        </div>
    );
}

export function Divider({ style }: { style?: CSSProperties }) {
    return <hr className="cv-divider" style={style} />;
}

export function Spacer() {
    return <span style={{ flex: 1 }} />;
}

function Heading({
    level,
    children,
    style,
}: {
    level: 1 | 2 | 3;
    children?: ReactNode;
    style?: CSSProperties;
}) {
    const Tag = `h${level}` as const;
    return (
        <Tag className={`cv-h${level}`} style={style}>
            {children}
        </Tag>
    );
}

export function H1(props: { children?: ReactNode; style?: CSSProperties }) {
    return <Heading level={1} {...props} />;
}
export function H2(props: { children?: ReactNode; style?: CSSProperties }) {
    return <Heading level={2} {...props} />;
}
export function H3(props: { children?: ReactNode; style?: CSSProperties }) {
    return <Heading level={3} {...props} />;
}

export function Text({
    children,
    tone = "primary",
    size = "body",
    as = "p",
    weight = "normal",
    italic = false,
    truncate = false,
    style,
}: {
    children?: ReactNode;
    tone?: "primary" | "secondary" | "tertiary" | "quaternary";
    size?: "body" | "small";
    as?: "p" | "span";
    weight?: "normal" | "medium" | "semibold" | "bold";
    italic?: boolean;
    truncate?: boolean | "start" | "end";
    style?: CSSProperties;
}) {
    const Tag = as;
    return (
        <Tag
            className={`cv-text cv-text-${tone} cv-text-${size}`}
            style={{
                fontWeight:
                    weight === "medium"
                        ? 500
                        : weight === "semibold"
                          ? 600
                          : weight === "bold"
                            ? 700
                            : 400,
                fontStyle: italic ? "italic" : undefined,
                overflow: truncate ? "hidden" : undefined,
                textOverflow: truncate ? "ellipsis" : undefined,
                whiteSpace: truncate ? "nowrap" : undefined,
                direction: truncate === "start" ? "rtl" : undefined,
                textAlign: truncate === "start" ? "left" : undefined,
                ...style,
            }}
        >
            {children}
        </Tag>
    );
}

export function Code({
    children,
    style,
}: {
    children?: ReactNode;
    style?: CSSProperties;
}) {
    return (
        <code className="cv-code" style={style}>
            {children}
        </code>
    );
}

export function Link({
    children,
    href,
    style,
}: {
    children?: ReactNode;
    href: string;
    style?: CSSProperties;
}) {
    return (
        <a
            className="cv-link"
            href={href}
            target="_blank"
            rel="noreferrer"
            style={style}
        >
            {children}
        </a>
    );
}

export function Card({
    children,
    variant = "default",
    size = "base",
    stickyHeader = false,
    collapsible = false,
    defaultOpen = true,
    open: controlledOpen,
    onOpenChange,
    style,
}: {
    children?: ReactNode;
    variant?: "default" | "borderless";
    size?: "base" | "lg";
    stickyHeader?: boolean;
    collapsible?: boolean;
    defaultOpen?: boolean;
    open?: boolean;
    onOpenChange?: (open: boolean) => void;
    style?: CSSProperties;
}) {
    const [ownOpen, setOwnOpen] = useState(defaultOpen);
    const open = controlledOpen ?? ownOpen;
    const parts = Children.toArray(children);
    const header = parts.find(
        (child) =>
            typeof child === "object" &&
            child &&
            "type" in child &&
            child.type === CardHeader,
    );
    const body = parts.filter((child) => child !== header);
    const toggle = () => {
        const next = !open;
        setOwnOpen(next);
        onOpenChange?.(next);
    };
    return (
        <section
            className={`cv-card cv-card-${variant} cv-card-${size} ${stickyHeader ? "cv-card-sticky" : ""}`}
            style={style}
        >
            {collapsible && header ? (
                <button
                    className="cv-card-toggle"
                    type="button"
                    onClick={toggle}
                >
                    <span aria-hidden="true">{open ? "⌄" : "›"}</span>
                    {header}
                </button>
            ) : (
                header
            )}
            {(!collapsible || open) && body}
        </section>
    );
}

export function CardHeader({
    children,
    trailing,
    style,
}: {
    children?: ReactNode;
    trailing?: ReactNode;
    style?: CSSProperties;
}) {
    return (
        <div className="cv-card-header" style={style}>
            <span>{children}</span>
            {trailing && <span className="cv-card-trailing">{trailing}</span>}
        </div>
    );
}

export function CardBody({
    children,
    style,
}: {
    children?: ReactNode;
    style?: CSSProperties;
}) {
    if (children === undefined || children === null) return null;
    return (
        <div className="cv-card-body" style={style}>
            {children}
        </div>
    );
}

export function Button({
    children,
    variant = "secondary",
    disabled,
    type = "button",
    style,
    onClick,
}: {
    children?: ReactNode;
    variant?: "primary" | "secondary" | "ghost";
    disabled?: boolean;
    type?: "button" | "submit" | "reset";
    style?: CSSProperties;
    onClick?: () => void;
}) {
    return (
        <button
            className={`cv-button cv-button-${variant}`}
            disabled={disabled}
            type={type}
            style={style}
            onClick={onClick}
        >
            {children}
        </button>
    );
}

export function Pill({
    children,
    active = false,
    size = "md",
    leadingContent,
    keyboardHint,
    disabled,
    title,
    style,
    onClick,
}: {
    children?: ReactNode;
    active?: boolean;
    size?: "sm" | "md";
    leadingContent?: ReactNode;
    keyboardHint?: string;
    disabled?: boolean;
    title?: string;
    style?: CSSProperties;
    onClick?: () => void;
}) {
    const content = (
        <>
            {leadingContent}
            <span>{children}</span>
            {keyboardHint && <kbd>{keyboardHint}</kbd>}
        </>
    );
    return onClick ? (
        <button
            type="button"
            className={`cv-pill ${active ? "cv-pill-active" : ""} cv-pill-${size}`}
            disabled={disabled}
            title={title}
            style={style}
            onClick={onClick}
        >
            {content}
        </button>
    ) : (
        <span
            className={`cv-pill ${active ? "cv-pill-active" : ""} cv-pill-${size}`}
            title={title}
            style={style}
        >
            {content}
        </span>
    );
}

export function Stat({
    value,
    label,
    tone,
    style,
}: {
    value: ReactNode;
    label: string;
    tone?: Tone;
    style?: CSSProperties;
}) {
    return (
        <div
            className={`cv-stat ${tone ? `cv-tone-${tone}` : ""}`}
            style={style}
        >
            <div className="cv-stat-value">{value}</div>
            <div className="cv-stat-label">{label}</div>
        </div>
    );
}

export function Callout({
    children,
    tone = "info",
    title,
    icon,
    style,
}: {
    children?: ReactNode;
    tone?: Tone;
    title?: ReactNode;
    icon?: ReactNode;
    style?: CSSProperties;
}) {
    return (
        <div
            className={`cv-callout cv-callout-${tone}`}
            role="note"
            style={style}
        >
            <span className="cv-callout-icon" aria-hidden="true">
                {icon ??
                    (tone === "success"
                        ? "✓"
                        : tone === "info" || tone === "neutral"
                          ? "i"
                          : "!")}
            </span>
            <div>
                {title && <div className="cv-callout-title">{title}</div>}
                <div>{children}</div>
            </div>
        </div>
    );
}

export function Table({
    headers,
    rows,
    columnAlign = [],
    rowTone = [],
    framed = true,
    striped = false,
    stickyHeader = false,
    style,
    emptyMessage,
}: {
    headers: ReactNode[];
    rows: ReactNode[][];
    columnAlign?: Array<"left" | "center" | "right" | undefined>;
    rowTone?: Array<Tone | undefined>;
    framed?: boolean;
    striped?: boolean;
    stickyHeader?: boolean;
    style?: CSSProperties;
    emptyMessage?: ReactNode;
}) {
    return (
        <div
            className={`cv-table-frame ${framed ? "cv-table-framed" : ""}`}
            style={style}
        >
            <table className={`cv-table ${striped ? "cv-table-striped" : ""}`}>
                <thead className={stickyHeader ? "cv-table-sticky" : ""}>
                    <tr>
                        {headers.map((header, index) => (
                            <th
                                key={index}
                                style={{ textAlign: columnAlign[index] }}
                            >
                                {header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.length === 0 ? (
                        <tr>
                            <td colSpan={headers.length}>{emptyMessage}</td>
                        </tr>
                    ) : (
                        rows.map((row, rowIndex) => (
                            <tr
                                key={rowIndex}
                                className={
                                    rowTone[rowIndex]
                                        ? `cv-table-${rowTone[rowIndex]}`
                                        : ""
                                }
                            >
                                {headers.map((_, columnIndex) => (
                                    <td
                                        key={columnIndex}
                                        style={{
                                            textAlign: columnAlign[columnIndex],
                                        }}
                                    >
                                        {columnIndex === 0 &&
                                            rowTone[rowIndex] && (
                                                <span
                                                    className="cv-row-tone"
                                                    aria-hidden="true"
                                                />
                                            )}
                                        {row[columnIndex]}
                                    </td>
                                ))}
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    );
}

const inputClass = "cv-input";
export function TextInput({
    value,
    onChange,
    placeholder,
    disabled,
    type = "text",
    style,
}: any) {
    return (
        <input
            className={inputClass}
            value={value ?? ""}
            onChange={(event) => onChange?.(event.target.value)}
            placeholder={placeholder}
            disabled={disabled}
            type={type}
            style={style}
        />
    );
}
export function TextArea({
    value,
    onChange,
    placeholder,
    disabled,
    rows = 3,
    style,
}: any) {
    return (
        <textarea
            className={inputClass}
            value={value ?? ""}
            onChange={(event) => onChange?.(event.target.value)}
            placeholder={placeholder}
            disabled={disabled}
            rows={rows}
            style={style}
        />
    );
}
export function Checkbox({ checked, onChange, disabled, label, style }: any) {
    const input = (
        <input
            type="checkbox"
            checked={checked ?? false}
            onChange={(event) => onChange?.(event.target.checked)}
            disabled={disabled}
        />
    );
    return label ? (
        <label className="cv-checkbox" style={style}>
            {input}
            <span>{label}</span>
        </label>
    ) : (
        input
    );
}
export function Toggle({
    checked,
    onChange,
    disabled,
    size = "sm",
    style,
}: any) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked ?? false}
            className={`cv-toggle cv-toggle-${size} ${checked ? "cv-toggle-on" : ""}`}
            onClick={() => onChange?.(!checked)}
            disabled={disabled}
            style={style}
        >
            <span />
        </button>
    );
}
export function Select({
    value,
    onChange,
    options,
    placeholder,
    disabled,
    style,
}: any) {
    return (
        <select
            className={inputClass}
            value={value ?? ""}
            onChange={(event) => onChange?.(event.target.value)}
            disabled={disabled}
            style={style}
        >
            {placeholder && <option value="">{placeholder}</option>}
            {options.map((option: any) => (
                <option
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                >
                    {option.label}
                </option>
            ))}
        </select>
    );
}
export function IconButton({
    children,
    onClick,
    disabled,
    title,
    variant = "default",
    size = "md",
    style,
}: any) {
    return (
        <button
            type="button"
            className={`cv-icon-button cv-icon-button-${variant} cv-icon-button-${size}`}
            onClick={onClick}
            disabled={disabled}
            title={title}
            aria-label={title}
            style={style}
        >
            {children}
        </button>
    );
}

export function CollapsibleSection({
    title,
    leading,
    count,
    trailing,
    children,
    defaultOpen = false,
    style,
}: any) {
    const [open, setOpen] = useState<boolean>(defaultOpen);
    return (
        <section className="cv-collapsible" style={style}>
            <button
                type="button"
                className="cv-collapsible-toggle"
                onClick={() => setOpen((value) => !value)}
            >
                <span aria-hidden="true">{open ? "⌄" : "›"}</span>
                {leading}
                <strong>{title}</strong>
                {count !== undefined && (
                    <span className="cv-count">{count}</span>
                )}
                <span className="cv-collapsible-trailing">{trailing}</span>
            </button>
            {open && <div className="cv-collapsible-body">{children}</div>}
        </section>
    );
}

export function TodoList({ todos, dimmedTodoIds, onTodoClick, style }: any) {
    if (!todos?.length) return null;
    return (
        <div className="cv-todos" style={style}>
            {todos.map((todo: any) => (
                <button
                    type="button"
                    key={todo.id}
                    className={`cv-todo cv-todo-${todo.status}`}
                    style={{ opacity: dimmedTodoIds?.has(todo.id) ? 0.45 : 1 }}
                    onClick={() => onTodoClick?.(todo)}
                >
                    <span aria-hidden="true">
                        {todo.status === "completed"
                            ? "✓"
                            : todo.status === "cancelled"
                              ? "×"
                              : todo.status === "in_progress"
                                ? "→"
                                : "○"}
                    </span>
                    <span>{todo.content}</span>
                </button>
            ))}
        </div>
    );
}
export function TodoListCard({
    todos,
    dimmedTodoIds,
    defaultExpanded = false,
    onTodoClick,
    style,
}: any) {
    const complete = todos.filter(
        (todo: any) => todo.status === "completed",
    ).length;
    return (
        <Card collapsible defaultOpen={defaultExpanded} style={style}>
            <CardHeader>
                {complete} of {todos.length} done
            </CardHeader>
            <CardBody>
                <TodoList
                    todos={todos}
                    dimmedTodoIds={dimmedTodoIds}
                    onTodoClick={onTodoClick}
                />
            </CardBody>
        </Card>
    );
}

export function Swatch({
    color,
    style,
}: {
    color: Color;
    style?: CSSProperties;
}) {
    return (
        <span
            className="cv-swatch"
            style={{ background: categoryColours[color], ...style }}
        />
    );
}

export function UsageBar({
    segments,
    total,
    topLeftLabel,
    topRightLabel,
    style,
}: any) {
    const used = segments.reduce(
        (sum: number, segment: any) =>
            sum + Math.max(0, Number(segment.value) || 0),
        0,
    );
    return (
        <div className="cv-usage" style={style}>
            {(topLeftLabel || topRightLabel) && (
                <div className="cv-usage-labels">
                    <span>{topLeftLabel}</span>
                    <span>{topRightLabel}</span>
                </div>
            )}
            <div className="cv-usage-bar">
                {segments.map((segment: any, index: number) => {
                    const colour =
                        (segment.color as Color | undefined) ??
                        usageColorSequence[index % usageColorSequence.length] ??
                        "gray";
                    return (
                        <span
                            key={segment.id}
                            style={{
                                flex: Math.max(0, segment.value),
                                background: categoryColours[colour],
                            }}
                        />
                    );
                })}
                {total > used && (
                    <span
                        className="cv-usage-remainder"
                        style={{ flex: total - used }}
                    />
                )}
            </div>
        </div>
    );
}

export function DiffStats({ additions = 0, deletions = 0, style }: any) {
    if (!additions && !deletions) return null;
    return (
        <span className="cv-diff-stats" style={style}>
            {additions > 0 && (
                <span className="cv-diff-added">+{additions}</span>
            )}
            {deletions > 0 && (
                <span className="cv-diff-removed">−{deletions}</span>
            )}
        </span>
    );
}
export function DiffView({
    lines,
    showLineNumbers = true,
    coloredLineNumbers = true,
    showAccentStrip = true,
    style,
}: any) {
    return (
        <div className="cv-diff" style={style}>
            {lines.map((line: any, index: number) => (
                <div
                    key={index}
                    className={`cv-diff-line cv-diff-${line.type} ${showAccentStrip ? "cv-diff-accent" : ""}`}
                >
                    {showLineNumbers && (
                        <span
                            className={`cv-diff-number ${coloredLineNumbers ? `cv-diff-number-${line.type}` : ""}`}
                        >
                            {line.lineNumber ?? ""}
                        </span>
                    )}
                    <span className="cv-diff-sign">
                        {line.type === "added"
                            ? "+"
                            : line.type === "removed"
                              ? "−"
                              : " "}
                    </span>
                    <code>{line.content}</code>
                </div>
            ))}
        </div>
    );
}

function chartColour(series: any, index: number) {
    if (series?.tone)
        return `var(--cv-${series.tone === "neutral" ? "text-secondary" : series.tone})`;
    return categoryColours[
        usageColorSequence[(index + 1) % usageColorSequence.length]
    ];
}

export function BarChart({
    categories,
    series,
    height = 260,
    horizontal = false,
    valuePrefix = "",
    valueSuffix = "",
    showValues,
    style,
}: any) {
    const maximum = Math.max(1, ...series.flatMap((item: any) => item.data));
    return (
        <div
            className={`cv-chart ${horizontal ? "cv-chart-horizontal" : ""}`}
            style={{ minHeight: height, ...style }}
        >
            <div className="cv-chart-legend">
                {series.length > 1 &&
                    series.map((item: any, index: number) => (
                        <span key={item.name}>
                            <i
                                style={{ background: chartColour(item, index) }}
                            />
                            {item.name}
                        </span>
                    ))}
            </div>
            <div className="cv-bars">
                {categories.map((category: string, categoryIndex: number) => (
                    <div className="cv-bar-group" key={category}>
                        <div className="cv-bar-values">
                            {series.map((item: any, seriesIndex: number) => {
                                const value = item.data[categoryIndex] ?? 0;
                                return (
                                    <div
                                        key={item.name}
                                        className="cv-bar"
                                        title={`${item.name}: ${valuePrefix}${value}${valueSuffix}`}
                                        style={
                                            horizontal
                                                ? {
                                                      width: `${(value / maximum) * 100}%`,
                                                      background: chartColour(
                                                          item,
                                                          seriesIndex,
                                                      ),
                                                  }
                                                : {
                                                      height: `${(value / maximum) * Math.max(80, height - 90)}px`,
                                                      background: chartColour(
                                                          item,
                                                          seriesIndex,
                                                      ),
                                                  }
                                        }
                                    >
                                        {(showValues ??
                                            (series.length === 1 &&
                                                categories.length <= 8)) && (
                                            <span>
                                                {valuePrefix}
                                                {value}
                                                {valueSuffix}
                                            </span>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                        <small>{category}</small>
                    </div>
                ))}
            </div>
        </div>
    );
}

export function LineChart({
    categories,
    series,
    height = 260,
    valuePrefix = "",
    valueSuffix = "",
    showValues = false,
    style,
}: any) {
    const width = 720;
    const pad = 30;
    const values = series.flatMap((item: any) => item.data);
    const minimum = Math.min(0, ...values);
    const maximum = Math.max(1, ...values);
    const x = (index: number) =>
        pad + (index * (width - pad * 2)) / Math.max(1, categories.length - 1);
    const y = (value: number) =>
        height -
        pad -
        ((value - minimum) / Math.max(1, maximum - minimum)) *
            (height - pad * 2);
    return (
        <div className="cv-chart" style={style}>
            <div className="cv-chart-legend">
                {series.map((item: any, index: number) => (
                    <span key={item.name}>
                        <i style={{ background: chartColour(item, index) }} />
                        {item.name}
                    </span>
                ))}
            </div>
            <svg
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label="Line chart"
            >
                {series.map((item: any, seriesIndex: number) => {
                    const points = item.data
                        .map(
                            (value: number, index: number) =>
                                `${x(index)},${y(value)}`,
                        )
                        .join(" ");
                    return (
                        <g key={item.name}>
                            <polyline
                                points={points}
                                fill="none"
                                stroke={chartColour(item, seriesIndex)}
                                strokeWidth="2"
                            />
                            {item.data.map((value: number, index: number) => (
                                <g key={index}>
                                    <circle
                                        cx={x(index)}
                                        cy={y(value)}
                                        r="3"
                                        fill={chartColour(item, seriesIndex)}
                                    />
                                    <title>
                                        {item.name}: {valuePrefix}
                                        {value}
                                        {valueSuffix}
                                    </title>
                                    {showValues && (
                                        <text
                                            x={x(index)}
                                            y={y(value) - 7}
                                            textAnchor="middle"
                                        >
                                            {valuePrefix}
                                            {value}
                                            {valueSuffix}
                                        </text>
                                    )}
                                </g>
                            ))}
                        </g>
                    );
                })}
                {categories.map((category: string, index: number) => (
                    <text
                        key={category}
                        x={x(index)}
                        y={height - 7}
                        textAnchor="middle"
                    >
                        {category}
                    </text>
                ))}
            </svg>
        </div>
    );
}

export function PieChart({ data, size = 200, donut = false, style }: any) {
    const total = Math.max(
        1,
        data.reduce(
            (sum: number, item: any) => sum + Math.max(0, item.value),
            0,
        ),
    );
    const radius = 42;
    const circumference = 2 * Math.PI * radius;
    let offset = 0;
    return (
        <div className="cv-pie" style={style}>
            <svg
                width={size}
                height={size}
                viewBox="0 0 100 100"
                role="img"
                aria-label="Pie chart"
            >
                <g transform="rotate(-90 50 50)">
                    {data.map((item: any, index: number) => {
                        const length =
                            (Math.max(0, item.value) / total) * circumference;
                        const dashOffset = -offset;
                        offset += length;
                        return (
                            <circle
                                key={item.label}
                                cx="50"
                                cy="50"
                                r={radius}
                                fill="none"
                                stroke={chartColour(item, index)}
                                strokeWidth={donut ? 16 : 84}
                                strokeDasharray={`${length} ${circumference - length}`}
                                strokeDashoffset={dashOffset}
                            >
                                <title>
                                    {item.label}: {item.value}
                                </title>
                            </circle>
                        );
                    })}
                </g>
                {donut && (
                    <text
                        x="50"
                        y="54"
                        textAnchor="middle"
                        className="cv-pie-total"
                    >
                        {total}
                    </text>
                )}
            </svg>
            <div className="cv-chart-legend">
                {data.map((item: any, index: number) => (
                    <span key={item.label}>
                        <i style={{ background: chartColour(item, index) }} />
                        {item.label}: {item.value}
                    </span>
                ))}
            </div>
        </div>
    );
}

export function computeDAGLayout(nodes: any[], edges: any[]) {
    const positioned = nodes.map((node, index) => ({
        ...node,
        x: (index % 4) * 220,
        y: Math.floor(index / 4) * 140,
        rank: Math.floor(index / 4),
    }));
    return {
        nodes: positioned,
        edges,
        width: Math.min(4, nodes.length) * 220,
        height: Math.ceil(nodes.length / 4) * 140,
    };
}
