import {
    Children,
    type CSSProperties,
    type ReactNode,
    isValidElement,
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

export type { CSSProperties, RefObject } from "react";
export { useEffect, useMemo, useRef, useState } from "react";

type Tone = "success" | "danger" | "warning" | "info" | "neutral";
export type Color =
    | "gray"
    | "blue"
    | "green"
    | "yellow"
    | "orange"
    | "red"
    | "purple"
    | "pink"
    | "cyan";

const categoryColours: Readonly<Record<Color, string>> = {
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

export const usageColorSequence: readonly Color[] = [
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
export type CategoryPalette = Readonly<Record<Color, string>>;

export interface CanvasPalette {
    readonly foreground: string;
    readonly foregroundSecondary: string;
    readonly foregroundTertiary: string;
    readonly foregroundQuaternary: string;
    readonly editor: string;
    readonly chrome: string;
    readonly sidebar: string;
    readonly elevated: string;
    readonly fillPrimary: string;
    readonly fillSecondary: string;
    readonly fillTertiary: string;
    readonly fillQuaternary: string;
    readonly strokePrimary: string;
    readonly strokeSecondary: string;
    readonly strokeTertiary: string;
    readonly strokeFocused: string;
    readonly accent: string;
    readonly buttonBackground: string;
    readonly buttonForeground: string;
    readonly buttonHoverBackground: string;
    readonly link: string;
    readonly diffInsertedLine: string;
    readonly diffRemovedLine: string;
    readonly diffStripAdded: string;
    readonly diffStripRemoved: string;
}

export interface CanvasTokens {
    readonly bg: { editor: string; chrome: string; elevated: string };
    readonly text: {
        primary: string;
        secondary: string;
        tertiary: string;
        quaternary: string;
        link: string;
        onAccent: string;
    };
    readonly stroke: {
        primary: string;
        secondary: string;
        tertiary: string;
        focused: string;
    };
    readonly fill: {
        primary: string;
        secondary: string;
        tertiary: string;
        quaternary: string;
    };
    readonly accent: {
        primary: string;
        control: string;
        controlHover: string;
    };
    readonly diff: {
        insertedLine: string;
        removedLine: string;
        stripAdded: string;
        stripRemoved: string;
    };
    readonly category: CategoryPalette;
}

export interface CanvasHostTheme extends CanvasTokens {
    readonly kind: "light" | "dark";
    readonly tokens: CanvasTokens;
    readonly palette: CanvasPalette;
}

export const canvasPaletteLight: CanvasPalette = {
    foreground: "#17191d",
    foregroundSecondary: "#555c66",
    foregroundTertiary: "#737b87",
    foregroundQuaternary: "#969da7",
    editor: "#ffffff",
    chrome: "#f6f7f9",
    sidebar: "#f6f7f9",
    elevated: "#ffffff",
    fillPrimary: "#eef1f5",
    fillSecondary: "#f3f5f7",
    fillTertiary: "#f7f8fa",
    fillQuaternary: "#fafbfc",
    strokePrimary: "#c4c9d1",
    strokeSecondary: "#d7dbe1",
    strokeTertiary: "#e5e7eb",
    strokeFocused: "#0771ea",
    accent: "#0771ea",
    buttonBackground: "#0771ea",
    buttonForeground: "#ffffff",
    buttonHoverBackground: "#075fca",
    link: "#075fca",
    diffInsertedLine: "#e8f5ed",
    diffRemovedLine: "#fbeaec",
    diffStripAdded: "#1a7b49",
    diffStripRemoved: "#b4233e",
};

export const canvasPaletteDark: CanvasPalette = {
    foreground: "#f2f3f5",
    foregroundSecondary: "#c1c6ce",
    foregroundTertiary: "#9fa6b1",
    foregroundQuaternary: "#7f8792",
    editor: "#17191d",
    chrome: "#202329",
    sidebar: "#202329",
    elevated: "#22262c",
    fillPrimary: "#2a2e35",
    fillSecondary: "#25292f",
    fillTertiary: "#20242a",
    fillQuaternary: "#1c1f24",
    strokePrimary: "#4d535d",
    strokeSecondary: "#3d424b",
    strokeTertiary: "#30353c",
    strokeFocused: "#3f8efc",
    accent: "#3f8efc",
    buttonBackground: "#3f8efc",
    buttonForeground: "#ffffff",
    buttonHoverBackground: "#3479d8",
    link: "#75aff8",
    diffInsertedLine: "#193628",
    diffRemovedLine: "#40242a",
    diffStripAdded: "#63c18f",
    diffStripRemoved: "#f07188",
};

export const categoryPaletteLight: CategoryPalette = {
    gray: "#737b87",
    purple: "#8056c8",
    green: "#2e8b57",
    yellow: "#b07a00",
    cyan: "#168ca0",
    pink: "#bf4f8d",
    blue: "#397bd6",
    orange: "#c76524",
    red: "#c43d55",
};

export const categoryPaletteDark: CategoryPalette = {
    gray: "#9fa6b1",
    purple: "#aa98d8",
    green: "#63c18f",
    yellow: "#e6b449",
    cyan: "#5bc5d5",
    pink: "#e8a0c4",
    blue: "#75aff8",
    orange: "#f0a040",
    red: "#f07188",
};

export const colorPalette = categoryPaletteDark;

export const chartPalette = {
    green: "#1F8A65E8",
    darkGreen: "#0D855AE0",
    lightGreen: "#52B896E0",
    mintGreen: "#7DCAB0E0",
    blue: "#2E79B5E0",
    lightBlue: "#70B0D8E0",
    indigo: "#5A6CC0F0",
    lightIndigo: "#9AAADCE0",
    purple: "#7B64B8F0",
    lightPurple: "#AA98D8E0",
    warmPink: "#C85898E0",
    lightPink: "#E8A0C4E0",
    brightOrange: "#F0A040E0",
    deepOrange: "#C06028E0",
    goldenYellow: "#E8C030E0",
    darkAmber: "#C04848E0",
    warmPeach: "#F0A088E0",
    vibrantTeal: "#2A9A8AE0",
    muted: "#8888A8E0",
    neutralLine: "#888899D0",
} as const;

export const chartColorSequence: readonly string[] = [
    chartPalette.green,
    chartPalette.blue,
    chartPalette.purple,
    chartPalette.brightOrange,
    chartPalette.warmPink,
    chartPalette.vibrantTeal,
    chartPalette.indigo,
    chartPalette.goldenYellow,
];

function tokensFromPalette(
    palette: CanvasPalette,
    category: CategoryPalette,
): CanvasTokens {
    return {
        bg: {
            editor: palette.editor,
            chrome: palette.chrome,
            elevated: palette.elevated,
        },
        text: {
            primary: palette.foreground,
            secondary: palette.foregroundSecondary,
            tertiary: palette.foregroundTertiary,
            quaternary: palette.foregroundQuaternary,
            link: palette.link,
            onAccent: palette.buttonForeground,
        },
        stroke: {
            primary: palette.strokePrimary,
            secondary: palette.strokeSecondary,
            tertiary: palette.strokeTertiary,
            focused: palette.strokeFocused,
        },
        fill: {
            primary: palette.fillPrimary,
            secondary: palette.fillSecondary,
            tertiary: palette.fillTertiary,
            quaternary: palette.fillQuaternary,
        },
        accent: {
            primary: palette.accent,
            control: palette.buttonBackground,
            controlHover: palette.buttonHoverBackground,
        },
        diff: {
            insertedLine: palette.diffInsertedLine,
            removedLine: palette.diffRemovedLine,
            stripAdded: palette.diffStripAdded,
            stripRemoved: palette.diffStripRemoved,
        },
        category,
    };
}

export const canvasTokensLight = tokensFromPalette(
    canvasPaletteLight,
    categoryPaletteLight,
);
export const canvasTokens = tokensFromPalette(
    canvasPaletteDark,
    categoryPaletteDark,
);

function hostTheme(kind: "light" | "dark"): CanvasHostTheme {
    const tokens = kind === "dark" ? canvasTokens : canvasTokensLight;
    const palette = kind === "dark" ? canvasPaletteDark : canvasPaletteLight;
    return { ...tokens, kind, tokens, palette };
}

export function useHostTheme(): CanvasHostTheme {
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
    return useMemo(() => hostTheme(dark ? "dark" : "light"), [dark]);
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
            {collapsible &&
            isValidElement<{
                children?: ReactNode;
                trailing?: ReactNode;
                style?: CSSProperties;
            }>(header) ? (
                <div
                    className="cv-card-header cv-card-collapsible-header"
                    style={header.props.style}
                >
                    <button
                        className="cv-card-toggle"
                        type="button"
                        onClick={toggle}
                    >
                        <span aria-hidden="true">{open ? "⌄" : "›"}</span>
                        <span>{header.props.children}</span>
                    </button>
                    {header.props.trailing && (
                        <span className="cv-card-trailing">
                            {header.props.trailing}
                        </span>
                    )}
                </div>
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
    label,
    "aria-label": ariaLabel,
    style,
}: any) {
    return (
        <button
            type="button"
            role="switch"
            aria-checked={checked ?? false}
            aria-label={ariaLabel ?? label ?? "Toggle"}
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
            aria-label={title ?? "Icon button"}
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
    return chartColorSequence[index % chartColorSequence.length];
}

type ChartReferenceLine = { value: number; label?: string; tone?: Tone };
type ChartSeries = { name: string; data: number[]; tone?: Tone };

function chartDomain(
    values: number[],
    {
        beginAtZero = true,
        yMin,
        yMax,
        referenceLines = [],
    }: {
        beginAtZero?: boolean;
        yMin?: number;
        yMax?: number;
        referenceLines?: ChartReferenceLine[];
    },
) {
    const finite = [
        ...values,
        ...referenceLines.map((line) => line.value),
    ].filter(Number.isFinite);
    const dataMinimum = finite.length > 0 ? Math.min(...finite) : 0;
    const dataMaximum = finite.length > 0 ? Math.max(...finite) : 1;
    const minimum =
        yMin ?? (beginAtZero ? Math.min(0, dataMinimum) : dataMinimum);
    const maximum =
        yMax ?? (beginAtZero ? Math.max(0, dataMaximum) : dataMaximum);
    return maximum === minimum
        ? { minimum, maximum: minimum + 1 }
        : { minimum, maximum };
}

function formattedValue(value: number, prefix: string, suffix: string) {
    return `${prefix}${Number.isInteger(value) ? value : value.toFixed(1)}${suffix}`;
}

export function BarChart({
    categories,
    series,
    height = 260,
    stacked = false,
    horizontal = false,
    normalized = false,
    valuePrefix = "",
    valueSuffix = "",
    showValues,
    beginAtZero = true,
    yMin,
    yMax,
    referenceLines = [],
    style,
}: {
    categories: string[];
    series: ChartSeries[];
    height?: number;
    stacked?: boolean;
    horizontal?: boolean;
    normalized?: boolean;
    valuePrefix?: string;
    valueSuffix?: string;
    showValues?: boolean;
    beginAtZero?: boolean;
    yMin?: number;
    yMax?: number;
    referenceLines?: ChartReferenceLine[];
    style?: CSSProperties;
}) {
    const width = 720;
    const padding = { top: 18, right: 24, bottom: 38, left: 52 };
    const plotWidth = width - padding.left - padding.right;
    const plotHeight = height - padding.top - padding.bottom;
    const stack = stacked || normalized;
    const plotted = categories.map((_, categoryIndex) => {
        const values = series.map((item) => item.data[categoryIndex] ?? 0);
        if (!normalized) return values;
        const total = values.reduce(
            (sum, value) => sum + Math.max(0, value),
            0,
        );
        return values.map((value) =>
            total > 0 ? (Math.max(0, value) / total) * 100 : 0,
        );
    });
    const domainValues = stack
        ? plotted.map((values) => values.reduce((sum, value) => sum + value, 0))
        : plotted.flat();
    const domain = normalized
        ? { minimum: 0, maximum: 100 }
        : chartDomain(
              domainValues,
              stack
                  ? { beginAtZero: true, referenceLines }
                  : { beginAtZero, yMin, yMax, referenceLines },
          );
    const domainSpan = domain.maximum - domain.minimum || 1;
    const scale = (value: number, span: number) =>
        ((value - domain.minimum) / domainSpan) * span;
    const suffix = normalized ? "%" : valueSuffix;
    const prefix = normalized ? "" : valuePrefix;
    const valuesVisible =
        !stack &&
        (showValues ?? (series.length === 1 && categories.length <= 8));

    return (
        <div className="cv-chart" style={style}>
            <div className="cv-chart-legend">
                {series.length > 1 &&
                    series.map((item, index) => (
                        <span key={item.name}>
                            <i
                                style={{ background: chartColour(item, index) }}
                            />
                            {item.name}
                        </span>
                    ))}
            </div>
            <svg
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label="Bar chart"
                data-chart-mode={
                    normalized ? "normalized" : stack ? "stacked" : "grouped"
                }
            >
                {referenceLines.map((line) => {
                    const position = scale(
                        line.value,
                        horizontal ? plotWidth : plotHeight,
                    );
                    return (
                        <g key={`${line.value}-${line.label ?? ""}`}>
                            <line
                                x1={
                                    horizontal
                                        ? padding.left + position
                                        : padding.left
                                }
                                x2={
                                    horizontal
                                        ? padding.left + position
                                        : width - padding.right
                                }
                                y1={
                                    horizontal
                                        ? padding.top
                                        : padding.top + plotHeight - position
                                }
                                y2={
                                    horizontal
                                        ? padding.top + plotHeight
                                        : padding.top + plotHeight - position
                                }
                                className="cv-chart-reference"
                                data-reference-value={line.value}
                                style={{ stroke: chartColour(line, 0) }}
                            />
                            {line.label && (
                                <text
                                    x={
                                        horizontal
                                            ? padding.left + position + 4
                                            : width - padding.right
                                    }
                                    y={
                                        horizontal
                                            ? padding.top + 10
                                            : padding.top +
                                              plotHeight -
                                              position -
                                              4
                                    }
                                    textAnchor={horizontal ? "start" : "end"}
                                >
                                    {line.label}
                                </text>
                            )}
                        </g>
                    );
                })}
                {categories.map((category, categoryIndex) => {
                    const categorySpan =
                        (horizontal ? plotHeight : plotWidth) /
                        Math.max(1, categories.length);
                    let cumulative = 0;
                    return (
                        <g key={category}>
                            {series.map((item, seriesIndex) => {
                                const value =
                                    plotted[categoryIndex]?.[seriesIndex] ?? 0;
                                const colour = chartColour(item, seriesIndex);
                                const baseline =
                                    domain.minimum <= 0 && domain.maximum >= 0
                                        ? 0
                                        : domain.minimum > 0
                                          ? domain.minimum
                                          : domain.maximum;
                                const start = stack ? cumulative : baseline;
                                if (stack) cumulative += value;
                                const end = stack ? cumulative : value;
                                if (horizontal) {
                                    const barHeight = stack
                                        ? Math.min(30, categorySpan * 0.62)
                                        : Math.min(
                                              24,
                                              (categorySpan * 0.7) /
                                                  Math.max(1, series.length),
                                          );
                                    const y = stack
                                        ? padding.top +
                                          categoryIndex * categorySpan +
                                          (categorySpan - barHeight) / 2
                                        : padding.top +
                                          categoryIndex * categorySpan +
                                          categorySpan * 0.15 +
                                          seriesIndex * barHeight;
                                    const startPosition = scale(
                                        start,
                                        plotWidth,
                                    );
                                    const endPosition = scale(end, plotWidth);
                                    const x =
                                        padding.left +
                                        Math.min(startPosition, endPosition);
                                    const barWidth = Math.abs(
                                        endPosition - startPosition,
                                    );
                                    return (
                                        <g key={item.name}>
                                            <rect
                                                x={x}
                                                y={y}
                                                width={barWidth}
                                                height={barHeight}
                                                rx="2"
                                                fill={colour}
                                                data-value={value}
                                                data-start={start}
                                                data-end={end}
                                            >
                                                <title>
                                                    {item.name}:{" "}
                                                    {formattedValue(
                                                        value,
                                                        prefix,
                                                        suffix,
                                                    )}
                                                </title>
                                            </rect>
                                            {valuesVisible && (
                                                <text
                                                    x={x + barWidth + 4}
                                                    y={y + barHeight / 2 + 4}
                                                >
                                                    {formattedValue(
                                                        value,
                                                        prefix,
                                                        suffix,
                                                    )}
                                                </text>
                                            )}
                                        </g>
                                    );
                                }
                                const barWidth = stack
                                    ? Math.min(42, categorySpan * 0.62)
                                    : Math.min(
                                          32,
                                          (categorySpan * 0.7) /
                                              Math.max(1, series.length),
                                      );
                                const x = stack
                                    ? padding.left +
                                      categoryIndex * categorySpan +
                                      (categorySpan - barWidth) / 2
                                    : padding.left +
                                      categoryIndex * categorySpan +
                                      categorySpan * 0.15 +
                                      seriesIndex * barWidth;
                                const startPosition = scale(start, plotHeight);
                                const endPosition = scale(end, plotHeight);
                                const y =
                                    padding.top +
                                    plotHeight -
                                    Math.max(startPosition, endPosition);
                                const barHeight = Math.abs(
                                    endPosition - startPosition,
                                );
                                return (
                                    <g key={item.name}>
                                        <rect
                                            x={x}
                                            y={y}
                                            width={barWidth}
                                            height={barHeight}
                                            rx="2"
                                            fill={colour}
                                            data-value={value}
                                            data-start={start}
                                            data-end={end}
                                        >
                                            <title>
                                                {item.name}:{" "}
                                                {formattedValue(
                                                    value,
                                                    prefix,
                                                    suffix,
                                                )}
                                            </title>
                                        </rect>
                                        {valuesVisible && (
                                            <text
                                                x={x + barWidth / 2}
                                                y={y - 5}
                                                textAnchor="middle"
                                            >
                                                {formattedValue(
                                                    value,
                                                    prefix,
                                                    suffix,
                                                )}
                                            </text>
                                        )}
                                    </g>
                                );
                            })}
                            <text
                                x={
                                    horizontal
                                        ? padding.left - 8
                                        : padding.left +
                                          categoryIndex * categorySpan +
                                          categorySpan / 2
                                }
                                y={
                                    horizontal
                                        ? padding.top +
                                          categoryIndex * categorySpan +
                                          categorySpan / 2 +
                                          4
                                        : height - 10
                                }
                                textAnchor={horizontal ? "end" : "middle"}
                            >
                                {category}
                            </text>
                        </g>
                    );
                })}
            </svg>
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
    fill = false,
    showHoverGuide = true,
    beginAtZero = true,
    yMin,
    yMax,
    referenceLines = [],
    style,
}: {
    categories: string[];
    series: ChartSeries[];
    height?: number;
    fill?: boolean;
    valueSuffix?: string;
    valuePrefix?: string;
    showValues?: boolean;
    showHoverGuide?: boolean;
    beginAtZero?: boolean;
    yMin?: number;
    yMax?: number;
    referenceLines?: ChartReferenceLine[];
    style?: CSSProperties;
}) {
    const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
    const width = 720;
    const pad = 30;
    const values = series.flatMap((item: any) => item.data);
    const { minimum, maximum } = chartDomain(values, {
        beginAtZero,
        yMin,
        yMax,
        referenceLines,
    });
    const x = (index: number) =>
        pad + (index * (width - pad * 2)) / Math.max(1, categories.length - 1);
    const domainSpan = maximum - minimum || 1;
    const y = (value: number) =>
        height - pad - ((value - minimum) / domainSpan) * (height - pad * 2);
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
                onMouseLeave={() => setHoveredIndex(null)}
            >
                {referenceLines.map((line) => {
                    const lineY = y(line.value);
                    return (
                        <g key={`${line.value}-${line.label ?? ""}`}>
                            <line
                                x1={pad}
                                x2={width - pad}
                                y1={lineY}
                                y2={lineY}
                                className="cv-chart-reference"
                                data-reference-value={line.value}
                                style={{ stroke: chartColour(line, 0) }}
                            />
                            {line.label && (
                                <text
                                    x={width - pad}
                                    y={lineY - 4}
                                    textAnchor="end"
                                >
                                    {line.label}
                                </text>
                            )}
                        </g>
                    );
                })}
                {series.map((item: any, seriesIndex: number) => {
                    const points = item.data
                        .map(
                            (value: number, index: number) =>
                                `${x(index)},${y(value)}`,
                        )
                        .join(" ");
                    return (
                        <g key={item.name}>
                            {fill && (
                                <polygon
                                    points={`${x(0)},${y(minimum)} ${points} ${x(Math.max(0, item.data.length - 1))},${y(minimum)}`}
                                    fill={chartColour(item, seriesIndex)}
                                    opacity="0.12"
                                />
                            )}
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
                    <g key={category}>
                        <rect
                            x={
                                x(index) -
                                (width - pad * 2) /
                                    Math.max(1, categories.length) /
                                    2
                            }
                            y={pad}
                            width={
                                (width - pad * 2) /
                                Math.max(1, categories.length)
                            }
                            height={height - pad * 2}
                            fill="transparent"
                            onMouseEnter={() => setHoveredIndex(index)}
                        />
                        <text x={x(index)} y={height - 7} textAnchor="middle">
                            {category}
                        </text>
                    </g>
                ))}
                {showHoverGuide && hoveredIndex !== null && (
                    <line
                        x1={x(hoveredIndex)}
                        x2={x(hoveredIndex)}
                        y1={pad}
                        y2={height - pad}
                        className="cv-chart-hover-guide"
                    />
                )}
            </svg>
        </div>
    );
}

export function PieChart({ data, size = 200, donut = false, style }: any) {
    const total = Math.max(
        0,
        data.reduce(
            (sum: number, item: any) => sum + Math.max(0, item.value),
            0,
        ),
    );
    const denominator = Math.max(1, total);
    const radius = donut ? 42 : 25;
    const strokeWidth = donut ? 16 : 50;
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
                            (Math.max(0, item.value) / denominator) *
                            circumference;
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
                                strokeWidth={strokeWidth}
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

export type DAGLayoutOptions = {
    nodes: Array<{ id: string }>;
    edges: Array<{ from: string; to: string }>;
    direction?: "vertical" | "horizontal";
    nodeWidth?: number;
    nodeHeight?: number;
    rankGap?: number;
    nodeGap?: number;
    padding?: number;
};

export type DAGLayoutNode = {
    id: string;
    x: number;
    y: number;
    rank: number;
    order: number;
};

export type DAGLayoutEdge = {
    from: string;
    to: string;
    sourceX: number;
    sourceY: number;
    targetX: number;
    targetY: number;
    isBackEdge: boolean;
};

export type DAGLayoutRank = {
    rank: number;
    x: number;
    y: number;
    width: number;
    height: number;
    nodeIds: string[];
};

export type DAGLayoutResult = {
    nodes: DAGLayoutNode[];
    edges: DAGLayoutEdge[];
    ranks: DAGLayoutRank[];
    direction: "vertical" | "horizontal";
    width: number;
    height: number;
};

export function computeDAGLayout(options: DAGLayoutOptions): DAGLayoutResult {
    const {
        direction = "vertical",
        nodeWidth = 160,
        nodeHeight = 40,
        rankGap = 64,
        nodeGap = 48,
        padding = 24,
    } = options;
    const nodeIds = [...new Set(options.nodes.map((node) => node.id))];
    if (nodeIds.length === 0) {
        return {
            nodes: [],
            edges: [],
            ranks: [],
            direction,
            width: padding * 2,
            height: padding * 2,
        };
    }
    const nodeSet = new Set(nodeIds);
    const edges = options.edges.filter(
        (edge) => nodeSet.has(edge.from) && nodeSet.has(edge.to),
    );
    const outgoing = new Map<string, Array<{ to: string; index: number }>>(
        nodeIds.map((id) => [id, []]),
    );
    edges.forEach((edge, index) => {
        outgoing.get(edge.from)?.push({ to: edge.to, index });
    });

    const visiting = new Set<string>();
    const visited = new Set<string>();
    const backEdges = new Set<number>();
    const visit = (id: string) => {
        if (visited.has(id)) return;
        visiting.add(id);
        for (const edge of outgoing.get(id) ?? []) {
            if (visiting.has(edge.to)) {
                backEdges.add(edge.index);
            } else {
                visit(edge.to);
            }
        }
        visiting.delete(id);
        visited.add(id);
    };
    nodeIds.forEach(visit);

    const indegree = new Map(nodeIds.map((id) => [id, 0]));
    const ranks = new Map(nodeIds.map((id) => [id, 0]));
    edges.forEach((edge, index) => {
        if (!backEdges.has(index)) {
            indegree.set(edge.to, (indegree.get(edge.to) ?? 0) + 1);
        }
    });
    const queue = nodeIds.filter((id) => indegree.get(id) === 0);
    const ranked = new Set<string>();
    while (queue.length > 0) {
        const id = queue.shift();
        if (!id) continue;
        ranked.add(id);
        for (const edge of outgoing.get(id) ?? []) {
            if (backEdges.has(edge.index)) continue;
            ranks.set(
                edge.to,
                Math.max(ranks.get(edge.to) ?? 0, (ranks.get(id) ?? 0) + 1),
            );
            const remaining = (indegree.get(edge.to) ?? 1) - 1;
            indegree.set(edge.to, remaining);
            if (remaining === 0) queue.push(edge.to);
        }
    }
    for (const id of nodeIds) {
        if (!ranked.has(id)) ranks.set(id, 0);
    }

    const idsByRank = new Map<number, string[]>();
    for (const id of nodeIds) {
        const rank = ranks.get(id) ?? 0;
        idsByRank.set(rank, [...(idsByRank.get(rank) ?? []), id]);
    }
    const rankNumbers = [...idsByRank.keys()].sort(
        (left, right) => left - right,
    );
    const largestRank = Math.max(0, ...rankNumbers);
    const rankSpan = (ids: string[]) =>
        ids.length * (direction === "vertical" ? nodeWidth : nodeHeight) +
        Math.max(0, ids.length - 1) * nodeGap;
    const maximumSpan = Math.max(
        0,
        ...rankNumbers.map((rank) => rankSpan(idsByRank.get(rank) ?? [])),
    );
    const width =
        direction === "vertical"
            ? padding * 2 + maximumSpan
            : padding * 2 +
              (largestRank + 1) * nodeWidth +
              largestRank * rankGap;
    const height =
        direction === "vertical"
            ? padding * 2 +
              (largestRank + 1) * nodeHeight +
              largestRank * rankGap
            : padding * 2 + maximumSpan;

    const positioned: DAGLayoutNode[] = [];
    const layoutRanks: DAGLayoutRank[] = [];
    for (const rank of rankNumbers) {
        const ids = idsByRank.get(rank) ?? [];
        const span = rankSpan(ids);
        const offset = padding + (maximumSpan - span) / 2;
        const rankNodes = ids.map((id, order) => {
            if (direction === "vertical") {
                return {
                    id,
                    x: offset + order * (nodeWidth + nodeGap),
                    y: padding + rank * (nodeHeight + rankGap),
                    rank,
                    order,
                };
            }
            return {
                id,
                x: padding + rank * (nodeWidth + rankGap),
                y: offset + order * (nodeHeight + nodeGap),
                rank,
                order,
            };
        });
        positioned.push(...rankNodes);
        layoutRanks.push({
            rank,
            x:
                direction === "vertical"
                    ? offset
                    : padding + rank * (nodeWidth + rankGap),
            y:
                direction === "vertical"
                    ? padding + rank * (nodeHeight + rankGap)
                    : offset,
            width: direction === "vertical" ? span : nodeWidth,
            height: direction === "vertical" ? nodeHeight : span,
            nodeIds: ids,
        });
    }

    const positionedById = new Map(positioned.map((node) => [node.id, node]));
    const layoutEdges = edges.map((edge, index) => {
        const source = positionedById.get(edge.from)!;
        const target = positionedById.get(edge.to)!;
        return {
            ...edge,
            sourceX:
                source.x +
                (direction === "vertical" ? nodeWidth / 2 : nodeWidth),
            sourceY:
                source.y +
                (direction === "vertical" ? nodeHeight : nodeHeight / 2),
            targetX: target.x + (direction === "vertical" ? nodeWidth / 2 : 0),
            targetY: target.y + (direction === "vertical" ? 0 : nodeHeight / 2),
            isBackEdge: backEdges.has(index),
        };
    });

    return {
        nodes: positioned,
        edges: layoutEdges,
        ranks: layoutRanks,
        direction,
        width,
        height,
    };
}
