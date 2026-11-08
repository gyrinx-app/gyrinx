import { memo, useCallback, useId, useState, type ReactNode } from "react";
import cotton from "../generated/cotton.json";
import { ButtonLink, Icon } from "./index";
import { CatalogueFrame } from "./CatalogueFrame";

export type HireOption = {
    key: string;
    name: string;
    price: number;
    totalPrice: number;
    default: boolean;
};
export type HireGroup = {
    choose: "one" | "any" | "one-or-none";
    offersChoice: boolean;
    options: HireOption[];
};
export type HireEntry = {
    key: string;
    name: string;
    profileType: string;
    basePrice: number;
    previewHref: string;
    confirmationHref: string;
    groups: HireGroup[];
};
export type HireSection = {
    name: string;
    categories: Array<{ name: string; entries: HireEntry[] }>;
};
export type CatalogueData = {
    scope: string;
    scopeLabel: string;
    scopeTabs: Array<{ key: string; label: string; href: string }>;
    section: string;
    listingHref: string;
    priceFloor: number;
    priceCeiling: number;
    categories: string[];
    categoryOptions: string[];
    sections: HireSection[];
};

export type PreviewRenderer = (
    href: string,
    selection: string[],
    onLoading: (loading: boolean) => void,
) => ReactNode;

const recipe = cotton.hireCatalogue;
const instructions = {
    one: "Choose one",
    any: "Choose any",
    "one-or-none": "Choose one, or none",
};
const defaults = (entry: HireEntry) =>
    entry.groups.flatMap((group) =>
        group.options
            .filter((option) => option.default && option.key)
            .map((option) => option.key),
    );

const Row = memo(function Row({
    entry,
    selected,
    expanded,
    renderPreview,
    onSelect,
    onExpand,
}: {
    entry: HireEntry;
    selected: string[];
    expanded: boolean;
    renderPreview: PreviewRenderer;
    onSelect: (key: string, selected: string[]) => void;
    onExpand: (key: string) => void;
}) {
    const id = useId();
    const [previewLoading, setPreviewLoading] = useState(false);
    const [previewReady, setPreviewReady] = useState(false);
    const previewState = useCallback((loading: boolean) => {
        setPreviewLoading(loading);
        if (!loading) setPreviewReady(true);
    }, []);
    const cardShown = expanded && (!previewLoading || previewReady);
    const selection = new Set(selected);
    const price = entry.groups
        .flatMap((group) => group.options)
        .reduce(
            (total, option) =>
                total +
                (selection.has(option.key)
                    ? option.totalPrice - entry.basePrice
                    : 0),
            entry.basePrice,
        );
    const href = `${entry.confirmationHref}${entry.confirmationHref.includes("?") ? "&" : "?"}selection=${encodeURIComponent(JSON.stringify(selected))}`;
    function choose(groupIndex: number, key: string, checked: boolean) {
        const group = entry.groups[groupIndex];
        const members = new Set(group.options.map((option) => option.key));
        const next = selected.filter((candidate) =>
            group.choose === "any"
                ? candidate !== key
                : !members.has(candidate),
        );
        if (key && checked) next.push(key);
        onSelect(entry.key, next);
    }
    return (
        <div className={recipe.row}>
            <div className={recipe.rowHeader}>
                <span className={recipe.nameBlock}>
                    <span className={recipe.rail} aria-hidden="true" />
                    <span className={`${recipe.name} break-words`}>
                        {entry.name}
                    </span>
                    <button
                        type="button"
                        className={recipe.disclosure}
                        data-busy={previewLoading ? "on" : undefined}
                        aria-busy={previewLoading || undefined}
                        aria-expanded={cardShown}
                        aria-controls={expanded ? id : undefined}
                        aria-label={`${cardShown ? "Hide" : "Show"} card for ${entry.name}`}
                        onClick={() => {
                            setPreviewLoading(false);
                            if (!expanded) setPreviewReady(false);
                            onExpand(entry.key);
                        }}
                    >
                        <span>{cardShown ? "Hide card" : "Show card"}</span>
                        <Icon
                            name="chevron-right"
                            className={`size-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
                            strokeWidth={2.5}
                        />
                    </button>
                </span>
                <div className={recipe.price}>{price}¢</div>
                <ButtonLink
                    href={href}
                    size="sm"
                    variant="primary"
                    data-busy="off"
                    aria-label={`Hire ${entry.name}`}
                >
                    Hire
                </ButtonLink>
            </div>
            <div className={recipe.inset}>
                {entry.groups.map((group, index) =>
                    group.offersChoice ? (
                        <div
                            key={index}
                            role="group"
                            aria-label={`${instructions[group.choose]} for ${entry.name}`}
                        >
                            {index > 0 && (
                                <div className={recipe.groupHeader}>
                                    <span className={recipe.groupName}>
                                        {instructions[group.choose]}
                                    </span>
                                </div>
                            )}
                            {group.options.map((option) => (
                                <label
                                    key={option.key}
                                    className={recipe.optionLabel}
                                >
                                    <input
                                        type={
                                            group.choose === "any"
                                                ? "checkbox"
                                                : "radio"
                                        }
                                        name={`${id}-${index}`}
                                        value={option.key}
                                        checked={selection.has(option.key)}
                                        className={recipe.optionInput}
                                        onChange={(event) =>
                                            choose(
                                                index,
                                                option.key,
                                                event.target.checked,
                                            )
                                        }
                                    />
                                    <span
                                        className={`${recipe.optionName} break-words`}
                                    >
                                        {option.name}
                                    </span>
                                    {option.price !== 0 && (
                                        <span className={recipe.optionPrice}>
                                            +{option.price}¢
                                        </span>
                                    )}
                                </label>
                            ))}
                            {group.choose === "one-or-none" && (
                                <label className={recipe.optionLabel}>
                                    <input
                                        type="radio"
                                        name={`${id}-${index}`}
                                        value=""
                                        className={recipe.optionInput}
                                        checked={
                                            !group.options.some((option) =>
                                                selection.has(option.key),
                                            )
                                        }
                                        onChange={() => choose(index, "", true)}
                                    />
                                    <span className={recipe.optionName}>
                                        None
                                    </span>
                                </label>
                            )}
                        </div>
                    ) : null,
                )}
            </div>
            {expanded && (
                <div
                    id={id}
                    hidden={previewLoading && !previewReady}
                    className={recipe.details}
                >
                    {renderPreview(entry.previewHref, selected, previewState)}
                </div>
            )}
        </div>
    );
});

export function HireCatalogue(
    props: CatalogueData & { renderPreview: PreviewRenderer },
) {
    const [selected, setSelected] = useState<Record<string, string[]>>({});
    const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
    const select = useCallback(
        (key: string, values: string[]) =>
            setSelected((previous) => ({ ...previous, [key]: values })),
        [],
    );
    const expand = useCallback(
        (key: string) =>
            setExpanded((previous) => {
                const next = new Set(previous);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
            }),
        [],
    );
    return (
        <CatalogueFrame
            {...props}
            sections={props.sections.map((section) => ({
                ...section,
                categories: section.categories.map((category) => ({
                    ...category,
                    entries: category.entries.map((entry) => ({
                        ...entry,
                        keywords: entry.profileType,
                    })),
                })),
            }))}
            noun="profile"
            plural="profiles"
            sectionLabel="Profile sections"
            empty="No profiles are available in this list. Choose another list."
            navigation={
                <nav
                    aria-label="Who can be hired"
                    data-speculate="who-can-be-hired"
                    className="mb-4 flex flex-wrap"
                >
                    {props.scopeTabs.map((tab) => (
                        <a
                            key={tab.key}
                            href={tab.href}
                            aria-current={
                                props.scope === tab.key ? "page" : undefined
                            }
                            data-busy="off"
                            className={
                                props.scope === tab.key
                                    ? recipe.scopeActive
                                    : recipe.scopeInactive
                            }
                        >
                            {tab.label}
                        </a>
                    ))}
                    <span className={recipe.tabEnd} aria-hidden="true" />
                </nav>
            }
            renderEntry={(entry) => (
                <Row
                    entry={entry}
                    selected={selected[entry.key] ?? defaults(entry)}
                    expanded={expanded.has(entry.key)}
                    renderPreview={props.renderPreview}
                    onSelect={select}
                    onExpand={expand}
                />
            )}
        />
    );
}
