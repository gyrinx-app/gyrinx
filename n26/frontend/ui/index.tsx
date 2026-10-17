import {
    type CSSProperties,
    createContext,
    createElement,
    useContext,
    useEffect,
    useId,
    useLayoutEffect,
    useRef,
    useState,
    type ComponentProps,
    type ReactNode,
} from "react";
import cotton from "../generated/cotton.json";

/** A native modal, styled from Cotton; React owns its lifetime and dismissal. */
export function Dialog({
    title,
    lead,
    children,
    onDismiss,
    onSubmit,
    pending = false,
    returnFocusId,
}: {
    title: string;
    lead?: string;
    children: ReactNode;
    onDismiss: () => void;
    onSubmit: ComponentProps<"form">["onSubmit"];
    pending?: boolean;
    returnFocusId?: string;
}) {
    const ref = useRef<HTMLDialogElement>(null);
    const previous = useRef(document.activeElement);
    const titleId = useId();
    useEffect(() => {
        const dialog = ref.current!;
        dialog.showModal();
        return () => {
            dialog.close();
            const target =
                (returnFocusId
                    ? document.getElementById(returnFocusId)
                    : null) ?? previous.current;
            if (target instanceof HTMLElement && target.isConnected)
                target.focus();
        };
    }, [returnFocusId]);
    return (
        <dialog
            ref={ref}
            aria-labelledby={titleId}
            className={cotton.dialog.root}
            onCancel={(event) => {
                event.preventDefault();
                if (!pending) onDismiss();
            }}
        >
            <form
                onSubmit={onSubmit}
                className={cotton.dialog.form}
                aria-busy={pending}
            >
                <div className={cotton.dialog.header}>
                    <h2 id={titleId} className={cotton.dialog.title}>
                        {title}
                    </h2>
                    {lead && <p className={cotton.dialog.lead}>{lead}</p>}
                </div>
                {children}
            </form>
        </dialog>
    );
}

export function Button({
    variant = "default",
    size = "default",
    className = "",
    type = "button",
    ...props
}: ComponentProps<"button"> & {
    variant?: keyof typeof cotton.button;
    size?: "default" | "sm";
}) {
    const recipe = size === "sm" ? cotton.buttonSmall : cotton.button;
    return (
        <button
            {...props}
            type={type}
            className={`${recipe[variant]} ${className}`}
        />
    );
}

export type ButtonLinkSize = keyof typeof cotton.buttonLinkBySize;
export type ButtonLinkVariant = keyof typeof cotton.buttonLinkBySize.md;

export function ButtonLink({
    variant = "default",
    size = "md",
    className = "",
    ...props
}: ComponentProps<"a"> & {
    href: string;
    variant?: ButtonLinkVariant;
    size?: ButtonLinkSize;
}) {
    return (
        <a
            {...props}
            className={`${cotton.buttonLinkBySize[size][variant]} ${className}`}
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

export interface RatingReceiptProps {
    defaultRating: number;
    overrideDelta: number;
    contributions: Array<{ label: string; rating: number }>;
    total: number;
}

export function RatingReceipt({
    defaultRating,
    overrideDelta,
    contributions,
    total,
}: RatingReceiptProps) {
    const recipe = cotton.ratingReceipt;
    const lines = [
        { label: "Default base rating", display: `${defaultRating}¢` },
        ...(overrideDelta
            ? [
                  {
                      label: "Base rating override",
                      display: `${overrideDelta > 0 ? "+" : ""}${overrideDelta}¢`,
                  },
              ]
            : []),
        ...contributions.map(({ label, rating }) => ({
            label,
            display: `${rating > 0 ? "+" : ""}${rating}¢`,
        })),
    ];
    return (
        <dl className={recipe[0]}>
            {lines.map(({ label, display }) => (
                <div key={label} className={recipe[1]}>
                    <dt className={recipe[2]}>{label}</dt>
                    <dd className={recipe[3]}>{display}</dd>
                </div>
            ))}
            <div className={recipe[4]}>
                <dt className={recipe[5]}>Total rating</dt>
                <dd className={recipe[6]}>{total}¢</dd>
            </div>
        </dl>
    );
}

export function RatingBaseline({ rating }: { rating: number }) {
    return (
        <div className={cotton.ratingBaseline[0]}>
            <span className={cotton.ratingBaseline[1]}>
                Without an override
            </span>
            <span className={cotton.ratingBaseline[2]}>{rating}¢</span>
        </div>
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

/** Errors in the danger colour, as `<c-ui.error>` draws them. */
export function FieldErrors({ id, errors }: { id?: string; errors: string[] }) {
    return (
        <div id={id}>
            {errors.map((error, index) => (
                <div key={index} className={cotton.field.error}>
                    {error}
                </div>
            ))}
        </div>
    );
}

/**
 * A labelled control. In the block variant, `descriptionPlacement="before"`
 * matches a Cotton field's `description` slot; the default matches
 * `description_trailing`. The toggle variant always draws it after.
 */
export function Field({
    label,
    htmlFor,
    errors = [],
    description,
    descriptionPlacement = "after",
    variant = "block",
    children,
}: {
    label: string;
    htmlFor: string;
    errors?: string[];
    description?: ReactNode;
    descriptionPlacement?: "before" | "after";
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
        <FieldErrors id={errorId} errors={errors} />
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
                        {descriptionPlacement === "before" &&
                            descriptionControl}
                        {children}
                    </>
                )}
                {(variant === "toggle" || descriptionPlacement === "after") &&
                    descriptionControl}
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
    controlSize = "default",
    ...props
}: ComponentProps<"select"> & { controlSize?: "default" | "sm" }) {
    const field = useFieldControl(id, describedBy);
    const recipe =
        controlSize === "sm" ? cotton.nativeSelectSmall : cotton.nativeSelect;
    return (
        <select
            {...props}
            id={field.id}
            className={`${recipe.className} ${className}`}
            style={{ ...recipe.style, ...style }}
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
    value = "on",
    disabled = false,
    accent = true,
    size = "md",
    className = "",
    embedded = false,
}: {
    id?: string;
    name: string;
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    label: string;
    value?: string;
    disabled?: boolean;
    accent?: boolean;
    size?: keyof typeof cotton.switch.sizes;
    className?: string;
    /** Posts through a real checkbox and keeps the cotton switch's two events. */
    embedded?: boolean;
}) {
    const field = useFieldControl(embedded ? undefined : id);
    const inputRef = useRef<HTMLInputElement>(null);
    const recipe = cotton.switch;
    const sizeRecipe = recipe.sizes[size] ?? recipe.sizes.md;
    const [ready, setReady] = useState(false);
    const [named, setNamed] = useState(label);
    const [labelledBy, setLabelledBy] = useState<string | undefined>();
    useEffect(() => {
        const frame = requestAnimationFrame(() => setReady(true));
        return () => cancelAnimationFrame(frame);
    }, []);
    useLayoutEffect(() => {
        if (!embedded) return;
        const associated = inputRef.current?.labels?.[0];
        const text = accessibleLabelText(associated);
        if (text) setNamed(text);
        setLabelledBy(associated?.id || undefined);
    }, [embedded]);

    function accessibleLabelText(element: HTMLElement | null | undefined) {
        if (!element) return "";
        // The island's props script sits inside a wrapping label. textContent
        // would announce that JSON as the switch's name.
        const copy = element.cloneNode(true) as HTMLElement;
        copy.querySelectorAll("script, style").forEach((node) => node.remove());
        return (copy.textContent ?? "").replace(/\s+/g, " ").trim();
    }

    function press() {
        if (disabled) return;
        const next = !checked;
        const input = inputRef.current;
        if (embedded && input) {
            // checkedChange reaches a parent before the box shows the new
            // value. change then reports that value. A label click only
            // fires change, via the handler below.
            input.dispatchEvent(
                new CustomEvent("checkedChange", { bubbles: true }),
            );
            input.checked = next;
            input.dispatchEvent(new Event("change", { bubbles: true }));
        }
        onCheckedChange(next);
    }

    const trackState = !checked
        ? recipe.trackUnchecked
        : accent
          ? recipe.trackChecked
          : recipe.trackCheckedMuted;
    return (
        <div className={recipe.root}>
            <input
                ref={inputRef}
                id={embedded ? id : undefined}
                type="checkbox"
                name={name}
                value={value}
                checked={checked}
                disabled={disabled}
                readOnly={embedded ? undefined : true}
                tabIndex={-1}
                aria-hidden={embedded ? undefined : true}
                className={recipe.control}
                onChange={(event) => {
                    if (!embedded || disabled) return;
                    onCheckedChange(event.currentTarget.checked);
                }}
            />
            <button
                id={embedded ? undefined : field.id}
                type="button"
                role="switch"
                aria-checked={checked}
                aria-label={named || undefined}
                aria-labelledby={embedded ? labelledBy : undefined}
                aria-describedby={embedded ? undefined : field.describedBy}
                disabled={disabled}
                onClick={press}
                className={[
                    recipe.track,
                    sizeRecipe.track,
                    disabled ? recipe.disabled : recipe.enabled,
                    ready ? recipe.trackTransition : "",
                    trackState,
                    className,
                ]
                    .filter(Boolean)
                    .join(" ")}
            >
                <span
                    className={[
                        recipe.thumb,
                        sizeRecipe.thumb,
                        ready ? recipe.thumbTransition : "",
                        checked ? sizeRecipe.on : sizeRecipe.off,
                    ]
                        .filter(Boolean)
                        .join(" ")}
                />
            </button>
        </div>
    );
}

/** A switch with words beside it that toggle it too, as `<c-n26.toggle>`. */
export function Toggle({
    label,
    checked,
    onCheckedChange,
    name = "",
}: {
    label: string;
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    name?: string;
}) {
    return (
        <label className={cotton.toggle}>
            <Switch
                embedded
                name={name}
                label=""
                size="sm"
                checked={checked}
                onCheckedChange={onCheckedChange}
            />
            <span>{label}</span>
        </label>
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
    name,
    value,
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
    /** Posts the checkbox with its form, as the Cotton card's input does. */
    name?: string;
    value?: string;
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
                    name={name}
                    value={value}
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

/** One nested tick inside a CheckboxCard body, as the Cotton card draws it. */
export function CheckboxCardItem({
    name,
    value,
    label,
    defaultChecked = false,
    checked,
    disabled = false,
    onCheckedChange,
    describedBy,
    meta,
}: {
    name: string;
    value: string;
    label: string;
    defaultChecked?: boolean;
    checked?: boolean;
    disabled?: boolean;
    onCheckedChange?: (checked: boolean) => void;
    describedBy?: string;
    meta?: string;
}) {
    const recipe = cotton.checkboxCard;
    return (
        <label className={recipe.item}>
            <input
                type="checkbox"
                name={name}
                value={value}
                defaultChecked={
                    checked === undefined ? defaultChecked : undefined
                }
                checked={checked}
                disabled={disabled}
                onChange={
                    onCheckedChange
                        ? (event) => onCheckedChange(event.target.checked)
                        : undefined
                }
                aria-describedby={describedBy}
                className={recipe.itemInput}
            />
            <span className={recipe.itemLabel}>{label}</span>
            {meta && <span className={recipe.itemMeta}>{meta}</span>}
        </label>
    );
}

/** A figure beside a CheckboxCard's label, as text. */
export function CheckboxCardMeta({ children }: { children: ReactNode }) {
    return <span className={cotton.checkboxCard.meta}>{children}</span>;
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

export function RadioOption({
    name,
    value,
    label,
    description = "",
    checked,
    disabled = false,
    onChange,
}: {
    name: string;
    value: string;
    label: string;
    description?: string;
    checked: boolean;
    disabled?: boolean;
    onChange: () => void;
}) {
    const id = useId();
    const recipe = cotton.radioOption;
    return (
        <label className={recipe.root}>
            <input
                type="radio"
                name={name}
                value={value}
                checked={checked}
                disabled={disabled}
                onChange={onChange}
                className={recipe.control}
                aria-labelledby={`${id}-label`}
                aria-describedby={description ? `${id}-description` : undefined}
            />
            <span className={recipe.content}>
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
        </label>
    );
}

export function RadioCards({
    legend,
    min = "14rem",
    errors = [],
    children,
}: {
    legend: string;
    min?: string;
    errors?: string[];
    children: ReactNode;
}) {
    const id = useId();
    const errorId = errors.length ? `${id}-errors` : undefined;
    const recipe = cotton.radioCards.group;
    const style = {
        "--radio-card-min": min,
        gridTemplateColumns: recipe.gridTemplateColumns,
    } as CSSProperties;
    return (
        <fieldset
            className={recipe.root}
            aria-invalid={errorId ? true : undefined}
            aria-describedby={errorId}
        >
            <legend className={recipe.legend}>{legend}</legend>
            <div className={recipe.grid} style={style}>
                {children}
            </div>
            {errorId && <FieldErrors id={errorId} errors={errors} />}
        </fieldset>
    );
}

export function RadioCard({
    name,
    value,
    label,
    description = "",
    example = "",
    reason = "",
    disabled = false,
    checked,
    onChange,
    autoFocus,
    flair,
    className = "",
    children,
}: {
    name: string;
    value: string;
    label: string;
    description?: string;
    example?: string;
    reason?: string;
    disabled?: boolean;
    checked: boolean;
    onChange: () => void;
    autoFocus?: boolean;
    flair?: ReactNode;
    className?: string;
    children?: ReactNode;
}) {
    const recipe = cotton.radioCards.card;
    const control = (
        <>
            <input
                type="radio"
                name={name}
                value={value}
                disabled={disabled}
                checked={checked}
                onChange={onChange}
                autoFocus={autoFocus}
                className={recipe.input}
            />
            <span className={recipe.content}>
                <span className={recipe.label}>
                    <span className={recipe.flairText}>
                        {label}
                        {flair && <span className={recipe.flair}>{flair}</span>}
                    </span>
                </span>
                {disabled && reason ? (
                    <span className={recipe.reason}>{reason}</span>
                ) : (
                    description && (
                        <span className={recipe.description}>
                            {description}
                        </span>
                    )
                )}
                {example && !disabled && (
                    <span
                        className={recipe.example}
                        tabIndex={0}
                        title={example}
                    >
                        <Icon name="info" className={recipe.exampleIcon} />
                        <span className={recipe.exampleText}>{example}</span>
                    </span>
                )}
            </span>
        </>
    );
    const rootClass = `${disabled ? recipe.disabled : recipe.enabled} ${className}`;
    // A field inside a choice needs its own label, outside the radio's label.
    if (children) {
        return (
            <div className={`${rootClass} flex-col`}>
                <label className="flex w-full cursor-pointer items-start gap-3">
                    {control}
                </label>
                <div className="w-full">{children}</div>
            </div>
        );
    }
    return <label className={rootClass}>{control}</label>;
}

export function Card({ children }: { children: ReactNode }) {
    return <div className={cotton.card}>{children}</div>;
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
    tone = "accent",
    ...props
}: ComponentProps<"a"> & {
    /** accent is `<c-n26.link>`'s default; current takes the text colour. */
    tone?: "accent" | "current";
}) {
    const recipe = tone === "current" ? cotton.linkCurrent : cotton.link;
    return (
        <a {...props} className={`${recipe[0]} ${className}`}>
            <span className={recipe[1]}>{children}</span>
        </a>
    );
}

export function Badge({
    children,
    className = "",
    color = "amber",
}: {
    children: ReactNode;
    className?: string;
    color?: "amber" | "ink";
}) {
    const recipe = color === "ink" ? cotton.badgeInk : cotton.badge;
    return <span className={`${recipe} ${className}`}>{children}</span>;
}

export function StagedBadge() {
    return <Badge className="ml-1">Staged</Badge>;
}

export function ActionBar({
    children,
    trailing,
    className = "",
    surface = true,
    spaced = true,
    ...props
}: ComponentProps<"div"> & {
    trailing?: ReactNode;
    /** The tinted band behind the controls; false for a bare row. */
    surface?: boolean;
    /** False when the parent already spaces its children. */
    spaced?: boolean;
}) {
    const bar = surface ? cotton.actionBar[0] : cotton.actionBarPlain;
    return (
        <div
            {...props}
            className={`${bar} ${spaced ? "mb-3" : ""} ${className}`}
        >
            {children}
            {trailing && <div className={cotton.actionBar[1]}>{trailing}</div>}
        </div>
    );
}

export function Icon({
    name,
    className = "size-4",
    strokeWidth,
}: {
    name: keyof typeof cotton.icons;
    className?: string;
    strokeWidth?: number;
}) {
    return (
        <svg
            className={className}
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={strokeWidth ?? (name === "search" ? 1.5 : 2)}
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

/** An SVG element from `n26/badges.py`: allowlisted tags and attributes. */
export type SvgNode = {
    tag: string;
    props: Record<string, string>;
    children?: (SvgNode | string)[];
};

/** A badge beside a name: its accessible name and its artwork. */
export type BadgeMark = { label: string; svg: SvgNode };

// The platform's SVG allowlist, checked again here so data never becomes markup.
const SVG_TAGS = new Set(cotton.svgTags);
const SVG_PROPS = new Set(cotton.svgProps);

function svgProps(props: Record<string, string>) {
    return Object.fromEntries(
        Object.entries(props).filter(
            ([name, value]) =>
                SVG_PROPS.has(name) &&
                (name !== "href" || value.trim().startsWith("#")) &&
                (!value.toLowerCase().includes("url(") ||
                    value.trim().toLowerCase().startsWith("url(#")),
        ),
    );
}

function SvgArt({ node }: { node: SvgNode }): ReactNode {
    if (!SVG_TAGS.has(node.tag)) return null;
    const props: Record<string, string> = svgProps(node.props);
    // The wrapper names the badge, so the drawing itself stays silent.
    if (node.tag === "svg") {
        props["aria-hidden"] = "true";
        props.focusable = "false";
    }
    return createElement(
        node.tag,
        props,
        ...(node.children ?? []).map((child, key) =>
            typeof child === "string" ? (
                child
            ) : (
                <SvgArt key={key} node={child} />
            ),
        ),
    );
}

export function Artwork({ node }: { node: SvgNode }) {
    return (
        <span className={cotton.userLink.flair} aria-hidden="true">
            <SvgArt node={node} />
        </span>
    );
}

export function ColorSwatch({ color }: { color: string }) {
    return color ? (
        <span
            className={cotton.colorSwatch}
            style={{ background: color }}
            aria-hidden="true"
        />
    ) : null;
}

/**
 * A person's name in the surrounding colour, with their badge after it, as
 * `<c-n26.user-link tone="current">` draws it. Without an href the name is
 * plain text, as on a button that already does something else.
 */
export function UserLink({
    name,
    href,
    badge,
}: {
    name: string;
    href?: string;
    badge?: BadgeMark | null;
}) {
    const recipe = cotton.userLink;
    const mark = badge && (
        <span
            className={recipe.flair}
            role="img"
            aria-label={badge.label}
            title={badge.label}
        >
            <SvgArt node={badge.svg} />
        </span>
    );
    if (!href)
        return (
            <span className={recipe.plain}>
                {name}
                {mark}
            </span>
        );
    return (
        <a href={href} className={recipe.link}>
            <span className={recipe.text}>{name}</span>
            {mark}
        </a>
    );
}

/** The class of the site bar's account button, as `<c-n26.site.nav>` draws it. */
export const siteNavAccountButton = cotton.siteNavTrigger.button;

/** The inside of the site bar's account button: the name, the icons and the unread pill. */
export function SiteNavAccount({
    name,
    unread,
}: {
    name: ReactNode;
    unread: number;
}) {
    const recipe = cotton.siteNavTrigger;
    return (
        <>
            <span className={recipe.name}>{name}</span>
            <span className={recipe.icons}>
                <Icon
                    name="ellipsis-vertical"
                    className="size-4"
                    strokeWidth={1.7}
                />
                <Icon
                    name="chevron-down"
                    className="size-3"
                    strokeWidth={2.5}
                />
            </span>
            <CountBadge count={unread} className={recipe.badge} />
        </>
    );
}

/**
 * A red count pill, as `<c-n26.count-badge>` draws it: nothing at zero, the
 * face capped at `max`, and the real count spoken with `label`.
 */
export function CountBadge({
    count,
    max = 99,
    label,
    className = "",
}: {
    count: number;
    max?: number;
    label?: string;
    className?: string;
}) {
    if (!count) return null;
    return (
        <span className={`${cotton.countBadge.root} ${className}`}>
            <span aria-hidden="true">{count > max ? `${max}+` : count}</span>
            {label && (
                <span className={cotton.countBadge.spoken}>
                    {count} {label}
                </span>
            )}
        </span>
    );
}

/** The design gallery's mark for a component that renders through React. */
export function ReactMark() {
    const mark = cotton.reactMark;
    return (
        <svg
            viewBox={mark.viewBox}
            className={mark.className}
            role="img"
            aria-label={mark.label}
        >
            <circle {...mark.dot} />
            <g {...mark.group}>
                {mark.orbits.map((orbit, key) => (
                    <ellipse key={key} {...orbit} />
                ))}
            </g>
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

export type PickOption = {
    key: string;
    name: string;
    detail: string;
    grantedBy: string;
    fixedBecause: string;
    picked: boolean;
};

/**
 * One tickable option. A grant or a priced hold is drawn fixed and disabled,
 * so it posts nothing an owner could take back.
 */
export function PickBox({
    option,
    name,
    checked,
    onChange,
}: {
    option: PickOption;
    name: string;
    checked: boolean;
    onChange: (checked: boolean) => void;
}) {
    const recipe = cotton.pickList;
    const fixed = !!(option.grantedBy || option.fixedBecause);
    const remark = option.grantedBy
        ? `From ${option.grantedBy}`
        : option.fixedBecause || option.detail;
    return (
        <label
            className={fixed ? recipe.boxFixed : recipe.box}
            title={
                option.grantedBy
                    ? `From ${option.grantedBy}`
                    : option.fixedBecause || undefined
            }
        >
            <input
                type="checkbox"
                name={name}
                value={option.key}
                checked={checked}
                disabled={fixed}
                onChange={(event) => onChange(event.target.checked)}
                className={recipe.checkbox}
            />
            <span className={recipe.text}>
                <span className={recipe.name}>{option.name}</span>
                {remark && <span className={recipe.remark}>{remark}</span>}
            </span>
        </label>
    );
}

export function PickLegend({
    name,
    caption,
}: {
    name: string;
    caption: string;
}) {
    return (
        <legend className={cotton.pickList.legend}>
            {name}
            {caption && (
                <>
                    {" "}
                    <span className={cotton.pickList.caption}>{caption}</span>
                </>
            )}
        </legend>
    );
}

/** The c-n26.tick-list layout: named groups of plain ticked rows. */
export function TickList({ children }: { children: ReactNode }) {
    return <div className={cotton.tickList.root}>{children}</div>;
}

export function TickListGroup({
    name,
    children,
}: {
    name: string;
    children: ReactNode;
}) {
    return (
        <fieldset>
            <legend className={cotton.tickList.legend}>{name}</legend>
            <div className={cotton.tickList.options}>{children}</div>
        </fieldset>
    );
}

export function TickListOption({
    name,
    value,
    label,
    checked,
    disabled = false,
    onChange,
}: {
    name: string;
    value: string;
    label: string;
    checked: boolean;
    disabled?: boolean;
    onChange: (checked: boolean) => void;
}) {
    const recipe = cotton.tickList;
    return (
        <label className={disabled ? recipe.labelDisabled : recipe.label}>
            <input
                type="checkbox"
                name={name}
                value={value}
                checked={checked}
                disabled={disabled}
                className={recipe.input}
                onChange={(event) => onChange(event.target.checked)}
            />
            <span className={recipe.text}>
                <span className={recipe.name}>{label}</span>
            </span>
        </label>
    );
}

export {
    ActionMenu,
    type ActionMenuItem,
    type ActionMenuProps,
} from "./ActionMenu";
export { FilterMenu, type FilterOption } from "./FilterMenu";
export { RangeMenu } from "./RangeMenu";
export {
    MenuButton,
    MenuGroup,
    MenuLink,
    MenuSeparator,
    MenuSubmit,
} from "./Menu";
export { ThemeChoice, type ThemeChoiceProps } from "./ThemeChoice";
export {
    QuickSwitcher,
    type QuickSwitcherProps,
    type SwitcherRow,
} from "./QuickSwitcher";
export { HelpPopover } from "./HelpPopover";
export { IncomeTooltip, type IncomeTooltipProps } from "./IncomeTooltip";
export {
    useAnchoredPlacement,
    useDismiss,
    type AnchoredPlacementOptions,
} from "./anchoredPanel";

export {
    SortableTable,
    compareTableValues,
    type TableView,
    type TableColumn,
    type TableGroup,
} from "./SortableTable";

export {
    campaignViewHref,
    openCampaignDialog,
    runCampaignDialog,
    guardDialogSubmission,
    useCampaignDialogRequests,
} from "./campaignNavigation";
