import {
    Fragment,
    useEffect,
    useId,
    useMemo,
    useRef,
    useState,
    type KeyboardEvent,
    type ReactNode,
} from "react";
import cotton from "../generated/cotton.json";
import { FilterMenu, Icon, QuickSwitcher, RangeMenu, SearchBar } from "./index";

export type CatalogueEntry = {
    key: string;
    name: string;
    keywords?: string;
    basePrice: number;
    tradePoints?: number | null;
    exclusive?: boolean;
};
export type CatalogueSection<T> = {
    name: string;
    categories: Array<{ name: string; entries: T[] }>;
};
export type CatalogueFrameProps<T extends CatalogueEntry> = {
    scopeLabel: string;
    section: string;
    priceFloor: number;
    priceCeiling: number;
    categories: string[];
    categoryOptions: string[];
    sections: CatalogueSection<T>[];
    tradePointsCeiling?: number;
    hasTradePoints?: boolean;
    filters?: boolean;
    noun: string;
    plural: string;
    sectionLabel: string;
    empty: string;
    categoriesOpen?: boolean;
    navigation?: ReactNode;
    renderEntry: (entry: T) => ReactNode;
};
const recipe = cotton.hireCatalogue;

export function CatalogueFrame<T extends CatalogueEntry>(
    props: CatalogueFrameProps<T>,
) {
    const id = useId();
    const [query, setQuery] = useState("");
    const [categories, setCategories] = useState(props.categories);
    const [range, setRange] = useState<[number, number]>([
        props.priceFloor,
        props.priceCeiling,
    ]);
    const [maxPoints, setMaxPoints] = useState(props.tradePointsCeiling ?? 0);
    const [chosen, setChosen] = useState(props.section);
    const [reset, setReset] = useState(0);
    const [openCategories, setOpenCategories] = useState<
        Record<string, boolean>
    >({});
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
                                            entry.keywords,
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
                                    entry.basePrice <= range[1] &&
                                    (!!entry.exclusive ||
                                        (entry.tradePoints ?? 0) <= maxPoints),
                            ),
                            selected:
                                props.filters === false ||
                                !category.name ||
                                categories.includes(category.name),
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
        [props.sections, props.filters, query, categories, range, maxPoints],
    );
    const live = allSections.filter((section) => section.count > 0);
    const active = live.find((section) => section.name === chosen) ?? live[0];
    const filtering =
        props.filters !== false &&
        (!!query ||
            categories.length !== props.categories.length ||
            range[0] > props.priceFloor ||
            range[1] < props.priceCeiling ||
            maxPoints < (props.tradePointsCeiling ?? 0));
    const categoryOptions = useMemo(
        () =>
            props.categoryOptions.map((name) => ({ value: name, label: name })),
        [props.categoryOptions],
    );
    function clear() {
        setQuery("");
        setCategories(props.categories);
        setRange([props.priceFloor, props.priceCeiling]);
        setMaxPoints(props.tradePointsCeiling ?? 0);
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
                    aria-label={props.sectionLabel}
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
            {props.navigation}
            <div
                className={recipe.sticky}
                style={{ top: "var(--n26-sticky-top, 0px)" }}
            >
                {props.filters !== false && (
                    <>
                        <SearchBar
                            value={query}
                            onChange={setQuery}
                            label={`Search ${props.scopeLabel.toLowerCase()}`}
                        />
                        {(categoryOptions.length > 0 ||
                            props.priceCeiling > props.priceFloor ||
                            props.hasTradePoints) && (
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
                                            (props.priceCeiling -
                                                props.priceFloor) %
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
                                {props.hasTradePoints && (
                                    <RangeMenu
                                        label="Trade points"
                                        min={0}
                                        max={props.tradePointsCeiling ?? 0}
                                        step={1}
                                        prefix="≤ "
                                        atMinLabel="Freely available"
                                        atMaxLabel="Any"
                                        maximumOnly
                                        value={[0, maxPoints]}
                                        onChange={([, maximum]) =>
                                            setMaxPoints(maximum)
                                        }
                                    />
                                )}
                            </div>
                        )}
                    </>
                )}
                <div className={recipe.summary}>
                    <span role="status" aria-live="polite" aria-atomic="true">
                        <span className={recipe.summaryCount}>
                            {active?.count ?? 0}
                        </span>
                        {active && active.count !== active.total ? (
                            <> of {active.total}</>
                        ) : null}{" "}
                        {(active?.total ?? 0) === 1 ? props.noun : props.plural}
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
                                (openCategories[key] ??
                                    props.categoriesOpen !== false) ||
                                !!query;
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
                                                        [key]: !open,
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
                                            <Fragment key={entry.key}>
                                                {props.renderEntry(entry)}
                                            </Fragment>
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
                        props.empty
                    )}
                </div>
            )}
        </div>
    );
}
