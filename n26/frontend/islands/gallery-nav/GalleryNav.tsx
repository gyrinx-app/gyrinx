import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Icon, ReactMark } from "../../ui";

type NavComponent = {
    slug: string;
    href: string;
    current: boolean;
    usesReact: boolean;
    parts: number;
    /** Lower-case text the filter matches against. */
    term: string;
};

export type GalleryNavProps = {
    pages: { label: string; href: string; current: boolean }[];
    shell: { label: string; href: string };
    groups: {
        name: string;
        href: string;
        current: boolean;
        components: NavComponent[];
    }[];
    query?: string;
    focused?: boolean;
};

const link = "rounded-control px-3 py-1.5 hover:bg-ink-500/10";

/**
 * The design gallery's sidebar: a filter over its component links.
 * designsystem/base.html draws the same classes as the fallback; change both.
 */
export function GalleryNav(props: GalleryNavProps) {
    const [query, setQuery] = useState(props.query ?? "");
    const filterRef = useRef<HTMLInputElement>(null);
    const navRef = useRef<HTMLElement>(null);
    const needle = query.trim().toLowerCase();
    const groups = props.groups
        .map((group) => ({
            ...group,
            components: group.components.filter(
                (component) => !query || component.term.includes(needle),
            ),
        }))
        .filter((group) => group.components.length > 0);

    useLayoutEffect(() => {
        if (props.focused) filterRef.current?.focus();
    }, [props.focused]);

    // The current component can be far down the list on a deep link.
    useEffect(() => {
        navRef.current
            ?.querySelector("[data-current]")
            ?.scrollIntoView({ block: "nearest" });
    }, []);

    return (
        <>
            <div className="border-b border-box-border px-4 py-3">
                <label htmlFor="component-filter" className="sr-only">
                    Filter components
                </label>
                <input
                    ref={filterRef}
                    id="component-filter"
                    type="search"
                    placeholder="Filter components…"
                    autoComplete="off"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    className="w-full rounded-control border border-box-border bg-input-bg px-3 py-1.5 text-sm placeholder:text-muted focus-ring"
                />
            </div>
            <nav
                ref={navRef}
                className="flex-1 overflow-y-auto px-3 py-4 text-sm"
            >
                {!query && (
                    <ul className="mb-5 space-y-0.5">
                        {props.pages.map((page) => (
                            <li key={page.href}>
                                <a
                                    href={page.href}
                                    aria-current={
                                        page.current ? "page" : undefined
                                    }
                                    className={`block font-medium ${link} ${page.current ? "nav-current" : ""}`}
                                >
                                    {page.label}
                                </a>
                            </li>
                        ))}
                        <li>
                            <a
                                href={props.shell.href}
                                className={`flex items-center gap-1.5 font-medium ${link}`}
                            >
                                {props.shell.label}
                                <Icon
                                    name="external-link"
                                    className="size-3.5 text-muted"
                                    strokeWidth={2}
                                />
                            </a>
                        </li>
                    </ul>
                )}
                {groups.map((group) => (
                    <div key={group.name} className="mb-5">
                        <a
                            href={group.href}
                            className={`flex items-center gap-1.5 rounded-control px-3 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-wider hover:text-ink-900 dark:hover:text-ink-100 ${group.current ? "text-ink-900 dark:text-ink-100" : "text-muted"}`}
                        >
                            {group.name}
                        </a>
                        <ul className="space-y-0.5">
                            {group.components.map((component) => (
                                <li key={component.slug}>
                                    <a
                                        href={component.href}
                                        aria-current={
                                            component.current
                                                ? "page"
                                                : undefined
                                        }
                                        data-current={
                                            component.current ? "" : undefined
                                        }
                                        className={`flex items-center justify-between gap-2 ${link} ${component.current ? "nav-current" : ""}`}
                                    >
                                        <span className="flex min-w-0 items-center gap-1.5">
                                            <span className="truncate">
                                                {component.slug}
                                            </span>
                                            {component.usesReact && (
                                                <ReactMark />
                                            )}
                                        </span>
                                        {component.parts > 0 && (
                                            <span className="text-[10px] text-muted">
                                                +{component.parts}
                                            </span>
                                        )}
                                    </a>
                                </li>
                            ))}
                        </ul>
                    </div>
                ))}
                {query && groups.length === 0 && (
                    <p className="px-3 py-2 text-sm text-muted">
                        Nothing matches “{query}”.
                    </p>
                )}
            </nav>
        </>
    );
}
