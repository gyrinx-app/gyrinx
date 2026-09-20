import {
    createElement,
    useId,
    useRef,
    type ComponentProps,
    type ReactNode,
} from "react";
import cotton from "../generated/cotton.json";

export function Button({
    variant = "default",
    className = "",
    type = "button",
    ...props
}: ComponentProps<"button"> & { variant?: keyof typeof cotton.button }) {
    return (
        <button
            {...props}
            type={type}
            className={`${cotton.button[variant]} ${className}`}
        />
    );
}

export function Table({
    children,
    className = "",
}: {
    children: ReactNode;
    className?: string;
}) {
    return (
        <div className={cotton.table[0]}>
            <table className={`${cotton.table[1]} ${className}`}>
                {children}
            </table>
        </div>
    );
}

export function Link({
    children,
    className = "",
    ...props
}: ComponentProps<"a">) {
    return (
        <a {...props} className={`${cotton.link[0]} ${className}`}>
            <span className={cotton.link[1]}>{children}</span>
        </a>
    );
}

export function StagedBadge() {
    return <span className={`ml-1 ${cotton.stagedBadge}`}>Staged</span>;
}

export function ActionBar({
    children,
    trailing,
}: {
    children: ReactNode;
    trailing: ReactNode;
}) {
    return (
        <div className={`${cotton.actionBar[0]} mb-3`}>
            {children}
            <div className={cotton.actionBar[1]}>{trailing}</div>
        </div>
    );
}

function Icon({ name }: { name: keyof typeof cotton.icons }) {
    return (
        <svg
            className="size-4"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={name === "search" ? 1.5 : 2}
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

export function SearchBar({
    value,
    onChange,
    label,
}: {
    value: string;
    onChange: (value: string) => void;
    label: string;
}) {
    const id = useId();
    const input = useRef<HTMLInputElement>(null);
    return (
        <div role="search" className={cotton.search.root}>
            <div className={cotton.search.group}>
                <span className={cotton.search.icon} aria-hidden="true">
                    <Icon name="search" />
                </span>
                <label htmlFor={id} className={cotton.search.label}>
                    {label}
                </label>
                <input
                    ref={input}
                    id={id}
                    type="search"
                    value={value}
                    placeholder={label}
                    autoComplete="off"
                    className={cotton.search.input}
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === "Enter") event.preventDefault();
                    }}
                />
                {value && (
                    <button
                        type="button"
                        className={cotton.search.clear}
                        aria-label="Clear search"
                        onClick={() => {
                            onChange("");
                            input.current?.focus();
                        }}
                    >
                        <Icon name="x" />
                    </button>
                )}
            </div>
        </div>
    );
}

export { FilterMenu, type FilterOption } from "./FilterMenu";
