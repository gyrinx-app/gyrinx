import {
    createContext,
    createElement,
    useContext,
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

export function ButtonLink({
    variant = "default",
    className = "",
    ...props
}: ComponentProps<"a"> & {
    href: string;
    variant?: keyof typeof cotton.buttonLink;
}) {
    return (
        <a
            {...props}
            className={`${cotton.buttonLink[variant]} ${className}`}
        />
    );
}

export function FormActions({
    children,
    className = "",
}: {
    children: ReactNode;
    className?: string;
}) {
    return (
        <div className={`${cotton.formActions} ${className}`}>{children}</div>
    );
}

const FieldContext = createContext<{
    id: string;
    errorId?: string;
    descriptionId?: string;
} | null>(null);

function useFieldControl(id?: string, describedBy?: string) {
    const field = useContext(FieldContext);
    const controlId = id ?? field?.id;
    const owned = field !== null && field.id === controlId ? field : undefined;
    return {
        id: controlId,
        errorId: owned?.errorId,
        describedBy:
            [describedBy, owned?.descriptionId, owned?.errorId]
                .filter(Boolean)
                .join(" ") || undefined,
    };
}

export function Field({
    label,
    htmlFor,
    errors = [],
    description,
    variant = "block",
    children,
}: {
    label: string;
    htmlFor: string;
    errors?: string[];
    description?: string;
    variant?: "block" | "toggle";
    children: ReactNode;
}) {
    const id = useId();
    const errorId = errors.length ? `${id}-errors` : undefined;
    const descriptionId = description ? `${id}-description` : undefined;
    const recipe = cotton.field;
    const labelControl = (
        <label htmlFor={htmlFor} className={recipe.label}>
            <span className={recipe.labelText}>{label}</span>
        </label>
    );
    const descriptionControl = descriptionId && (
        <div id={descriptionId} className={recipe.description}>
            {description}
        </div>
    );
    const errorControl = errorId && (
        <div id={errorId}>
            {errors.map((error, index) => (
                <div key={index} className={recipe.error}>
                    {error}
                </div>
            ))}
        </div>
    );

    return (
        <FieldContext value={{ id: htmlFor, errorId, descriptionId }}>
            <div className={recipe.root}>
                {variant === "toggle" ? (
                    <div className={recipe.toggleRow}>
                        <div className={recipe.toggleText}>{labelControl}</div>
                        <div className={recipe.toggleControl}>{children}</div>
                    </div>
                ) : (
                    <>
                        {labelControl}
                        {children}
                    </>
                )}
                {descriptionControl}
                {errorControl}
            </div>
        </FieldContext>
    );
}

export function Input({
    id,
    className = "",
    "aria-describedby": describedBy,
    "aria-invalid": invalid,
    ...props
}: ComponentProps<"input">) {
    const field = useFieldControl(id, describedBy);
    return (
        <div className={cotton.input.root}>
            <input
                {...props}
                id={field.id}
                className={`${cotton.input.control} ${className}`}
                aria-invalid={invalid ?? (field.errorId ? true : undefined)}
                aria-describedby={field.describedBy}
            />
        </div>
    );
}

export function NativeSelect({
    id,
    className = "",
    style,
    "aria-describedby": describedBy,
    "aria-invalid": invalid,
    ...props
}: ComponentProps<"select">) {
    const field = useFieldControl(id, describedBy);
    return (
        <select
            {...props}
            id={field.id}
            className={`${cotton.nativeSelect.className} ${className}`}
            style={{ ...cotton.nativeSelect.style, ...style }}
            aria-invalid={invalid ?? (field.errorId ? true : undefined)}
            aria-describedby={field.describedBy}
        />
    );
}

export function Switch({
    id,
    name,
    checked,
    onCheckedChange,
    label,
}: {
    id?: string;
    name: string;
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    label: string;
}) {
    const field = useFieldControl(id);
    const recipe = cotton.switch;
    return (
        <div className={recipe.root}>
            <input
                type="checkbox"
                name={name}
                value="on"
                checked={checked}
                readOnly
                tabIndex={-1}
                aria-hidden="true"
                className={recipe.control}
            />
            <button
                id={field.id}
                type="button"
                role="switch"
                aria-checked={checked}
                aria-label={label}
                aria-describedby={field.describedBy}
                onClick={() => onCheckedChange(!checked)}
                className={`${recipe.track} ${recipe.trackTransition} ${
                    checked ? recipe.trackChecked : recipe.trackUnchecked
                }`}
            >
                <span
                    className={`${recipe.thumb} ${recipe.thumbTransition} ${
                        checked ? recipe.thumbChecked : recipe.thumbUnchecked
                    }`}
                />
            </button>
        </div>
    );
}

export function CheckboxCard({
    checked,
    onCheckedChange,
    label,
    description,
    meta,
    children,
    disabled = false,
    className = "",
    checkboxLabel,
    checkboxDescribedBy,
    notice,
    errors,
}: {
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    label: string;
    description?: string;
    meta?: ReactNode;
    children?: ReactNode;
    disabled?: boolean;
    className?: string;
    checkboxLabel?: string;
    checkboxDescribedBy?: string;
    notice?: ReactNode;
    errors?: ReactNode;
}) {
    const id = useId();
    const recipe = cotton.checkboxCard;
    const nestedInactive = !checked || disabled;
    return (
        <div
            className={`${recipe.root} ${recipe.selection[checked ? "checked" : "unchecked"]} ${className}`}
        >
            <label htmlFor={id} className={recipe.header}>
                <input
                    id={id}
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={(event) => onCheckedChange(event.target.checked)}
                    className={recipe.checkbox}
                    aria-label={checkboxLabel}
                    aria-labelledby={checkboxLabel ? undefined : `${id}-label`}
                    aria-describedby={
                        [
                            description ? `${id}-description` : undefined,
                            checkboxDescribedBy,
                        ]
                            .filter(Boolean)
                            .join(" ") || undefined
                    }
                />
                <span className={recipe.text}>
                    <span id={`${id}-label`} className={recipe.label}>
                        {label}
                    </span>
                    {description && (
                        <span
                            id={`${id}-description`}
                            className={recipe.description}
                        >
                            {description}
                        </span>
                    )}
                </span>
                {meta}
            </label>
            {notice}
            {children != null &&
                typeof children !== "boolean" &&
                children !== "" && (
                    // Inert preserves field values and form submission; callers
                    // disable inputs separately when they should not be submitted.
                    <div
                        inert={nestedInactive}
                        className={`${recipe.body} ${recipe.nested[nestedInactive ? "unchecked" : "checked"]}`}
                    >
                        {children}
                    </div>
                )}
            {errors}
        </div>
    );
}

export function Callout({
    children,
    className = "",
    id,
}: {
    children: ReactNode;
    className?: string;
    id?: string;
}) {
    return (
        <div
            id={id}
            role="note"
            className={`${cotton.callout.root} ${className}`}
        >
            <div className={cotton.callout.content}>
                <div className={cotton.callout.body}>{children}</div>
            </div>
        </div>
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
