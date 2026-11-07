import {
    memo,
    useCallback,
    useEffect,
    useId,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent,
    type ReactNode,
} from "react";
import cotton from "../generated/cotton.json";
import {
    ButtonLink,
    FilterMenu,
    Icon,
    QuickSwitcher,
    RangeMenu,
    SearchBar,
} from "./index";

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

export type PreviewRenderer = (href: string, selection: string[]) => ReactNode;

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
                        aria-expanded={expanded}
                        aria-controls={expanded ? id : undefined}
                        aria-label={`${expanded ? "Hide" : "Show"} card for ${entry.name}`}
                        onClick={() => onExpand(entry.key)}
                    >
                        <span>{expanded ? "Hide card" : "Show card"}</span>
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
                    variant="success"
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
                <div id={id} className={recipe.details}>
                    {renderPreview(entry.previewHref, selected)}
                </div>
            )}
        </div>
    );
});

export function HireCatalogue(
    props: CatalogueData & { renderPreview: PreviewRenderer },
) {
    const id = useId();
    const [query, setQuery] = useState("");
    const [categories, setCategories] = useState(props.categories);
    const [range, setRange] = useState<[number, number]>([
        props.priceFloor,
        props.priceCeiling,
    ]);
    const [chosen, setChosen] = useState(props.section);
    const [reset, setReset] = useState(0);
    const [openCategories, setOpenCategories] = useState<
        Record<string, boolean>
    >({});
    const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
    const [selected, setSelected] = useState<Record<string, string[]>>(() =>
        Object.fromEntries(
            props.sections.flatMap((section) =>
                section.categories.flatMap((category) =>
                    category.entries.map((entry) => [
                        entry.key,
                        defaults(entry),
                    ]),
                ),
            ),
        ),
    );
    const tabRefs = useRef(new Map<string, HTMLButtonElement>());
    const tabFocus = useRef<string | null>(null);
    const allSections = useMemo(
        () =>
            props.sections
                .map((section, sectionIndex) => ({
                    ...section,
                    sectionIndex,
                    total: section.categories.reduce(
                        (sum, category) => sum + category.entries.length,
                        0,
                    ),
                    categories: section.categories.map(
                        (category, categoryIndex) => ({
                            ...category,
                            categoryIndex,
                            matches: category.entries.filter(
                                (entry) =>
                                    (!query ||
                                        [
                                            entry.name,
                                            entry.profileType,
                                            category.name,
                                            section.name,
                                        ]
                                            .filter(Boolean)
                                            .join(" ")
                                            .toLowerCase()
                                            .includes(
                                                query.trim().toLowerCase(),
                                            )) &&
                                    entry.basePrice >= range[0] &&
                                    entry.basePrice <= range[1],
                            ),
                            selected: categories.includes(
                                category.name || section.name,
                            ),
                        }),
                    ),
                }))
                .map((section) => ({
                    ...section,
                    count: section.categories.reduce(
                        (sum, category) =>
                            sum +
                            (category.selected ? category.matches.length : 0),
                        0,
                    ),
                })),
        [props.sections, query, categories, range],
    );
    const live = allSections.filter((section) => section.count > 0);
    const active = live.find((section) => section.name === chosen) ?? live[0];
    const filtering =
        !!query ||
        categories.length !== props.categories.length ||
        range[0] > props.priceFloor ||
        range[1] < props.priceCeiling;
    const categoryOptions = useMemo(
        () =>
            props.categoryOptions.map((name) => ({ value: name, label: name })),
        [props.categoryOptions],
    );
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
    function clear() {
        setQuery("");
        setCategories(props.categories);
        setRange([props.priceFloor, props.priceCeiling]);
        setReset((value) => value + 1);
    }
    function toggleAll(open: boolean) {
        setOpenCategories(
            Object.fromEntries(
                props.sections.flatMap((section, sectionIndex) =>
                    section.categories.map((_, categoryIndex) => [
                        `${sectionIndex}:${categoryIndex}`,
                        open,
                    ]),
                ),
            ),
        );
    }
    function chooseSection(name: string) {
        setChosen(name);
        const url = new URL(window.location.href);
        url.searchParams.set("section", name);
        window.history.replaceState(window.history.state, "", url);
    }
    useEffect(() => {
        const restore = () =>
            setChosen(
                new URLSearchParams(window.location.search).get("section") ||
                    props.section,
            );
        window.addEventListener("popstate", restore);
        return () => window.removeEventListener("popstate", restore);
    }, [props.section]);
    useEffect(() => {
        if (!tabFocus.current) return;
        tabRefs.current.get(tabFocus.current)?.focus();
        tabFocus.current = null;
    }, [active?.name]);
    function moveTab(event: KeyboardEvent<HTMLButtonElement>, narrow: boolean) {
        if (event.altKey || event.ctrlKey || event.metaKey || !active) return;
        let next: number;
        const current = live.indexOf(active);
        if (event.key === "ArrowRight") next = (current + 1) % live.length;
        else if (event.key === "ArrowLeft")
            next = (current + live.length - 1) % live.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = live.length - 1;
        else return;
        event.preventDefault();
        if (live[next].name === active.name) return;
        tabFocus.current = `${narrow ? "narrow" : "wide"}:${live[next].name}`;
        chooseSection(live[next].name);
    }
    function tabs(narrow: boolean) {
        return (
            <div className={narrow ? recipe.narrowTabs : recipe.wideTabs}>
                <div
                    role="tablist"
                    aria-label="Profile sections"
                    className="contents"
                >
                    {live
                        .filter(
                            (section) =>
                                !narrow ||
                                live.length <= 2 ||
                                active?.name === section.name,
                        )
                        .map((section) => (
                            <button
                                key={section.name}
                                ref={(node) => {
                                    const key = `${narrow ? "narrow" : "wide"}:${section.name}`;
                                    if (node) tabRefs.current.set(key, node);
                                    else tabRefs.current.delete(key);
                                }}
                                type="button"
                                role="tab"
                                aria-selected={active?.name === section.name}
                                aria-controls={`${id}-panel`}
                                tabIndex={
                                    active?.name === section.name ? 0 : -1
                                }
                                onKeyDown={(event) => moveTab(event, narrow)}
                                onClick={() => chooseSection(section.name)}
                                className={`${recipe.tab} ${active?.name === section.name ? recipe.tabActive : recipe.tabInactive}`}
                            >
                                <span>{section.name}</span>
                                <span className={recipe.tabCount}>
                                    {section.count}
                                </span>
                            </button>
                        ))}
                </div>
                {narrow && live.length > 2 && (
                    <span className={recipe.moreSections}>
                        <QuickSwitcher
                            heading="Which section"
                            menuLabel="Other sections"
                            placeholder="Search sections"
                            align="end"
                            triggerWords={`+${live.length - 1} more`}
                            current={active?.name}
                            items={live.map((section) => ({
                                label: section.name,
                                value: section.name,
                            }))}
                            onChoose={chooseSection}
                        />
                    </span>
                )}
                <span className={recipe.tabEnd} aria-hidden="true" />
            </div>
        );
    }
    return (
        <div>
            <nav aria-label="Who can be hired" className="mb-4 flex flex-wrap">
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
            <div
                className={recipe.sticky}
                style={{ top: "var(--n26-sticky-top, 0px)" }}
            >
                <SearchBar
                    value={query}
                    onChange={setQuery}
                    label={`Search ${props.scopeLabel.toLowerCase()}`}
                />
                {(categoryOptions.length > 0 ||
                    props.priceCeiling > props.priceFloor) && (
                    <div className="flex flex-wrap items-center gap-2">
                        {categoryOptions.length > 0 && (
                            <FilterMenu
                                key={reset}
                                label="Category"
                                options={categoryOptions}
                                onApply={setCategories}
                            />
                        )}
                        {props.priceCeiling > props.priceFloor && (
                            <RangeMenu
                                label="Price"
                                min={props.priceFloor}
                                max={props.priceCeiling}
                                step={
                                    (props.priceCeiling - props.priceFloor) %
                                        5 ===
                                    0
                                        ? 5
                                        : 1
                                }
                                suffix="¢"
                                atMaxLabel="Any"
                                value={range}
                                onChange={setRange}
                            />
                        )}
                    </div>
                )}
                <div className={recipe.summary}>
                    <span role="status" aria-live="polite" aria-atomic="true">
                        <span className={recipe.summaryCount}>
                            {active?.count ?? 0}
                        </span>
                        {active && active.count !== active.total ? (
                            <> of {active.total}</>
                        ) : null}{" "}
                        {(active?.total ?? 0) === 1 ? "profile" : "profiles"}
                    </span>
                    {filtering && (
                        <button
                            type="button"
                            className={recipe.filterButton}
                            onClick={clear}
                        >
                            Clear filters
                        </button>
                    )}
                    <span className={recipe.summaryActions}>
                        <button
                            type="button"
                            className={recipe.filterButton}
                            onClick={() => toggleAll(true)}
                        >
                            Expand all
                        </button>
                        <button
                            type="button"
                            className={recipe.filterButton}
                            onClick={() => toggleAll(false)}
                        >
                            Collapse all
                        </button>
                    </span>
                </div>
                {live.length > 0 && (
                    <>
                        {tabs(false)}
                        {tabs(true)}
                    </>
                )}
            </div>
            {active ? (
                <section
                    role="tabpanel"
                    aria-label={active.name}
                    id={`${id}-panel`}
                >
                    {active.categories
                        .filter(
                            (category) =>
                                category.selected &&
                                category.matches.length > 0,
                        )
                        .map((category) => {
                            const key = `${active.sectionIndex}:${category.categoryIndex}`;
                            const open =
                                openCategories[key] !== false || !!query;
                            return (
                                <div key={key}>
                                    {category.name && (
                                        <button
                                            type="button"
                                            className={recipe.category}
                                            aria-expanded={open}
                                            onClick={() =>
                                                setOpenCategories(
                                                    (previous) => ({
                                                        ...previous,
                                                        [key]:
                                                            previous[key] ===
                                                            false,
                                                    }),
                                                )
                                            }
                                        >
                                            <span
                                                className={`${recipe.gutter} ${open ? "rotate-180" : ""}`}
                                            >
                                                <Icon
                                                    name="chevron-down"
                                                    strokeWidth={2}
                                                />
                                            </span>
                                            <span
                                                className={recipe.categoryName}
                                            >
                                                {category.name}
                                            </span>
                                            <span
                                                className={recipe.categoryCount}
                                                aria-hidden="true"
                                            >
                                                {category.matches.length}
                                            </span>
                                        </button>
                                    )}
                                    <div hidden={!!category.name && !open}>
                                        {category.matches.map((entry) => (
                                            <Row
                                                key={entry.key}
                                                entry={entry}
                                                selected={
                                                    selected[entry.key] ??
                                                    defaults(entry)
                                                }
                                                expanded={expanded.has(
                                                    entry.key,
                                                )}
                                                renderPreview={
                                                    props.renderPreview
                                                }
                                                onSelect={select}
                                                onExpand={expand}
                                            />
                                        ))}
                                    </div>
                                </div>
                            );
                        })}
                </section>
            ) : (
                <div className={recipe.empty}>
                    {filtering ? (
                        <>
                            Nothing matches those filters.{" "}
                            <button
                                type="button"
                                className={recipe.filterButton}
                                onClick={clear}
                            >
                                Clear them
                            </button>
                        </>
                    ) : (
                        "No profiles are available in this list. Choose another list."
                    )}
                </div>
            )}
        </div>
    );
}
