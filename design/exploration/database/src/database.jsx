import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
    Search,
    X,
    ArrowRight,
    ChevronDown,
    Users,
    Swords,
    Wrench,
    BicepsFlexed,
    Map,
    Sparkles,
    Medal,
    Database,
    SunMoon,
    CornerDownLeft,
    Backpack,
    HeartPulse,
    Dice1,
    Dice2,
    Dice3,
    Dice4,
    Dice5,
    Dice6,
} from "lucide-react";
import { Button, Icon } from "./controls.jsx";
import cotton from "./cotton.json";
import { Cotton } from "./cotton-tree.jsx";
import base from "./presentation.json";
import { ModelName } from "./model-name.jsx";
import { nameplateEdge } from "./nameplate-edge.js";
function DatabaseCotton({ name, ...props }) {
    return <Cotton tree={base[name]} {...props} />;
}
import { categories, entries, searchEntries } from "./database-data.js";
const icons = {
    profiles: Users,
    weapons: Swords,
    accessories: Wrench,
    gear: Backpack,
    injuries: HeartPulse,
    skills: BicepsFlexed,
    territories: Map,
    powers: Sparkles,
    ranks: Medal,
};
const readURL = () => {
    const p = new URLSearchParams(location.search);
    return {
        query: p.get("q") || "",
        category: categories.some(([id]) => id === p.get("category"))
            ? p.get("category")
            : "all",
        entry: p.get("entry") || "",
    };
};
const label = (id) =>
    categories.find(([key]) => key === id)?.[1] || "All categories";
function Badge({ children }) {
    return <span className={cotton.badge}>{children}</span>;
}
function Disclosure({ title, children, open = false }) {
    return (
        <details className="db-disclosure" open={open || undefined}>
            <summary>
                {title}
                <Icon icon={ChevronDown} size={15} />
            </summary>
            <div className="db-disclosure-body">{children}</div>
        </details>
    );
}
const dice = [null, Dice1, Dice2, Dice3, Dice4, Dice5, Dice6];
function Roll({ value, kind = "D6" }) {
    const result = String(value);
    return (
        <span
            className="db-roll"
            role="img"
            aria-label={`${kind} result ${result}`}
            title={`${kind} result ${result}`}
        >
            {[...result].map((n, i) => (
                <Icon key={i} icon={dice[Number(n)]} size={20} />
            ))}
        </span>
    );
}
function Modifiers({ modifiers }) {
    if (!modifiers?.length) return null;
    const verbs = {
        increase: "Increases",
        reduce: "Reduces",
        improve: "Improves",
        worsen: "Worsens",
        set: "Sets",
    };
    return (
        <div className="db-modifiers">
            <h4>Modifiers</h4>
            <ul>
                {modifiers.map((m, i) => (
                    <li key={i}>
                        <span>
                            {verbs[m.mode]} {m.stat}{" "}
                            {m.mode === "set" ? "to" : "by"} {m.amount}.
                        </span>
                        <small>{m.scope}</small>
                    </li>
                ))}
            </ul>
        </div>
    );
}
const houseColours = {
    "House Escher": "violet",
    "House Goliath": "red",
    "House Orlock": "blue",
    "House Delaque": "slate",
    "House Van Saar": "green",
    "House Cawdor": "amber",
};
function ReferenceFrame({ item, selected, children }) {
    const colour = houseColours[item.set] || "amber";
    return (
        <article
            id={item.id}
            tabIndex={-1}
            data-striped=""
            className={`${cotton.card} gang-card gang-material gang-new callout-frame db-card db-reference-card ${item.category === "profiles" ? "db-model" : "db-weapon"} ${selected?.id === item.id ? "db-selected" : ""}`}
            style={{
                "--gang-theme": `var(--color-${colour}-500)`,
                "--nameplate-edge": nameplateEdge(item.name, true),
            }}
        >
            <header className="gang-card-header">
                <div className="gang-card-title">
                    <ModelName model={{ name: item.name, type: item.set }} />
                    <div className="gang-header-marks">
                        <span className="gang-portrait-placeholder db-reference-symbol">
                            <Icon icon={icons[item.category]} size={25} />
                        </span>
                        <span
                            className="gang-rating"
                            title="Example base price"
                        >
                            {item.price}¢
                        </span>
                    </div>
                </div>
            </header>
            <div className="gang-card-controls db-reference-controls">
                <span>
                    {item.category === "profiles"
                        ? "Characteristics"
                        : "Weapon profiles"}
                </span>
            </div>
            <div className="gang-card-panel db-reference-body">{children}</div>
        </article>
    );
}
function WeaponProfiles({ item, onTrait }) {
    const own = item.profiles.find((p) => p.name === "Standard");
    const named = item.profiles.filter((p) => p !== own);
    const stats = (p) =>
        Object.fromEntries(
            p.values.map((v, i) => [`VALUE_${String.fromCharCode(65 + i)}`, v]),
        );
    const traits = (p) => (
        <tr className="db-nested-traits">
            <td></td>
            <td colSpan={5}>
                {p.traits.map((t, i) => (
                    <React.Fragment key={t}>
                        {i > 0 && " · "}
                        <button onClick={() => onTrait(t)}>{t}</button>
                    </React.Fragment>
                ))}
            </td>
        </tr>
    );
    return (
        <div className="gang-weapons db-nested-weapons">
            <table aria-label={`${item.name} weapon profiles`}>
                <thead>
                    <DatabaseCotton name="weaponHeader" />
                </thead>
                <tbody>
                    {own ? (
                        <>
                            <DatabaseCotton
                                name="weaponRow"
                                bindings={stats(own)}
                                slots={{ "profile-name": item.name }}
                            />
                            {traits(own)}
                        </>
                    ) : (
                        <tr className="db-parent-weapon">
                            <th scope="row" colSpan={6}>
                                {item.name}
                            </th>
                        </tr>
                    )}
                    {named.map((p) => (
                        <React.Fragment key={p.name}>
                            <DatabaseCotton
                                name="weaponRow"
                                bindings={stats(p)}
                                slots={{
                                    "profile-name": (
                                        <span className="db-nested-profile">
                                            <span aria-hidden="true">−</span>
                                            <span>
                                                {p.name}
                                                {p.price > 0 && (
                                                    <small>+{p.price}¢</small>
                                                )}
                                            </span>
                                        </span>
                                    ),
                                }}
                            />
                            {traits(p)}
                        </React.Fragment>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
function Card({ item, selected, related, facts, onTrait }) {
    const defaults = entries.filter(
        (e) => e.category === "profiles" && e.related?.includes(item.id),
    );
    const model = item.category === "profiles",
        weapon = item.category === "weapons";
    const metadata = (
        <>
            {defaults.length > 0 && (
                <Disclosure title={`Built into profiles (${defaults.length})`}>
                    {defaults.map((p) => related(p.id))}
                </Disclosure>
            )}
            {item.levels && (
                <Disclosure title={`Rank thresholds (${item.levels.length})`}>
                    <dl className="db-facts">
                        {item.levels.map(([n, title]) => (
                            <div key={n}>
                                <dt>{n}</dt>
                                <dd>{title}</dd>
                            </div>
                        ))}
                    </dl>
                </Disclosure>
            )}
            <Disclosure title={model ? "Profile details" : "Details"}>
                {facts(item)}
                {["skills", "powers"].includes(item.category) &&
                    !defaults.length && (
                        <p className="text-sm text-muted">
                            No built-in profile links in this example pack.
                        </p>
                    )}
            </Disclosure>
        </>
    );
    if (model || weapon)
        return (
            <ReferenceFrame item={item} selected={selected}>
                {model ? (
                    <DatabaseCotton
                        name="modelBody"
                        bindings={{
                            NAME: item.name,
                            HOUSE: item.set,
                            MODEL_ID: item.id,
                            TYPE: `Fighter (${item.type})`,
                            ...Object.fromEntries(
                                item.stats.map((v, i) => [
                                    `STAT_${String.fromCharCode(65 + i)}`,
                                    v,
                                ]),
                            ),
                        }}
                        slots={{
                            skills: item.related.length ? (
                                item.related.map(related)
                            ) : (
                                <span className="text-muted">
                                    None built in
                                </span>
                            ),
                            gear: (
                                <span className="text-muted">
                                    None built in
                                </span>
                            ),
                            details: metadata,
                        }}
                    />
                ) : (
                    <>
                        <WeaponProfiles item={item} onTrait={onTrait} />
                        <div className="db-entry-summary text-xs text-muted">
                            {item.slots} weapon slot · {item.profiles.length}{" "}
                            {item.profiles.length === 1
                                ? "profile"
                                : "profiles"}
                        </div>
                        {metadata}
                    </>
                )}
            </ReferenceFrame>
        );
    const header = (
        <div className="db-entry-heading">
            <div>
                <h3 className="text-base font-semibold">{item.name}</h3>
                <p className="mt-1 text-sm text-muted">{item.set}</p>
            </div>
            {item.price !== undefined ? (
                <span className="db-price" title="Example base price">
                    {item.price}¢
                </span>
            ) : item.number ? (
                <Roll value={item.number} />
            ) : item.roll ? (
                <Roll value={item.roll} kind="D66" />
            ) : null}
        </div>
    );
    return (
        <article
            id={item.id}
            tabIndex={-1}
            className={`db-card ${selected?.id === item.id ? "db-selected" : ""}`}
        >
            <DatabaseCotton
                name="card"
                slots={{
                    header,
                    content: (
                        <>
                            {!item.number && !item.modifiers?.length && (
                                <div className="db-entry-summary text-sm text-muted">
                                    {item.applies ||
                                        item.type ||
                                        `${item.levels?.length || 0} thresholds · ${item.counter}`}
                                </div>
                            )}
                            <Modifiers modifiers={item.modifiers} />
                            {metadata}
                        </>
                    ),
                }}
            />
        </article>
    );
}
function App() {
    const [state, setState] = useState(readURL),
        [set, setSet] = useState("all"),
        [dark, setDark] = useState(false),
        [suggest, setSuggest] = useState(false),
        [active, setActive] = useState(-1),
        [limits, setLimits] = useState({});
    const input = useRef(),
        searchBox = useRef();
    const { query, category, entry } = state;
    const idle = category === "all" && !query.trim();
    const selected = entries.find((e) => e.id === entry);
    const matches = searchEntries(query),
        visible = matches.filter(
            (e) =>
                (category === "all" || e.category === category) &&
                (set === "all" || e.set === set),
        );
    const suggestions = query.trim()
        ? matches.slice(0, 6)
        : ["Escher", "Agility", "Plasma", "Toxin", "Shotgun"];
    function navigate(next, replace = false) {
        const fresh = { ...state, ...next };
        const p = new URLSearchParams();
        if (fresh.query) p.set("q", fresh.query);
        if (fresh.category !== "all") p.set("category", fresh.category);
        if (fresh.entry) p.set("entry", fresh.entry);
        history[replace ? "replaceState" : "pushState"](
            null,
            "",
            `${location.pathname}${p.size ? "?" + p : ""}`,
        );
        setState(fresh);
        setLimits({});
        if (next.category !== undefined) setSet("all");
    }
    useEffect(() => {
        const pop = () => {
            setState(readURL());
            setSet("all");
            setSuggest(false);
        };
        const shortcut = (e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "k") {
                e.preventDefault();
                input.current.focus();
                input.current.select();
            }
            if (e.key === "Escape") {
                setSuggest(false);
                setActive(-1);
            }
        };
        const outside = (e) => {
            if (!e.composedPath().includes(searchBox.current))
                setSuggest(false);
        };
        window.addEventListener("popstate", pop);
        document.addEventListener("keydown", shortcut);
        document.addEventListener("pointerdown", outside);
        return () => {
            window.removeEventListener("popstate", pop);
            document.removeEventListener("keydown", shortcut);
            document.removeEventListener("pointerdown", outside);
        };
    }, []);
    useEffect(() => {
        document.documentElement.style.colorScheme = dark ? "dark" : "light";
        document.querySelector("#database-root").classList.toggle("dark", dark);
    }, [dark]);
    useEffect(() => {
        if (!selected) return;
        const node = document
            .querySelector("#database-root")
            .shadowRoot.getElementById(selected.id);
        if (node) {
            node.querySelector("details")?.setAttribute("open", "");
            node.scrollIntoView({ block: "center", behavior: "instant" });
            node.focus({ preventScroll: true });
        }
    }, [entry]);
    function openEntry(item) {
        setSet("all");
        navigate({ query: "", category: item.category, entry: item.id });
        setSuggest(false);
        setActive(-1);
    }
    function choose(value) {
        if (typeof value === "string")
            navigate({ query: value, category: "all", entry: "" });
        else openEntry(value);
        setSuggest(false);
        setActive(-1);
    }
    function related(id) {
        const item = entries.find((e) => e.id === id);
        return item ? (
            <button
                key={id}
                className="db-related"
                onClick={() => openEntry(item)}
            >
                {item.name}
                <Icon icon={ArrowRight} size={14} />
            </button>
        ) : null;
    }
    function facts(item) {
        const values = [
            ["Content pack", item.pack],
            ...(item.metadata || []),
            ...(item.applies ? [["Applies to", item.applies]] : []),
        ];
        return (
            <dl className="db-facts">
                {values.map(([key, value]) => (
                    <div key={key}>
                        <dt>{key}</dt>
                        <dd>{value}</dd>
                    </div>
                ))}
            </dl>
        );
    }

    const availableSets = [
        ...new Set(
            entries
                .filter((e) => category === "all" || e.category === category)
                .map((e) => e.set),
        ),
    ].sort();
    return (
        <div className={`db-page ${dark ? "dark" : ""}`}>
            <style>{base.layoutStyle.replaceAll(":root", ".db-page")}</style>
            <Cotton
                tree={base.nav}
                slots={{
                    switcher: (
                        <span className="text-sm text-ink-100">Database</span>
                    ),
                    actions: (
                        <Button
                            icon={SunMoon}
                            title="Switch colour theme"
                            aria-label="Switch colour theme"
                            onClick={() => setDark(!dark)}
                        />
                    ),
                    navigation: (
                        <div className="db-site-links">
                            <a href="?category=profiles">Profiles</a>
                            <a href="?category=weapons">Weapons</a>
                        </div>
                    ),
                }}
            />
            <main className={`${base.layout.attrs.class} db-main`}>
                <DatabaseCotton
                    name="header"
                    slots={{ actions: <Badge>Example content</Badge> }}
                />
                <div className="db-search-area" ref={searchBox}>
                    <form
                        role="search"
                        onSubmit={(e) => {
                            e.preventDefault();
                            if (active >= 0 && suggestions[active])
                                choose(suggestions[active]);
                            else setSuggest(false);
                        }}
                    >
                        <div className={`${cotton.search.field} db-search`}>
                            <span className={cotton.search.icon}>
                                <Icon icon={Search} size={22} />
                            </span>
                            <input
                                ref={input}
                                className={cotton.search.input}
                                value={query}
                                placeholder="Search names, skill sets, weapon traits…"
                                aria-label="Search database"
                                role="combobox"
                                aria-autocomplete="list"
                                aria-expanded={suggest}
                                aria-controls="database-suggestions"
                                aria-activedescendant={
                                    active >= 0
                                        ? `db-suggestion-${active}`
                                        : undefined
                                }
                                onFocus={() => setSuggest(true)}
                                onChange={(e) => {
                                    navigate(
                                        { query: e.target.value, entry: "" },
                                        true,
                                    );
                                    setSuggest(true);
                                    setActive(-1);
                                }}
                                onKeyDown={(e) => {
                                    if (e.key === "ArrowDown") {
                                        e.preventDefault();
                                        setSuggest(true);
                                        setActive((v) =>
                                            Math.min(
                                                v + 1,
                                                suggestions.length - 1,
                                            ),
                                        );
                                    }
                                    if (e.key === "ArrowUp") {
                                        e.preventDefault();
                                        setActive((v) => Math.max(v - 1, 0));
                                    }
                                    if (e.key === "Escape") {
                                        e.preventDefault();
                                        setSuggest(false);
                                        setActive(-1);
                                    }
                                    if (e.key === "Tab") setSuggest(false);
                                }}
                            />
                            {query ? (
                                <Button
                                    icon={X}
                                    title="Clear search"
                                    aria-label="Clear search"
                                    onClick={() => {
                                        navigate({ query: "", entry: "" });
                                        input.current.focus();
                                        setActive(-1);
                                    }}
                                />
                            ) : (
                                <kbd>⌘ K</kbd>
                            )}
                        </div>
                    </form>
                    {suggest && (
                        <div className="db-suggestions">
                            <div className="db-suggestion-label">
                                {query
                                    ? "Matching entries"
                                    : "Suggested searches"}
                            </div>
                            <ul
                                role="listbox"
                                id="database-suggestions"
                                aria-label="Suggested searches"
                            >
                                {suggestions.map((value, i) => (
                                    <li
                                        key={
                                            typeof value === "string"
                                                ? value
                                                : value.id
                                        }
                                        id={`db-suggestion-${i}`}
                                        role="option"
                                        aria-selected={active === i}
                                        onPointerDown={(e) =>
                                            e.preventDefault()
                                        }
                                        onMouseMove={() => setActive(i)}
                                        onClick={() => choose(value)}
                                    >
                                        <Icon
                                            icon={
                                                typeof value === "string"
                                                    ? Search
                                                    : icons[value.category]
                                            }
                                            size={17}
                                        />
                                        <span>
                                            {typeof value === "string"
                                                ? value
                                                : value.name}
                                        </span>
                                        <small>
                                            {typeof value === "string"
                                                ? "Search"
                                                : label(value.category)}
                                        </small>
                                        <Icon icon={CornerDownLeft} size={14} />
                                    </li>
                                ))}
                            </ul>
                            {!suggestions.length && (
                                <p>
                                    No matching suggestions. Try a shorter
                                    search.
                                </p>
                            )}
                        </div>
                    )}
                </div>
                <div className="db-quick">
                    <span>Try</span>
                    {["Escher", "Agility", "Plasma", "Toxin"].map((q) => (
                        <button
                            key={q}
                            onClick={() => {
                                navigate({
                                    query: q,
                                    category: "all",
                                    entry: "",
                                });
                                setSet("all");
                                setSuggest(false);
                            }}
                        >
                            {q}
                            <Icon icon={ArrowRight} size={12} />
                        </button>
                    ))}
                </div>
                <div className="db-layout">
                    <aside>
                        <nav aria-label="Database categories">
                            <div className="db-eyebrow">Browse</div>
                            {[["all", "All categories"], ...categories].map(
                                ([id, name]) => (
                                    <a
                                        key={id}
                                        aria-current={
                                            category === id ? "page" : undefined
                                        }
                                        href={
                                            id === "all"
                                                ? "/database/"
                                                : `?category=${id}${query ? `&q=${encodeURIComponent(query)}` : ""}`
                                        }
                                        onClick={(e) => {
                                            e.preventDefault();
                                            navigate({
                                                category: id,
                                                entry: "",
                                            });
                                            setSuggest(false);
                                        }}
                                    >
                                        <Icon
                                            icon={
                                                id === "all"
                                                    ? Database
                                                    : icons[id]
                                            }
                                            size={18}
                                        />
                                        <span>{name}</span>
                                        <small>
                                            {id === "all"
                                                ? matches.length
                                                : matches.filter(
                                                      (e) => e.category === id,
                                                  ).length}
                                        </small>
                                    </a>
                                ),
                            )}
                        </nav>
                        <p className="db-aside-note">
                            Search across categories, or browse one at a time.
                        </p>
                    </aside>
                    <div className="db-results">
                        {!idle && (
                            <div className="db-results-bar">
                                <div>
                                    <h2>
                                        {query
                                            ? `Results for “${query}”`
                                            : category === "all"
                                              ? "Browse the database"
                                              : label(category)}
                                    </h2>
                                    <p role="status" aria-live="polite">
                                        {visible.length}{" "}
                                        {visible.length === 1
                                            ? "entry"
                                            : "entries"}
                                        {category === "all"
                                            ? " across all categories"
                                            : ""}
                                    </p>
                                </div>
                                {category !== "all" && (
                                    <label className="db-filter">
                                        <span className="sr-only">
                                            Filter by set
                                        </span>
                                        <select
                                            aria-label="Filter by set"
                                            className={cotton.select.className}
                                            style={cotton.select.style}
                                            value={set}
                                            onChange={(e) => {
                                                setSet(e.target.value);
                                                setLimits({});
                                            }}
                                        >
                                            <option value="all">
                                                All sets
                                            </option>
                                            {availableSets.map((s) => (
                                                <option key={s}>{s}</option>
                                            ))}
                                        </select>
                                    </label>
                                )}
                            </div>
                        )}
                        {idle ? (
                            <div className="db-search-prompt">
                                <Icon icon={Search} size={36} />
                                <h2>What are you looking for?</h2>
                                <p>
                                    Search for a name, skill set, weapon trait
                                    or characteristic.
                                </p>
                                <p className="text-sm text-muted">
                                    You can also select a category to browse its
                                    entries.
                                </p>
                                <Button
                                    variant="primary"
                                    icon={Search}
                                    onClick={() => input.current.focus()}
                                >
                                    Search the database
                                </Button>
                            </div>
                        ) : !visible.length ? (
                            <div className="db-empty">
                                <Icon icon={Search} size={32} />
                                <h3>No entries found</h3>
                                <p>Try a shorter name or another category.</p>
                                <Button
                                    variant="default"
                                    onClick={() => {
                                        navigate({
                                            query: "",
                                            category: "all",
                                            entry: "",
                                        });
                                        setSet("all");
                                    }}
                                >
                                    Clear filters
                                </Button>
                            </div>
                        ) : (
                            categories
                                .filter(
                                    ([id]) =>
                                        category === "all" || id === category,
                                )
                                .map(([id, name]) => {
                                    const items = visible.filter(
                                        (e) => e.category === id,
                                    );
                                    if (!items.length) return null;
                                    const limit =
                                        limits[id] ||
                                        (category === "all" ? 2 : 12);
                                    const shown =
                                        selected?.category === id &&
                                        !items
                                            .slice(0, limit)
                                            .includes(selected)
                                            ? [
                                                  selected,
                                                  ...items
                                                      .filter(
                                                          (e) =>
                                                              e.id !==
                                                              selected.id,
                                                      )
                                                      .slice(0, limit - 1),
                                              ]
                                            : items.slice(0, limit);
                                    return (
                                        <DatabaseCotton
                                            key={id}
                                            name={
                                                category === "all"
                                                    ? "section"
                                                    : "results"
                                            }
                                            bindings={{
                                                TITLE: name,
                                                COUNT: items.length,
                                                SECTION_ID: `heading-${id}`,
                                            }}
                                            slots={{
                                                actions:
                                                    category === "all" ? (
                                                        <Button
                                                            variant="text"
                                                            icon={ArrowRight}
                                                            onClick={() =>
                                                                navigate({
                                                                    category:
                                                                        id,
                                                                    entry: "",
                                                                })
                                                            }
                                                        >
                                                            View all
                                                        </Button>
                                                    ) : null,
                                                content: (
                                                    <>
                                                        <div className="db-grid">
                                                            {shown.map(
                                                                (item) => (
                                                                    <Card
                                                                        key={
                                                                            item.id
                                                                        }
                                                                        item={
                                                                            item
                                                                        }
                                                                        selected={
                                                                            selected
                                                                        }
                                                                        related={
                                                                            related
                                                                        }
                                                                        facts={
                                                                            facts
                                                                        }
                                                                        onTrait={(
                                                                            t,
                                                                        ) => {
                                                                            navigate(
                                                                                {
                                                                                    query: t,
                                                                                    category:
                                                                                        "all",
                                                                                    entry: "",
                                                                                },
                                                                            );
                                                                            setSet(
                                                                                "all",
                                                                            );
                                                                        }}
                                                                    />
                                                                ),
                                                            )}
                                                        </div>
                                                        {items.length > limit &&
                                                            category !==
                                                                "all" && (
                                                                <div className="db-load">
                                                                    <Button
                                                                        variant="default"
                                                                        onClick={() =>
                                                                            setLimits(
                                                                                {
                                                                                    ...limits,
                                                                                    [id]:
                                                                                        limit +
                                                                                        12,
                                                                                },
                                                                            )
                                                                        }
                                                                    >
                                                                        Show
                                                                        more (
                                                                        {items.length -
                                                                            limit}{" "}
                                                                        remaining)
                                                                    </Button>
                                                                </div>
                                                            )}
                                                    </>
                                                ),
                                            }}
                                        />
                                    );
                                })
                        )}
                    </div>
                </div>
                <footer className="db-footer">
                    Design preview · {entries.length} example entries.
                    Statistics, prices and built-in relationships are
                    illustrative.
                </footer>
            </main>
        </div>
    );
}
const host = document.querySelector("#database-root"),
    shadow = host.attachShadow({ mode: "open" }),
    style = document.createElement("link");
style.rel = "stylesheet";
style.href = host.dataset.themeUrl;
shadow.append(style);
const root = document.createElement("div");
shadow.append(root);
createRoot(root).render(<App />);
